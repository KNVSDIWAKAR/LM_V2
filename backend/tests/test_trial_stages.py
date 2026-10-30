"""Stage 3 · Trial UW and Stage 4 · Trial Monitoring, from the database rows they read and write."""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app import models
from app.core.database import SessionLocal
from app.engine import runner
from app.engine.nodes.trial_monitoring import match_installments
from app.engine.nodes.trial_uw import amortized_payment, first_due_date

from .conftest import LOAN

T0 = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)

BANK = {"institution_name": "Bank", "account_holder_name": "Test Borrower", "statement_start_date": "01/01/2026",
        "statement_end_date": "01/31/2026", "all_deposits": [], "recurring_deposits_over_250": []}


@pytest.fixture()
def clock(monkeypatch):
    """Move the engine's clock; every run and decision reads runner.now_utc()."""
    now = {"t": T0}
    monkeypatch.setattr(runner, "now_utc", lambda: now["t"])
    return now


@pytest.fixture()
def uw_case(loaded, clock):
    """The conftest loan handed on to Trial UW: Facially Complete, full package on file."""
    with SessionLocal() as db:
        lm = db.get(models.LmStages, LOAN)
        lm.intake_status, lm.retention_eligibility_status = "Complete", "Facially Complete"
        doc = db.get(models.ExtractedData, LOAN)
        doc.bank_statement = BANK
        doc.credit_report = {**doc.credit_report, "monthly_mortgage_payment": 2100.0}
        db.commit()
    return loaded


def _run(db, loan_id=LOAN):
    wf = runner.start_workflow(db, loan_id)
    db.commit()
    return wf


def _pending(db, stage_no):
    return db.scalar(select(models.Decision).where(models.Decision.stage_no == stage_no, models.Decision.status == "pending"))


# --------------------------------------------------------------------------- #
# Formulas
# --------------------------------------------------------------------------- #


def test_amortization_and_first_due_date():
    assert amortized_payment(212400, 6.875, 480) == 1300.68
    assert amortized_payment(212400, 6.875, 360) == 1395.32
    assert amortized_payment(1200, 0, 12) == 100.0
    assert first_due_date(date(2026, 10, 30), 15) == date(2026, 12, 1)  # Nov 1 is only 2 days away
    assert first_due_date(date(2026, 10, 10), 15) == date(2026, 11, 1)


def test_match_installments_classifies_each_payment():
    inst = [{"installment_no": n, "due_date": d, "grace_end_date": g, "expected_amount": 1000.0}
            for n, d, g in ((1, "2026-12-01", "2026-12-16"), (2, "2027-01-01", "2027-01-16"), (3, "2027-02-01", "2027-02-16"))]
    pay = lambda *rows: [{"payment_date": d, "amount": a} for d, a in rows]  # noqa: E731
    statuses = lambda rows, today: [m["status"] for m in match_installments(inst, rows, date.fromisoformat(today), 1.0)]  # noqa: E731

    assert statuses(pay(("2026-12-01", 1000), ("2027-01-10", 1000), ("2027-02-16", 999.5)), "2027-03-01") == ["paid", "paid", "paid"]
    assert statuses(pay(("2026-12-20", 1000)), "2026-12-21") == ["late", "pending", "pending"]
    assert statuses(pay(("2026-12-05", 600)), "2026-12-17") == ["partial", "pending", "pending"]
    assert statuses([], "2026-12-17") == ["missed", "pending", "pending"]
    # A double payment carries forward to the next installment.
    assert statuses(pay(("2026-12-01", 2000)), "2027-01-20") == ["paid", "paid", "pending"]
    in_grace = match_installments(inst, [], date(2026, 12, 5), 1.0)[0]
    assert in_grace["status"] == "pending" and in_grace["past_due"]


# --------------------------------------------------------------------------- #
# Stage 3
# --------------------------------------------------------------------------- #


@pytest.fixture()
def affordable(uw_case):
    """Lower the balance so both plan options fit the 40% housing ratio on $4,200."""
    with SessionLocal() as db:
        msp = db.get(models.Msp, LOAN)
        msp.dlq1 = {**msp.dlq1, "upb_balance": 180000.0}
        db.commit()
    return uw_case


