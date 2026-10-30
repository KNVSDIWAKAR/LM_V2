import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence } from "framer-motion";
import { CircleAlert, FileSearch, LoaderCircle, Search } from "lucide-react";
import Card from "../components/ui/Card";
import LoanDrawer from "../components/knowledge/LoanDrawer";
import RetentionCaseDrawer from "../components/process/RetentionCaseDrawer";
import { PrimaryButton, StatusPill, fg, mutedFg, statusColor, useRefreshRuns } from "../components/process/ProcessParts";
import { RunTable } from "../components/runs/RunPrimitives";
import { apiGet, apiPost } from "../lib/api";
import { timeAgo } from "../lib/utils";
import { retentionProgress } from "../lib/retentionProgress";

const verdicts = ["Facially Complete", "Denied", "Facially Incomplete", "In Human Review"];

function CountTile({ title, value, active, onClick }) {
  const color = title === "Loans in book" ? "hsl(var(--foreground))" : statusColor(title);
  return <button onClick={onClick} aria-pressed={active} className="rounded-md border p-4 text-left min-w-0 transition-colors hover:brightness-[0.98]"
    style={{ background: "hsl(var(--card))", borderColor: active ? color : "hsl(var(--border))" }}>
    <p className="font-sans text-xs mb-3" style={mutedFg}>{title}</p>
    <p className="font-serif text-3xl font-semibold tabular-nums" style={{ color }}>{value}</p>
  </button>;
}

