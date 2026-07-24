export type LoadSummary = {
  dataset: string;
  season: number;
  week: number | null;
  rows_written: number;
};

export type LoadResponse = {
  summaries: LoadSummary[];
};

export type SlateLoadResponse = {
  resource: string;
  season: number;
  week: number;
  slate: string;
  rows_written: number;
  message: string;
  completed_at: string;
};

export type SlateReadinessStatus = "pass" | "warn" | "fail";

export type SlateReadinessGateKey =
  | "prediction"
  | "classic_cash"
  | "classic_gpp"
  | "showdown_cash"
  | "showdown_gpp"
  | "replay";

export type SlateReadinessCheck = {
  check_id: string;
  category: string;
  status: SlateReadinessStatus;
  message: string;
  value: unknown;
  threshold?: string | null;
  applies_to: SlateReadinessGateKey[];
  blocks: SlateReadinessGateKey[];
  details: Record<string, unknown>;
};

export type SlateReadinessGate = {
  status: SlateReadinessStatus;
  score: number;
  summary: Record<SlateReadinessStatus, number>;
  blocking_checks: string[];
  attention_checks: string[];
  message: string;
};

export type SlateReadinessResponse = {
  report_id: string;
  contract_id: string;
  season: number;
  week: number;
  slate: string;
  generated_at: string;
  status: SlateReadinessStatus;
  score: number;
  summary: Record<SlateReadinessStatus, number>;
  gates: Record<SlateReadinessGateKey, SlateReadinessGate>;
  checks: SlateReadinessCheck[];
};

export type DataQualityCheck = {
  quality_check_id: string;
  quality_run_id: string;
  check_id: string;
  category: string;
  status: SlateReadinessStatus;
  severity: string;
  table_name?: string | null;
  check_name: string;
  message: string;
  value: unknown;
  threshold?: string | null;
  affected_scope: Record<string, unknown>;
  details: Record<string, unknown>;
  created_at: string;
};

export type DataQualityRun = {
  quality_run_id: string;
  report_id?: string | null;
  contract_id: string;
  trigger: string;
  season: number;
  week?: number | null;
  slate?: string | null;
  status: SlateReadinessStatus;
  score: number;
  summary: Record<SlateReadinessStatus, number>;
  source_context: Record<string, unknown>;
  created_at: string;
  checks: DataQualityCheck[];
};

export type DataQualityHistoryResponse = {
  season: number;
  week?: number | null;
  slate?: string | null;
  runs: DataQualityRun[];
};

export type OptimizerResponse = {
  job_id: string;
  status: string;
  contest_format: "classic" | "showdown";
  objective: "cash" | "gpp";
  projection_run_id?: string | null;
  rule_run_id?: string | null;
  data_cutoff_at?: string | null;
  lineage_persisted: boolean;
  message?: string;
  results?: unknown;
  created_at?: string;
  updated_at?: string;
};

export type PredictionResponse = {
  season: number;
  week: number;
  rows_written: number;
  message: string;
  feature_run_id?: string | null;
  model_run_id?: string | null;
  projection_run_id?: string | null;
  data_cutoff_at?: string | null;
  target_persisted: boolean;
  calibration_metrics?: Record<string, unknown>;
};

export type PredictionRow = {
  player_id: string;
  player_display_name: string;
  position: string;
  recent_team: string;
  opponent_team: string;
  salary?: number | null;
  season: number;
  week: number;
  predicted_mean: number;
  predicted_p10: number;
  predicted_p25: number;
  predicted_p50: number;
  predicted_p75: number;
  predicted_p90: number;
  model: string;
  feature_run_id?: string | null;
  model_run_id?: string | null;
  projection_run_id?: string | null;
  data_cutoff_at?: string | null;
  game_id?: string | null;
  calibration_method?: string;
  calibration_position?: string;
  calibration_role?: string;
  calibration_sample_size?: number;
  team_implied_total?: number;
  team_spread?: number;
  game_total?: number;
  opp_pts_allowed_pos_3?: number;
  opp_pts_allowed_pos_5?: number;
  run_funnel?: number;
  pass_funnel?: number;
  last3_points: number[];
  last3_avg: number;
  recent_median: number;
  recent_robust: number;
  delta_vs_last3: number;
  team_pos_avg: number;
  adj_mean: number;
  adj_mean_base: number;
  matchup_factor: number;
  adj_mean_final: number;
};

export type PredictionListResponse = {
  season: number;
  week: number;
  projection_run_id?: string | null;
  rows: PredictionRow[];
};

export type OwnershipProjectionRow = {
  player_id: string;
  player_master_id?: string | null;
  player_display_name: string;
  roster_position?: string | null;
  projected_ownership: number;
  actual_ownership?: number | null;
  source?: string | null;
  ownership_run_id?: string | null;
  data_cutoff_at?: string | null;
  salary?: number | null;
  projection_mean?: number | null;
  projection_p90?: number | null;
  salary_percentile?: number | null;
  projection_percentile?: number | null;
  prior_player_ownership?: number | null;
  contest_format?: string | null;
  roster_slot?: string | null;
  model_metrics_json?: string | null;
};

