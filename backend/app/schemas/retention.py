"""API contracts for the persisted retention report (not a second evaluation)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class Answer(BaseModel):
    model_config = ConfigDict(extra="allow")
    question_id: str
    question: str
    answer: bool | str | None
    confidence: float
    explanation: str
    result: Literal["pass", "fail", "pending", "neutral"]


class Stip(BaseModel):
    model_config = ConfigDict(extra="allow")
    stip_id: str
    question_id: str
    category: str
    document_required: str
    reason: str


class RetentionReport(BaseModel):
    model_config = ConfigDict(extra="allow")
    loan_id: str
    borrower_name: str
    evaluation_date: str
    review_start_date: str | None
    answers: list[Answer]
    stip_count: int
    stip_list: list[Stip]
    overall_confidence: float
    low_confidence_flags: list[dict[str, Any]]
    dm712_required: bool
    summary: dict[str, int]
    verdict: str


class RetentionCase(BaseModel):
    loan_id: str
    borrower_name: str
    investor: str | None
    months_delinquent: int | None
    hardship: str | None
    status: str | None
    stip_count: int | None
    remark: str
    last_run_id: str | None
    last_run_at: datetime | None
    last_run_status: str | None
    open_decision_id: str | None
    pending_reason: str | None


class RetentionCaseDetail(RetentionCase):
    report: RetentionReport | None
    trace: list[dict[str, Any]]
    can_route_to_inbox: bool


class RetentionSummary(BaseModel):
    loans_in_book: int
    total_records: int
    eligible: int
    counts: dict[str, int]
    run_count: int
    last_run_id: str | None
    last_run_at: datetime | None
    records: list[RetentionCase]
    pending_actions: list[RetentionCase]
    active_run_ids: list[str] = []