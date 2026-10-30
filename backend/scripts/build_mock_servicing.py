"""Write data/mock_servicing.json: MOCK servicer data for every loan in msp.json (POC only).

    python -m scripts.build_mock_servicing            # reads data/msp.json, writes data/mock_servicing.json

Every loan gets a clean "pays on time" trial and closing inputs that agree with its own MSP
data (borrower, property, UPB), so it can flow Trial Monitoring → Final UW & Closing.
SCENARIOS overrides a few loans to show the other paths. Edit it and re-run, then reset_db.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engine.nodes.trial_uw import amortized_payment  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data"
NEW_RATE, NEW_TERM = 6.875, 480  # matches the Trial UW 40-year option at the GSE posted rate

# loan_id → (scenario, trial payments, current note rate, open tasks)
SCENARIOS = {
    "8995970241": ("Second trial payment late → monitoring review", ["on_time", "late", "on_time"], 4.75, []),
    "3479708607": ("Third trial payment missed → Defaulted", ["on_time", "on_time", "missed"], 4.75, []),
    "2625792787": ("Trial complete; SCRA rate at threshold → Team Lead", ["on_time"] * 3, 5.75, []),
}
DEFAULT = ("Trial complete; closing inputs clean", ["on_time"] * 3, 4.75, [])


def build(loans: list[dict]) -> list[dict]:
    out = []
    for loan in loans:
        scenario, payments, rate, open_tasks = SCENARIOS.get(loan["loan_id"], DEFAULT)
        dlq1 = loan["servicing_data"]["DLQ1"]
        upb = float(dlq1["upb_balance"])
        out.append({
            "loan_id": loan["loan_id"],
            "scenario": scenario,
            "trial_payments": payments,
            "servicing_data": {
                "DLQ1": {"interest_rate": rate},
                "TASK1": {"tasks": [
                    {"task_id": "ESCMOD", "status": "Completed", "description": "Escrow modification", "opened_date": "2026-09-01", "completed_date": "2026-09-18"},
                    {"task_id": "PLNMTR", "status": "Completed", "description": "Plan monitoring", "opened_date": "2026-09-01", "completed_date": "2026-09-25"},
                    *open_tasks,
                ]},
                "MES1": {"tasks": []},
                "LSMR": {"current_interest_rate": rate, "new_interest_rate": NEW_RATE, "new_term_months": NEW_TERM,
                         "new_principal_balance": upb, "new_payment_amount": amortized_payment(upb, NEW_RATE, NEW_TERM)},
                "LMT3": {"x65_date": "2026-10-19", "e74_date": "2026-10-20", "j03_date": "2026-10-21",
                         "x58_date": "2026-10-22", "e68_date": "2026-10-23"},
            },
            "neighbourhood_document": {"document_date": "09/15/2026", "borrower_name": loan["borrower_name"],
                                       "property_address": loan["property_address"], "upb": upb, "prior_partial_claim_amounts": []},
        })
    return out


def main() -> None:
    loans = json.loads((DATA / "msp.json").read_text(encoding="utf-8"))["loans"]
    mock = build(loans)
    meta = {"primary_key": "loan_id", "total_loans": len(mock), "purpose": "MOCK servicer data for the POC — not from MSP. Built by scripts/build_mock_servicing.py"}
    (DATA / "mock_servicing.json").write_text(json.dumps({"meta": meta, "loans": mock}, indent=2), encoding="utf-8")
    print(f"wrote {len(mock)} mock loans to {DATA / 'mock_servicing.json'}")


if __name__ == "__main__":
    main()
