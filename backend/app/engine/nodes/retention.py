"""Deterministic ART question functions. Routing and business policy live in YAML.

Only the primary borrower's income is evaluated. Every fallback records its provenance;
no absent upload, document, amount, date or investor subtype is fabricated.
"""

from collections import defaultdict
from datetime import timedelta

from ... import models
from ..registry import node
from ..retention_support import Evaluation, classify, contains, dated_notes, norm, number, parse_date, primary_stubs, question


@node("retention.load_case")
def load_case(state, deps):
    msp = deps.db.get(models.Msp, state["loan_id"])
    if msp is None:
        raise LookupError(f"Loan {state['loan_id']} is not in MSP")
    extracted = deps.db.get(models.ExtractedData, state["loan_id"])
    view = {key: getattr(msp, key, None) for key in (*models.msp.SCREENS, "borrower_name", "coborrower_name", "hoa", "foreclosure")}
    context = {"msp": view, "documents": {key: getattr(extracted, key) if extracted else None for key in models.DOCUMENT_TYPES},
               "flags": (extracted.flags if extracted else None) or {}, "notes": dated_notes(view),
               "report": {"loan_id": state["loan_id"], "borrower_name": msp.borrower_name,
                          "evaluation_date": deps.now.date().isoformat(), "review_start_date": (msp.lmt3 or {}).get("review_start_date"),
                          "answers": [], "stip_list": []}}
    return Evaluation({"context": context}, deps).finish()


@question("Q1")
def q1(e):
    value = classify(e.maa.get("desired_workflow"), e.rules["workflow_keywords"])
    level, explanation = "high", "Application desired workflow."
    if value is None:
        value = classify(e.note_text, e.rules["workflow_keywords"])
        level, explanation = "medium", "Dated NOTS workflow inside the review window."
    if value is None:
        value, level, explanation = e.rules["default_workflow"], "default", "Default applied"
    e.answer("Q1", value, level, explanation)
    if value == "Liquidation":
        e.context["exit_reason"] = "Liquidation requested — exit retention without stips."


@question("Q2")
def q2(e):
    screen = e.msp.get("lmt1")
    value = None if screen is None or "loan_type_status" not in screen else bool(str(screen["loan_type_status"] or "").strip())
    e.answer("Q2", value, "default" if value is None else "high", "MSP LMT1 loan type/status checked." if value is not None else "MSP LMT1 loan type/status unavailable.")
    if value:
        e.context["exit_reason"] = "Already approved for a long-term option — exit to Post-Underwriting."


@question("investor_rules")
def investor_rules(e):
    threshold = e.policy.get("form_exempt_after_months")
    delinquent = number((e.msp.get("dlq1") or {}).get("months_delinquent"))
    if threshold is not None and delinquent is not None and delinquent > threshold:
        e.context["exit_reason"] = f"{e.investor} over {threshold} months delinquent — no form checks required."
        # The specified exemption is an unconditional no-stip exit, including a
        # preceding unavailable LMT1 answer; retain that answer for auditability.
        e.report["stip_list"] = []
        e.outcome = "exempt"
    else:
        e.outcome = "va" if e.policy.get("request_only") else "standard"


@question("va_request")
def va_request(e):
    e.answer("Q3", None, "high", "VA request-only workflow — application and detailed form checks not required.", not_applicable=True)


def signature(e, key):
    if e.maa.get(key):
        return True, "high"
    if e.flags.get(f"missing_{key}") is True:
        return False, "medium"
    if key in e.maa:
        return False, "high"
    return None, "default"


@question("Q3")
def q3(e):
    borrower, b_level = signature(e, "borrower_signature")
    co, c_level = signature(e, "coborrower_signature")
    required = [(borrower, b_level)]
    if e.joint and not e.policy.get("borrower_only_signature"):
        required.append((co, c_level))
    value = False if any(v is False for v, _ in required) else None if any(v is None for v, _ in required) else True
    level = min((level for _, level in required), key=lambda k: e.confidence[k])
    checks = [{"borrower": "Borrower-1", "answer": borrower, "confidence": e.confidence[b_level]}]
    if e.joint:
        checks.append({"borrower": "Borrower-2", "answer": co, "confidence": e.confidence[c_level]})
    row = e.answer("Q3", value, level, "Investor-required application signatures checked.", sub_checks=checks)
    forms = e.policy.get("forms")
    if not forms or e.maa.get("type") not in forms:
        e.stip("Q3", "form_type", forms=", ".join(forms or []), investor=e.investor or "Unknown")
        if row["result"] == "pass":
            row["result"] = "fail"


