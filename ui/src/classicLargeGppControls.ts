export const LARGE_GPP_CONTROLS_STORAGE_KEY = "football-26-classic-large-gpp-controls";
export type LargeGppControls = {
  maxLineupOverlap: number | null;
  elevatedExposurePercent: number | null;
  maxElevatedPerLineup: number | null;
};
export const DEFAULT_LARGE_GPP_CONTROLS: LargeGppControls = {
  maxLineupOverlap: null, elevatedExposurePercent: null, maxElevatedPerLineup: null,
};
export function largeGppControlParams(controls: LargeGppControls): Record<string, number> {
  const params: Record<string, number> = {};
  for (const [key, value, maximum] of [
    ["max_lineup_overlap", controls.maxLineupOverlap, 8],
    ["max_elevated_players_per_lineup", controls.maxElevatedPerLineup, 9],
  ] as const) {
    if (value === null) continue;
    if (!Number.isInteger(value) || value < 0 || value > maximum) throw new Error(`${key} must be a whole number from 0 through ${maximum}.`);
    params[key] = value;
  }
  const rate = controls.elevatedExposurePercent;
  if (rate !== null) {
    if (!Number.isFinite(rate) || rate < 0 || rate > 100) throw new Error("Elevated-risk exposure must be 0–100%.");
    params.elevated_player_max_exposure = rate / 100;
  }
  return params;
}
export function parseSavedLargeGppControls(raw: string | null): LargeGppControls {
  try {
    const row = JSON.parse(raw ?? "null");
    if (!row || typeof row !== "object") return { ...DEFAULT_LARGE_GPP_CONTROLS };
    const controls = { ...DEFAULT_LARGE_GPP_CONTROLS };
    // A malformed sibling preference must not discard a valid explicit overlap.
    for (const key of Object.keys(controls) as Array<keyof LargeGppControls>) {
      const value = row[key] ?? null;
      try {
        largeGppControlParams({ ...DEFAULT_LARGE_GPP_CONTROLS, [key]: value });
        controls[key] = value;
      } catch { /* Restore this field's default only. */ }
    }
    return controls;
  } catch { return { ...DEFAULT_LARGE_GPP_CONTROLS }; }
}
export function parseSavedLargeGppVolume(raw: string | null): { numLineups: number; maxExposure: number } {
  try {
    const row = JSON.parse(raw ?? "null");
    return { numLineups: Number.isInteger(row?.numLineups) && row.numLineups >= 1 && row.numLineups <= 50 ? row.numLineups : 20,
      maxExposure: typeof row?.maxExposure === "number" && Number.isFinite(row.maxExposure) && row.maxExposure >= 1 && row.maxExposure <= 100 ? row.maxExposure : 60 };
  } catch { return { numLineups: 20, maxExposure: 60 }; }
}
