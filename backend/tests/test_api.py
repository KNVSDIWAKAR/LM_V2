import json

import pytest

from app.core.database import SessionLocal
from scripts.import_data import import_extracted, import_lm_stages, import_msp

from .conftest import EXTRACTED, LOAN


def test_starts_empty(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/loans").json() == []
    assert client.get("/api/documents").json() == []
    assert client.get("/api/workflow-runs").json() == []
    assert client.get("/api/agent-runs").json() == []


def test_msp_screens_are_separate(loaded):
    loan = loaded.get(f"/api/loans/{LOAN}").json()
    screens = loan["servicing_data"]
    assert set(k for k, v in screens.items() if v) == {"ANA1", "DLQ1", "NOTS", "USR2"}
    assert screens["DLQ1"]["months_delinquent"] == 1 and screens["DLQ1"]["due_date"] == "2026-04-19"
    assert screens["NOTS"]["notes"] == ["MAA received", "Income verified"]
    assert loan["foreclosure"]["status"] == "Referred"
    summary = loaded.get("/api/loans").json()[0]
    assert summary["investor_type"] == "GSE" and summary["foreclosure_status"] == "Referred"
    assert loaded.get("/api/loans/nope").status_code == 404


def test_documents_one_column_each(loaded):
    listing = loaded.get("/api/documents").json()
    assert listing[0]["documents"] == {
        "application_form": True,
        "paystubs": True,
        "bank_statement": False,
        "credit_report": True,
        "letter_of_explanation": False,
    }
    assert listing[0]["flags"] == ["only_one_paystub"]

    docs = loaded.get(f"/api/documents/{LOAN}").json()
    assert docs["paystubs"][0]["employer_name"] == "Acme"
    assert docs["credit_report"]["representative_credit_score"] == 634
    assert docs["bank_statement"] is None and docs["flags"]["only_one_paystub"] is True

    one = loaded.get(f"/api/documents/{LOAN}/application_form").json()
    assert one["label"] == "Application Form (MAA)" and one["data"]["income_sources"][0]["gross_monthly_amount"] == 4200
    assert loaded.get(f"/api/documents/{LOAN}/nope").status_code == 404


def test_import_rejects_unknown_fields(client, files, tmp_path):
    bad = json.loads(json.dumps(EXTRACTED))
    bad["loans"][0]["extracted_data"]["CREDIT_REPORT"]["surprise"] = 1
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad))
    with SessionLocal() as db:
        import_msp(db, files["msp"])
        with pytest.raises(Exception, match="surprise"):
            import_extracted(db, path)


def test_import_is_idempotent(loaded, files):
    with SessionLocal() as db:
        import_msp(db, files["msp"])
        import_lm_stages(db, files["lm"])
        import_extracted(db, files["extracted"])
        db.commit()
    assert len(loaded.get("/api/loans").json()) == 1
    assert len(loaded.get(f"/api/loans/{LOAN}").json()["servicing_data"]["NOTS"]["notes"]) == 2


def test_stage_status_only_allows_configured_values(loaded):
    stages = loaded.get("/api/lm/stages").json()
    assert [s["stage_name"] for s in stages] == ["Intake", "Retention Eligibility", "Trial UW", "Trial Monitoring", "Closing"]

    status = loaded.get(f"/api/lm/status/{LOAN}").json()
    assert [s["status"] for s in status["stages"]] == [None] * 5

    assert loaded.put(f"/api/lm/status/{LOAN}/1", json={"status": "Denied"}).status_code == 422
    ok = loaded.put(f"/api/lm/status/{LOAN}/1", json={"status": "Missing Doc", "remark": "No LOE"}).json()
    assert ok["stages"][0]["status"] == "Missing Doc" and ok["stages"][0]["remark"] == "No LOE" and ok["updated_at"]
    cleared = loaded.put(f"/api/lm/status/{LOAN}/1", json={"status": ""}).json()
    assert cleared["stages"][0]["status"] is None


def test_import_accepts_trial_and_closing_fields(client, tmp_path):
    from copy import deepcopy

    from app import models
    from app.core.database import create_tables

    from .conftest import MSP

    msp = deepcopy(MSP)
    screens = msp["loans"][0]["servicing_data"]
    screens["DLQ1"]["interest_rate"] = 4.5
    screens["DLQ1"]["payment_history"] = [{"payment_date": "2026-12-01", "amount": 1487.5, "transaction_type": "Trial"}]
    screens["TASK1"] = {"tasks": [{"task_id": "BKCASH", "status": "Completed", "opened_date": "2026-09-01"}]}
    screens["MES1"] = {"tasks": []}
    screens["LSMR"] = {"current_interest_rate": 4.5, "new_interest_rate": 4.0, "new_term_months": 480,
                       "new_principal_balance": 212400.0, "new_payment_amount": 1272.0}
    screens["LMT3"] = {"x65_date": "2026-10-05", "e68_date": "2026-10-09"}
    extracted = deepcopy(EXTRACTED)
    extracted["loans"][0]["extracted_data"]["NEIGHBOURHOOD_DOCUMENT"] = {
        "document_date": "10/01/2026", "borrower_name": "Test Borrower", "property_address": "1 Main St",
        "upb": 212400.0, "prior_partial_claim_amounts": []}
    (tmp_path / "msp.json").write_text(json.dumps(msp), encoding="utf-8")
    (tmp_path / "ex.json").write_text(json.dumps(extracted), encoding="utf-8")
    with SessionLocal() as db:
        import_msp(db, tmp_path / "msp.json")
        import_extracted(db, tmp_path / "ex.json")
        db.commit()
        row = db.get(models.Msp, LOAN)
        assert row.dlq1["payment_history"][0]["payment_date"] == "2026-12-01"
        assert row.task1["tasks"][0]["task_id"] == "BKCASH" and row.lsmr["new_term_months"] == 480
        assert db.get(models.ExtractedData, LOAN).neighbourhood_document["upb"] == 212400.0
    create_tables()  # idempotent on an up-to-date schema (adds nothing)
    assert client.get(f"/api/loans/{LOAN}").status_code == 200
