import test from "node:test";
import assert from "node:assert/strict";
import { retentionProgress } from "../src/lib/retentionProgress.js";

test("accepted IDs stay busy before polling has returned", () => {
  const progress = retentionProgress(["a", "b"]);
  assert.equal(progress.active, true);
  assert.equal(progress.finished, 0);
  assert.equal(progress.percent, 0);
});

test("queued and running cases remain busy, unrelated runs do not count", () => {
  const progress = retentionProgress(["a", "b", "c"], [
    { id: "a", status: "completed" }, { id: "b", status: "running" },
    { id: "c", status: "queued" }, { id: "other", status: "completed" },
  ]);
  assert.equal(progress.active, true);
  assert.equal(progress.finished, 1);
  assert.equal(progress.percent, 33);
});

test("completed, failed and paused runs stop the spinner and expose outcomes", () => {
  const progress = retentionProgress(["a", "b", "c"], [
    { id: "a", status: "completed" },
    { id: "b", loan_id: "123", status: "failed", error: "Evaluation failed" },
    { id: "c", status: "paused" },
  ]);
  assert.equal(progress.active, false);
  assert.equal(progress.percent, 100);
  assert.equal(progress.failed, 1);
  assert.equal(progress.paused, 1);
  assert.deepEqual(progress.errors, ["Loan 123: Evaluation failed"]);
});

test("empty batch is idle", () => {
  assert.equal(retentionProgress([]).active, false);
});