def test_trial_uw_proposes_plans_in_db_and_waits_for_underwriter(affordable):
    uw_case = affordable
    with SessionLocal() as db:
        _run(db)
        assert runner.stage_status(db, LOAN, 3) == "In Human Review"
        plans = list(db.scalars(select(models.TrialPlan).where(models.TrialPlan.loan_id == LOAN).order_by(models.TrialPlan.option_no)))
        decision = _pending(db, 3)
    assert decision.gate == "underwriter_review" and decision.team == "Human Underwriter"
    assert [p.status for p in plans] == ["proposed", "proposed"]
    for p in plans:
        assert p.trial_payment == round(p.principal_interest + p.escrow_payment, 2)
        assert p.housing_ratio <= 40
        assert p.first_due_date == date(2026, 12, 1) and len(p.installments) == p.trial_duration_months == 3
        assert p.calculation["upb_balance"] == p.upb_balance and p.conditions and p.reason_codes

    body = uw_case.get(f"/api/decisions/{decision.id}").json()
    assert [p["plan_id"] for p in body["trial_plans"]] == [p.id for p in plans]
    case = uw_case.get(f"/api/cases/3/{LOAN}").json()
    assert case["status"] == "In Human Review" and case["open_decision_id"] == decision.id
    assert case["data"]["plans"][0]["installments"][0]["due_date"] == "2026-12-01"
    assert any(f["check"] == "Retention report" for f in case["latest_run"]["findings"])


def test_two_options_need_an_explicit_choice(affordable):
    with SessionLocal() as db:
        _run(db)
        decision = _pending(db, 3)
        plans = list(db.scalars(select(models.TrialPlan).where(models.TrialPlan.loan_id == LOAN)))
    assert len(plans) == 2
    r = affordable.post(f"/api/decisions/{decision.id}/decide", json={"decision": "approved"})
    assert r.status_code == 422
    r = affordable.post(f"/api/decisions/{decision.id}/decide", json={"decision": "approved", "selected_plan_id": "TP-unknown"})
    assert r.status_code == 422
    with SessionLocal() as db:
        assert db.get(models.Decision, decision.id).status == "pending"


def test_approve_plan_ready_then_monitoring_starts(affordable):
    with SessionLocal() as db:
        _run(db)
        decision = _pending(db, 3)
        chosen = db.scalar(select(models.TrialPlan).where(models.TrialPlan.loan_id == LOAN, models.TrialPlan.option_no == 2))
    r = affordable.post(f"/api/decisions/{decision.id}/decide",
                        json={"decision": "approved", "decided_by": "uw1", "selected_plan_id": chosen.id})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        statuses = {p.option_no: p.status for p in db.scalars(select(models.TrialPlan).where(models.TrialPlan.loan_id == LOAN))}
        assert statuses == {1: "not_selected", 2: "approved"}
        assert runner.stage_status(db, LOAN, 3) == "Ready"
        # Stage 4 ran straight away: nothing due yet, no payment history needed.
        assert runner.stage_status(db, LOAN, 4) == "Within Plan"
        notes = db.get(models.Msp, LOAN).nots["notes"]
        assert notes[-1].startswith("LMT TRIAL 2026-10-30: plan " + chosen.id)
    # The saved "review" plan findings now show the decision.
    body = affordable.get(f"/api/decisions/{decision.id}").json()
    plan_rows = {f["plan_id"]: f for f in body["findings"] if f.get("plan_id")}
    assert plan_rows[chosen.id]["result"] == "approved" and "Approved by uw1" in plan_rows[chosen.id]["detail"]
    assert {f["result"] for pid, f in plan_rows.items() if pid != chosen.id} == {"not_selected"}
    case = affordable.get(f"/api/cases/3/{LOAN}").json()
    assert not any(f["result"] == "review" and f.get("plan_id") for f in case["latest_run"]["findings"])


