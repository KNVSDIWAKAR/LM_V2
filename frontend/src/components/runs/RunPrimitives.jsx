// Shared bits for the Agent Runs and Workflow Runs pages (backend app/schemas/runs.py).
import { Ban, CircleCheckBig, CircleDashed, CircleOff, CirclePause, CircleX, Clock, LoaderCircle } from "lucide-react";

export const mutedFg = { color: "hsl(var(--muted-foreground))" };
export const fg = { color: "hsl(var(--foreground))" };

const STATUS = {
  queued: { color: "hsl(var(--muted-foreground))", Icon: Clock, label: "Queued" },
  running: { color: "hsl(217, 91%, 50%)", Icon: LoaderCircle, label: "Running", spin: true },
  paused: { color: "hsl(32, 90%, 40%)", Icon: CirclePause, label: "Paused · review" },
  completed: { color: "hsl(142, 71%, 34%)", Icon: CircleCheckBig, label: "Completed" },
  blocked: { color: "hsl(0, 0%, 45%)", Icon: CircleOff, label: "Blocked" },
  failed: { color: "hsl(0, 78%, 50%)", Icon: CircleX, label: "Failed" },
  cancelled: { color: "hsl(var(--muted-foreground))", Icon: Ban, label: "Cancelled" },
  none: { color: "hsl(var(--muted-foreground))", Icon: CircleDashed, label: "Not run" },
};

export function RunStatus({ status }) {
  const s = STATUS[status] ?? STATUS.none;
  return (
    <span className="inline-flex items-center gap-1.5" style={{ color: s.color }}>
      <s.Icon size={13} className={s.spin ? "animate-spin" : undefined} />
      <span className="font-sans text-xs font-medium">{s.label}</span>
    </span>
  );
}

export const formatMs = (ms) => (ms == null ? "—" : ms < 1000 ? `${ms}ms` : ms < 60000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms / 60000)}m`);
export const formatTime = (iso) => (iso ? new Date(iso).toLocaleString() : "—");

export function RunTable({ columns, children, empty }) {
  return (
    <div className="overflow-x-auto rounded" style={{ border: "1px solid hsl(var(--border))", borderRadius: "var(--radius)" }}>
      <table className="w-full text-sm font-sans" style={{ borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: "hsl(var(--muted))", borderBottom: "1px solid hsl(var(--border))" }}>
            {columns.map((col, i) => (
              <th key={i} className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider whitespace-nowrap" style={mutedFg}>
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {empty ? (
            <tr>
              <td colSpan={columns.length} className="px-4 py-8 text-center text-sm" style={mutedFg}>
                {empty}
              </td>
            </tr>
          ) : (
            children
          )}
        </tbody>
      </table>
    </div>
  );
}

export function JsonBlock({ title, value }) {
  if (value == null) return null;
  return (
    <section className="flex flex-col gap-1">
      <h3 className="font-sans text-xs font-semibold uppercase tracking-widest" style={mutedFg}>
        {title}
      </h3>
      <pre
        className="rounded p-3 text-xs overflow-x-auto whitespace-pre-wrap break-words font-mono"
        style={{ background: "hsl(var(--muted))", borderRadius: "var(--radius)", ...fg }}
      >
        {JSON.stringify(value, null, 2)}
      </pre>
    </section>
  );
}
