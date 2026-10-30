import test from "node:test";
import assert from "node:assert/strict";
import { cleanDisplayMessages } from "../src/lib/displayMessages.js";

test("removes retired message from pending actions and historical run traces", () => {
  const original = {
    pending_actions: [{ pending_reason: "1 stip(s); confidence is not considered" }],
    remark: "0 stip(s); confidence is not considered",
    trace: [{ detail: "1 stip(s); confidence is not considered" }],
    report: { explanation: "Confidence not considered", stip_count: 1 },
  };
  const result = cleanDisplayMessages(original);
  assert.equal(result.pending_actions[0].pending_reason, "1 stip(s)");
  assert.equal(result.remark, "0 stip(s)");
  assert.equal(result.trace[0].detail, "1 stip(s)");
  assert.equal(result.report.explanation, "");
  assert.equal(result.report.stip_count, 1);
  assert.equal(original.remark, "0 stip(s); confidence is not considered");
});

test("preserves source data, decisions, metadata, nulls and other explanations", () => {
  const source = { status: "Facially Incomplete", confidence_considered: false,
    hardship_reason: "confidence is not considered", detail: "Current tax bill required",
    report: null, values: [0, false, null] };
  assert.deepEqual(cleanDisplayMessages(source), source);
});