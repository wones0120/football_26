export type AnalystPacketMetadata = {
  contract_id: string;
  packet_id: string;
  analyst_name: string;
  analyst_packet_sha256: string;
  decision_at: string;
  frozen_at: string;
  assessment_count: number;
  scenario_count?: number;
  captain_analysis_contract?: string | null;
  discovery_contract?: string | null;
  discovery_snapshot_sha256?: string | null;
  discovery_finding_count?: number;
  teammate_enabled?: boolean;
  joint_opportunity_enabled?: boolean;
  challenger_enabled?: boolean;
  focus_mode?: "MIXED" | "SELECTED_ONLY";
  focus_ids?: string[];
  scenario_options?: { scenario_id: string; label: string; game_ids: string[]; focus_applicable: boolean }[];
  selected_strategy?: "CONSTRUCTION" | "MERGED_SCENARIOS";
  games: { game_id: string; season: number; week: number; teams: string[];
    kickoff_at: string; format_membership: Record<string, string> }[];
};

export function captainAnalystEnabled(packet: AnalystPacketMetadata | null, format: "classic" | "showdown"): boolean {
  return format === "showdown" && packet?.selected_strategy === "MERGED_SCENARIOS" && packet.captain_analysis_contract === "captain_analysis_v1";
}

export function analystPacketScopeIssue(packet: AnalystPacketMetadata, season: number, week: number, format: "classic" | "showdown"): string | null {
  return packet.games.some(game => game.season === season && game.week === week && game.format_membership[format.toUpperCase()] === "confirmed_in_scope")
    ? null : "This packet has no confirmed game for the selected season, week and format.";
}

export function analystOptimizerParams(packet: AnalystPacketMetadata | null, format: "classic" | "showdown" = "classic"): Record<string, unknown> {
  const focused = packet?.selected_strategy === "MERGED_SCENARIOS" && packet.focus_mode === "SELECTED_ONLY";
  return packet ? { ...(packet.selected_strategy === "MERGED_SCENARIOS" && typeof packet.joint_opportunity_enabled === "boolean" ? {analyst_joint_opportunity_enabled:packet.joint_opportunity_enabled} : {}), ...(focused ? { analyst_scenario_focus_mode: "SELECTED_ONLY", analyst_scenario_focus_ids: packet?.focus_ids ?? [] } : {}), analyst_packet_sha256: packet.analyst_packet_sha256, analyst_candidates_per_thesis: 2, analyst_strategy: packet.selected_strategy ?? "CONSTRUCTION", ...(packet.selected_strategy === "MERGED_SCENARIOS" && format === "classic" ? { analyst_portfolio_mode: "SCENARIO_FIRST" } : {}), ...(!focused && format === "classic" && typeof packet.teammate_enabled === "boolean" && packet.selected_strategy === "MERGED_SCENARIOS" ? { analyst_teammate_enabled: packet.teammate_enabled } : {}), ...(!focused && format === "classic" && typeof packet.challenger_enabled === "boolean" && packet.selected_strategy === "MERGED_SCENARIOS" ? { analyst_challenger_enabled: packet.challenger_enabled } : {}) } : {};
}
