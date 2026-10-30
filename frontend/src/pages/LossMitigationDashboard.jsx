import { ArrowRight, Calculator, ChevronRight, ClipboardCheck, ClipboardList, LifeBuoy, Sparkles, SquareCheckBig, Workflow } from "lucide-react";
import { useLocation } from "wouter";
import PromptInput from "../components/ui/PromptInput";
import { ActionsRequired, AgentInsights, LOGO_URL } from "./CommandCenter";

const LIFECYCLE_STAGES = [
  {
    id: "loss-mit-intake",
    label: "Intake & Doc Review",
    icon: ClipboardCheck,
    path: "/loss-mit-intake",
    description:
      "Validate the MAA + hardship/income documents against investor matrices; compute completeness; draft borrower follow-ups",
  },
  {
    id: "loss-mit",
    label: "Retention Eligibility",
    icon: LifeBuoy,
    path: "/loss-mit",
    description:
      "GSE retention waterfall — delinquency, hardship, affordability, exclusions; recommend Forbearance / Payment Deferral / Flex Modification / Refer / Decline",
  },
  {
    id: "loss-mit-trial-uw",
    label: "Trial Underwriting",
    icon: Calculator,
    path: "/loss-mit-trial-uw",
    description:
      "Underwrite the Flex Mod trial — recompute payment-reduction & escrow, run NPV + investor approval, generate the 3-month Trial Plan",
  },
  {
    id: "loss-mit-trial",
    label: "Trial Monitoring",
    icon: ClipboardList,
    path: "/loss-mit-trial",
    description: "Monitor the 3-month trial — payments made vs missed, 15-day grace; flag On Track / At Risk / Completed / Broken",
  },
  {
    id: "loss-mit-closing",
    label: "Final Mod & Closing",
    icon: SquareCheckBig,
    path: "/loss-mit-closing",
    description:
      "Finalize the permanent modification — QC checklist and the 14-day county-recording SLA; Cleared / In QC / Recording / Denied / SLA Breach",
  },
];

/** /loss-mitigation-dashboard — lifecycle landing page (not linked from the sidebar). */
export default function LossMitigationDashboard() {
  const [, navigate] = useLocation();
  const ask = (message) => navigate(`/agent-console?message=${encodeURIComponent(message)}`);

  return (
    <div className="lmdash-root">
      <div className="lmdash-hero">
        <img src={LOGO_URL} alt="Firstsource" onError={(e) => (e.currentTarget.style.display = "none")} />
        <h1>Loss Mitigation Workbench</h1>
        <p>End-to-end loss-mitigation lifecycle — Intake to Final Modification &amp; Closing</p>
      </div>

      <PromptInput placeholder="How can I help?" onSend={ask} className="lmdash-search" />

      <section className="lmdash-section">
        <div className="lmdash-section-head">
          <Sparkles size={16} style={{ color: "hsl(var(--primary))" }} />
          <h2>Loss Mitigation Lifecycle</h2>
        </div>

        <button type="button" className="lmdash-end-to-end" onClick={() => navigate("/loss-mitigation")}>
          <Workflow size={28} className="lmdash-end-icon" />
          <div style={{ flex: 1, minWidth: 0 }}>
            <h3>Loss Mitigation — End to End</h3>
            <p>The full 12-step LM cycle with source systems and where agents plug in today vs. roadmap</p>
          </div>
          <ChevronRight size={18} style={{ color: "hsl(var(--muted-foreground))", flexShrink: 0, marginTop: 6 }} />
        </button>

        <div className="lmdash-stage-row">
          {LIFECYCLE_STAGES.map((stage, i) => {
            const Icon = stage.icon;
            return (
              <button key={stage.id} type="button" className="lmdash-stage-card" onClick={() => navigate(stage.path)}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span className="lmdash-stage-num">{i + 1}</span>
                  <Icon size={18} className="lmdash-stage-icon" />
                </div>
                <div className="lmdash-stage-title">{stage.label}</div>
                <div className="lmdash-stage-desc">{stage.description}</div>
                <div className="lmdash-stage-foot">
                  Open module <ArrowRight size={12} />
                </div>
              </button>
            );
          })}
        </div>
      </section>

      <div className="lmdash-bottom">
        <AgentInsights />
        <ActionsRequired />
      </div>
    </div>
  );
}