export type OwnershipProjectionListResponse = {
  season: number;
  week: number;
  slate?: string | null;
  rows: OwnershipProjectionRow[];
};

export type SimulationPlayerRow = {
  player_id: string;
  player_display_name: string;
  position: string;
  salary: number;
  projection_mean: number;
  optimal_lineup_count: number;
  optimal_lineup_probability: number;
  field_ownership?: number | null;
  leverage_score?: number | null;
};

export type SimulationResponse = {
  simulation_run_id: string;
  simulation_model_id: string;
  season: number;
  week: number;
  slate: string;
  contest_format: string;
  projection_run_id: string;
  ownership_run_id?: string | null;
  num_simulations: number;
  successful_simulations: number;
  seed: number;
  status: string;
  message: string;
  data_cutoff_at?: string | null;
  created_at: string;
  rows: SimulationPlayerRow[];
};

export type StartingQBResponse = {
  season: number;
  week: number;
  slate: string;
  rows_written: number;
  message: string;
  completed_at: string;
};

export type UnmatchedSalaryRow = {
  season: number;
  week: number;
  slate: string;
  name: string;
  player_team: string;
  created_at: string;
};

export type UnmatchedSalaryResponse = {
  rows: UnmatchedSalaryRow[];
};

export type UnmatchedInjuryRow = {
  season: number;
  week: number;
  slate: string;
  name: string;
  player_team: string;
  opponent: string;
  status?: string;
};

export type UnmatchedInjuryResponse = {
  rows: UnmatchedInjuryRow[];
};

export type ValidationRow = {
  season: number;
  week: number;
  rows: number;
  expected_rows?: number | null;
  status: "ok" | "partial" | "missing";
};

export type ValidationResponse = {
  table: string;
  results: ValidationRow[];
};

export type CurrentContext = {
  season: number;
  week: number;
  provider: string;
};

export type BuildFeaturesResponse = {
  season: number;
  weeks?: number[] | null;
  rows_written: number;
  message: string;
};

export type ProcessUnmatchedResponse = {
  added: number;
  skipped_existing: number;
  processed: number;
  message: string;
};

export type StartPostgresResponse = {
  ok: boolean;
  message: string;
  stdout?: string;
  stderr?: string;
};

export type AgentRunResponse = {
  season: number;
  week: number;
  rule_run_id: string;
  projection_run_id?: string | null;
  target_persisted: boolean;
  adjusted_rows: number;
  adjustments: {
    player_id: string;
    reason: string;
    projection_delta: number;
    ceiling_delta: number;
    ownership_delta: number;
  }[];
  config: Record<string, unknown>;
  trace_rows: number;
  traces: AgentTrace[];
};

export type AgentTrace = {
  player_id: string;
  rule_id: string;
  rule_name: string;
  reason: string;
  mean_before: number;
  mean_after: number;
  p90_before: number;
  p90_after: number;
  mean_multiplier: number;
  p90_multiplier: number;
};

export type SymbolicRule = {
  rule_id: string;
  rule_name: string;
  rule_type: string;
  enabled: boolean;
  priority: number;
  version: number;
  condition_json: Record<string, unknown>;
  action_json: Record<string, unknown>;
};

export type SymbolicBacktestMetrics = {
  rows: number;
  base_mae: number;
  adjusted_mae: number;
  mae_delta: number;
  base_rmse: number;
  adjusted_rmse: number;
  rmse_delta: number;
  base_bias: number;
  adjusted_bias: number;
  improved_rows: number;
  worse_rows: number;
  unchanged_rows: number;
  hit_rate: number;
};

export type SymbolicBacktestRuleMetrics = SymbolicBacktestMetrics & {
  rule_id: string;
  rule_name: string;
};

export type SymbolicBacktestResponse = {
  filters: Record<string, unknown>;
  overall: SymbolicBacktestMetrics;
  by_rule: SymbolicBacktestRuleMetrics[];
  runs: Record<string, unknown>[];
};

export type NewsMonitorSignal = {
  signal_type: string;
  signal_text: string;
  dfs_relevance: string;
  confidence: string;
  player_name?: string | null;
  team?: string | null;
  source_link?: string | null;
};

export type NewsMonitorHeadline = {
  source_id: string;
  title?: string | null;
  link?: string | null;
  published_at?: string | null;
};

export type NewsMonitorSourceCheck = {
  source_id: string;
  source_name: string;
  status: string;
  items_seen: number;
  items_inserted: number;
  signals_inserted: number;
};

export type NewsMonitorSourceError = {
  source_id: string;
  error: string;
};

export type NewsMonitorReportSummary = {
  high_priority_count: number;
  items_needing_manual_review: number;
};

