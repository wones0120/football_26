import test from "node:test";
import assert from "node:assert/strict";
import { recoverOptimizerReceipt } from "../src/optimizerQueue.ts";

test("lost receipt retries the identical submission once and recovers the existing job", async () => {
  const payload = { optimizer_run_id: "same-run", params: { num_lineups: 5 } };
  const sent: unknown[] = [];
  const job = await recoverOptimizerReceipt(async () => {
    sent.push(payload);
    if (sent.length === 1) throw new Error("Request timed out while contacting /api");
    return { created: false, job_id: "existing-job" };
  });
  assert.deepEqual(job, { created: false, job_id: "existing-job" });
  assert.equal(sent.length, 2);
  assert.equal(sent[0], sent[1]);
});
test("validation failures never resubmit and transport retries are bounded", async () => {
  let calls = 0;
  await assert.rejects(recoverOptimizerReceipt(async () => { calls++; throw new Error("Prepared inputs changed"); }), /Prepared inputs changed/);
  assert.equal(calls, 1);
  calls = 0;
  await assert.rejects(recoverOptimizerReceipt(async () => { calls++; throw new Error("Could not reach the backend API at /api"); }), /Could not reach/);
  assert.equal(calls, 2);
});
