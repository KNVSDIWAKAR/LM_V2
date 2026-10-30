import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CircleAlert, FileCode2, Inbox, LoaderCircle } from "lucide-react";
import { Link } from "wouter";
import LoanDrawer from "../components/knowledge/LoanDrawer";
import ClosingCaseDrawer from "../components/process/ClosingCaseDrawer";
import TrialMonitoringCaseDrawer from "../components/process/TrialMonitoringCaseDrawer";
import TrialUWCaseDrawer from "../components/process/TrialUWCaseDrawer";
import Card from "../components/ui/Card";
import { PlaybookFlow, PrimaryButton, StatusPill, fg, mutedFg, statusColor, useRefreshRuns } from "../components/process/ProcessParts";
import { RunStatus, RunTable } from "../components/runs/RunPrimitives";
import { apiGet, apiPost } from "../lib/api";
import { PROCESSES } from "../lib/navigation";
import { timeAgo } from "../lib/utils";

// Stages whose loans open a case drawer (checks, plans, payments, closing record) instead of the documents drawer.
const CASE_DRAWERS = { 3: TrialUWCaseDrawer, 4: TrialMonitoringCaseDrawer, 5: ClosingCaseDrawer };

function Tile({ label, value, color, active, onClick }) {
  return (
    <button
      onClick={onClick}
      className="text-left rounded-md border px-3 py-2 transition-colors"
      style={{
        borderColor: active ? color : "hsl(var(--border))",
        background: active ? "hsl(var(--muted))" : "hsl(var(--card))",
      }}
    >
      <p className="font-sans text-[11px] uppercase tracking-wider truncate" style={mutedFg}>
        {label}
      </p>
      <p className="font-serif text-2xl tabular-nums leading-tight" style={{ color: value ? color : "hsl(var(--muted-foreground))" }}>
        {value}
      </p>
    </button>
  );
}

