"""Workflow runs (end-to-end), agent runs (one stage), and the requests that start them."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

RunStatus = Literal["queued", "running", "paused", "completed", "blocked", "failed", "cancelled"]
Trigger = Literal["manual", "scheduled", "api"]


class RunRequest(BaseModel):
    """Start runs. Without loan_id, every loan that is waiting is picked up."""

    model_config = ConfigDict(extra="forbid")

    loan_id: str | None = None
    requested_by: str = ""


class RunQueued(BaseModel):
    queued: int
    loan_ids: list[str]


class ProcessRunQueued(RunQueued):
    run_ids: list[str] | None = None
    skipped: list[dict[str, str]] | None = None


class ProcessRunRequest(RunRequest):
    """Explicit re-evaluation is currently supported only by retention."""

    rerun: bool = False


class AgentRunOut(BaseModel):
    id: str
    workflow_run_id: str | None
    stage_no: int
    stage_name: str
    loan_id: str | None
    agent_name: str
    status: RunStatus
    trigger: Trigger
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    input: dict[str, Any] | None
    output: dict[str, Any] | None
    trace: list[dict[str, Any]]
    error: str | None


class WorkflowRunOut(BaseModel):
    id: str
    status: RunStatus
    trigger: Trigger
    requested_by: str
    loan_id: str | None
    current_stage: int
    current_stage_name: str
    outcome: str
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    error: str | None
    stages_total: int
    stages_completed: int


class WorkflowRunDetail(WorkflowRunOut):
    agent_runs: list[AgentRunOut]


class AutoFlowStatus(BaseModel):
    enabled: bool
    interval_seconds: int
    last_tick: datetime | None
    last_moved: int
    last_error: str | None


class AutoFlowUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
