// HTTP 202 means accepted, not finished. Track exact persisted run IDs.
const executing = new Set(["queued", "running"]);

export function retentionProgress(runIds, runs = []) {
  const selected = runs.filter((run) => runIds.includes(run.id));
  const finished = selected.filter((run) => !executing.has(run.status));
  const failed = selected.filter((run) => run.status === "failed" || run.status === "cancelled");
  const paused = selected.filter((run) => run.status === "paused");
  return {
    total: runIds.length,
    finished: finished.length,
    failed: failed.length,
    paused: paused.length,
    active: runIds.length > finished.length,
    percent: runIds.length ? Math.round(100 * finished.length / runIds.length) : 0,
    errors: failed.map((run) => `Loan ${run.loan_id}: ${run.error || run.status}`),
  };
}