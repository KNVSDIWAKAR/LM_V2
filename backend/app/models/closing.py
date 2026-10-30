"""Final Mod & Closing facts that people record (one row per loan).

The three QC flags are set by MOD QC (in the Decision Inbox or on the closing page);
NULL means not reviewed yet, which the Final Mod checks report as pending.
mod_approved_at is written when Human Sign-off approves the Underwriting plan and starts the
14-day recording SLA. recorded_date is entered when the county records the modification.
"""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base

QC_FLAGS = ("borrower_property_verified", "principal_matches_msp", "new_terms_match_plan")


class ClosingQc(Base):
    __tablename__ = "closing_qc"

    loan_id: Mapped[str] = mapped_column(String(20), ForeignKey("msp.loan_id", ondelete="CASCADE"), primary_key=True)

    borrower_property_verified: Mapped[bool | None] = mapped_column(Boolean)
    principal_matches_msp: Mapped[bool | None] = mapped_column(Boolean)
    new_terms_match_plan: Mapped[bool | None] = mapped_column(Boolean)
    qc_by: Mapped[str | None] = mapped_column(String(120))
    qc_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    qc_note: Mapped[str | None] = mapped_column(Text)

    mod_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mod_approved_by: Mapped[str | None] = mapped_column(String(120))

    recorded_date: Mapped[date | None] = mapped_column(Date)
    recorded_by: Mapped[str | None] = mapped_column(String(120))

    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