@question("Q4")
def q4(e):
    values = [signature(e, "borrower_signature")]
    if e.joint:
        values.append(signature(e, "coborrower_signature"))
    hits = [item for item in values if item[0] is True]
    value, level = hits[0] if hits else (None, "default") if any(v is None for v, _ in values) else (False, "high")
    e.answer("Q4", value, level, "Available borrower signatures checked.")


@question("signature_checks")
def signature_checks(e):
    e.outcome = "joint" if e.joint else "single"


@question("QX")
def qx(e):
    # Same priority as Q7: the application hardship wins over dated NOTS.
    hardship = e.maa.get("hardship_reason") or e.note_text
    policies = e.rules["hardship_documents"]
    required = [key for key, policy in policies.items() if contains(hardship, policy["hardship_keywords"])]
    evidence = {}
    for key, policy in policies.items():
        # A mention of a missing/requested document is not proof it was received.
        evidence[key] = [n for n in e.notes if contains(n["text"], policy["document_keywords"])
                         and contains(n["text"], e.rules["document_received_keywords"])
                         and not contains(n["text"], e.rules["document_missing_keywords"])]
    missing = [key for key in required if not evidence[key]]
    if missing:
        explanation = "Required hardship document evidence is missing: " + "; ".join(policies[key]["document_required"] for key in missing) + "."
    elif required:
        explanation = "Dated NOTS confirms receipt of the documents required for the reported hardship."
    else:
        explanation = "Reported hardship does not require death/divorce/separation documents; no document stip applies."
    row = e.answer("QX", any(evidence.values()), "medium" if any(evidence.values()) else "high", explanation,
                   informational=True, document_required=bool(required), hardship=hardship or None,
                   required_documents=[policies[key]["document_required"] for key in required],
                   document_evidence={key: evidence[key] for key in required})
    for key in missing:
        e.stip("QX", "hardship_document", document_required=policies[key]["document_required"], hardship=hardship)
    row["result"] = "fail" if missing else "pass"


@question("Q4b")
def q4b(e):
    # No page metadata table exists; FLAGS is the available fallback, not an invented count.
    issue = e.flags.get("maa_page_count_issue")
    e.answer("Q4b", not issue if isinstance(issue, bool) else None, "medium" if isinstance(issue, bool) else "default",
             "Application page-count extraction flag checked." if isinstance(issue, bool) else "No page metadata or page-count flag is available.")


@question("Q5")
def q5(e):
    value, level = parse_date(e.dates.get("l92_date")), "high"
    if value is None:
        note = next((n for n in e.notes if contains(n["text"], e.rules["submission_keywords"])
                 and contains(n["text"], e.rules["submission_channel_keywords"])), None)
        if note:
            value, level = parse_date(note["date"]) - timedelta(days=1), "medium"
            while value.weekday() in e.rules["business_weekend_days"]:
                value -= timedelta(days=1)
    e.answer("Q5", value.isoformat() if value else None, level if value else "default",
             "LMT3 L92 date." if level == "high" and value else "Dated submission NOTS minus one business day." if value else "All available L92 sources exhausted.")


def application_or_notes(e, qid, field, mapping):
    raw = e.maa.get(field)
    value = classify(raw, e.rules[mapping])
    # A nonempty hardship outside the named categories is explicitly Other Hardship.
    if qid == "Q7" and raw and value is None:
        value = e.rules["default_hardship_type"]
    level = "high"
    if value is None:
        value, level = classify(e.note_text, e.rules[mapping]), "medium"
    e.answer(qid, value, level if value else "default", f"{field.replace('_', ' ').capitalize()} from application." if level == "high" and value else "Dated NOTS fallback." if value else "All available sources exhausted.")


@question("Q6")
def q6(e):
    application_or_notes(e, "Q6", "occupancy_status", "occupancy_keywords")


@question("Q7")
def q7(e):
    application_or_notes(e, "Q7", "hardship_reason", "hardship_keywords")