export type NewsMonitorReport = {
  date: string;
  summary: NewsMonitorReportSummary;
  high_priority_signals: NewsMonitorSignal[];
  injury_updates: NewsMonitorSignal[];
  roster_moves: NewsMonitorSignal[];
  depth_chart_notes: NewsMonitorSignal[];
  manual_review: NewsMonitorSignal[];
  team_headlines: NewsMonitorHeadline[];
  sources_checked: NewsMonitorSourceCheck[];
  source_errors: NewsMonitorSourceError[];
};

export type NewsMonitorRunResponse = {
  run_id: string;
  run_date: string;
  status: string;
  forced: boolean;
  skipped: boolean;
  message: string;
  sources_checked: number;
  items_ingested: number;
  signals_extracted: number;
  completed_at: string;
  report: NewsMonitorReport;
};

export type NewsMonitorFeedbackChoice = "Valuable" | "Relevant" | "Monitor" | "Noise";

export type NewsMonitorFeedbackRow = {
  feedback_id: string;
  run_date: string;
  signal_key: string;
  signal_type: string;
  signal_text: string;
  player_name?: string | null;
  team?: string | null;
  source_link?: string | null;
  feedback_choice?: NewsMonitorFeedbackChoice | null;
  note_text: string;
  created_at: string;
  updated_at: string;
};

export type NewsMonitorFeedbackListResponse = {
  rows: NewsMonitorFeedbackRow[];
};

export type BeliefScope = "global" | "contest_profile" | "season" | "weekly" | "game" | "player";
export type BeliefDirection = "boost" | "fade" | "prefer" | "avoid" | "monitor" | "neutral";

