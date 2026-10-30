"""Engine: YAML playbook → LangGraph, pauses to the Decision Inbox, resumes on a decision."""

from datetime import date, datetime, timedelta

import pytest

from app import models
from app.core.database import SessionLocal
from app.engine.scheduler import auto_flow

from .conftest import EXTRACTED, LOAN

APPLICATION_FORM = EXTRACTED["loans"][0]["extracted_data"]["Application_Form"]


def _complete_package(**msp_changes) -> None:
    """Give the fixture loan an application form that matches MSP; optionally change its MSP row."""
    with SessionLocal() as db:
        doc = db.get(models.ExtractedData, LOAN)
        doc.application_form = {**doc.application_form, "borrower_ssn_last4": "6789"}
        msp = db.get(models.Msp, LOAN)
        for key, value in msp_changes.items():
            setattr(msp, key, value)
        db.commit()


def _no_application_form() -> None:
    with SessionLocal() as db:
        db.get(models.ExtractedData, LOAN).application_form = None
        db.commit()


def _tick() -> int:
    return auto_flow.tick("manual")


def _workflow(client) -> dict:
    return client.get(f"/api/workflow-runs?loan_id={LOAN}").json()[0]


def _intake(client) -> dict:
    return client.get(f"/api/lm/status/{LOAN}").json()["stages"][0]


def test_playbook_compiles_from_yaml(loaded):
    pb = loaded.get("/api/processes/1/playbook").json()
    nodes = {n["id"]: n for n in pb["nodes"]}
    assert pb["start"] == "load_case" and nodes["msp_check"]["routes"]["bk_active"] == "end_case_bk"
    assert nodes["complete"]["advance"] is True and "load_case" in pb["mermaid"]
    retention = loaded.get("/api/processes/2/playbook")
    assert retention.status_code == 200
    assert retention.json()["process"] == "retention"
    summary = {p["stage_no"]: p for p in loaded.get("/api/processes").json()}
    assert summary[1]["playbook"] is True and summary[2]["playbook"] is True


def test_bad_playbook_is_rejected(tmp_path):
    from app.engine.playbook import load_playbook

    (tmp_path / "rules.yaml").write_text("version: x\n")
    (tmp_path / "playbook.yaml").write_text(
        "process: t\nstage_no: 1\nname: T\nagent: A\nrules: rules.yaml\nstart: a\n"
        "nodes:\n"
        "  a:\n    run: intake.load_case\n    next: nowhere\n"
        "  done:\n    end: true\n    status: Complete\n    advance: true\n"
    )
    with pytest.raises(ValueError, match="nowhere"):
        load_playbook(tmp_path / "playbook.yaml")


def test_missing_documents_stop_at_intake(loaded):
    _no_application_form()
    assert _tick() == 1
    wf = _workflow(loaded)
    assert wf["status"] == "blocked" and wf["outcome"] == "Stopped at Intake: Missing Doc"
    assert _intake(loaded)["status"] == "Missing Doc" and "Application Form (MAA) not received" in _intake(loaded)["remark"]
    assert _tick() == 0  # nothing new, so it does not run again


def test_new_documents_rerun_a_blocked_case(loaded):
    _no_application_form()
    _tick()
    with SessionLocal() as db:
        doc = db.get(models.ExtractedData, LOAN)
        doc.application_form = APPLICATION_FORM
        doc.extracted_at = datetime(2099, 1, 1)
        db.commit()
    assert _tick() == 1
    runs = loaded.get(f"/api/workflow-runs?loan_id={LOAN}").json()
    assert len(runs) == 2 and runs[0]["outcome"] == "Stopped at Retention Eligibility: Facially Incomplete"
    assert runs[0]["error"] is None


def test_clean_case_hands_off_and_moves_to_next_stage(loaded):
    _complete_package()
    _tick()
    wf = loaded.get(f"/api/workflow-runs/{_workflow(loaded)['id']}").json()
    assert wf["status"] == "blocked" and wf["current_stage"] == 2 and wf["stages_completed"] == 1
    run = wf["agent_runs"][0]
    assert [t["node"] for t in run["trace"]] == ["load_case", "msp_check", "document_checks", "handoff", "complete"]
    assert run["output"]["handoff"]["to_team"] == "LM Setup" and run["output"]["rules_version"] == "2026.10.2"
    assert _intake(loaded)["status"] == "Complete"


