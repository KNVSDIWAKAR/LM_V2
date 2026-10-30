"""ART decision-tree regression checklist, using isolated SQLite and fixed evaluation dates."""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app import models
from app.core.database import SessionLocal
from app.engine import runner
from app.engine.playbook import Deps, get_playbook, load_playbook
from app.engine.registry import NODES

from .conftest import EXTRACTED, LOAN, MSP

NOW = datetime(2026, 10, 23, tzinfo=timezone.utc)


@pytest.fixture
def case(monkeypatch):
    monkeypatch.setattr(runner, "now_utc", lambda: NOW)
    loan = deepcopy(MSP["loans"][0])
    docs = deepcopy(EXTRACTED["loans"][0]["extracted_data"])
    first = docs["PAYSTUBS"][0]
    docs["PAYSTUBS"] = [first, {**first, "pay_date": "02/17/2026", "pay_period_start": "02/01/2026", "pay_period_end": "02/15/2026"}]
    docs["Application_Form"].update(desired_workflow="Keep the property", occupancy_status="Owner occupied", hardship_reason="Reduction in income", hoa_indicated=False)
    docs["BANK_STATEMENT"] = {"account_holder_name": "Test Borrower", "statement_end_date": "03/20/2026", "all_deposits": [], "recurring_deposits_over_250": []}
    docs["CREDIT_REPORT"].update(report_date="03/20/2026", total_accounts=3, total_balance=1000)
    docs["flags"] = {"maa_page_count_issue": False, "only_one_paystub": False}
    sd = loan.pop("servicing_data")
    loan.update({key.lower(): value for key, value in sd.items()})
    loan.update(lmt1={"loan_type_status": ""}, lmt3={"l92_date": "2026-03-21", "review_start_date": "2026-03-21", "review_date_minus_90": "2025-12-21", "review_date_minus_10": "2026-03-11"},
                haz1={"policy_current": True, "policy_expiry_date": "2027-01-01"}, foreclosure={"sale_date": "2030-01-01"})
    documents = dict(zip(models.DOCUMENT_TYPES, [docs["Application_Form"], docs["PAYSTUBS"], docs["BANK_STATEMENT"], docs["CREDIT_REPORT"], docs["LETTER_OF_EXPLANATION"]]))
    return {"msp": loan, "documents": documents, "flags": docs["flags"]}


def evaluate(case, rules=None):
    pb = get_playbook(2)
    msp = SimpleNamespace(**case["msp"])
    extracted = SimpleNamespace(**case["documents"], flags=case["flags"])
    msp.loan_id = LOAN
    db = SimpleNamespace(get=lambda model, key: msp if model is models.Msp else extracted)
    return pb.graph.invoke({"loan_id": LOAN, "stage_no": 2, "trace": []}, config={
        "configurable": {"deps": Deps(db=db, rules=rules or pb.rules, now=NOW)}, "recursion_limit": 10000})


def answers(final, qid):
    return [a for a in final["context"]["report"]["answers"] if a["question_id"] == qid]


def stips(final, qid):
    return [s for s in final["context"]["report"]["stip_list"] if s["question_id"] == qid]


def test_clean_tree_and_report(case):
    final = evaluate(case)
    assert final["result"]["status"] == "Facially Complete"
    assert final["result"]["advance"] is True
    report = final["context"]["report"]
    assert report["stip_count"] == 0 and not report["dm712_required"]
    assert not answers(final, "Q4") and not answers(final, "Q8a")
    assert answers(final, "QX")[0]["result"] == "pass"
    assert answers(final, "Q35")[0]["not_applicable"]
    assert not report["low_confidence_flags"]
    applicable = [a for a in report["answers"] if a["answer"] is not None and not a.get("not_applicable")]
    assert report["overall_confidence"] == round(sum(a["confidence"] for a in applicable) / len(applicable), 2)
    assert report["summary"]["total_questions"] == len(report["answers"])
    assert len(final["trace"]) > 25  # default LangGraph recursion limit is insufficient


