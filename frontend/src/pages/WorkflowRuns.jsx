import { Fragment, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Link } from "wouter";
import { PageHeader, StatCard } from "../components/ui/Card";
import UnderlineTabs from "../components/ui/UnderlineTabs";
import { RunStatus, RunTable, fg, formatMs, formatTime, mutedFg } from "../components/runs/RunPrimitives";
import { apiGet } from "../lib/api";

/** The five stages of one workflow run, each with the agent run behind it (or "Not run"). */
function StageStrip({ runId, stages }) {
  const { data, isLoading } = useQuery({
    queryKey: ["workflow-run", runId],
    queryFn: () => apiGet(`/api/workflow-runs/${runId}`),
    refetchInterval: 5000,
  });
  if (isLoading || !data) return <p className="font-sans text-xs" style={mutedFg}>Loading stages…</p>;
  const byStage = Object.fromEntries(data.agent_runs.map((a) => [a.stage_no, a]));

  return (
    <div className="flex flex-col gap-2">
      <div className="grid gap-2 grid-cols-1 sm:grid-cols-5">
        {stages.map((stage) => {
          const run = byStage[stage.stage_no];
          return (
            <div key={stage.stage_no} className="rounded-md border p-2.5 flex flex-col gap-1 min-w-0" style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--card))" }}>
              <span className="font-sans text-[11px] uppercase tracking-wider" style={mutedFg}>
                Stage {stage.stage_no}
              </span>
              <span className="font-sans text-sm font-medium truncate" style={fg}>{stage.stage_name}</span>
              <RunStatus status={run?.status ?? "none"} />
              {run && (
                <span className="font-sans text-xs truncate" style={mutedFg} title={run.agent_name}>
                  {run.agent_name} · {formatMs(run.duration_ms)}
                </span>
              )}
            </div>
          );
        })}
      </div>
      {data.agent_runs.length > 0 && (
        <Link href={`/agent-runs?workflow=${encodeURIComponent(runId)}`} className="font-sans text-xs hover:underline" style={{ color: "hsl(var(--primary))" }}>
          View the {data.agent_runs.length} agent run{data.agent_runs.length === 1 ? "" : "s"} →
        </Link>
      )}
    </div>
  );
}

const TAB_DEFS = [
  { key: "all", label: "All" },
  { key: "paused", label: "Paused" },
  { key: "blocked", label: "Blocked" },
  { key: "completed", label: "Completed" },
  { key: "failed", label: "Failed" },
];

export default function WorkflowRuns() {
  const [tab, setTab] = useState("all");
  const [open, setOpen] = useState({});
  const { data: runs = [], isLoading, isError } = useQuery({
    queryKey: ["workflow-runs"],
    queryFn: () => apiGet("/api/workflow-runs"),
    refetchInterval: 5000,
  });
  const { data: stages = [] } = useQuery({ queryKey: ["lm-stages"], queryFn: () => apiGet("/api/lm/stages") });

  const count = (status) => runs.filter((r) => r.status === status).length;
  const visible = tab === "all" ? runs : runs.filter((r) => r.status === tab);
  const tabs = TAB_DEFS.map((t) => ({ ...t, count: t.key === "all" ? runs.length : count(t.key) }));
  const columns = ["", "Loan", "Status", "Outcome", "Stages", "Trigger", "Started", "Duration"];

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Workflow Runs"
        subtitle="End-to-end Loss Mitigation runs — Intake → Retention Eligibility → Trial UW → Trial Monitoring → Closing, one agent run per stage"
      />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard value={runs.length} label="Workflow Runs" />
        <StatCard value={count("paused")} label="Paused · review" />
        <StatCard value={count("completed")} label="Completed" />
        <StatCard value={count("blocked")} label="Blocked" />
      </div>

      <UnderlineTabs tabs={tabs} value={tab} onChange={setTab} />

      {isLoading && <p className="font-sans text-sm" style={mutedFg}>Loading runs…</p>}
      {isError && <p className="font-sans text-sm text-red-600">Failed to load workflow runs.</p>}
      {!isLoading && !isError && (
        <RunTable columns={columns} empty={visible.length === 0 ? "No workflow runs recorded yet." : null}>
          {visible.map((run) => {
            const isOpen = !!open[run.id];
            return (
              <Fragment key={run.id}>
                <tr
                  onClick={() => setOpen((p) => ({ ...p, [run.id]: !isOpen }))}
                  className="cursor-pointer"
                  style={{ background: "hsl(var(--card))", borderBottom: "1px solid hsl(var(--border))" }}
                >
                  <td className="pl-4 py-3 w-6" style={mutedFg}>{isOpen ? <ChevronDown size={15} /> : <ChevronRight size={15} />}</td>
                  <td className="px-4 py-3">
                    <span className="font-mono text-xs" style={fg}>{run.loan_id ?? "All"}</span>
                    <p className="font-mono text-[11px]" style={mutedFg}>{run.id}</p>
                  </td>
                  <td className="px-4 py-3">
                    <RunStatus status={run.status} />
                    {run.error && <p className="font-sans text-xs mt-0.5 text-red-600">{run.error}</p>}
                  </td>
                  <td className="px-4 py-3 text-sm" style={fg}>{run.outcome || `At ${run.current_stage_name}`}</td>
                  <td className="px-4 py-3 tabular-nums text-xs" style={fg}>{run.stages_completed}/{run.stages_total}</td>
                  <td className="px-4 py-3 text-xs" style={mutedFg}>{run.requested_by || run.trigger}</td>
                  <td className="px-4 py-3 text-xs whitespace-nowrap" style={mutedFg}>{formatTime(run.started_at)}</td>
                  <td className="px-4 py-3 text-xs tabular-nums" style={mutedFg}>{formatMs(run.duration_ms)}</td>
                </tr>
                {isOpen && (
                  <tr style={{ background: "hsl(var(--muted))", borderBottom: "1px solid hsl(var(--border))" }}>
                    <td colSpan={columns.length} className="px-4 py-3">
                      <StageStrip runId={run.id} stages={stages} />
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </RunTable>
      )}
    </div>
  );
}
