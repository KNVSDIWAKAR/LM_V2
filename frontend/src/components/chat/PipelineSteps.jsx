import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  BookOpen,
  Brain,
  Check,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  CircleCheckBig,
  Compass,
  Cpu,
  FilePlus,
  FileSearch,
  LoaderCircle,
  Network,
  ShieldAlert,
  Sparkles,
  Terminal,
  X,
} from "lucide-react";

export const STEP_TYPE_ICONS = {
  agent_init: { icon: Cpu, color: "text-gray-500" },
  skill_discovery: { icon: Compass, color: "text-blue-600" },
  skill_load: { icon: BookOpen, color: "text-indigo-600" },
  memory_load: { icon: Brain, color: "text-purple-600" },
  file_read: { icon: FileSearch, color: "text-teal-600" },
  file_write: { icon: FilePlus, color: "text-green-600" },
  tool_exec: { icon: Terminal, color: "text-amber-600" },
  llm_thinking: { icon: Sparkles, color: "text-violet-500" },
  output_ready: { icon: CircleCheckBig, color: "text-green-600" },
  error: { icon: CircleAlert, color: "text-red-600" },
  wiki_update: { icon: Network, color: "text-purple-600" },
};

export function StepTypeIcon({ type }) {
  const { icon: Icon, color } = STEP_TYPE_ICONS[type] ?? { icon: Cpu, color: "text-gray-400" };
  return <Icon size={16} className={color} aria-hidden="true" />;
}

export function formatDuration(ms) {
  return ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(1)}s`;
}

function StepStatusIcon({ status }) {
  if (status === "running") {
    return (
      <motion.span
        animate={{ rotate: 360 }}
        transition={{ repeat: Infinity, duration: 1, ease: "linear" }}
        style={{ display: "inline-flex" }}
      >
        <LoaderCircle size={14} style={{ color: "hsl(var(--info))" }} aria-label="Running" />
      </motion.span>
    );
  }
  if (status === "completed") return <Check size={14} className="text-green-600" aria-label="Completed" />;
  if (status === "blocked")
    return <ShieldAlert size={14} className="text-amber-500" aria-label="Blocked — routed to Decision Inbox" />;
  return <X size={14} style={{ color: "hsl(var(--destructive))" }} aria-label="Failed" />;
}

export const darkPreStyle = {
  background: "hsl(25, 30%, 15%)",
  color: "hsl(36, 20%, 80%)",
  fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
  fontSize: "13px",
  borderRadius: "var(--radius)",
};

function PipelineStep({ step }) {
  const [open, setOpen] = useState(false);
  const hasContent = Boolean(step.content);
  const duration = step.duration != null ? formatDuration(step.duration) : null;

  const labelColor =
    step.status === "running"
      ? "hsl(var(--muted-foreground))"
      : step.status === "failed"
        ? "hsl(var(--destructive))"
        : "hsl(var(--foreground))";

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }}>
      <div className="flex items-center gap-2 py-1 px-2 rounded" style={{ minHeight: "28px" }}>
        <span className="flex-none">
          <StepTypeIcon type={step.type} />
        </span>
        <span className="flex-none">
          <StepStatusIcon status={step.status} />
        </span>
        <span className="flex-1 text-sm font-sans truncate" style={{ color: labelColor }}>
          {step.label}
        </span>
        {duration && (
          <span className="flex-none text-xs font-sans tabular-nums" style={{ color: "hsl(var(--muted-foreground))" }}>
            {duration}
          </span>
        )}
        {hasContent && (
          <button
            onClick={() => setOpen((v) => !v)}
            className="flex-none p-0.5 rounded transition-colors"
            style={{ color: "hsl(var(--muted-foreground))" }}
            aria-label={open ? "Collapse details" : "Expand details"}
          >
            {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
        )}
      </div>
      <AnimatePresence>
        {open && hasContent && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="ml-8 mr-2 mb-1 mt-0.5">
              <pre className="rounded text-xs overflow-x-auto p-3 whitespace-pre-wrap break-words" style={darkPreStyle}>
                {step.content}
              </pre>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

const stepListStyle = {
  borderColor: "hsl(var(--border))",
  background: "hsl(var(--card))",
  borderRadius: "var(--radius)",
};

export default function PipelineSteps({ steps, isStreaming }) {
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    if (isStreaming) setCollapsed(false);
  }, [isStreaming]);

  if (steps.length === 0) return null;

  if (isStreaming) {
    return (
      <div className="mb-3 rounded border py-1" style={stepListStyle}>
        {steps.map((step) => (
          <PipelineStep key={step.id} step={step} />
        ))}
      </div>
    );
  }

  return (
    <div className="mb-3">
      <button
        onClick={() => setCollapsed((v) => !v)}
        className="flex items-center gap-2 text-xs font-sans py-1 px-2 rounded transition-colors w-full text-left"
        style={{ color: "hsl(var(--muted-foreground))", background: "transparent" }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "hsl(var(--muted))")}
        onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
      >
        {collapsed ? <ChevronRight size={14} aria-hidden="true" /> : <ChevronDown size={14} aria-hidden="true" />}
        <span className="uppercase tracking-wide font-medium text-xs">
          {steps.length} {steps.length === 1 ? "STEP" : "STEPS"} COMPLETED
        </span>
      </button>
      <AnimatePresence>
        {!collapsed && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="rounded border mt-1 py-1" style={stepListStyle}>
              {steps.map((step) => (
                <PipelineStep key={step.id} step={step} />
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
