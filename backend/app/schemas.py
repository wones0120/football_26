from __future__ import annotations

from datetime import datetime
from typing import Any
from typing import Literal

from pydantic import BaseModel, Field


SourceSystem = Literal["draftkings", "fanduel", "nflreadpy"]


class HealthResponse(BaseModel):
    status: str
    app_env: str
    timestamp: datetime


class ModelDefaultsResponse(BaseModel):
    showdown_captain_model_path: str
    showdown_captain_prior_strength: float
    classic_value_driver_model_path: str
    classic_value_driver_prior_strength: float
    matchup_outcome_model_path: str
    matchup_outcome_prior_strength: float
    matchup_prior_gate_model_path: str


class BenchmarkArtifactResponse(BaseModel):
    name: str
    path: str
    exists: bool
    download_url: str | None = None


class BootstrapMetricIntervalResponse(BaseModel):
    estimate: float
    lower: float
    upper: float
    standard_error: float
    sample_size: int
    confidence_level: float
    bootstrap_samples: int
    method: str


class BenchmarkMetricsResponse(BaseModel):
    classic_mean_gap_points: float | None = None
    classic_median_gap_points: float | None = None
    classic_slates_completed: int | None = None
    showdown_mean_gap_points: float | None = None
    showdown_median_gap_points: float | None = None
    showdown_slates_completed: int | None = None
    captain_informed_win_rate: float | None = None
    captain_mean_gap_lift_points: float | None = None
    captain_paired_slates: int | None = None
    classic_mean_gap_interval: BootstrapMetricIntervalResponse | None = None
    classic_median_gap_interval: BootstrapMetricIntervalResponse | None = None
    showdown_mean_gap_interval: BootstrapMetricIntervalResponse | None = None
    showdown_median_gap_interval: BootstrapMetricIntervalResponse | None = None
    captain_win_rate_interval: BootstrapMetricIntervalResponse | None = None
    captain_mean_gap_lift_interval: BootstrapMetricIntervalResponse | None = None


class BenchmarkRunResponse(BaseModel):
    run_directory: str
    status: str
    suite_started_at: str | None = None
    suite_finished_at: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[BenchmarkArtifactResponse] = Field(default_factory=list)
    metrics: BenchmarkMetricsResponse = Field(default_factory=BenchmarkMetricsResponse)


class BenchmarkRunListResponse(BaseModel):
    rows: list[BenchmarkRunResponse]


class BenchmarkSuiteRunRequest(BaseModel):
    source_system: Literal["draftkings", "fanduel"] = "draftkings"
    season_start: int = Field(default=2024, ge=2000)
    season_end: int = Field(default=2025, ge=2000)
    lineups_per_slate_classic: int = Field(default=1000, ge=100, le=20000)
    lineups_per_slate_showdown: int = Field(default=1000, ge=100, le=20000)
    lineups_per_slate_showdown_ab: int = Field(default=2500, ge=100, le=20000)
    training_window_slates: int = Field(default=24, ge=2, le=120)
    min_training_slates: int = Field(default=4, ge=1, le=80)
    min_training_rows: int = Field(default=2000, ge=100, le=2000000)
    ab_min_training_slates: int = Field(default=2, ge=1, le=80)
    ab_min_training_rows: int = Field(default=500, ge=100, le=2000000)
    learned_only: bool = True
    random_seed: int = 42
    bootstrap_samples: int = Field(default=2000, ge=100, le=100000)
    confidence_level: float = Field(default=0.95, gt=0.0, lt=1.0)
    limit_slates: int = Field(default=0, ge=0, le=2000)
    analysis_limit_slates: int = Field(default=0, ge=0, le=2000)
    quiet_progress: bool = True
    showdown_captain_model_path: str | None = None
    showdown_captain_prior_strength: float | None = Field(default=None, ge=0.0, le=1.0)


class BenchmarkSuiteRunResponse(BaseModel):
    status: str
    error_message: str | None = None
    stdout: str = ""
    stderr: str = ""
    run: BenchmarkRunResponse | None = None


class SalaryIngestRequest(BaseModel):
    source_system: Literal["draftkings", "fanduel"]
    season: int = Field(..., ge=2000)
    week: int = Field(..., ge=1, le=25)
    slate: str = Field(..., min_length=1)
    path: str = Field(..., min_length=1)