@pytest.mark.parametrize("code", ["MOD", "PC", "Partial Claim", "CMBO", "OTHER"])
def test_approved_exit(case, code):
    case["msp"]["lmt1"]["loan_type_status"] = code
    final = evaluate(case)
    assert final["result"]["node"] == "approved_exit"
    assert final["result"]["status"] == "Denied" and not final["result"]["advance"]
    assert not final["context"]["report"]["stip_list"]
    assert [a["question_id"] for a in final["context"]["report"]["answers"]] == ["Q1", "Q2"]


def test_liquidation_exit(case):
    case["documents"]["application_form"]["desired_workflow"] = "Liquidation"
    final = evaluate(case)
    assert final["result"]["node"] == "liquidation_exit"
    assert len(final["context"]["report"]["answers"]) == 1
    assert not final["context"]["report"]["stip_list"]


@pytest.mark.parametrize("investor,months,exempt", [("FNMA", 10, True), ("FNMA", 9, False), ("GSE", 10, False), ("FHLMC", 10, False)])
def test_fnma_exemption_not_assumed_from_gse(case, investor, months, exempt):
    case["msp"]["dlq1"].update(investor_type=investor, months_delinquent=months)
    final = evaluate(case)
    assert (final["result"]["node"] == "form_exempt_exit") is exempt
    assert bool(answers(final, "Q4b")) is not exempt


def test_va_only_three_questions(case):
    case["msp"]["dlq1"]["investor_type"] = "VA"
    case["documents"]["application_form"] = {"desired_workflow": "Retention"}
    final = evaluate(case)
    assert [a["question_id"] for a in final["context"]["report"]["answers"]] == ["Q1", "Q2", "Q3"]
    assert final["result"]["status"] == "Facially Complete"


@pytest.mark.parametrize("investor,form,allowed", [("USDA", "RMA", True), ("USDA", "UBAF", True), ("GSE", "RMA", False), ("FHA", "UBAF", True), ("Asset", "RMA", False)])
def test_investor_forms(case, investor, form, allowed):
    case["msp"]["dlq1"]["investor_type"] = investor
    case["documents"]["application_form"]["type"] = form
    final = evaluate(case)
    assert bool(stips(final, "Q3")) is not allowed


def test_joint_signatures_q4_and_qx(case):
    case["msp"]["coborrower_name"] = "Second Borrower"
    final = evaluate(case)
    assert answers(final, "Q3")[0]["answer"] is False and stips(final, "Q3")
    assert answers(final, "Q4")[0]["answer"] is True and not stips(final, "Q4")
    assert len(answers(final, "Q3")[0]["sub_checks"]) == 2
    assert answers(final, "QX")[0]["answer"] is False and not stips(final, "QX")
    case["msp"]["dlq1"]["investor_type"] = "FHA"
    final = evaluate(case)
    assert not stips(final, "Q3") and not answers(final, "Q4")


@pytest.mark.parametrize("qid,change", [
    ("Q2", lambda c: c["msp"].update(lmt1=None)),
    ("Q3", lambda c: c["documents"]["application_form"].update(borrower_signature=False)),
    ("Q4", lambda c: c["documents"]["application_form"].update(borrower_signature=False)),
    ("Q4b", lambda c: c["flags"].update(maa_page_count_issue=True)),
    ("Q5", lambda c: c["msp"]["lmt3"].update(l92_date=None)),
    ("Q6", lambda c: c["documents"]["application_form"].update(occupancy_status=None)),
    ("Q7", lambda c: c["documents"]["application_form"].update(hardship_reason=None)),
    ("Q8a", lambda c: c["documents"]["application_form"].update(hoa_indicated=True)),
    ("Q9", lambda c: c["documents"]["application_form"].update(other_income_description="Non-borrower contribution")),
    ("Q13", lambda c: c["msp"]["lmt3"].update(review_date_minus_90="2026-03-01")),
    ("Q14", lambda c: [s.update(pay_frequency=None) for s in c["documents"]["paystubs"]]),
    ("Q16", lambda c: c["documents"].update(paystubs=c["documents"]["paystubs"][:1])),
    ("Q17", lambda c: c["documents"]["paystubs"][-1].update(has_ytd_earnings=False)),
    ("Q30", lambda c: c["documents"]["bank_statement"].update(recurring_deposits_over_250=[{"source": "Friend", "amount": 250, "months": 2}])),
    ("Q32", lambda c: c["documents"]["application_form"].update(mailing_address="2 Other Street")),
    ("Q33", lambda c: c["msp"]["haz1"].update(policy_expiry_date="2026-10-22")),
    ("Q34", lambda c: c["msp"]["ana1"].update(tax_bill_on_file=False)),
    ("Q36", lambda c: c["flags"].update(document_altered=True)),
])
def test_stip_trigger_checklist(case, qid, change):
    change(case)
    final = evaluate(case)
    assert stips(final, qid), qid
    assert final["result"]["status"] == "Facially Incomplete"
    report = final["context"]["report"]
    assert report["dm712_required"]
    assert [s["stip_id"] for s in report["stip_list"]] == [f"STIP-{i:03d}" for i in range(1, report["stip_count"] + 1)]
    if qid == "Q36":
        assert not answers(final, "CALC_Q1")


