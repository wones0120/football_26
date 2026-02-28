export type IngestResult = {
  ingest_run_id: string;
  source_system: string;
  source_table: string;
  status: string;
  rows_raw: number;
  rows_curated: number;
  rows_unresolved: number;
  error_message?: string | null;
  started_at: string;
  completed_at?: string | null;
};

export type UnresolvedRow = {
  unresolved_id: string;
  ingest_run_id: string;
  source_system: string;
  source_table: string;
  source_player_key?: string | null;
  season?: number | null;
  week?: number | null;
  slate?: string | null;
  normalized_name: string;
  team?: string | null;
  position?: string | null;
  resolution_status: string;
  resolved_player_master_id?: string | null;
  raw_row_json: Record<string, unknown>;
  created_at: string;
};

export type PlayerMaster = {
  player_master_id: string;
  full_name: string;
  normalized_name: string;
  primary_team?: string | null;
  position?: string | null;
  created_at: string;
  updated_at: string;
};

export type SeasonCoverageRow = {
  dataset: string;
  season?: number | null;
  rows: number;
};

export type CuratedSalarySliceRow = {
  source_system: string;
  season: number;
  week: number;
  slate: string;
  rows: number;
};

export type SimulatedPlayerOutcome = {
  player_master_id?: string | null;
  source_player_key?: string | null;
  player_name: string;
  team?: string | null;
  position?: string | null;
  salary?: number | null;
  history_games: number;
  mean_points: number;
  median_points: number;
  p75_points: number;
  p90_points: number;
  p95_points: number;
  ceiling_prob_20: number;
  ceiling_prob_25: number;
};

export type SimulateWeekResult = {
  simulation_run_id: string;
  source_system: string;
  season: number;
  week: number;
  slate: string;
  iterations: number;
  players_considered: number;
  players_simulated: number;
  status: string;
  error_message?: string | null;
  started_at: string;
  completed_at?: string | null;
  top_rows: SimulatedPlayerOutcome[];
};

export type BacktestPlayerRow = {
  player_master_id?: string | null;
  source_player_key?: string | null;
  player_name: string;
  team?: string | null;
  position?: string | null;
  salary?: number | null;
  history_games: number;
  predicted_mean_points: number;
  predicted_p90_points: number;
  actual_points: number;
  error: number;
  abs_error: number;
  salary_value_actual?: number | null;
};

export type PositionLearningRow = {
  position: string;
  players: number;
  mean_prediction: number;
  mean_actual: number;
  mean_error: number;
  adjustment_multiplier: number;
};

export type SalaryBucketLearningRow = {
  bucket: string;
  players: number;
  mean_prediction: number;
  mean_actual: number;
  mean_error: number;
};

export type BacktestWeekResult = {
  source_system: string;
  season: number;
  week: number;
  slate: string;
  iterations: number;
  players_considered: number;
  players_simulated: number;
  players_with_actuals: number;
  mae: number;
  rmse: number;
  mean_error: number;
  correlation?: number | null;
  evaluation_top_n: number;
  top_n_hits: number;
  low_salary_threshold: number;
  low_salary_candidates: number;
  low_salary_hits: number;
  low_salary_hit_rate: number;
  learning_notes: string[];
  position_learning: PositionLearningRow[];
  salary_bucket_learning: SalaryBucketLearningRow[];
  rows: BacktestPlayerRow[];
};

export type OptimalVsPredictedBacktestRow = {
  season: number;
  week: number;
  slate: string;
  slate_type: "classic" | "showdown";
  status: string;
  optimal_actual_points?: number | null;
  predicted_actual_points?: number | null;
  gap_points?: number | null;
  optimal_salary_used?: number | null;
  predicted_salary_used?: number | null;
  predicted_projected_mean_points?: number | null;
  predicted_projected_p90_points?: number | null;
  predicted_policy_score?: number | null;
  error_message?: string | null;
};

export type OptimalVsPredictedBacktestResult = {
  source_system: "draftkings" | "fanduel";
  season_start: number;
  season_end: number;
  slate_filter?: string | null;
  slate_type: "classic" | "showdown";
  lineups_per_slate: number;
  training_window_slates: number;
  learned_only: boolean;
  slates_total: number;
  slates_completed: number;
  slates_failed_or_skipped: number;
  mean_gap_points?: number | null;
  median_gap_points?: number | null;
  best_case_gap_points?: number | null;
  worst_case_gap_points?: number | null;
  rows: OptimalVsPredictedBacktestRow[];
};

export type AutoDiscoveredFile = {
  file_name: string;
  path: string;
  season: number;
  week: number;
  slate: string;
  status: string;
  rows_curated: number;
  rows_unresolved: number;
  error_message?: string | null;
};

export type AutoDiscoverIngestResult = {
  source_system: string;
  source_table: string;
  directory: string;
  files_attempted: number;
  files_completed: number;
  files_failed: number;
  rows_curated: number;
  rows_unresolved: number;
  rows: AutoDiscoveredFile[];
};

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";

