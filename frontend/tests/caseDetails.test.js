import test from "node:test";
import assert from "node:assert/strict";
import { countFindings, money, pct, plansByEvaluation } from "../src/lib/caseDetails.js";

test("counts never treat unknown or missing results as passes", () => {
  assert.deepEqual(countFindings(undefined), { pass: 0, fail: 0, review: 0, other: 0 });
  const findings = [
    { result: "pass" }, { result: "fail" }, { result: "flagged" }, { result: "review" },
    { result: "pending" }, { result: "neutral" }, { result: "skipped" }, {},
  ];
  assert.deepEqual(countFindings(findings), { pass: 1, fail: 2, review: 2, other: 3 });
});

test("missing amounts stay distinct from zero", () => {
  assert.equal(money(null), "Not recorded");
  assert.equal(money(undefined), "Not recorded");
  assert.equal(money("bad"), "Not recorded");
  assert.equal(money(0), "$0.00");
  assert.equal(money(1250.5), "$1,250.50");
  assert.equal(pct(null), "Not recorded");
  assert.equal(pct(35.42), "35.4%");
});

test("plans group by the evaluation that proposed them, in order", () => {
  const groups = plansByEvaluation([
    { plan_id: "b1", agent_run_id: "ar-b", created_at: "2026-10-30" },
    { plan_id: "b2", agent_run_id: "ar-b", created_at: "2026-10-30" },
    { plan_id: "a1", agent_run_id: "ar-a", created_at: "2026-10-01" },
  ]);
  assert.deepEqual(groups.map((g) => [g.agent_run_id, g.plans.map((p) => p.plan_id)]), [["ar-b", ["b1", "b2"]], ["ar-a", ["a1"]]]);
});
