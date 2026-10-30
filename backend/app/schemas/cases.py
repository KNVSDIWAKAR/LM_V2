"""Case pages for Trial UW, Trial Monitoring and Final UW & Closing: what the agent saw,
what it decided, and the records people maintain (QC flags, recording date)."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class RunSummary(BaseModel):
    id: str
    status: str
    trigger: str
    started_at: datetime
    finished_at: datetime | None
    outcome: str | None  # final stage status, or the gate it is paused at
    error: str | None


class LatestRun(RunSummary):
    rules_version: str | None
    start_at: str | None  # entry node; fm_trial_outcome on a Final Mod re-check
    findings: list[dict[str, Any]]
    trace: list[dict[str, Any]]
    stage_report: dict[str, Any]
    paused_at: dict[str, Any] | None


class StageCase(BaseModel):
    stage_no: int
    stage_name: str
    loan_id: str
    borrower_name: str
    status: str | None
    remark: str
    open_decision_id: str | None
    latest_run: LatestRun | None
    runs: list[RunSummary]
    # Stage-specific records, read live from the database (see routes/cases.py).
    data: dict[str, Any]


class ClosingRecordUpdate(BaseModel):
    """Fields MOD QC / closing staff record. Omitted fields are left unchanged; null clears a QC flag."""

    model_config = ConfigDict(extra="forbid")

    borrower_property_verified: bool | None = None
    principal_matches_msp: bool | None = None
    new_terms_match_plan: bool | None = None
    recorded_date: date | None = None
    updated_by: str = "closing-page"
    note: str | None = None
