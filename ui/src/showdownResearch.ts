export type ShowdownResearchNotes = {
  contract_id: "showdown_research_notes_v1";
  title: string; label: string; purpose: string; sample_period: string;
  sample: { games: number; contests: number; entries: number; unresolved_entries: number };
  success_definition: string; limitations: string;
  source: { path: string; sha256: string; captured_at: string };
  findings: { id: string; title: string; label: string; observation: string; sample_period: string; comparison_baseline: string; limitations: string }[];
};

type Coverage = {
  count: number; captain_archetypes: Record<string, number>; qb_counts: Record<string, number>;
  team_splits: Record<string, number>; receiver_captain_pairings: { with_own_qb: number; without_own_qb: number };
};

export type ShowdownPrelockChecklist = {
  contract_id: "showdown_prelock_review_checklist_v1";
  nonbinding: true; evidence_basis: string; data_cutoff_at: string; incomplete_evidence: boolean;
  scopes: Record<string, Coverage>;
  qb_families: { family: string; generated: number; quality_eligible: number; finalists: number; proposal: number; absence_stage: string; reason_codes: string[] }[];
  ownership_provenance: { status: string; sources: string[]; source_ids: string[]; observed_at: string | null };
  candidate_details: { candidate_id: string; captain: string; quality_eligible: boolean; physical_player_ids: string[]; salary_left: number | null; projected_total_ownership: number | null; ownership_unavailable_reason: string | null }[];
  proposed_pair: { basis: string; candidate_ids: string[]; physical_player_overlap: number | null; unavailable_reason: string | null };
  limitations: string[];
};
