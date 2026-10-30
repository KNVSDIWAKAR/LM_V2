// Loss Mitigation end-to-end model: the 12-step LM cycle, the 5 agent gates,
// and how each gate's engine verdicts roll up into the business-facing slots.

export const LM_STEPS = [
  {
    "id": "1.01",
    "name": "Customer contact / LM enquiry",
    "team": "Call Center",
    "fte": null,
    "ahtLabel": "—",
    "systems": [
      "Phone",
      "MSP"
    ],
    "automation": "roadmap"
  },
  {
    "id": "1.02",
    "name": "Borrower submits MAA + docs",
    "team": "Customer",
    "fte": null,
    "ahtLabel": "—",
    "systems": [
      "MAA"
    ],
    "automation": "borrower"
  },
  {
    "id": "1.03",
    "name": "LM Mailbox: document upload & intake",
    "team": "LM Mailbox",
    "fte": 12,
    "ahtLabel": "8 min",
    "systems": [
      "Outlook",
      "SIME",
      "Clarifire"
    ],
    "automation": "automated-first-pass",
    "linkedJourney": "loss-mit-intake"
  },
  {
    "id": "1.04",
    "name": "Retention / LM Setup review",
    "team": "Retention / LM Setup",
    "fte": 90,
    "ahtLabel": "~25–90 min",
    "systems": [
      "LMS",
      "MSP",
      "MIR",
      "ART"
    ],
    "automation": "agent-augmented",
    "linkedJourney": "loss-mit"
  },
  {
    "id": "1.05",
    "name": "Trial UW validation & plan",
    "team": "Trial U/W",
    "fte": 31,
    "ahtLabel": "35 min",
    "systems": [
      "LMSR",
      "MSP",
      "MIR"
    ],
    "automation": "agent-augmented",
    "linkedJourney": "loss-mit"
  },
  {
    "id": "1.06",
    "name": "Borrower makes trial payments",
    "team": "Customer",
    "fte": null,
    "ahtLabel": "—",
    "systems": [],
    "automation": "borrower"
  },
  {
    "id": "1.07",
    "name": "Trial monitoring / AC exception",
    "team": "Trial Monitoring",
    "fte": 5,
    "ahtLabel": "5 min",
    "systems": [
      "MSP"
    ],
    "automation": "roadmap"
  },
  {
    "id": "1.08",
    "name": "Mod Doc Final Underwriting",
    "team": "Mod Doc Final U/W",
    "fte": 20,
    "ahtLabel": "70 min",
    "systems": [
      "MSP",
      "LMSR",
      "MIR"
    ],
    "automation": "roadmap"
  },
  {
    "id": "1.09",
    "name": "UW approves MOD plan",
    "team": "U/W",
    "fte": null,
    "ahtLabel": "—",
    "systems": [
      "LMSR"
    ],
    "automation": "roadmap"
  },
  {
    "id": "1.10",
    "name": "MOD document generated & QC",
    "team": "MOD Team / QC",
    "fte": 5,
    "ahtLabel": "11 min",
    "systems": [
      "Exact Track",
      "SIME",
      "MSP"
    ],
    "automation": "roadmap"
  },
  {
    "id": "1.11",
    "name": "Recording & shipping",
    "team": "Recording",
    "fte": null,
    "ahtLabel": "—",
    "systems": [
      "County",
      "Exact Track",
      "FedEx"
    ],
    "automation": "roadmap"
  },
  {
    "id": "1.12",
    "name": "MOD delivery tracking & closing",
    "team": "LM Closing",
    "fte": 5,
    "ahtLabel": "11 min",
    "systems": [
      "SIME",
      "Exact Track",
      "FedEx"
    ],
    "automation": "roadmap"
  }
];

export const AUTOMATION_LABELS = {
  "automated-first-pass": "Automated first-pass",
  "agent-augmented": "Agent-augmented",
  "human-signoff": "Human sign-off",
  "roadmap": "Roadmap",
  "borrower": "Borrower"
};

/** Gate tone → dot color on the Case Timeline. */
export const GATE_TONE_COLORS = {
  "good": "#16a34a",
  "warn": "#f59e0b",
  "bad": "#ef4444",
  "neutral": "#94a3b8"
};

/** Gate keys in pipeline order. */
export const GATE_KEYS = [
  "intake",
  "eligibility",
  "trialUw",
  "trial",
  "closing"
];

/** Sort order for the Case Timeline (furthest-progressed borrower first). */
export const STAGE_SORT_ORDER = {
  "Closing": 0,
  "Trial": 1,
  "Trial UW": 2,
  "Retention Eligibility": 3,
  "Intake": 4
};

