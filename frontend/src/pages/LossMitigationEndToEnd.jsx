import { useQuery } from "@tanstack/react-query";
import { ArrowRight, ChevronRight, FileCode2, Inbox, Workflow } from "lucide-react";
import { Link } from "wouter";
import { WorkflowControls, fg, mutedFg, statusColor } from "../components/process/ProcessParts";
import { RunStatus, formatTime } from "../components/runs/RunPrimitives";
import { apiGet } from "../lib/api";
import { AUTOMATION_LABELS, LM_STEPS } from "../lib/lmPipelineModel";
import { PROCESSES } from "../lib/navigation";

const panel = { background: "hsl(var(--card))", borderColor: "hsl(var(--border))" };

const AUTOMATION_STYLES = {
  "automated-first-pass": { bg: "hsl(220 70% 50% / 0.12)", color: "hsl(220 70% 45%)" },
  "agent-augmented": { bg: "hsl(142 60% 35% / 0.13)", color: "hsl(142 60% 30%)" },
  "human-signoff": { bg: "hsl(38 92% 50% / 0.13)", color: "hsl(38 80% 35%)" },
  roadmap: { bg: "hsl(var(--muted) / 0.5)", color: "hsl(var(--muted-foreground))" },
  borrower: { bg: "hsl(var(--muted) / 0.3)", color: "hsl(var(--muted-foreground))" },
};

/** One of the five stages: playbook state, where its cases sit, and what is running or waiting. */
function StageCard({ stage }) {
  const nav = PROCESSES[stage.stage_no - 1];
  const total = Object.values(stage.counts).reduce((a, b) => a + b, 0);
  const worked = Object.entries(stage.counts).filter(([s, n]) => s !== "Not reached" && n > 0);
  return (
    <Link
      href={nav?.path ?? "/"}
      className="flex flex-col gap-3 rounded-lg border p-3 w-full min-w-0 transition-colors hover:brightness-[0.98]"
      style={{ ...panel, borderColor: stage.playbook ? "hsl(var(--primary) / 0.35)" : "hsl(var(--border))" }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-sans text-[11px] uppercase tracking-wider" style={mutedFg}>
            Process {stage.stage_no}
          </p>
          <p className="font-serif text-base leading-tight" style={fg}>
            {stage.name}
          </p>
        </div>
        <span
          className="inline-flex items-center gap-1 font-sans text-[11px] font-medium px-1.5 py-0.5 rounded shrink-0"
          style={stage.playbook ? { background: "hsl(142, 60%, 94%)", color: "hsl(142, 60%, 28%)" } : { background: "hsl(var(--muted))", ...mutedFg }}
          title={stage.playbook ? `${stage.agent} · rules v${stage.rules_version}` : "No playbook yet"}
        >
          <FileCode2 size={11} />
          {stage.playbook ? "Playbook live" : "Not built"}
        </span>
      </div>

      <div className="flex flex-col gap-1">
        {worked.length === 0 ? (
          <span className="font-sans text-xs" style={mutedFg}>
            No cases worked yet
          </span>
        ) : (
          worked.map(([status, n]) => (
            <div key={status} className="flex items-center justify-between gap-2">
              <span className="font-sans text-xs truncate" style={{ color: statusColor(status) }}>
                {status}
              </span>
              <span className="font-sans text-sm font-semibold tabular-nums" style={fg}>
                {n}
              </span>
            </div>
          ))
        )}
      </div>

      <div className="flex flex-wrap gap-x-3 gap-y-1 mt-auto pt-2 border-t font-sans text-[11px]" style={{ borderColor: "hsl(var(--border))", ...mutedFg }}>
        <span>
          {total - (stage.counts["Not reached"] ?? 0) - (stage.counts.Waiting ?? 0)} of {total} worked
        </span>
        {stage.running > 0 && <span style={{ color: "hsl(217, 91%, 50%)" }}>{stage.running} running</span>}
        {stage.paused > 0 && <span style={{ color: "hsl(32, 90%, 38%)" }}>{stage.paused} in review</span>}
      </div>
    </Link>
  );
}

function StageBoard() {
  const { data: stages = [], isLoading } = useQuery({ queryKey: ["processes"], queryFn: () => apiGet("/api/processes"), refetchInterval: 5000 });
  if (isLoading)
    return (
      <p className="font-sans text-sm" style={mutedFg}>
        Loading stages…
      </p>
    );
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
      {stages.map((stage, i) => (
        <div key={stage.stage_no} className="relative flex">
          <StageCard stage={stage} />
          {i < stages.length - 1 && (
            <ArrowRight size={14} className="hidden lg:block absolute -right-3.75 top-1/2 -translate-y-1/2" style={mutedFg} />
          )}
        </div>
      ))}
    </div>
  );
}

