"""LM stage tracking: the five stages, their allowed statuses, and each loan's status per stage."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..core.database import get_db
from ..schemas.lm_stages import LoanStageOut, LoanStatusOut, StageOut, StageStatusUpdate

router = APIRouter(prefix="/api/lm", tags=["lm stages"])


def _status_out(loan: models.Msp, row: models.LmStages | None) -> LoanStatusOut:
    return LoanStatusOut(
        loan_id=loan.loan_id,
        borrower_name=loan.borrower_name,
        updated_at=row.updated_at if row else None,
        stages=[
            LoanStageOut(
                stage_no=s.no,
                stage_name=s.name,
                status=getattr(row, f"{s.key}_status") if row else None,
                remark=getattr(row, f"{s.key}_remark") if row else "",
            )
            for s in models.STAGES
        ],
    )


@router.get("/stages", response_model=list[StageOut])
def stages() -> list[StageOut]:
    return [StageOut(stage_no=s.no, stage_name=s.name, allowed_statuses=list(s.allowed)) for s in models.STAGES]


@router.get("/status", response_model=list[LoanStatusOut])
def all_status(db: Session = Depends(get_db)) -> list[LoanStatusOut]:
    rows = db.execute(
        select(models.Msp, models.LmStages)
        .outerjoin(models.LmStages, models.LmStages.loan_id == models.Msp.loan_id)
        .order_by(models.Msp.borrower_name)
    )
    return [_status_out(loan, row) for loan, row in rows]


@router.get("/status/{loan_id}", response_model=LoanStatusOut)
def loan_status(loan_id: str, db: Session = Depends(get_db)) -> LoanStatusOut:
    loan = db.get(models.Msp, loan_id)
    if loan is None:
        raise HTTPException(status_code=404, detail="Loan not found")
    return _status_out(loan, db.get(models.LmStages, loan_id))


@router.put("/status/{loan_id}/{stage_no}", response_model=LoanStatusOut)
def set_status(loan_id: str, stage_no: int, body: StageStatusUpdate, db: Session = Depends(get_db)) -> LoanStatusOut:
    loan = db.get(models.Msp, loan_id)
    if loan is None:
        raise HTTPException(status_code=404, detail="Loan not found")
    stage = models.STAGE_BY_NO.get(stage_no)
    if stage is None:
        raise HTTPException(status_code=404, detail="Unknown stage")
    if body.status is not None and body.status not in stage.allowed:
        raise HTTPException(status_code=422, detail=f"'{body.status}' is not allowed for {stage.name}. Allowed: {', '.join(stage.allowed)}")

    row = db.get(models.LmStages, loan_id) or models.LmStages(loan_id=loan_id)
    setattr(row, f"{stage.key}_status", body.status)
    setattr(row, f"{stage.key}_remark", body.remark)
    row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    db.commit()
    return _status_out(loan, row)