def test_reject_declines_plans_and_escalates(affordable):
    with SessionLocal() as db:
        _run(db)
        decision = _pending(db, 3)
    assert affordable.post(f"/api/decisions/{decision.id}/decide", json={"decision": "rejected", "note": "income unverified"}).status_code == 200
    with SessionLocal() as db:
        assert runner.stage_status(db, LOAN, 3) == "Declined"
        assert runner.stage_status(db, LOAN, 4) is None
        assert {p.status for p in db.scalars(select(models.TrialPlan))} == {"declined"}
        run = db.scalar(select(models.AgentRun).where(models.AgentRun.stage_no == 3))
        assert run.output["team"] == "Onshore"


def test_missing_bank_statement_holds_without_plans(uw_case):
    with SessionLocal() as db:
        db.get(models.ExtractedData, LOAN).bank_statement = None
        db.commit()
        _run(db)
        assert runner.stage_status(db, LOAN, 3) == "Hold Docs Pending"
        assert _pending(db, 3) is None and db.scalar(select(models.TrialPlan.id)) is None


def test_unaffordable_balance_declines(uw_case):
    """$212,400 at 6.875% + $385 escrow is over 40% of $4,200 on both options."""
    with SessionLocal() as db:
        _run(db)
        assert runner.stage_status(db, LOAN, 3) == "Declined"
        assert "housing ratio" in db.get(models.LmStages, LOAN).trial_uw_remark


def test_ineligible_investor_declines(uw_case):
    with SessionLocal() as db:
        msp = db.get(models.Msp, LOAN)
        msp.dlq1 = {**msp.dlq1, "investor_type": "Private"}
        db.commit()
        _run(db)
        assert runner.stage_status(db, LOAN, 3) == "Declined"


def test_trial_uw_requires_retention_forwarding(loaded, clock):
    with SessionLocal() as db:
        db.get(models.LmStages, LOAN).intake_status = "Complete"
        db.commit()
        assert runner.stage_candidates(db, 3) == []


# --------------------------------------------------------------------------- #
# Stage 4
# --------------------------------------------------------------------------- #


@pytest.fixture()
def monitoring(affordable, clock):
    """An approved plan (option 1) with Stage 4 already run once (Within Plan)."""
    with SessionLocal() as db:
        _run(db)
        decision = _pending(db, 3)
        plan = db.scalar(select(models.TrialPlan).where(models.TrialPlan.option_no == 1))
    affordable.post(f"/api/decisions/{decision.id}/decide", json={"decision": "approved", "selected_plan_id": plan.id})
    return plan


def _pay(rows):
    with SessionLocal() as db:
        msp = db.get(models.Msp, LOAN)
        msp.dlq1 = {**msp.dlq1, "payment_history": [{"payment_date": d, "amount": a} for d, a in rows]}
        db.commit()


def test_all_payments_on_time_completes_and_hands_on(monitoring, clock):
    amt = monitoring.trial_payment
    _pay([("2026-12-01", amt), ("2027-01-05", amt), ("2027-02-10", amt), ("2026-09-01", 5000)])  # old payment ignored
    clock["t"] = datetime(2027, 2, 20, tzinfo=timezone.utc)
    with SessionLocal() as db:
        assert LOAN in runner.stage_candidates(db, 4)  # Within Plan re-runs each cycle
        _run(db)
        assert runner.stage_status(db, LOAN, 4) == "Completed"
        rows = db.scalars(select(models.TrialInstallment).where(models.TrialInstallment.plan_id == monitoring.id))
        assert [(i.status, i.received_amount) for i in rows] == [("paid", amt)] * 3
        # Stage 5 started; no TASK1/MES1 loaded, so the Team Lead is asked.
        assert runner.stage_status(db, LOAN, 5) == "In Human Review"
        assert _pending(db, 5).gate == "underwriting_team_lead"