export type HumanBelief = {
  belief_version_id: string;
  belief_id: string;
  belief_version: number;
  supersedes_version_id?: string | null;
  operation: "created" | "revised" | "deactivated" | "reactivated";
  status: "active" | "inactive";
  scope_type: BeliefScope;
  subject_label?: string | null;
  subject_id?: string | null;
  season?: number | null;
  week?: number | null;
  slate?: string | null;
  contest_format?: "classic" | "showdown" | null;
  objective?: "cash" | "gpp" | null;
  direction: BeliefDirection;
  strength: number;
  confidence: number;
  thought_text: string;
  evidence_text?: string | null;
  expires_at?: string | null;
  is_retrospective: boolean;
  is_expired: boolean;
  impact_status: string;
  source: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type BeliefListResponse = {
  rows: HumanBelief[];
  summary: {
    total: number;
    active: number;
    inactive: number;
    expired: number;
    by_scope: Record<string, number>;
  };
};

export type BeliefCreatePayload = {
  scope_type: BeliefScope;
  subject_label?: string | null;
  subject_id?: string | null;
  season?: number | null;
  week?: number | null;
  slate?: string | null;
  contest_format?: "classic" | "showdown" | null;
  objective?: "cash" | "gpp" | null;
  direction: BeliefDirection;
  strength: number;
  confidence: number;
  thought_text: string;
  evidence_text?: string | null;
  expires_at?: string | null;
  is_retrospective: boolean;
  source?: string;
  metadata?: Record<string, unknown>;
};

export type BeliefRevisionPayload = Partial<Omit<BeliefCreatePayload, "scope_type">>;

export type ThoughtCaptureContext = "auto" | "general" | "slate" | "player";

export type ThoughtCandidate = {
  candidate_id: string;
  capture_id: string;
  ordinal: number;
  scope_type: BeliefScope;
  subject_label?: string | null;
  subject_id?: string | null;
  season?: number | null;
  week?: number | null;
  slate?: string | null;
  contest_format?: "classic" | "showdown" | null;
  objective?: "cash" | "gpp" | null;
  direction: BeliefDirection;
  strength: number;
  confidence: number;
  thought_text: string;
  extraction_reason: string;
  status: "pending" | "accepted" | "rejected";
  decision_id?: string | null;
  belief_id?: string | null;
  belief_version_id?: string | null;
  reviewed_payload: Record<string, unknown>;
  created_at: string;
  decided_at?: string | null;
};

export type ThoughtCapture = {
  capture_id: string;
  context_type: ThoughtCaptureContext;
  raw_text: string;
  subject_label?: string | null;
  subject_id?: string | null;
  season?: number | null;
  week?: number | null;
  slate?: string | null;
  contest_format?: "classic" | "showdown" | null;
  objective?: "cash" | "gpp" | null;
  extraction_policy_id: string;
  notices: string[];
  source: string;
  created_at: string;
  candidates: ThoughtCandidate[];
};

export type ThoughtCaptureListResponse = { rows: ThoughtCapture[] };

export type BeliefImpactMetricSet = {
  projection_mean: number | null;
  projection_p10: number | null;
  projection_p50: number | null;
  projection_p90: number | null;
  field_ownership_pct: number | null;
  portfolio_exposure_pct: number | null;
  optimal_lineup_probability: number | null;
};

export type BeliefImpactPreview = {
  preview_id: string;
  belief_version_id: string;
  belief_id: string;
  policy_id: string;
  season: number;
  week: number;
  slate?: string | null;
  contest_format?: string | null;
  objective?: string | null;
  target_player_id: string;
  target_label: string;
  adjustment_pct: number;
  baseline: BeliefImpactMetricSet;
  proposed: BeliefImpactMetricSet;
  delta: BeliefImpactMetricSet;
  modifier: Record<string, unknown>;
  lineage: Record<string, unknown>;
  notices: string[];
  status: "pending" | "approved" | "rejected";
  decision_id?: string | null;
  note_text?: string | null;
  approved_modifier: Record<string, unknown>;
  created_at: string;
  decided_at?: string | null;
};

export type BeliefImpactPreviewListResponse = { rows: BeliefImpactPreview[] };

export type DigitalTwinVariantComparisonRow = {
  player_id: string;
  player_label: string;
  projection_multiplier: number;
  model_projection_mean: number | null;
  combined_projection_mean: number | null;
  projection_mean_delta: number | null;
  approved_decision_ids: string[];
  approved_preview_ids: string[];
};

export type DigitalTwinVariantComparison = {
  player_count: number;
  players_with_human_input: number;
  players_unchanged: number;
  changed_players: DigitalTwinVariantComparisonRow[];
};

export type DigitalTwinVariantSet = {
  variant_set_id: string;
  policy_id: string;
  season: number;
  week: number;
  slate: string;
  contest_format?: string | null;
  objective?: string | null;
  projection_run_id: string;
  projection_data_cutoff_at?: string | null;
  decision_cutoff_at: string;
  status: "completed";
  created_at: string;
  variant_ids: Record<string, string>;
  artifact_hashes: Record<string, string>;
  artifacts: Record<string, Record<string, unknown>>;
  comparison: DigitalTwinVariantComparison;
};

export type DigitalTwinVariantSetListResponse = { rows: DigitalTwinVariantSet[] };

export type DigitalTwinVariantReplay = {
  variant_set_id: string;
  policy_id: string;
  status: "verified" | "mismatch";
  checks: Record<string, boolean>;
  stored_hashes: Record<string, string>;
  recomputed_hashes: Record<string, string>;
  comparison: DigitalTwinVariantComparison;
};

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";

// Allow long-running operations (feature builds, predictions); 10 minutes default.
const DEFAULT_TIMEOUT_MS = 600_000;

function normalizeFetchError(error: unknown): Error {
  if (error instanceof DOMException && error.name === "AbortError") {
    return new Error(`Request timed out while contacting ${API_BASE}`);
  }
  if (error instanceof TypeError) {
    return new Error(`Could not reach the backend API at ${API_BASE}`);
  }
  return error instanceof Error ? error : new Error(String(error));
}

async function postJson<T>(path: string, body: unknown, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (!res.ok) {
      throw new Error(await extractError(res));
    }
    return (await res.json()) as T;
  } catch (error) {
    throw normalizeFetchError(error);
  } finally {
    window.clearTimeout(timeout);
  }
}

async function getJson<T>(path: string, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_BASE}${path}`, { signal: controller.signal });
    if (!res.ok) {
      throw new Error(await extractError(res));
    }
    return (await res.json()) as T;
  } catch (error) {
    throw normalizeFetchError(error);
  } finally {
    window.clearTimeout(timeout);
  }
}

async function getJsonOrNull<T>(path: string, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T | null> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_BASE}${path}`, { signal: controller.signal });
    if (res.status === 404) {
      return null;
    }
    if (!res.ok) {
      throw new Error(await extractError(res));
    }
    return (await res.json()) as T;
  } catch (error) {
    throw normalizeFetchError(error);
  } finally {
    window.clearTimeout(timeout);
  }
}

async function patchJson<T>(path: string, body: unknown, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (!res.ok) {
      throw new Error(await extractError(res));
    }
    return (await res.json()) as T;
  } catch (error) {
    throw normalizeFetchError(error);
  } finally {
    window.clearTimeout(timeout);
  }
}

async function extractError(res: Response): Promise<string> {
  const text = await res.text();
  try {
    const payload = JSON.parse(text);
    if (payload.detail) {
      return payload.detail;
    }
  } catch {
    // ignore JSON parse failure
  }
  return text || res.statusText;
}

export function loadSeason(payload: {
  season: number;
  datasets?: string[];
}): Promise<LoadResponse> {
  return postJson("/season/load", payload);
}

export function loadWeek(payload: {
  season: number;
  week: number;
  datasets?: string[];
}): Promise<LoadResponse> {
  return postJson("/week/load", payload);
}

export function loadRawWeek(payload: {
  season: number;
  week: number;
}): Promise<LoadResponse> {
  return postJson("/raw/week/stats", payload);
}

