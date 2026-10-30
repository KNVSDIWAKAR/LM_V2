"""Loss-mitigation stage tracking: one row per loan, a status + remark column pair per stage.

Each status column has a CHECK constraint listing the statuses that stage allows, so the
database rejects anything else. NULL means the stage hasn't been worked yet.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


@dataclass(frozen=True)
class Stage:
    no: int
    name: str
    key: str  # column prefix: {key}_status, {key}_remark
    allowed: tuple[str, ...]
    advances: tuple[str, ...]  # statuses that hand the loan on to the next stage (a subset of allowed)


STAGES: tuple[Stage, ...] = (
    Stage(1, "Intake", "intake", ("Complete", "Invalid Date Doc", "Missing Doc", "Missing & Invalid", "End Case", "In Human Review"), ("Complete",)),
    Stage(2, "Retention Eligibility", "retention_eligibility", ("Facially Complete", "Denied", "Facially Incomplete", "In Human Review"), ("Facially Complete",)),
    Stage(3, "Trial UW", "trial_uw", ("Ready", "UW In Progress", "Hold Docs Pending", "Hold Approval Pending", "Declined", "In Human Review"), ("Ready",)),
    Stage(4, "Trial Monitoring", "trial_monitoring", ("Completed", "Within Plan", "Delayed Payment", "Defaulted", "In Human Review"), ("Completed",)),
    Stage(5, "Closing", "closing", ("Recording", "Signed Off", "Sign Off & In Progress", "Denied", "In Human Review"), ("Recording", "Signed Off")),
)
STAGE_BY_NO = {s.no: s for s in STAGES}


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


class LmStages(Base):
    __tablename__ = "lm_stages"
    __table_args__ = tuple(
        CheckConstraint(
            f"{s.key}_status IS NULL OR {s.key}_status IN ({', '.join(_quote(a) for a in s.allowed)})",
            name=f"ck_lm_stages_{s.key}_status",
        )
        for s in STAGES
    )

    loan_id: Mapped[str] = mapped_column(String(20), ForeignKey("msp.loan_id", ondelete="CASCADE"), primary_key=True)

    intake_status: Mapped[str | None] = mapped_column(String(40))
    intake_remark: Mapped[str] = mapped_column(Text, default="")
    retention_eligibility_status: Mapped[str | None] = mapped_column(String(40))
    retention_eligibility_remark: Mapped[str] = mapped_column(Text, default="")
    trial_uw_status: Mapped[str | None] = mapped_column(String(40))
    trial_uw_remark: Mapped[str] = mapped_column(Text, default="")
    trial_monitoring_status: Mapped[str | None] = mapped_column(String(40))
    trial_monitoring_remark: Mapped[str] = mapped_column(Text, default="")
    closing_status: Mapped[str | None] = mapped_column(String(40))
    closing_remark: Mapped[str] = mapped_column(Text, default="")

    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
