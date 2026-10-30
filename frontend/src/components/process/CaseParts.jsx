// Shared pieces of the Trial UW / Trial Monitoring / Final UW & Closing case drawers (backend routes/cases.py).
import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { FileSearch, LoaderCircle, Play, X } from "lucide-react";
import { Link } from "wouter";
import Card from "../ui/Card";
import { PrimaryButton, StatusPill, fg, mutedFg } from "./ProcessParts";
import { RunStatus } from "../runs/RunPrimitives";
import { apiGet } from "../../lib/api";
import { RESULT_LABEL, countFindings, resultColor } from "../../lib/caseDetails";
import { timeAgo } from "../../lib/utils";

/** The case for one loan at stage 3, 4 or 5, refreshed while the drawer is open. */
export function useStageCase(stageNo, loanId) {
  return useQuery({
    queryKey: ["stage-case", stageNo, loanId],
    queryFn: () => apiGet(`/api/cases/${stageNo}/${encodeURIComponent(loanId)}`),
    refetchInterval: 5000,
  });
}

/** Slide-over with focus trap, Escape to close, header and footer. */
export function CaseDrawerShell({ title, subtitle, status, onClose, footer, children, width = 880 }) {
  const panel = useRef(null);
  const close = useRef(onClose);
  close.current = onClose;

  useEffect(() => {
    const previous = document.activeElement;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panel.current?.focus();
    const keydown = (event) => {
      if (event.key === "Escape") close.current();
      if (event.key !== "Tab") return;
      const elements = panel.current?.querySelectorAll('button:not([disabled]), a[href], summary, input, select, textarea, [tabindex="0"]');
      if (!elements?.length) return;
      const first = elements[0], last = elements[elements.length - 1];
      if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first.focus();
      }
    };
    window.addEventListener("keydown", keydown);
    return () => {
      document.body.style.overflow = overflow;
      window.removeEventListener("keydown", keydown);
      previous?.focus();
    };
  }, []);

  return <>
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="fixed inset-0 z-40" style={{ background: "rgba(0,0,0,0.3)" }} onClick={onClose} />
    <motion.aside ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="case-drawer-title"
      initial={{ x: "100%" }} animate={{ x: 0 }} transition={{ type: "spring", stiffness: 320, damping: 34 }}
      className="fixed right-0 top-0 h-full z-50 flex flex-col outline-none shadow-2xl"
      style={{ width: `min(${width}px, 100vw)`, background: "hsl(var(--background))", borderLeft: "1px solid hsl(var(--border))" }}>
      <header className="flex items-start justify-between gap-3 px-6 py-5 border-b" style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--card))" }}>
        <div className="min-w-0">
          <p className="font-mono text-xs mb-1" style={mutedFg}>{subtitle}</p>
          <h2 id="case-drawer-title" className="font-serif text-2xl mb-2" style={fg}>{title}</h2>
          <StatusPill status={status} />
        </div>
        <button onClick={onClose} className="p-2 rounded hover:bg-black/5" aria-label="Close case"><X size={20} /></button>
      </header>
      <div className="flex-1 overflow-y-auto p-6 space-y-5">{children}</div>
      {footer && <footer className="border-t px-6 py-4 flex flex-wrap items-center gap-3" style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--card))" }}>{footer}</footer>}
    </motion.aside>
  </>;
}

export function CaseLoading({ query, label }) {
  if (query.isLoading) return <p className="flex items-center gap-2" style={mutedFg}><LoaderCircle size={16} className="animate-spin" /> Loading {label}…</p>;
  if (query.isError) return <p role="alert" style={fg}>Could not load this case. <button className="underline" onClick={() => query.refetch()}>Try again</button></p>;
  return null;
}

export function Section({ title, count, children, aside }) {
  return (
    <section className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-sans text-xs font-semibold uppercase tracking-widest" style={mutedFg}>
          {title}{count != null ? ` (${count})` : ""}
        </h3>
        {aside}
      </div>
      {children}
    </section>
  );
}

export function ResultBadge({ result }) {
  return (
    <span className="text-[11px] font-semibold uppercase shrink-0" style={{ color: resultColor(result) }}>
      {RESULT_LABEL[result] ?? result ?? "Not recorded"}
    </span>
  );
}