@pytest.mark.parametrize("qid", ["Q2", "Q3", "Q4", "Q4b", "Q5", "Q6", "Q7", "Q8", "Q8a", "Q9", "Q10", "Q11", "Q12", "Q13", "Q14", "Q16", "Q17", "Q30", "Q32", "Q33", "Q34", "Q35", "Q36"])
def test_null_stip_policy_for_each_question(case, qid):
    from app.engine.retention_support import Evaluation
    final = evaluate(case)
    e = Evaluation(final, Deps(None, get_playbook(2).rules, NOW))
    e.context.pop("wage_index", None)
    before = len(e.report["stip_list"])
    row = e.answer(qid, None, "default", "All available sources exhausted.")
    assert len(e.report["stip_list"]) == before + 1
    assert row["result"] == "fail"


@pytest.mark.parametrize("qid", ["Q1", "QX", "Q9a", "Q9b", "Q9c", "Q9d", "Q9e", "Q15", "Q15a", "Q18", "Q19", "Q31", "CALC_Q1", "CALC_Q2", "CALC_Q3", "CALC_Q4"])
def test_informational_questions_never_stip(case, qid):
    from app.engine.retention_support import Evaluation
    e = Evaluation(evaluate(case), Deps(None, get_playbook(2).rules, NOW))
    e.context.pop("wage_index", None)
    before = len(e.report["stip_list"])
    for value in (True, False, None):
        e.answer(qid, value, "default", "Informational only.")
    assert len(e.report["stip_list"]) == before


def test_missing_income_and_wage_sources(case):
    case["documents"].update(paystubs=[], bank_statement=None)
    final = evaluate(case)
    assert stips(final, "Q10") and stips(final, "Q11") and stips(final, "Q12") and stips(final, "Q13")
    assert answers(final, "Q11")[0]["answer"] is None
    assert len(answers(final, "Q12")) == 1
    case["documents"]["application_form"]["income_sources"] = []
    final = evaluate(case)
    assert answers(final, "Q10")[0]["answer"] is None and stips(final, "Q10")
    assert not answers(final, "Q11")


def test_wage_loop_primary_only_and_latest_stub(case):
    other = [{**s, "employer_name": "County School", "has_variable_pay": True} for s in case["documents"]["paystubs"]]
    co = [{**s, "employee_name": "Second Borrower", "employer_name": "Co Company"} for s in other]
    case["documents"]["paystubs"] += other + co
    # Deliberately unsorted: Q17 must inspect latest pay_date, not list order.
    case["documents"]["paystubs"].reverse()
    final = evaluate(case)
    assert answers(final, "Q11")[0]["answer"] == "2"
    for qid in [f"Q{i}" for i in range(12, 20)]:
        assert len(answers(final, qid)) == 2
        assert {a["wage_number"] for a in answers(final, qid)} == {1, 2}
    assert any(a["answer"] for a in answers(final, "Q19"))
    assert [t["outcome"] for t in final["trace"] if t["node"] == "next_wage"] == ["more", "done"]
    assert all(a["answer"] for a in answers(final, "Q17"))


