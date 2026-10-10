import { DEFAULT_LARGE_GPP_CONTROLS, largeGppControlParams, type LargeGppControls } from "./classicLargeGppControls.ts";

export type LineupControls = LargeGppControls & {
  numLineups: number; maxExposure: number; primaryGameCap: number | null;
  maxPlayersPerTeam: number; maxPlayersPerGame: number;
  captainMaxExposure: number; coreMaxExposure: number; startingQbMaxExposure: number; cheapPuntMaxExposure: number;
};
export const LINEUP_CONTROLS_STORAGE_KEY = "football-26-lineup-controls";
export const MAX_LINEUPS = 500;
export function defaultLineupControls(format: "classic" | "showdown"): LineupControls {
  return { ...DEFAULT_LARGE_GPP_CONTROLS, numLineups: 5, maxExposure: 100, primaryGameCap: null,
    maxPlayersPerTeam: format === "classic" ? 4 : 5, maxPlayersPerGame: format === "classic" ? 5 : 6,
    captainMaxExposure: 100, coreMaxExposure: 100, startingQbMaxExposure: 100, cheapPuntMaxExposure: 100 };
}

export function lineupControlParams(value: LineupControls, format: "classic" | "showdown"): Record<string, number> {
  const size = format === "classic" ? 9 : 6;
  const params: Record<string, number> = {};
  for (const [key, input, low, high] of [
    ["num_lineups", value.numLineups, 1, MAX_LINEUPS],
    ["max_players_per_team", value.maxPlayersPerTeam, format === "classic" ? 1 : 3, format === "classic" ? 4 : 5],
    ["max_players_per_game", value.maxPlayersPerGame, 1, size],
  ] as const) {
    if (!Number.isInteger(input) || input < low || input > high) throw new Error(`${key} must be a whole number from ${low} through ${high}.`);
    params[key] = input;
  }
  // Overlap counts canonical players across both Captain and FLEX slots.
  if (value.maxLineupOverlap !== null && (!Number.isInteger(value.maxLineupOverlap) || value.maxLineupOverlap < 0 || value.maxLineupOverlap > size)) throw new Error(`Max shared players must be 0–${size}.`);
  if (value.maxElevatedPerLineup !== null && value.maxElevatedPerLineup > size) throw new Error(`Max elevated-risk players must be 0–${size}.`);
  Object.assign(params, largeGppControlParams({ ...value, maxLineupOverlap: null }));
  if (value.maxLineupOverlap !== null) params.max_lineup_overlap = value.maxLineupOverlap;
  for (const [key, input] of [
    ["max_exposure", value.maxExposure],
    ...(format === "showdown" ? [["captain_max_exposure", value.captainMaxExposure], ["core_player_max_exposure", value.coreMaxExposure],
      ["starting_qb_max_exposure", value.startingQbMaxExposure], ["cheap_punt_max_exposure", value.cheapPuntMaxExposure]] as const : []),
  ] as const) {
    if (typeof input !== "number" || !Number.isFinite(input) || input < 0 || input > 100) throw new Error(`${key} must be 0–100%.`);
    params[key] = input / 100;
  }
  if (format === "classic" && value.primaryGameCap !== null) {
    if (!Number.isInteger(value.primaryGameCap) || value.primaryGameCap < 1 || value.primaryGameCap > MAX_LINEUPS) throw new Error(`Primary-game cap must be 1–${MAX_LINEUPS}.`);
    params.max_lineups_per_primary_game = value.primaryGameCap;
  }
  return params;
}

export function parseLineupControls(raw: string | null, format: "classic" | "showdown"): LineupControls {
  const defaults = defaultLineupControls(format);
  try {
    const row = JSON.parse(raw ?? "null");
    if (!row || typeof row !== "object") return defaults;
    const restored = { ...defaults };
    // Restore valid siblings even if one preference is malformed.
    for (const key of Object.keys(defaults) as Array<keyof LineupControls>) {
      if (!(key in row)) continue;
      const candidate = { ...defaults, [key]: row[key] };
      try { lineupControlParams(candidate, format); Object.assign(restored, { [key]: row[key] }); } catch { /* Use field default. */ }
    }
    return restored;
  } catch { return defaults; }
}

export function restoreLineupControls(raw: string | null, legacyClassic: string | null) {
  let saved: Record<string, unknown> = {};
  try { saved = JSON.parse(raw ?? "{}") ?? {}; } catch { /* Use defaults and legacy choices. */ }
  const classicRaw = saved.classic ? JSON.stringify(saved.classic) : legacyClassic;
  return { classic: parseLineupControls(classicRaw, "classic"), showdown: parseLineupControls(JSON.stringify(saved.showdown ?? null), "showdown") };
}
