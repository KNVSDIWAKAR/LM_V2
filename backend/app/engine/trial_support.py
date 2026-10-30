"""Trial plans in the database: approve / decline from the Decision Inbox, and read them back.

Stage 3 writes proposed plans to trial_plans (nodes/trial_uw.py). The Human Underwriter's
decision lands here before the paused graph resumes, so the stage status and the plan rows
always agree. Stage 4 monitors the one approved plan.
"""

import calendar
import math
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models


class PlanSelectionError(ValueError):
    """Invalid review input; the pending decision must remain untouched."""


def as_float(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def add_months(day: date, months: int) -> date:
    """Calendar months, clamping the day to the end of short months."""
    year, month = divmod(day.year * 12 + day.month - 1 + months, 12)
    return date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def plans_for_run(db: Session, run_id: str) -> list[models.TrialPlan]:
    return list(db.scalars(select(models.TrialPlan).where(models.TrialPlan.agent_run_id == run_id).order_by(models.TrialPlan.option_no)))


def approved_plan(db: Session, loan_id: str) -> models.TrialPlan | None:
    """The plan Stage 4 monitors: the most recently approved plan for the loan."""
    return db.scalar(
        select(models.TrialPlan)
        .where(models.TrialPlan.loan_id == loan_id, models.TrialPlan.status == "approved")
        .order_by(models.TrialPlan.decided_at.desc())
        .limit(1)
    )


def supersede_open_proposals(db: Session, loan_id: str, now: datetime) -> int:
    """A new evaluation replaces any proposal still waiting from an earlier one."""
    rows = list(db.scalars(select(models.TrialPlan).where(models.TrialPlan.loan_id == loan_id, models.TrialPlan.status == "proposed")))
    for plan in rows:
        plan.status = "superseded"
        plan.decided_at = now
        plan.decision_note = "Replaced by a newer Trial UW evaluation"
    return len(rows)


def _plan_id(selection) -> str | None:
    if isinstance(selection, dict):
        return selection.get("plan_id") or selection.get("id")
    return selection if isinstance(selection, str) and selection.strip() else None


def approve_plan(db: Session, run: models.AgentRun, selection, decided_by: str, note: str | None, now: datetime) -> models.TrialPlan:
    """Approve exactly one proposed plan of this run; the run's other options become not_selected."""
    plans = plans_for_run(db, run.id)
    if not plans:
        raise PlanSelectionError("This evaluation has no proposed trial plan, so it cannot be approved")
    plan_id = _plan_id(selection)
    if plan_id is None:
        if len(plans) != 1:
            raise PlanSelectionError("Select the trial plan to approve (selected_plan_id)")
        plan_id = plans[0].id
    chosen = next((p for p in plans if p.id == plan_id), None)
    if chosen is None:
        raise PlanSelectionError(f"Plan {plan_id} is not one of this evaluation's proposed plans")
    if chosen.status != "proposed":
        raise PlanSelectionError(f"Plan {plan_id} is {chosen.status}; only a proposed plan can be approved")
    for plan in plans:
        if plan.status != "proposed":
            continue
        plan.status = "approved" if plan is chosen else "not_selected"
        plan.decided_at, plan.decided_by, plan.decision_note = now, decided_by, note
    return chosen


def decline_plans(db: Session, run: models.AgentRun, decided_by: str, note: str | None, now: datetime) -> None:
    for plan in plans_for_run(db, run.id):
        if plan.status == "proposed":
            plan.status = "declined"
            plan.decided_at, plan.decided_by, plan.decision_note = now, decided_by, note


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def plan_out(plan: models.TrialPlan) -> dict:
    """A plan and its installments as plain JSON (API responses and agent-run output)."""
    return {
        "plan_id": plan.id,
        "loan_id": plan.loan_id,
        "agent_run_id": plan.agent_run_id,
        "option_no": plan.option_no,
        "plan_type": plan.plan_type,
        "plan_name": plan.plan_name,
        "status": plan.status,
        "trial_payment": plan.trial_payment,
        "principal_interest": plan.principal_interest,
        "escrow_payment": plan.escrow_payment,
        "interest_rate_pct": plan.interest_rate_pct,
        "amortization_months": plan.amortization_months,
        "trial_duration_months": plan.trial_duration_months,
        "grace_period_days": plan.grace_period_days,
        "first_due_date": _iso(plan.first_due_date),
        "upb_balance": plan.upb_balance,
        "gross_monthly_income": plan.gross_monthly_income,
        "current_payment": plan.current_payment,
        "housing_ratio": plan.housing_ratio,
        "payment_change_pct": plan.payment_change_pct,
        "conditions": plan.conditions or [],
        "reason_codes": plan.reason_codes or [],
        "calculation": plan.calculation or {},
        "created_at": _iso(plan.created_at),
        "decided_at": _iso(plan.decided_at),
        "decided_by": plan.decided_by,
        "decision_note": plan.decision_note,
        "installments": [
            {
                "installment_no": i.installment_no,
                "due_date": i.due_date.isoformat(),
                "grace_end_date": i.grace_end_date.isoformat(),
                "expected_amount": i.expected_amount,
                "received_amount": i.received_amount,
                "received_date": _iso(i.received_date),
                "status": i.status,
                "evaluated_at": _iso(i.evaluated_at),
            }
            for i in plan.installments
        ],
    }
