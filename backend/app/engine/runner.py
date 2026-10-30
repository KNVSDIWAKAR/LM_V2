"""Runs playbooks against loans and keeps every table consistent.

    run_stage()          one agent run: one stage's graph for one loan (always inside a workflow)
    resume()             a person decided on a Decision Inbox item → continue the paused agent run
    start_workflow()     carry one loan end to end, from the first stage it has not passed
    advance_workflow()   keep going until all five stages are done or something stops it
    continue_at_stage()  the process page's Run button: move a loan that is waiting at a stage

Every agent run belongs to a workflow run, so a loan is only ever worked down one path.

Everything a run decides is written in the same place every time:
    agent_runs   status, trace, output (findings, sensors, result), saved state while paused
    lm_stages    the stage status and remark for the loan
    decisions    one pending item per pause
    workflow_runs current stage, status and a plain-words outcome
Callers commit; each public function leaves the session ready to commit.
"""

import threading
import uuid
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from . import sensors
from .playbook import Deps, Playbook, get_playbook
from .trial_support import approve_plan, decline_plans

ACTIVE = ("running", "paused")

# Non-advancing statuses that are evaluated again on the next Run (a new monitoring cycle,
# or Final Mod checks once QC / recording has been recorded).
RERUNNABLE: dict[int, tuple[str, ...]] = {4: ("Within Plan", "Delayed Payment"), 5: ("Sign Off & In Progress",)}

# Context keys a stage exposes in agent_runs.output["stage_report"] for its case page.
REPORT_KEYS = ("retention", "terms", "options", "plans", "plan", "installments", "payments_considered",
               "lmt_note", "uw_results", "handoff", "final_mod")

# One lock per loan: the scheduler, the Run buttons and the Decision Inbox can all act on a
# loan, but never at the same time.
_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
_locks_guard = threading.Lock()


def loan_lock(loan_id: str) -> threading.Lock:
    with _locks_guard:
        return _locks[loan_id]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _finish(run: models.AgentRun | models.WorkflowRun, status: str) -> None:
    run.status = status
    run.finished_at = now_utc()
    run.duration_ms = int((run.finished_at - as_utc(run.started_at)).total_seconds() * 1000)


def set_stage_status(db: Session, loan_id: str, stage_no: int, status: str | None, remark: str) -> None:
    stage = models.STAGE_BY_NO[stage_no]
    row = db.get(models.LmStages, loan_id) or models.LmStages(loan_id=loan_id)
    setattr(row, f"{stage.key}_status", status)
    setattr(row, f"{stage.key}_remark", remark)
    row.updated_at = now_utc()
    db.add(row)


def stage_status(db: Session, loan_id: str, stage_no: int) -> str | None:
    row = db.get(models.LmStages, loan_id)
    return getattr(row, f"{models.STAGE_BY_NO[stage_no].key}_status") if row else None


def first_open_stage(row: models.LmStages | None) -> int:
    """The first stage this loan has not been handed on from (6 when all five are done)."""
    for stage in models.STAGES:
        if (getattr(row, f"{stage.key}_status") if row else None) not in stage.advances:
            return stage.no
    return len(models.STAGES) + 1


def stage_position(row: models.LmStages | None, stage: models.Stage, has_documents: bool) -> str:
    """Where a loan stands at one stage: 'worked', 'waiting' (handed on, not yet worked) or 'not_reached'."""
    if row is not None and getattr(row, f"{stage.key}_status"):
        return "worked"
    if stage.no == 1:
        return "waiting" if has_documents else "not_reached"
    prev = models.STAGE_BY_NO[stage.no - 1]
    return "waiting" if row is not None and getattr(row, f"{prev.key}_status") in prev.advances else "not_reached"


