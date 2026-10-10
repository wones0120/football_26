import { classicGameCapParams } from "./classicGameConcentration.ts";
import { largeGppControlParams, type LargeGppControls } from "./classicLargeGppControls.ts";

// Select using the submitted strategy, never a different mode's form state.
export function classicOptimizerControlParams(strategy: string, form: {
  largeGppControls: LargeGppControls;
  primaryGameCap: number | null;
  minimumUniqueness: number;
  maxPlayersPerTeam: number;
  maxPlayersPerGame: number;
}): Record<string, number> {
  if (strategy !== "classic_large_gpp_v1" && strategy !== "classic_small_field_gpp") return {};
  return {
    max_players_per_team: form.maxPlayersPerTeam,
    max_players_per_game: form.maxPlayersPerGame,
    ...classicGameCapParams(form.primaryGameCap),
    ...(strategy === "classic_large_gpp_v1"
      ? largeGppControlParams(form.largeGppControls)
      : { minimum_uniqueness: form.minimumUniqueness }),
  };
}
