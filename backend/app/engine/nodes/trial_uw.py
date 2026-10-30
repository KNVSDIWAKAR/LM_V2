"""Process 3 · Trial Underwriting.

Ingest the Facially Complete retention result → check the package → investor constraints →
calculate income / payment / escrow from MSP and the extracted documents → validate the
payment terms of every configured plan option → write the Trial Plan package to trial_plans
→ the Human Underwriter approves one plan (Ready) or rejects (Declined, escalated to Onshore).

Every finding records the value it used and where it came from. A missing value is never
replaced by a default: it holds the case or is flagged for the underwriter.
"""

from copy import deepcopy
from datetime import date, timedelta

from sqlalchemy import select

from ... import models
from ..registry import node
from ..trial_support import add_months, as_float, plan_out, supersede_open_proposals


def _finding(check: str, result: str, detail: str, **extra) -> dict:
    return {"check": check, "result": result, "detail": detail, "group": "trial_uw", **extra}


def _money(value: float | None) -> str:
    return "not recorded" if value is None else f"${value:,.2f}"


def amortized_payment(principal: float, rate_pct: float, months: int) -> float:
    """Standard fixed-rate amortization: P · r / (1 − (1 + r)^−n), r monthly."""
    r = rate_pct / 100 / 12
    if r == 0:
        return round(principal / months, 2)
    return round(principal * r / (1 - (1 + r) ** -months), 2)


def first_due_date(evaluated: date, lead_days: int) -> date:
    """The 1st of the first month that is at least `lead_days` after the evaluation date."""
    due = add_months(evaluated.replace(day=1), 1)
    while (due - evaluated).days < lead_days:
        due = add_months(due, 1)
    return due


def _latest_retention_report(db, loan_id: str) -> dict | None:
    run = db.scalar(
        select(models.AgentRun)
        .where(models.AgentRun.loan_id == loan_id, models.AgentRun.stage_no == 2, models.AgentRun.status == "completed")
        .order_by(models.AgentRun.finished_at.desc())
        .limit(1)
    )
    if run is None:
        return None
    report = (run.output or {}).get("report") or {}
    return {
        "agent_run_id": run.id,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "verdict": (run.output or {}).get("status"),
        "stip_count": report.get("stip_count"),
        "overall_confidence": report.get("overall_confidence"),
        "answers": [{"question_id": a.get("question_id"), "answer": a.get("answer"), "result": a.get("result")} for a in report.get("answers", [])],
    }


def _finish(state: dict, context: dict, findings: list, outcome: str, detail: str, **extra) -> dict:
    return {"outcome": outcome, "context": context, "findings": findings, "detail": detail, **extra}


@node("trial_uw.load_case")
def load_case(state: dict, deps) -> dict:
    rules = deps.rules["trial_uw"]
    msp = deps.db.get(models.Msp, state["loan_id"])
    if msp is None:
        raise LookupError(f"Loan {state['loan_id']} is not in MSP")
    stages = deps.db.get(models.LmStages, state["loan_id"])
    required = rules["entry"]["required_retention_status"]
    if stages is None or stages.retention_eligibility_status != required:
        raise ValueError(f"Trial UW only processes cases Retention forwarded as {required}")

    extracted = deps.db.get(models.ExtractedData, state["loan_id"])
    retention = _latest_retention_report(deps.db, msp.loan_id)
    case = {
        "loan_id": msp.loan_id,
        "borrower_name": msp.borrower_name,
        "documents": {t: getattr(extracted, t) if extracted else None for t in models.DOCUMENT_TYPES},
        "dlq1": msp.dlq1,
        "ana1": msp.ana1,
        "lmt1": msp.lmt1,
        "usr2": msp.usr2,
        "evaluation_date": deps.now.date().isoformat(),
    }
    findings = [
        _finding("Retention forwarded", "pass", f"Retention Eligibility is {required}", source="lm_stages.retention_eligibility_status"),
        _finding(
            "Retention report",
            "pass" if retention else "neutral",
            f"Retention run {retention['agent_run_id']}: {retention['verdict']}, {retention['stip_count']} stip(s)"
            if retention
            else "No saved retention run report for this loan (status was imported); underwriting uses MSP and extracted documents",
            source="agent_runs (stage 2)",
        ),
    ]
    return {
        "context": {"case": case, "retention": retention, "msp": {"loan_id": msp.loan_id, "borrower_name": msp.borrower_name}},
        "findings": findings,
        "detail": f"Loan {msp.loan_id} ingested from Retention ({required})",
    }


