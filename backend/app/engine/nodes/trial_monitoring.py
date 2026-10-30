"""Process 4 · Trial Monitoring.

Load the approved trial plan → match MSP DLQ1 payment_history to its installments
(amount / date / grace / tolerance, cumulative so an overpayment carries forward) → write
the installment results and one LMT note → decide: Completed (hand on to Final UW),
Within Plan / Delayed Payment (monitor again next cycle), Defaulted (Denial / Onshore), or
review when the evidence is missing or a payment was late.
"""

from copy import deepcopy
from datetime import date

from ... import models
from ..registry import node
from ..trial_support import approved_plan, as_float, plan_out


def _finding(check: str, result: str, detail: str, **extra) -> dict:
    return {"check": check, "result": result, "detail": detail, "group": "trial_monitoring", **extra}


def match_installments(installments: list[dict], payments: list[dict], today: date, tolerance: float) -> list[dict]:
    """Classify each installment from cumulative payments. Pure: same inputs, same answer.

    paid     cumulative received by grace end ≥ cumulative expected − tolerance
    late     not covered by grace end, but covered by today
    partial  grace over; some but not all of this installment received by today
    missed   grace over; nothing received for this installment by today
    pending  grace not over and not yet covered (with `past_due` when the due date has passed)
    """
    rows = sorted(((date.fromisoformat(p["payment_date"]), float(p["amount"])) for p in payments), key=lambda r: r[0])

    def received_by(day: date) -> float:
        return sum(amount for paid_on, amount in rows if paid_on <= day)

    def covered_on(required: float) -> date | None:
        total = 0.0
        for paid_on, amount in rows:
            total += amount
            if total >= required - tolerance:
                return paid_on
        return None

    out, required_before = [], 0.0
    for inst in installments:
        due, grace_end = date.fromisoformat(inst["due_date"]), date.fromisoformat(inst["grace_end_date"])
        expected = float(inst["expected_amount"])
        required = required_before + expected
        to_date = received_by(today)
        applied = round(max(0.0, min(expected, to_date - required_before)), 2)
        result = {**inst, "received_amount": applied, "received_date": None, "past_due": False}
        if received_by(grace_end) >= required - tolerance:
            result.update(status="paid", received_date=covered_on(required).isoformat())
        elif today <= grace_end:
            result.update(status="pending", past_due=today > due, received_amount=applied or None)
        elif to_date >= required - tolerance:
            result.update(status="late", received_date=covered_on(required).isoformat())
        elif applied > tolerance:
            result.update(status="partial")
        else:
            result.update(status="missed", received_amount=0.0)
        out.append(result)
        required_before = required
    return out


@node("trial_monitoring.load_case")
def load_case(state: dict, deps) -> dict:
    rules = deps.rules["trial_monitoring"]
    msp = deps.db.get(models.Msp, state["loan_id"])
    if msp is None:
        raise LookupError(f"Loan {state['loan_id']} is not in MSP")
    stages = deps.db.get(models.LmStages, state["loan_id"])
    required = rules["entry"]["required_trial_uw_status"]
    if stages is None or stages.trial_uw_status != required:
        raise ValueError(f"Trial Monitoring only runs for Trial UW {required} loans")

    context = {"msp": {"loan_id": msp.loan_id, "borrower_name": msp.borrower_name},
               "evaluation_date": deps.now.date().isoformat(), "dlq1": deepcopy(msp.dlq1)}
    plan = approved_plan(deps.db, msp.loan_id)
    if plan is None:
        findings = [_finding("Approved trial plan", "review", "Trial UW is Ready but no approved plan is recorded in trial_plans", source="trial_plans")]
        return {"outcome": "review", "context": context, "findings": findings,
                "review_reason": "No approved trial plan to monitor", "detail": "No approved trial plan on record"}
    context["plan"] = plan_out(plan)
    findings = [_finding("Approved trial plan", "pass", f"{plan.plan_name}: ${plan.trial_payment:,.2f}/mo × {plan.trial_duration_months}, "
                         f"approved by {plan.decided_by or 'not recorded'}", plan_id=plan.id, source="trial_plans")]
    return {"outcome": "pass", "context": context, "findings": findings, "detail": f"Monitoring plan {plan.id}"}


