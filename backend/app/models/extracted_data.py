"""Documents extracted from each borrower's loss-mitigation package: one row per loan, one column per document."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base, JSONType

# Column name → label, in the order a reviewer reads the package.
DOCUMENT_TYPES: dict[str, str] = {
    "application_form": "Application Form (MAA)",
    "paystubs": "Paystubs",
    "bank_statement": "Bank Statement",
    "credit_report": "Credit Report",
    "letter_of_explanation": "Letter of Explanation",
}
# Documents used only after the trial (Final Underwriting). Kept apart so Intake and Retention
# never treat them as part of the borrower's package.
CLOSING_DOCUMENT_TYPES: dict[str, str] = {
    "neighbourhood_document": "Neighbourhood Document",
}


class ExtractedData(Base):
    __tablename__ = "extracted_data"

    loan_id: Mapped[str] = mapped_column(String(20), ForeignKey("msp.loan_id", ondelete="CASCADE"), primary_key=True)
    extraction_status: Mapped[str] = mapped_column(String(20))
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime)
    flags: Mapped[dict[str, bool]] = mapped_column(JSONType, default=dict)

    # The five documents (NULL when the borrower did not submit it).
    application_form: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    paystubs: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONType)
    bank_statement: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    credit_report: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    letter_of_explanation: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    neighbourhood_document: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
