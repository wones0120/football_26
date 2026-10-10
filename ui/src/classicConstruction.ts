export const SINGLE_TE_STORAGE_KEY = "football-26-classic-enforce-single-te";
export function parseSingleTePreference(value: string | null): boolean {
  return value === "false" ? false : true;
}
export const CONSTRUCTION_COLUMNS = [
  ["flex_position", "Natural FLEX"], ["composition", "Composition"],
  ["qb_team_offense_including_qb", "QB-team offense incl. QB"], ["qb_pass_catchers", "Same-team WR/TE"],
  ["qb_same_team_rb", "Same-team RB"], ["bring_backs", "Offensive bring-backs"],
  ["bring_back_positions", "Bring-back positions"], ["qb_game_all_players", "QB-game players incl. DST"],
  ["secondary_opposing_game_count", "Secondary opposing games"], ["true_unrelated_oneoffs", "True unrelated one-offs"],
  ["max_team_all", "Max team incl. DST"], ["max_team_offense", "Max team offense"],
] as const;
export type ConstructionSummary = {
  selected_count: number; definitions: string; research_scope: string; coverage: string;
  lineups: Array<Record<string, unknown>>;
  distributions: Record<string, Record<string, number>>;
};
export function constructionValue(value: unknown): string {
  if (value == null) return "Unavailable";
  if (Array.isArray(value)) return value.join(" + ") || "None";
  if (typeof value === "object") return Object.entries(value as Record<string, unknown>).map(([k, v]) => `${k} ${v}`).join(" · ");
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}
