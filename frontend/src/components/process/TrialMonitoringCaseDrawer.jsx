import Card from "../ui/Card";
import { fg, mutedFg } from "./ProcessParts";
import { RunTable } from "../runs/RunPrimitives";
import {
  CaseDrawerShell, CaseFooter, CaseLoading, FindingList, KeyValues, LatestRunCard, RunHistory, Section, useStageCase,
} from "./CaseParts";
import { money, resultColor } from "../../lib/caseDetails";

const row = { background: "hsl(var(--card))", borderBottom: "1px solid hsl(var(--border))" };

export default function TrialMonitoringCaseDrawer({ loan, onClose, onDocuments, onRun, running }) {
  const query = useStageCase(4, loan.loan_id);
  const data = query.data;
  const run = data?.latest_run;
  const d = data?.data;
  const plan = d?.approved_plan;
  const status = data?.status ?? loan.status ?? (loan.position === "waiting" ? "Waiting" : "Not reached");
  const paidCount = plan?.installments.filter((i) => i.status === "paid" || i.status === "late").length ?? 0;

  return (
    <CaseDrawerShell title={loan.borrower_name} subtitle={`Loan ${loan.loan_id} · Trial Monitoring`} status={status} onClose={onClose}
      footer={<CaseFooter loan={loan} data={data} onDocuments={onDocuments} onClose={onClose} onRun={onRun} running={running}
        runnable={loan.runnable} runLabel="Run monitoring cycle" />}>
      <CaseLoading query={query} label="trial monitoring" />
      {data && <>
        <LatestRunCard run={run} remark={data.remark} emptyText="This loan has not been monitored yet." />

        <Section title="Approved trial plan">
          {plan ? (
            <Card className="!p-4 space-y-3">
              <div className="flex flex-wrap justify-between gap-2">
                <div>
                  <p className="font-sans text-sm font-semibold" style={fg}>{plan.plan_name}</p>
                  <p className="font-mono text-xs" style={mutedFg}>{plan.plan_id}</p>
                </div>
                <p className="font-serif text-2xl tabular-nums" style={fg}>{paidCount} / {plan.installments.length} <span className="text-sm" style={mutedFg}>received</span></p>
              </div>
              <KeyValues columns={4} rows={[
                ["Trial payment", money(plan.trial_payment)], ["Grace period", `${plan.grace_period_days} days`],
                ["First due", plan.first_due_date], ["Approved by", plan.decided_by],
              ]} />
            </Card>
          ) : <Card><p className="text-sm" style={mutedFg}>No approved trial plan is recorded for this loan.</p></Card>}
        </Section>

        {plan && (
          <Section title="Installments vs DLQ1 payments" count={plan.installments.length}>
            <RunTable columns={["#", "Due", "Grace ends", "Expected", "Received", "Received on", "Status"]}>
              {plan.installments.map((i) => (
                <tr key={i.installment_no} style={row}>
                  <td className="px-4 py-2 text-xs" style={fg}>{i.installment_no}</td>
                  <td className="px-4 py-2 text-xs whitespace-nowrap" style={fg}>{i.due_date}</td>
                  <td className="px-4 py-2 text-xs whitespace-nowrap" style={mutedFg}>{i.grace_end_date}</td>
                  <td className="px-4 py-2 text-xs" style={fg}>{money(i.expected_amount)}</td>
                  <td className="px-4 py-2 text-xs" style={fg}>{i.received_amount == null ? "—" : money(i.received_amount)}</td>
                  <td className="px-4 py-2 text-xs" style={mutedFg}>{i.received_date ?? "—"}</td>
                  <td className="px-4 py-2 text-xs font-semibold uppercase" style={{ color: resultColor(i.status) }}>{i.status}</td>
                </tr>
              ))}
            </RunTable>
            {plan.installments[0]?.evaluated_at && <p className="text-xs" style={mutedFg}>Last matched {new Date(plan.installments[0].evaluated_at).toLocaleString()}</p>}
          </Section>
        )}

        <Section title="MSP DLQ1 payment history" count={d.payment_history?.length}>
          {!d.payment_history_available ? (
            <Card><p className="text-sm" style={mutedFg}>MSP has not sent DLQ1 payment_history for this loan. Monitoring can only confirm installments that are not due yet; once a grace period ends without history the case goes to review.</p></Card>
          ) : (
            <RunTable columns={["Payment date", "Amount", "Type", "Reference"]} empty={d.payment_history.length ? null : "DLQ1 shows no payments."}>
              {d.payment_history.map((p, i) => (
                <tr key={i} style={row}>
                  <td className="px-4 py-2 text-xs" style={fg}>{p.payment_date}</td>
                  <td className="px-4 py-2 text-xs" style={fg}>{money(p.amount)}</td>
                  <td className="px-4 py-2 text-xs" style={mutedFg}>{p.transaction_type ?? "—"}</td>
                  <td className="px-4 py-2 text-xs font-mono" style={mutedFg}>{p.reference ?? "—"}</td>
                </tr>
              ))}
            </RunTable>
          )}
          <p className="text-xs" style={mutedFg}>DLQ1 due date {d.due_date ?? "not recorded"} · {d.months_delinquent ?? "—"} month(s) delinquent</p>
        </Section>

        <Section title="LMT notes written" count={d.lmt_notes.length}>
          {d.lmt_notes.length ? (
            <ul className="space-y-1.5">{[...d.lmt_notes].reverse().map((n, i) => <li key={i} className="text-xs rounded border px-3 py-2" style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--card))", ...fg }}>{n}</li>)}</ul>
          ) : <p className="text-sm" style={mutedFg}>No monitoring cycle has written a note yet.</p>}
        </Section>

        {run && <Section title="Monitoring checks" count={run.findings.length}><FindingList findings={run.findings} /></Section>}
        <RunHistory runs={data.runs} />
      </>}
    </CaseDrawerShell>
  );
}
