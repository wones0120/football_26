export type ReviewPlayer = { player_id: string; name: string; slot: string; team: string; position: string };
export type ReviewCandidate = {
  candidate_id: string; players: ReviewPlayer[]; ownership_availability: string;
  metrics: { selector_rank: number; projected_mean: number; summed_marginal_p90_proxy: number; salary_used: number;
    projected_total_ownership: number | null; projection_rank: number; ceiling_proxy_rank: number };
  quality_eligibility: { eligible: boolean; mean_fraction: number; ceiling_fraction: number };
  construction: { captain_player_id: string; captain_player_name: string; captain_position: string; captain_team: string;
    team_split: string; qb_structure: string; primary_football_scenario: string; primary_thesis_signature: string;
    scenario_tags: string[]; salary_remaining: number | null; risk_flags: string[] };
  market_compatibility: string; market_compatibility_reason_codes: string[];
};
export type CoverageRow = { family: string; label: string; generated: number; quality_eligible: number; finalists: number;
  absence_stage: string; highest_ceiling_nonfinalist_id: string | null; highest_ceiling_nonfinalist_fraction: number | null };
export type ReviewIdentity = { optimizer_run_id: string; season: number; week: number; slate: string; game_id: string;
  projection_run_id: string; evidence_cutoff: string; kickoff_at: string; ai_packet_hash: string; candidate_pool_hash: string;
  frozen_source_evidence_hash: string; review_policy_version: string; timing_status: string };
export type SelectionReview = {
  contract_id: string; nonbinding: boolean; protocol: string; run_identity: ReviewIdentity;
  counts: { quality_eligible: number; finalists: number; ceiling_outsiders: number };
  attention_shortlist: { rows: { candidate_id: string; attention_group: string }[];
    finalist_candidate_ids: string[]; ceiling_outsider_candidate_ids: string[] };
  candidates: ReviewCandidate[]; coverage: Record<string, CoverageRow[] | Record<string, number>>;
  control_candidate_ids: string[]; limitations: string[];
};
export type PairDiagnostic = {
  candidate_ids: string[]; shared_player_count: number; shared_player_names: string[]; unique_players_across_pair: number;
  overlap_message: string; shared_flex_player_count: number; same_captain: boolean;
  captains: { captain_player_name: string; captain_position: string; captain_team: string }[];
  primary_scripts: string[]; primary_theses: string[]; scenario_overlap: string[]; team_splits: string[]; qb_structures: string[];
  salary_used: (number | null)[]; means: number[]; p90_proxies: number[]; mean_fractions: number[]; ceiling_fractions: number[];
  min_mean_fraction: number; min_ceiling_fraction: number; market_compatibilities: string[]; risk_flags: string[][];
  ownership_availability: string[]; projected_total_ownership: (number | null)[];
  shared_core_projected_flex_ownership: (number | null)[];
  quality_opportunity_cost?: Record<string, { current: number; alternative: number; current_minus_alternative: number }>;
  player_substitutions?: { added: { name: string }[]; removed: { name: string }[] };
};
export type PairComparison = { proposed_pair: PairDiagnostic; alternative_portfolio: { status: string; ordering: string;
  alternatives: PairDiagnostic[]; feasible_pair_count: number | null } };
export type SelectionDecision = PairComparison & { decision_id: string; previous_decision_id: string | null; revision: number;
  status: string; decision_timestamp: string; record_hash: string; review_hash: string; proposed_candidate_ids: string[];
  reasoning: string; complementarity_reason: string; football_theses: string[]; accepted_high_overlap_exception: string | null;
  attention: { explicitly_considered_ids: string[]; other_displayed_candidate_ids: string[] };
  alternative_candidate_ids_considered: string[]; rejected_candidates: { candidate_id: string; reason: string }[];
  execution: { matches_approved_pair: boolean; entries: { contest_id: string; entry_id: string; candidate_id: string | null }[] } | null };
export type ReviewResponse = { review: SelectionReview; review_hash: string; selection_status: string;
  can_record_prelock: boolean; decision_history: SelectionDecision[]; server_time: string };
export type DecisionInput = { idempotency_key: string; previous_decision_id: string | null; review_hash: string;
  status: "PROPOSED" | "SELECTED" | "USER_APPROVED"; proposed_candidate_ids: string[]; explicitly_considered_ids: string[];
  other_displayed_candidate_ids: string[]; alternative_candidate_ids_considered: string[];
  rejected_candidates: { candidate_id: string; reason: string }[]; reasoning: string; football_theses: string[];
  complementarity_reason: string; accepted_high_overlap_exception: string | null; reviewer_type: string;
  reviewer_identity: string | null; model_name: string | null };

export function candidateIds(text: string): string[] {
  return [...new Set(text.split(/[\s,]+/).map(value => value.trim()).filter(Boolean))];
}

// ChatGPT returns an explicit recommendation, never a fabricated timestamp or
// entered/approval status. The app supplies provenance and revision metadata.
export function parseRecommendation(text: string, eligibleIds: Set<string>): {
  proposed_candidate_ids: string[]; explicitly_considered_ids: string[]; reasoning: string;
  football_theses: string[]; complementarity_reason: string; accepted_high_overlap_exception?: string;
  alternative_candidate_ids_considered?: string[]; rejected_candidates?: { candidate_id: string; reason: string }[];
} {
  const value = JSON.parse(text);
  const allowed = new Set(["proposed_candidate_ids", "explicitly_considered_ids", "reasoning", "football_theses",
    "complementarity_reason", "accepted_high_overlap_exception", "alternative_candidate_ids_considered", "rejected_candidates"]);
  if (!value || typeof value !== "object" || Array.isArray(value) || Object.keys(value).some(k => !allowed.has(k))) {
    throw new Error("Use the recommendation template; timestamps, outcomes, approval and entry status are supplied by the app.");
  }
  for (const key of ["proposed_candidate_ids", "explicitly_considered_ids", "alternative_candidate_ids_considered"]) {
    const ids = value[key] ?? [];
    if (!Array.isArray(ids) || ids.some(id => typeof id !== "string" || !eligibleIds.has(id)) || new Set(ids).size !== ids.length) {
      throw new Error(`${key} must contain unique exact IDs from this frozen run.`);
    }
  }
  if (value.proposed_candidate_ids?.length !== 2 || !Array.isArray(value.explicitly_considered_ids)
      || value.proposed_candidate_ids.some((id: string) => !value.explicitly_considered_ids.includes(id))) {
    throw new Error("Recommend exactly two IDs and explicitly list the candidates actually considered.");
  }
  if ([value.reasoning, value.complementarity_reason].some(x => typeof x !== "string" || !x.trim())
      || !Array.isArray(value.football_theses) || value.football_theses.length !== 2
      || value.football_theses.some((x: unknown) => typeof x !== "string" || !x.trim())) {
    throw new Error("Written reasoning, two football theses and complementarity are required.");
  }
  if (value.accepted_high_overlap_exception !== undefined && typeof value.accepted_high_overlap_exception !== "string") {
    throw new Error("The high-overlap exception must be written reasoning.");
  }
  if (value.rejected_candidates !== undefined && (!Array.isArray(value.rejected_candidates)
      || value.rejected_candidates.some((r: { candidate_id: string; reason: string }) => !r || !eligibleIds.has(r.candidate_id)
        || typeof r.reason !== "string" || !r.reason.trim()))) {
    throw new Error("Rejected candidates require exact IDs and written reasons.");
  }
  return value;
}
