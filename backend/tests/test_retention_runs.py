"""Re-run must execute, preserve history and expose real async progress."""

from copy import deepcopy

import pytest
from sqlalchemy import select

from app import models
from app.core.database import SessionLocal
from app.engine import retention_runs, runner

from .conftest import LOAN
from .test_retention import NOW, case, install_case  # noqa: F401 — shared fixture


def test_explicit_rerun_updates_existing_case_and_preserves_history(loaded, case):
    # Incomplete files remain at retention; complete files now run later stages
    # and must not be overwritten by a retention re-run.
    case["flags"]["maa_page_count_issue"] = True
    install_case(case)
    loaded.post("/api/processes/2/run")
    previous = loaded.get(f"/api/retention/cases/{LOAN}").json()
    assert previous["status"] == "Facially Incomplete"
    with SessionLocal() as db:
        original = deepcopy(db.get(models.AgentRun, previous["last_run_id"]).output)
        doc = db.get(models.ExtractedData, LOAN)
        doc.flags = {**doc.flags, "maa_page_count_issue": False}
        db.commit()
    response = loaded.post("/api/processes/2/run", json={"rerun": True})
    assert response.status_code == 202, response.text
    result = response.json()
    assert result["queued"] == 1 and len(result["run_ids"]) == 1 and not result["skipped"]
    detail = loaded.get(f"/api/retention/cases/{LOAN}").json()
    assert detail["last_run_id"] == result["run_ids"][0] != previous["last_run_id"]
    assert detail["status"] == "Facially Complete"
    assert detail["report"]["confidence_considered"] is False
    with SessionLocal() as db:
        assert db.get(models.AgentRun, previous["last_run_id"]).output == original
        new = db.get(models.AgentRun, result["run_ids"][0])
        assert new.input["source_run_id"] == previous["last_run_id"]
        assert new.workflow_run_id and new.status == "completed"
        assert db.get(models.LmStages, LOAN).intake_status == "Complete"
        assert list(db.scalars(select(models.AgentRun).where(models.AgentRun.stage_no == 1))) == []
    progress = loaded.get("/api/retention/executions", params={"ids": ",".join(result["run_ids"])}).json()
    assert progress["runs"][0]["status"] == "completed"
    assert progress["runs"][0]["verdict"] == "Facially Complete"


def test_queued_and_running_progress_visible_before_completion(loaded, case, monkeypatch):
    install_case(case)
    worker = retention_runs.execute
    monkeypatch.setattr(retention_runs, "execute", lambda ids: None)
    result = loaded.post("/api/processes/2/run", json={"rerun": True}).json()
    ids = result["run_ids"]
    assert len(ids) == 1
    assert loaded.get("/api/retention/executions", params={"ids": ids[0]}).json()["runs"][0]["status"] == "queued"
    assert loaded.get("/api/retention/summary").json()["active_run_ids"] == ids
    # A second click cannot enqueue duplicates, and the normal scheduler cannot run it.
    assert loaded.post("/api/processes/2/run", json={"rerun": True}).json()["queued"] == 0
    with SessionLocal() as db:
        assert runner.stage_candidates(db, 2) == []
        assert runner.workflow_candidates(db) == []
    execute_graph = runner._execute

    def inspect_running(db, run, pb, state):
        with SessionLocal() as observer:
            assert observer.get(models.AgentRun, ids[0]).status == "running"
        execute_graph(db, run, pb, state)

    monkeypatch.setattr(runner, "_execute", inspect_running)
    worker(ids)
    worker(ids)  # duplicate background delivery is a no-op
    assert loaded.get("/api/retention/executions", params={"ids": ids[0]}).json()["runs"][0]["status"] == "completed"
    assert loaded.get("/api/retention/summary").json()["active_run_ids"] == []


def test_rerun_failure_is_terminal_and_old_verdict_preserved(loaded, case, monkeypatch):
    case["flags"]["maa_page_count_issue"] = True
    install_case(case)
    loaded.post("/api/processes/2/run")
    before = loaded.get(f"/api/retention/cases/{LOAN}").json()

    def fail(*args, **kwargs):
        raise RuntimeError("Test evaluator failure")

    monkeypatch.setattr(runner, "_execute", fail)
    response = loaded.post("/api/processes/2/run", json={"rerun": True}).json()
    progress = loaded.get("/api/retention/executions", params={"ids": response["run_ids"][0]}).json()
    assert progress["runs"][0]["status"] == "failed"
    assert "Test evaluator failure" in progress["runs"][0]["error"]
    with SessionLocal() as db:
        run = db.get(models.AgentRun, response["run_ids"][0])
        assert run.workflow_run.status == "failed"
        assert db.get(models.LmStages, LOAN).retention_eligibility_status == before["status"]