@node("trial_monitoring.match_payments")
def match_payments(state: dict, deps) -> dict:
    rules = deps.rules["trial_monitoring"]
    context = deepcopy(state["context"])
    findings = list(state["findings"])
    plan = context["plan"]
    today = date.fromisoformat(context["evaluation_date"])
    history = (context["dlq1"] or {}).get("payment_history")
    context["payment_history_available"] = history is not None

    payments = []
    for p in history or []:
        if as_float(p.get("amount")) is None or not p.get("payment_date"):
            continue
        if rules["ignore_payments_before_plan"] and p["payment_date"] < plan["created_at"][:10]:
            continue
        payments.append(p)
    context["payments_considered"] = payments

    # Without payment history nothing can be judged once an installment's grace has ended.
    if history is None:
        matched = [{**i, "status": "pending", "past_due": today > date.fromisoformat(i["due_date"])} for i in plan["installments"]]
    else:
        matched = match_installments(plan["installments"], payments, today, float(rules["amount_tolerance"]))
    context["installments"] = matched

    row = deps.db.get(models.TrialPlan, plan["plan_id"])
    by_no = {i.installment_no: i for i in row.installments}
    for m in matched:
        inst = by_no[m["installment_no"]]
        inst.status = m["status"]
        inst.received_amount = m.get("received_amount")
        inst.received_date = date.fromisoformat(m["received_date"]) if m.get("received_date") else None
        inst.evaluated_at = deps.now
        result = {"paid": "pass", "pending": "neutral", "late": "warn", "partial": "fail", "missed": "fail"}[m["status"]]
        findings.append(_finding(
            f"Installment {m['installment_no']}", result,
            f"{m['status']}{' (past due, in grace)' if m.get('past_due') and m['status'] == 'pending' else ''}: "
            f"expected ${m['expected_amount']:,.2f} due {m['due_date']} (grace to {m['grace_end_date']}), "
            f"received {'$' + format(m['received_amount'], ',.2f') if m.get('received_amount') is not None else 'nothing yet'}"
            f"{' on ' + m['received_date'] if m.get('received_date') else ''}",
            due_date=m["due_date"], expected_amount=m["expected_amount"], received_amount=m.get("received_amount"), status=m["status"]))
    deps.db.flush()
    return {"context": context, "findings": findings,
            "detail": f"{sum(m['status'] in ('paid', 'late') for m in matched)} of {len(matched)} installment(s) received; "
                      f"{len(payments)} DLQ1 payment(s) considered"}


@node("trial_monitoring.determine_completion")
def determine_completion(state: dict, deps) -> dict:
    rules = deps.rules["trial_monitoring"]
    context = deepcopy(state["context"])
    findings = list(state["findings"])
    matched = context["installments"]
    statuses = [m["status"] for m in matched]
    today = date.fromisoformat(context["evaluation_date"])
    grace_over = [m for m in matched if today > date.fromisoformat(m["grace_end_date"])]

    if not context["payment_history_available"] and grace_over:
        outcome, detail = "review", "MSP DLQ1 payment_history is not available but installment grace periods have ended"
        findings.append(_finding("DLQ1 payment history", "review", detail, source="MSP DLQ1.payment_history"))
    elif any(s in ("missed", "partial") for s in statuses):
        bad = next(m for m in matched if m["status"] in ("missed", "partial"))
        outcome, detail = "defaulted", f"Installment {bad['installment_no']} {bad['status']} after the grace period — trial failed, route to Onshore"
    elif all(s == "paid" for s in statuses):
        outcome, detail = "completed", f"All {len(statuses)} trial payments received on time — hand on to Final Underwriting"
    elif all(s in ("paid", "late") for s in statuses):
        outcome = "review" if rules["late_but_complete"] == "review" else "completed"
        detail = "All trial payments received, but at least one after its grace period"
    elif "late" in statuses or any(m.get("past_due") for m in matched):
        outcome, detail = "delayed", "A trial payment is past due (inside its grace period) or was received late"
    else:
        outcome, detail = "within_plan", f"{statuses.count('paid')} of {len(statuses)} paid; remaining installments not yet due"

    status_name = {"completed": "Completed", "within_plan": "Within Plan", "delayed": "Delayed Payment",
                   "defaulted": "Defaulted", "review": "In Human Review"}[outcome]
    note = (f"{rules['lmt_note']['prefix']} {today.isoformat()}: plan {context['plan']['plan_id']} — "
            f"{statuses.count('paid')} paid, {statuses.count('late')} late, {statuses.count('pending')} pending, "
            f"{statuses.count('partial')} partial, {statuses.count('missed')} missed. Outcome: {status_name}. {detail}")
    msp = deps.db.get(models.Msp, state["loan_id"])
    nots = deepcopy(msp.nots or {})
    nots["notes"] = [*(nots.get("notes") or []), note]
    nots["latest_note_date"] = today.isoformat()
    msp.nots = nots  # reassign so the JSON column is saved
    context["lmt_note"] = note
    findings.append(_finding("LMT note update", "pass", note, source="MSP NOTS"))
    return {"outcome": outcome, "context": context, "findings": findings, "detail": detail,
            "review_reason": detail if outcome == "review" else ""}
