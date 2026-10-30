import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, FileText, Shield, Zap } from "lucide-react";
import { apiGet } from "../../lib/api";
import { cn } from "../../lib/utils";

const mutedFg = { color: "hsl(var(--muted-foreground))" };

function CollapsibleSection({ title, count, children, defaultOpen = true }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-b last:border-b-0" style={{ borderColor: "hsl(var(--border))" }}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center justify-between w-full px-4 py-2.5 text-left transition-colors"
        style={{ background: "transparent" }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "hsl(var(--muted))")}
        onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
      >
        <div className="flex items-center gap-2">
          {open ? <ChevronDown size={14} style={mutedFg} /> : <ChevronRight size={14} style={mutedFg} />}
          <span
            className="text-xs font-medium font-sans tracking-wide uppercase"
            style={{ color: "hsl(var(--foreground))" }}
          >
            {title}
          </span>
        </div>
        <span
          className="text-xs font-sans font-medium rounded-full px-1.5 py-0.5 min-w-[20px] text-center"
          style={{ background: "hsl(var(--muted))", ...mutedFg }}
        >
          {count}
        </span>
      </button>
      {open && <div className="px-4 pb-3 pt-1">{children}</div>}
    </div>
  );
}

function Placeholder({ title, text }) {
  return (
    <CollapsibleSection title={title} count={0}>
      <p className="text-xs font-sans" style={mutedFg}>
        {text}
      </p>
    </CollapsibleSection>
  );
}

function ShowMore({ remaining, onClick, className = "mt-1.5" }) {
  return (
    <button onClick={onClick} className={cn(className, "text-xs font-sans underline")} style={mutedFg}>
      Show {remaining} More
    </button>
  );
}

function ActiveSkills({ activeSkill }) {
  const [expanded, setExpanded] = useState(false);
  const { data, isError, isLoading } = useQuery({
    queryKey: ["skills"],
    queryFn: () => apiGet("/api/skills"),
    retry: 1,
  });

  if (isLoading) return <Placeholder title="Active Skills" text="Loading..." />;
  if (isError || !data) return <Placeholder title="Active Skills" text="Unavailable" />;

  const visible = expanded ? data : data.slice(0, 4);
  const remaining = data.length - 4;

  return (
    <CollapsibleSection title="Active Skills" count={data.length}>
      <div className="flex flex-wrap gap-1.5">
        {visible.map((skill) => {
          const active = activeSkill === skill.name;
          return (
            <span
              key={skill.name}
              className={cn(
                "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-sans transition-all",
                active && "ring-1 ring-offset-1",
              )}
              style={{
                background: active ? "hsl(var(--primary) / 0.12)" : "hsl(var(--muted))",
                color: active ? "hsl(var(--primary))" : "hsl(var(--foreground))",
                animation: active ? "pulse 2s ease-in-out infinite" : undefined,
              }}
            >
              <span className="w-1.5 h-1.5 rounded-full flex-none" style={{ background: "hsl(142, 71%, 45%)" }} />
              {skill.name}
            </span>
          );
        })}
      </div>
      {!expanded && remaining > 0 && <ShowMore remaining={remaining} onClick={() => setExpanded(true)} className="mt-2" />}
    </CollapsibleSection>
  );
}

function DataFiles({ activeFiles }) {
  const [expanded, setExpanded] = useState(false);
  const { data, isError, isLoading } = useQuery({
    queryKey: ["knowledge-sources"],
    queryFn: () => apiGet("/api/knowledge/sources"),
    retry: 1,
  });

  if (isLoading) return <Placeholder title="Data Files" text="Loading..." />;
  if (isError || !data) return <Placeholder title="Data Files" text="Unavailable" />;

  const files = [...(data.loanFiles ?? []), ...(data.complaints ?? [])];
  const visible = expanded ? files : files.slice(0, 4);
  const remaining = files.length - 4;
  const activeSet = new Set(activeFiles ?? []);

  return (
    <CollapsibleSection title="Data Files" count={files.length}>
      <div className="space-y-1">
        {visible.map((file) => {
          const active = activeSet.has(file);
          const name = file.split("/").pop() ?? file;
          return (
            <div
              key={file}
              className="flex items-center gap-1.5 rounded px-1.5 py-0.5 transition-colors"
              style={{ background: active ? "hsl(var(--primary) / 0.08)" : "transparent" }}
            >
              <FileText
                size={12}
                className="flex-none"
                style={{ color: active ? "hsl(var(--primary))" : "hsl(var(--muted-foreground))" }}
              />
              <span
                className="text-xs font-sans truncate"
                style={{ color: active ? "hsl(var(--primary))" : "hsl(var(--foreground))" }}
                title={file}
              >
                {name}
              </span>
            </div>
          );
        })}
      </div>
      {!expanded && remaining > 0 && <ShowMore remaining={remaining} onClick={() => setExpanded(true)} />}
    </CollapsibleSection>
  );
}

function ComplianceGuardrails() {
  const [expanded, setExpanded] = useState(false);
  const { data, isError, isLoading } = useQuery({
    queryKey: ["compliance"],
    queryFn: () => apiGet("/api/agent/compliance"),
    retry: 1,
  });

  if (isLoading) return <Placeholder title="Compliance Guardrails" text="Loading..." />;
  if (isError || !data) return <Placeholder title="Compliance Guardrails" text="Unavailable" />;

  const rules = [...(data.mustAlways ?? []), ...(data.mustNever ?? []), ...(data.escalation ?? [])];
  const visible = expanded ? rules : rules.slice(0, 3);
  const remaining = rules.length - 3;

  return (
    <CollapsibleSection title="Compliance Guardrails" count={rules.length}>
      <div className="space-y-1.5">
        {visible.map((rule, i) => (
          <div key={i} className="flex items-start gap-1.5">
            <Shield size={12} className="flex-none mt-0.5" style={mutedFg} />
            <span className="text-xs font-sans leading-relaxed" style={{ color: "hsl(var(--foreground))" }}>
              {rule}
            </span>
          </div>
        ))}
      </div>
      {!expanded && remaining > 0 && <ShowMore remaining={remaining} onClick={() => setExpanded(true)} />}
    </CollapsibleSection>
  );
}

export default function AgentContextPanel({ activeSkill, activeFiles }) {
  return (
    <div
      className="flex-none flex flex-col rounded border overflow-hidden"
      style={{
        width: "300px",
        background: "hsl(var(--card))",
        borderColor: "hsl(var(--border))",
        borderRadius: "var(--radius)",
      }}
    >
      <div
        className="flex items-center gap-2 px-4 py-3 border-b"
        style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--muted))" }}
      >
        <Zap size={14} style={{ color: "hsl(var(--primary))" }} />
        <span
          className="text-xs font-sans font-semibold uppercase tracking-wider"
          style={{ color: "hsl(var(--foreground))" }}
        >
          Agent Context
        </span>
      </div>
      <div className="flex-1 overflow-y-auto">
        <ActiveSkills activeSkill={activeSkill} />
        <DataFiles activeFiles={activeFiles} />
        <ComplianceGuardrails />
      </div>
    </div>
  );
}
