"""Explicit retention re-evaluation with durable run IDs and observable progress.

No Intake resets or deletion of run/decision history. Reservations use a running
workflow so the existing scheduler and stage buttons cannot work the same loan.
"""

import logging
import uuid
from datetime import timedelta

from sqlalchemy import select

from .. import models
from ..core.database import SessionLocal
from . import runner
from .playbook import get_playbook

log = logging.getLogger(__name__)
EXECUTING = ("queued", "running")


def blocked_reason(db, loan_id):
    lm = db.get(models.LmStages, loan_id)
    if lm is None or lm.intake_status != "Complete":
        return "Intake must be Complete"
    if db.get(models.ExtractedData, loan_id) is None:
        return "No extracted documents available"
    if db.scalar(select(models.WorkflowRun.id).where(models.WorkflowRun.loan_id == loan_id,
                  models.WorkflowRun.status.in_((*EXECUTING, "paused")))):
        return "A workflow is already running or waiting for human review"
    if db.scalar(select(models.AgentRun.id).where(models.AgentRun.loan_id == loan_id,
                  models.AgentRun.status.in_((*EXECUTING, "paused")))):
        return "An agent run is already active"
    if db.scalar(select(models.Decision.id).where(models.Decision.loan_id == loan_id, models.Decision.status == "pending")):
        return "Resolve the pending Decision Inbox item first"
    if any(getattr(lm, f"{stage.key}_status") for stage in models.STAGES if stage.no > 2):
        return "Later-stage work exists; retention cannot be overwritten"
    if db.scalar(select(models.AgentRun.id).where(models.AgentRun.loan_id == loan_id, models.AgentRun.stage_no > 2)):
        return "Later-stage run history exists; retention cannot be overwritten"
    return None


def queue(db, loan_id=None, requested_by=""):
    """Commit each reservation under the same per-loan lock used by other workers."""
    candidates = [loan_id] if loan_id else list(db.scalars(select(models.LmStages.loan_id)
                 .where(models.LmStages.intake_status == "Complete").order_by(models.LmStages.loan_id)))
    run_ids, loan_ids, skipped = [], [], []
    pb = get_playbook(2)
    if pb is None:
        raise ValueError("Retention playbook is not available")
    for lid in candidates:
        with runner.loan_lock(lid):
            # End a potentially stale read transaction before checking the reservation.
            db.rollback()
            reason = blocked_reason(db, lid)
            if reason:
                skipped.append({"loan_id": lid, "reason": reason})
                continue
            previous = db.scalar(select(models.AgentRun).where(models.AgentRun.loan_id == lid, models.AgentRun.stage_no == 2)
                                 .order_by(models.AgentRun.started_at.desc(), models.AgentRun.id.desc()))
            now = runner.now_utc()
            if previous and runner.as_utc(previous.started_at) >= now:
                now = runner.as_utc(previous.started_at) + timedelta(microseconds=1)
            wf = models.WorkflowRun(id=f"wf-{uuid.uuid4().hex[:12]}", loan_id=lid, status="running", trigger="manual",
                                    requested_by=requested_by, current_stage=2, started_at=now, outcome="Queued for Retention Eligibility re-evaluation")
            run = models.AgentRun(id=f"ar-{uuid.uuid4().hex[:12]}", loan_id=lid, workflow_run_id=wf.id, stage_no=2,
                                  agent_name=pb.spec.agent, status="queued", trigger="manual", started_at=now, trace=[],
                                  input={"loan_id": lid, "playbook": pb.spec.process, "rules_version": pb.rules_version,
                                         "rerun": True, "source_run_id": previous.id if previous else None})
            db.add(wf)
            db.flush()
            db.add(run)
            db.commit()
            run_ids.append(run.id)
            loan_ids.append(lid)
    return {"queued": len(run_ids), "loan_ids": loan_ids, "run_ids": run_ids, "skipped": skipped}


def execute(run_ids):
    for run_id in run_ids:
        try:
            with SessionLocal() as db:
                reserved = db.get(models.AgentRun, run_id)
                if reserved is None:
                    continue
                loan_id = reserved.loan_id
            with runner.loan_lock(loan_id), SessionLocal() as db:
                run = db.get(models.AgentRun, run_id)
                if run.status != "queued":
                    continue
                # Publish the running state before graph evaluation so GET can observe it.
                run.status = "running"
                run.workflow_run.outcome = "Running Retention Eligibility"
                db.commit()
                if runner.stage_status(db, loan_id, 1) != "Complete":
                    raise ValueError("Intake is no longer Complete")
                pb = get_playbook(2)
                runner._execute(db, run, pb, {"loan_id": loan_id, "stage_no": 2, "rules_version": pb.rules_version, "trace": []})
                # Continue using the newly reserved stage-2 run, never re-run Intake.
                runner.advance_workflow(db, run.workflow_run)
                db.commit()
        except Exception as err:
            log.exception("retention rerun failed: %s", run_id)
            # Roll back partial verdict writes, but keep a terminal error for polling.
            with SessionLocal() as db:
                run = db.get(models.AgentRun, run_id)
                if run is not None:
                    run.error = f"{type(err).__name__}: {err}"
                    runner._finish(run, "failed")
                    if run.workflow_run:
                        run.workflow_run.error = run.error
                        run.workflow_run.outcome = "Retention re-evaluation failed; previous stage result preserved"
                        runner._finish(run.workflow_run, "failed")
                    db.commit()