def _hand_on(db: Session, loan_id: str, from_stage: models.Stage) -> None:
    """Record on the next stage that the loan has arrived and is waiting to be worked."""
    nxt = models.STAGE_BY_NO.get(from_stage.no + 1)
    if nxt is None or stage_status(db, loan_id, nxt.no):
        return
    set_stage_status(db, loan_id, nxt.no, None, f"Waiting — handed on from {from_stage.name} on {now_utc():%Y-%m-%d %H:%M} UTC")


# --------------------------------------------------------------------------- #
# One stage
# --------------------------------------------------------------------------- #


def _execute(db: Session, run: models.AgentRun, pb: Playbook, state: dict[str, Any]) -> None:
    """Invoke the graph from `state` and record whatever it ends with."""
    now = now_utc()
    run.status = "running"
    try:
        config = {"configurable": {"deps": Deps(db=db, rules=pb.rules, now=now)}}
        if "recursion_limit" in pb.rules.get("engine", {}):
            config["recursion_limit"] = pb.rules["engine"]["recursion_limit"]
        final = pb.graph.invoke(state, config=config)
    except Exception as err:  # noqa: BLE001 — a failed run is recorded, never lost
        run.error = f"{type(err).__name__}: {err}"
        run.trace = list(state.get("trace", []))
        _finish(run, "failed")
        return

    run.trace = final.get("trace", [])
    context = final.get("context") or {}
    stage_report = {key: deepcopy(context[key]) for key in REPORT_KEYS if key in context}
    report_payload = {"stage_report": stage_report} if stage_report else {}
    paused = final.get("paused")
    if paused:
        run.state = {k: v for k, v in final.items() if k not in ("next", "paused")}
        run.output = {"paused_at": paused, "findings": final.get("findings", []), "rules_version": pb.rules_version, **report_payload}
        if (final.get("context") or {}).get("report") is not None:
            run.output["report"] = {**final["context"]["report"], "verdict": paused["status"], "dm712_required": False}
        run.status = "paused"
        set_stage_status(db, run.loan_id, pb.stage_no, paused["status"], f"Waiting for {paused['team']}: {paused['reason']}"[:1000])
        db.add(
            models.Decision(
                id=f"dc-{uuid.uuid4().hex[:12]}",
                loan_id=run.loan_id,
                agent_run_id=run.id,
                workflow_run_id=run.workflow_run_id,
                stage_no=pb.stage_no,
                gate=paused["gate"],
                team=paused["team"],
                title=f"{pb.spec.name}: {paused['title'].split('·', 1)[-1].strip()} — loan {run.loan_id}",
                reason=paused["reason"],
                findings=[f for f in final.get("findings", []) if f.get("result") != "pass"],
                status="pending",
                created_at=now,
            )
        )
        return

    readings, override = sensors.evaluate(final, pb.rules, now)
    result = override or final["result"]
    remark = next((t.get("detail") for t in reversed(run.trace) if t.get("kind") == "run" and t.get("detail")), "")
    set_stage_status(db, run.loan_id, pb.stage_no, result["status"], remark[:1000])
    run.state = None
    run.output = {
        "status": result["status"],
        "advance": result["advance"],
        "end_node": result["node"],
        "team": result.get("team"),
        "findings": final.get("findings", []),
        "sensors": readings,
        "handoff": (final.get("context") or {}).get("handoff"),
        "decision": final.get("decision"),
        "rules_version": pb.rules_version,
        **report_payload,
    }
    if (final.get("context") or {}).get("report") is not None:
        run.output["report"] = {**final["context"]["report"], "verdict": result["status"],
                                "dm712_required": result["status"] == "Facially Incomplete"}
        if final["context"].get("exit_reason"):
            run.output["report"]["exit_reason"] = final["context"]["exit_reason"]
    _finish(run, "completed")


