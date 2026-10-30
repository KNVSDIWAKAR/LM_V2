import json
import os
import tempfile
from pathlib import Path

# Point the app at a throwaway SQLite database before anything imports it.
_tmp = Path(tempfile.mkdtemp())
os.environ["DATABASE_URL"] = f"sqlite:///{(_tmp / 'test.db').as_posix()}"
os.environ["AUTO_FLOW_ENABLED"] = "false"  # tests drive the engine themselves
os.environ["FRONTEND_AUTO_BUILD"] = "false"  # never run npm from the test suite

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.database import Base, SessionLocal, create_tables, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import STAGES  # noqa: E402
from scripts.import_data import import_extracted, import_lm_stages, import_msp  # noqa: E402

LOAN = "1234567890"

MSP = {
    "meta": {"primary_key": "loan_id", "total_loans": 1},
    "loans": [
        {
            "loan_id": LOAN,
            "borrower_name": "Test Borrower",
            "coborrower_name": None,
            "borrower_ssn_last4": "6789",
            "coborrower_ssn_last4": None,
            "property_address": "1 Main St, Bellevue, WA 98004",
            "mailing_address": "1 Main St, Bellevue, WA 98004",
            "loan_type": "Asset",
            "bankruptcy": {"status": "None", "chapter": None, "case_number": None, "filing_date": None, "closed_date": None},
            "foreclosure": {"status": "Referred", "referral_date": "2026-08-22", "sale_date": None},
            "servicing_data": {
                "ANA1": {"tax_bill_date": "2026-03-10", "escrow_current": True, "tax_bill_on_file": True, "escrow_payment_amount": 385.0},
                "DLQ1": {
                    "due_date": "2026-04-19",
                    "loan_type": "Asset",
                    "upb_balance": 212400.0,
                    "investor_type": "GSE",
                    "property_state": "WA",
                    "mailing_address": "1 Main St, Bellevue, WA 98004",
                    "property_address": "1 Main St, Bellevue, WA 98004",
                    "months_delinquent": 1,
                    "number_of_borrowers": 1,
                },
                "NOTS": {"notes": ["MAA received", "Income verified"], "latest_note_date": "2026-03-20"},
                "USR2": {"status": "Partially-Claimed"},
            },
            "hoa": {"hoa_exists": False, "monthly_amount": 0.0, "association_name": None},
        }
    ],
}

LM_STATUS = {
    "meta": {"primary_key": "loan_id", "total_loans": 1},
    "lm_stage_config": [{"stage_no": s.no, "stage_name": s.name, "allowed_statuses": list(s.allowed)} for s in STAGES],
    "loans": [
        {
            "loan_id": LOAN,
            "lm_stages": [{"stage_no": s.no, "stage_name": s.name, "status": "", "remark": ""} for s in STAGES],
        }
    ],
}

EXTRACTED = {
    "meta": {"primary_key": "loan_id", "total_loans": 1},
    "loans": [
        {
            "loan_id": LOAN,
            "extraction_status": "success",
            "extracted_at": "2026-10-08 13:40:39.312920",
            "extracted_data": {
                "flags": {"only_one_paystub": True},
                "loan_id": LOAN,
                "PAYSTUBS": [
                    {
                        "net_pay": 1449.16,
                        "pay_date": "02/02/2026",
                        "gross_ytd": 4200,
                        "employer_ein": "91-2847301",
                        "annual_salary": 50400.0,
                        "employee_name": "Test Borrower",
                        "employer_name": "Acme",
                        "pay_frequency": "Semi-Monthly",
                        "is_handwritten": False,
                        "pay_period_end": "01/31/2026",
                        "has_variable_pay": False,
                        "has_ytd_earnings": True,
                        "pay_period_start": "01/16/2026",
                        "ytd_periods_paid": 2,
                        "gross_current_period": 2100,
                    }
                ],
                "CREDIT_REPORT": {"borrower_name": "Test Borrower", "representative_credit_score": 634},
                "BANK_STATEMENT": None,
                "Application_Form": {
                    "type": "MAA",
                    "borrower_name": "TEST BORROWER",
                    "property_address": "1 Main St, Bellevue, WA 98004",
                    "mailing_address": "1 Main St, Bellevue, WA 98004",
                    "income_sources": [{"type": "Wages", "gross_monthly_amount": 4200}],
                    "borrower_signature": True,
                    "coborrower_signature": False,
                },
                "LETTER_OF_EXPLANATION": None,
            },
        }
    ],
}


def _write(name: str, data: dict) -> Path:
    path = _tmp / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture()
def files() -> dict[str, Path]:
    return {"msp": _write("msp.json", MSP), "lm": _write("lm.json", LM_STATUS), "extracted": _write("ex.json", EXTRACTED)}


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    create_tables()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def loaded(client, files):
    with SessionLocal() as db:
        import_msp(db, files["msp"])
        import_lm_stages(db, files["lm"])
        import_extracted(db, files["extracted"])
        db.commit()
    return client