export function loadRawSeason(payload: {
  season: number;
}): Promise<LoadResponse> {
  return postJson("/raw/season/load", payload);
}

export function loadRawWeekRosters(payload: {
  season: number;
  week: number;
}): Promise<LoadResponse> {
  return postJson("/raw/week/rosters", payload);
}

export function loadRawSalaries(payload: {
  season: number;
  week: number;
  slate: string;
  path: string;
}): Promise<LoadResponse> {
  return postJson("/raw/salaries/load", payload);
}

export function loadRawInjuries(payload: {
  season: number;
  week: number;
  slate: string;
  path: string;
}): Promise<SlateLoadResponse> {
  return postJson("/raw/injuries/load", payload);
}

export function loadSlateResource(
  type: "salaries" | "injuries",
  payload: { season: number; week: number; slate: string }
): Promise<SlateLoadResponse> {
  return postJson(`/slate/${type}`, payload);
}

export function runOptimizer(payload: {
  season: number;
  week: number;
  slate: string;
  strategy: string;
  contest_format: "classic" | "showdown";
  objective: "cash" | "gpp";
  projection_run_id?: string;
  rule_run_id?: string;
  data_cutoff_at?: string;
  params?: Record<string, unknown>;
}): Promise<OptimizerResponse> {
  return postJson("/optimizer/run", payload);
}

export function fetchOptimizerResults(jobId: string): Promise<OptimizerResponse> {
  return getJson(`/optimizer/results/${jobId}`);
}

export function fetchCurrentContext(): Promise<CurrentContext> {
  return getJson("/meta/current");
}

export function runPredictions(payload: {
  season: number;
  week: number;
  positions?: string[];
  slate?: string;
  data_cutoff_at?: string;
}): Promise<PredictionResponse> {
  return postJson("/predict/run", payload);
}

export function fetchValidation(table?: string): Promise<ValidationResponse> {
  const suffix = table ? `?table=${encodeURIComponent(table)}` : "";
  return getJson(`/data/validate${suffix}`);
}

export function fetchSlateReadiness(params: {
  season: number;
  week: number;
  slate: string;
  record?: boolean;
}): Promise<SlateReadinessResponse> {
  const query = new URLSearchParams({
    season: String(params.season),
    week: String(params.week),
    slate: params.slate,
  });
  if (params.record) query.set("record", "true");
  return getJson(`/slate/readiness?${query.toString()}`);
}

export function fetchDataQualityHistory(params: {
  season: number;
  week?: number;
  slate?: string;
  limit?: number;
}): Promise<DataQualityHistoryResponse> {
  const query = new URLSearchParams({
    season: String(params.season),
    limit: String(params.limit ?? 12),
  });
  if (params.week !== undefined) query.set("week", String(params.week));
  if (params.slate) query.set("slate", params.slate);
  return getJson(`/data/quality/history?${query.toString()}`);
}

export function fetchLatestPredictions(params: {
  season: number;
  week: number;
  limit?: number;
  slate?: string;
  projectionRunId?: string;
}): Promise<PredictionListResponse> {
  const query = new URLSearchParams({
    season: String(params.season),
    week: String(params.week),
    limit: String(params.limit ?? 1000),
    ...(params.slate ? { slate: params.slate } : {}),
    ...(params.projectionRunId ? { projection_run_id: params.projectionRunId } : {}),
  });
  return getJson(`/predict/latest?${query.toString()}`);
}

export function fetchLatestOwnership(params: {
  season: number;
  week: number;
  limit?: number;
  slate?: string;
}): Promise<OwnershipProjectionListResponse> {
  const query = new URLSearchParams({
    season: String(params.season),
    week: String(params.week),
    limit: String(params.limit ?? 1000),
    ...(params.slate ? { slate: params.slate } : {}),
  });
  return getJson(`/ownership/latest?${query.toString()}`);
}

export function runSlateSimulation(payload: {
  season: number;
  week: number;
  slate: string;
  contest_format?: "classic" | "showdown";
  num_simulations?: number;
  seed?: number;
  salary_cap?: number;
  projection_run_id?: string;
  ownership_run_id?: string;
}): Promise<SimulationResponse> {
  return postJson("/simulations/run", payload, 120_000);
}

export function fetchLatestSlateSimulation(params: {
  season: number;
  week: number;
  slate: string;
  contestFormat?: "classic" | "showdown";
  projectionRunId?: string;
}): Promise<SimulationResponse | null> {
  const query = new URLSearchParams({
    season: String(params.season),
    week: String(params.week),
    slate: params.slate,
    contest_format: params.contestFormat ?? "classic",
    ...(params.projectionRunId ? { projection_run_id: params.projectionRunId } : {}),
  });
  return getJsonOrNull(`/simulations/latest?${query.toString()}`);
}