class InjuryIngestRequest(BaseModel):
    source_system: Literal["draftkings", "fanduel"]
    season: int = Field(..., ge=2000)
    week: int = Field(..., ge=1, le=25)
    slate: str = Field(..., min_length=1)
    path: str = Field(..., min_length=1)


class NflReadPyBootstrapRequest(BaseModel):
    season: int = Field(..., ge=2000)
    weeks: list[int] | None = None


class NflReadPySeasonRequest(BaseModel):
    season: int = Field(..., ge=2000)
    weeks: list[int] | None = None


class AutoDiscoverIngestRequest(BaseModel):
    source_system: Literal["draftkings", "fanduel"] = "draftkings"
    directory: str = Field(default="~/Downloads", min_length=1)


class SimulateWeekRequest(BaseModel):
    source_system: Literal["draftkings", "fanduel"] = "draftkings"
    season: int = Field(..., ge=2000)
    week: int = Field(..., ge=1, le=25)
    slate: str = Field(default="main", min_length=1)
    iterations: int = Field(default=5000, ge=500, le=50000)
    top_n: int = Field(default=40, ge=5, le=300)
    min_history_games: int = Field(default=4, ge=1, le=30)
    prior_weight: float = Field(default=12.0, ge=0.0, le=100.0)
    noise_scale: float = Field(default=0.12, ge=0.0, le=1.0)
    random_seed: int | None = None


class BacktestWeekRequest(BaseModel):
    source_system: Literal["draftkings", "fanduel"] = "draftkings"
    season: int = Field(..., ge=2000)
    week: int = Field(..., ge=1, le=25)
    slate: str = Field(default="main", min_length=1)
    iterations: int = Field(default=5000, ge=500, le=50000)
    min_history_games: int = Field(default=4, ge=1, le=30)
    prior_weight: float = Field(default=12.0, ge=0.0, le=100.0)
    noise_scale: float = Field(default=0.12, ge=0.0, le=1.0)
    random_seed: int | None = None
    evaluation_top_n: int = Field(default=25, ge=5, le=300)
    low_salary_threshold: int = Field(default=4500, ge=500, le=20000)
    low_salary_hit_points: float = Field(default=15.0, ge=1.0, le=80.0)


class BacktestRangeABRequest(BaseModel):
    source_system: Literal["draftkings", "fanduel"] = "draftkings"
    season_start: int = Field(default=2024, ge=2000)
    season_end: int = Field(default=2025, ge=2000)
    slate: str | None = None
    iterations: int = Field(default=3000, ge=500, le=50000)
    min_history_games: int = Field(default=4, ge=1, le=30)
    prior_weight: float = Field(default=12.0, ge=0.0, le=100.0)
    noise_scale: float = Field(default=0.12, ge=0.0, le=1.0)
    random_seed: int | None = None
    evaluation_top_n: int = Field(default=25, ge=5, le=300)
    low_salary_threshold: int = Field(default=4500, ge=500, le=20000)
    low_salary_hit_points: float = Field(default=15.0, ge=1.0, le=80.0)
    persist_calibration: bool = True
    reset_existing_calibration: bool = False


class IngestResultResponse(BaseModel):
    ingest_run_id: str
    source_system: str
    source_table: str
    season: int | None = None
    week: int | None = None
    slate: str | None = None
    status: str
    rows_raw: int
    rows_curated: int
    rows_unresolved: int
    error_message: str | None = None
    started_at: datetime
    completed_at: datetime | None = None


class IngestRunListResponse(BaseModel):
    rows: list[IngestResultResponse]


class SeasonCoverageRowResponse(BaseModel):
    dataset: str
    season: int | None
    rows: int


class SeasonCoverageResponse(BaseModel):
    rows: list[SeasonCoverageRowResponse]


class CuratedSalarySliceRowResponse(BaseModel):
    source_system: str
    season: int
    week: int
    slate: str
    rows: int


class CuratedSalarySliceResponse(BaseModel):
    rows: list[CuratedSalarySliceRowResponse]


