/** Helpers for the Stage 3–5 case drawers (backend routes/cases.py). Present saved data only. */

export const RESULT_COLOR = {
  pass: "hsl(142, 60%, 32%)",
  paid: "hsl(142, 60%, 32%)",
  fail: "hsl(0, 72%, 48%)",
  flagged: "hsl(0, 72%, 48%)",
  missed: "hsl(0, 72%, 48%)",
  partial: "hsl(0, 72%, 48%)",
  review: "hsl(32, 90%, 38%)",
  warn: "hsl(32, 90%, 38%)",
  late: "hsl(32, 90%, 38%)",
  pending: "hsl(217, 80%, 45%)",
};

export const RESULT_LABEL = {
  pass: "Passed",
  fail: "Failed",
  review: "Review",
  warn: "Warning",
  neutral: "Info",
  flagged: "Flagged",
  pending: "Pending",
  skipped: "Skipped",
  not_applicable: "N/A",
  paid: "Paid",
  late: "Late",
  partial: "Partial",
  missed: "Missed",
};

export function resultColor(result) {
  return RESULT_COLOR[result] ?? "hsl(var(--muted-foreground))";
}

/** Count findings by result; anything unexpected is "other", never assumed to pass. */
export function countFindings(findings) {
  const counts = { pass: 0, fail: 0, review: 0, other: 0 };
  for (const f of Array.isArray(findings) ? findings : []) {
    const key = f.result === "flagged" ? "fail" : f.result === "pending" ? "review" : f.result;
    counts[["pass", "fail", "review"].includes(key) ? key : "other"] += 1;
  }
  return counts;
}

export function money(value) {
  return value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value))
    ? new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(Number(value))
    : "Not recorded";
}

export function pct(value, digits = 1) {
  return value !== null && value !== undefined && Number.isFinite(Number(value)) ? `${Number(value).toFixed(digits)}%` : "Not recorded";
}

/** Plans grouped by the evaluation (agent run) that proposed them, newest first. */
export function plansByEvaluation(plans) {
  const groups = [];
  for (const plan of Array.isArray(plans) ? plans : []) {
    let group = groups.find((g) => g.agent_run_id === plan.agent_run_id);
    if (!group) {
      group = { agent_run_id: plan.agent_run_id, created_at: plan.created_at, plans: [] };
      groups.push(group);
    }
    group.plans.push(plan);
  }
  return groups;
}
