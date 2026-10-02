import assert from "node:assert/strict";
import test from "node:test";

import { optimizerAvailabilityOverrides } from "../src/optimizerProjectionScenario.ts";

test("player exclusions become assumed-out scenarios by name or canonical ID", () => {
  const overrides = optimizerAvailabilityOverrides([
    { playerName: " Receiver ", availability: "default", excludeFromLineups: true },
    { playerName: "Healthy", availability: "assume_active", excludeFromLineups: false },
    { playerName: "Unchanged", availability: "default", excludeFromLineups: false },
  ], "receiver, Other Receiver", "canonical-1, canonical-2");
  assert.deepEqual(overrides, [
    { player_name: "receiver", availability: "assume_out" },
    { player_name: "Healthy", availability: "assume_active" },
    { player_name: "Other Receiver", availability: "assume_out" },
    { player_id: "canonical-1", availability: "assume_out" },
    { player_id: "canonical-2", availability: "assume_out" },
  ]);
});

test("conflicting active assumptions and exclusions block the rebuild", () => {
  assert.throws(() => optimizerAvailabilityOverrides([
    { playerName: "Receiver", availability: "assume_active", excludeFromLineups: true },
  ], "", ""), /Cannot assume Receiver active/);
  assert.throws(() => optimizerAvailabilityOverrides([
    { playerName: "Receiver", availability: "assume_active", excludeFromLineups: false },
  ], "Receiver", ""), /Conflicting availability/);
});

test("no player decisions leaves the current football scenario unchanged", () => {
  assert.deepEqual(optimizerAvailabilityOverrides([], "", ""), []);
});
