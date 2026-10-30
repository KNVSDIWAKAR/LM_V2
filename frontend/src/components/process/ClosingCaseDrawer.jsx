import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { LoaderCircle, Save } from "lucide-react";
import Card from "../ui/Card";
import { fg, mutedFg } from "./ProcessParts";
import { RunTable } from "../runs/RunPrimitives";
import {
  CaseDrawerShell, CaseFooter, CaseLoading, FindingList, KeyValues, LatestRunCard, ResultBadge, RunHistory, Section, useStageCase,
} from "./CaseParts";
import { API_BASE } from "../../lib/api";
import { money } from "../../lib/caseDetails";

const UW_ORDER = ["hold_tasks", "scra", "neighbourhood", "lsmr_terms", "lmt3_dates", "handoff"];
const UW_LABELS = {
  hold_tasks: "TASK1 / MES1 hold tasks", scra: "SCRA rate threshold", neighbourhood: "Neighbourhood document",
  lsmr_terms: "LSMR modification terms", lmt3_dates: "LMT3 closing-code dates", handoff: "Underwriting handoff",
};
const QC_FIELDS = [
  ["borrower_property_verified", "Borrower & property match the Note"],
  ["principal_matches_msp", "Principal balance matches MSP"],
  ["new_terms_match_plan", "New terms match the approved plan"],
];
const TONE = { green: "hsl(142, 60%, 32%)", amber: "hsl(32, 90%, 38%)", red: "hsl(0, 72%, 48%)" };
const row = { background: "hsl(var(--card))", borderBottom: "1px solid hsl(var(--border))" };
const toChoice = (v) => (v === true ? "true" : v === false ? "false" : "");
const fromChoice = (v) => (v === "true" ? true : v === "false" ? false : null);

