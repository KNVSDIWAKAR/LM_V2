"""One loan at Trial UW (3), Trial Monitoring (4) or Final UW & Closing (5).

Everything comes from the database: the latest agent run (findings, trace, stage_report),
trial_plans / trial_installments, the MSP screens and documents the checks read, and
closing_qc. Nothing is recalculated here.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..core.database import get_db
from ..engine import runner
from ..engine.playbook import get_playbook
from ..engine.trial_support import approved_plan, plan_out
from ..schemas.cases import ClosingRecordUpdate, LatestRun, RunSummary, StageCase

router = APIRouter(prefix="/api/cases", tags=["cases"])

CASE_STAGES = (3, 4, 5)


def _outcome(run: models.AgentRun) -> str | None:
    out = run.output or {}
    if out.get("status"):
        return out["status"]
    if out.get("paused_at"):
        return f"Waiting for {out['paused_at'].get('team')}"
    return None


def _summary(run: models.AgentRun) -> RunSummary:
    return RunSummary(id=run.id, status=run.status, trigger=run.trigger, started_at=run.started_at,
                      finished_at=run.finished_at, outcome=_outcome(run), error=run.error)


def _qc_out(qc: models.ClosingQc | None) -> dict:
    fields = (*models.QC_FLAGS, "qc_by", "qc_at", "qc_note", "mod_approved_at", "mod_approved_by", "recorded_date", "recorded_by", "updated_at")
    return {f: getattr(qc, f) if qc else None for f in fields}


def _stage3(db: Session, msp: models.Msp) -> dict:
    plans = db.scalars(select(models.TrialPlan).where(models.TrialPlan.loan_id == msp.loan_id)
                       .order_by(models.TrialPlan.created_at.desc(), models.TrialPlan.option_no))
    docs = db.get(models.ExtractedData, msp.loan_id)
    application = (docs.application_form if docs else None) or {}
    return {
        "plans": [plan_out(p) for p in plans],
        "evidence": {
            "investor_type": (msp.dlq1 or {}).get("investor_type"),
            "upb_balance": (msp.dlq1 or {}).get("upb_balance"),
            "months_delinquent": (msp.dlq1 or {}).get("months_delinquent"),
            "escrow_payment_amount": (msp.ana1 or {}).get("escrow_payment_amount"),
            "escrow_current": (msp.ana1 or {}).get("escrow_current"),
            "income_sources": [s for s in application.get("income_sources") or [] if s.get("gross_monthly_amount")],
            "other_income_amount": application.get("other_income_amount"),
            "hardship_reason": application.get("hardship_reason"),
            "current_payment": ((docs.credit_report if docs else None) or {}).get("monthly_mortgage_payment"),
        },
    }


def _stage4(db: Session, msp: models.Msp, rules: dict) -> dict:
    plan = approved_plan(db, msp.loan_id)
    prefix = ((rules.get("trial_monitoring") or {}).get("lmt_note") or {}).get("prefix", "LMT TRIAL")
    history = (msp.dlq1 or {}).get("payment_history")
    return {
        "approved_plan": plan_out(plan) if plan else None,
        "payment_history": history,
        "payment_history_available": history is not None,
        "lmt_notes": [n for n in (msp.nots or {}).get("notes", []) if str(n).startswith(prefix)],
        "months_delinquent": (msp.dlq1 or {}).get("months_delinquent"),
        "due_date": (msp.dlq1 or {}).get("due_date"),
    }


def _stage5(db: Session, msp: models.Msp, rules: dict) -> dict:
    docs = db.get(models.ExtractedData, msp.loan_id)
    plan = approved_plan(db, msp.loan_id)
    lmt3_keys = ((rules.get("final_underwriting") or {}).get("lmt3") or {}).get("date_keys", [])
    fm = rules.get("final_mod_closing") or {}
    return {
        "qc": _qc_out(db.get(models.ClosingQc, msp.loan_id)),
        "tasks": {"TASK1": (msp.task1 or {}).get("tasks") if msp.task1 is not None else None,
                  "MES1": (msp.mes1 or {}).get("tasks") if msp.mes1 is not None else None},
        "lsmr": msp.lsmr,
        "lmt3_dates": {k: (msp.lmt3 or {}).get(k) for k in lmt3_keys},
        "neighbourhood_document": docs.neighbourhood_document if docs else None,
        "approved_plan": plan_out(plan) if plan else None,
        "property_state": (msp.dlq1 or {}).get("property_state"),
        "sla_days": (fm.get("settings") or {}).get("sla_days"),
        "county_recording_states": (fm.get("settings") or {}).get("county_recording_states", []),
        "rerun_entry": runner.entry_node(db, msp.loan_id, 5),
    }


@router.get("/{stage_no}/{loan_id}", response_model=StageCase)
def stage_case(stage_no: int, loan_id: str, db: Session = Depends(get_db)) -> StageCase:
    if stage_no not in CASE_STAGES:
        raise HTTPException(404, "Case pages exist for stages 3, 4 and 5")
    msp = db.get(models.Msp, loan_id)
    if msp is None:
        raise HTTPException(404, "Loan not found")
    stage = models.STAGE_BY_NO[stage_no]
    lm = db.get(models.LmStages, loan_id)
    runs = list(db.scalars(select(models.AgentRun).where(models.AgentRun.loan_id == loan_id, models.AgentRun.stage_no == stage_no)
                           .order_by(models.AgentRun.started_at.desc())))
    decision = db.scalar(select(models.Decision.id).where(models.Decision.loan_id == loan_id, models.Decision.stage_no == stage_no,
                                                          models.Decision.status == "pending"))
    latest = None
    if runs:
        r, out = runs[0], runs[0].output or {}
        latest = LatestRun(**_summary(r).model_dump(), rules_version=out.get("rules_version"),
                           start_at=(r.input or {}).get("start_at"), findings=out.get("findings", []),
                           trace=r.trace or [], stage_report=out.get("stage_report") or {}, paused_at=out.get("paused_at"))
    pb = get_playbook(stage_no)
    rules = pb.rules if pb else {}
    data = {3: lambda: _stage3(db, msp), 4: lambda: _stage4(db, msp, rules), 5: lambda: _stage5(db, msp, rules)}[stage_no]()
    return StageCase(stage_no=stage_no, stage_name=stage.name, loan_id=loan_id, borrower_name=msp.borrower_name,
                     status=getattr(lm, f"{stage.key}_status") if lm else None, remark=(getattr(lm, f"{stage.key}_remark") if lm else "") or "",
                     open_decision_id=decision, latest_run=latest, runs=[_summary(r) for r in runs], data=data)


@router.put("/5/{loan_id}/closing-record", response_model=StageCase)
def update_closing_record(loan_id: str, body: ClosingRecordUpdate, db: Session = Depends(get_db)) -> StageCase:
    """Record MOD QC flags and/or the county recording date. Run Stage 5 again to re-check."""
    lm = db.get(models.LmStages, loan_id)
    if lm is None or lm.trial_monitoring_status != "Completed":
        raise HTTPException(409, "The loan has not reached Final Underwriting & Closing (Trial Monitoring is not Completed)")
    fields = body.model_dump(exclude_unset=True)
    if not set(fields) - {"updated_by", "note"}:
        raise HTTPException(422, "Nothing to record")
    with runner.loan_lock(loan_id):
        now = runner.now_utc()
        row = db.get(models.ClosingQc, loan_id) or models.ClosingQc(loan_id=loan_id)
        if "recorded_date" in fields:
            recorded = fields["recorded_date"]
            if recorded is not None:
                if recorded > now.date():
                    raise HTTPException(422, "Recorded date cannot be in the future")
                if row.mod_approved_at is None:
                    raise HTTPException(409, "The Underwriting plan has not been signed off yet")
                if recorded < runner.as_utc(row.mod_approved_at).date():
                    raise HTTPException(422, "Recorded date is before the Underwriting sign-off")
            row.recorded_date, row.recorded_by = recorded, body.updated_by
        qc_changed = [f for f in models.QC_FLAGS if f in fields]
        for flag in qc_changed:
            setattr(row, flag, fields[flag])
        if qc_changed:
            row.qc_by, row.qc_at = body.updated_by, now
            if body.note is not None:
                row.qc_note = body.note
        row.updated_at = now
        db.add(row)
        db.commit()
    return stage_case(5, loan_id, db)