/** Each check the agent ran, with the value and source it used. */
export function FindingList({ findings, empty = "No check results were saved for this run." }) {
  if (!findings?.length) return <p className="text-sm" style={mutedFg}>{empty}</p>;
  return (
    <div className="rounded-md border divide-y" style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--card))" }}>
      {findings.map((f, i) => (
        <div key={`${f.check}-${i}`} className="px-4 py-2.5 flex items-start gap-3" style={{ borderColor: "hsl(var(--border))" }}>
          <div className="min-w-0 flex-1">
            <p className="font-sans text-sm font-medium" style={fg}>{f.check}</p>
            <p className="font-sans text-xs mt-0.5" style={mutedFg}>{f.detail}</p>
            {(f.source || f.document || f.reason_codes?.length) && (
              <p className="font-mono text-[11px] mt-1" style={mutedFg}>
                {[f.source, f.document, ...(f.reason_codes ?? [])].filter(Boolean).join(" · ")}
              </p>
            )}
          </div>
          <ResultBadge result={f.result} />
        </div>
      ))}
    </div>
  );
}

const GRID_COLS = { 2: "sm:grid-cols-2", 3: "sm:grid-cols-3", 4: "sm:grid-cols-4" };

export function KeyValues({ rows, columns = 3 }) {
  return (
    <dl className={`grid grid-cols-2 ${GRID_COLS[columns]} gap-x-4 gap-y-3 text-sm`}>
      {rows.map(([label, value]) => (
        <div key={label} className="min-w-0">
          <dt className="text-xs" style={mutedFg}>{label}</dt>
          <dd className="mt-0.5 break-words" style={fg}>{value ?? "Not recorded"}</dd>
        </div>
      ))}
    </dl>
  );
}

/** The latest run: when, which rules, what it concluded, and a count of results. */
export function LatestRunCard({ run, remark, emptyText }) {
  if (!run) return <Card><p className="text-sm" style={mutedFg}>{emptyText}</p></Card>;
  const counts = countFindings(run.findings);
  return (
    <Card className="space-y-2">
      <div className="flex flex-wrap justify-between gap-2">
        <span className="font-mono text-xs" style={mutedFg}>{run.id}</span>
        <RunStatus status={run.status} />
      </div>
      <p className="text-xs" style={mutedFg}>
        Evaluated {new Date(run.started_at).toLocaleString()} · rules v{run.rules_version ?? "not recorded"} · {run.trigger}
      </p>
      <p className="text-sm" style={fg}>{run.paused_at?.reason || remark || run.outcome || "—"}</p>
      {run.error && <p role="alert" className="text-sm" style={{ color: resultColor("fail") }}>{run.error}</p>}
      <p className="text-sm" style={fg}>
        {counts.pass} passed · {counts.fail} failed · {counts.review} need review{counts.other ? ` · ${counts.other} informational` : ""}
      </p>
    </Card>
  );
}

export function RunHistory({ runs }) {
  if (!runs?.length || runs.length < 2) return null;
  return (
    <details>
      <summary className="cursor-pointer font-sans text-xs font-semibold uppercase tracking-widest" style={mutedFg}>Run history ({runs.length})</summary>
      <ul className="mt-2 space-y-1">
        {runs.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center gap-3 text-xs" style={mutedFg}>
            <span className="font-mono">{r.id}</span>
            <RunStatus status={r.status} />
            <span style={fg}>{r.outcome ?? "—"}</span>
            <span>{timeAgo(r.started_at)}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}

/** Footer: documents, open decision, and re-run when the loan can run at this stage. */
export function CaseFooter({ loan, data, onDocuments, onClose, onRun, running, runnable, runLabel = "Run again" }) {
  return <>
    <PrimaryButton icon={FileSearch} onClick={() => onDocuments(loan)}>View documents</PrimaryButton>
    {runnable && <PrimaryButton icon={Play} busy={running} onClick={onRun}>{runLabel}</PrimaryButton>}
    {data?.open_decision_id && (
      <Link href={`/decision-inbox/${data.open_decision_id}`} onClick={onClose} className="text-sm underline" style={fg}>
        Open Decision Inbox
      </Link>
    )}
  </>;
}
