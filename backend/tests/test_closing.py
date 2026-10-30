"""Stage 5 · Final Underwriting & Closing: the V1 underwriting checks, MOD QC and sign-off
gates, then the five legacy Final Mod checks and their first-match verdicts."""

from datetime import datetime, timedelta, timezone

import pytest
import yaml
from sqlalchemy import select

from app import models
from app.core.database import SessionLocal
from app.engine import runner
from app.engine.nodes.closing import evaluate_verdict
from app.engine.playbook import HARNESS_DIR

from .conftest import LOAN

T0 = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
QC_OK = {"borrower_property_verified": True, "principal_matches_msp": True, "new_terms_match_plan": True}


@pytest.fixture()
def clock(monkeypatch):
    now = {"t": T0}
    monkeypatch.setattr(runner, "now_utc", lambda: now["t"])
    return now


@pytest.fixture()
def closing_case(loaded, clock):
    """Trial completed, every Final UW input on file and consistent with MSP."""
    with SessionLocal() as db:
        lm = db.get(models.LmStages, LOAN)
        lm.intake_status, lm.retention_eligibility_status = "Complete", "Facially Complete"
        lm.trial_uw_status, lm.trial_monitoring_status = "Ready", "Completed"
        msp = db.get(models.Msp, LOAN)
        msp.task1 = {"tasks": [{"task_id": "BKCASH", "status": "Completed"}, {"task_id": "OTHER", "status": "Open"}]}
        msp.mes1 = {"tasks": []}
        msp.lsmr = {"current_interest_rate": 4.5, "new_interest_rate": 4.0, "new_term_months": 480,
                    "new_principal_balance": 212400.0, "new_payment_amount": 1272.0}
        msp.lmt3 = {**(msp.lmt3 or {}), "x65_date": "2026-10-05", "e74_date": "2026-10-06", "j03_date": "2026-10-07",
                    "x58_date": "2026-10-08", "e68_date": "2026-10-09"}
        db.get(models.ExtractedData, LOAN).neighbourhood_document = {
            "document_date": "10/01/2026", "borrower_name": "TEST BORROWER", "property_address": msp.property_address,
            "upb": 212400.0, "prior_partial_claim_amounts": [1500.0]}
        db.commit()
    return loaded


def _run(db):
    wf = runner.start_workflow(db, LOAN)
    db.commit()
    return wf


def _pending(db):
    return db.scalar(select(models.Decision).where(models.Decision.stage_no == 5, models.Decision.status == "pending"))


def _decide(client, approved=True, **body):
    with SessionLocal() as db:
        d = _pending(db)
    r = client.post(f"/api/decisions/{d.id}/decide", json={"decision": "approved" if approved else "rejected", "note": "n", **body})
    assert r.status_code == 200, r.text
    return d


def _set_state(state):
    with SessionLocal() as db:
        msp = db.get(models.Msp, LOAN)
        msp.dlq1 = {**msp.dlq1, "property_state": state}
        db.commit()


def _through_sign_off(client, qc=QC_OK):
    with SessionLocal() as db:
        _run(db)
        assert _pending(db).gate == "underwriting_mod_qc"
    _decide(client, qc=qc, decided_by="qc1")
    with SessionLocal() as db:
        assert _pending(db).gate == "underwriting_sign_off"
    _decide(client, decided_by="lead1")


def test_clean_case_reaches_mod_qc_with_every_check_passing(closing_case):
    with SessionLocal() as db:
        _run(db)
        run = db.scalar(select(models.AgentRun).where(models.AgentRun.stage_no == 5))
        uw = run.output["stage_report"]["uw_results"]
        assert {k: v["outcome"] for k, v in uw.items()} == {
            "hold_tasks": "pass", "scra": "pass", "neighbourhood": "pass", "lsmr_terms": "pass", "lmt3_dates": "pass", "handoff": "pass"}
        assert _pending(db).team == "MOD QC"


def test_signed_off_outside_recording_states_completes_the_workflow(closing_case):
    _through_sign_off(closing_case)
    with SessionLocal() as db:
        assert runner.stage_status(db, LOAN, 5) == "Signed Off"
        qc = db.get(models.ClosingQc, LOAN)
        assert qc.qc_by == "qc1" and qc.mod_approved_by == "lead1" and qc.new_terms_match_plan is True
        wf = db.scalars(select(models.WorkflowRun).order_by(models.WorkflowRun.started_at.desc())).first()
        assert wf.status == "completed"
        fm = db.scalars(select(models.AgentRun).where(models.AgentRun.stage_no == 5)).first().output["stage_report"]["final_mod"]
        assert fm["checks"]["recording_sla"]["status"] == "not_applicable" and fm["facts"]["qc_complete"] is True


def test_pending_qc_flag_is_in_progress_then_rerun_after_qc(closing_case):
    _through_sign_off(closing_case, qc={**QC_OK, "new_terms_match_plan": None})
    with SessionLocal() as db:
        assert runner.stage_status(db, LOAN, 5) == "Sign Off & In Progress"
        assert runner.entry_node(db, LOAN, 5) == "fm_trial_outcome"
    r = closing_case.put(f"/api/cases/5/{LOAN}/closing-record", json={"new_terms_match_plan": True, "updated_by": "qc2"})
    assert r.status_code == 200, r.text
    assert closing_case.post("/api/processes/5/run", json={"loan_id": LOAN}).json()["queued"] == 1
    with SessionLocal() as db:
        assert runner.stage_status(db, LOAN, 5) == "Signed Off"
        runs = list(db.scalars(select(models.AgentRun).where(models.AgentRun.stage_no == 5)))
        assert sorted(r.input["start_at"] for r in runs) == ["fm_trial_outcome", "load_case"]
        rerun = next(r for r in runs if r.input["start_at"] == "fm_trial_outcome")
        assert rerun.output["status"] == "Signed Off"
        assert not any(t["node"].startswith("uw_") for t in rerun.trace)  # underwriting is not repeated