def test_latest_ytd_not_older_stub(case):
    case["documents"]["paystubs"][-1]["gross_current_period"] = case["documents"]["paystubs"][-1]["net_pay"]
    case["documents"]["paystubs"].reverse()
    assert stips(evaluate(case), "Q17")


def test_handwriting_branches_and_contribution_subquestions(case):
    case["documents"]["paystubs"][0]["is_handwritten"] = True
    final = evaluate(case)
    assert answers(final, "Q15a") and not stips(final, "Q15a")
    case["documents"]["application_form"]["other_income_description"] = "Family support"
    final = evaluate(case)
    assert stips(final, "Q9")
    for qid in ("Q9a", "Q9b", "Q9c", "Q9d", "Q9e"):
        assert answers(final, qid) and not stips(final, qid)


def test_other_income_skips_wage_checks(case):
    case["documents"]["application_form"]["income_sources"] = [{"type": "Pension", "gross_monthly_amount": 2000}]
    case["documents"]["bank_statement"]["all_deposits"] = [{"description": "Pension", "date": "03/01/2026"}]
    final = evaluate(case)
    assert answers(final, "Q10")[0]["answer"] == "Pension"
    assert answers(final, "Q10a") and not answers(final, "Q11")
    assert not stips(final, "Q10")


def test_default_confidence_ignored_and_stips_take_precedence(case):
    case["documents"]["application_form"].pop("desired_workflow")
    final = evaluate(case)
    assert final["result"]["status"] == "Facially Complete" and not final.get("paused")
    assert answers(final, "Q1")[0]["confidence"] == .50
    assert answers(final, "Q1")[0]["explanation"] == "Default applied"
    assert not final["review_reason"]
    assert answers(final, "Q1")[0]["result"] == "pass"
    case["flags"]["maa_page_count_issue"] = True
    final = evaluate(case)
    assert not final.get("paused") and final["result"]["status"] == "Facially Incomplete"


def test_confidence_cannot_change_verdict_or_badges(case):
    rules = deepcopy(get_playbook(2).rules)
    rules["confidence"] = {"high": .90, "medium": .90}
    assert evaluate(case, rules)["result"]["status"] == "Facially Complete"
    rules["confidence"].update(high=.01, medium=.01, inferred=.01, default=.01)
    final = evaluate(case, rules)
    assert final["result"]["status"] == "Facially Complete"
    report = final["context"]["report"]
    assert report["overall_confidence"] == .01  # retained only for audit
    assert report["confidence_considered"] is False and not report["low_confidence_flags"]
    assert all(a["result"] in ("pass", "neutral") for a in report["answers"] if a["answer"] is not None)


@pytest.mark.parametrize("config", ["absent", None, {}, {"high": .75}])
def test_optional_confidence_supports_full_graph_and_joint_signatures(case, config):
    from app.engine.retention_support import DEFAULT_CONFIDENCE

    rules = deepcopy(get_playbook(2).rules)
    rules.pop("confidence", None)
    if config != "absent":
        rules["confidence"] = config
    original = deepcopy(rules)
    case["msp"]["coborrower_name"] = "Second Borrower"
    case["documents"]["application_form"]["coborrower_signature"] = True

    final = evaluate(case, rules)

    assert final["result"]["status"] == "Facially Complete"
    report = final["context"]["report"]
    expected = {**DEFAULT_CONFIDENCE, **(config if isinstance(config, dict) else {})}
    assert answers(final, "Q3")[0]["confidence"] == expected["high"]
    assert [check["confidence"] for check in answers(final, "Q3")[0]["sub_checks"]] == [expected["high"]] * 2
    assert answers(final, "Q4b")[0]["confidence"] == expected["medium"]
    assert report["confidence_considered"] is False
    assert not report["low_confidence_flags"]
    assert rules == original  # Never mutate the shared cached playbook rules.


