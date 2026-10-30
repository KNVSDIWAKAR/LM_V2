"""Hardship-specific documents, neutral dates and auditable consecutive periods."""

from copy import deepcopy

import pytest

from app.engine.playbook import get_playbook
from .conftest import LOAN
from .test_retention import answers, case, evaluate, install_case, stips  # noqa: F401


@pytest.mark.parametrize("missing_document", [False, True])
def test_run_messages_only_summarize_stips(case, missing_document):
    if missing_document:
        case["documents"]["application_form"]["hardship_reason"] = "Death of spouse"
    final = evaluate(case)
    details = [step.get("detail", "") for step in final["trace"]]
    expected_count = 1 if missing_document else 0
    assert f"{expected_count} stip(s)" in details
    assert all("confidence" not in detail.lower() for detail in details)
    assert final["context"]["report"]["confidence_considered"] is False


@pytest.mark.parametrize("hardship", ["Reduction in income", "Illness or Medical Expenses", "Job loss"])
@pytest.mark.parametrize("joint", [False, True])
def test_no_death_or_divorce_document_needed_for_other_hardships(case, hardship, joint):
    case["documents"]["application_form"]["hardship_reason"] = hardship
    if joint:
        case["msp"]["coborrower_name"] = "Second Borrower"
        case["documents"]["application_form"]["coborrower_signature"] = True
    final = evaluate(case)
    answer = answers(final, "QX")[0]
    assert answer["answer"] is False and answer["result"] == "pass"
    assert answer["document_required"] is False
    assert not stips(final, "QX")
    assert final["result"]["status"] == "Facially Complete"


@pytest.mark.parametrize("hardship,document", [
    ("Death of Borrower or Co-Borrower", "Death certificate"),
    ("Spouse passed away", "Death certificate"),
    ("Divorce or Legal Separation", "Divorce/separation agreement or quit-claim deed"),
    ("Separated from spouse", "Divorce/separation agreement or quit-claim deed"),
])
def test_relevant_hardship_makes_supporting_document_mandatory(case, hardship, document):
    case["documents"]["application_form"]["hardship_reason"] = hardship
    final = evaluate(case)
    assert answers(final, "QX")[0]["result"] == "fail"
    assert answers(final, "QX")[0]["document_required"] is True
    assert stips(final, "QX")[0]["document_required"] == document
    assert final["result"]["status"] == "Facially Incomplete"


@pytest.mark.parametrize("hardship,note", [
    ("Death of co-borrower", "Death certificate received"),
    ("Divorce", "Divorce decree on file"),
    ("Legal separation", "Separation agreement provided"),
    ("Divorce", "Quit-claim deed submitted"),
])
def test_required_document_receipt_passes(case, hardship, note):
    case["documents"]["application_form"]["hardship_reason"] = hardship
    case["msp"]["nots"] = {"latest_note_date": "2026-03-20", "notes": [note]}
    final = evaluate(case)
    assert answers(final, "QX")[0]["answer"] is True
    assert answers(final, "QX")[0]["result"] == "pass"
    assert not stips(final, "QX")


@pytest.mark.parametrize("note,stamp", [
    ("Death certificate not received", "2026-03-20"),
    ("Death certificate requested", "2026-03-20"),
    ("Death certificate required", "2026-03-20"),
    ("Death certificate", "2026-03-20"),
    ("Death certificate received", "2026-03-01"),
    ("Divorce agreement received", "2026-03-20"),
])
def test_missing_stale_or_unrelated_document_does_not_satisfy_death_requirement(case, note, stamp):
    case["documents"]["application_form"]["hardship_reason"] = "Death of spouse"
    case["msp"]["nots"] = {"latest_note_date": stamp, "notes": [note]}
    assert stips(evaluate(case), "QX")


def test_combined_hardships_need_each_document_and_policy_is_configurable(case):
    case["documents"]["application_form"]["hardship_reason"] = "Death and divorce"
    final = evaluate(case)
    assert len(stips(final, "QX")) == 2
    rules = deepcopy(get_playbook(2).rules)
    rules["hardship_documents"]["death"]["document_required"] = "Certified death certificate"
    assert stips(evaluate(case, rules), "QX")[0]["document_required"] == "Certified death certificate"


def test_hardship_source_priority_and_notes_fallback(case):
    case["msp"]["nots"] = {"latest_note_date": "2026-03-20", "notes": ["Hardship: death of spouse"]}
    assert not stips(evaluate(case), "QX")  # application reports reduced income
    case["documents"]["application_form"]["hardship_reason"] = None
    assert stips(evaluate(case), "QX")