class DataFreshnessRowResponse(BaseModel):
    dataset: Literal["salaries", "injuries", "schedules", "weekly_stats"]
    source_system: str
    season: int
    week: int
    slate: str | None = None
    rows: int
    latest_loaded_at: datetime | None = None
    age_hours: float | None = None
    stale_after_hours: int
    status: Literal["fresh", "stale", "missing"]


class DataFreshnessResponse(BaseModel):
    checked_at: datetime
    source_system: Literal["draftkings", "fanduel"]
    season: int
    week: int
    slate: str
    rows: list[DataFreshnessRowResponse]


class AutoDiscoveredFileResponse(BaseModel):
    file_name: str
    path: str
    season: int
    week: int
    slate: str
    status: str
    rows_curated: int
    rows_unresolved: int
    error_message: str | None = None


class AutoDiscoverIngestResponse(BaseModel):
    source_system: str
    source_table: str
    directory: str
    files_attempted: int
    files_completed: int
    files_failed: int
    rows_curated: int
    rows_unresolved: int
    rows: list[AutoDiscoveredFileResponse]


class SimulatedPlayerOutcomeResponse(BaseModel):
    player_master_id: str | None
    source_player_key: str | None
    player_name: str
    team: str | None
    position: str | None
    salary: int | None
    history_games: int
    mean_points: float
    median_points: float
    p75_points: float
    p90_points: float
    p95_points: float
    ceiling_prob_20: float
    ceiling_prob_25: float


class SimulateWeekResponse(BaseModel):
    simulation_run_id: str
    source_system: str
    season: int
    week: int
    slate: str
    iterations: int
    players_considered: int
    players_simulated: int
    status: str
    error_message: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    top_rows: list[SimulatedPlayerOutcomeResponse]


class BacktestPlayerRowResponse(BaseModel):
    player_master_id: str | None
    source_player_key: str | None
    player_name: str
    team: str | None
    position: str | None
    salary: int | None
    history_games: int
    predicted_mean_points: float
    predicted_p90_points: float
    predicted_low_hit_prob: float | None = None
    actual_points: float
    error: float
    abs_error: float
    salary_value_actual: float | None


class PositionLearningRowResponse(BaseModel):
    position: str
    players: int
    mean_prediction: float
    mean_actual: float
    mean_error: float
    adjustment_multiplier: float


class SalaryBucketLearningRowResponse(BaseModel):
    bucket: str
    players: int
    mean_prediction: float
    mean_actual: float
    mean_error: float


class BacktestWeekResponse(BaseModel):
    source_system: str
    season: int
    week: int
    slate: str
    iterations: int
    players_considered: int
    players_simulated: int
    players_with_actuals: int
    mae: float
    rmse: float
    mean_error: float
    correlation: float | None
    evaluation_top_n: int
    top_n_hits: int
    low_salary_threshold: int
    low_salary_candidates: int
    low_salary_hits: int
    low_salary_hit_rate: float
    learning_notes: list[str]
    position_learning: list[PositionLearningRowResponse]
    salary_bucket_learning: list[SalaryBucketLearningRowResponse]
    rows: list[BacktestPlayerRowResponse]


class BacktestWeekABResponse(BaseModel):
    source_system: str
    season: int
    week: int
    slate: str
    baseline: BacktestWeekResponse
    calibrated: BacktestWeekResponse
    mae_lift_pct: float
    rmse_lift_pct: float
    top_n_hit_rate_baseline: float
    top_n_hit_rate_calibrated: float
    top_n_hit_rate_lift_pct: float
    low_salary_hit_rate_baseline: float
    low_salary_hit_rate_calibrated: float
    low_salary_hit_rate_lift_pct: float


class BacktestRangeSliceABRowResponse(BaseModel):
    season: int
    week: int
    slate: str
    players_with_actuals: int = 0
    baseline_mae: float | None = None
    calibrated_mae: float | None = None
    baseline_rmse: float | None = None
    calibrated_rmse: float | None = None
    baseline_top_n_hit_rate: float | None = None
    calibrated_top_n_hit_rate: float | None = None
    baseline_low_salary_hit_rate: float | None = None
    calibrated_low_salary_hit_rate: float | None = None
    mae_lift_pct: float | None = None
    rmse_lift_pct: float | None = None
    top_n_hit_rate_lift_pct: float | None = None
    low_salary_hit_rate_lift_pct: float | None = None
    error_message: str | None = None


