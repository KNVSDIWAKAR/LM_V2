"""MOCK servicer file (data/mock_servicing.json): validated on import like every other data file."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from .extracted_data import NeighbourhoodDocument
from .msp import Lmt3, Lsmr, TaskScreen


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MockDlq1(Strict):
    interest_rate: float | None = None


class MockScreens(Strict):
    """Screens merged into the loan's MSP row (LMT3 / DLQ1: only the keys given)."""

    TASK1: TaskScreen | None = None
    MES1: TaskScreen | None = None
    LSMR: Lsmr | None = None
    LMT3: Lmt3 | None = None
    DLQ1: MockDlq1 | None = None


class MockLoanIn(Strict):
    loan_id: str
    scenario: str
    trial_payments: list[Literal["on_time", "late", "partial", "missed", "not_yet"]]
    servicing_data: MockScreens = MockScreens()
    neighbourhood_document: NeighbourhoodDocument | None = None
