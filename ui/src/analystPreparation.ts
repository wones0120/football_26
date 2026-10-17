import type { AnalystPacketMetadata } from "./analystPacket";
export type AnalystHandoffMode = "AUTO" | "MANUAL" | "BASELINE";
export type AnalystHandoff = {
  personal_context?: import("./PersonalThoughtSummary").PersonalContext;
  optimization_intent?: string; scenario_ids?: string[];
  contract_id: string; mode: AnalystHandoffMode; status: "compatible" | "needs_review" | "unavailable" | "baseline_only";
  checked_at: string; scope: { season: number; week: number; slate: string; format: "classic" | "showdown" | "CLASSIC" | "SHOWDOWN" };
  source_packet_sha256?: string | null; checked_packet_sha256?: string | null; packet_id?: string | null;
  research_decision_at?: string | null; preferred_strategy: "MERGED_SCENARIOS" | "CONSTRUCTION";
  active_features: string[]; changes: { kind: string; player_master_id?: string; finding_id?: string; reason: string }[];
  preferred_params?: { analyst_discovery_enabled?: boolean; analyst_challenger_enabled?: boolean; analyst_teammate_enabled?: boolean };
  missing_checks: string[]; compatibility_sha256: string; prepared_source_sha256: string; projection_run_id: string;
};

export function scopedAnalystHandoff(handoff: AnalystHandoff | null | undefined, scope: { season:number;week:number;slate:string;format:string }): AnalystHandoff | null {
  return handoff?.scope.season === scope.season && handoff.scope.week === scope.week && handoff.scope.slate.toUpperCase() === scope.slate.toUpperCase() && handoff.scope.format.toLowerCase() === scope.format.toLowerCase() ? handoff : null;
}

export function checkedAnalystSelection(mode: AnalystHandoffMode, handoff: AnalystHandoff | null, checked: AnalystPacketMetadata | null, manual: AnalystPacketMetadata | null): AnalystPacketMetadata | null {
  if (mode === "BASELINE") return null;
  if (!handoff?.checked_packet_sha256 || checked?.analyst_packet_sha256 !== handoff.checked_packet_sha256) return mode === "MANUAL" ? manual : null;
  if (mode === "MANUAL" && (!manual || ![handoff.source_packet_sha256, handoff.checked_packet_sha256].includes(manual.analyst_packet_sha256))) return manual;
  return { ...checked, selected_strategy: mode === "MANUAL" ? manual?.selected_strategy ?? handoff.preferred_strategy : handoff.preferred_strategy,
    challenger_enabled: mode === "MANUAL" && manual?.challenger_enabled != null ? manual.challenger_enabled : handoff.preferred_params?.analyst_challenger_enabled,
    joint_opportunity_enabled: manual?.joint_opportunity_enabled ?? false,
    teammate_enabled: mode === "MANUAL" && manual?.teammate_enabled != null ? manual.teammate_enabled : handoff.preferred_params?.analyst_teammate_enabled,
    ...(mode === "MANUAL" && manual ? { focus_mode: manual.focus_mode, focus_ids: manual.focus_ids } : {}) };
}

export function analystHandoffIssue(mode: AnalystHandoffMode, handoff: AnalystHandoff | null, selected: AnalystPacketMetadata | null): string | null {
  if (mode === "BASELINE") return null;
  if (!handoff) return "Prepare this slate again to check Analyst research against its current inputs, or explicitly choose baseline.";
  if (handoff.status === "unavailable" || !handoff.checked_packet_sha256) return "Preparation has no checked Analyst packet. Refresh research and prepare again, or explicitly choose baseline.";
  if (selected?.analyst_packet_sha256 !== handoff.checked_packet_sha256) return "The selected Analyst override is not checked against this prepared build. Prepare again with this choice; no fallback is used.";
  return null;
}
