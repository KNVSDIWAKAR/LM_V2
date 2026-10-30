"""Trial plans: what Trial Underwriting proposed, which plan a person approved, and how
Trial Monitoring matched MSP DLQ1 payments against each installment.

A plan row is written by the Stage 3 agent run that calculated it (agent_run_id) and keeps
every input and formula result, so a reviewer sees exactly what was proposed and why.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base, JSONType

# proposed      calculated by Stage 3, waiting for the Human Underwriter
# approved      chosen by the Human Underwriter; Stage 4 monitors this plan
# not_selected  another option of the same evaluation was approved
# declined      the Human Underwriter rejected the case
# superseded    a newer Stage 3 evaluation replaced this proposal
PLAN_STATUSES = ("proposed", "approved", "not_selected", "declined", "superseded")
# pending  not yet due, or due and still inside the grace period
# paid     covered by DLQ1 payments on or before due date + grace
# late     covered, but only after the grace period ended
# partial  grace period over and only part of the amount was received
# missed   grace period over and nothing was received for it
INSTALLMENT_STATUSES = ("pending", "paid", "late", "partial", "missed")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class TrialPlan(Base):
    __tablename__ = "trial_plans"
    __table_args__ = (CheckConstraint(_in("status", PLAN_STATUSES), name="ck_trial_plans_status"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    loan_id: Mapped[str] = mapped_column(String(20), ForeignKey("msp.loan_id", ondelete="CASCADE"), index=True)
    agent_run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"), index=True)
    option_no: Mapped[int] = mapped_column(Integer)
    plan_type: Mapped[str] = mapped_column(String(40))
    plan_name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="proposed", index=True)

    # The proposal.
    trial_payment: Mapped[float] = mapped_column(Float)  # principal_interest + escrow
    principal_interest: Mapped[float] = mapped_column(Float)
    escrow_payment: Mapped[float] = mapped_column(Float)
    interest_rate_pct: Mapped[float] = mapped_column(Float)
    amortization_months: Mapped[int] = mapped_column(Integer)
    trial_duration_months: Mapped[int] = mapped_column(Integer)
    grace_period_days: Mapped[int] = mapped_column(Integer)
    first_due_date: Mapped[date] = mapped_column(Date)

    # The evidence it was calculated from.
    upb_balance: Mapped[float] = mapped_column(Float)
    gross_monthly_income: Mapped[float] = mapped_column(Float)
    current_payment: Mapped[float | None] = mapped_column(Float)
    housing_ratio: Mapped[float] = mapped_column(Float)  # trial_payment / gross_monthly_income
    payment_change_pct: Mapped[float | None] = mapped_column(Float)  # vs current_payment; negative = reduction

    conditions: Mapped[list[str]] = mapped_column(JSONType, default=list)
    reason_codes: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    calculation: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)  # inputs, sources, formula

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[str | None] = mapped_column(String(120))
    decision_note: Mapped[str | None] = mapped_column(Text)

    installments: Mapped[list["TrialInstallment"]] = relationship(
        back_populates="plan", order_by="TrialInstallment.installment_no", cascade="all, delete-orphan"
    )


class TrialInstallment(Base):
    __tablename__ = "trial_installments"
    __table_args__ = (
        CheckConstraint(_in("status", INSTALLMENT_STATUSES), name="ck_trial_installments_status"),
        UniqueConstraint("plan_id", "installment_no", name="uq_trial_installments_plan_no"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("trial_plans.id", ondelete="CASCADE"), index=True)
    installment_no: Mapped[int] = mapped_column(Integer)
    due_date: Mapped[date] = mapped_column(Date)
    grace_end_date: Mapped[date] = mapped_column(Date)
    expected_amount: Mapped[float] = mapped_column(Float)
    # Written by Trial Monitoring from MSP DLQ1 payment_history; NULL until evaluated.
    received_amount: Mapped[float | None] = mapped_column(Float)
    received_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    plan: Mapped[TrialPlan] = relationship(back_populates="installments")
