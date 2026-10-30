# Process 2 — deterministic Retention Eligibility

The graph is `playbook.yaml`; policy, stips, investor configuration and keywords
are `rules.yaml`. Python lives in `app/engine/nodes/retention.py`
with source/report helpers in `app/engine/retention_support.py`. No model or LLM is
called. Intake's playbook, rules and Python functions are unchanged.

The optional `confidence` mapping is audit metadata, not a required business rule.
When omitted, empty or null, report helpers use `high=0.98`, `medium=0.92`,
`inferred=0.85`, `default=0.50`, `decimals=2`; partial mappings override only the
specified keys. These scores never affect eligibility, stips or review routing.
Only the `retention.*` node implementation is active; the obsolete
`retention_eligibility.*` implementation has been removed along with its harness.

## Execution and API

- `POST /api/processes/2/run` uses existing `stage_candidates` / `continue_at_stage`:
  Intake must be Complete, retention must have no status, and no workflow may be active.
  Re-run queues newly eligible loans, not existing results. No destructive status reset.
- Existing end-to-end/auto-flow also discovers this playbook and continues Intake-complete
  loans through it. Scheduler behavior is unchanged.
- `GET /api/retention/summary`: portfolio size, eligible count, verdict counts, latest
  run, case records and pending actions. Records are the Intake-complete cohort.
- `GET /api/retention/cases` and `/api/retention/cases/{loan_id}`: latest saved result;
  never re-evaluate using today's data during a GET. Imported statuses without run
  reports have a null report/stip count, not invented questions or zero stips.
- `POST /api/retention/cases/{loan_id}/review`: explicit, idempotent manual routing
  to Decision Inbox. A new review snapshot preserves the original evaluation. Approval
  acknowledges, but does not waive stips or change an existing denial into completion.
- Confidence is not considered for new evaluations: any stip means Facially Incomplete;
  otherwise Facially Complete (explicit routing exits remain unchanged). Manual Decision
  Inbox routing remains available. The unreachable `human_review` gate is retained only
  so historical paused runs can still resume. Existing saved decisions are not rewritten.
- `agent_runs.output.report` persists the full report on completion and on pause.
  Actual verdict and DM712 applicability are updated after a human decision. The
  original answers, confidence flags and stips remain auditable.

## Specification interpretations

- **Q32 raises a stip for different addresses (true)**, following the detailed rule.
  The supplied final trigger summary incorrectly lists false for this question.
- **Liquidation / already-approved exits use Denied**, `advance: false`, no stips.
  These are routing exits, not a substantive eligibility denial. Each has its own
  titled YAML end node and a recorded exit reason, so the status is easy to change.
- **FNMA >9 months** exits Facially Complete with advancement and no form checks.
  Generic GSE does not prove FNMA (it can include FHLMC), so it does not get this exemption.
- **VA** records Q1, Q2 and a Q3 request-only/not-applicable annotation, then uses the
  verdict gate; it skips detailed form/income checks. No new fictitious question ID.
- No-wage income records the calculation-document choice under Q10a and skips Q11–Q19.
- **QX** checks the hardship for single and joint borrower cases (investor exits remain
  unchanged). Death-related hardship requires a death certificate; divorce/separation
  requires an agreement/decree or quit-claim deed. Unrelated hardship passes without
  those documents. Requirements and keywords are configurable in `hardship_documents`.
  Dated NOTS must explicitly confirm receipt/on-file evidence of the appropriate document;
  missing/requested/required mentions or an unrelated document do not satisfy the check.
- Missing required evidence is **fail**, not pending. Optional unknown values and
  date-only outputs (`Q5`, `CALC_Q4`) are **neutral**, shown in black with no verdict badge.
  If the required L92 date cannot be resolved, Q5 still raises its stip and fails.
  Real date validations (recent paystubs, insurance expiry, report freshness) keep their
  pass/fail checks. Not-applicable checks pass rather than appear pending.
  The API retains support for historical pending answers, but new runs do not create them.
  New reports use question_results_version=2 and count informational results separately.
  Summary failed counts fail badges, not stip count. Q35 not applicable is excluded
  from confidence aggregation. Overall/source confidence is retained only as audit metadata,
  not displayed or used for decisions/badges. New reports set confidence_considered=false,
  low_confidence_flags=[], and summary.low_confidence=0. Inferred dates and default answers
  do not cause human review. Missing required evidence still raises the specified stips.