class BacktestRangeABResponse(BaseModel):
    source_system: str
    season_start: int
    season_end: int
    slate: str | None
    total_slates: int
    slates_evaluated: int
    slates_failed: int
    players_with_actuals_total: int
    baseline_mae: float | None
    calibrated_mae: float | None
    mae_lift_pct: float | None
    baseline_rmse: float | None
    calibrated_rmse: float | None
    rmse_lift_pct: float | None
    baseline_top_n_hit_rate: float | None
    calibrated_top_n_hit_rate: float | None
    top_n_hit_rate_lift_pct: float | None
    baseline_low_salary_hit_rate: float | None
    calibrated_low_salary_hit_rate: float | None
    low_salary_hit_rate_lift_pct: float | None
    rows: list[BacktestRangeSliceABRowResponse]


class LineupLearningRequest(BaseModel):
    source_system: Literal["draftkings", "fanduel"] = "draftkings"
    season_start: int = Field(default=2024, ge=2000)
    season_end: int = Field(default=2025, ge=2000)
    slate: str | None = None
    lineups_per_slate: int = Field(default=6000, ge=1000, le=200000)
    selection_size: int = Field(default=150, ge=10, le=5000)
    min_training_slates: int = Field(default=6, ge=2, le=50)
    min_training_rows: int = Field(default=15000, ge=1000, le=2000000)
    training_window_slates: int = Field(default=24, ge=4, le=100)
    random_seed: int | None = None


class LineupLearningFeatureInsightRowResponse(BaseModel):
    feature_name: str
    weight: float
    direction: Literal["positive", "negative"]


class LineupLearningSlateResultRowResponse(BaseModel):
    season: int
    week: int
    slate: str
    generated_lineups: int
    selected_lineups: int
    mean_selected_points: float | None
    mean_random_points: float | None
    selected_top1pct_rate: float | None
    random_top1pct_rate: float | None
    uplift_points: float | None
    uplift_top1pct_rate: float | None
    error_message: str | None = None


class LineupLearningResponse(BaseModel):
    source_system: str
    season_start: int
    season_end: int
    slate: str | None
    lineups_per_slate: int
    slates_total: int
    slates_evaluated: int
    slates_warmup_or_failed: int
    mean_selected_points: float | None
    mean_random_points: float | None
    points_uplift: float | None
    mean_selected_top1pct_rate: float | None
    mean_random_top1pct_rate: float | None
    top1pct_rate_uplift: float | None
    discovered_patterns: list[str]
    feature_insights: list[LineupLearningFeatureInsightRowResponse]
    rows: list[LineupLearningSlateResultRowResponse]


class OptimalVsPredictedBacktestRequest(BaseModel):
    source_system: Literal["draftkings", "fanduel"] = "draftkings"
    season_start: int = Field(default=2024, ge=2000)
    season_end: int = Field(default=2025, ge=2000)
    slate: str | None = None
    slate_type: Literal["classic", "showdown"] = "classic"
    lineups_per_slate: int = Field(default=600, ge=100, le=20000)
    training_window_slates: int = Field(default=24, ge=2, le=120)
    min_training_slates: int = Field(default=2, ge=1, le=80)
    min_training_rows: int = Field(default=500, ge=100, le=2000000)
    classic_top_target_percentile: float = Field(default=98.0, ge=80.0, le=99.5)
    learned_only: bool = True
    random_seed: int | None = None
    limit_slates: int = Field(default=0, ge=0, le=2000)
    showdown_captain_model_path: str | None = None
    showdown_captain_prior_strength: float = Field(default=0.0, ge=0.0, le=1.0)
    classic_value_driver_model_path: str | None = None
    classic_value_driver_prior_strength: float = Field(default=0.0, ge=0.0, le=1.0)
    matchup_outcome_model_path: str | None = None
    matchup_outcome_prior_strength: float = Field(default=0.0, ge=0.0, le=1.0)
    matchup_prior_gate_model_path: str | None = None


class OptimalVsPredictedBacktestRowResponse(BaseModel):
    season: int
    week: int
    slate: str
    slate_type: Literal["classic", "showdown"]
    status: str
    optimal_actual_points: float | None = None
    predicted_actual_points: float | None = None
    gap_points: float | None = None
    optimal_salary_used: int | None = None
    predicted_salary_used: int | None = None
    predicted_projected_mean_points: float | None = None
    predicted_projected_p90_points: float | None = None
    predicted_policy_score: float | None = None
    error_message: str | None = None