@question("Q8")
def q8(e):
    hoa = e.msp.get("hoa") or {}
    if e.maa.get("hoa_indicated") is True:
        value, level = True, "high"
    elif hoa.get("hoa_exists") is True:
        value, level = True, "medium"
    elif e.maa.get("hoa_indicated") is False or hoa.get("hoa_exists") is False:
        value, level = False, "high" if "hoa_indicated" in e.maa else "medium"
    else:
        value, level = None, "default"
    referenced = contains(e.note_text, e.rules["hoa_keywords"])
    e.answer("Q8", value, level, "Application and MSP HOA evidence checked.",
             force_stip=value is False and referenced and not (number(hoa.get("monthly_amount")) or 0) > 0)


@question("Q8a")
def q8a(e):
    amount = number((e.msp.get("hoa") or {}).get("monthly_amount"))
    e.answer("Q8a", amount is not None and amount > 0, "medium" if amount is not None else "default",
             f"MSP HOA monthly amount: {amount}." if amount is not None else "No HOA amount is available.")


@question("Q9")
def q9(e):
    words = e.rules["contribution_keywords"]
    sources = [(str(e.maa.get("income_sources", [])) + " " + str(e.maa.get("other_income_description") or ""), "high"),
               (str(e.loe), "medium")]
    match = next(((True, level) for text, level in sources if contains(text, words)), None)
    if match is None:
        # Deposits clearly matching known income types are not third-party contributions.
        employers = [s.get("employer_name") for s in primary_stubs(e.context)]
        unmatched = [d for d in e.bank.get("all_deposits", [])
                     if d.get("description") and not any(e.employer_matches(name, d["description"]) for name in employers)
                     and classify(d["description"], e.rules["income_keywords"]) not in set(e.rules["income_keywords"]) - {"Contribution", "Other"}]
        if unmatched:
            match = (True, "inferred")
    if match is None and contains(e.note_text, words):
        match = (True, "medium")
    value, level = match or (False, "high" if e.maa or e.bank or e.notes else "default")
    e.answer("Q9", value, level, "Third-party contribution evidence found." if value else "No third-party contribution indicators in available records.")


def contribution_channel(e, qid):
    # The dataset contains no email sheet, fax cover, LMS or MIR upload metadata.
    e.answer(qid, False, "default", "No channel-specific contribution document metadata is available.")


@question("Q9a")
def q9a(e):
    contribution_channel(e, "Q9a")


@question("Q9b")
def q9b(e):
    contribution_channel(e, "Q9b")


@question("Q9c")
def q9c(e):
    found = contains(e.note_text, e.rules["contribution_keywords"])
    e.answer("Q9c", found, "medium" if e.notes else "default", "Dated NOTS checked for contribution comments.")


@question("Q9d")
def q9d(e):
    contribution_channel(e, "Q9d")


@question("Q9e")
def q9e(e):
    contribution_channel(e, "Q9e")


def income_type(e, raw):
    return classify(raw, e.rules["income_keywords"]) or e.rules["default_income_type"]


def supported_income(e, kind):
    for doc in e.rules["income_documents"][kind]:
        if doc == "paystubs" and primary_stubs(e.context):
            return True
        if doc == "bank_statement" and any(income_type(e, d.get("description")) == kind for d in e.bank.get("all_deposits", [])):
            return True
        if doc == "letter_of_explanation" and e.loe.get("loe_sufficient") in e.rules["loe_sufficient_values"]:
            if income_type(e, e.loe.get("income_type_explained") or e.loe.get("purpose")) == kind:
                return True
    return False


@question("Q10")
def q10(e):
    listed = [income_type(e, s.get("type")) for s in e.maa.get("income_sources", []) if (number(s.get("gross_monthly_amount")) or 0) > 0]
    kinds, level = list(dict.fromkeys(listed)), "high"
    if not kinds and primary_stubs(e.context):
        kinds, level = ["Wages"], "medium"
    if not kinds and e.bank.get("all_deposits"):
        kinds, level = list(dict.fromkeys(income_type(e, d.get("description")) for d in e.bank["all_deposits"] if d.get("description"))), "medium"
    if not kinds:
        # Explicit primary-borrower NOTS only; co-borrower income is out of scope.
        notes = " ".join(n["text"] for n in e.notes if "co borrower" not in norm(n["text"]) and "coborrower" not in norm(n["text"]))
        kind = classify(notes, e.rules["income_keywords"])
        kinds, level = [kind] if kind else [], "medium"
    row = e.answer("Q10", ", ".join(kinds) or None, level if kinds else "default", "Positive income types resolved using application, paystubs, bank deposits and dated NOTS.")
    for kind in dict.fromkeys(listed):
        if not supported_income(e, kind):
            e.stip("Q10", "income_support", income_type=kind)
            if row["result"] == "pass":
                row["result"] = "fail"
    e.context["income_types"] = kinds
    e.outcome = "wages" if "Wages" in kinds else "other" if kinds else "unknown"


