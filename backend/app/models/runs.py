"""Execution history.

A **workflow run** carries one loan end to end through the five stages.
An **agent run** is one stage's agent working that loan: either a step of a workflow run
(workflow_run_id set) or run on its own from the process page. A loan can have many runs,
so each run has its own id.

Statuses:
  running    the graph is executing
  paused     a gate needs a person; a Decision Inbox item is open
  completed  agent run: the stage reached an end node · workflow run: all five stages advanced
  blocked    workflow run only: a stage ended without advancing (e.g. Missing Doc, End Case)
             or the next stage has no playbook yet
  failed     an error stopped it
"""

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base, JSONType

RUN_STATUSES = ("queued", "running", "paused", "completed", "blocked", "failed", "cancelled")
TRIGGERS = ("manual", "scheduled", "api")
_status_check = "status IN ({})".format(", ".join(f"'{s}'" for s in RUN_STATUSES))
_trigger_check = "trigger IN ({})".format(", ".join(f"'{t}'" for t in TRIGGERS))


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        CheckConstraint(_status_check, name="ck_workflow_runs_status"),
        CheckConstraint(_trigger_check, name="ck_workflow_runs_trigger"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    loan_id: Mapped[str | None] = mapped_column(String(20), ForeignKey("msp.loan_id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    trigger: Mapped[str] = mapped_column(String(20), default="manual")
    requested_by: Mapped[str] = mapped_column(String(120), default="")
    current_stage: Mapped[int] = mapped_column(Integer, default=1)
    outcome: Mapped[str] = mapped_column(Text, default="")  # where and why it stopped, in words
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)

    agent_runs: Mapped[list["AgentRun"]] = relationship(back_populates="workflow_run", order_by="AgentRun.stage_no")


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(_status_check, name="ck_agent_runs_status"),
        CheckConstraint(_trigger_check, name="ck_agent_runs_trigger"),
        CheckConstraint("stage_no BETWEEN 1 AND 5", name="ck_agent_runs_stage_no"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    loan_id: Mapped[str | None] = mapped_column(String(20), ForeignKey("msp.loan_id", ondelete="SET NULL"), index=True)
    workflow_run_id: Mapped[str | None] = mapped_column(ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True)
    stage_no: Mapped[int] = mapped_column(Integer, index=True)
    agent_name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    trigger: Mapped[str] = mapped_column(String(20), default="manual")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    input: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    trace: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    # The graph state saved when the run pauses at a gate, so an approval can resume it.
    state: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    error: Mapped[str | None] = mapped_column(Text)

    workflow_run: Mapped[WorkflowRun | None] = relationship(back_populates="agent_runs")
