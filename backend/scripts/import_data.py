"""Load the MSP, LM-status and extracted-document files into msp, lm_stages and extracted_data.

Every record is validated against the Pydantic schemas first (unknown or missing fields stop
the import), then upserted by loan_id, so re-running with newer files is safe.
Runs are never touched.

    python -m scripts.import_data --msp msp.json --lm-status lm_status.json --extracted extracted_data.json
    python -m scripts.import_data --mock mock_servicing.json      # POC mock servicer data (after msp / extracted)
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models  # noqa: E402
from app.core.database import SessionLocal, create_tables  # noqa: E402
from app.schemas.extracted_data import DocumentSet, ExtractionFlags  # noqa: E402
from app.schemas.lm_stages import LoanStagesIn, StageConfigIn  # noqa: E402
from app.schemas.mock import MockLoanIn  # noqa: E402
from app.schemas.msp import MspLoanIn  # noqa: E402


def _loans(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    loans = data["loans"]
    expected = data.get("meta", {}).get("total_loans")
    if expected is not None and expected != len(loans):
        raise SystemExit(f"{path.name}: meta says {expected} loans but file has {len(loans)}")
    return loans


def import_msp(db: Session, path: Path) -> int:
    loans = [MspLoanIn.model_validate(raw) for raw in _loans(path)]
    for loan in loans:
        data = loan.model_dump(mode="json")
        screens = data.pop("servicing_data")
        db.merge(models.Msp(**data, **{code: screens.get(code.upper()) for code in models.SCREENS}))
    db.flush()
    return len(loans)


def import_lm_stages(db: Session, path: Path) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    # The stage definitions live in code (they drive the CHECK constraints); the file must agree.
    for cfg in (StageConfigIn.model_validate(c) for c in data["lm_stage_config"]):
        stage = models.STAGE_BY_NO.get(cfg.stage_no)
        if stage is None or stage.name != cfg.stage_name or list(stage.allowed) != cfg.allowed_statuses:
            raise SystemExit(f"{path.name}: stage {cfg.stage_no} ({cfg.stage_name}) differs from app/models/lm_stages.py")

    loans = [LoanStagesIn.model_validate(raw) for raw in _loans(path)]
    for loan in loans:
        row = models.LmStages(loan_id=loan.loan_id)
        for entry in loan.lm_stages:
            stage = models.STAGE_BY_NO.get(entry.stage_no)
            if stage is None:
                raise SystemExit(f"Loan {loan.loan_id}: unknown stage {entry.stage_no}")
            status = entry.status or None
            if status is not None and status not in stage.allowed:
                raise SystemExit(f"Loan {loan.loan_id}: '{status}' is not allowed for {stage.name}")
            setattr(row, f"{stage.key}_status", status)
            setattr(row, f"{stage.key}_remark", entry.remark)
        db.merge(row)
    db.flush()
    return len(loans)


def import_extracted(db: Session, path: Path) -> int:
    loans = _loans(path)
    for raw in loans:
        body = raw["extracted_data"]
        if body.get("loan_id", raw["loan_id"]) != raw["loan_id"]:
            raise SystemExit(f"Loan {raw['loan_id']}: extracted_data.loan_id is {body['loan_id']}")
        docs = DocumentSet.model_validate(
            {
                "application_form": body.get("Application_Form"),
                "paystubs": body.get("PAYSTUBS"),
                "bank_statement": body.get("BANK_STATEMENT"),
                "credit_report": body.get("CREDIT_REPORT"),
                "letter_of_explanation": body.get("LETTER_OF_EXPLANATION"),
                "neighbourhood_document": body.get("NEIGHBOURHOOD_DOCUMENT"),
            }
        )
        flags = ExtractionFlags.model_validate(body.get("flags") or {})
        extracted_at = raw.get("extracted_at")
        db.merge(
            models.ExtractedData(
                loan_id=raw["loan_id"],
                extraction_status=raw["extraction_status"],
                extracted_at=datetime.fromisoformat(extracted_at) if extracted_at else None,
                flags=flags.model_dump(),
                **docs.model_dump(mode="json"),
            )
        )
    db.flush()
    return len(loans)


def import_mock_servicing(db: Session, path: Path) -> int:
    """MOCK servicer data: trial payment patterns plus the MSP screens / document Final UW reads.

    Screens are merged into the existing loan (LMT3 and DLQ1 only the keys given), so the real
    MSP import stays the base. Loans must already exist in msp."""
    loans = [MockLoanIn.model_validate(raw) for raw in _loans(path)]
    now = datetime.now(timezone.utc)
    for loan in loans:
        msp = db.get(models.Msp, loan.loan_id)
        if msp is None:
            raise SystemExit(f"{path.name}: loan {loan.loan_id} is not in msp; import msp.json first")
        screens = loan.servicing_data.model_dump(mode="json", exclude_none=True)
        for code in ("TASK1", "MES1", "LSMR"):
            if code in screens:
                setattr(msp, code.lower(), screens[code])
        for code in ("LMT3", "DLQ1"):
            if code in screens:
                current = getattr(msp, code.lower()) or {}
                setattr(msp, code.lower(), {**current, **screens[code]})
        if loan.neighbourhood_document is not None:
            doc = db.get(models.ExtractedData, loan.loan_id)
            if doc is None:
                raise SystemExit(f"{path.name}: loan {loan.loan_id} has no extracted_data row; import extracted_data.json first")
            doc.neighbourhood_document = loan.neighbourhood_document.model_dump(mode="json")
        db.merge(models.MockServicing(loan_id=loan.loan_id, trial_payments=list(loan.trial_payments), scenario=loan.scenario, loaded_at=now))
    db.flush()
    return len(loans)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--msp", type=Path, help="msp.json")
    parser.add_argument("--lm-status", type=Path, help="lm_status.json")
    parser.add_argument("--extracted", type=Path, help="extracted_data.json")
    parser.add_argument("--mock", type=Path, help="mock_servicing.json (POC mock servicer)")
    args = parser.parse_args()
    if not (args.msp or args.lm_status or args.extracted or args.mock):
        parser.error("give at least one file")

    create_tables()
    with SessionLocal() as db:
        # MSP first: the other two reference msp.loan_id.
        if args.msp:
            print(f"msp:             {import_msp(db, args.msp)} loans")
        if args.lm_status:
            print(f"lm_stages:       {import_lm_stages(db, args.lm_status)} loans")
        if args.extracted:
            print(f"extracted_data:  {import_extracted(db, args.extracted)} loans")
        if args.mock:
            print(f"mock_servicing:  {import_mock_servicing(db, args.mock)} loans (MOCK)")
        db.commit()
    print("Import committed.")


if __name__ == "__main__":
    main()