def test_only_canonical_retention_nodes_are_registered():
    pb = get_playbook(2)
    assert pb.spec.process == "retention"
    assert all(n.run.startswith("retention.") for n in pb.spec.nodes.values() if n.run)
    assert not any(name.startswith("retention_eligibility.") for name in NODES)


def test_sale_proxy_inferred_and_not_stip(case):
    case["msp"]["foreclosure"]["sale_date"] = None
    final = evaluate(case)
    assert answers(final, "CALC_Q4")[0]["answer"] == "2027-03-21"
    assert answers(final, "CALC_Q4")[0]["confidence"] == .85
    assert not stips(final, "CALC_Q4") and final["result"]["status"] == "Facially Complete"


def test_nots_l92_business_day_and_window(case):
    case["msp"]["lmt3"]["l92_date"] = None
    case["msp"]["nots"] = {"notes": ["Documents submitted via email"], "latest_note_date": "2026-03-16"}
    final = evaluate(case)
    assert answers(final, "Q5")[0]["answer"] == "2026-03-13"
    assert answers(final, "Q5")[0]["confidence"] == .92
    case["msp"]["nots"]["latest_note_date"] = "2026-03-10"
    assert stips(evaluate(case), "Q5")


@pytest.mark.parametrize("investor,stip", [("GSE", True), ("FNMA", True), ("FHLMC", True), ("FHA", False), ("Asset", False), ("USDA", False)])
def test_investor_bank_requirement(case, investor, stip):
    case["msp"]["dlq1"]["investor_type"] = investor
    case["documents"]["bank_statement"] = None
    assert bool(stips(evaluate(case), "Q30")) is stip


def test_recurring_small_deposits_sum_months_and_loe(case):
    bank = case["documents"]["bank_statement"]
    deposits = [{"date": day, "amount": 125, "description": "Source A", "reference_number": str(i)} for i, day in enumerate(["01/01/2026", "01/15/2026", "02/01/2026", "02/15/2026"])]
    bank["all_deposits"] = deposits
    assert stips(evaluate(case), "Q30")
    case["documents"]["letter_of_explanation"] = {"loe_sufficient": "yes", "deposit_references": [{"reference": str(i)} for i in range(4)]}
    assert not stips(evaluate(case), "Q30")
    case["documents"]["letter_of_explanation"] = None
    deposits[2]["date"], deposits[3]["date"] = "03/01/2026", "03/15/2026"
    assert not stips(evaluate(case), "Q30")


def test_bank_balance_is_not_a_deposit_amount(case):
    case["documents"]["bank_statement"]["all_deposits"] = [{"date": d, "balance": 9999, "description": "Payroll", "reference_number": d} for d in ("01/01/2026", "02/01/2026")]
    assert not stips(evaluate(case), "Q30")


@pytest.mark.parametrize("accounts,balance,report_date,answer,stip", [(0, 0, "03/20/2026", True, True), (3, 1000, "03/20/2026", False, False), (3, 1000, None, None, True), (3, 1000, "01/01/2025", None, True)])
def test_usda_credit_only(case, accounts, balance, report_date, answer, stip):
    case["msp"]["dlq1"]["investor_type"] = "USDA"
    case["documents"]["credit_report"].update(total_accounts=accounts, total_balance=balance, report_date=report_date)
    final = evaluate(case)
    assert answers(final, "Q35")[0]["answer"] is answer
    assert bool(stips(final, "Q35")) is stip


def test_nongse_does_not_count_payroll_as_paystubs(case):
    case["documents"]["paystubs"] = []
    case["documents"]["bank_statement"]["all_deposits"] = [{"date": d, "description": "Payroll Acme"} for d in ("01/01/2026", "01/15/2026")]
    assert answers(evaluate(case), "Q13")[0]["answer"] == "2"
    case["msp"]["dlq1"]["investor_type"] = "FHA"
    final = evaluate(case)
    assert answers(final, "Q13")[0]["answer"] == "0" and stips(final, "Q13")


def test_same_address_and_insurance_boundary(case):
    case["documents"]["application_form"]["mailing_address"] = "SAME AS PROPERTY ADDRESS"
    case["msp"]["haz1"]["policy_expiry_date"] = "2026-10-23"
    final = evaluate(case)
    assert not stips(final, "Q32") and not stips(final, "Q33")


