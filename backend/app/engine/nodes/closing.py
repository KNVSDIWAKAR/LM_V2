"""Process 5 · Final Underwriting & Closing (one stage, one page).

Final Underwriting: TASK1/MES1 holds → SCRA rate → Neighbourhood document → LSMR terms →
LMT3 closing-code dates → handoff readiness → route (hold/review → Team Lead) → MOD QC →
Human Sign-off. Then the five Final Mod checks, evaluated exactly as configured in
rules.yaml (skills, requires, tags, facts, first-match verdict rules).

Every value is read from the database at the time of the check. MOD QC flags, the sign-off
time and the county recording date come from closing_qc, which people fill in.
"""

import re
from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime

from sqlalchemy import select

from ... import models
from ..registry import node
from ..trial_support import approved_plan, as_float

UW_ORDER = ("hold_tasks", "scra", "neighbourhood", "lsmr_terms", "lmt3_dates", "handoff")
UW_LABELS = {
    "hold_tasks": "TASK1 / MES1 hold tasks",
    "scra": "SCRA rate threshold",
    "neighbourhood": "Neighbourhood document",
    "lsmr_terms": "LSMR modification terms",
    "lmt3_dates": "LMT3 closing-code dates",
    "handoff": "Underwriting handoff",
}


def _uw(state: dict, deps, key: str, outcome: str, detail: str, **extra) -> dict:
    """Record one Final Underwriting check and route on its outcome."""
    context = deepcopy(state["context"])
    findings = list(state.get("findings", []))
    context.setdefault("uw_results", {})[key] = {"outcome": outcome, "detail": detail, **extra}
    result = {"pass": "pass", "hold": "fail", "review": "review"}[outcome]
    findings.append({"check": UW_LABELS[key], "result": result, "outcome": outcome, "detail": detail, "group": "final_underwriting", **extra})
    return {"outcome": outcome, "context": context, "findings": findings, "detail": f"{UW_LABELS[key]}: {detail}"}


def _norm(text) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


@node("closing.load_case")
def load_case(state: dict, deps) -> dict:
    rules = deps.rules["final_underwriting"]
    msp = deps.db.get(models.Msp, state["loan_id"])
    if msp is None:
        raise LookupError(f"Loan {state['loan_id']} is not in MSP")
    stages = deps.db.get(models.LmStages, state["loan_id"])
    required = rules["entry"]["required_trial_monitoring_status"]
    if stages is None or stages.trial_monitoring_status != required:
        raise ValueError(f"Final Underwriting only runs for loans whose Trial Monitoring is {required}")
    extracted = deps.db.get(models.ExtractedData, msp.loan_id)
    plan = approved_plan(deps.db, msp.loan_id)
    context = {
        "msp": {"loan_id": msp.loan_id, "borrower_name": msp.borrower_name, "coborrower_name": msp.coborrower_name,
                "property_address": msp.property_address},
        "screens": {"task1": msp.task1, "mes1": msp.mes1, "lsmr": msp.lsmr, "lmt3": msp.lmt3, "dlq1": msp.dlq1},
        "neighbourhood_document": extracted.neighbourhood_document if extracted else None,
        "approved_plan": {"plan_id": plan.id, "plan_name": plan.plan_name, "trial_payment": plan.trial_payment,
                          "interest_rate_pct": plan.interest_rate_pct, "amortization_months": plan.amortization_months} if plan else None,
        "evaluation_date": deps.now.date().isoformat(),
        "uw_results": {},
    }
    findings = [{"check": "Trial Monitoring", "result": "pass", "detail": f"Stage 4 status is {required}", "group": "final_underwriting"}]
    return {"context": context, "findings": findings, "detail": f"Loan {msp.loan_id} loaded for Final Underwriting"}


