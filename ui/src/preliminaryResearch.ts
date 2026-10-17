export type PreliminarySnapshot = {
  analyst_intent_handoffs?: Partial<Record<"EXPECTED_GAME" | "CONTRARIAN", import("./analystPreparation").AnalystHandoff>>;
  analyst_handoff?: import("./analystPreparation").AnalystHandoff | null;
  snapshot_sha256: string; classification: "PRELIMINARY_RESEARCH"; entry_ready: false;
  scope: { season: number; week: number; slate: string; contest_format: "classic" };
  projection_run_id: string; ownership_run_id: string; preparation_job_id?: string; data_cutoff_at?: string;
  normal_reason_codes: string[]; assumption_manifest_sha256: string;
  assumption_manifest: { declared_at: string; injury_policy: string; exclude_player_ids: string[]; practice_assumption: string; other_player_assumption: string; known_unavailable_policy: string; source_truth: string; players: unknown[] };
};
export function preliminaryScopeIssue(snapshot: PreliminarySnapshot, scope: {season: number; week: number; slate: string}): string | null {
  return snapshot.scope.season === scope.season && snapshot.scope.week === scope.week && snapshot.scope.slate === scope.slate && snapshot.entry_ready === false ? null : "The research snapshot does not match the selected slate.";
}
export function preliminaryRunParams(params: Record<string, unknown>, noSeasonRankRestriction: boolean): Record<string, unknown> {
  if (params.exclude_questionable !== true) throw new Error("Enable Exclude questionable players before preliminary generation.");
  if (Array.isArray(params.availability_overrides) && params.availability_overrides.length || params.assume_questionable_out === true) throw new Error("Preliminary generation preserves source availability; clear projection availability overrides first.");
  const copy = {...params};
  if (copy.prepared_input_job_id || copy.allow_incomplete_evidence) throw new Error("Use the explicit preliminary snapshot rather than ordinary readiness overrides.");
  if (noSeasonRankRestriction) for (const position of ["qb","rb","wr","te"]) delete copy[`season_ppg_top_pct_${position}`];
  return copy;
}

export function analystFocusedRunIssue(packet: Pick<import("./analystPacket").AnalystPacketMetadata, "focus_mode" | "focus_ids" | "scenario_options" | "selected_strategy"> | null): string | null {
  if (packet?.selected_strategy !== "MERGED_SCENARIOS" || packet.focus_mode !== "SELECTED_ONLY") return null;
  if (!packet.scenario_options?.length) return "Refresh available Analyst packets before selected-only generation; supported story options are not loaded.";
  if (!packet.focus_ids?.length) return "Choose at least one supported football story before selected-only generation.";
  const eligible = new Set(packet.scenario_options.filter(option => option.focus_applicable).map(option => option.scenario_id));
  return packet.focus_ids.every(id => eligible.has(id)) ? null : "A selected story is unavailable or is a composite stress without supported focused construction.";
}
