// Hide a retired status-message suffix in historical API responses without
// rewriting stored audit history or changing source documents/verdicts.
const messageFields = new Set(["detail", "remark", "pending_reason", "reason", "explanation", "outcome"]);

export function cleanDisplayMessages(value, field = "") {
  if (typeof value === "string" && messageFields.has(field)) {
    return value.replace(/(?:;\s*|\s+)?confidence(?:\s+score)?\s+(?:is\s+)?not\s+considered\.?/gi, "").trim();
  }
  if (Array.isArray(value)) return value.map((item) => cleanDisplayMessages(item));
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, cleanDisplayMessages(item, key)]));
  }
  return value;
}