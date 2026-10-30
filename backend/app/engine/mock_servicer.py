"""MOCK MSP servicer (POC only): posts simulated trial payments to DLQ1.payment_history.

Real trial payments arrive over months. To let a case move from Trial Monitoring to Closing in
a demo, the mock posts each installment's payment as its `mock_servicing.trial_payments`
pattern says, and returns the date the simulated trial has reached. Monitoring then evaluates
as of that date. Every posted payment is marked transaction_type "Trial (MOCK)" and a
reference starting MOCK-<plan id>-, and a re-run replaces the earlier mock payments for the plan.
"""

from copy import deepcopy
from datetime import date, timedelta

from .. import models

LATE_DAYS_AFTER_GRACE = 5


def post_trial_payments(db, loan_id: str, plan: dict) -> dict | None:
    """Post the mock payments for `plan` (a trial_support.plan_out dict). None when the loan has no mock row."""
    mock = db.get(models.MockServicing, loan_id)
    if mock is None:
        return None
    msp = db.get(models.Msp, loan_id)
    prefix = f"MOCK-{plan['plan_id']}-"
    dlq1 = deepcopy(msp.dlq1 or {})
    history = [p for p in dlq1.get("payment_history") or [] if not str(p.get("reference", "")).startswith(prefix)]

    posted, as_of = [], None
    pattern = list(mock.trial_payments)
    for inst in plan["installments"]:
        behaviour = pattern[inst["installment_no"] - 1] if inst["installment_no"] <= len(pattern) else pattern[-1] if pattern else "on_time"
        if behaviour == "not_yet":
            break
        due, grace_end = date.fromisoformat(inst["due_date"]), date.fromisoformat(inst["grace_end_date"])
        amount = float(inst["expected_amount"])
        paid_on, paid = {
            "on_time": (due, amount),
            "late": (grace_end + timedelta(days=LATE_DAYS_AFTER_GRACE), amount),
            "partial": (due, round(amount / 2, 2)),
            "missed": (None, 0.0),
        }[behaviour]
        if paid_on is not None:
            posted.append({"payment_date": paid_on.isoformat(), "amount": paid, "transaction_type": "Trial (MOCK)",
                           "reference": f"{prefix}{inst['installment_no']}"})
        # The simulated trial has reached the day after this installment's grace period (or its late payment).
        reached = max(grace_end, paid_on or grace_end) + timedelta(days=1)
        as_of = reached if as_of is None else max(as_of, reached)
        if behaviour in ("missed", "partial"):
            break  # the trial fails here; nothing after it is simulated

    dlq1["payment_history"] = history + posted
    msp.dlq1 = dlq1  # reassign so the JSON column is saved
    db.flush()
    return {"scenario": mock.scenario, "pattern": pattern, "posted": posted,
            "as_of": as_of.isoformat() if as_of else None}
