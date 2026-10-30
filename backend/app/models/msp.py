"""MSP (servicing system of record): one row per loan.

Identity fields are plain columns. Each MSP screen is its own JSONB column, so screens stay
separate (DLQ1 never mixes with HAZ1) while the loan stays one row.
"""

from typing import Any

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base, JSONType

SCREENS = ("ana1", "dlq1", "haz1", "lmt1", "lmt3", "nots", "usr2", "task1", "mes1", "lsmr")


class Msp(Base):
    __tablename__ = "msp"

    loan_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    borrower_name: Mapped[str] = mapped_column(String(120))
    coborrower_name: Mapped[str | None] = mapped_column(String(120))
    borrower_ssn_last4: Mapped[str] = mapped_column(String(4))
    coborrower_ssn_last4: Mapped[str | None] = mapped_column(String(4))
    property_address: Mapped[str] = mapped_column(String(255))
    mailing_address: Mapped[str] = mapped_column(String(255))
    loan_type: Mapped[str] = mapped_column(String(40))

    bankruptcy: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    foreclosure: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    hoa: Mapped[dict[str, Any] | None] = mapped_column(JSONType)

    # Servicing screens.
    ana1: Mapped[dict[str, Any] | None] = mapped_column(JSONType)  # escrow analysis
    dlq1: Mapped[dict[str, Any] | None] = mapped_column(JSONType)  # delinquency
    haz1: Mapped[dict[str, Any] | None] = mapped_column(JSONType)  # hazard insurance
    lmt1: Mapped[dict[str, Any] | None] = mapped_column(JSONType)  # loss-mit status
    lmt3: Mapped[dict[str, Any] | None] = mapped_column(JSONType)  # loss-mit review dates
    nots: Mapped[dict[str, Any] | None] = mapped_column(JSONType)  # servicing notes
    usr2: Mapped[dict[str, Any] | None] = mapped_column(JSONType)  # user-defined status
    task1: Mapped[dict[str, Any] | None] = mapped_column(JSONType)  # servicing tasks (Final UW hold check)
    mes1: Mapped[dict[str, Any] | None] = mapped_column(JSONType)  # message/event tasks (Final UW hold check)
    lsmr: Mapped[dict[str, Any] | None] = mapped_column(JSONType)  # loss-mit modification terms
