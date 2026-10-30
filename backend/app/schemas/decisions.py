"""Decision Inbox items and the reviewer's decision."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class DecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    loan_id: str
    borrower_name: str
    agent_run_id: str
    workflow_run_id: str | None
    stage_no: int
    stage_name: str
    gate: str
    team: str
    title: str
    reason: str
    findings: list[dict[str, Any]]
    status: Literal["pending", "approved", "rejected"]
    created_at: datetime
    decided_at: datetime | None
    decided_by: str | None
    note: str | None
    # Stage 3: the plans this evaluation proposed (trial_plans rows), one of which is approved.
    trial_plans: list[dict[str, Any]] = Field(default_factory=list)
    # Stage 5 MOD QC gate: the QC flags currently recorded (closing_qc).
    qc: dict[str, Any] | None = None
    # True when the gate is not in the current playbook (created before a playbook change): retire, don't decide.
    stale: bool = False


class QcFlags(BaseModel):
    """MOD QC verification. None = not reviewed (the Final Mod check stays pending)."""

    model_config = ConfigDict(extra="forbid")

    borrower_property_verified: bool | None = None
    principal_matches_msp: bool | None = None
    new_terms_match_plan: bool | None = None


class DecideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected"]
    decided_by: str = "reviewer"
    note: str | None = None
    selected_trial_plan: dict[str, Any] | str | None = None  # plan id, or {"plan_id": ...}
    selected_plan_id: str | None = None
    qc: QcFlags | None = None  # Stage 5 MOD QC gate only


class DecideResult(BaseModel):
    decision: DecisionOut
    stage_status: str | None
    workflow_status: str | None
    workflow_outcome: str | None