export const GATE_LABELS = {
  "intake": "Intake",
  "eligibility": "Retention Eligibility",
  "trialUw": "Trial UW",
  "trial": "Trial Monitoring",
  "closing": "Closing"
};

/** Engine verdict → business label shown on the timeline. */
export const VERDICT_DISPLAY_NAMES = {
  "Package Complete — Ready for Eval": "Complete",
  "Incomplete — Docs Outstanding": "Missing Doc",
  "Stale — Refresh Needed": "Invalid Date Doc",
  "Flex Modification — Trial": "Facially Complete",
  "Decline": "Denied",
  "Refer — Manual Review": "In Human Review",
  "Refer — Incomplete Package": "Facially Incomplete",
  "Trial Plan Ready": "Ready",
  "In Underwriting": "UW In Progress",
  "Hold — Awaiting Docs": "Hold Docs Pending",
  "Hold — Awaiting Approval": "Hold Approval Pending",
  "Declined — No Affordable Plan": "Declined",
  "On Track": "Within Plan",
  "At Risk": "Delayed Payment",
  "Broken": "Defaulted",
  "Cleared to Record": "Signed Off",
  "In QC": "Sign Off & In Progress",
  "SLA Breach": "In Human Review"
};

/** Per-stage slot definitions used by the dashboard summary cards. */
export const STAGE_CONFIG = {
  "Intake": {
    "path": "/loss-mit-intake",
    "gateKey": "intake",
    "advanceGate": "eligibility",
    "slots": [
      {
        "label": "Complete",
        "engine": [
          "Package Complete — Ready for Eval"
        ],
        "tone": "good"
      },
      {
        "label": "Invalid Date Doc",
        "engine": [
          "Stale — Refresh Needed"
        ],
        "tone": "warn"
      },
      {
        "label": "Missing Doc",
        "engine": [
          "Incomplete — Docs Outstanding"
        ],
        "tone": "warn"
      },
      {
        "label": "Missing & Invalid",
        "engine": [],
        "tone": "warn"
      },
      {
        "label": "End Case",
        "engine": [],
        "tone": "neutral"
      },
      {
        "label": "In Human Review",
        "engine": [],
        "tone": "warn",
        "isHumanReview": true
      }
    ]
  },
  "Retention Eligibility": {
    "path": "/loss-mit",
    "gateKey": "eligibility",
    "advanceGate": "trialUw",
    "exclude": [
      "Forbearance Plan",
      "Payment Deferral",
      "Refer — Manual Review"
    ],
    "slots": [
      {
        "label": "Facially Complete",
        "engine": [
          "Flex Modification — Trial"
        ],
        "tone": "good"
      },
      {
        "label": "Denied",
        "engine": [
          "Decline"
        ],
        "tone": "bad"
      },
      {
        "label": "Facially Incomplete",
        "engine": [
          "Refer — Incomplete Package"
        ],
        "tone": "warn"
      },
      {
        "label": "In Human Review",
        "engine": [],
        "tone": "warn",
        "isHumanReview": true
      }
    ]
  },
  "Trial UW": {
    "path": "/loss-mit-trial-uw",
    "gateKey": "trialUw",
    "advanceGate": "trial",
    "slots": [
      {
        "label": "Ready",
        "engine": [
          "Trial Plan Ready"
        ],
        "tone": "good"
      },
      {
        "label": "UW In Progress",
        "engine": [
          "In Underwriting"
        ],
        "tone": "warn"
      },
      {
        "label": "Hold Docs Pending",
        "engine": [
          "Hold — Awaiting Docs"
        ],
        "tone": "warn"
      },
      {
        "label": "Hold Approval Pending",
        "engine": [
          "Hold — Awaiting Approval"
        ],
        "tone": "warn"
      },
      {
        "label": "Declined",
        "engine": [
          "Declined — No Affordable Plan"
        ],
        "tone": "bad"
      },
      {
        "label": "In Human Review",
        "engine": [],
        "tone": "warn",
        "isHumanReview": true
      }
    ]
  },
  "Trial": {
    "path": "/loss-mit-trial",
    "gateKey": "trial",
    "advanceGate": "closing",
    "slots": [
      {
        "label": "Completed",
        "engine": [
          "Completed"
        ],
        "tone": "good"
      },
      {
        "label": "Within Plan",
        "engine": [
          "On Track"
        ],
        "tone": "good"
      },
      {
        "label": "Delayed Payment",
        "engine": [
          "At Risk"
        ],
        "tone": "warn"
      },
      {
        "label": "Defaulted",
        "engine": [
          "Broken"
        ],
        "tone": "bad"
      },
      {
        "label": "In Human Review",
        "engine": [],
        "tone": "warn",
        "isHumanReview": true
      }
    ]
  },
  "Closing": {
    "path": "/loss-mit-closing",
    "gateKey": "closing",
    "reclassify": {
      "SLA Breach": "In Human Review"
    },
    "slots": [
      {
        "label": "Recording",
        "engine": [
          "Recording"
        ],
        "tone": "good"
      },
      {
        "label": "Signed Off",
        "engine": [
          "Cleared to Record"
        ],
        "tone": "good"
      },
      {
        "label": "Sign Off & In Progress",
        "engine": [
          "In QC"
        ],
        "tone": "warn"
      },
      {
        "label": "Denied",
        "engine": [
          "Denied"
        ],
        "tone": "bad"
      },
      {
        "label": "In Human Review",
        "engine": [
          "SLA Breach"
        ],
        "tone": "warn",
        "isHumanReview": true
      }
    ]
  }
};

