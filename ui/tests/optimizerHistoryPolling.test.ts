import assert from "node:assert/strict";
import test from "node:test";
import { optimizerHistoryPollDelay } from "../src/optimizerHistory.ts";

test("completed, failed, and empty histories stop polling", () => {
  for (const runs of [[], [{status: "completed"}], [{status: "failed"}], [{status:"completed"},{status:"failed"}]]) {
    assert.equal(optimizerHistoryPollDelay(runs), null);
  }
});
test("active runs poll until finished", () => {
  assert.equal(optimizerHistoryPollDelay([{status:"completed"},{status:"running"}]), 5000);
  assert.equal(optimizerHistoryPollDelay([{status:"queued"}]), 5000);
});