async function errorMessage(res: Response): Promise<string> {
  try {
    const payload = (await res.json()) as { detail?: unknown; message?: unknown };
    if (typeof payload.detail === "string" && payload.detail.trim().length > 0) {
      return payload.detail;
    }
    if (typeof payload.message === "string" && payload.message.trim().length > 0) {
      return payload.message;
    }
    return JSON.stringify(payload);
  } catch {
    const text = await res.text();
    return text || "request failed";
  }
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(await errorMessage(res));
  }
  return (await res.json()) as T;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(await errorMessage(res));
  }
  return (await res.json()) as T;
}

export function ingestSalaries(payload: {
  source_system: "draftkings" | "fanduel";
  season: number;
  week: number;
  slate: string;
  path: string;
}): Promise<IngestResult> {
  return postJson("/ingest/salaries", payload);
}

export function ingestInjuries(payload: {
  source_system: "draftkings" | "fanduel";
  season: number;
  week: number;
  slate: string;
  path: string;
}): Promise<IngestResult> {
  return postJson("/ingest/injuries", payload);
}

export function autoDiscoverSalaryFiles(payload: {
  source_system: "draftkings" | "fanduel";
  directory?: string;
}): Promise<AutoDiscoverIngestResult> {
  return postJson("/ingest/auto-discover/salaries", payload);
}

export function autoDiscoverInjuryFiles(payload: {
  source_system: "draftkings" | "fanduel";
  directory?: string;
}): Promise<AutoDiscoverIngestResult> {
  return postJson("/ingest/auto-discover/injuries", payload);
}

export function bootstrapNflreadpy(payload: {
  season: number;
  weeks?: number[];
}): Promise<IngestResult> {
  return postJson("/ingest/nflreadpy/bootstrap", payload);
}

export function ingestNflreadpySchedules(payload: {
  season: number;
  weeks?: number[];
}): Promise<IngestResult> {
  return postJson("/ingest/nflreadpy/schedules", payload);
}

export function ingestNflreadpyWeeklyStats(payload: {
  season: number;
  weeks?: number[];
}): Promise<IngestResult> {
  return postJson("/ingest/nflreadpy/weekly-stats", payload);
}

export function simulateWeek(payload: {
  source_system: "draftkings" | "fanduel";
  season: number;
  week: number;
  slate: string;
  iterations?: number;
  top_n?: number;
  min_history_games?: number;
  prior_weight?: number;
  noise_scale?: number;
  random_seed?: number;
}): Promise<SimulateWeekResult> {
  return postJson("/simulate/week", payload);
}

export function backtestWeek(payload: {
  source_system: "draftkings" | "fanduel";
  season: number;
  week: number;
  slate: string;
  iterations?: number;
  min_history_games?: number;
  prior_weight?: number;
  noise_scale?: number;
  random_seed?: number;
  evaluation_top_n?: number;
  low_salary_threshold?: number;
  low_salary_hit_points?: number;
}): Promise<BacktestWeekResult> {
  return postJson("/simulate/backtest-week", payload);
}

export function runOptimalVsPredictedBacktest(payload: {
  source_system: "draftkings" | "fanduel";
  season_start: number;
  season_end: number;
  slate?: string | null;
  slate_type: "classic" | "showdown";
  lineups_per_slate?: number;
  training_window_slates?: number;
  min_training_slates?: number;
  min_training_rows?: number;
  learned_only?: boolean;
  random_seed?: number;
  limit_slates?: number;
}): Promise<OptimalVsPredictedBacktestResult> {
  return postJson("/lineups/optimal-vs-predicted", payload);
}

export function fetchRuns(): Promise<{ rows: IngestResult[] }> {
  return getJson("/ingest/runs?limit=50");
}

export function fetchSeasonCoverage(): Promise<{ rows: SeasonCoverageRow[] }> {
  return getJson("/coverage/season");
}

export function fetchCuratedSalarySlices(params?: {
  season?: number;
  source_system?: "draftkings" | "fanduel";
  limit?: number;
}): Promise<{ rows: CuratedSalarySliceRow[] }> {
  const search = new URLSearchParams();
  if (params?.season != null) {
    search.set("season", String(params.season));
  }
  if (params?.source_system) {
    search.set("source_system", params.source_system);
  }
  search.set("limit", String(params?.limit ?? 2000));
  return getJson(`/coverage/curated-salary-slices?${search.toString()}`);
}

export function fetchUnresolved(): Promise<{ rows: UnresolvedRow[] }> {
  return getJson("/unresolved?status=open&limit=300");
}

export function upsertPlayerMaster(payload: {
  full_name: string;
  team?: string;
  position?: string;
}): Promise<PlayerMaster> {
  return postJson("/player-master/upsert", payload);
}

export function resolveUnresolved(
  unresolvedId: string,
  payload: {
    player_master_id: string;
    resolved_by: string;
    notes?: string;
    create_alias: boolean;
  }
): Promise<UnresolvedRow> {
  return postJson(`/unresolved/${encodeURIComponent(unresolvedId)}/resolve`, payload);
}