@node("trial_uw.check_documents")
def check_documents(state: dict, deps) -> dict:
    rules = deps.rules["trial_uw"]["documents"]
    context = deepcopy(state["context"])
    findings = list(state["findings"])
    docs = context["case"]["documents"]
    missing = []
    for doc in rules["required"]:
        value = docs.get(doc)
        label = models.DOCUMENT_TYPES.get(doc, doc)
        if doc == "paystubs":
            count = len([p for p in value or [] if isinstance(p, dict) and p])
            ok = count >= rules["minimum_paystubs"]
            findings.append(_finding(label, "pass" if ok else "fail", f"{count} paystub(s); minimum {rules['minimum_paystubs']}", document=doc))
        else:
            ok = bool(value)
            findings.append(_finding(label, "pass" if ok else "fail", "On file" if ok else "Missing", document=doc))
        if not ok:
            missing.append(label)
    if missing:
        return _finish(state, context, findings, "hold_docs", f"Hold — missing {', '.join(missing)}")
    return _finish(state, context, findings, "pass", "Underwriting package complete")


@node("trial_uw.check_eligibility")
def check_eligibility(state: dict, deps) -> dict:
    rules = deps.rules["trial_uw"]
    context = deepcopy(state["context"])
    findings = list(state["findings"])
    case = context["case"]
    dlq1 = case["dlq1"] or {}

    investor = dlq1.get("investor_type")
    eligible = rules["investor"]["eligible"]
    if investor not in eligible:
        findings.append(_finding("Investor constraint", "fail", f"Investor {investor or 'not recorded'} is not eligible ({', '.join(eligible)})",
                                 value=investor, source="MSP DLQ1.investor_type"))
        return _finish(state, context, findings, "declined", f"Declined — investor {investor or 'not recorded'} not eligible for a trial plan")
    findings.append(_finding("Investor constraint", "pass", f"Investor {investor} is eligible", value=investor, source="MSP DLQ1.investor_type"))

    upb = as_float(dlq1.get("upb_balance"))
    if upb is None or upb <= 0:
        findings.append(_finding("Unpaid principal balance", "fail", f"UPB is {_money(upb)}; nothing to modify", value=upb, source="MSP DLQ1.upb_balance"))
        return _finish(state, context, findings, "declined", "Declined — loan has no unpaid principal balance")
    findings.append(_finding("Unpaid principal balance", "pass", f"UPB {_money(upb)}", value=upb, source="MSP DLQ1.upb_balance"))

    statuses = {s.lower() for s in rules["approval_hold_statuses"]}
    lmt1, usr2 = case["lmt1"] or {}, case["usr2"] or {}
    for source, value in (("MSP LMT1.mod_status", lmt1.get("mod_status")), ("MSP LMT1.status_description", lmt1.get("status_description")),
                          ("MSP USR2.status", usr2.get("status"))):
        if value and str(value).strip().lower() in statuses:
            findings.append(_finding("Approval status", "review", f"{value} — an approval is still outstanding", value=value, source=source))
            return _finish(state, context, findings, "hold_approval", f"Hold — approval pending ({value})")
    findings.append(_finding("Approval status", "pass", "No outstanding approval on LMT1 / USR2", source="MSP LMT1, USR2"))

    months = dlq1.get("months_delinquent")
    findings.append(_finding("Delinquency", "neutral", f"{months} month(s) delinquent" if months is not None else "Months delinquent not recorded",
                             value=months, source="MSP DLQ1.months_delinquent"))
    return _finish(state, context, findings, "pass", f"{investor} loan eligible for trial underwriting")