@node("closing.check_hold_tasks")
def check_hold_tasks(state: dict, deps) -> dict:
    rules = deps.rules["final_underwriting"]["hold_tasks"]
    screens = state["context"]["screens"]
    loaded = {src: screens.get(src.lower()) for src in rules["task_sources"]}
    if all(v is None for v in loaded.values()):
        return _uw(state, deps, "hold_tasks", "review", f"{' / '.join(rules['task_sources'])} not loaded from MSP; required tasks cannot be verified")
    watched = set(rules["task_ids"])
    found = [{**t, "source": src} for src, screen in loaded.items() for t in (screen or {}).get("tasks", []) if t.get("task_id") in watched]
    held = [t for t in found if t.get("status") in rules["hold_statuses"]]
    unknown = [t for t in found if t.get("status") not in (*rules["hold_statuses"], *rules["completed_statuses"])]
    tasks = [{"task_id": t["task_id"], "status": t.get("status"), "source": t["source"]} for t in found]
    if held:
        return _uw(state, deps, "hold_tasks", "hold", "Open tasks: " + ", ".join(f"{t['task_id']} ({t['status']}, {t['source']})" for t in held), tasks=tasks)
    if unknown:
        return _uw(state, deps, "hold_tasks", "review", "Unrecognised task status: " + ", ".join(f"{t['task_id']}={t.get('status')}" for t in unknown), tasks=tasks)
    detail = f"{len(found)} required task(s) found, all completed" if found else "No required task is open on TASK1 / MES1"
    return _uw(state, deps, "hold_tasks", "pass", detail, tasks=tasks)


@node("closing.check_scra")
def check_scra(state: dict, deps) -> dict:
    rules = deps.rules["final_underwriting"]["scra"]
    screens = state["context"]["screens"]
    rate = as_float((screens.get("lsmr") or {}).get("current_interest_rate"))
    source = "MSP LSMR.current_interest_rate"
    if rate is None:
        rate, source = as_float((screens.get("dlq1") or {}).get("interest_rate")), "MSP DLQ1.interest_rate"
    threshold = float(rules["interest_rate_threshold"])
    if rate is None:
        return _uw(state, deps, "scra", "review", "Current interest rate not recorded on LSMR or DLQ1", source=source)
    if rate >= threshold:
        return _uw(state, deps, "scra", "review", f"Current rate {rate:.3f}% ≥ {threshold:.2f}% SCRA threshold — {rules['action_at_or_above_threshold']}"
                   + ("" if rules["legal_search"] else " (no legal search performed)"), value=rate, source=source)
    return _uw(state, deps, "scra", "pass", f"Current rate {rate:.3f}% below the {threshold:.2f}% SCRA threshold", value=rate, source=source)


@node("closing.check_neighbourhood")
def check_neighbourhood(state: dict, deps) -> dict:
    rules = deps.rules["final_underwriting"]["neighbourhood"]
    context = state["context"]
    doc = context["neighbourhood_document"]
    if not doc:
        return _uw(state, deps, "neighbourhood", "hold", "Neighbourhood document not on file", document="neighbourhood_document")
    missing = [f for f in rules["required_fields"] if doc.get(f) in (None, "")]
    if missing:
        return _uw(state, deps, "neighbourhood", "review", f"Missing field(s): {', '.join(missing)}", document="neighbourhood_document")
    try:
        doc_date = datetime.strptime(doc["document_date"], rules["date_format"]).date()
    except ValueError:
        return _uw(state, deps, "neighbourhood", "review", f"document_date {doc['document_date']!r} is not {rules['date_format']}")
    age = (date.fromisoformat(context["evaluation_date"]) - doc_date).days
    if age > rules["max_age_days"] or age < 0:
        return _uw(state, deps, "neighbourhood", "hold", f"Document dated {doc_date.isoformat()} is {age} day(s) old (max {rules['max_age_days']})")
    issues = []
    if rules["compare_available_msp_identity_and_upb"]:
        names = {_norm(context["msp"]["borrower_name"]), _norm(context["msp"].get("coborrower_name"))} - {""}
        if _norm(doc["borrower_name"]) not in names:
            issues.append(f"borrower {doc['borrower_name']!r} ≠ MSP {context['msp']['borrower_name']!r}")
        if _norm(doc["property_address"]) != _norm(context["msp"]["property_address"]):
            issues.append(f"property {doc['property_address']!r} ≠ MSP {context['msp']['property_address']!r}")
        msp_upb = as_float((context["screens"].get("dlq1") or {}).get("upb_balance"))
        if msp_upb is None or abs(float(doc["upb"]) - msp_upb) > float(rules["upb_tolerance"]):
            issues.append(f"UPB ${float(doc['upb']):,.2f} ≠ MSP DLQ1 {'$' + format(msp_upb, ',.2f') if msp_upb is not None else 'not recorded'}")
    if issues:
        return _uw(state, deps, "neighbourhood", "review", "; ".join(issues), document="neighbourhood_document")
    claims = doc.get("prior_partial_claim_amounts") or []
    return _uw(state, deps, "neighbourhood", "pass", f"Dated {doc_date.isoformat()} ({age} days); identity and UPB match MSP; "
               f"{len(claims)} prior partial claim(s) totalling ${sum(claims):,.2f}", document="neighbourhood_document")