def install_case(case):
    with SessionLocal() as db:
        msp, doc = db.get(models.Msp, LOAN), db.get(models.ExtractedData, LOAN)
        for key, value in case["msp"].items():
            if key not in ("loan_id",):
                setattr(msp, key, value)
        for key, value in case["documents"].items():
            setattr(doc, key, value)
        doc.flags = case["flags"]
        db.get(models.LmStages, LOAN).intake_status = "Complete"
        db.commit()


def test_playbook_startup_and_api_report(loaded, case):
    install_case(case)
    pb = loaded.get("/api/processes/2/playbook")
    assert pb.status_code == 200 and pb.json()["process"] == "retention"
    assert loaded.get("/api/retention/summary").json()["eligible"] == 1
    assert loaded.post("/api/processes/2/run").json() == {"queued": 1, "loan_ids": [LOAN]}
    detail = loaded.get(f"/api/retention/cases/{LOAN}").json()
    assert detail["status"] == "Facially Complete" and detail["report"]["stip_count"] == 0
    assert detail["report"]["loan_id"] == LOAN
    assert loaded.get("/api/retention/cases").json()[0]["last_run_id"] == detail["last_run_id"]
    output = loaded.get(f"/api/agent-runs/{detail['last_run_id']}").json()["output"]
    assert output["report"] == detail["report"]
    assert loaded.post("/api/processes/2/run").json()["queued"] == 0
    assert loaded.get("/api/retention/cases/missing").status_code == 404
    assert loaded.post(f"/api/retention/cases/{LOAN}/review").status_code == 409


def test_candidates_require_complete_intake_and_no_status(loaded, case):
    assert loaded.post("/api/processes/2/run").json()["queued"] == 0
    assert loaded.get("/api/retention/summary").json()["records"] == []
    with SessionLocal() as db:
        lm = db.get(models.LmStages, LOAN)
        for status in (None, "Missing Doc", "In Human Review", "End Case"):
            lm.intake_status = status
            db.flush()
            assert runner.stage_candidates(db, 2) == []
        lm.intake_status = "Complete"
        db.flush()
        assert runner.stage_candidates(db, 2) == [LOAN]
        for status in models.STAGE_BY_NO[2].allowed:
            lm.retention_eligibility_status = status
            db.flush()
            assert runner.stage_candidates(db, 2) == []


@pytest.mark.parametrize("use_proxy", [True, False])
def test_low_confidence_completes_without_inbox_item(loaded, case, use_proxy):
    case["documents"]["application_form"].pop("desired_workflow")
    # A balance whose trial payment fits the 40% housing ratio, so Trial UW reaches its gate.
    case["msp"]["dlq1"]["upb_balance"] = 180000.0
    if use_proxy:
        case["msp"]["foreclosure"]["sale_date"] = None
    install_case(case)
    loaded.post("/api/processes/2/run")
    detail = loaded.get(f"/api/retention/cases/{LOAN}").json()
    assert detail["status"] == "Facially Complete" and not detail["report"]["dm712_required"]
    # Retention still creates no review. Its successful handoff now pauses at
    # the mandatory Trial UW plan-selection gate instead of auto-approving UW.
    pending = loaded.get("/api/decisions?status=pending").json()
    assert not any(d["stage_no"] == 2 for d in pending)
    assert len(pending) == 1 and pending[0]["stage_no"] == 3
    assert pending[0]["gate"] == "underwriter_review" and pending[0]["trial_plans"]
    assert all(p["status"] == "proposed" for p in pending[0]["trial_plans"])
    assert detail["report"]["confidence_considered"] is False
    assert not detail["report"]["low_confidence_flags"]
    assert detail["report"]["answers"]