def test_missed_payment_defaults(monitoring, clock):
    _pay([("2026-12-01", monitoring.trial_payment)])
    clock["t"] = datetime(2027, 1, 20, tzinfo=timezone.utc)
    with SessionLocal() as db:
        _run(db)
        assert runner.stage_status(db, LOAN, 4) == "Defaulted"
        run = db.scalars(select(models.AgentRun).where(models.AgentRun.stage_no == 4).order_by(models.AgentRun.started_at.desc())).first()
        assert run.output["team"] == "Onshore"


def test_past_due_in_grace_is_delayed(monitoring, clock):
    _pay([])
    clock["t"] = datetime(2026, 12, 8, tzinfo=timezone.utc)
    with SessionLocal() as db:
        _run(db)
        assert runner.stage_status(db, LOAN, 4) == "Delayed Payment"


def test_no_payment_history_after_grace_needs_review(monitoring, clock):
    clock["t"] = datetime(2026, 12, 20, tzinfo=timezone.utc)
    with SessionLocal() as db:
        _run(db)
        assert runner.stage_status(db, LOAN, 4) == "In Human Review"
        assert "payment_history" in _pending(db, 4).reason


def test_late_but_complete_goes_to_review(monitoring, clock):
    amt = monitoring.trial_payment
    _pay([("2026-12-20", amt), ("2027-01-05", amt), ("2027-02-10", amt)])
    clock["t"] = datetime(2027, 2, 20, tzinfo=timezone.utc)
    with SessionLocal() as db:
        _run(db)
        assert runner.stage_status(db, LOAN, 4) == "In Human Review"


def test_monitoring_case_endpoint(affordable, monitoring):
    case = affordable.get(f"/api/cases/4/{LOAN}").json()
    assert case["status"] == "Within Plan"
    assert case["data"]["approved_plan"]["plan_id"] == monitoring.id
    assert case["data"]["payment_history_available"] is False
    assert case["data"]["lmt_notes"] and case["latest_run"]["stage_report"]["installments"]


def test_new_plan_tables_have_check_constraints(loaded):
    with SessionLocal() as db:
        db.add(models.TrialPlan(id="x", loan_id=LOAN, option_no=1, plan_type="t", plan_name="t", status="bogus", trial_payment=1,
                                principal_interest=1, escrow_payment=0, interest_rate_pct=1, amortization_months=1,
                                trial_duration_months=1, grace_period_days=1, first_due_date=date.today(), upb_balance=1,
                                gross_monthly_income=1, housing_ratio=1, created_at=T0 - timedelta(days=1)))
        with pytest.raises(Exception):
            db.commit()


def test_review_from_older_playbook_is_409_then_retired_to_waiting(affordable):
    """A pending item whose gate the playbook no longer has (old Stage 3 `review`) must not 500."""
    with SessionLocal() as db:
        _run(db)
        d = _pending(db, 3)
        d.gate = "review"  # what the pre-rework Stage 3 playbook called its gate
        db.commit()
        decision_id = d.id
    listed = affordable.get(f"/api/decisions/{decision_id}").json()
    assert listed["stale"] is True
    r = affordable.post(f"/api/decisions/{decision_id}/decide", json={"decision": "approved"})
    assert r.status_code == 409 and "older" in r.json()["detail"]
    r = affordable.post(f"/api/decisions/{decision_id}/retire")
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    with SessionLocal() as db:
        assert runner.stage_status(db, LOAN, 3) is None
        assert LOAN in runner.stage_candidates(db, 3)
        run = db.get(models.AgentRun, db.get(models.Decision, decision_id).agent_run_id)
        assert run.status == "cancelled" and run.workflow_run.status == "cancelled"
    assert affordable.post(f"/api/decisions/{decision_id}/retire").status_code == 409
    # Run again: a fresh, current-playbook review.
    assert affordable.post("/api/processes/3/run", json={"loan_id": LOAN}).json()["queued"] == 1
    with SessionLocal() as db:
        assert _pending(db, 3).gate == "underwriter_review"


# --------------------------------------------------------------------------- #
# MOCK servicer (POC): data/mock_servicing.json drives Stage 4 straight to Closing
# --------------------------------------------------------------------------- #


