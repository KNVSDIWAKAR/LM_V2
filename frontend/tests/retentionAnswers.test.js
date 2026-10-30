import test from "node:test";
import assert from "node:assert/strict";
import { answerPresentation, answerSummary } from "../src/lib/retentionAnswers.js";

test("date-only outputs have no badge, including old confidence-based pending", () => {
  for (const question_id of ["Q5", "CALC_Q4"]) {
    const display = answerPresentation({ question_id, answer: "2027-03-21", result: "pending", confidence: .5 });
    assert.deepEqual(display, { result: "neutral", dateOnly: true, badge: null });
  }
});

test("missing required dates still fail; optional dates stay neutral", () => {
  const answer = { question_id: "Q5", answer: null, result: "pending" };
  assert.equal(answerPresentation(answer, [{ question_id: "Q5" }]).badge, "fail");
  assert.equal(answerPresentation({ question_id: "CALC_Q4", answer: null, result: "neutral" }).badge, null);
});

test("real validation failures are not suppressed even for a date", () => {
  assert.equal(answerPresentation({ question_id: "Q5", answer: "2026-01-01", result: "fail" }).badge, "fail");
  assert.equal(answerPresentation({ question_id: "Q33", answer: false, result: "fail" }).badge, "fail");
});

test("old false QX without a stip passes, not pending due to confidence", () => {
  const answer = { question_id: "QX", answer: false, result: "pending", confidence: .5 };
  assert.equal(answerPresentation(answer).badge, "pass");
  assert.equal(answerPresentation(answer, [{ question_id: "QX" }]).badge, "fail");
});

test("missing required values fail and not-applicable checks pass", () => {
  assert.equal(answerPresentation({ question_id: "Q6", answer: null, result: "pending" }, [{ question_id: "Q6" }]).badge, "fail");
  assert.equal(answerPresentation({ question_id: "Q35", answer: null, result: "pending", not_applicable: true }).badge, "pass");
});

test("a failed second wage does not mark the first wage failed", () => {
  const answer = { question_id: "Q16", answer: true, result: "pass", wage_number: 1 };
  const stips = [{ question_id: "Q16", wage_number: 2 }];
  assert.equal(answerPresentation(answer, stips).badge, "pass");
  assert.equal(answerPresentation({ ...answer, wage_number: 2 }, stips).badge, "fail");
});

test("display counts match displayed results without mutating saved reports", () => {
  const answers = [{ question_id: "QX", answer: false, result: "pending" },
    { question_id: "Q16", answer: false, result: "fail" },
    { question_id: "CALC_Q4", answer: "2027-03-21", result: "pending" }];
  assert.deepEqual(answerSummary(answers), { pass: 1, fail: 1, neutral: 1 });
  assert.equal(answers[0].result, "pending");
});