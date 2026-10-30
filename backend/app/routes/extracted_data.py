"""Knowledge Base: each loan's five extracted documents, readable one by one."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..core.database import get_db
from ..schemas.extracted_data import DocumentSummary, ExtractionFlags, LoanDocuments

router = APIRouter(prefix="/api/documents", tags=["extracted data"])


def _flags(row: models.ExtractedData) -> ExtractionFlags:
    return ExtractionFlags.model_validate(row.flags or {})


@router.get("/types")
def document_types() -> dict[str, str]:
    """Document column → display label, in reading order."""
    return models.DOCUMENT_TYPES


@router.get("", response_model=list[DocumentSummary])
def list_documents(db: Session = Depends(get_db)) -> list[DocumentSummary]:
    rows = db.execute(
        select(models.ExtractedData, models.Msp)
        .join(models.Msp, models.Msp.loan_id == models.ExtractedData.loan_id)
        .order_by(models.Msp.borrower_name)
    )
    return [
        DocumentSummary(
            loan_id=doc.loan_id,
            borrower_name=loan.borrower_name,
            coborrower_name=loan.coborrower_name,
            extraction_status=doc.extraction_status,
            extracted_at=doc.extracted_at,
            documents={t: bool(getattr(doc, t)) for t in models.DOCUMENT_TYPES},
            flags=[name for name, raised in _flags(doc).model_dump().items() if raised],
        )
        for doc, loan in rows
    ]


def _row_or_404(db: Session, loan_id: str) -> models.ExtractedData:
    doc = db.get(models.ExtractedData, loan_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="No documents for this loan")
    return doc


@router.get("/{loan_id}", response_model=LoanDocuments)
def loan_documents(loan_id: str, db: Session = Depends(get_db)) -> LoanDocuments:
    doc = _row_or_404(db, loan_id)
    loan = db.get(models.Msp, loan_id)
    return LoanDocuments.model_validate(
        {
            "loan_id": loan_id,
            "borrower_name": loan.borrower_name,
            "coborrower_name": loan.coborrower_name,
            "extraction_status": doc.extraction_status,
            "extracted_at": doc.extracted_at,
            "flags": _flags(doc),
            "document_labels": {**models.DOCUMENT_TYPES, **models.CLOSING_DOCUMENT_TYPES},
            **{t: getattr(doc, t) for t in (*models.DOCUMENT_TYPES, *models.CLOSING_DOCUMENT_TYPES)},
        }
    )


@router.get("/{loan_id}/{document_type}")
def loan_document(loan_id: str, document_type: str, db: Session = Depends(get_db)) -> dict:
    labels = {**models.DOCUMENT_TYPES, **models.CLOSING_DOCUMENT_TYPES}
    if document_type not in labels:
        raise HTTPException(status_code=404, detail=f"Unknown document type; use one of {', '.join(labels)}")
    doc = _row_or_404(db, loan_id)
    return {
        "loan_id": loan_id,
        "document_type": document_type,
        "label": labels[document_type],
        "data": getattr(doc, document_type),
    }