def _paystub_monthly_wages(paystubs: list, periods: dict) -> tuple[float | None, list[str]]:
    """Average gross per pay period per employee × periods per year / 12, summed over employees."""
    by_employee: dict[str, list[tuple[float, int]]] = {}
    unknown = []
    for stub in paystubs or []:
        gross, freq = as_float(stub.get("gross_current_period")), stub.get("pay_frequency")
        if gross is None or gross <= 0:
            continue
        if freq not in periods:
            unknown.append(str(freq))
            continue
        by_employee.setdefault(str(stub.get("employee_name", "")).strip().lower(), []).append((gross, periods[freq]))
    if not by_employee:
        return None, unknown
    total = sum(sum(g for g, _ in rows) / len(rows) * rows[0][1] / 12 for rows in by_employee.values())
    return round(total, 2), unknown


@node("trial_uw.calculate_terms")
def calculate_terms(state: dict, deps) -> dict:
    rules = deps.rules["trial_uw"]
    context = deepcopy(state["context"])
    findings = list(state["findings"])
    case = context["case"]
    docs = case["documents"]
    application = docs.get("application_form") or {}

    sources = [s for s in application.get("income_sources") or [] if (as_float(s.get("gross_monthly_amount")) or 0) > 0]
    income = sum(as_float(s["gross_monthly_amount"]) for s in sources)
    other = as_float(application.get("other_income_amount")) or 0
    if rules["income"]["include_other_income"] and other > 0:
        income += other
    stub_wages, unknown = _paystub_monthly_wages(docs.get("paystubs"), rules["income"]["paystub_periods_per_year"])
    income_source = "MAA income_sources" + (" + other_income_amount" if rules["income"]["include_other_income"] and other > 0 else "")
    if income <= 0 and stub_wages:
        income, income_source = stub_wages, "paystubs (gross per period × periods per year / 12)"
    if income <= 0:
        findings.append(_finding("Gross monthly income", "fail", "No positive income on the MAA or paystubs", source="MAA, paystubs"))
        return _finish(state, context, findings, "hold_docs", "Hold — no verifiable income")
    income = round(income, 2)
    findings.append(_finding("Gross monthly income", "pass", f"{_money(income)} from {income_source}", value=income, source=income_source))

    wage_sources = sum(as_float(s["gross_monthly_amount"]) for s in sources if str(s.get("type", "")).lower().startswith("gross wages"))
    if unknown:
        findings.append(_finding("Paystub income check", "review", f"Unrecognised pay frequency: {', '.join(sorted(set(unknown)))}", source="paystubs"))
    elif stub_wages and wage_sources:
        variance = abs(stub_wages - wage_sources) / wage_sources * 100
        ok = variance <= rules["income"]["paystub_tolerance_pct"]
        findings.append(_finding("Paystub income check", "pass" if ok else "review",
                                 f"Paystub wages {_money(stub_wages)}/mo vs MAA wages {_money(wage_sources)}/mo ({variance:.1f}% variance, "
                                 f"tolerance {rules['income']['paystub_tolerance_pct']}%)", value=round(variance, 1), source="paystubs vs MAA"))
    else:
        findings.append(_finding("Paystub income check", "neutral", "No wage source on both the MAA and the paystubs to compare", source="paystubs vs MAA"))

    doc_name, field = rules["current_payment_field"].split(".", 1)
    current = as_float((docs.get(doc_name) or {}).get(field))
    findings.append(_finding("Current mortgage payment", "pass" if current else "review",
                             f"{_money(current)}/mo" if current else "Not recorded; payment change cannot be measured",
                             value=current, source=rules["current_payment_field"]))

    ana1 = case["ana1"]
    escrow = as_float((ana1 or {}).get("escrow_payment_amount"))
    if ana1 is None or escrow is None:
        findings.append(_finding("Escrow payment", "fail", "MSP ANA1 escrow analysis is not on file", source="MSP ANA1.escrow_payment_amount"))
        return _finish(state, context, findings, "hold_docs", "Hold — escrow analysis (ANA1) missing")
    findings.append(_finding("Escrow payment", "pass", f"{_money(escrow)}/mo", value=escrow, source="MSP ANA1.escrow_payment_amount"))

    dlq1 = case["dlq1"]
    investor = dlq1["investor_type"]
    rate = as_float(rules["investor"]["posted_rate_pct"].get(investor))
    if rate is None:
        findings.append(_finding("Modification rate", "fail", f"No posted modification rate configured for {investor}", source="rules investor.posted_rate_pct"))
        return _finish(state, context, findings, "hold_docs", f"Hold — no posted rate configured for {investor}")
    findings.append(_finding("Modification rate", "pass", f"{rate:.3f}% posted rate for {investor}", value=rate, source="rules investor.posted_rate_pct"))

    context["terms"] = {
        "gross_monthly_income": income,
        "income_source": income_source,
        "paystub_monthly_wages": stub_wages,
        "current_payment": current,
        "escrow_payment": escrow,
        "escrow_current": (ana1 or {}).get("escrow_current"),
        "upb_balance": as_float(dlq1["upb_balance"]),
        "investor_type": investor,
        "interest_rate_pct": rate,
    }
    return _finish(state, context, findings, "pass", f"Income {_money(income)}, escrow {_money(escrow)}, rate {rate:.3f}%")