def calculation_document(e):
    value = "Paystubs" if primary_stubs(e.context) else "Bank Statement" if e.bank else "Other"
    e.answer("Q10a", value, "high" if value != "Other" or e.loe else "default", "Calculation document selected from documents actually on file.")


@question("Q10a")
def q10a(e):
    calculation_document(e)


@question("other_income_document")
def other_income_document(e):
    calculation_document(e)


@question("Q11")
def q11(e):
    sources = list({norm(s["employer_name"]): s["employer_name"] for s in primary_stubs(e.context) if s.get("employer_name")}.values())
    level = "high"
    if not sources:
        sources, level = list(dict.fromkeys(d["description"] for d in e.payroll())), "medium"
    if not sources:
        sources, level = e.note_employers(), "medium"
    e.context.update(wage_sources=sources or [None], wage_index=0, wage_source_level=level if sources else "default")
    e.answer("Q11", str(len(sources)) if sources else None, level if sources else "default",
             "Distinct primary-borrower wage sources counted." if sources else "No wage source count available; assume one for subsequent checks.")


@question("Q12")
def q12(e):
    value, level = e.latest.get("employer_name"), "high"
    if value is None:
        employers = [s["employer"] for s in e.maa.get("income_sources", [])
                     if s.get("employer") and income_type(e, s.get("type")) == "Wages"]
        value = next((name for name in employers if e.employer_matches(name, e.wage)), None)
        if value is None and len(employers) == 1 and len(e.context["wage_sources"]) == 1:
            value = employers[0]
        level = "medium"
    if value is None:
        value, level = e.wage, e.context["wage_source_level"]
    if value is not None:
        e.context["wage_sources"][e.context["wage_index"]] = value
        e.context["current_wage_level"] = level
    e.answer("Q12", value, level, "Current primary-borrower wage employer identified." if value else "All employer-name sources exhausted.")


@question("Q13")
def q13(e):
    cutoff = parse_date(e.dates.get("review_date_minus_90"))
    count, level = None, "default"
    if cutoff:
        count = sum(bool(parse_date(s.get("pay_date")) and parse_date(s["pay_date"]) >= cutoff) for s in e.stubs)
        level = "high"
        if not count and e.policy.get("payroll_as_paystubs"):
            count = sum(bool(parse_date(d.get("date")) and parse_date(d["date"]) >= cutoff) for d in e.payroll(e.wage))
            level = "medium"
    e.answer("Q13", str(count) if count is not None else None, level, "Recent borrower-matched paystubs (or permitted GSE payroll deposits) counted.", force_stip=count == 0)


@question("Q14")
def q14(e):
    ordered = sorted(e.stubs, key=lambda s: parse_date(s.get("pay_date")) or parse_date("0001-01-01"), reverse=True)
    value = next((classify(s.get("pay_frequency"), e.rules["frequency_keywords"]) for s in ordered
                  if classify(s.get("pay_frequency"), e.rules["frequency_keywords"]) is not None), None)
    level = "high"
    if value is None:
        raw = next((s.get("frequency") for s in e.maa.get("income_sources", []) if income_type(e, s.get("type")) == "Wages" and s.get("frequency")), None)
        value, level = classify(raw, e.rules["frequency_keywords"]), "medium"
    if value is None:
        days = sorted({parse_date(d.get("date")) for d in e.payroll(e.wage) if parse_date(d.get("date"))})
        gaps = [(b - a).days for a, b in zip(days, days[1:])]
        value = next((label for label, (lo, hi) in e.rules["frequency_intervals"].items() if gaps and all(lo <= g <= hi for g in gaps)), None)
        level = "inferred"
    if value is None:
        notes = " ".join(n["text"] for n in e.notes if "co borrower" not in norm(n["text"]) and "coborrower" not in norm(n["text"]))
        value, level = classify(notes, e.rules["frequency_keywords"]), "medium"
    e.answer("Q14", value, level if value else "default", "Pay frequency resolved from the first available source." if value else "No pay frequency source is available.")


