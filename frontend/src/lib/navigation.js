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
      "Validate the MAA + hardship/income documents against investor matrices; compute completeness; draft borrower follow-ups",
  },
  {
    id: "loss-mit",
    label: "LM Retention Eligibility",
    icon: LifeBuoy,
    path: "/loss-mit",
    process: "eligibility",
    description:
      "GSE (Fannie/Freddie) retention waterfall — delinquency, hardship, affordability & exclusions; recommend Forbearance / Payment Deferral / Flex Modification / Refer / Decline",
  },
  {
    id: "loss-mit-trial-uw",
    label: "LM Trial Underwriting",
    icon: Calculator,
    path: "/loss-mit-trial-uw",
    process: "trial-underwriting",
    description:
      "Underwrite the Flex Modification trial — verify income/package, recompute payment-reduction & escrow, generate the 3-month Trial Plan and route as Ready / In UW / Hold / Declined",
  },
  {
    id: "loss-mit-trial",
    label: "LM Trial Monitoring",
    icon: ClipboardList,
    path: "/loss-mit-trial",
    process: "trial-monitoring",
    description:
      "Monitor the 3-month modification trial — payments made vs missed and the 15-day grace; flag On Track / At Risk / Completed / Broken",
  },
  {
    id: "loss-mit-closing",
    label: "LM Final Mod & Closing",
    icon: SquareCheckBig,
    path: "/loss-mit-closing",
    process: "closing",
    description:
      "Finalize the permanent modification — QC checklist and the 14-day county-recording SLA; Cleared to Record / In QC / Recording / Denied / SLA Breach",
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
