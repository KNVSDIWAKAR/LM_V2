"""MSP loans: identity plus each servicing screen."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..core.database import get_db
from ..schemas.msp import MspLoanOut, MspLoanSummary

router = APIRouter(prefix="/api/loans", tags=["msp"])

IDENTITY = ("loan_id", "borrower_name", "coborrower_name", "borrower_ssn_last4", "coborrower_ssn_last4", "property_address", "mailing_address", "loan_type")


def loan_out(row: models.Msp) -> MspLoanOut:
    return MspLoanOut.model_validate(
        {
            **{c: getattr(row, c) for c in IDENTITY},
            "bankruptcy": row.bankruptcy,
            "foreclosure": row.foreclosure,
            "hoa": row.hoa,
            "servicing_data": {code.upper(): getattr(row, code) for code in models.SCREENS if getattr(row, code) is not None},
        }
    )


@router.get("", response_model=list[MspLoanSummary])
def list_loans(db: Session = Depends(get_db)) -> list[MspLoanSummary]:
    out = []
    for row in db.scalars(select(models.Msp).order_by(models.Msp.borrower_name)):
        dlq1 = row.dlq1 or {}
        out.append(
            MspLoanSummary.model_validate(
                {
                    **{c: getattr(row, c) for c in IDENTITY},
                    "investor_type": dlq1.get("investor_type"),
                    "property_state": dlq1.get("property_state"),
                    "months_delinquent": dlq1.get("months_delinquent"),
                    "upb_balance": dlq1.get("upb_balance"),
                    "bankruptcy_status": (row.bankruptcy or {}).get("status"),
                    "foreclosure_status": (row.foreclosure or {}).get("status"),
                }
            )
        )
    return out


@router.get("/{loan_id}", response_model=MspLoanOut)
def get_loan(loan_id: str, db: Session = Depends(get_db)) -> MspLoanOut:
    row = db.get(models.Msp, loan_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Loan not found")
    return loan_out(row)