export const STAGE_TITLES = {
  "Intake": "Intake",
  "Retention Eligibility": "Retention Eligibility",
  "Trial UW": "Trial UW",
  "Trial": "Trial Monitoring",
  "Closing": "Closing"
};

export const STAGE_NUMBERS = {
  "Intake": 1,
  "Retention Eligibility": 2,
  "Trial UW": 3,
  "Trial": 4,
  "Closing": 5
};

export const SLOT_TONE_COLORS = {
  "good": "#16a34a",
  "warn": "#c2410c",
  "bad": "#ef4444",
  "neutral": "hsl(var(--muted-foreground))"
};

/** Display verdict + tone for one gate of a borrower; Flex Mod is only "good" once Trial UW has picked it up. */
export function gateDisplay(gateKey, borrower) {
  const gate = borrower.gates[gateKey];
  if (!gate) return undefined;
  let tone = gate.tone;
  if (gateKey === "eligibility" && gate.verdict === "Flex Modification — Trial") {
    tone = borrower.gates.trialUw ? "good" : "warn";
  }
  return { verdict: VERDICT_DISPLAY_NAMES[gate.verdict] ?? gate.verdict, tone };
}

/** Count gate outcomes across the cohort for the Case Timeline header tiles. */
export function summarizeTimeline(borrowers) {
  let onTrack = 0;
  let atRisk = 0;
  let slaBreach = 0;
  for (const borrower of borrowers) {
    for (const key of GATE_KEYS) {
      const d = gateDisplay(key, borrower);
      if (!d) continue;
      if (d.tone === "good") onTrack++;
      else if (d.tone === "warn") atRisk++;
      else if (d.tone === "bad") slaBreach++;
    }
  }
  return { onTrack, atRisk, slaBreach };
}

/** Roll a stage's engine verdicts up into total / moving-forward / needs-attention and per-slot counts. */
export function summarizeStage(stage, borrowers) {
  const cfg = STAGE_CONFIG[stage];
  const verdictOf = (b) => b.gates[cfg.gateKey]?.verdict ?? "";
  const reached = borrowers.filter((b) => !!b.gates[cfg.gateKey]);
  const inScope = cfg.exclude ? reached.filter((b) => !cfg.exclude.includes(verdictOf(b))) : reached;
  const total = inScope.length;

  const verdicts = cfg.slots.map((slot) => {
    let count = inScope.filter((b) => {
      const v = verdictOf(b);
      const effective = cfg.reclassify?.[v] === slot.label ? slot.engine[0] : v;
      if (cfg.reclassify?.[v] && cfg.reclassify[v] !== slot.label && slot.engine.includes(v)) return false;
      return slot.engine.includes(effective);
    }).length;

    // Intake: "Complete" only counts packages Retention Eligibility has picked up;
    // complete-but-not-yet-picked-up packages sit in human review.
    if (stage === "Intake" && cfg.advanceGate) {
      if (slot.label === "Complete") {
        count = inScope.filter((b) => slot.engine.includes(verdictOf(b)) && !!b.gates[cfg.advanceGate]).length;
      }
      if (slot.isHumanReview) {
        count = inScope.filter(
          (b) => ["Package Complete — Ready for Eval"].includes(verdictOf(b)) && !b.gates[cfg.advanceGate],
        ).length;
      }
    }

    return { verdict: slot.label, count, tone: slot.tone, isHumanReview: !!slot.isHumanReview };
  });

  let forward = verdicts.filter((v) => v.tone === "good").reduce((n, v) => n + v.count, 0);
  if (stage === "Intake" && cfg.advanceGate) {
    const excluded = STAGE_CONFIG["Retention Eligibility"].exclude ?? [];
    forward = inScope.filter((b) => {
      const next = b.gates[cfg.advanceGate];
      return !!next && !excluded.includes(next.verdict);
    }).length;
  }

  return { total, forward, attention: total - forward, verdicts };
}
