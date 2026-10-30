# Stages 3–5: Trial UW, Trial Monitoring, Final UW & Closing

Each stage reads only the database and writes its results back to it. If a value is
missing, the case is held or flagged for a person. Nothing gets a default.

| Stage | Playbook | Reads | Writes |
|---|---|---|---|
| 3 Trial UW | `trial_uw/` | lm_stages (Facially Complete), latest Stage 2 run report, extracted documents, MSP DLQ1/ANA1/LMT1/USR2 | `trial_plans` + `trial_installments` (proposed) |
| 4 Trial Monitoring | `trial_monitoring/` | the approved `trial_plans` row, MSP `DLQ1.payment_history` | installment status / received amount / date, one LMT note in MSP NOTS per cycle |
| 5 Final UW & Closing | `closing/` | MSP TASK1, MES1, LSMR, LMT3, DLQ1; `extracted_data.neighbourhood_document`; `closing_qc`; Stage 4 status | `closing_qc` (QC flags at MOD QC, `mod_approved_at` at sign-off) |

## Stage 3 · Trial Underwriting

1. Ingest: the loan must be **Facially Complete** in Retention. The saved Stage 2 Retention report is recorded as a finding.
2. Package: MAA, paystubs (at least `minimum_paystubs`), bank statement and credit report must be on file. If any is missing → **Hold Docs Pending**.
3. Eligibility: an investor outside `investor.eligible`, or UPB ≤ 0 → **Declined** (escalated to Onshore). An approval status still outstanding on LMT1/USR2 → **Hold Approval Pending**.
4. Terms: gross monthly income is the sum of the MAA `income_sources`, plus `other_income_amount` when the rules include it. Paystub wages are cross-checked within the tolerance. Current payment comes from `credit_report.monthly_mortgage_payment`, escrow from ANA1, UPB from DLQ1, and the rate from `posted_rate_pct[investor]`.
5. Validate each `plan_options` entry: `P&I = UPB·r/(1−(1+r)^−n)`, `trial payment = P&I + escrow`. It is checked against `max_housing_ratio_pct`, the payment change against the current payment, the rate/term bounds and escrow consistency. If no option is within the ratio → **Declined**.
6. Package: each affordable option is written to `trial_plans` with its first due date, installments, grace period, conditions, reason codes and full calculation inputs. Older proposals for the loan become `superseded`.
7. The Human Underwriter gate: approving requires `selected_plan_id` (optional when only one plan exists). That plan becomes `approved`, the others `not_selected`, and the status becomes **Ready**. Rejecting sets every plan to `declined` and the status to **Declined** (team Onshore).

## Stage 4 · Trial Monitoring

Each cycle compares cumulative DLQ1 payments, dated on or after the plan was proposed, with cumulative expected amounts:

- `paid`: covered by the grace end date
- `late`: covered after the grace end date
- `partial` / `missed`: the grace period is over and the installment is short or unpaid
- `pending`: not due yet, or due but still inside its grace period

Outcome: any partial/missed → **Defaulted** (Onshore). All paid → **Completed** (hands on to Stage 5). All covered but some late → review. Any past due or late → **Delayed Payment**. Otherwise → **Within Plan**. If `payment_history` is absent once a grace period has ended → review. Within Plan and Delayed Payment are picked up again by **Run**.

## Stage 5 · Final Underwriting & Closing

The flow follows `playbook_draft.yaml` / `rules_draft.yaml`. Two gates change so they no longer loop:

- Team Lead approval → MOD QC.
- An approved SLA breach → Sign Off & In Progress.

The MOD QC decision records the three QC flags. Human Sign-off records `mod_approved_at`, which starts the 14-day SLA. The Final Mod checks, facts and first-match verdicts are evaluated straight from `rules.yaml`. A loan in **Sign Off & In Progress** re-runs from `fm_trial_outcome` (underwriting is not repeated) after QC flags or the recording date are saved on the closing page (`PUT /api/cases/5/{loan}/closing-record`).

The legacy policy edge case is kept: QC complete with recording still pending inside the SLA → **Signed Off**.

## Input data contract (add to the import files; nothing is seeded)

`msp.json` → `servicing_data`:

```json
"DLQ1": { "...existing fields": "...", "interest_rate": 4.5,
          "payment_history": [{"payment_date": "2026-12-01", "amount": 1685.68, "transaction_type": "Trial", "reference": "PMT-1"}] },
"LMT3": { "...existing fields": "...", "x65_date": "2026-10-05", "e74_date": "2026-10-06", "j03_date": "2026-10-07", "x58_date": "2026-10-08", "e68_date": "2026-10-09" },
"TASK1": { "tasks": [{"task_id": "BKCASH", "status": "Completed", "description": null, "opened_date": "2026-09-01", "completed_date": "2026-09-10"}] },
"MES1":  { "tasks": [] },
"LSMR":  { "current_interest_rate": 4.5, "new_interest_rate": 4.0, "new_term_months": 480, "new_principal_balance": 212400.0, "new_payment_amount": 1272.0 }
```

`extracted_data.json` → `extracted_data`:

```json
"NEIGHBOURHOOD_DOCUMENT": { "document_date": "10/01/2026", "borrower_name": "...", "property_address": "...", "upb": 212400.0, "prior_partial_claim_amounts": [1500.0] }
```

`payment_history: null` (or absent) means MSP sent no history. `[]` means MSP reports no payments. On startup, `create_tables()` adds the new nullable columns to an existing database.

## MOCK servicer (POC)

Real trial payments take months to arrive, so `backend/data/mock_servicing.json` gives every
loan mock MSP data: a trial payment pattern plus TASK1, MES1, LSMR, the LMT3 closing dates,
DLQ1.interest_rate and a neighbourhood document that matches the loan's own MSP identity and UPB.
`python -m scripts.reset_db` loads it whenever the file is in the data folder. To load it on
its own, run `python -m scripts.import_data --mock data/mock_servicing.json`. It is rebuilt
by `python -m scripts.build_mock_servicing`; edit `SCENARIOS` there to change who pays late or misses.

When Stage 4 runs for a loan with a `mock_servicing` row, the mock servicer posts that loan's
payments to DLQ1. They are marked `Trial (MOCK)` with reference `MOCK-<plan>-<n>`. Monitoring
then evaluates as of the end of the simulated trial, so an on-time loan becomes Completed and
moves straight into Closing. The Trial Monitoring drawer labels these runs MOCK. To monitor
real DLQ1 data only, set `MOCK_SERVICER_ENABLED=false` or leave the file out.

Patterns: `on_time`, `late` (5 days after grace), `partial` (half), `missed`, `not_yet` (trial not that far yet).
