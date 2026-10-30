"""The five processes: status board, loans per stage, and the playbook behind each."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ProcessSummary(BaseModel):
    stage_no: int
    name: str
    key: str
    allowed_statuses: list[str]
    playbook: bool  # False until harness/<process>/playbook.yaml exists
    agent: str | None
    rules_version: str | None
    advances: list[str]  # statuses that hand a loan on to the next stage
    counts: dict[str, int]  # "Not reached", "Waiting", then each allowed status → loans
    waiting: int  # loans handed on to this stage and not yet worked
    runnable: int  # waiting + re-runnable (next monitoring cycle, Final Mod re-check); what Run picks up
    running: int
    paused: int


class LoanAtStage(BaseModel):
    loan_id: str
    borrower_name: str
    status: str | None
    position: str  # not_reached | waiting | worked
    remark: str
    last_run_id: str | None
    last_run_status: str | None
    last_run_at: datetime | None
    open_decision_id: str | None
    runnable: bool = False  # Run would pick this loan up now (waiting, or a re-runnable status)


class ProcessDetail(ProcessSummary):
    loans: list[LoanAtStage]


class PlaybookNode(BaseModel):
    id: str
    title: str
    kind: str  # run | gate | end
    run: str | None
    routes: dict[str, str]
    team: str | None
    status: str | None
    advance: bool


class PlaybookOut(BaseModel):
    stage_no: int
    process: str
    name: str
    agent: str
    start: str
    rules_version: str
    nodes: list[PlaybookNode]
    rules: dict[str, Any]
    mermaid: str
    files: dict[str, str]  # file name (relative to backend/) → its YAML text