def _mock(pattern):
    with SessionLocal() as db:
        db.merge(models.MockServicing(loan_id=LOAN, trial_payments=pattern, scenario="test"))
        db.commit()


def _approve_first_plan(client):
    with SessionLocal() as db:
        _run(db)
        decision = _pending(db, 3)
        plan = db.scalar(select(models.TrialPlan).where(models.TrialPlan.option_no == 1))
    assert client.post(f"/api/decisions/{decision.id}/decide", json={"decision": "approved", "selected_plan_id": plan.id}).status_code == 200
    return plan


def test_mock_on_time_trial_completes_and_reaches_closing(affordable):
    _mock(["on_time", "on_time", "on_time"])
    plan = _approve_first_plan(affordable)
    with SessionLocal() as db:
        assert runner.stage_status(db, LOAN, 4) == "Completed"
        assert runner.stage_status(db, LOAN, 5) == "In Human Review"  # Final UW ran; no TASK1 here → Team Lead
        history = db.get(models.Msp, LOAN).dlq1["payment_history"]
        assert [p["reference"] for p in history] == [f"MOCK-{plan.id}-{n}" for n in (1, 2, 3)]
        run = db.scalar(select(models.AgentRun).where(models.AgentRun.stage_no == 4))
        assert run.output["stage_report"]["mock_servicer"]["as_of"] == "2027-02-17"
        assert any(f["check"] == "MOCK servicer" for f in run.output["findings"])


@pytest.mark.parametrize("pattern, status", [
    (["on_time", "missed", "on_time"], "Defaulted"),
    (["partial"], "Defaulted"),
    (["on_time", "late", "on_time"], "In Human Review"),
    (["on_time", "not_yet", "not_yet"], "Within Plan"),
])
def test_mock_payment_patterns(affordable, pattern, status):
    _mock(pattern)
    _approve_first_plan(affordable)
    with SessionLocal() as db:
        assert runner.stage_status(db, LOAN, 4) == status


def test_mock_rerun_replaces_its_own_payments(affordable):
    _mock(["on_time", "not_yet", "not_yet"])
    plan = _approve_first_plan(affordable)
    with SessionLocal() as db:
        _run(db)  # Within Plan re-runs: a second monitoring cycle
        refs = [p["reference"] for p in db.get(models.Msp, LOAN).dlq1["payment_history"]]
    assert refs == [f"MOCK-{plan.id}-1"]


def test_mock_disabled_uses_real_dlq1_only(affordable, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "mock_servicer_enabled", False)
    _mock(["on_time", "on_time", "on_time"])
    _approve_first_plan(affordable)
    with SessionLocal() as db:
        assert runner.stage_status(db, LOAN, 4) == "Within Plan"
        assert db.get(models.Msp, LOAN).dlq1.get("payment_history") is None


def test_mock_file_imports_screens_and_pattern(loaded, tmp_path):
    import json

    from app.core.config import BACKEND_DIR
    from scripts.import_data import import_mock_servicing

    data = json.loads((BACKEND_DIR / "data" / "mock_servicing.json").read_text(encoding="utf-8"))
    data["loans"] = [l for l in data["loans"] if l["loan_id"] == LOAN]
    data["meta"]["total_loans"] = 1
    (tmp_path / "mock.json").write_text(json.dumps(data), encoding="utf-8")
    with SessionLocal() as db:
        db.get(models.Msp, LOAN).lmt3 = {"review_start_date": "2026-03-21"}
        db.commit()
        assert import_mock_servicing(db, tmp_path / "mock.json") == 1
        db.commit()
        msp = db.get(models.Msp, LOAN)
        assert msp.task1["tasks"] and msp.lsmr["new_term_months"] == 480 and msp.lmt3["e68_date"] == "2026-10-23"
        assert msp.lmt3["review_start_date"] == "2026-03-21"  # real LMT3 keys kept
        assert db.get(models.ExtractedData, LOAN).neighbourhood_document["upb"] == msp.dlq1["upb_balance"]
        assert db.get(models.MockServicing, LOAN).trial_payments == ["on_time"] * 3
