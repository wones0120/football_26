import assert from "node:assert/strict";
import test from "node:test";

import { optimizerProjectionOverrideForRequest, optimizerProjectionRunIdForRequest } from "../src/optimizerProjectionSelection.ts";

const runs = [
  { projection_run_id: "new", created_at: "2026-09-17T12:00:00Z", row_count: 30 },
  { projection_run_id: "old", created_at: "2026-09-15T12:00:00Z", row_count: 30 },
];

test("optimizer validates an older-run override and sends the latest ID by default", () => {
  assert.equal(optimizerProjectionOverrideForRequest(runs), undefined);
  assert.equal(optimizerProjectionOverrideForRequest(runs, "old"), "old");
  assert.equal(optimizerProjectionRunIdForRequest(runs), "new");
  assert.equal(optimizerProjectionRunIdForRequest(runs, "old"), "old");
  assert.throws(() => optimizerProjectionOverrideForRequest(runs, "missing"), /no longer available/);
  assert.throws(() => optimizerProjectionOverrideForRequest([]), /No completed projection/);
});