export function loadStartingQBs(payload: {
  season: number;
  week: number;
  slate: string;
}): Promise<StartingQBResponse> {
  return postJson("/slate/starting-qbs", payload);
}

export function buildFeatures(payload: {
  season: number;
  weeks?: number[];
  future_week?: number;
}): Promise<BuildFeaturesResponse> {
  return postJson("/features/build", payload);
}

export function processUnmatchedToPlayerMaster(payload: {
  season?: number;
  week?: number;
  source?: string;
}): Promise<ProcessUnmatchedResponse> {
  return postJson("/data/unmatched/process", payload);
}

export function fetchUnmatchedSalaries(params?: {
  season?: number;
  week?: number;
  slate?: string;
  limit?: number;
}): Promise<UnmatchedSalaryResponse> {
  const query = new URLSearchParams();
  if (params?.season) query.set("season", String(params.season));
  if (params?.week) query.set("week", String(params.week));
  if (params?.slate) query.set("slate", params.slate);
  query.set("limit", String(params?.limit ?? 50));
  return getJson(`/data/unmatched-salaries?${query.toString()}`);
}

export function fetchUnmatchedInjuries(params?: {
  season?: number;
  week?: number;
  slate?: string;
  limit?: number;
}): Promise<UnmatchedInjuryResponse> {
  const query = new URLSearchParams();
  if (params?.season) query.set("season", String(params.season));
  if (params?.week) query.set("week", String(params.week));
  if (params?.slate) query.set("slate", params.slate);
  query.set("limit", String(params?.limit ?? 50));
  return getJson(`/data/unmatched-injuries?${query.toString()}`);
}

export function startPostgres(): Promise<StartPostgresResponse> {
  return postJson("/utils/postgres/start", {});
}

export type OwnershipPayoutTierInput = {
  min_rank: number;
  max_rank: number;
  payout?: number;
  prize_description?: string;
};

export type OwnershipLoadPayload = {
  season: number;
  week: number;
  slate: string;
  path: string;
  contest_id?: string;
  contest_name?: string;
  contest_format?: "classic" | "showdown";
  contest_type?: "cash" | "gpp";
  entry_fee?: number;
  field_size?: number;
  max_entries_per_user?: number;
  prize_pool?: number;
  payout_tiers?: OwnershipPayoutTierInput[];
};

export function loadOwnership(payload: OwnershipLoadPayload): Promise<{
  season: number;
  week: number;
  slate: string;
  rows_written: number;
  message: string;
  contest_id?: string | null;
  source_file_id?: string | null;
  target_persisted: boolean;
}> {
  return postJson("/ownership/load", payload);
}

export type DraftKingsBatchFile = {
  path: string;
  file_type: string;
  status: string;
  season: number;
  week: number;
  slate: string;
  rows_written: number;
  source_file_id?: string | null;
  contest_id?: string | null;
  template_id?: string | null;
  message: string;
};

export function batchImportDraftKings(payload: {
  directory: string;
  season: number;
  week: number;
  slate: string;
  recursive?: boolean;
  dry_run?: boolean;
}): Promise<{
  batch_id: string;
  directory: string;
  discovered: number;
  imported: number;
  deduplicated: number;
  skipped: number;
  failed: number;
  dry_run: boolean;
  files: DraftKingsBatchFile[];
}> {
  return postJson("/imports/draftkings/batch", payload);
}

export type PortfolioAssignment = {
  assignment_id: string;
  portfolio_id: string;
  template_id: string;
  template_row_number: number;
  entry_id: string;
  contest_id: string;
  lineup_id: string;
  portfolio_lineup_number: number;
};

export type PortfolioResponse = {
  portfolio_id: string;
  portfolio_name: string;
  optimizer_run_id: string;
  template_id: string;
  season: number;
  week: number;
  slate: string;
  contest_format: "classic" | "showdown";
  objective: "cash" | "gpp";
  status: string;
  lineup_count: number;
  assignment_count: number;
  assignments: PortfolioAssignment[];
};

export function createPortfolio(payload: {
  portfolio_name: string;
  optimizer_run_id: string;
  template_id: string;
  lineup_ids?: string[];
  default_contest_id?: string;
}): Promise<PortfolioResponse> {
  return postJson("/portfolios", payload);
}

export function fetchPortfolio(portfolioId: string): Promise<PortfolioResponse> {
  return getJson(`/portfolios/${encodeURIComponent(portfolioId)}`);
}

export type DraftKingsExportResponse = {
  export_id: string;
  portfolio_id: string;
  contest_format: "classic" | "showdown";
  file_name: string;
  row_count: number;
  content_sha256: string;
  csv_content: string;
  validation_id: string;
};

export type ExportValidationResponse = {
  validation_id: string;
  portfolio_id: string;
  status: "passed" | "failed";
  checks_run: number;
  errors: { code: string; message: string; lineup_number?: number; player_id?: string }[];
  warnings: { code: string; message: string; lineup_number?: number; player_id?: string }[];
};