class OptimalVsPredictedBacktestResponse(BaseModel):
    source_system: str
    season_start: int
    season_end: int
    slate_filter: str | None
    slate_type: Literal["classic", "showdown"]
    lineups_per_slate: int
    training_window_slates: int
    min_training_slates: int
    min_training_rows: int
    classic_top_target_percentile: float
    learned_only: bool
    showdown_captain_model_path: str | None = None
    showdown_captain_prior_strength: float = 0.0
    classic_value_driver_model_path: str | None = None
    classic_value_driver_prior_strength: float = 0.0
    matchup_outcome_model_path: str | None = None
    matchup_outcome_prior_strength: float = 0.0
    matchup_prior_gate_model_path: str | None = None
    slates_total: int
    slates_completed: int
    slates_failed_or_skipped: int
    mean_gap_points: float | None
    median_gap_points: float | None
    best_case_gap_points: float | None
    worst_case_gap_points: float | None
    rows: list[OptimalVsPredictedBacktestRowResponse]


class ActualTopLineupBuildRequest(BaseModel):
    source_system: Literal["draftkings", "fanduel"] = "draftkings"
    season_start: int = Field(default=2024, ge=2000)
    season_end: int = Field(default=2025, ge=2000)
    slate: str | None = None
    top_k: int = Field(default=100, ge=1, le=500)
    overwrite_existing: bool = False
    limit_slates: int = Field(default=0, ge=0, le=2000)


class ActualTopLineupPlayerResponse(BaseModel):
    slot_index: int
    roster_slot: str | None
    position: str
    player_name: str
    team: str | None
    salary: int
    actual_points: float


class ActualTopLineupRowResponse(BaseModel):
    source_system: str
    season: int
    week: int
    slate: str
    lineup_rank: int
    salary_used: int
    actual_points: float
    players: list[ActualTopLineupPlayerResponse]


class ActualTopLineupBuildSliceResponse(BaseModel):
    source_system: str
    season: int
    week: int
    slate: str
    status: str
    rows_written: int
    error_message: str | None = None


class ActualTopLineupBuildResponse(BaseModel):
    source_system: str
    season_start: int
    season_end: int
    slate: str | None
    top_k: int
    slates_total: int
    slates_completed: int
    slates_failed: int
    rows_written: int
    rows: list[ActualTopLineupBuildSliceResponse]


class ActualTopLineupLearningRequest(BaseModel):
    source_system: Literal["draftkings", "fanduel"] = "draftkings"
    season_start: int = Field(default=2024, ge=2000)
    season_end: int = Field(default=2025, ge=2000)
    slate: str | None = None
    top_k_label: int = Field(default=100, ge=1, le=500)
    candidate_lineups_per_slate: int = Field(default=3000, ge=500, le=50000)
    training_window_slates: int = Field(default=24, ge=4, le=120)
    min_training_slates: int = Field(default=4, ge=2, le=80)
    min_training_rows: int = Field(default=2000, ge=500, le=2000000)
    selection_size: int = Field(default=100, ge=10, le=1000)
    random_seed: int | None = None


class ActualTopLineupLearningSlateRowResponse(BaseModel):
    season: int
    week: int
    slate: str
    generated_lineups: int
    positives_in_pool: int
    selected_lineups: int
    selected_mean_actual_points: float | None
    random_mean_actual_points: float | None
    uplift_points: float | None
    error_message: str | None = None


class ActualTopLineupLearningResponse(BaseModel):
    source_system: str
    season_start: int
    season_end: int
    slate: str | None
    top_k_label: int
    candidate_lineups_per_slate: int
    slates_total: int
    slates_evaluated: int
    slates_warmup_or_failed: int
    mean_selected_points: float | None
    mean_random_points: float | None
    points_uplift: float | None
    discovered_patterns: list[str]
    feature_insights: list[LineupLearningFeatureInsightRowResponse]
    rows: list[ActualTopLineupLearningSlateRowResponse]