@node("closing.check_lsmr_terms")
def check_lsmr_terms(state: dict, deps) -> dict:
    rules = deps.rules["final_underwriting"]["lsmr_terms"]
    lsmr = state["context"]["screens"].get("lsmr")
    if lsmr is None:
        return _uw(state, deps, "lsmr_terms", "review", "MSP LSMR screen not loaded; new modification terms unavailable")
    problems = [f"{f} missing" for f in rules["required_fields"] if lsmr.get(f) is None]
    problems += [f"{f} must be positive" for f in rules["positive_numeric_fields"] if lsmr.get(f) is not None and not (as_float(lsmr[f]) or 0) > 0]
    term = lsmr.get("new_term_months")
    if rules["new_term_months_must_be_positive_integer"] and term is not None and not (isinstance(term, int) and not isinstance(term, bool) and term > 0):
        problems.append("new_term_months must be a positive whole number")
    terms = {f: lsmr.get(f) for f in rules["required_fields"]}
    if problems:
        return _uw(state, deps, "lsmr_terms", "review", "; ".join(problems), terms=terms)
    plan = state["context"].get("approved_plan")
    return _uw(state, deps, "lsmr_terms", "pass",
               f"{lsmr['new_interest_rate']}% for {term} months on ${float(lsmr['new_principal_balance']):,.2f}, payment ${float(lsmr['new_payment_amount']):,.2f}"
               + (f" (approved trial payment ${plan['trial_payment']:,.2f}; formula not recalculated)" if plan else ""), terms=terms)


@node("closing.check_lmt3_dates")
def check_lmt3_dates(state: dict, deps) -> dict:
    rules = deps.rules["final_underwriting"]["lmt3"]
    lmt3 = state["context"]["screens"].get("lmt3") or {}
    keys = rules["date_keys"]
    missing = [k for k in keys if not lmt3.get(k)]
    if missing:
        return _uw(state, deps, "lmt3_dates", "review", f"LMT3 missing {', '.join(missing)}")
    try:
        dates = {k: date.fromisoformat(str(lmt3[k])) for k in keys}
    except ValueError as err:
        return _uw(state, deps, "lmt3_dates", "review", f"Unreadable LMT3 date: {err}")
    problems = [f"{k} {d.isoformat()} is a {d.strftime('%A')}" for k, d in dates.items() if d.weekday() not in rules["working_weekdays"]]
    for a, b in zip(keys, keys[1:]):
        if dates[b] < dates[a] or (rules["strict_sequence"] and dates[b] == dates[a]):
            problems.append(f"{b} {dates[b].isoformat()} is not after {a} {dates[a].isoformat()}")
    shown = {k: d.isoformat() for k, d in dates.items()}
    if problems:
        return _uw(state, deps, "lmt3_dates", "review", "; ".join(problems), dates=shown)
    return _uw(state, deps, "lmt3_dates", "pass", " < ".join(f"{k.split('_')[0].upper()} {d}" for k, d in shown.items())
               + ("" if rules["update_msp"] else " (MSP not updated)"), dates=shown)


@node("closing.check_underwriting_handoff")
def check_underwriting_handoff(state: dict, deps) -> dict:
    rules = deps.rules["final_underwriting"]["handoff"]
    results = state["context"]["uw_results"]
    open_items = [UW_LABELS[k] for k in UW_ORDER[:-1] if results.get(k, {}).get("outcome") != "pass"]
    handoff = {"mir": rules["mir_mode"], "escalation": rules["escalation_mode"], "open_items": open_items}
    if open_items:
        update = _uw(state, deps, "handoff", "review", f"Not ready — {', '.join(open_items)}. Team Lead escalation: {rules['escalation_mode']}", **handoff)
    else:
        update = _uw(state, deps, "handoff", "pass", f"Ready for MOD QC. Plan to MIR: {rules['mir_mode']}", **handoff)
    update["context"]["handoff"] = handoff
    return update