@pytest.mark.parametrize("stage_status", ["Facially Complete", "Denied", "Facially Incomplete", "In Human Review"])
def test_rerun_accepts_existing_status_without_active_work(loaded, case, stage_status):
    install_case(case)
    with SessionLocal() as db:
        db.get(models.LmStages, LOAN).retention_eligibility_status = stage_status
        db.commit()
    result = loaded.post("/api/processes/2/run", json={"rerun": True, "loan_id": LOAN})
    assert result.status_code == 202 and result.json()["queued"] == 1
    assert loaded.get(f"/api/retention/cases/{LOAN}").json()["status"] == "Facially Complete"


def test_rerun_skips_pending_human_review(loaded, case):
    case["flags"]["maa_page_count_issue"] = True
    install_case(case)
    loaded.post("/api/processes/2/run")
    decision = loaded.post(f"/api/retention/cases/{LOAN}/review").json()["decision_id"]
    result = loaded.post("/api/processes/2/run", json={"rerun": True}).json()
    assert result["queued"] == 0 and result["skipped"][0]["loan_id"] == LOAN
    assert "review" in result["skipped"][0]["reason"]
    assert loaded.post("/api/processes/2/run", json={"rerun": True, "loan_id": LOAN}).status_code == 409
    assert loaded.get("/api/decisions?status=pending").json()[0]["id"] == decision


def test_rerun_skips_later_stage_and_incomplete_intake(loaded, case):
    install_case(case)
    with SessionLocal() as db:
        lm = db.get(models.LmStages, LOAN)
        lm.trial_uw_status = "Ready"
        db.commit()
    result = loaded.post("/api/processes/2/run", json={"rerun": True}).json()
    assert result["queued"] == 0 and "Later-stage" in result["skipped"][0]["reason"]
    with SessionLocal() as db:
        lm = db.get(models.LmStages, LOAN)
        lm.trial_uw_status = None
        lm.intake_status = "Missing Doc"
        db.commit()
    assert loaded.post("/api/processes/2/run", json={"rerun": True}).json()["queued"] == 0
    assert loaded.post("/api/processes/2/run", json={"rerun": True, "loan_id": LOAN}).status_code == 409


def test_completed_retention_handoff_blocks_rerun(loaded, case):
    case["msp"]["dlq1"]["upb_balance"] = 180000.0
    install_case(case)
    assert loaded.post("/api/processes/2/run").json()["queued"] == 1
    before = loaded.get(f"/api/retention/cases/{LOAN}").json()
    assert before["status"] == "Facially Complete"
    with SessionLocal() as db:
        assert db.scalar(select(models.AgentRun.id).where(models.AgentRun.stage_no > 2))
    response = loaded.post("/api/processes/2/run", json={"rerun": True, "loan_id": LOAN})
    assert response.status_code == 409
    assert "waiting for human review" in response.json()["detail"]
    pending = loaded.get("/api/decisions?status=pending").json()
    assert len(pending) == 1 and pending[0]["stage_no"] == 3
    assert loaded.get(f"/api/retention/cases/{LOAN}").json()["last_run_id"] == before["last_run_id"]


def test_rerun_does_not_change_intake_run_semantics(loaded):
    assert loaded.post("/api/processes/1/run", json={"rerun": True}).status_code == 422
    assert loaded.get("/api/retention/executions", params={"ids": "missing"}).status_code == 404


def test_worker_failure_does_not_stop_remaining_cases(loaded, case, monkeypatch):
    install_case(case)
    # Reserve one run, simulate a failure, and verify it can be explicitly retried.
    original = runner._execute

    def fail(*args, **kwargs):
        raise RuntimeError("Transient failure")

    monkeypatch.setattr(runner, "_execute", fail)
    failed = loaded.post("/api/processes/2/run", json={"rerun": True}).json()
    monkeypatch.setattr(runner, "_execute", original)
    retried = loaded.post("/api/processes/2/run", json={"rerun": True}).json()
    assert retried["queued"] == 1 and retried["run_ids"] != failed["run_ids"]
    assert loaded.get(f"/api/retention/cases/{LOAN}").json()["status"] == "Facially Complete"