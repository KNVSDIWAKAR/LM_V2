const VARIANTS = {
  active: "bg-green-50 text-green-700 border border-green-200",
  available: "bg-gray-50 text-gray-600 border border-gray-200",
  draft: "bg-amber-50 text-amber-700 border border-amber-200",
  error: "bg-red-50 text-red-700 border border-red-200",
  running: "bg-blue-50 text-blue-700 border border-blue-200",
  pending: "bg-amber-50 text-amber-700 border border-amber-200",
  pass: "bg-green-100 text-green-800 border border-green-200",
  flagged: "bg-red-100 text-red-800 border border-red-200",
  warning: "bg-amber-100 text-amber-800 border border-amber-200",
  critical: "bg-red-100 text-red-800 border border-red-200",
  high: "bg-amber-100 text-amber-800 border border-amber-200",
  medium: "bg-stone-100 text-stone-700 border border-stone-200",
  low: "bg-gray-100 text-gray-600 border border-gray-200",
};

export default function Badge({ variant, children }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium font-sans tracking-wide ${VARIANTS[variant] ?? ""}`}
    >
      {children}
    </span>
  );
}

export function priorityVariant(priority) {
  const p = priority?.toLowerCase();
  if (p === "critical") return "critical";
  if (p === "high") return "high";
  if (p === "medium") return "medium";
  return "low";
}
