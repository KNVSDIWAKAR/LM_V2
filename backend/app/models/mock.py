"""MOCK servicer data (POC only): how each loan's trial payments behave.

Loaded from data/mock_servicing.json by scripts/reset_db.py (or import_data --mock). When a
loan has a row here and MOCK_SERVICER_ENABLED is true, Trial Monitoring asks the mock
servicer (app/engine/mock_servicer.py) to post the trial payments into MSP DLQ1 before
matching them. Delete the rows (or disable the setting) to monitor real DLQ1 data only.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base, JSONType

# One entry per installment, in order:
#   on_time  paid in full on the due date
#   late     paid in full 5 days after the grace period ended
#   partial  half paid on the due date, nothing more
#   missed   nothing paid
#   not_yet  the simulated trial has not reached this installment (and the ones after it)
MOCK_PAYMENT_BEHAVIOURS = ("on_time", "late", "partial", "missed", "not_yet")


class MockServicing(Base):
    __tablename__ = "mock_servicing"

    loan_id: Mapped[str] = mapped_column(String(20), ForeignKey("msp.loan_id", ondelete="CASCADE"), primary_key=True)
    trial_payments: Mapped[list[str]] = mapped_column(JSONType, default=list)
    scenario: Mapped[str] = mapped_column(String(120), default="")
    loaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
