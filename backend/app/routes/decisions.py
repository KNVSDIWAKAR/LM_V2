"""Decision Inbox: cases paused at a playbook gate. Deciding resumes them."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..core.database import get_db
from ..engine import runner
from ..engine.trial_support import PlanSelectionError, findings_with_plan_status, plan_out, plans_for_run
from ..schemas.decisions import DecideRequest, DecideResult, DecisionOut

router = APIRouter(prefix="/api/decisions", tags=["decisions"])


def decision_out(db: Session, d: models.Decision) -> DecisionOut:
    loan = db.get(models.Msp, d.loan_id)
    extra = {}
    if d.stage_no == 3:
        extra["trial_plans"] = [plan_out(p) for p in plans_for_run(db, d.agent_run_id)]
        extra["findings"] = findings_with_plan_status(d.findings or [], extra["trial_plans"])
    if d.stage_no == 5:
        qc = db.get(models.ClosingQc, d.loan_id)
        extra["qc"] = {flag: getattr(qc, flag) if qc else None for flag in models.QC_FLAGS}
    return DecisionOut.model_validate(
        {
            **{c: getattr(d, c) for c in DecisionOut.model_fields if hasattr(d, c)},
            "borrower_name": loan.borrower_name if loan else "",
            "stage_name": models.STAGE_BY_NO[d.stage_no].name,
            "stale": d.status == "pending" and runner.is_stale(d),
            **extra,
        }
    )


@router.get("", response_model=list[DecisionOut])
def list_decisions(status: str | None = None, db: Session = Depends(get_db)) -> list[DecisionOut]:
    query = select(models.Decision).order_by(models.Decision.created_at.desc())
    if status is not None:
        query = query.where(models.Decision.status == status)
    return [decision_out(db, d) for d in db.scalars(query)]


@router.get("/{decision_id}", response_model=DecisionOut)
def get_decision(decision_id: str, db: Session = Depends(get_db)) -> DecisionOut:
    d = db.get(models.Decision, decision_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    return decision_out(db, d)


@router.post("/retire-stale", response_model=list[DecisionOut])
def retire_all_stale(db: Session = Depends(get_db)) -> list[DecisionOut]:
    """Retire every pending review created by an older playbook; each loan goes back to Waiting."""
    retired = []
    for d in list(db.scalars(select(models.Decision).where(models.Decision.status == "pending"))):
        if runner.is_stale(d):
            with runner.loan_lock(d.loan_id):
                runner.retire_stale(db, d, "system")
            retired.append(d)
    db.commit()
    return [decision_out(db, d) for d in retired]


@router.post("/{decision_id}/retire", response_model=DecisionOut)
def retire(decision_id: str, db: Session = Depends(get_db)) -> DecisionOut:
    d = db.get(models.Decision, decision_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    with runner.loan_lock(d.loan_id):
        try:
            runner.retire_stale(db, d, "reviewer")
        except ValueError as err:
            raise HTTPException(status_code=409, detail=str(err)) from err
        db.commit()
    return decision_out(db, d)


@router.post("/{decision_id}/decide", response_model=DecideResult)
def decide(decision_id: str, body: DecideRequest, db: Session = Depends(get_db)) -> DecideResult:
    d = db.get(models.Decision, decision_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    if d.status != "pending":
        raise HTTPException(status_code=409, detail=f"Decision is already {d.status}")
    if body.decision == "rejected" and not (body.note or "").strip():
        raise HTTPException(status_code=422, detail="Say why when rejecting")

    lock = runner.loan_lock(d.loan_id)
    with lock:
        # Serialize competing approvals, including requests in different workers.
        db.refresh(d, with_for_update=True)
        if d.status != "pending":
            raise HTTPException(status_code=409, detail=f"Decision is already {d.status}")
        try:
            if body.selected_trial_plan is not None and body.selected_plan_id is not None:
                raise PlanSelectionError("Provide selected_trial_plan or selected_plan_id, not both")
            run = runner.resume(db, d, body.decision == "approved", body.decided_by, body.note,
                                body.selected_trial_plan if body.selected_trial_plan is not None else body.selected_plan_id,
                                body.qc.model_dump(exclude_unset=True) if body.qc else None)
        except PlanSelectionError as err:
            db.rollback()
            raise HTTPException(status_code=422, detail=str(err)) from err
        except ValueError as err:
            db.rollback()
            raise HTTPException(status_code=409, detail=str(err)) from err
        db.commit()
    wf = run.workflow_run
    return DecideResult(
        decision=decision_out(db, d),
        stage_status=runner.stage_status(db, d.loan_id, d.stage_no),
        workflow_status=wf.status if wf else None,
        workflow_outcome=wf.outcome if wf else None,
    )