export function validateDraftKingsExport(portfolioId: string): Promise<ExportValidationResponse> {
  return postJson(`/portfolios/${encodeURIComponent(portfolioId)}/exports/draftkings/validate`, {});
}

export function generateDraftKingsExport(portfolioId: string): Promise<DraftKingsExportResponse> {
  return postJson(`/portfolios/${encodeURIComponent(portfolioId)}/exports/draftkings`, {});
}

export function draftKingsExportDownloadUrl(exportId: string): string {
  return `${API_BASE}/exports/${encodeURIComponent(exportId)}/download`;
}

export function runOwnershipModel(payload: {
  season: number;
  week: number;
  slate?: string;
  positions?: string[];
  data_cutoff_at?: string;
}): Promise<{ season: number; week: number; slate?: string; rows_written: number; message: string; ownership_run_id?: string | null; data_cutoff_at?: string | null; target_persisted?: boolean; model_metrics?: Record<string, unknown> }> {
  return postJson("/ownership/run", payload);
}

export function analyzePastSlate(payload: {
  season: number;
  week: number;
  slate: string;
  path: string;
  top_n?: number;
}): Promise<{
  season: number;
  week: number;
  slate: string;
  lineups: number;
  top_n: number;
  exposures: {
    player_display_name: string;
    roster_position?: string | null;
    count: number;
    pct: number;
  }[];
  bucket_stats?: {
    bucket: string;
    lineups: number;
    avg_actual_own_sum: number;
    median_actual_own_sum: number;
    avg_num_chalk: number;
    avg_num_low_owned: number;
    avg_total_salary: number;
    avg_num_sub_4k: number;
  }[];
  top_lineups?: {
    rank: number;
    final_points: number;
    entry_id: string;
    salary_used: number;
    salary_left: number;
    players?: string;
    total_own_sum: number;
    avg_own: number;
    num_chalk: number;
    num_low_owned: number;
    num_sub_4k: number;
    qb_stack_type: string;
    bring_back_count: number;
    notes: string;
  }[];
  message: string;
}> {
  return postJson("/ownership/analyze-past", payload);
}

export function runAgent(season: number, week: number, slate?: string): Promise<AgentRunResponse> {
  return postJson("/agent/run", { season, week, slate });
}

export function fetchSymbolicRules(params?: {
  include_disabled?: boolean;
}): Promise<{ rows: SymbolicRule[] }> {
  const includeDisabled = params?.include_disabled ?? true;
  return getJson(`/agent/rules?include_disabled=${includeDisabled ? "true" : "false"}`);
}

export function upsertSymbolicRule(payload: SymbolicRule): Promise<SymbolicRule> {
  return postJson("/agent/rules", payload);
}

export function setSymbolicRuleEnabled(ruleId: string, enabled: boolean): Promise<SymbolicRule> {
  return patchJson(`/agent/rules/${encodeURIComponent(ruleId)}/enabled`, { enabled });
}

export function fetchSymbolicBacktest(params?: {
  season?: number;
  week?: number;
  rule_run_id?: string;
  slate?: string;
}): Promise<SymbolicBacktestResponse> {
  const query = new URLSearchParams();
  if (params?.season) query.set("season", String(params.season));
  if (params?.week) query.set("week", String(params.week));
  if (params?.rule_run_id) query.set("rule_run_id", params.rule_run_id);
  if (params?.slate) query.set("slate", params.slate);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return getJson(`/agent/backtest${suffix}`);
}

export function fetchNewsMonitorReport(runDate: string): Promise<NewsMonitorRunResponse | null> {
  return getJsonOrNull(`/news-monitor/report/${encodeURIComponent(runDate)}`);
}

export function runNewsMonitor(payload: {
  run_date?: string;
  force?: boolean;
  source_ids?: string[];
}): Promise<NewsMonitorRunResponse> {
  return postJson("/news-monitor/run", payload);
}

export function fetchNewsMonitorFeedback(runDate: string): Promise<NewsMonitorFeedbackListResponse> {
  return getJson(`/news-monitor/feedback/${encodeURIComponent(runDate)}`);
}

export function upsertNewsMonitorFeedback(payload: {
  run_date: string;
  signal_key: string;
  signal_type: string;
  signal_text: string;
  player_name?: string | null;
  team?: string | null;
  source_link?: string | null;
  feedback_choice?: NewsMonitorFeedbackChoice | null;
  note_text?: string;
}): Promise<NewsMonitorFeedbackRow> {
  return postJson("/news-monitor/feedback", payload);
}