@node("trial_uw.validate_payment_terms")
def validate_payment_terms(state: dict, deps) -> dict:
    rules = deps.rules["trial_uw"]
    context = deepcopy(state["context"])
    findings = list(state["findings"])
    terms = context["terms"]
    income, current, escrow = terms["gross_monthly_income"], terms["current_payment"], terms["escrow_payment"]
    rate, upb = terms["interest_rate_pct"], terms["upb_balance"]
    limits = rules["terms"]
    max_ratio = rules["affordability"]["max_housing_ratio_pct"]
    target = rules["affordability"]["target_payment_reduction_pct"]

    rate_ok = limits["min_rate_pct"] <= rate <= limits["max_rate_pct"]
    findings.append(_finding("Rate consistency", "pass" if rate_ok else "review",
                             f"{rate:.3f}% within {limits['min_rate_pct']}–{limits['max_rate_pct']}%" if rate_ok
                             else f"{rate:.3f}% is outside {limits['min_rate_pct']}–{limits['max_rate_pct']}%", value=rate))
    escrow_ok = escrow > 0 and (terms["escrow_current"] is True or not rules["escrow"]["require_current"])
    findings.append(_finding("Escrow consistency", "pass" if escrow_ok else "review",
                             f"Escrow {_money(escrow)}/mo, account {'current' if terms['escrow_current'] else 'not current'}",
                             value=escrow, source="MSP ANA1"))

    options = []
    for n, option in enumerate(rules["plan_options"], 1):
        months = int(option["amortization_months"])
        codes = []
        term_ok = 0 < months <= limits["max_amortization_months"]
        pi = amortized_payment(upb, rate, months)
        payment = round(pi + escrow, 2)
        ratio = round(payment / income * 100, 2)
        change = round((payment - current) / current * 100, 2) if current else None
        affordable = ratio <= max_ratio
        codes.append({"code": "TU-AFF-OK" if affordable else "TU-AFF-HIGH",
                      "text": f"Housing ratio {ratio:.1f}% {'≤' if affordable else '>'} {max_ratio}% of gross income"})
        if change is None:
            codes.append({"code": "TU-PMT-UNKNOWN", "text": "Current payment not recorded"})
        elif change > 0:
            codes.append({"code": "TU-PMT-INCREASE", "text": f"Payment increases {change:.1f}% over the current {_money(current)}"})
        elif -change >= target:
            codes.append({"code": "TU-PMT-REDUCED", "text": f"Payment reduced {-change:.1f}% (target {target}%)"})
        else:
            codes.append({"code": "TU-PMT-BELOW-TARGET", "text": f"Payment reduced {-change:.1f}%, below the {target}% target"})
        if not term_ok:
            codes.append({"code": "TU-TERM-INVALID", "text": f"{months}-month amortization exceeds {limits['max_amortization_months']}"})
        if not escrow_ok:
            codes.append({"code": "TU-ESC-REVIEW", "text": "Escrow must be reviewed before the trial starts"})
        flagged = not affordable or (change is not None and change > 0) or not term_ok or change is None
        findings.append(_finding(f"Payment terms · {option['plan_name']}", "review" if flagged else "pass",
                                 f"P&I {_money(pi)} + escrow {_money(escrow)} = {_money(payment)}/mo; housing ratio {ratio:.1f}%"
                                 + (f"; change {change:+.1f}% vs current" if change is not None else ""),
                                 value=payment, reason_codes=[c["code"] for c in codes]))
        options.append({
            **option, "option_no": n, "principal_interest": pi, "trial_payment": payment, "housing_ratio": ratio,
            "payment_change_pct": change, "affordable": affordable and term_ok, "reason_codes": codes,
            "calculation": {
                "formula": "P&I = UPB × r / (1 − (1 + r)^−n), r = rate / 12; trial payment = P&I + escrow",
                "upb_balance": upb, "interest_rate_pct": rate, "amortization_months": months,
                "escrow_payment": escrow, "gross_monthly_income": income, "income_source": terms["income_source"],
                "current_payment": current, "max_housing_ratio_pct": max_ratio, "target_payment_reduction_pct": target,
                "rules_version": state.get("rules_version"),
            },
        })
    context["options"] = options
    if not any(o["affordable"] for o in options):
        return _finish(state, context, findings, "declined",
                       f"Declined — no plan option is within the {max_ratio}% housing ratio on {_money(income)} income")
    return _finish(state, context, findings, "pass", f"{sum(o['affordable'] for o in options)} of {len(options)} option(s) within the {max_ratio}% housing ratio")