@node("closing.route_underwriting")
def route_underwriting(state: dict, deps) -> dict:
    results = state["context"]["uw_results"]
    outcomes = [results[k]["outcome"] for k in UW_ORDER if k in results]
    outcome = "hold" if "hold" in outcomes else "review" if "review" in outcomes else "pass"
    issues = "; ".join(f"{UW_LABELS[k]}: {results[k]['detail']}" for k in UW_ORDER if k in results and results[k]["outcome"] != "pass" and k != "handoff")
    reason = (f"Underwriting {outcome}: {issues}" if outcome != "pass"
              else "Complete MOD QC: confirm borrower & property match the Note, principal matches MSP, and new terms match the approved plan")
    return {"outcome": outcome, "review_reason": reason,
            "detail": f"{outcomes.count('pass')} of {len(outcomes)} underwriting checks passed" + (f" — {outcome}" if outcome != "pass" else "")}


# --------------------------------------------------------------------------- #
# Final Mod checks: the legacy five-check configuration, evaluated from rules.yaml
# --------------------------------------------------------------------------- #


def final_mod_inputs(db, loan_id: str, rules: dict, today: date) -> dict:
    """The legacy JSON input fields, each read from its database source (rules.inputs)."""
    stages = db.get(models.LmStages, loan_id)
    msp = db.get(models.Msp, loan_id)
    qc = db.get(models.ClosingQc, loan_id)
    stage4 = stages.trial_monitoring_status if stages else None
    approved_at = qc.mod_approved_at if qc else None
    return {
        "trial_outcome": rules["trial_outcome_from_stage4"].get(stage4, "in_progress"),
        "trial_monitoring_status": stage4,
        **{flag: getattr(qc, flag) if qc else None for flag in models.QC_FLAGS},
        "state": (msp.dlq1 or {}).get("property_state") if msp else None,
        "mod_approved_at": approved_at.isoformat() if approved_at else None,
        "days_since_approval": (today - approved_at.date()).days if approved_at else None,
        "recorded_date": qc.recorded_date.isoformat() if qc and qc.recorded_date else None,
    }


def _skill(skill: str, params: dict, inputs: dict, settings: dict) -> tuple[str, dict]:
    if skill == "check_trial_outcome":
        value = str(inputs.get(params["field"]) or "").lower()
        return ("pass" if value == "completed" else "flagged" if value == "broken" else "pending"), {}
    if skill == "check_flag_verified":
        value = inputs.get(params["field"])
        return ("pass" if value is True else "flagged" if value is False else "pending"), {}
    if skill == "check_recording_sla":
        state, days, recorded = inputs.get(params["state_field"]), inputs.get(params["days_field"]), inputs.get(params["recorded_field"])
        sla = int(settings["sla_days"])
        values = {"state": state or "Unknown state", "recorded_date": recorded}
        if state not in settings["county_recording_states"]:
            return "not_applicable", values
        if recorded:
            return "pass", values
        if days is None:
            return "pending", {**values, "days_left": "unknown (sign-off date not recorded)"}
        if days > sla:
            return "flagged", {**values, "days_over": days - sla}
        return "pending", {**values, "days_left": sla - days}
    raise ValueError(f"Unknown Final Mod skill {skill!r}")