## Verified data mapping and limits

| Source | Actual database field |
|---|---|
| Application_Form | extracted_data.application_form |
| PAYSTUBS | extracted_data.paystubs (primary employee-name match only) |
| BANK_STATEMENT | extracted_data.bank_statement |
| LETTER_OF_EXPLANATION | extracted_data.letter_of_explanation |
| CREDIT_REPORT / flags | extracted_data.credit_report / flags |
| LMT1 / LMT3 / NOTS | msp.lmt1 / lmt3 / nots |
| DLQ1 investor/state/addresses/borrower count | msp.dlq1 |
| HAZ1 / ANA1 / HOA / foreclosure | msp.haz1 / ana1 / hoa / foreclosure |

The supplied 30 JSON loans all have DLQ1 investor_type GSE, even where the top-level
loan_type says Asset. DLQ1 controls investor policy.

- There is no document page-count metadata, email sheet, fax cover, portal/upload table,
  death/divorce/quit-claim document or employment-verification document column. Q4b uses
  the available page-count flag. QX/Q15a can find references in dated NOTS, but do not
  fabricate documents. Q9 channel subquestions without metadata return false/default.
- NOTS string arrays use their screen's latest_note_date. Structured notes, if supplied,
  use their own date. Notes outside LMT3 minus-10 through review-start are ignored.
- L92 uses LMT3 first, then dated NOTS describing a submission channel minus one business
  day. Weekends are configurable; no holiday calendar is present.
- Pay dates and periods are MM/DD/YYYY; MSP dates are YYYY-MM-DD. Invalid dates remain
  unknown. Q16 accepts adjacent pay periods OR consecutive calendar coverage months,
  using pay_period_end rather than pay_date, for the same primary borrower and employer.
  The consecutive-month alternative is configured under `paystub_sequence` in rules.yaml.
  Q16 records the distinct periods, consecutive count and exact coverage gaps. Duplicate
  copies do not count as extra periods. Alexandra's seed covers Jan 16–31 and Feb 16–28;
  these cover consecutive months and therefore pass Q16 even though Feb 1–15 is absent.
  Skipped months do not pass the month-based check. The report records the acceptance
  basis and gaps for audit; original source data is unchanged.
- Raw bank deposit rows contain **balance**, not amount. Balance is never treated as
  income/deposit amount. Explicit amounts, when available, are summed by source/month;
  the existing recurring_deposits_over_250 aggregate is also supported. LOE reference
  numbers must cover deposits and the LOE must be sufficient to explain them.
- Seed credit reports have no report_date or servicer-specific tradelines. USDA report
  freshness cannot be established from these rows; extraction time is not report time.
  Missing USDA reports are internal-review requirements, never borrower requests.
- Current supporting documents can establish income through borrower-matched paystubs,
  matching bank descriptions, or a sufficient LOE of the listed income type. No award
  letter/tax-return/VOE is fabricated when no such document exists in the schema.

## Verification

The pytest suite uses a throwaway SQLite database and disables auto-flow/front-end
autobuild. Tests cover graph routes, exits, all stip policies, investor variants,
primary-only wage loops, confidence-independent outcomes, source dates, bank aggregation,
persisted reports, candidate selection and Decision Inbox resume. Existing Intake
assertions remain; only assumptions that stage 2 has no playbook were updated.

Run the backend pytest suite and the frontend production build from their respective
directories. No database migration, seed rewrite, or second server is required.
An already-running backend must load the new code/playbooks through its normal reload
or restart mechanism; no test sends a Run request to the live service on port 8000.