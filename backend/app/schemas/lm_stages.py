"""Loss-mitigation stages and each loan's status per stage (table lm_stages)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class StageConfigIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage_no: int
    stage_name: str
    allowed_statuses: list[str]


class LoanStageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage_no: int
    stage_name: str
    status: str = ""
    remark: str = ""


class LoanStagesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    loan_id: str
    lm_stages: list[LoanStageIn]


class StageOut(BaseModel):
    stage_no: int
    stage_name: str
    allowed_statuses: list[str]


class LoanStageOut(BaseModel):
    stage_no: int
    stage_name: str
    status: str | None
    remark: str


class LoanStatusOut(BaseModel):
    loan_id: str
    borrower_name: str
    updated_at: datetime | None
    stages: list[LoanStageOut]


class StageStatusUpdate(BaseModel):
    """Set a loan's status for one stage; null clears it back to not started."""

    model_config = ConfigDict(extra="forbid")

    status: str | None
    remark: str = ""

    @field_validator("status")
    @classmethod
    def blank_is_none(cls, v: str | None) -> str | None:
        return v or None