def test_mismatch_pauses_then_approval_resumes(loaded):
    _complete_package(borrower_ssn_last4="0000")
    _tick()
    wf = _workflow(loaded)
    assert wf["status"] == "paused" and wf["outcome"] == "Paused at Intake: LM Oversight review"
    assert _intake(loaded)["status"] == "In Human Review"

    [decision] = loaded.get("/api/decisions?status=pending").json()
    assert decision["gate"] == "mismatch_review" and {f["check"] for f in decision["findings"]} == {"Borrower SSN"}
    assert _tick() == 0  # a paused case waits for the person

    result = loaded.post(f"/api/decisions/{decision['id']}/decide", json={"decision": "approved", "decided_by": "qa"}).json()
    assert result["stage_status"] == "Complete" and result["workflow_status"] == "blocked"
    assert loaded.post(f"/api/decisions/{decision['id']}/decide", json={"decision": "approved"}).status_code == 409
    run = loaded.get(f"/api/workflow-runs/{wf['id']}").json()["agent_runs"][0]
    assert run["status"] == "completed" and run["output"]["decision"]["approved"] is True


def test_mismatch_rejected_ends_case(loaded):
    _complete_package(property_address="9 Other Rd, Seattle, WA 98101")
    _tick()
    [decision] = loaded.get("/api/decisions?status=pending").json()
    assert decision["gate"] == "mismatch_review" and {f["check"] for f in decision["findings"]} == {"Property address"}
    assert loaded.post(f"/api/decisions/{decision['id']}/decide", json={"decision": "rejected"}).status_code == 422
    result = loaded.post(f"/api/decisions/{decision['id']}/decide", json={"decision": "rejected", "note": "Wrong property"}).json()
    assert result["stage_status"] == "End Case" and result["workflow_outcome"] == "Stopped at Intake: End Case"


def test_process_run_button_continues_the_workflow(loaded):
    _complete_package()
    response = loaded.post("/api/processes/2/run")
    assert response.status_code == 202
    assert response.json() == {"queued": 0, "loan_ids": []}  # Intake has not completed yet.
    assert loaded.post("/api/processes/1/run").json() == {"queued": 1, "loan_ids": [LOAN]}
    runs = loaded.get("/api/agent-runs?stage_no=1").json()
    assert len(runs) == 1 and runs[0]["workflow_run_id"] is not None  # every agent run belongs to a workflow
    assert _workflow(loaded)["current_stage"] == 2
    assert loaded.post("/api/processes/1/run").json()["queued"] == 0  # nothing left waiting at Intake


def test_completed_intake_runs_retention_at_the_next_stage(loaded):
    _complete_package()
    before = {p["stage_no"]: p for p in loaded.get("/api/processes").json()}
    assert before[1]["counts"]["Waiting"] == 1 and before[2]["counts"]["Not reached"] == 1

    _tick()
    after = {p["stage_no"]: p for p in loaded.get("/api/processes").json()}
    assert after[1]["counts"]["Complete"] == 1 and after[1]["waiting"] == 0
    assert after[2]["counts"]["Facially Incomplete"] == 1 and after[2]["waiting"] == 0
    stage2 = loaded.get(f"/api/lm/status/{LOAN}").json()["stages"][1]
    assert stage2["status"] == "Facially Incomplete"
    [row] = loaded.get("/api/processes/2").json()["loans"]
    assert row["position"] == "worked" and row["last_run_status"] == "completed"


def test_stale_candidate_list_cannot_run_a_loan_twice(loaded):
    """The race behind duplicate inbox items: two workers holding the same out-of-date list."""
    from app.engine import runner

    _complete_package(borrower_ssn_last4="0000")
    with SessionLocal() as db:
        stale = runner.workflow_candidates(db)
    assert _tick() == 1  # the first worker pauses the case for review
    with SessionLocal() as db:
        for loan_id, _ in stale:  # the second worker re-checks under the lock, as the scheduler does
            assert loan_id not in dict(runner.workflow_candidates(db, loan_id))
    assert _tick() == 0
    assert len(loaded.get("/api/decisions").json()) == 1


def test_active_bankruptcy_ends_the_case(loaded):
    _complete_package(bankruptcy={"status": "Active", "chapter": "7", "case_number": "26-1"})
    _tick()
    assert _workflow(loaded)["outcome"] == "Stopped at Intake: End Case"
    assert loaded.get("/api/decisions").json() == []


def test_sale_within_window_rejected_ends_case(loaded):
    soon = (date.today() + timedelta(days=10)).isoformat()
    _complete_package(foreclosure={"status": "Sale Scheduled", "referral_date": "2026-07-07", "sale_date": soon})
    _tick()
    [decision] = loaded.get("/api/decisions?status=pending").json()
    assert decision["gate"] == "oversight_review"
    assert loaded.post(f"/api/decisions/{decision['id']}/decide", json={"decision": "rejected"}).status_code == 422
    result = loaded.post(f"/api/decisions/{decision['id']}/decide", json={"decision": "rejected", "note": "Too close"}).json()
    assert result["stage_status"] == "End Case" and result["workflow_outcome"] == "Stopped at Intake: End Case"
