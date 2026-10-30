import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { Link, useSearch } from "wouter";
import { PageHeader, StatCard } from "../components/ui/Card";
import UnderlineTabs from "../components/ui/UnderlineTabs";
import { JsonBlock, RunStatus, RunTable, fg, formatMs, formatTime, mutedFg } from "../components/runs/RunPrimitives";
import { apiGet } from "../lib/api";

function MetaRow({ label, value }) {
  return (
    <>
      <span className="font-sans text-xs font-medium uppercase tracking-wider" style={mutedFg}>
        {label}
      </span>
      <span className="font-sans text-sm break-words" style={fg}>
        {value}
      </span>
    </>
  );
}

function RunDrawer({ run, onClose }) {
  return (
    <>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-40"
        style={{ background: "rgba(0,0,0,0.25)" }}
        onClick={onClose}
      />
      <motion.div
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ type: "spring", stiffness: 320, damping: 32 }}
        className="fixed right-0 top-0 h-full z-50 flex flex-col overflow-hidden"
        style={{ width: "min(520px, 100vw)", background: "hsl(var(--card))", borderLeft: "1px solid hsl(var(--border))" }}
      >
        <div className="flex items-start justify-between px-6 py-4 border-b" style={{ borderColor: "hsl(var(--border))" }}>
          <div>
            <h2 className="font-serif text-lg leading-tight" style={fg}>
              {run.agent_name}
            </h2>
            <p className="mt-0.5 font-mono text-xs" style={mutedFg}>
              {run.id}
            </p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded" style={mutedFg} aria-label="Close">
            <X size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-5 flex flex-col gap-6">
          <div className="grid grid-cols-2 gap-x-4 gap-y-2">
            <MetaRow label="Stage" value={`${run.stage_no}. ${run.stage_name}`} />
            <MetaRow label="Status" value={<RunStatus status={run.status} />} />
            <MetaRow label="Loan" value={run.loan_id ?? "All loans"} />
            <MetaRow label="Trigger" value={run.trigger} />
            <MetaRow label="Started" value={formatTime(run.started_at)} />
            <MetaRow label="Finished" value={formatTime(run.finished_at)} />
            <MetaRow label="Duration" value={formatMs(run.duration_ms)} />
            <MetaRow
              label="Workflow"
              value={
                run.workflow_run_id ? (
                  <Link href="/workflow-runs" className="font-mono text-xs hover:underline" style={{ color: "hsl(var(--primary))" }}>
                    {run.workflow_run_id}
                  </Link>
                ) : (
                  "Standalone"
                )
              }
            />
          </div>
          {run.error && (
            <p className="rounded p-3 text-sm font-sans" style={{ background: "hsl(0, 90%, 97%)", color: "hsl(0, 70%, 40%)" }}>
              {run.error}
            </p>
          )}
          <JsonBlock title="Input" value={run.input} />
          <JsonBlock title="Output" value={run.output} />
          {run.trace.length > 0 && <JsonBlock title={`Trace (${run.trace.length} steps)`} value={run.trace} />}
        </div>
      </motion.div>
    </>
  );
}

const TAB_DEFS = [
  { key: "all", label: "All" },
  { key: "running", label: "Running" },
  { key: "paused", label: "Paused" },
  { key: "completed", label: "Completed" },
  { key: "failed", label: "Failed" },
];

export default function AgentRuns() {
  const [tab, setTab] = useState("all");
  const [selected, setSelected] = useState(null);
  const workflowId = new URLSearchParams(useSearch()).get("workflow");
  const { data: runs = [], isLoading, isError } = useQuery({
    queryKey: ["agent-runs", workflowId],
    queryFn: () => apiGet(`/api/agent-runs${workflowId ? `?workflow_run_id=${encodeURIComponent(workflowId)}` : ""}`),
    refetchInterval: 5000,
  });

  const count = (status) => runs.filter((r) => r.status === status).length;
  const visible = tab === "all" ? runs : runs.filter((r) => r.status === tab);
  const tabs = TAB_DEFS.map((t) => ({ ...t, count: t.key === "all" ? runs.length : count(t.key) }));

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Agent Runs" subtitle="One agent working one loss-mitigation stage — standalone or as a step of a workflow run" />

      {workflowId && (
        <div className="flex items-center justify-between gap-3 rounded px-3 py-2 font-sans text-sm" style={{ background: "hsl(var(--muted))", ...fg }}>
          <span>
            Agent runs of workflow <span className="font-mono text-xs">{workflowId}</span>
          </span>
          <Link href="/agent-runs" className="text-xs hover:underline" style={{ color: "hsl(var(--primary))" }}>
            Show all
          </Link>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard value={runs.length} label="Runs" />
        <StatCard value={count("paused")} label="Paused · review" />
        <StatCard value={count("completed")} label="Completed" />
        <StatCard value={count("failed")} label="Failed" />
      </div>

      <UnderlineTabs tabs={tabs} value={tab} onChange={setTab} />

      {isLoading && <p className="font-sans text-sm" style={mutedFg}>Loading runs…</p>}
      {isError && <p className="font-sans text-sm text-red-600">Failed to load agent runs.</p>}
      {!isLoading && !isError && (
        <RunTable
          columns={["Run", "Stage", "Agent", "Loan", "Status", "Started", "Duration", "Workflow"]}
          empty={visible.length === 0 ? "No agent runs recorded yet." : null}
        >
          {visible.map((run) => (
            <tr
              key={run.id}
              onClick={() => setSelected(run)}
              className="cursor-pointer hover:brightness-95"
              style={{ background: "hsl(var(--card))", borderBottom: "1px solid hsl(var(--border))" }}
            >
              <td className="px-4 py-3 font-mono text-xs" style={{ color: "hsl(var(--primary))" }}>{run.id.slice(-8)}</td>
              <td className="px-4 py-3 whitespace-nowrap" style={fg}>{run.stage_no}. {run.stage_name}</td>
              <td className="px-4 py-3" style={fg}>{run.agent_name}</td>
              <td className="px-4 py-3 font-mono text-xs" style={mutedFg}>{run.loan_id ?? "All"}</td>
              <td className="px-4 py-3"><RunStatus status={run.status} /></td>
              <td className="px-4 py-3 text-xs whitespace-nowrap" style={mutedFg}>{formatTime(run.started_at)}</td>
              <td className="px-4 py-3 text-xs tabular-nums" style={mutedFg}>{formatMs(run.duration_ms)}</td>
              <td className="px-4 py-3 font-mono text-xs" style={mutedFg}>{run.workflow_run_id?.slice(-8) ?? "—"}</td>
            </tr>
          ))}
        </RunTable>
      )}

      <AnimatePresence>{selected && <RunDrawer key={selected.id} run={selected} onClose={() => setSelected(null)} />}</AnimatePresence>
    </div>
  );
}