def test_pending_actions_and_manual_inbox_route(loaded, case):
    case["flags"]["maa_page_count_issue"] = True
    install_case(case)
    loaded.post("/api/processes/2/run")
    summary = loaded.get("/api/retention/summary").json()
    assert summary["counts"]["Facially Incomplete"] == 1 and len(summary["pending_actions"]) == 1
    assert summary["pending_actions"][0]["pending_reason"]
    routed = loaded.post(f"/api/retention/cases/{LOAN}/review")
    assert routed.status_code == 200, routed.text
    decision_id = routed.json()["decision_id"]
    assert loaded.post(f"/api/retention/cases/{LOAN}/review").json()["decision_id"] == decision_id
    assert loaded.post(f"/api/decisions/{decision_id}/decide", json={"decision": "approved", "note": "Documents still needed"}).status_code == 200
    detail = loaded.get(f"/api/retention/cases/{LOAN}").json()
    assert detail["status"] == "Facially Incomplete" and detail["report"]["dm712_required"]
    assert detail["report"]["stip_count"] > 0


def test_retention_yaml_team_and_rules_validation(tmp_path):
    import yaml
    pb = get_playbook(2)
    rules = deepcopy(pb.rules)
    rules["review"]["team"] = "Retention QA"
    (tmp_path / "playbook.yaml").write_text(pb.path.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "rules.yaml").write_text(yaml.safe_dump(rules), encoding="utf-8")
    compiled = load_playbook(tmp_path / "playbook.yaml")
    assert compiled.node("human_review").team == "Retention QA"
    assert all(n.run in NODES for n in compiled.spec.nodes.values() if n.run)


def test_one_paystub_stip_belongs_to_q16_not_q13(case):
    case["documents"]["paystubs"] = case["documents"]["paystubs"][:1]
    final = evaluate(case)
    assert answers(final, "Q13")[0]["answer"] == "1"
    assert not stips(final, "Q13") and stips(final, "Q16")


def test_hoa_reference_and_amount_fallback(case):
    case["msp"]["nots"] = {"latest_note_date": "2026-03-20", "notes": ["HOA fees are due"]}
    assert stips(evaluate(case), "Q8")
    case["msp"]["hoa"].update(hoa_exists=True, monthly_amount=250)
    final = evaluate(case)
    assert answers(final, "Q8a")[0]["answer"] is True and not stips(final, "Q8a")


def test_source_waterfall_and_stale_notes(case):
    case["msp"]["nots"] = {"latest_note_date": "2026-03-20", "notes": ["Liquidation requested; vacant property; job loss"]}
    final = evaluate(case)
    assert answers(final, "Q1")[0]["answer"] == "Retention"  # application wins
    assert answers(final, "Q6")[0]["answer"] == "Owner Occupied"
    case["documents"]["application_form"].update(occupancy_status=None, hardship_reason=None)
    final = evaluate(case)
    assert answers(final, "Q6")[0]["answer"] == "Vacant"
    assert answers(final, "Q7")[0]["answer"] == "Unemployment / Job Loss"
    assert answers(final, "Q6")[0]["confidence"] == .92
    case["msp"]["nots"]["latest_note_date"] = "2026-03-01"
    assert stips(evaluate(case), "Q6")


def test_wage_frequency_inferred_from_payroll(case):
    for stub in case["documents"]["paystubs"]:
        stub["pay_frequency"] = None
    case["documents"]["bank_statement"]["all_deposits"] = [{"description": "Payroll Acme", "date": d} for d in ("01/02/2026", "01/09/2026", "01/16/2026")]
    final = evaluate(case)
    assert answers(final, "Q14")[0]["answer"] == "Weekly"
    assert answers(final, "Q14")[0]["confidence"] == .85
    assert not stips(final, "Q14") and final["result"]["status"] == "Facially Complete"


def test_unknown_frequency_is_note_only(case):
    for stub in case["documents"]["paystubs"]:
        stub["pay_frequency"] = "Unknown"
    assert not stips(evaluate(case), "Q14")


def test_unknown_credit_servicer_is_neutral_not_fabricated(case):
    case["documents"]["credit_report"]["tradelines"] = [{"type": "Mortgage"}]
    final = evaluate(case)
    assert answers(final, "Q31")[0]["answer"] is None
    assert answers(final, "Q31")[0]["result"] == "neutral" and not stips(final, "Q31")


