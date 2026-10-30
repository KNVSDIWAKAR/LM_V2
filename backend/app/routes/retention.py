"""Retention read models and explicit human routing; Run reuses /processes/2/run."""

import uuid
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models
from ..core.database import get_db
from ..engine import runner
from ..engine.playbook import get_playbook
from ..schemas.retention import RetentionCase, RetentionCaseDetail, RetentionSummary

router = APIRouter(prefix="/api/retention", tags=["retention"])


def _data(db):
    rows = db.execute(select(models.Msp, models.LmStages, models.ExtractedData)
                      .join(models.LmStages, models.LmStages.loan_id == models.Msp.loan_id)
                      .outerjoin(models.ExtractedData, models.ExtractedData.loan_id == models.Msp.loan_id)
                      .where(models.LmStages.intake_status == "Complete").order_by(models.Msp.borrower_name)).all()
    runs = list(db.scalars(select(models.AgentRun).where(models.AgentRun.stage_no == 2).order_by(models.AgentRun.started_at, models.AgentRun.id)))
    latest = {run.loan_id: run for run in runs}
    decisions = {d.loan_id: d.id for d in db.scalars(select(models.Decision).where(models.Decision.stage_no == 2, models.Decision.status == "pending"))}
    records = []
    for loan, lm, doc in rows:
        run = latest.get(loan.loan_id)
        report = (run.output or {}).get("report") if run else None
        stips = report.get("stip_list", []) if report else []
        records.append(RetentionCase(
            loan_id=loan.loan_id, borrower_name=loan.borrower_name,
            investor=(loan.dlq1 or {}).get("investor_type"), months_delinquent=(loan.dlq1 or {}).get("months_delinquent"),
            hardship=((doc.application_form or {}).get("hardship_reason") if doc else None),
            status=lm.retention_eligibility_status, stip_count=report["stip_count"] if report else None,
            remark=lm.retention_eligibility_remark or "", last_run_id=run.id if run else None,
            last_run_at=run.started_at if run else None, last_run_status=run.status if run else None,
            open_decision_id=decisions.get(loan.loan_id),
            pending_reason="; ".join(s["reason"] for s in stips[:2]) or (lm.retention_eligibility_remark if lm.retention_eligibility_status == "Facially Incomplete" else None)))
    return records, latest, runs


@router.get("/summary", response_model=RetentionSummary)
def summary(db: Session = Depends(get_db)):
    records, _, runs = _data(db)
    counts = Counter(r.status or "Waiting" for r in records)
    return RetentionSummary(
        loans_in_book=db.scalar(select(func.count()).select_from(models.Msp)), total_records=len(records),
        eligible=len(runner.stage_candidates(db, 2)), counts={s: counts[s] for s in ("Waiting", *models.STAGE_BY_NO[2].allowed)},
        run_count=len(runs), last_run_id=runs[-1].id if runs else None, last_run_at=runs[-1].started_at if runs else None,
        records=records, pending_actions=[r for r in records if r.status == "Facially Incomplete"],
        active_run_ids=[r.id for r in runs if r.status in ("queued", "running")])


@router.get("/executions")
def executions(ids: str = Query(min_length=1, max_length=16000), db: Session = Depends(get_db)):
    """Poll exact run IDs, rather than treating HTTP 202 as completion."""
    run_ids = list(dict.fromkeys(ids.split(",")))
    runs = list(db.scalars(select(models.AgentRun).where(models.AgentRun.id.in_(run_ids), models.AgentRun.stage_no == 2)))
    if len(runs) != len(run_ids):
        raise HTTPException(404, "One or more retention runs were not found")
    return {"runs": [{"id": r.id, "loan_id": r.loan_id, "status": r.status, "error": r.error,
                      "verdict": (r.output or {}).get("status"), "finished_at": r.finished_at} for r in runs]}


@router.get("/cases", response_model=list[RetentionCase])
def cases(db: Session = Depends(get_db)):
    return _data(db)[0]


@router.get("/cases/{loan_id}", response_model=RetentionCaseDetail)
def case_detail(loan_id: str, db: Session = Depends(get_db)):
    records, latest, _ = _data(db)
    record = next((r for r in records if r.loan_id == loan_id), None)
    if record is None:
        raise HTTPException(404, "Retention case not found (Intake must be Complete)")
    run = latest.get(loan_id)
    report = (run.output or {}).get("report") if run else None
    return RetentionCaseDetail(**record.model_dump(), report=report, trace=run.trace or [] if run else [],
                               can_route_to_inbox=bool(report and record.status not in (None, "Facially Complete") and not record.open_decision_id))


@router.post("/cases/{loan_id}/review")
def route_to_review(loan_id: str, db: Session = Depends(get_db)):
    """Create an auditable review snapshot, preserving the original report and its stips.

Approval acknowledges the stips; it cannot turn an incomplete file into a complete one.
The normal runner.resume handles both decisions through the YAML manual-review gate.
"""
    with runner.loan_lock(loan_id):
        detail = case_detail(loan_id, db)
        if detail.open_decision_id:
            return {"decision_id": detail.open_decision_id}
        if not detail.can_route_to_inbox:
            raise HTTPException(409, "Only evaluated non-complete retention cases can be routed")
        if db.scalar(select(models.WorkflowRun.id).where(models.WorkflowRun.loan_id == loan_id, models.WorkflowRun.status.in_(runner.ACTIVE))):
            raise HTTPException(409, "Loan already has an active workflow")
        pb = get_playbook(2)
        gate = pb.node("manual_review")
        now = runner.now_utc()
        report = detail.report.model_dump()
        reason = detail.pending_reason or detail.remark or "Manual validation of retention result requested"
        findings = [{"check": s.question_id, "document": s.document_required, "result": "fail", "detail": s.reason} for s in detail.report.stip_list]
        wf = models.WorkflowRun(id=f"wf-{uuid.uuid4().hex[:12]}", loan_id=loan_id, status="paused", trigger="manual",
                                requested_by="retention-page", current_stage=2, started_at=now, outcome=f"Paused at Retention Eligibility: {gate.team} review")
        paused = {"gate": "manual_review", "title": gate.title, "team": gate.team, "status": gate.status, "reason": reason}
        run = models.AgentRun(id=f"ar-{uuid.uuid4().hex[:12]}", loan_id=loan_id, workflow_run_id=wf.id, stage_no=2,
                              agent_name=pb.spec.agent, status="paused", trigger="manual", started_at=now,
                              input={"source_run_id": detail.last_run_id, "rules_version": pb.rules_version},
                              trace=[{"node": "manual_review", "kind": "gate", "title": gate.title, "detail": reason, "duration_ms": 0}],
                              output={"paused_at": paused, "report": {**report, "verdict": gate.status, "dm712_required": False}, "findings": findings, "rules_version": pb.rules_version},
                              state={"loan_id": loan_id, "stage_no": 2, "context": {"report": report, "reviewed_status": detail.status}, "findings": findings, "trace": detail.trace})
        decision = models.Decision(id=f"dc-{uuid.uuid4().hex[:12]}", loan_id=loan_id, agent_run_id=run.id, workflow_run_id=wf.id,
                                   stage_no=2, gate="manual_review", team=gate.team, title=f"Retention file review — loan {loan_id}",
                                   reason=reason, findings=findings, status="pending", created_at=now)
        db.add(wf)
        db.flush()
        db.add(run)
        db.flush()
        db.add(decision)
        runner.set_stage_status(db, loan_id, 2, gate.status, f"Waiting for {gate.team}: {reason}"[:1000])
        db.commit()
        return {"decision_id": decision.id}