export const CLASSIC_OBJECTIVE_STORAGE_KEY = "dfs-classic-selection-objectives-v1";
export type ClassicSelectionObjective = "scenario" | "baseline_mean";

/** Explicit one-run policy; saved lineup preferences and source projections remain untouched. */
export function classicSelectionParams(params: Record<string, unknown>, highestProjection: boolean): Record<string, unknown> {
  if (!highestProjection) return {...params};
  const copy = {...params};
  for (const key of Object.keys(copy)) if (key.startsWith("analyst_")) delete copy[key];
  for (const key of ["lock_player_ids", "locked_captain_player_id", "minimum_exposure_by_player"]) delete copy[key];
  return {...copy, classic_selection_objective:"baseline_mean", num_lineups:1,
    locked_player_ids:[], locked_players:[], analyst_handoff_mode:"BASELINE", analyst_optimization_intent:"MIXED"};
}

export type HighestProjectionReport = {objective_label: string; solver_status: string; base_mean?: number; salary?: number; optimal: boolean; locked_player_ids: string[]; input_snapshot_sha256: string};
export function savedHighestProjectionReport(status: {highest_projection?: HighestProjectionReport | null; results?: unknown} | null): HighestProjectionReport | null {
  if (status?.highest_projection) return status.highest_projection;
  const firstLineup = Array.isArray(status?.results) ? status.results[0] : null;
  const first = Array.isArray(firstLineup) ? firstLineup[0] : null;
  return first?.selection_objective === "baseline_mean" ? first.highest_projection_report ?? null : null;
}
