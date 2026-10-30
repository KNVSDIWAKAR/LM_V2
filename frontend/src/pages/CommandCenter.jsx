import { motion } from "framer-motion";
import { Bell, ChevronRight, Sparkles } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useLocation } from "wouter";
import PromptInput from "../components/ui/PromptInput";
import { DOMAIN_JOURNEYS } from "../lib/navigation";
import { apiGet } from "../lib/api";
import { formatShortDate } from "../lib/utils";

export const LOGO_URL =
  "/firstsource-logo.png";

const cardStyle = {
  background: "hsl(var(--card))",
  border: "1px solid hsl(var(--border))",
  borderRadius: "var(--radius)",
};

const muted = { color: "hsl(var(--muted-foreground))" };

function JourneyCard({ icon: Icon, title, description, onClick }) {
  return (
    <motion.button
      onClick={onClick}
      whileHover={{ scale: 1.01 }}
      transition={{ duration: 0.15 }}
      className="w-full flex items-start gap-4 p-5 text-left transition-colors"
      style={{ ...cardStyle, cursor: "pointer" }}
      onMouseEnter={(e) => (e.currentTarget.style.borderColor = "hsl(213 100% 17% / 0.25)")}
      onMouseLeave={(e) => (e.currentTarget.style.borderColor = "hsl(var(--border))")}
    >
      <Icon size={24} style={{ ...muted, flexShrink: 0, marginTop: 2 }} />
      <div className="flex-1 min-w-0">
        <h3 className="font-serif" style={{ fontSize: "16px", fontWeight: 500, color: "hsl(var(--foreground))" }}>
          {title}
        </h3>
        {description && (
          <p className="font-sans mt-1 line-clamp-2" style={{ fontSize: "13px", ...muted }}>
            {description}
          </p>
        )}
      </div>
      <ChevronRight size={18} style={{ ...muted, flexShrink: 0, marginTop: 4 }} />
    </motion.button>
  );
}

function SectionHeading({ title, count }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <h2 className="font-serif" style={{ fontSize: "18px", fontWeight: 500, color: "hsl(var(--foreground))" }}>
        {title}
      </h2>
      {count > 0 && (
        <span className="font-sans rounded-full px-2 py-0.5 text-xs font-medium" style={{ background: "hsl(var(--muted))", ...muted }}>
          {count}
        </span>
      )}
    </div>
  );
}

function StatusLine({ children }) {
  return (
    <p className="font-sans text-sm" style={muted}>
      {children}
    </p>
  );
}

/** Where cases sit across the five processes right now. */
export function AgentInsights() {
  const { data, isLoading, isError } = useQuery({ queryKey: ["processes"], queryFn: () => apiGet("/api/processes"), refetchInterval: 10000 });
  const stages = data ?? [];

  return (
    <section>
      <SectionHeading title="Pipeline" />
      {isLoading && <StatusLine>Loading stages…</StatusLine>}
      {isError && <StatusLine>Could not load the pipeline.</StatusLine>}
      <div className="space-y-2">
        {stages.map((s) => {
          const worked = Object.entries(s.counts).filter(([k, n]) => k !== "Not reached" && n > 0);
          return (
            <div key={s.stage_no} className="p-3" style={cardStyle}>
              <div className="flex items-center justify-between gap-2">
                <p className="font-sans font-semibold" style={{ fontSize: "13px", color: "hsl(var(--foreground))" }}>
                  {s.stage_no}. {s.name}
                </p>
                <span className="font-sans text-[11px]" style={muted}>
                  {s.playbook ? (s.paused ? `${s.paused} in review` : "Playbook live") : "Not built"}
                </span>
              </div>
              <p className="font-sans mt-1" style={{ fontSize: "12px", ...muted }}>
                {worked.length ? worked.map(([k, n]) => `${k} ${n}`).join(" · ") : "No cases worked yet"}
              </p>
            </div>
          );
        })}
      </div>
    </section>
  );
}

/** Decision Inbox items waiting for a person. */
export function ActionsRequired() {
  const [, navigate] = useLocation();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["decisions", "pending"],
    queryFn: () => apiGet("/api/decisions?status=pending"),
    refetchInterval: 10000,
  });
  const actions = data ?? [];

  return (
    <section>
      <SectionHeading title="Actions Required" count={actions.length} />
      {isLoading && <StatusLine>Loading actions…</StatusLine>}
      {isError && <StatusLine>Could not load actions.</StatusLine>}
      {!isLoading && !isError && actions.length === 0 && <StatusLine>Nothing is waiting for a decision.</StatusLine>}
      <div className="space-y-2">
        {actions.slice(0, 5).map((a) => (
          <button key={a.id} onClick={() => navigate(`/decision-inbox/${a.id}`)} className="w-full text-left p-3" style={{ ...cardStyle, cursor: "pointer" }}>
            <div className="flex items-start gap-3">
              <div className="flex items-center justify-center rounded-full shrink-0" style={{ width: 28, height: 28, background: "hsl(213 100% 17% / 0.1)" }}>
                <Bell size={14} style={{ color: "hsl(var(--primary))" }} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-sans font-semibold truncate" style={{ fontSize: "13px", color: "hsl(var(--foreground))" }}>
                  {a.borrower_name} · {a.loan_id}
                </p>
                <p className="font-sans mt-0.5 line-clamp-2" style={{ fontSize: "12px", ...muted }}>
                  {a.reason}
                </p>
                <p className="font-sans mt-1 uppercase tracking-wide" style={{ fontSize: "10px", ...muted }}>
                  {a.stage_name} · {a.team} · {formatShortDate(a.created_at)}
                </p>
              </div>
              <ChevronRight size={16} style={{ ...muted, flexShrink: 0 }} />
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}

export default function CommandCenter() {
  const [, navigate] = useLocation();
  const ask = (message) => navigate(`/agent-console?message=${encodeURIComponent(message)}`);

  return (
    <div className="flex flex-col items-center px-2 pt-2 pb-8">
      <div className="flex flex-col items-center text-center mb-8 mt-4">
        <img
          src={LOGO_URL}
          alt="Firstsource"
          className="mb-4 rounded-xl"
          style={{ height: 56, width: "auto", objectFit: "contain" }}
          onError={(e) => (e.currentTarget.style.display = "none")}
        />
        <h1
          className="font-serif tracking-tight"
          style={{ fontSize: "28px", fontWeight: 600, color: "hsl(var(--foreground))" }}
        >
          Welcome, COE Team
        </h1>
        <p className="font-sans mt-1" style={{ fontSize: "14px", ...muted }}>
          Loss Mitigation Workbench — Agentic OS for retention, modification &amp; servicing recovery
        </p>
      </div>

      <PromptInput placeholder="How can I help?" onSend={ask} className="max-w-2xl w-full" />

      <section className="w-full max-w-4xl mt-10">
        <div className="flex items-center gap-2 mb-4">
          <Sparkles size={16} style={{ color: "hsl(var(--primary))" }} />
          <h2 className="font-sans font-medium uppercase tracking-widest" style={{ fontSize: "11px", ...muted }}>
            Agent Journeys
          </h2>
        </div>
        <div className="grid grid-cols-2 gap-4">
          {DOMAIN_JOURNEYS.map((journey) => (
            <JourneyCard
              key={journey.id}
              icon={journey.icon}
              title={journey.label}
              description={journey.description}
              onClick={() => navigate(journey.path)}
            />
          ))}
        </div>
      </section>

      <div className="w-full max-w-4xl grid grid-cols-2 gap-8 mt-10">
        <AgentInsights />
        <ActionsRequired />
      </div>
    </div>
  );
}