def _fm(state: dict, deps, check_id: str) -> dict:
    rules = deps.rules["final_mod_closing"]
    context = deepcopy(state.get("context") or {})  # empty on a Final Mod re-run
    findings = list(state.get("findings", []))
    fm = context.get("final_mod")
    if fm is None or check_id == "trial_outcome":
        # First Final Mod check (also the re-run entry point): read the current inputs.
        today = deps.now.date()
        context.setdefault("evaluation_date", today.isoformat())
        fm = context["final_mod"] = {"inputs": final_mod_inputs(deps.db, state["loan_id"], rules, today), "checks": {}}
        findings = [f for f in findings if f.get("group") != "final_mod"]
    spec = next(c for c in rules["checks"] if c["id"] == check_id)
    unmet = [dep for dep, need in (spec.get("requires") or {}).items() if fm["checks"].get(dep, {}).get("status") != need]
    if unmet:
        status, message = "skipped", f"Skipped — requires {', '.join(unmet)} to pass."
    else:
        status, values = _skill(spec["skill"], spec["params"], fm["inputs"], rules["settings"])
        message = spec["messages"][status].format_map(defaultdict(lambda: "—", values))
    fm["checks"][check_id] = {"id": check_id, "label": spec["label"], "status": status, "message": message, "tags": spec.get("tags", [])}
    findings.append({"check": spec["label"], "result": status, "detail": message, "group": "final_mod", "check_id": check_id})
    return {"outcome": status, "context": context, "findings": findings, "detail": f"{spec['label']}: {message}"}


@node("closing.check_trial_outcome")
def check_trial_outcome(state: dict, deps) -> dict:
    return _fm(state, deps, "trial_outcome")


@node("closing.check_borrower_property")
def check_borrower_property(state: dict, deps) -> dict:
    return _fm(state, deps, "borrower_property")


@node("closing.check_principal_balance")
def check_principal_balance(state: dict, deps) -> dict:
    return _fm(state, deps, "principal_balance")


@node("closing.check_new_terms")
def check_new_terms(state: dict, deps) -> dict:
    return _fm(state, deps, "new_terms")


@node("closing.check_recording_sla")
def check_recording_sla(state: dict, deps) -> dict:
    return _fm(state, deps, "recording_sla")


def evaluate_verdict(checks: dict, rules: dict) -> tuple[str, dict]:
    """Facts from the check results, then the first verdict rule whose condition holds."""
    facts: dict = {}
    for name, spec in rules["facts"].items():
        if spec["type"] == "check_status":
            facts[name] = checks.get(spec["check"], {}).get("status")
        elif spec["type"] == "count_checks":
            facts[name] = sum(1 for c in checks.values() if spec["tag"] in c["tags"] and ("status" not in spec or c["status"] == spec["status"]))
        elif spec["type"] == "compare":
            facts[name] = _compare(facts[spec["left"]], spec["op"], facts[spec["right"]])
        else:
            raise ValueError(f"Unknown fact type {spec['type']!r}")
    for rule in rules["verdict_rules"]:
        when = rule.get("when")
        if when is None or _compare(facts.get(when["fact"]), when["op"], when["value"]):
            return rule["verdict"], facts
    raise ValueError("No verdict rule matched and there is no default rule")


def _compare(left, op: str, right) -> bool:
    ops = {"eq": lambda a, b: a == b, "ne": lambda a, b: a != b, "gt": lambda a, b: a > b, "lt": lambda a, b: a < b}
    return ops[op](left, right)


@node("closing.route_final_mod")
def route_final_mod(state: dict, deps) -> dict:
    rules = deps.rules["final_mod_closing"]
    context = deepcopy(state["context"])
    fm = context["final_mod"]
    verdict, facts = evaluate_verdict(fm["checks"], rules)
    spec = rules["verdicts"][verdict]
    fm.update(verdict=verdict, verdict_label=spec["label"], description=spec["description"], tone=spec["tone"],
              group=spec["group"], action=spec.get("action"), facts=facts)
    reason = ""
    if verdict == "human_review":
        reason = f"{spec['description']} {fm['checks']['recording_sla']['message']}"
    return {"outcome": verdict, "context": context, "review_reason": reason,
            "detail": f"{spec['label']} — {spec['description']} (QC {facts.get('qc_pass')}/{facts.get('qc_total')})"}


def underwriting_sign_off_decision(db, loan_id: str) -> models.Decision | None:
    return db.scalar(
        select(models.Decision)
        .where(models.Decision.loan_id == loan_id, models.Decision.stage_no == 5,
               models.Decision.gate == "underwriting_sign_off", models.Decision.status == "approved")
        .order_by(models.Decision.decided_at.desc())
        .limit(1)
    )