def test_other_mortgage_and_us_bank(case):
    credit = case["documents"]["credit_report"]
    credit["tradelines"] = [{"type": "Mortgage", "servicer": "Other Bank"}]
    assert answers(evaluate(case), "Q31")[0]["answer"] is True
    credit["tradelines"][0]["servicer"] = "US Bank"
    assert answers(evaluate(case), "Q31")[0]["answer"] is False


def test_stip_text_and_authenticity_keywords_are_configurable(case):
    rules = deepcopy(get_playbook(2).rules)
    rules["stips"]["Q36"]["reason"] = "Custom supervisor review required"
    rules["authenticity_flags"].append("custom_review")
    case["flags"]["custom_review"] = True
    final = evaluate(case, rules)
    assert stips(final, "Q36")[0]["reason"] == "Custom supervisor review required"
    assert not answers(final, "CALC_Q1")


def test_denied_manual_review_cannot_become_incomplete(loaded, case):
    case["msp"]["lmt1"]["loan_type_status"] = "MOD"
    install_case(case)
    loaded.post("/api/processes/2/run")
    routed = loaded.post(f"/api/retention/cases/{LOAN}/review")
    assert routed.status_code == 200
    decision_id = routed.json()["decision_id"]
    assert loaded.post(f"/api/decisions/{decision_id}/decide", json={"decision": "approved"}).status_code == 200
    detail = loaded.get(f"/api/retention/cases/{LOAN}").json()
    assert detail["status"] == "Denied" and not detail["report"]["dm712_required"]


def test_active_workflow_excludes_retention_candidate(loaded, case):
    install_case(case)
    with SessionLocal() as db:
        db.add(models.WorkflowRun(id="wf-active", loan_id=LOAN, status="running", trigger="manual", current_stage=2, started_at=NOW))
        db.flush()
        assert runner.stage_candidates(db, 2) == []


def test_all_real_seed_shapes_evaluate_without_mutation():
    """Read every real input row without importing into or touching the running DB."""
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "scripts"
    loans = json.loads((root / "msp.json").read_text(encoding="utf-8"))["loans"]
    extracted = {row["loan_id"]: row["extracted_data"] for row in json.loads((root / "extracted_data.json").read_text(encoding="utf-8"))["loans"]}
    keys = {"application_form": "Application_Form", "paystubs": "PAYSTUBS", "bank_statement": "BANK_STATEMENT", "credit_report": "CREDIT_REPORT", "letter_of_explanation": "LETTER_OF_EXPLANATION"}
    for loan in loans:
        loan = deepcopy(loan)
        doc = extracted[loan["loan_id"]]
        loan.update({key.lower(): value for key, value in loan.pop("servicing_data").items()})
        final = evaluate({"msp": loan, "flags": doc.get("flags") or {}, "documents": {key: doc.get(source) for key, source in keys.items()}})
        assert final.get("result") or final.get("paused"), loan["loan_id"]
        assert final["context"]["report"]["answers"]
        if loan["loan_id"] == LOAN:  # Alexandra's actual JSON package, not a corrected fixture
            assert answers(final, "Q16")[0]["result"] == "pass"
            assert answers(final, "QX")[0]["result"] == "pass"
            assert final["result"]["status"] == "Facially Complete"


def test_fnma_exit_keeps_no_stips_even_if_lmt1_missing(case):
    case["msp"]["dlq1"].update(investor_type="FNMA", months_delinquent=10)
    case["msp"]["lmt1"] = None
    final = evaluate(case)
    assert final["result"]["node"] == "form_exempt_exit"
    assert final["context"]["report"]["stip_count"] == 0


def test_q12_application_employer_precedes_bank_description(case):
    case["documents"]["paystubs"] = []
    case["documents"]["application_form"]["income_sources"][0]["employer"] = "Acme"
    case["documents"]["bank_statement"]["all_deposits"] = [{"description": "Payroll Acme", "date": "01/01/2026"}]
    final = evaluate(case)
    assert answers(final, "Q12")[0]["answer"] == "Acme"
    assert answers(final, "Q12")[0]["confidence"] == .92