/** MOD QC flags and the county recording date: the facts people record for closing. */
function ClosingRecordForm({ loanId, qc, recordingState, signedOff }) {
  const qcClient = useQueryClient();
  const [values, setValues] = useState(() => Object.fromEntries(QC_FIELDS.map(([k]) => [k, toChoice(qc[k])])));
  const [recorded, setRecorded] = useState(qc.recorded_date ?? "");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);
  useEffect(() => {
    setValues(Object.fromEntries(QC_FIELDS.map(([k]) => [k, toChoice(qc[k])])));
    setRecorded(qc.recorded_date ?? "");
  }, [qc.qc_at, qc.recorded_date]); // eslint-disable-line react-hooks/exhaustive-deps

  async function save() {
    setBusy(true);
    setMessage(null);
    const body = { updated_by: "closing-page" };
    for (const [k] of QC_FIELDS) if (values[k] !== toChoice(qc[k])) body[k] = fromChoice(values[k]);
    if ((recorded || null) !== (qc.recorded_date ?? null)) body.recorded_date = recorded || null;
    try {
      const res = await fetch(`${API_BASE}/api/cases/5/${encodeURIComponent(loanId)}/closing-record`, {
        method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Could not save");
      qcClient.setQueryData(["stage-case", 5, loanId], data);
      setMessage("Saved. Run the Final Mod checks again to update the verdict.");
    } catch (err) {
      setMessage(err.message);
    } finally {
      setBusy(false);
    }
  }

  const select = { borderColor: "hsl(var(--border))", background: "hsl(var(--card))", ...fg };
  return (
    <Card className="!p-4 space-y-3">
      {QC_FIELDS.map(([key, label]) => (
        <label key={key} className="flex flex-wrap items-center justify-between gap-2 text-sm" style={fg}>
          {label}
          <select value={values[key]} onChange={(e) => setValues({ ...values, [key]: e.target.value })} className="rounded-md border px-2 py-1 text-sm" style={select}>
            <option value="">Not reviewed</option>
            <option value="true">Verified</option>
            <option value="false">Mismatch found</option>
          </select>
        </label>
      ))}
      <label className="flex flex-wrap items-center justify-between gap-2 text-sm" style={fg}>
        County recording date {recordingState ? "" : <span className="text-xs" style={mutedFg}>(not a county-recording state)</span>}
        <input type="date" value={recorded} disabled={!signedOff} onChange={(e) => setRecorded(e.target.value)}
          className="rounded-md border px-2 py-1 text-sm disabled:opacity-50" style={select} />
      </label>
      <div className="flex flex-wrap items-center gap-3">
        <button onClick={save} disabled={busy} className="inline-flex items-center gap-1.5 text-sm font-medium px-3 py-1.5 rounded-md border disabled:opacity-50"
          style={{ borderColor: "hsl(var(--primary))", color: "hsl(var(--primary))", background: "hsl(var(--card))" }}>
          {busy ? <LoaderCircle size={14} className="animate-spin" /> : <Save size={14} />} Save closing record
        </button>
        {message && <span className="text-xs" style={mutedFg}>{message}</span>}
      </div>
      <p className="text-xs" style={mutedFg}>
        {qc.qc_at ? `QC last recorded by ${qc.qc_by} on ${new Date(qc.qc_at).toLocaleString()}.` : "QC not recorded yet."}{" "}
        {qc.mod_approved_at ? `Underwriting signed off ${new Date(qc.mod_approved_at).toLocaleString()} by ${qc.mod_approved_by}.` : "Underwriting plan not signed off yet."}
      </p>
    </Card>
  );
}

export default function ClosingCaseDrawer({ loan, onClose, onDocuments, onRun, running }) {
  const query = useStageCase(5, loan.loan_id);
  const data = query.data;
  const run = data?.latest_run;
  const d = data?.data;
  const report = run?.stage_report ?? {};
  const uw = report.uw_results ?? {};
  const fm = report.final_mod;
  const status = data?.status ?? loan.status ?? (loan.position === "waiting" ? "Waiting" : "Not reached");
  const recordingState = d && d.county_recording_states.includes(d.property_state);

  return (
    <CaseDrawerShell title={loan.borrower_name} subtitle={`Loan ${loan.loan_id} · Final Underwriting & Closing`} status={status} onClose={onClose}
      footer={<CaseFooter loan={loan} data={data} onDocuments={onDocuments} onClose={onClose} onRun={onRun} running={running}
        runnable={loan.runnable} runLabel={d?.rerun_entry ? "Re-check Final Mod" : "Run Final UW"} />}>
      <CaseLoading query={query} label="closing case" />
      {data && <>
        <LatestRunCard run={run} remark={data.remark} emptyText="Final Underwriting has not run for this loan yet." />

        {fm && (
          <Card className="!p-4 space-y-2" >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-serif text-xl" style={{ color: TONE[fm.tone] ?? "inherit" }}>{fm.verdict_label}</p>
              <span className="text-xs" style={mutedFg}>QC {fm.facts.qc_pass} / {fm.facts.qc_total} verified</span>
            </div>
            <p className="text-sm" style={fg}>{fm.description}</p>
            {fm.action && <p className="text-xs" style={mutedFg}>Action: <span style={fg}>{fm.action.label}</span> ({fm.action.severity}) — see {fm.action.show_checks.join(", ")}</p>}
          </Card>
        )}

        <Section title="Final Underwriting checks" count={Object.keys(uw).length || null}>
          {Object.keys(uw).length ? (
            <div className="rounded-md border divide-y" style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--card))" }}>
              {UW_ORDER.filter((k) => uw[k]).map((k) => (
                <div key={k} className="px-4 py-2.5 flex items-start gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium" style={fg}>{UW_LABELS[k]}</p>
                    <p className="text-xs mt-0.5" style={mutedFg}>{uw[k].detail}</p>
                  </div>
                  <ResultBadge result={{ pass: "pass", hold: "fail", review: "review" }[uw[k].outcome]} />
                </div>
              ))}
            </div>
          ) : <p className="text-sm" style={mutedFg}>{run?.start_at === "fm_trial_outcome" ? "This run re-checked Final Mod only; underwriting results are on the earlier run." : "No underwriting results saved yet."}</p>}
        </Section>

        <Section title="Final Mod checks" count={fm ? Object.keys(fm.checks).length : null}>
          {fm ? (
            <div className="rounded-md border divide-y" style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--card))" }}>
              {Object.values(fm.checks).map((c) => (
                <div key={c.id} className="px-4 py-2.5 flex items-start gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium" style={fg}>{c.label}{c.tags.includes("qc") && <span className="ml-2 text-[10px] uppercase" style={mutedFg}>QC</span>}</p>
                    <p className="text-xs mt-0.5" style={mutedFg}>{c.message}</p>
                  </div>
                  <ResultBadge result={c.status} />
                </div>
              ))}
            </div>
          ) : <p className="text-sm" style={mutedFg}>The Final Mod checks run after MOD QC and Human Sign-off approve the Underwriting plan.</p>}
        </Section>

        <Section title="Closing record (MOD QC · recording)">
          <ClosingRecordForm loanId={loan.loan_id} qc={d.qc} recordingState={recordingState} signedOff={!!d.qc.mod_approved_at} />
          <p className="text-xs" style={mutedFg}>
            Property state {d.property_state ?? "not recorded"} · county recording required in {d.county_recording_states.join(", ")} within {d.sla_days} days of sign-off.
          </p>
        </Section>

        <Section title="TASK1 / MES1 tasks">
          {d.tasks.TASK1 == null && d.tasks.MES1 == null ? <p className="text-sm" style={mutedFg}>Neither TASK1 nor MES1 has been loaded from MSP.</p> : (
            <RunTable columns={["Screen", "Task", "Status", "Opened", "Completed"]}
              empty={[...(d.tasks.TASK1 ?? []), ...(d.tasks.MES1 ?? [])].length ? null : "No tasks on either screen."}>
              {["TASK1", "MES1"].flatMap((src) => (d.tasks[src] ?? []).map((t, i) => (
                <tr key={`${src}-${i}`} style={row}>
                  <td className="px-4 py-2 text-xs font-mono" style={mutedFg}>{src}</td>
                  <td className="px-4 py-2 text-xs font-mono" style={fg}>{t.task_id}</td>
                  <td className="px-4 py-2 text-xs" style={fg}>{t.status}</td>
                  <td className="px-4 py-2 text-xs" style={mutedFg}>{t.opened_date ?? "—"}</td>
                  <td className="px-4 py-2 text-xs" style={mutedFg}>{t.completed_date ?? "—"}</td>
                </tr>
              )))}
            </RunTable>
          )}
        </Section>

        <Section title="LSMR new modification terms">
          {d.lsmr ? <Card className="!p-4"><KeyValues rows={[
            ["Current rate", d.lsmr.current_interest_rate != null ? `${d.lsmr.current_interest_rate}%` : null],
            ["New rate", d.lsmr.new_interest_rate != null ? `${d.lsmr.new_interest_rate}%` : null],
            ["New term", d.lsmr.new_term_months != null ? `${d.lsmr.new_term_months} months` : null],
            ["New principal", money(d.lsmr.new_principal_balance)], ["New payment", money(d.lsmr.new_payment_amount)],
            ["Approved trial payment", d.approved_plan ? money(d.approved_plan.trial_payment) : null],
          ]} /></Card> : <p className="text-sm" style={mutedFg}>MSP LSMR has not been loaded for this loan.</p>}
        </Section>

        <Section title="LMT3 closing-code dates">
          <Card className="!p-4"><KeyValues columns={4} rows={Object.entries(d.lmt3_dates).map(([k, v]) => [k.split("_")[0].toUpperCase(), v])} /></Card>
        </Section>

        <Section title="Neighbourhood document">
          {d.neighbourhood_document ? <Card className="!p-4"><KeyValues rows={[
            ["Document date", d.neighbourhood_document.document_date], ["Borrower", d.neighbourhood_document.borrower_name],
            ["Property", d.neighbourhood_document.property_address], ["UPB", money(d.neighbourhood_document.upb)],
            ["Prior partial claims", (d.neighbourhood_document.prior_partial_claim_amounts ?? []).map(money).join(", ") || "None"],
          ]} /></Card> : <p className="text-sm" style={mutedFg}>No neighbourhood document has been extracted for this loan.</p>}
        </Section>

        {run && <Section title="All findings" count={run.findings.length}><FindingList findings={run.findings} /></Section>}
        <RunHistory runs={data.runs} />
      </>}
    </CaseDrawerShell>
  );
}