def run_stage(
    db: Session,
    loan_id: str,
    stage_no: int,
    *,
    workflow: models.WorkflowRun | None = None,
    trigger: str = "manual",
    start_at: str | None = None,
) -> models.AgentRun | None:
    """Run one stage's playbook for one loan. Returns None when the stage has no playbook yet.

    `start_at` enters the graph at another entry node (a re-run of the Final Mod checks)."""
    pb = get_playbook(stage_no)
    if pb is None:
        return None
    run = models.AgentRun(
        id=f"ar-{uuid.uuid4().hex[:12]}",
        loan_id=loan_id,
        workflow_run_id=workflow.id if workflow else None,
        stage_no=stage_no,
        agent_name=pb.spec.agent,
        status="running",
        trigger=trigger,
        started_at=now_utc(),
        input={"loan_id": loan_id, "playbook": pb.spec.process, "rules_version": pb.rules_version, "start_at": start_at or pb.spec.start},
        trace=[],
    )
    db.add(run)
    db.flush()
    state = {"loan_id": loan_id, "stage_no": stage_no, "agent_run_id": run.id, "rules_version": pb.rules_version, "trace": []}
    if start_at:
        state["resume_at"] = start_at
    _execute(db, run, pb, state)
    return run


def entry_node(db: Session, loan_id: str, stage_no: int) -> str | None:
    """Where a re-run enters: Final Mod checks again once the Underwriting plan was signed off."""
    if stage_no == 5 and stage_status(db, loan_id, 5) in RERUNNABLE[5]:
        qc = db.get(models.ClosingQc, loan_id)
        if qc is not None and qc.mod_approved_at is not None:
            return "fm_trial_outcome"
    return None


def _apply_decision(db: Session, run: models.AgentRun, decision: models.Decision, approved: bool,
                    decided_by: str, note: str | None, selection, qc: dict | None) -> dict:
    """Write what the decision means to the stage's own tables, before the graph resumes."""
    now = now_utc()
    if run.stage_no == 3 and decision.gate == "underwriter_review":
        if approved:
            plan = approve_plan(db, run, selection, decided_by, note, now)
            return {"approved_plan_id": plan.id, "approved_plan_name": plan.plan_name, "trial_payment": plan.trial_payment}
        decline_plans(db, run, decided_by, note, now)
    if run.stage_no == 5 and approved and decision.gate in ("underwriting_mod_qc", "underwriting_sign_off"):
        row = db.get(models.ClosingQc, run.loan_id) or models.ClosingQc(loan_id=run.loan_id)
        if decision.gate == "underwriting_mod_qc":
            for flag in models.QC_FLAGS:
                if qc and flag in qc:
                    setattr(row, flag, qc[flag])
            row.qc_by, row.qc_at, row.qc_note = decided_by, now, note
        else:
            row.mod_approved_at, row.mod_approved_by = now, decided_by
        row.updated_at = now
        db.add(row)
        db.flush()
        if decision.gate == "underwriting_mod_qc":
            return {"qc": {flag: getattr(row, flag) for flag in models.QC_FLAGS}}
        return {"mod_approved_at": now.isoformat()}
    return {}


def is_stale(decision: models.Decision) -> bool:
    """A pending review whose gate is not in the stage's current playbook cannot be resumed."""
    pb = get_playbook(decision.stage_no)
    return pb is None or decision.gate not in pb.spec.nodes


def retire_stale(db: Session, decision: models.Decision, retired_by: str) -> None:
    """Close a stale review and put the loan back to Waiting at its stage, so Run re-evaluates it
    under the current rules. The old run, decision and workflow stay in the history, marked closed."""
    if decision.status != "pending" or not is_stale(decision):
        raise ValueError("Only a pending review from an older playbook can be retired")
    now = now_utc()
    stage = models.STAGE_BY_NO[decision.stage_no]
    reason = f"Retired: created by an older {stage.name} playbook (gate {decision.gate!r} no longer exists)"
    decision.status, decision.decided_at, decision.decided_by, decision.note = "rejected", now, retired_by, reason
    run = db.get(models.AgentRun, decision.agent_run_id)
    if run is not None and run.status == "paused":
        run.state = None
        run.error = reason
        _finish(run, "cancelled")
        wf = run.workflow_run
        if wf is not None and wf.status in ACTIVE:
            wf.outcome = f"{reason}; loan reset to Waiting at {stage.name}"
            _finish(wf, "cancelled")
    set_stage_status(db, decision.loan_id, stage.no, None, f"Waiting — {reason}; run {stage.name} again")


