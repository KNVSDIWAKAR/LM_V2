// Shared pieces for the End-to-End page and the five process pages (backend routes/processes.py, routes/workflow.py).
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleDot, Flag, LoaderCircle, Play, UserRound, Zap } from "lucide-react";
import { apiGet, apiPost } from "../../lib/api";
import { timeAgo } from "../../lib/utils";

export const mutedFg = { color: "hsl(var(--muted-foreground))" };
export const fg = { color: "hsl(var(--foreground))" };

const GOOD = "hsl(142, 60%, 32%)";
const WARN = "hsl(32, 90%, 38%)";
const BAD = "hsl(0, 72%, 48%)";
const IDLE = "hsl(var(--muted-foreground))";

/** Colour for an lm_stages status. Advancing statuses are green, people-needed amber, stops red. */
export function statusColor(status) {
  if (!status || status === "Not reached" || status === "Not started") return IDLE;
  if (status === "Waiting") return "hsl(217, 80%, 45%)";
  if (/^(Complete|Completed|Facially Complete|Ready|Within Plan|Signed Off|Recording)$/.test(status)) return GOOD;
  if (/Human Review|Progress|Hold|Delayed/.test(status)) return WARN;
  return BAD;
}

export function StatusPill({ status }) {
  const color = statusColor(status);
  return (
    <span
      className="inline-block font-sans text-xs font-medium px-2 py-0.5 rounded-full border whitespace-nowrap"
      style={{ color, borderColor: color }}
    >
      {status || "Not reached"}
    </span>
  );
}

export function PrimaryButton({ onClick, disabled, busy, icon: Icon = Play, children, title }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled || busy}
      title={title}
      className="inline-flex items-center gap-1.5 font-sans text-sm font-medium px-3 py-1.5 rounded-md transition-opacity hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
      style={{ background: "hsl(var(--primary))", color: "hsl(var(--primary-foreground))" }}
    >
      {busy ? <LoaderCircle size={14} className="animate-spin" /> : <Icon size={14} />}
      {children}
    </button>
  );
}

/** Invalidate everything a run can change, now and again once the background work has had time to land. */
export function useRefreshRuns() {
  const qc = useQueryClient();
  return () => {
    const keys = ["processes", "process", "workflow-runs", "agent-runs", "decisions", "auto-flow"];
    const go = () => keys.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
    go();
    [1500, 4000, 9000].forEach((ms) => setTimeout(go, ms));
  };
}

/** "Run end-to-end" + the auto-flow switch. */
export function WorkflowControls() {
  const refresh = useRefreshRuns();
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState(null);
  const { data: auto } = useQuery({ queryKey: ["auto-flow"], queryFn: () => apiGet("/api/workflow/auto"), refetchInterval: 10000 });
  const qc = useQueryClient();

  async function runAll() {
    setBusy(true);
    setNote(null);
    try {
      const r = await apiPost("/api/workflow/run", {});
      setNote(r.queued ? `${r.queued} case${r.queued === 1 ? "" : "s"} started` : "Nothing waiting — every case is running, paused, or done");
      refresh();
    } catch (err) {
      setNote(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function toggle() {
    const next = await fetch("/api/workflow/auto", {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ enabled: !auto?.enabled }),
    }).then((r) => r.json());
    qc.setQueryData(["auto-flow"], next);
  }

  return (
    <div className="flex flex-col items-end gap-1.5">
      <div className="flex flex-wrap items-center justify-end gap-2">
        {auto && (
          <button
            onClick={toggle}
            className="inline-flex items-center gap-1.5 font-sans text-xs font-medium px-2.5 py-1.5 rounded-md border"
            style={{ borderColor: auto.enabled ? GOOD : "hsl(var(--border))", color: auto.enabled ? GOOD : IDLE, background: "hsl(var(--card))" }}
            title={`Every ${auto.interval_seconds}s, new cases start and unblocked cases continue on their own`}
          >
            <Zap size={13} />
            Auto-flow {auto.enabled ? "on" : "off"}
          </button>
        )}
        <PrimaryButton onClick={runAll} busy={busy}>
          Run end-to-end
        </PrimaryButton>
      </div>
      <span className="font-sans text-xs" style={mutedFg}>
        {note ?? (auto?.last_tick ? `Last auto-flow check ${timeAgo(auto.last_tick)} · moved ${auto.last_moved}` : auto?.enabled ? "Auto-flow is watching for new cases" : "")}
      </span>
    </div>
  );
}

const KIND_ICON = { run: CircleDot, gate: UserRound, end: Flag };

/** The playbook as the steps it runs, each with where each outcome leads.
 *  Pass an agent run's `trace` to highlight the path one loan took and what each step found. */
export function PlaybookFlow({ playbook, trace }) {
  const visited = Object.fromEntries((trace ?? []).map((t) => [t.node, t]));
  const traced = !!trace;
  const work = playbook.nodes.filter((n) => n.kind !== "end");
  const ends = playbook.nodes.filter((n) => n.kind === "end");
  const titleOf = Object.fromEntries(playbook.nodes.map((n) => [n.id, n.title]));

  return (
    <div className="flex flex-col gap-3">
      <ol className="flex flex-col gap-2">
        {work.map((n) => {
          const Icon = KIND_ICON[n.kind];
          const isGate = n.kind === "gate";
          const step = visited[n.id];
          return (
            <li
              key={n.id}
              className="rounded-md border px-3 py-2.5 transition-opacity"
              style={{
                borderColor: step ? "hsl(var(--primary))" : isGate ? "hsl(0, 60%, 80%)" : "hsl(var(--border))",
                borderWidth: step ? 2 : 1,
                background: isGate ? "hsl(0, 80%, 98%)" : "hsl(var(--card))",
                opacity: traced && !step ? 0.45 : 1,
              }}
            >
              <div className="flex items-center gap-2">
                <Icon size={14} style={{ color: isGate ? BAD : "hsl(var(--primary))" }} />
                <span className="font-sans text-sm font-medium" style={fg}>
                  {n.title}
                </span>
                <span className="font-mono text-[11px] ml-auto" style={mutedFg}>
                  {n.run ?? (isGate ? `gate · ${n.team}` : n.id)}
                </span>
              </div>
              {step?.detail && (
                <p className="font-sans text-xs mt-1 pl-6" style={fg}>
                  {step.detail}
                </p>
              )}
              <div className="flex flex-wrap gap-1.5 mt-1.5 pl-6">
                {Object.entries(n.routes).map(([outcome, target]) => (
                  <span
                    key={outcome}
                    className="font-sans text-[11px] px-1.5 py-0.5 rounded"
                    style={
                      step && step.next === target
                        ? { background: "hsl(var(--primary))", color: "hsl(var(--primary-foreground))" }
                        : { background: "hsl(var(--muted))", ...mutedFg }
                    }
                  >
                    {outcome === "next" ? "→" : `${outcome} →`} <span>{titleOf[target]?.replace(/^\d · /, "") ?? target}</span>
                  </span>
                ))}
              </div>
            </li>
          );
        })}
      </ol>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="font-sans text-xs" style={mutedFg}>
          Ends with:
        </span>
        {ends.map((n) => (
          <span
            key={n.id}
            title={n.advance ? "Moves the loan to the next stage" : "The loan stops here"}
            style={{ opacity: traced && !visited[n.id] ? 0.35 : 1 }}
          >
            <StatusPill status={n.status} />
          </span>
        ))}
      </div>
    </div>
  );
}