/** One of the five processes: its status board, its playbook, its loans, and its Run button. */
export default function ProcessPage({ stageNo }) {
  const nav = PROCESSES[stageNo - 1];
  const refresh = useRefreshRuns();
  const [filter, setFilter] = useState(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState(null);
  const [openLoan, setOpenLoan] = useState(null);
  const [documentLoan, setDocumentLoan] = useState(null);
  const [runningLoan, setRunningLoan] = useState(null);
  const CaseDrawer = CASE_DRAWERS[stageNo];

  const { data, isLoading, isError } = useQuery({
    queryKey: ["process", stageNo],
    queryFn: () => apiGet(`/api/processes/${stageNo}`),
    refetchInterval: 5000,
  });
  const { data: playbook } = useQuery({
    queryKey: ["playbook", stageNo],
    queryFn: () => apiGet(`/api/processes/${stageNo}/playbook`),
    enabled: !!data?.playbook,
  });

  // A loan's label at this stage: its status once worked, otherwise Waiting / Not reached.
  const label = (l) => l.status ?? (l.position === "waiting" ? "Waiting" : "Not reached");
  const loans = useMemo(
    () => (data?.loans ?? []).filter((l) => (filter ? label(l) === filter : l.position !== "not_reached")),
    [data, filter],
  );
  const notReached = data?.counts?.["Not reached"] ?? 0;

  async function run() {
    setBusy(true);
    setNote(null);
    try {
      const r = await apiPost(`/api/processes/${stageNo}/run`, {});
      setNote(r.queued ? `Running ${r.queued} case${r.queued === 1 ? "" : "s"}…` : "No cases are waiting at this stage.");
      refresh();
    } catch (err) {
      setNote(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function runLoan(loan) {
    setRunningLoan(loan.loan_id);
    setNote(null);
    try {
      await apiPost(`/api/processes/${stageNo}/run`, { loan_id: loan.loan_id });
      setNote(`Running ${loan.loan_id}…`);
      refresh();
    } catch (err) {
      setNote(err.message);
    } finally {
      setRunningLoan(null);
    }
  }

  if (isLoading)
    return (
      <div className="flex items-center gap-2 py-12 justify-center" style={mutedFg}>
        <LoaderCircle size={18} className="animate-spin" /> Loading…
      </div>
    );
  if (isError || !data)
    return (
      <div className="flex items-center gap-2 py-12 justify-center" style={mutedFg}>
        <CircleAlert size={18} /> Could not load this process.
      </div>
    );

  return (
    <div className="px-2 sm:px-6 py-6 max-w-7xl mx-auto flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="font-sans text-xs uppercase tracking-widest" style={mutedFg}>
            Process {stageNo} of 5
          </p>
          <h1 className="font-serif text-2xl font-semibold tracking-tight" style={fg}>
            {nav?.label ?? data.name}
          </h1>
          <p className="font-sans text-sm mt-1 max-w-3xl" style={mutedFg}>
            {nav?.description}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1.5">
          <PrimaryButton
            onClick={run}
            busy={busy}
            disabled={!data.playbook}
            title={data.playbook ? "Run this stage for every case waiting at it (and re-check cases in a re-runnable status)" : "No playbook for this stage yet"}
          >
            Run {data.name}
            {data.playbook && data.runnable > 0 ? ` (${data.runnable})` : ""}
          </PrimaryButton>
          <span className="font-sans text-xs" style={mutedFg}>
            {note ?? (data.playbook ? `${data.agent} · rules v${data.rules_version}` : "Playbook not built yet")}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
        {Object.entries(data.counts).map(([status, n]) => (
          <Tile
            key={status}
            label={status}
            value={n}
            color={statusColor(status)}
            active={filter === status}
            onClick={() => setFilter(filter === status ? null : status)}
          />
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_380px] gap-6 items-start">
        <section className="flex flex-col gap-2 min-w-0">
          <div className="flex items-center justify-between">
            <h2 className="font-sans text-xs font-semibold uppercase tracking-widest" style={mutedFg}>
              Cases {filter ? `· ${filter}` : "at this stage"} ({loans.length})
            </h2>
            {data.paused > 0 && (
              <Link href="/decision-inbox" className="inline-flex items-center gap-1 font-sans text-xs hover:underline" style={{ color: "hsl(var(--primary))" }}>
                <Inbox size={13} /> {data.paused} waiting for review
              </Link>
            )}
          </div>
          <RunTable
            columns={["Loan", "Borrower", "Status", "Remark", "Last run"]}
            empty={loans.length === 0 ? (filter ? "No cases." : "No case has reached this stage yet.") : null}
          >
            {loans.map((l) => (
              <tr
                key={l.loan_id}
                onClick={() => setOpenLoan(l)}
                className="cursor-pointer hover:brightness-[0.97]"
                title={CaseDrawer ? "View the checks, plans and records for this case" : "Open documents and compare with MSP"}
                style={{ background: "hsl(var(--card))", borderBottom: "1px solid hsl(var(--border))" }}
              >
                <td className="px-4 py-2.5 font-mono text-xs" style={mutedFg}>{l.loan_id}</td>
                <td className="px-4 py-2.5 whitespace-nowrap" style={fg}>{CaseDrawer ? (
                  <button className="text-left hover:underline" onClick={(event) => { event.stopPropagation(); setOpenLoan(l); }}
                    aria-label={`View case details for ${l.borrower_name}, loan ${l.loan_id}`}>{l.borrower_name}</button>
                ) : l.borrower_name}</td>
                <td className="px-4 py-2.5">
                  {l.open_decision_id ? (
                    <Link href={`/decision-inbox/${l.open_decision_id}`} onClick={(e) => e.stopPropagation()}><StatusPill status={label(l)} /></Link>
                  ) : (
                    <StatusPill status={label(l)} />
                  )}
                </td>
                <td className="px-4 py-2.5 text-xs max-w-md" style={mutedFg} title={l.remark}>
                  <span className="line-clamp-2">{l.remark || "—"}</span>
                </td>
                <td className="px-4 py-2.5 whitespace-nowrap">
                  {l.last_run_status ? (
                    <span className="flex flex-col">
                      <RunStatus status={l.last_run_status} />
                      <span className="text-[11px]" style={mutedFg}>{timeAgo(l.last_run_at)}</span>
                    </span>
                  ) : (
                    <span className="text-xs" style={mutedFg}>—</span>
                  )}
                </td>
              </tr>
            ))}
          </RunTable>
          {!filter && notReached > 0 && (
            <button onClick={() => setFilter("Not reached")} className="self-start font-sans text-xs hover:underline" style={mutedFg}>
              {notReached} case{notReached === 1 ? " has" : "s have"} not reached this stage yet — show
            </button>
          )}
        </section>

        <Card className="flex flex-col gap-3 lg:sticky lg:top-4">
          <div className="flex items-center gap-2">
            <FileCode2 size={15} style={{ color: "hsl(var(--primary))" }} />
            <h2 className="font-sans text-sm font-semibold" style={fg}>
              Playbook
            </h2>
            {playbook && (
              <span className="font-mono text-[11px] ml-auto" style={mutedFg}>
                harness/{playbook.process}/playbook.yaml
              </span>
            )}
          </div>
          {playbook ? (
            <PlaybookFlow playbook={playbook} />
          ) : (
            <p className="font-sans text-sm" style={mutedFg}>
              No playbook yet. Cases that reach this stage wait here (blocked) until{" "}
              <code className="font-mono text-xs">harness/&lt;process&gt;/playbook.yaml</code> is added — then auto-flow continues them.
            </p>
          )}
        </Card>
      </div>
      {CaseDrawer && openLoan ? <CaseDrawer key={openLoan.loan_id}
        loan={data.loans.find((l) => l.loan_id === openLoan.loan_id) ?? openLoan}
        onClose={() => setOpenLoan(null)} onDocuments={(loan) => { setOpenLoan(null); setDocumentLoan(loan); }}
        onRun={() => runLoan(openLoan)} running={runningLoan === openLoan.loan_id} /> : null}
      <LoanDrawer loanId={CaseDrawer ? documentLoan?.loan_id : openLoan?.loan_id}
        borrowerName={CaseDrawer ? documentLoan?.borrower_name : openLoan?.borrower_name}
        onClose={() => { setOpenLoan(null); setDocumentLoan(null); }} />
    </div>
  );
}