def test_date_only_values_are_neutral_and_not_applicable_checks_pass(case):
    case["msp"]["foreclosure"]["sale_date"] = None
    final = evaluate(case)
    for qid in ("Q5", "CALC_Q4"):
        row = answers(final, qid)[0]
        assert row["result"] == "neutral" and row["display_type"] == "date"
        assert not stips(final, qid)
    assert answers(final, "Q35")[0]["result"] == "pass"
    assert final["context"]["report"]["summary"]["neutral"] == 2


@pytest.mark.parametrize("invalid", [None, "invalid", "2026-02-30"])
def test_missing_or_invalid_required_date_fails(case, invalid):
    case["msp"]["lmt3"]["l92_date"] = invalid
    final = evaluate(case)
    assert answers(final, "Q5")[0]["result"] == "fail"
    assert stips(final, "Q5")


def test_missing_optional_proxy_is_neutral(case):
    case["msp"]["foreclosure"]["sale_date"] = None
    case["msp"]["lmt3"]["review_start_date"] = None
    final = evaluate(case)
    assert answers(final, "CALC_Q4")[0]["answer"] is None
    assert answers(final, "CALC_Q4")[0]["result"] == "neutral"
    assert not stips(final, "CALC_Q4")


def test_alexandra_january_february_paystubs_pass_by_consecutive_months(case):
    case["documents"]["paystubs"][1].update(pay_period_start="02/16/2026", pay_period_end="02/28/2026", pay_date="03/02/2026")
    final = evaluate(case)
    assert answers(final, "Q13")[0]["answer"] == "2"
    row = answers(final, "Q16")[0]
    assert row["answer"] is True and row["result"] == "pass"
    assert row["coverage_gaps"] == [{"start": "2026-02-01", "end": "2026-02-15"}]
    assert "consecutive calendar months" in row["explanation"]
    assert row["sequence_basis"] == "consecutive_calendar_months"
    assert row["consecutive_month_count"] == 2
    assert not stips(final, "Q16")
    assert final["result"]["status"] == "Facially Complete"


def test_skipped_coverage_month_does_not_pass_q16(case):
    case["documents"]["paystubs"][1].update(pay_period_start="03/16/2026", pay_period_end="03/31/2026", pay_date="04/02/2026")
    final = evaluate(case)
    assert answers(final, "Q16")[0]["result"] == "fail"
    assert stips(final, "Q16")


def test_monthly_acceptance_is_configurable(case):
    case["documents"]["paystubs"][1].update(pay_period_start="02/16/2026", pay_period_end="02/28/2026", pay_date="03/02/2026")
    rules = deepcopy(get_playbook(2).rules)
    rules["paystub_sequence"]["allow_consecutive_months"] = False
    assert stips(evaluate(case, rules), "Q16")


def test_two_nonadjacent_periods_in_same_month_do_not_pass(case):
    case["documents"]["paystubs"][0].update(pay_period_start="01/01/2026", pay_period_end="01/07/2026")
    case["documents"]["paystubs"][1].update(pay_period_start="01/22/2026", pay_period_end="01/28/2026")
    assert stips(evaluate(case), "Q16")


def test_consecutive_periods_pass_even_with_duplicate_copies(case):
    case["documents"]["paystubs"].append(deepcopy(case["documents"]["paystubs"][1]))
    final = evaluate(case)
    row = answers(final, "Q16")[0]
    assert row["result"] == "pass" and row["consecutive_period_count"] == 2
    assert len(row["pay_periods"]) == 2 and not row["coverage_gaps"]
    assert not stips(final, "Q16")


def test_duplicate_only_is_not_two_consecutive_periods(case):
    first = case["documents"]["paystubs"][0]
    case["documents"]["paystubs"] = [first, deepcopy(first)]
    assert stips(evaluate(case), "Q16")


def test_neutral_report_and_hardship_stip_survive_api_roundtrip(loaded, case):
    case["documents"]["application_form"]["hardship_reason"] = "Death of spouse"
    install_case(case)
    response = loaded.post("/api/processes/2/run")
    assert response.status_code == 202
    response = loaded.get(f"/api/retention/cases/{LOAN}")
    assert response.status_code == 200, response.text
    detail = response.json()
    report = detail["report"]
    assert report["question_results_version"] == 2
    assert next(a for a in report["answers"] if a["question_id"] == "Q5")["result"] == "neutral"
    assert next(a for a in report["answers"] if a["question_id"] == "QX")["result"] == "fail"
    assert detail["status"] == "Facially Incomplete" and report["stip_list"][0]["question_id"] == "QX"