function RecentWorkflows() {
  const { data: runs = [] } = useQuery({ queryKey: ["workflow-runs"], queryFn: () => apiGet("/api/workflow-runs"), refetchInterval: 5000 });
  const paused = runs.filter((r) => r.status === "paused").length;
  return (
    <div className="rounded-lg border" style={panel}>
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 border-b" style={{ borderColor: "hsl(var(--border))" }}>
        <p className="font-sans text-xs font-semibold uppercase tracking-wide" style={mutedFg}>
          Latest cases ({runs.length} workflow runs)
        </p>
        <div className="flex items-center gap-3">
          {paused > 0 && (
            <Link href="/decision-inbox" className="inline-flex items-center gap-1 font-sans text-xs hover:underline" style={{ color: "hsl(32, 90%, 38%)" }}>
              <Inbox size={13} /> {paused} paused for review
            </Link>
          )}
          <Link href="/workflow-runs" className="inline-flex items-center font-sans text-xs hover:underline" style={{ color: "hsl(var(--primary))" }}>
            All workflow runs <ChevronRight size={13} />
          </Link>
        </div>
      </div>
      {runs.length === 0 ? (
        <p className="px-3 py-4 font-sans text-sm" style={mutedFg}>
          No workflow runs yet. Press Run end-to-end, or leave auto-flow on and new cases start by themselves.
        </p>
      ) : (
        <ul>
          {runs.slice(0, 8).map((r) => (
            <li key={r.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-2 border-b last:border-b-0" style={{ borderColor: "hsl(var(--border))" }}>
              <span className="font-mono text-xs w-24" style={mutedFg}>
                {r.loan_id}
              </span>
              <span className="w-36">
                <RunStatus status={r.status} />
              </span>
              <span className="font-sans text-sm flex-1 min-w-0 truncate" style={fg}>
                {r.outcome}
              </span>
              <span className="font-sans text-xs" style={mutedFg}>
                {formatTime(r.started_at)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function AutomationBadge({ automation }) {
  const style = AUTOMATION_STYLES[automation];
  return (
    <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-sans font-medium" style={{ background: style.bg, color: style.color }}>
      {AUTOMATION_LABELS[automation]}
    </span>
  );
}

function SystemChip({ name }) {
  return (
    <span className="inline-flex items-center rounded px-1.5 py-0.5 text-xs font-mono" style={{ background: "hsl(var(--muted) / 0.5)", ...mutedFg }}>
      {name}
    </span>
  );
}

function ProcessStep({ step }) {
  return (
    <div
      className="rounded-lg border p-3 space-y-1.5 transition-colors"
      style={{ background: "hsl(var(--card))", borderColor: step.linkedJourney ? "hsl(var(--primary) / 0.4)" : "hsl(var(--border))" }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-baseline gap-2 min-w-0">
          <span className="font-mono text-xs flex-none" style={mutedFg}>
            {step.id}
          </span>
          <span className="font-sans text-sm font-semibold truncate" style={fg}>
            {step.name}
          </span>
        </div>
        <AutomationBadge automation={step.automation} />
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <span className="font-sans text-xs" style={mutedFg}>
          {step.team}
        </span>
        {step.fte !== null && (
          <span className="font-sans text-xs font-medium" style={fg}>
            {step.fte} FTE
          </span>
        )}
        {step.ahtLabel !== "—" && (
          <span className="font-sans text-xs" style={mutedFg}>
            AHT {step.ahtLabel}
          </span>
        )}
      </div>
      {step.systems.length > 0 && (
        <div className="flex flex-wrap gap-1 pt-0.5">
          {step.systems.map((s) => (
            <SystemChip key={s} name={s} />
          ))}
        </div>
      )}
      {step.linkedJourney && (
        <div className="font-sans text-xs" style={{ color: "hsl(var(--primary))" }}>
          → Open process
        </div>
      )}
    </div>
  );
}

export default function LossMitigationEndToEnd() {
  return (
    <div className="px-2 sm:px-6 py-6 max-w-7xl mx-auto">
      <div className="space-y-5 pb-6">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div className="flex items-center gap-2">
              <Workflow size={20} style={{ color: "hsl(var(--primary))" }} />
              <h1 className="font-serif text-2xl tracking-tight" style={fg}>
                Loss Mitigation — End to End
              </h1>
            </div>
            <p className="font-sans text-sm mt-1 max-w-3xl" style={mutedFg}>
              Every case flows Intake → Retention Eligibility → Trial UW → Trial Monitoring → Closing. It pauses when a person must
              decide (Decision Inbox), continues once approved, and stops at a blocker.
            </p>
          </div>
          <WorkflowControls />
        </div>

        <StageBoard />
        <RecentWorkflows />

        <div className="rounded-lg border p-3" style={panel}>
          <p className="font-sans text-xs font-semibold uppercase tracking-wide mb-2" style={mutedFg}>
            The 12-step LM cycle · capability
          </p>
          <div className="flex flex-wrap gap-2">
            {Object.keys(AUTOMATION_LABELS).map((key) => (
              <AutomationBadge key={key} automation={key} />
            ))}
          </div>
        </div>

        <div className="space-y-2">
          {LM_STEPS.map((step) =>
            step.linkedJourney ? (
              <Link key={step.id} href={`/${step.linkedJourney}`} style={{ display: "block", textDecoration: "none" }}>
                <ProcessStep step={step} />
              </Link>
            ) : (
              <div key={step.id}>
                <ProcessStep step={step} />
              </div>
            ),
          )}
        </div>

        <p className="font-sans text-xs pb-6" style={mutedFg}>
          Current-state team / FTE / AHT figures are the client&apos;s own numbers from the Firstsource process documentation.
        </p>
      </div>
    </div>
  );
}