def stub_flag(e, qid, field):
    values = [s[field] for s in e.stubs if isinstance(s.get(field), bool)]
    value = True if any(values) else False if values and len(values) == len(e.stubs) else None
    e.answer(qid, value, "high" if value is not None else "default", f"{field.replace('_', ' ').capitalize()} checked for this wage source.")


@question("Q15")
def q15(e):
    stub_flag(e, "Q15", "is_handwritten")


@question("Q15a")
def q15a(e):
    found = contains(e.note_text, e.rules["employment_document_keywords"])
    e.answer("Q15a", found, "medium" if found else "default", "NOTS references employment documentation; validate its validity." if found else "No employment verification document data exists.")


@question("Q16")
def q16(e):
    # Duplicate copies cannot add periods or break a genuine consecutive sequence.
    periods = sorted({(parse_date(s.get("pay_period_start")), parse_date(s.get("pay_period_end"))) for s in e.stubs
                      if parse_date(s.get("pay_period_start")) and parse_date(s.get("pay_period_end"))
                      and parse_date(s["pay_period_start"]) <= parse_date(s["pay_period_end"])})
    longest = streak = 1 if periods else 0
    gaps = []
    for a, b in zip(periods, periods[1:]):
        gap = (b[0] - a[1]).days
        streak = streak + 1 if gap == e.rules["thresholds"]["sequential_gap_days"] else 1
        longest = max(longest, streak)
        if gap > e.rules["thresholds"]["sequential_gap_days"]:
            gaps.append({"start": (a[1] + timedelta(days=1)).isoformat(), "end": (b[0] - timedelta(days=1)).isoformat()})
    months = sorted({end.year * 12 + end.month for _, end in periods})
    month_longest = month_streak = 1 if months else 0
    sequence = e.rules["paystub_sequence"]
    for previous, current in zip(months, months[1:]):
        month_streak = month_streak + 1 if current - previous == sequence["month_gap"] else 1
        month_longest = max(month_longest, month_streak)
    required = e.rules["thresholds"]["minimum_paystubs"]
    adjacent_periods = longest >= required
    consecutive_months = sequence["allow_consecutive_months"] and month_longest >= required
    sequential = adjacent_periods or consecutive_months
    if sequential:
        value, level = True, "high"
    elif e.flags.get("only_one_paystub") is True:
        value, level = False, "medium"
    else:
        value, level = (False, "high") if periods else (None, "default")
    labels = "; ".join(f"{start.isoformat()} to {end.isoformat()}" for start, end in periods)
    if adjacent_periods:
        explanation = f"{longest} consecutive pay periods for {e.wage}: {labels}."
    elif consecutive_months:
        explanation = f"Paystubs cover {month_longest} consecutive calendar months for the same borrower and employer ({e.wage}): {labels}; intervening pay-period gaps are permitted."
    elif gaps:
        missing = "; ".join(f"{gap['start']} to {gap['end']}" for gap in gaps)
        explanation = f"Pay periods on file: {labels}; missing coverage: {missing} — two stubs alone do not prove consecutive periods."
    else:
        explanation = f"{len(periods)} distinct valid pay period(s) on file; {e.rules['thresholds']['minimum_paystubs']} consecutive periods required" + (f": {labels}." if labels else ".")
    e.answer("Q16", value, level, explanation, pay_periods=[{"start": start.isoformat(), "end": end.isoformat()} for start, end in periods],
             coverage_gaps=gaps, consecutive_period_count=longest, consecutive_month_count=month_longest,
             sequence_basis="adjacent_pay_periods" if adjacent_periods else "consecutive_calendar_months" if consecutive_months else None)


@question("Q17")
def q17(e):
    stub = e.latest
    gross, net = number(stub.get("gross_current_period")), number(stub.get("net_pay"))
    value = bool(stub.get("has_ytd_earnings") is True and gross is not None and net is not None and gross - net > 0) if stub else None
    e.answer("Q17", value, "high" if stub else "default", "Only the highest-pay-date stub checked for YTD earnings and positive deductions.")


