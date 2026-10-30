import {
  BookOpen,
  Calculator,
  ClipboardCheck,
  ClipboardList,
  FileCode2,
  GitBranch,
  Inbox,
  LifeBuoy,
  Search,
  Server,
  SquareCheckBig,
  Workflow,
} from "lucide-react";

export const DOMAIN_JOURNEYS = [
  {
    id: "loss-mit-optimization",
    label: "Loss Mitigation — End to End",
    icon: Workflow,
    path: "/loss-mitigation",
    description:
      "End-to-end LM cycle (12 steps) with source systems and where agents plug in today vs. roadmap",
  },
  {
    id: "loss-mit-intake",
    label: "LM Intake & Doc Review",
    icon: ClipboardCheck,
    path: "/loss-mit-intake",
    process: "intake",
    description:
      "Validate the MAA + hardship/income documents against MSP (BK/FC, identity); route as Complete / Missing Doc / End Case / In Human Review",
  },
  {
    id: "loss-mit",
    label: "LM Retention Eligibility",
    icon: LifeBuoy,
    path: "/loss-mit",
    process: "eligibility",
    description:
      "GSE (Fannie/Freddie) retention questionnaire — workflow, investor rules, signatures, income documents; verdict Facially Complete / Facially Incomplete",
  },
  {
    id: "loss-mit-trial-uw",
    label: "LM Trial Underwriting",
    icon: Calculator,
    path: "/loss-mit-trial-uw",
    process: "trial-underwriting",
    description:
      "Underwrite the modification trial — verify the package, calculate income, P&I and escrow, propose Trial Plans for the Human Underwriter; Ready / Hold / Declined",
  },
  {
    id: "loss-mit-trial",
    label: "LM Trial Monitoring",
    icon: ClipboardList,
    path: "/loss-mit-trial",
    process: "trial-monitoring",
    description:
      "Match MSP DLQ1 payments to the approved trial plan with its 15-day grace; Within Plan / Delayed Payment / Completed / Defaulted",
  },
  {
    id: "loss-mit-closing",
    label: "LM Final Mod & Closing",
    icon: SquareCheckBig,
    path: "/loss-mit-closing",
    process: "closing",
    description:
      "Final Underwriting checks, MOD QC and sign-off, then the Final Mod checks and 14-day recording SLA; Recording / Signed Off / Sign Off & In Progress / Denied",
  },
];

/** The five processes (everything but the End-to-End overview), in pipeline order. */
export const PROCESSES = DOMAIN_JOURNEYS.filter((j) => j.process);

/** API base for one process: /api/processes/{slug}. */
export function processApi(journeyId) {
  const process = DOMAIN_JOURNEYS.find((j) => j.id === journeyId)?.process;
  return `/api/processes/${process ?? journeyId}`;
}

export const BUILD_NAV = [
  { id: "playbooks", label: "Playbooks", icon: FileCode2, path: "/playbooks" },
  { id: "knowledge-base", label: "Knowledge Base", icon: BookOpen, path: "/knowledge-base" },
  { id: "systems", label: "Systems", icon: Server, path: "/systems" },
];

export const OBSERVE_NAV = [
  { id: "decision-inbox", label: "Decision Inbox", icon: Inbox, path: "/decision-inbox" },
  { id: "agent-runs", label: "Agent Runs", icon: Search, path: "/agent-runs" },
  { id: "workflow-runs", label: "Workflow Runs", icon: GitBranch, path: "/workflow-runs" },
];