export default function RetentionEligibility() {
  const refresh = useRefreshRuns();
  const [filter, setFilter] = useState(null);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState(null);
  const [documents, setDocuments] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);
  const [runIds, setRunIds] = useState([]);
  const [skipped, setSkipped] = useState([]);
  const completedBatch = useRef(null);
  const qc = useQueryClient();
  const close = useCallback(() => setSelected(null), []);
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["process", 2, "retention-summary"],
    queryFn: () => apiGet("/api/retention/summary"),
    refetchInterval: 5000,
  });
  // Reattach to durable queued/running executions when returning to the page.
  useEffect(() => {
    if (!runIds.length && data?.active_run_ids?.length) setRunIds(data.active_run_ids);
  }, [data?.active_run_ids, runIds.length]);
  const execution = useQuery({
    queryKey: ["retention-execution", runIds],
    queryFn: () => apiGet(`/api/retention/executions?ids=${encodeURIComponent(runIds.join(","))}`),
    enabled: runIds.length > 0,
    refetchInterval: (query) => retentionProgress(runIds, query.state.data?.runs).active ? 1000 : false,
    retry: 1,
  });
  const progress = retentionProgress(runIds, execution.data?.runs);
  const working = busy || progress.active || (!runIds.length && !!data?.active_run_ids?.length);
  useEffect(() => {
    const batch = runIds.join(",");
    if (!batch || progress.active || completedBatch.current === batch) return;
    completedBatch.current = batch;
    setMessage(`Finished ${progress.finished} case(s): ${progress.failed} failed, ${progress.paused} awaiting review.`);
    ["process", "processes", "agent-runs", "workflow-runs", "decisions"].forEach((key) => qc.invalidateQueries({ queryKey: [key] }));
  }, [runIds, progress.active, progress.finished, progress.failed, progress.paused, qc]);
  async function run() {
    if (working) return;
    setBusy(true); setMessage(null);
    setSkipped([]);
    try {
      const result = await apiPost("/api/processes/2/run", { rerun: true });
      setRunIds(result.run_ids ?? []);
      setSkipped(result.skipped ?? []);
      setMessage(result.queued ? `${result.queued} case(s) queued for fresh evaluation.` : "No cases can run now. Intake must be complete, with no active review or later-stage work.");
      refresh();
    } catch (err) {
      setMessage(err.message);
      refetch(); // Recover accepted work if the network dropped after the POST.
    } finally {
      setBusy(false);
    }
  }
  if (isLoading) return <div className="flex items-center justify-center gap-2 py-16" style={mutedFg}><LoaderCircle size={18} className="animate-spin" /> Loading Retention Eligibility…</div>;
  if (isError || !data) return <div className="flex items-center justify-center gap-2 py-16" role="alert" style={mutedFg}><CircleAlert size={18} /> Could not load retention results. <button className="underline" onClick={() => refetch()}>Try again</button></div>;

  const records = data.records.filter((r) => (!filter || (r.status ?? "Waiting") === filter) && `${r.loan_id} ${r.borrower_name}`.toLowerCase().includes(search.toLowerCase()));
  const evaluated = verdicts.reduce((n, status) => n + data.counts[status], 0);
  const toggle = (status) => setFilter((current) => current === status ? null : status);
  return <div className="px-2 sm:px-6 py-6 max-w-7xl mx-auto flex flex-col gap-6">
    <header className="flex flex-wrap justify-between items-start gap-4">
      <div>
        <p className="font-sans text-xs uppercase tracking-widest mb-1" style={mutedFg}>Process 2 of 5 · Deterministic ART evaluation</p>
        <h1 className="font-serif text-2xl font-semibold tracking-tight" style={fg}>Loss Mitigation - Retention Eligibility</h1>
        <p className="font-sans text-sm mt-2" style={mutedFg}>{data.last_run_id ? `Latest run ${data.last_run_id} · ${timeAgo(data.last_run_at)}` : "No retention runs yet"} · {data.total_records} records · {data.eligible} ready to run</p>
      </div>
      <div className="flex flex-col items-end gap-2">
        <PrimaryButton onClick={run} busy={working} title="Re-evaluates Intake-complete retention cases and preserves history; active reviews and later-stage work are skipped">
          {working ? (busy ? "Queuing…" : `Running… ${progress.finished}/${progress.total}`) : data.run_count ? "Re-run" : "Run"}
        </PrimaryButton>
        <p className="font-sans text-xs max-w-sm text-right" style={mutedFg} aria-live="polite">{message ?? "Re-run evaluates existing cases using the latest rules and data."}</p>
      </div>
    </header>

    {(working || runIds.length > 0) && <Card className="space-y-3">
      <div className="flex items-center gap-2 text-sm" role="status" aria-live="polite" style={fg}>
        {working && <LoaderCircle size={16} className="animate-spin" />}
        {busy ? "Preparing retention evaluations…" : progress.active ? `Processing cases — ${progress.finished} of ${progress.total} finished` : `Run finished — ${progress.finished} of ${progress.total} processed`}
      </div>
      <div role="progressbar" aria-label="Retention run progress" aria-valuemin={0} aria-valuemax={progress.total || 1} aria-valuenow={progress.finished}
        className="h-2 rounded-full overflow-hidden" style={{ background: "hsl(var(--muted))" }}>
        <div className="h-full transition-all rounded-full" style={{ width: `${progress.percent}%`, background: "hsl(var(--primary))" }} />
      </div>
      {execution.isError && <p role="alert" className="text-xs text-red-700">Could not refresh progress. Retrying automatically; do not submit another run. <button className="underline" onClick={() => execution.refetch()}>Retry now</button></p>}
      {progress.errors.map((error) => <p key={error} role="alert" className="text-xs text-red-700">{error}</p>)}
      {progress.paused > 0 && <p className="text-xs" style={mutedFg}>{progress.paused} case(s) require a decision in the Decision Inbox.</p>}
    </Card>}
    {skipped.length > 0 && <details className="text-xs rounded border p-3" style={{ borderColor: "hsl(var(--border))", ...mutedFg }}>
      <summary className="cursor-pointer font-semibold">{skipped.length} case(s) skipped — show reasons</summary>
      <ul className="mt-2 space-y-1">{skipped.map((item) => <li key={item.loan_id}>Loan {item.loan_id}: {item.reason}</li>)}</ul>
    </details>}

    <section aria-labelledby="pending-actions-title">
      <Card className="!p-0 overflow-hidden">
        <div className="flex items-center gap-2 px-5 py-4 border-b" style={{ borderColor: "hsl(var(--border))" }}>
          <CircleAlert size={17} style={{ color: statusColor("Facially Incomplete") }} />
          <h2 id="pending-actions-title" className="font-sans text-sm font-semibold" style={fg}>Pending actions ({data.pending_actions.length})</h2>
        </div>
        {data.pending_actions.length === 0 ? <p className="px-5 py-4 text-sm" style={mutedFg}>No facially incomplete cases need document follow-up.</p> :
          <div className="max-h-72 overflow-y-auto">{data.pending_actions.map((record) => <div key={record.loan_id} className="flex items-center justify-between gap-4 px-5 py-3 border-b last:border-b-0" style={{ borderColor: "hsl(var(--border))" }}>
            <div className="min-w-0">
              <p className="font-sans text-sm font-medium" style={fg}>{record.borrower_name} <span className="font-mono text-xs ml-2" style={mutedFg}>{record.loan_id}</span></p>
              <p className="text-xs mt-1 line-clamp-2" style={mutedFg}>{record.pending_reason || "Open the case to review outstanding requirements."}</p>
            </div>
            <button className="inline-flex items-center gap-1.5 shrink-0 text-xs font-semibold rounded border px-3 py-2" style={{ color: "hsl(var(--primary))", borderColor: "hsl(var(--border))" }} onClick={() => setSelected(record)}><FileSearch size={14} /> Open file</button>
          </div>)}</div>}
      </Card>
    </section>

    <section aria-label="Retention status counts" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
      <div className="flex flex-col gap-2"><p className="text-[11px] uppercase tracking-widest" style={mutedFg}>Portfolio</p><CountTile title="Loans in book" value={data.loans_in_book} active={!filter} onClick={() => setFilter(null)} /></div>
      <div className="flex flex-col gap-2"><p className="text-[11px] uppercase tracking-widest" style={mutedFg}>Moving forward</p><CountTile title="Facially Complete" value={data.counts["Facially Complete"]} active={filter === "Facially Complete"} onClick={() => toggle("Facially Complete")} /></div>
      <div className="flex flex-col gap-2 lg:col-span-3"><p className="text-[11px] uppercase tracking-widest" style={mutedFg}>Needs attention</p><div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {verdicts.slice(1).map((status) => <CountTile key={status} title={status} value={data.counts[status]} active={filter === status} onClick={() => toggle(status)} />)}
      </div></div>
    </section>

    <Card className="space-y-4">
      <div className="flex flex-wrap justify-between gap-2"><h2 className="font-sans text-sm font-semibold" style={fg}>Verdict distribution</h2><p className="text-xs" style={mutedFg}>{evaluated} evaluated · {data.counts.Waiting} waiting</p></div>
      <div className="flex h-4 w-full rounded-full overflow-hidden" role="img" aria-label={verdicts.map((status) => `${status}: ${data.counts[status]}`).join(", ")} style={{ background: "hsl(var(--muted))" }}>
        {verdicts.map((status) => <div key={status} title={`${status}: ${data.counts[status]}`} style={{ width: evaluated ? `${100 * data.counts[status] / evaluated}%` : "0%", background: statusColor(status) }} />)}
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-2">{verdicts.map((status) => <button key={status} onClick={() => toggle(status)} className="flex items-center gap-2 text-xs" style={mutedFg}>
        <span className="w-2.5 h-2.5 rounded-full" style={{ background: statusColor(status) }} />{status} <strong style={fg}>{data.counts[status]}</strong>
      </button>)}</div>
      {!evaluated && <p className="text-xs" style={mutedFg}>Run eligible cases to see the verdict distribution.</p>}
    </Card>

    <section aria-labelledby="retention-records-title" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="retention-records-title" className="font-sans text-sm font-semibold" style={fg}>Records ({records.length}){filter ? ` · ${filter}` : ""}</h2>
        <div className="flex items-center gap-3">
          {filter && <button onClick={() => setFilter(null)} className="text-xs underline" style={mutedFg}>Clear filter</button>}
          <button onClick={() => toggle("Waiting")} className="text-xs underline" style={mutedFg}>Waiting ({data.counts.Waiting})</button>
          <label className="flex items-center gap-2 border rounded px-3 py-1.5" style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--card))" }}><Search size={14} style={mutedFg} /><input value={search} onChange={(event) => setSearch(event.target.value)} aria-label="Search retention records" placeholder="Loan or borrower" className="text-xs bg-transparent outline-none w-36" /></label>
        </div>
      </div>
      <RunTable columns={["Loan ID", "Borrower", "Investor", "Months delinquent", "Hardship", "Stips", "Verdict"]} empty={records.length ? null : "No matching Intake-complete cases."}>
        {records.map((record) => <tr key={record.loan_id} onClick={() => setSelected(record)} className="cursor-pointer hover:brightness-[0.97]" style={{ background: "hsl(var(--card))", borderBottom: "1px solid hsl(var(--border))" }}>
          <td className="px-4 py-3 font-mono text-xs"><button className="underline underline-offset-2" onClick={(event) => { event.stopPropagation(); setSelected(record); }} aria-label={`Open case ${record.loan_id}`}>{record.loan_id}</button></td>
          <td className="px-4 py-3 whitespace-nowrap" style={fg}>{record.borrower_name}</td>
          <td className="px-4 py-3 text-xs" style={mutedFg}>{record.investor ?? "—"}</td>
          <td className="px-4 py-3 tabular-nums text-xs" style={fg}>{record.months_delinquent ?? "—"}</td>
          <td className="px-4 py-3 text-xs max-w-56" style={mutedFg}>{record.hardship ?? "—"}</td>
          <td className="px-4 py-3 tabular-nums text-sm" style={fg}>{record.stip_count ?? "—"}</td>
          <td className="px-4 py-3"><StatusPill status={record.status ?? "Waiting"} />{record.last_run_status === "failed" && <span className="block text-xs mt-1 text-red-600">Last run failed</span>}</td>
        </tr>)}
      </RunTable>
      <p className="text-xs" style={mutedFg}>Records include only loans with Intake = Complete. Loans in book counts the full portfolio. Blank stip counts mean no saved evaluation report.</p>
    </section>
    <AnimatePresence>{selected && !documents && <RetentionCaseDrawer key={selected.loan_id} loan={selected} onClose={close} onDocuments={setDocuments} onRefresh={refresh} />}</AnimatePresence>
    <LoanDrawer loanId={documents?.loan_id} borrowerName={documents?.borrower_name} initialTab="documents" onClose={() => setDocuments(null)} />
  </div>;
}