@question("Q18")
def q18(e):
    stub_flag(e, "Q18", "has_variable_pay")


@question("Q19")
def q19(e):
    name = e.latest.get("employer_name") or e.wage
    e.answer("Q19", contains(name, e.rules["school_keywords"]) if name else None,
             e.context.get("current_wage_level", e.context["wage_source_level"]) if name else "default", "Wage employer checked against configured education keywords.")


@question("next_wage")
def next_wage(e):
    e.context["wage_index"] += 1
    e.outcome = "more" if e.context["wage_index"] < len(e.context["wage_sources"]) else "done"


def unexplained_recurring(e):
    """Use explicit deposit amounts, never running balances; aggregate by source/month."""
    cutoff = parse_date(e.dates.get("review_date_minus_90"))
    references = {str(r.get("reference")) for r in e.loe.get("deposit_references", []) if isinstance(r, dict) and r.get("reference")}
    explained = e.loe.get("loe_sufficient") in e.rules["loe_sufficient_values"]
    monthly = defaultdict(lambda: defaultdict(float))
    threshold = e.rules["thresholds"]
    for d in e.bank.get("all_deposits", []):
        day, amount = parse_date(d.get("date")), number(d.get("amount"))
        if not day or not cutoff or day < cutoff or amount is None:
            continue
        if explained and str(d.get("reference_number")) in references:
            continue
        source = norm(d.get("source") or d.get("description"))
        if source:
            monthly[source][day.year * 12 + day.month] += amount
    for by_month in monthly.values():
        qualified = sorted(m for m, amount in by_month.items() if amount >= threshold["deposit_amount"])
        streak, previous = 0, None
        for month in qualified:
            streak = streak + 1 if previous is not None and month == previous + 1 else 1
            if streak >= threshold["deposit_months"]:
                return True
            previous = month
    for d in e.bank.get("recurring_deposits_over_250", []):
        amount, months = number(d.get("amount")), number(d.get("months"))
        if amount is None or months is None:
            continue
        refs = d.get("reference_numbers") or ([d["reference_number"]] if d.get("reference_number") else [])
        if explained and refs and all(str(ref) in references for ref in refs):
            continue
        if amount >= threshold["deposit_amount"] and months >= threshold["deposit_months"]:
            return True
    return False


@question("Q30")
def q30(e):
    cutoff, end = parse_date(e.dates.get("review_date_minus_90")), parse_date(e.bank.get("statement_end_date"))
    if not e.bank or not cutoff or not end or end < cutoff:
        value = None if e.policy.get("bank_required") else False
        e.answer("Q30", value, "default" if value is None else "high", "No valid in-window bank statement; investor bank requirement applied.", stip_key="bank_missing")
        return
    e.answer("Q30", unexplained_recurring(e), "high", "Recurring source/month totals checked against sufficient LOE deposit references.")


@question("Q31")
def q31(e):
    if contains(str(e.maa), e.rules["mortgage_keywords"]):
        value, level = True, "high"
    else:
        credit = e.docs.get("credit_report") or {}
        lines = credit.get("tradelines") or credit.get("accounts") or []
        mortgage_lines = [line for line in lines if isinstance(line, dict) and contains(line.get("type"), e.rules["mortgage_type_keywords"])]
        if any(line.get("servicer") and not contains(line["servicer"], e.rules["own_servicer_keywords"]) for line in mortgage_lines):
            value, level = True, "medium"
        elif any(not line.get("servicer") for line in mortgage_lines):
            value, level = None, "default"
        else:
            value, level = False, "medium" if credit else "default"
    e.answer("Q31", value, level, "Other-mortgage evidence checked; credit is obtained internally, never requested from the borrower.")


def address(e, value):
    return " ".join(e.rules["address_abbreviations"].get(part, part) for part in norm(value).split())


@question("Q32")
def q32(e):
    for source, level in ((e.maa, "high"), (e.msp.get("dlq1") or {}, "medium")):
        mailing, property_address = source.get("mailing_address"), source.get("property_address")
        if contains(mailing, e.rules["same_address_keywords"]):
            e.answer("Q32", False, level, "Mailing address explicitly same as property address.")
            return
        if mailing and property_address:
            e.answer("Q32", address(e, mailing) != address(e, property_address), level, "Normalized mailing and property addresses compared.")
            return
    e.answer("Q32", None, "default", "Both application and MSP address pairs are unavailable.")


