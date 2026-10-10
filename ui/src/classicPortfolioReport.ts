import type { OptimizerResponse } from "./api.ts";
export function portfolioSettingValue(key: string, value: unknown, requested = false): string {
  if ((value === null || value === undefined) && !requested && key === "max_elevated_players_per_lineup") return "No additional cap";
  if (value === null || value === undefined) return key === "max_lineups_per_primary_game" ? "No limit" : requested ? "Strategy default" : "Existing player/global caps";
  if (typeof value === "object") return Object.entries(value as Record<string, unknown>).map(([name, count]) => `${name}: ${count}`).join(" · ") || "None";
  if ((key === "max_exposure" || key === "elevated_player_max_exposure") && typeof value === "number") return `${Number((value * 100).toFixed(6))}%`;
  return String(value);
}
export function portfolioSettingsRows(optimizer: OptimizerResponse) {
  return (optimizer.portfolio_controls_report?.settings ?? []).map((row) => ({
    setting: row.setting, requested: portfolioSettingValue(row.key, row.requested, true),
    effective: portfolioSettingValue(row.key, row.effective), source: row.source.replaceAll("_", " "),
    achieved: portfolioSettingValue("achieved", row.achieved),
  }));
}
