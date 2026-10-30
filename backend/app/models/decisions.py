"""Decision Inbox: a case that paused at a playbook gate and needs a person.

Approving resumes the paused agent run from the gate's on_approve node; rejecting resumes it
from on_reject. Either way the workflow then continues until it finishes or hits a blocker.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base, JSONType

DECISION_STATUSES = ("pending", "approved", "rejected")


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="ck_decisions_status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    loan_id: Mapped[str] = mapped_column(String(20), ForeignKey("msp.loan_id", ondelete="CASCADE"), index=True)
    agent_run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    workflow_run_id: Mapped[str | None] = mapped_column(ForeignKey("workflow_runs.id", ondelete="CASCADE"))
    stage_no: Mapped[int] = mapped_column(Integer)
    gate: Mapped[str] = mapped_column(String(60))  # playbook node that paused
    team: Mapped[str] = mapped_column(String(60))  # who reviews: LM Oversight, Onshore, ...
    title: Mapped[str] = mapped_column(String(300))
    reason: Mapped[str] = mapped_column(Text)
    findings: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)  # what the checks found
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[str | None] = mapped_column(String(120))
    note: Mapped[str | None] = mapped_column(Text)