export function fetchDigitalTwinBeliefs(params?: {
  season?: number;
  week?: number;
  slate?: string;
  include_inactive?: boolean;
  limit?: number;
}): Promise<BeliefListResponse> {
  const query = new URLSearchParams();
  if (params?.season) query.set("season", String(params.season));
  if (params?.week) query.set("week", String(params.week));
  if (params?.slate) query.set("slate", params.slate);
  query.set("include_inactive", String(params?.include_inactive ?? true));
  query.set("limit", String(params?.limit ?? 200));
  return getJson(`/digital-twin/beliefs?${query.toString()}`);
}

export function fetchDigitalTwinThoughtCaptures(params?: {
  season?: number;
  week?: number;
  slate?: string;
  limit?: number;
}): Promise<ThoughtCaptureListResponse> {
  const query = new URLSearchParams();
  if (params?.season) query.set("season", String(params.season));
  if (params?.week) query.set("week", String(params.week));
  if (params?.slate) query.set("slate", params.slate);
  query.set("limit", String(params?.limit ?? 20));
  return getJson(`/digital-twin/thought-captures?${query.toString()}`);
}

export function createDigitalTwinThoughtCapture(payload: {
  context_type: ThoughtCaptureContext;
  raw_text: string;
  subject_label?: string | null;
  subject_id?: string | null;
  season?: number | null;
  week?: number | null;
  slate?: string | null;
  contest_format?: "classic" | "showdown" | null;
  objective?: "cash" | "gpp" | null;
  source?: string;
}): Promise<ThoughtCapture> {
  return postJson("/digital-twin/thought-captures", payload);
}

export function decideDigitalTwinThoughtCandidate(
  candidateId: string,
  decision: "accepted" | "rejected",
  belief?: BeliefCreatePayload,
): Promise<ThoughtCandidate> {
  return postJson(`/digital-twin/thought-candidates/${encodeURIComponent(candidateId)}/decision`, {
    decision,
    belief: belief ?? null,
  });
}

export function createDigitalTwinBelief(payload: BeliefCreatePayload): Promise<HumanBelief> {
  return postJson("/digital-twin/beliefs", payload);
}

export function reviseDigitalTwinBelief(
  beliefId: string,
  payload: BeliefRevisionPayload,
): Promise<HumanBelief> {
  return postJson(`/digital-twin/beliefs/${encodeURIComponent(beliefId)}/revisions`, payload);
}

export function setDigitalTwinBeliefStatus(
  beliefId: string,
  status: "active" | "inactive",
): Promise<HumanBelief> {
  return postJson(`/digital-twin/beliefs/${encodeURIComponent(beliefId)}/status`, { status });
}

export function fetchDigitalTwinImpactPreviews(params?: {
  belief_id?: string;
  season?: number;
  week?: number;
  slate?: string;
  limit?: number;
}): Promise<BeliefImpactPreviewListResponse> {
  const query = new URLSearchParams();
  if (params?.belief_id) query.set("belief_id", params.belief_id);
  if (params?.season) query.set("season", String(params.season));
  if (params?.week) query.set("week", String(params.week));
  if (params?.slate) query.set("slate", params.slate);
  query.set("limit", String(params?.limit ?? 200));
  return getJson(`/digital-twin/impact-previews?${query.toString()}`);
}

export function createDigitalTwinImpactPreview(
  beliefId: string,
  payload: {
    target_player_id?: string | null;
    season: number;
    week: number;
    slate?: string | null;
    contest_format?: "classic" | "showdown" | null;
    objective?: "cash" | "gpp" | null;
  },
): Promise<BeliefImpactPreview> {
  return postJson(`/digital-twin/beliefs/${encodeURIComponent(beliefId)}/impact-previews`, payload);
}

export function decideDigitalTwinImpactPreview(
  previewId: string,
  decision: "approved" | "rejected",
  noteText?: string,
): Promise<BeliefImpactPreview> {
  return postJson(`/digital-twin/impact-previews/${encodeURIComponent(previewId)}/decision`, {
    decision,
    note_text: noteText || null,
  });
}

export function fetchDigitalTwinVariantSets(params?: {
  season?: number;
  week?: number;
  slate?: string;
  limit?: number;
}): Promise<DigitalTwinVariantSetListResponse> {
  const query = new URLSearchParams();
  if (params?.season) query.set("season", String(params.season));
  if (params?.week) query.set("week", String(params.week));
  if (params?.slate) query.set("slate", params.slate);
  query.set("limit", String(params?.limit ?? 20));
  return getJson(`/digital-twin/variant-sets?${query.toString()}`);
}

export function createDigitalTwinVariantSet(payload: {
  season: number;
  week: number;
  slate: string;
  contest_format?: "classic" | "showdown" | null;
  objective?: "cash" | "gpp" | null;
  projection_run_id?: string | null;
}): Promise<DigitalTwinVariantSet> {
  return postJson("/digital-twin/variant-sets", payload);
}

export function replayDigitalTwinVariantSet(variantSetId: string): Promise<DigitalTwinVariantReplay> {
  return postJson(`/digital-twin/variant-sets/${encodeURIComponent(variantSetId)}/replay`, {});
}