class UltimateLineupRequest(BaseModel):
    source_system: Literal["draftkings", "fanduel"] = "draftkings"
    season: int = Field(..., ge=2000)
    week: int = Field(..., ge=1, le=25)
    slate: str = Field(default="sunday_main", min_length=1)
    candidate_lineups: int = Field(default=100000, ge=1000, le=500000)
    output_lineups: int = Field(default=150, ge=10, le=1000)
    min_salary_floor: int = Field(default=43000, ge=30000, le=50000)
    training_start_season: int = Field(default=2024, ge=2000)
    training_window_slates: int = Field(default=24, ge=4, le=120)
    training_lineups_per_slate: int = Field(default=1500, ge=500, le=10000)
    min_training_slates: int = Field(default=4, ge=2, le=80)
    min_training_rows: int = Field(default=2000, ge=1000, le=2000000)
    learned_only: bool = True
    max_player_exposure: float = Field(default=0.35, ge=0.05, le=1.0)
    max_qb_exposure: float = Field(default=0.25, ge=0.05, le=1.0)
    max_dst_exposure: float = Field(default=0.30, ge=0.05, le=1.0)
    classic_value_driver_model_path: str | None = None
    classic_value_driver_prior_strength: float = Field(default=0.0, ge=0.0, le=1.0)
    matchup_outcome_model_path: str | None = None
    matchup_outcome_prior_strength: float = Field(default=0.0, ge=0.0, le=1.0)
    matchup_prior_gate_model_path: str | None = None
    random_seed: int | None = None


class UltimateLineupPlayerRowResponse(BaseModel):
    player_name: str
    team: str | None
    position: str
    salary: int
    projected_mean_points: float
    projected_p90_points: float


class UltimateLineupRowResponse(BaseModel):
    rank: int
    salary_used: int
    salary_left: int
    projected_mean_points: float
    projected_p90_points: float
    policy_score: float
    composite_score: float
    players: list[UltimateLineupPlayerRowResponse]


class UltimateLineupExposureRowResponse(BaseModel):
    player_name: str
    team: str | None
    position: str
    salary: int
    exposure_count: int
    exposure_rate: float


class UltimateLineupResponse(BaseModel):
    source_system: str
    season: int
    week: int
    slate: str
    candidate_lineups_requested: int
    generated_candidate_lineups: int
    output_lineups: int
    training_slates_used: int
    training_rows_used: int
    training_positive_rate: float
    classic_value_driver_model_path: str | None = None
    classic_value_driver_prior_strength: float = 0.0
    matchup_outcome_model_path: str | None = None
    matchup_outcome_prior_strength: float = 0.0
    matchup_prior_gate_model_path: str | None = None
    discovered_patterns: list[str]
    rows: list[UltimateLineupRowResponse]
    exposures: list[UltimateLineupExposureRowResponse]


class UnresolvedRowResponse(BaseModel):
    unresolved_id: str
    ingest_run_id: str
    source_system: str
    source_table: str
    source_player_key: str | None
    season: int | None
    week: int | None
    slate: str | None
    normalized_name: str
    team: str | None
    position: str | None
    resolution_status: str
    resolved_player_master_id: str | None
    raw_row_json: dict
    created_at: datetime


class UnresolvedListResponse(BaseModel):
    rows: list[UnresolvedRowResponse]


class UnresolvedTriageRowResponse(BaseModel):
    source_system: str
    source_table: str
    season: int | None
    week: int | None
    slate: str | None
    open_count: int
    new_count: int
    oldest_created_at: datetime
    newest_created_at: datetime


class UnresolvedTriageResponse(BaseModel):
    generated_at: datetime
    lookback_hours: int
    open_total: int
    new_total: int
    groups_returned: int
    rows: list[UnresolvedTriageRowResponse]


class ResolveUnresolvedRequest(BaseModel):
    player_master_id: str = Field(..., min_length=1)
    resolved_by: str = Field(default="ui")
    notes: str | None = None
    create_alias: bool = True


class PlayerMasterUpsertRequest(BaseModel):
    player_master_id: str | None = None
    full_name: str = Field(..., min_length=1)
    team: str | None = None
    position: str | None = None


class PlayerMasterResponse(BaseModel):
    player_master_id: str
    full_name: str
    normalized_name: str
    primary_team: str | None
    position: str | None
    created_at: datetime
    updated_at: datetime