@node("trial_uw.prepare_trial_plan")
def prepare_trial_plan(state: dict, deps) -> dict:
    rules = deps.rules["trial_uw"]
    context = deepcopy(state["context"])
    findings = list(state["findings"])
    loan_id, terms = state["loan_id"], context["terms"]
    evaluated = date.fromisoformat(context["case"]["evaluation_date"])
    first_due = first_due_date(evaluated, rules["schedule"]["first_due_min_lead_days"])
    grace = int(rules["schedule"]["grace_period_days"])
    run_tag = (state.get("agent_run_id") or "manual").removeprefix("ar-")

    supersede_open_proposals(deps.db, loan_id, deps.now)
    plans = []
    for option in context["options"]:
        if not option["affordable"]:
            continue  # an option outside the limits is reported in the findings, never proposed
        plan = models.TrialPlan(
            id=f"TP-{loan_id}-{run_tag}-{option['option_no']}",
            loan_id=loan_id, agent_run_id=state.get("agent_run_id"), option_no=option["option_no"],
            plan_type=option["plan_type"], plan_name=option["plan_name"], status="proposed",
            trial_payment=option["trial_payment"], principal_interest=option["principal_interest"],
            escrow_payment=terms["escrow_payment"], interest_rate_pct=terms["interest_rate_pct"],
            amortization_months=option["amortization_months"], trial_duration_months=option["trial_duration_months"],
            grace_period_days=grace, first_due_date=first_due, upb_balance=terms["upb_balance"],
            gross_monthly_income=terms["gross_monthly_income"], current_payment=terms["current_payment"],
            housing_ratio=option["housing_ratio"], payment_change_pct=option["payment_change_pct"],
            conditions=list(rules["conditions"]), reason_codes=option["reason_codes"], calculation=option["calculation"],
            created_at=deps.now,
        )
        for k in range(option["trial_duration_months"]):
            due = add_months(first_due, k)
            plan.installments.append(models.TrialInstallment(
                installment_no=k + 1, due_date=due, grace_end_date=due + timedelta(days=grace),
                expected_amount=option["trial_payment"], status="pending"))
        deps.db.add(plan)
        plans.append(plan)
    deps.db.flush()

    context["plans"] = [plan_out(p) for p in plans]
    for p in context["plans"]:
        findings.append(_finding(f"Trial plan · {p['plan_name']}", "review", f"{_money(p['trial_payment'])}/mo × {p['trial_duration_months']} from "
                                 f"{p['first_due_date']}, {grace}-day grace — awaiting Human Underwriter", plan_id=p["plan_id"]))
    summary = "; ".join(f"{p['plan_name']} {_money(p['trial_payment'])}/mo" for p in context["plans"])
    return {
        "context": context,
        "findings": findings,
        "review_reason": f"Approve one trial plan: {summary}",
        "detail": f"{len(plans)} trial plan(s) proposed, first payment {first_due.isoformat()}",
    }
