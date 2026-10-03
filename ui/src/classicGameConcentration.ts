export const PRIMARY_GAME_CAP_STORAGE_KEY = "football-26-classic-primary-game-cap";

export function classicGameCapParams(value: number | null): Record<string, number> {
  if (value === null) return {};
  if (!Number.isInteger(value) || value < 1) throw new Error("Max lineups per primary game must be a positive whole number or No limit.");
  return { max_lineups_per_primary_game: value };
}

export function parseSavedPrimaryGameCap(raw: string | null): number | null {
  try {
    const value: unknown = JSON.parse(raw ?? "null");
    if (typeof value !== "number") return null;
    classicGameCapParams(value);
    return value;
  } catch { return null; }
}