def resume(db: Session, decision: models.Decision, approved: bool, decided_by: str, note: str | None,
           selected_trial_plan: dict | str | None = None, qc: dict | None = None) -> models.AgentRun:
    """Record the decision and continue the paused agent run (and its workflow, if any)."""
    if decision.status != "pending":
        raise ValueError(f"Decision is already {decision.status}")
    run = db.get(models.AgentRun, decision.agent_run_id)
    if run is None or run.status != "paused" or not run.state:
        raise ValueError("The agent run for this decision is not paused")
    pb = get_playbook(run.stage_no)
    if is_stale(decision):
        raise ValueError(f"This review was created by an older {models.STAGE_BY_NO[decision.stage_no].name} playbook "
                         f"(gate {decision.gate!r} no longer exists). Retire it to reset the loan to Waiting, then Run the stage again.")
    gate = pb.node(decision.gate)
    current = stage_status(db, decision.loan_id, decision.stage_no)
    if current != gate.status:
        raise ValueError(f"This case is no longer waiting for review: {models.STAGE_BY_NO[decision.stage_no].name} is now {current or 'not started'}")

    state = deepcopy(run.state)
    applied = _apply_decision(db, run, decision, approved, decided_by, note, selected_trial_plan, qc)

    decision.status = "approved" if approved else "rejected"
    decision.decided_at = now_utc()
    decision.decided_by = decided_by
    decision.note = note

    state["resume_at"] = gate.on_approve if approved else gate.on_reject
    state["decision"] = {"gate": decision.gate, "approved": approved, "by": decided_by, "note": note, "at": decision.decided_at.isoformat()}
    state["decision"].update(applied)
    state["review_reason"] = ""
    _execute(db, run, pb, state)

    if run.workflow_run is not None and run.status in ("completed", "failed"):
        advance_workflow(db, run.workflow_run)
    return run


# --------------------------------------------------------------------------- #
# End to end
# --------------------------------------------------------------------------- #


def advance_workflow(db: Session, wf: models.WorkflowRun) -> models.WorkflowRun:
    """Move a workflow forward stage by stage until it finishes, pauses or is blocked."""
    wf.status = "running"
    while True:
        if wf.current_stage > len(models.STAGES):
            wf.outcome = "All five stages complete"
            _finish(wf, "completed")
            return wf
        stage = models.STAGE_BY_NO[wf.current_stage]
        run = next((a for a in wf.agent_runs if a.stage_no == stage.no), None)
        if run is None and stage_status(db, wf.loan_id, stage.no) in stage.advances:
            wf.current_stage += 1  # already handed on from this stage by an earlier workflow
            continue
        if run is None and get_playbook(stage.no) is None:
            wf.outcome = f"Waiting at {stage.name}: no playbook built for this stage yet"
            _finish(wf, "blocked")
            return wf

        if run is None:
            run = run_stage(db, wf.loan_id, stage.no, workflow=wf, trigger=wf.trigger, start_at=entry_node(db, wf.loan_id, stage.no))
            db.flush()
            db.refresh(wf)

        if run.status == "paused":
            wf.status = "paused"
            wf.outcome = f"Paused at {stage.name}: {run.output['paused_at']['team']} review"
            return wf
        if run.status == "failed":
            wf.error = run.error
            wf.outcome = f"Failed at {stage.name}"
            _finish(wf, "failed")
            return wf
        if not run.output.get("advance"):
            wf.outcome = f"Stopped at {stage.name}: {run.output['status']}"
            _finish(wf, "blocked")
            return wf
        _hand_on(db, wf.loan_id, stage)
        wf.current_stage += 1


