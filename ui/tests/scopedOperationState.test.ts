import assert from "node:assert/strict";
import test from "node:test";
import { nextScopedOperationState, scopedOperationValue } from "../src/scopedOperationState.ts";

test("a Monday error and import receipt cannot appear on Sunday", () => {
  const monday = "2026:6:MONDAY_NIGHT", sunday = "2026:6:SUNDAY_NIGHT";
  const error = { scope: monday, value: "Monday role missing" };
  assert.equal(scopedOperationValue(error, sunday, null), null);
  const receipt = { scope: monday, value: ["120 Monday salary rows"] };
  assert.deepEqual(scopedOperationValue(receipt, sunday, []), []);
  assert.equal(scopedOperationValue(error, monday, null), error.value);
});

test("late prior-slate completion cannot erase the active operation's error or pending state", () => {
  const current = { scope: "Sunday", value: "Current source error" };
  assert.equal(nextScopedOperationState(current, "Monday", "Sunday", null), current);
  assert.deepEqual(nextScopedOperationState(current, "Sunday", "Sunday", null), { scope: "Sunday", value: null });
});
