import { classicOptimizerControlParams } from "../src/classicOptimizerControls.ts";
import type { LargeGppControls } from "../src/classicLargeGppControls.ts";

// Synthetic season/pool only. No production projections, ownership, or jobs.
export function overlapFixtureRequest(strategy: string, numLineups: number, maxExposure: number, primaryGameCap: number | null, largeGppControls: LargeGppControls) {
  return {
    season: 2000, week: 1, slate: "SUNDAY_MAIN",
    optimizer_run_id: "synthetic-overlap-" + (largeGppControls.maxLineupOverlap ?? "default"),
    strategy, contest_format: "classic", objective: "gpp",
    params: {
      num_lineups: numLineups, max_exposure: maxExposure / 100,
      ...classicOptimizerControlParams(strategy, {
        largeGppControls, primaryGameCap, minimumUniqueness: 2,
        maxPlayersPerTeam: 4, maxPlayersPerGame: 5,
      }),
    },
  };
}