def start_workflow(db: Session, loan_id: str, *, trigger: str = "manual", requested_by: str = "") -> models.WorkflowRun:
    """Start (or return the already active) end-to-end run for a loan."""
    active = db.scalar(select(models.WorkflowRun).where(models.WorkflowRun.loan_id == loan_id, models.WorkflowRun.status.in_(ACTIVE)))
    if active is not None:
        return active
    wf = models.WorkflowRun(
        id=f"wf-{uuid.uuid4().hex[:12]}",
        loan_id=loan_id,
        status="running",
        trigger=trigger,
        requested_by=requested_by,
        current_stage=first_open_stage(db.get(models.LmStages, loan_id)),
        started_at=now_utc(),
    )
    db.add(wf)
    db.flush()
    return advance_workflow(db, wf)


def _latest_workflows(db: Session, loan_id: str | None = None) -> dict[str, models.WorkflowRun]:
    query = select(models.WorkflowRun).order_by(models.WorkflowRun.started_at)
    if loan_id is not None:
        query = query.where(models.WorkflowRun.loan_id == loan_id)
    return {wf.loan_id: wf for wf in db.scalars(query)}


def workflow_candidates(db: Session, loan_id: str | None = None) -> list[tuple[str, models.WorkflowRun | None]]:
    """Loans that should flow now, as (loan_id, workflow to continue or None to start one).

    * a new case: documents extracted, never run end to end;
    * a blocked case whose documents were re-extracted after it stopped;
    * a case blocked only because its stage had no playbook, now that one exists.
    Call it again under the loan's lock before acting: another worker may have just moved it.
    """
    latest = _latest_workflows(db, loan_id)
    query = select(models.ExtractedData.loan_id, models.ExtractedData.extracted_at)
    if loan_id is not None:
        query = query.where(models.ExtractedData.loan_id == loan_id)
    out: list[tuple[str, models.WorkflowRun | None]] = []
    for lid, extracted_at in db.execute(query):
        wf = latest.get(lid)
        if wf is None:
            out.append((lid, None))
        elif wf.status == "blocked":
            if not any(a.stage_no == wf.current_stage for a in wf.agent_runs) and get_playbook(wf.current_stage) is not None:
                out.append((lid, wf))
            elif extracted_at and as_utc(extracted_at) > as_utc(wf.finished_at):
                out.append((lid, None))
    return out


def stage_candidates(db: Session, stage_no: int) -> list[str]:
    """Loans waiting at a stage (handed on and not yet worked, or in a re-runnable status) with no workflow active."""
    stage = models.STAGE_BY_NO[stage_no]
    rerun = RERUNNABLE.get(stage_no, ())
    active = set(db.scalars(select(models.WorkflowRun.loan_id).where(models.WorkflowRun.status.in_(ACTIVE))))
    rows = db.execute(
        select(models.ExtractedData.loan_id, models.LmStages).outerjoin(models.LmStages, models.LmStages.loan_id == models.ExtractedData.loan_id)
    )
    return [lid for lid, lm in rows if lid not in active and (
        stage_position(lm, stage, has_documents=True) == "waiting" or (lm is not None and getattr(lm, f"{stage.key}_status") in rerun))]


def continue_at_stage(db: Session, loan_id: str, stage_no: int, *, trigger: str = "manual", requested_by: str = "") -> models.WorkflowRun | None:
    """Run a loan waiting at `stage_no` by continuing its workflow (or starting one). None if it is not waiting there."""
    if loan_id not in stage_candidates(db, stage_no):
        return None
    wf = _latest_workflows(db, loan_id).get(loan_id)
    if wf is not None and wf.status == "blocked" and wf.current_stage == stage_no and not any(a.stage_no == stage_no for a in wf.agent_runs):
        return advance_workflow(db, wf)
    return start_workflow(db, loan_id, trigger=trigger, requested_by=requested_by)