def test_recording_state_sla(closing_case, clock):
    _set_state("OH")
    _through_sign_off(closing_case)
    with SessionLocal() as db:
        # Inside the 14-day SLA, not yet recorded: legacy rule → Signed Off.
        assert runner.stage_status(db, LOAN, 5) == "Signed Off"


def test_sla_breach_goes_to_human_review_and_recording_records(closing_case, clock):
    _set_state("NY")
    _through_sign_off(closing_case, qc={**QC_OK, "principal_matches_msp": None})
    clock["t"] = T0 + timedelta(days=20)
    with SessionLocal() as db:
        _run(db)
        assert runner.stage_status(db, LOAN, 5) == "In Human Review"
        assert "6 day(s) over SLA" in _pending(db).reason
    _decide(closing_case)  # breach acknowledged → still in progress
    with SessionLocal() as db:
        assert runner.stage_status(db, LOAN, 5) == "Sign Off & In Progress"
    r = closing_case.put(f"/api/cases/5/{LOAN}/closing-record",
                         json={"principal_matches_msp": True, "recorded_date": (T0 + timedelta(days=19)).date().isoformat()})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        _run(db)
        assert runner.stage_status(db, LOAN, 5) == "Recording"


def test_open_hold_task_escalates_to_team_lead(closing_case):
    with SessionLocal() as db:
        msp = db.get(models.Msp, LOAN)
        msp.task1 = {"tasks": [{"task_id": "FCCOST", "status": "Open"}]}
        db.commit()
        _run(db)
        d = _pending(db)
        assert d.gate == "underwriting_team_lead" and d.team == "Team Lead" and "FCCOST" in d.reason
    _decide(closing_case)
    with SessionLocal() as db:
        assert _pending(db).gate == "underwriting_mod_qc"


@pytest.mark.parametrize("change, key, outcome", [
    (lambda m, d: setattr(m, "lsmr", {**m.lsmr, "current_interest_rate": 5.5}), "scra", "review"),
    (lambda m, d: setattr(d, "neighbourhood_document", None), "neighbourhood", "hold"),
    (lambda m, d: setattr(d, "neighbourhood_document", {**d.neighbourhood_document, "document_date": "01/01/2025"}), "neighbourhood", "hold"),
    (lambda m, d: setattr(d, "neighbourhood_document", {**d.neighbourhood_document, "upb": 100.0}), "neighbourhood", "review"),
    (lambda m, d: setattr(m, "lsmr", {**m.lsmr, "new_term_months": None}), "lsmr_terms", "review"),
    (lambda m, d: setattr(m, "lmt3", {**m.lmt3, "e68_date": "2026-10-10"}), "lmt3_dates", "review"),  # Saturday
    (lambda m, d: setattr(m, "lmt3", {**m.lmt3, "j03_date": "2026-10-06"}), "lmt3_dates", "review"),  # not strictly after
    (lambda m, d: (setattr(m, "task1", None), setattr(m, "mes1", None)), "hold_tasks", "review"),
])
def test_each_underwriting_check(closing_case, change, key, outcome):
    with SessionLocal() as db:
        change(db.get(models.Msp, LOAN), db.get(models.ExtractedData, LOAN))
        db.commit()
        _run(db)
        run = db.scalar(select(models.AgentRun).where(models.AgentRun.stage_no == 5))
        assert run.output["stage_report"]["uw_results"][key]["outcome"] == outcome
        assert _pending(db).gate == "underwriting_team_lead"


def test_verdict_rules_first_match():
    rules = yaml.safe_load((HARNESS_DIR / "closing" / "rules.yaml").read_text(encoding="utf-8"))["final_mod_closing"]
    def checks(trial, recording, *qc):
        out = {"trial_outcome": {"status": trial, "tags": []}, "recording_sla": {"status": recording, "tags": []}}
        out.update({f"q{i}": {"status": s, "tags": ["qc"]} for i, s in enumerate(qc)})
        return out
    assert evaluate_verdict(checks("flagged", "flagged", "pass"), rules)[0] == "denied"
    assert evaluate_verdict(checks("pass", "flagged", "pass"), rules)[0] == "human_review"
    assert evaluate_verdict(checks("pending", "pass", "pass", "skipped"), rules)[0] == "sign_off_in_progress"
    assert evaluate_verdict(checks("pass", "pass", "pass", "pass"), rules)[0] == "recording"
    assert evaluate_verdict(checks("pass", "pending", "pass", "pass"), rules)[0] == "signed_off"


def test_closing_record_validation(closing_case):
    assert closing_case.put(f"/api/cases/5/{LOAN}/closing-record", json={"recorded_date": "2026-10-30"}).status_code == 409  # not signed off
    assert closing_case.put(f"/api/cases/5/{LOAN}/closing-record", json={}).status_code == 422
    case = closing_case.get(f"/api/cases/5/{LOAN}").json()
    assert case["data"]["lsmr"]["new_term_months"] == 480 and case["data"]["tasks"]["TASK1"]
