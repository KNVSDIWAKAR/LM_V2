import Card from "../ui/Card";
import { StatusPill, fg, mutedFg } from "./ProcessParts";
import {
  CaseDrawerShell, CaseFooter, CaseLoading, FindingList, KeyValues, LatestRunCard, RunHistory, Section, useStageCase,
} from "./CaseParts";
import { money, pct, plansByEvaluation, resultColor } from "../../lib/caseDetails";

const PLAN_STATUS = { proposed: "Proposed", approved: "Approved", not_selected: "Not selected", declined: "Declined", superseded: "Superseded" };
const CODE_TONE = { OK: "pass", REDUCED: "pass", HIGH: "fail", INCREASE: "fail", INVALID: "fail" };

function codeColor(code) {
  const key = Object.keys(CODE_TONE).find((k) => code.endsWith(k));
  return resultColor(key ? CODE_TONE[key] : "review");
}

function PlanCard({ plan }) {
  const calc = plan.calculation ?? {};
  return (
    <Card className="!p-4 space-y-4">
      <div className="flex flex-wrap justify-between items-start gap-3">
        <div className="min-w-0">
          <h4 className="font-sans text-sm font-semibold" style={fg}>Option {plan.option_no} · {plan.plan_name}</h4>
          <p className="font-mono text-xs mt-1" style={mutedFg}>{plan.plan_id}</p>
        </div>
        <div className="text-right">
          <StatusPill status={PLAN_STATUS[plan.status] ?? plan.status} />
          <p className="font-serif text-2xl tabular-nums mt-1" style={fg}>{money(plan.trial_payment)}<span className="text-sm" style={mutedFg}>/mo</span></p>
        </div>
      </div>

      <KeyValues columns={4} rows={[
        ["Principal & interest", money(plan.principal_interest)],
        ["Escrow (ANA1)", money(plan.escrow_payment)],
        ["Interest rate", `${Number(plan.interest_rate_pct).toFixed(3)}%`],
        ["Amortization", `${plan.amortization_months} months`],
        ["Trial length", `${plan.trial_duration_months} payments`],
        ["Grace period", `${plan.grace_period_days} days`],
        ["First payment due", plan.first_due_date],
        ["Housing ratio", pct(plan.housing_ratio)],
        ["Gross monthly income", money(plan.gross_monthly_income)],
        ["Current payment", money(plan.current_payment)],
        ["Payment change", plan.payment_change_pct == null ? "Not measurable" : `${plan.payment_change_pct > 0 ? "+" : ""}${pct(plan.payment_change_pct)}`],
        ["UPB (DLQ1)", money(plan.upb_balance)],
      ]} />

      {!!plan.reason_codes?.length && (
        <div className="flex flex-wrap gap-1.5">
          {plan.reason_codes.map((c) => (
            <span key={c.code} title={c.text} className="font-sans text-[11px] px-2 py-0.5 rounded-full border" style={{ color: codeColor(c.code), borderColor: codeColor(c.code) }}>
              {c.code} · {c.text}
            </span>
          ))}
        </div>
      )}

      <details>
        <summary className="cursor-pointer text-sm font-medium" style={fg}>Installment schedule ({plan.installments.length})</summary>
        <div className="overflow-x-auto mt-2">
          <table className="w-full text-left text-xs">
            <thead style={mutedFg}><tr>{["#", "Due date", "Grace ends", "Expected", "Received", "Status"].map((h) => <th key={h} className="py-2 pr-3 font-medium">{h}</th>)}</tr></thead>
            <tbody>{plan.installments.map((i) => (
              <tr key={i.installment_no} className="border-t" style={{ borderColor: "hsl(var(--border))", ...fg }}>
                <td className="py-2 pr-3">{i.installment_no}</td>
                <td className="pr-3 whitespace-nowrap">{i.due_date}</td>
                <td className="pr-3 whitespace-nowrap">{i.grace_end_date}</td>
                <td className="pr-3">{money(i.expected_amount)}</td>
                <td className="pr-3">{i.received_amount == null ? "—" : money(i.received_amount)}</td>
                <td className="font-semibold uppercase" style={{ color: resultColor(i.status) }}>{i.status}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </details>

      <details>
        <summary className="cursor-pointer text-sm font-medium" style={fg}>Conditions ({plan.conditions.length})</summary>
        <ul className="list-disc pl-5 mt-2 space-y-1 text-sm" style={fg}>{plan.conditions.map((c) => <li key={c}>{c}</li>)}</ul>
      </details>

      <details>
        <summary className="cursor-pointer text-sm font-medium" style={fg}>How this was calculated</summary>
        <div className="mt-2 space-y-2 text-xs" style={mutedFg}>
          <p className="font-mono" style={fg}>{calc.formula}</p>
          <KeyValues columns={3} rows={[
            ["Income source", calc.income_source], ["Max housing ratio", pct(calc.max_housing_ratio_pct, 0)],
            ["Target reduction", pct(calc.target_payment_reduction_pct, 0)], ["Rules version", calc.rules_version],
          ]} />
        </div>
      </details>

      {plan.decided_at && plan.status !== "proposed" && (
        <p className="text-xs" style={mutedFg}>
          {PLAN_STATUS[plan.status]} {new Date(plan.decided_at).toLocaleString()}{plan.decided_by ? ` by ${plan.decided_by}` : ""}
          {plan.decision_note ? ` — “${plan.decision_note}”` : ""}
        </p>
      )}
    </Card>
  );
}

export default function TrialUWCaseDrawer({ loan, onClose, onDocuments, onRun, running }) {
  const query = useStageCase(3, loan.loan_id);
  const data = query.data;
  const run = data?.latest_run;
  const groups = plansByEvaluation(data?.data?.plans);
  const evidence = data?.data?.evidence;
  const status = data?.status ?? loan.status ?? (loan.position === "waiting" ? "Waiting" : "Not reached");

  return (
    <CaseDrawerShell title={loan.borrower_name} subtitle={`Loan ${loan.loan_id} · Trial Underwriting`} status={status} onClose={onClose}
      footer={<CaseFooter loan={loan} data={data} onDocuments={onDocuments} onClose={onClose} onRun={onRun} running={running}
        runnable={loan.runnable} runLabel="Run Trial UW" />}>
      <CaseLoading query={query} label="underwriting details" />
      {data && <>
        <LatestRunCard run={run} remark={data.remark}
          emptyText="Trial UW has not evaluated this loan yet. An imported stage status carries no checks or plans." />

        <Section title="Proposed trial plans" count={data.data.plans.length}>
          {!groups.length && <Card><p className="text-sm" style={mutedFg}>No plan was proposed. See the underwriting checks below for the hold or decline reason.</p></Card>}
          {groups.map((g, index) => (
            <div key={g.agent_run_id ?? index} className="space-y-3">
              <p className="text-xs" style={mutedFg}>
                {index === 0 ? "Latest evaluation" : "Earlier evaluation"} · {new Date(g.created_at).toLocaleString()} · <span className="font-mono">{g.agent_run_id}</span>
              </p>
              {g.plans.map((plan) => <PlanCard key={plan.plan_id} plan={plan} />)}
            </div>
          ))}
        </Section>

        {evidence && (
          <Section title="Evidence on file (live from MSP and documents)">
            <Card className="!p-4">
              <KeyValues rows={[
                ["Investor (DLQ1)", evidence.investor_type], ["UPB (DLQ1)", money(evidence.upb_balance)],
                ["Months delinquent", evidence.months_delinquent], ["Escrow (ANA1)", money(evidence.escrow_payment_amount)],
                ["Escrow current", evidence.escrow_current == null ? null : evidence.escrow_current ? "Yes" : "No"],
                ["Current payment (credit report)", money(evidence.current_payment)],
                ["Hardship", evidence.hardship_reason], ["Other income (MAA)", money(evidence.other_income_amount)],
              ]} />
              {!!evidence.income_sources.length && (
                <ul className="mt-3 text-xs space-y-0.5" style={mutedFg}>
                  {evidence.income_sources.map((s) => <li key={s.type}>{s.type}: <span style={fg}>{money(s.gross_monthly_amount)}/mo</span></li>)}
                </ul>
              )}
            </Card>
          </Section>
        )}

        {run && (
          <Section title="Underwriting checks" count={run.findings.length}>
            <FindingList findings={run.findings} />
          </Section>
        )}
        <RunHistory runs={data.runs} />
      </>}
    </CaseDrawerShell>
  );
}