@question("Q33")
def q33(e):
    haz = e.msp.get("haz1") or {}
    expiry = parse_date(haz.get("policy_expiry_date"))
    valid = expiry is not None and expiry >= e.now.date() and haz.get("policy_current") is True
    e.answer("Q33", valid, "high" if haz else "default", "MSP HAZ1 expiry and policy-current flag compared with evaluation day.")


@question("Q34")
def q34(e):
    ana = e.msp.get("ana1") or {}
    valid = (number(ana.get("escrow_payment_amount")) or 0) > 0 and ana.get("tax_bill_on_file") is True
    e.answer("Q34", valid, "high" if ana else "default", "MSP ANA1 positive escrow payment and tax-bill flag checked.")


@question("Q35")
def q35(e):
    if not e.policy.get("credit_required"):
        e.answer("Q35", None, "high", "Not applicable - not USDA", not_applicable=True)
        return
    credit = e.docs.get("credit_report") or {}
    # No report date exists in the supplied seed. Never substitute extracted_at.
    report_date, cutoff = parse_date(credit.get("report_date")), parse_date(e.dates.get("review_date_minus_90"))
    if report_date is None or cutoff is None or report_date < cutoff:
        e.answer("Q35", None, "default", "No dated, in-window internal credit report.", stip_key="credit_missing")
        return
    accounts = number(credit.get("total_accounts"))
    balance = number(credit.get("total_balance"))
    value = None
    if accounts is not None and balance is not None:
        balances = [number(credit.get(k)) for k in ("total_balance", "mortgage_balance", "total_debt") if credit.get(k) is not None]
        if accounts > 0:
            value = False
        elif accounts == 0 and all(v == 0 for v in balances):
            value = True
    e.answer("Q35", value, "high" if value is not None else "default", "In-window credit account counts and balances checked.", stip_key="credit_missing" if value is None else None)


@question("Q36")
def q36(e):
    concerns = [key for key, raised in e.flags.items() if raised is True and
                (key in e.rules["authenticity_flags"] or contains(key.replace("_", " "), e.rules["authenticity_flag_keywords"]))]
    e.answer("Q36", not bool(concerns), "high" if e.flags else "default",
             "Authenticity concern flags: " + ", ".join(concerns) if concerns else "No authenticity concern flags found.")


@question("CALC_Q1")
def calc_q1(e):
    value = parse_date((e.msp.get("foreclosure") or {}).get("sale_date")) is not None
    e.answer("CALC_Q1", value, "high", "MSP foreclosure sale date exists." if value else "No FC date - use review_date + 1 year as proxy")


@question("CALC_Q2")
def calc_q2(e):
    e.answer("CALC_Q2", e.investor in e.rules["gse_investors"] if e.investor else None, "high" if e.investor else "default", "DLQ1 investor type checked.")


@question("CALC_Q3")
def calc_q3(e):
    state = (e.msp.get("dlq1") or {}).get("property_state")
    e.answer("CALC_Q3", state in e.rules["calculator_states"] if state else None, "high" if state else "default", "DLQ1 property state checked.")


@question("CALC_Q4")
def calc_q4(e):
    value, level = parse_date((e.msp.get("foreclosure") or {}).get("sale_date")), "high"
    if not value:
        review = parse_date(e.dates.get("review_start_date"))
        value, level = review + timedelta(days=e.rules["thresholds"]["proxy_sale_days"]) if review else None, "inferred"
    e.answer("CALC_Q4", value.isoformat() if value else None, level if value else "default",
             "MSP foreclosure sale date." if level == "high" else "Proxy derived from review_start_date plus configured days." if value else "No sale date or review_start_date is available.")


@question("verdict")
def verdict(e):
    report = e.report
    if report["stip_count"]:
        e.outcome = "incomplete"
    else:
        e.outcome = "complete"


@node("retention.manual_result")
def manual_result(state, deps):
    """Acknowledging a manual review retains the original non-complete verdict."""
    return {"outcome": "incomplete" if state["context"]["reviewed_status"] == "Facially Incomplete" else "denied",
            "detail": "Manual review acknowledged; original verdict and document requirements retained."}