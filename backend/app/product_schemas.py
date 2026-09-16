"""Pydantic schemas for FastAPI endpoints."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field


class BaseLoadRequest(BaseModel):
    season: int = Field(..., ge=2000)
    datasets: Optional[List[str]] = None


class SeasonLoadRequest(BaseLoadRequest):
    pass


class WeekLoadRequest(BaseLoadRequest):
    week: int = Field(..., ge=1, le=25)


class SlateRequest(BaseModel):
    season: int = Field(..., ge=2000)
    week: int = Field(..., ge=1, le=25)
    slate: str = Field(..., min_length=1)


class PregamePlayerContextInput(BaseModel):
    player_id: str = Field(..., min_length=1, max_length=64)
    team: Optional[str] = Field(default=None, max_length=16)
    position: Optional[str] = Field(default=None, max_length=16)
    availability_probability: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    start_probability: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    carry_share: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    target_share: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    expected_snaps: Optional[float] = Field(default=None, ge=0.0)
    expected_routes: Optional[float] = Field(default=None, ge=0.0)
    expected_carries: Optional[float] = Field(default=None, ge=0.0)
    expected_targets: Optional[float] = Field(default=None, ge=0.0)
    red_zone_share: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    goal_line_share: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    role_label: Optional[
        Literal[
            "STARTER",
            "BACKUP",
            "LEAD",
            "COMMITTEE",
            "PRIMARY",
            "SECONDARY",
            "ROTATION",
        ]
    ] = None
    injury_status: Optional[str] = Field(default=None, max_length=64)
    evidence: dict[str, Any] = Field(default_factory=dict)


class PregameContextRunRequest(BaseModel):
    season: int = Field(..., ge=2000)
    week: int = Field(..., ge=1, le=25)
    slate: str = Field(..., min_length=1, max_length=64)
    source: str = Field(..., min_length=1, max_length=128)
    source_uri: Optional[str] = None
    observed_at: datetime
    notes: Optional[str] = None
    players: List[PregamePlayerContextInput] = Field(..., min_length=1)


class PregameContextRunResponse(BaseModel):
    context_run_id: str
    season: int
    week: int
    slate: str
    source: str
    source_uri: Optional[str] = None
    observed_at: datetime
    received_at: datetime
    notes: Optional[str] = None
    content_hash: str
    status: str
    created_at: datetime
    players: List[dict[str, Any]] = Field(default_factory=list)


class PregameContextCurrentResponse(BaseModel):
    season: int
    week: int
    slate: str
    cutoff: datetime
    context_run_ids: List[str] = Field(default_factory=list)
    rows: List[dict[str, Any]] = Field(default_factory=list)
    player_pool: List[dict[str, Any]] = Field(default_factory=list)


class OptimizerRunRequest(BaseModel):
    season: int
    week: int
    slate: str
    strategy: str = Field(..., description="Optimizer strategy name")
    contest_format: Optional[Literal["classic", "showdown"]] = None
    objective: Optional[Literal["cash", "gpp"]] = None
    projection_run_id: Optional[str] = None
    rule_run_id: Optional[str] = None
    data_cutoff_at: Optional[datetime] = None
    params: dict = Field(default_factory=dict)


class ContestPreviewRequest(BaseModel):
    urls: List[str]
    manual_contest_metadata: List[dict[str, Any]] = Field(default_factory=list)


class OptimizerStatusResponse(BaseModel):
    job_id: str
    status: str
    strategy: str
    strategy_config: dict = Field(default_factory=dict)
    contest_format: str
    objective: str
    projection_run_id: Optional[str] = None
    rule_run_id: Optional[str] = None
    data_cutoff_at: Optional[datetime] = None
    lineage_persisted: bool = False
    message: Optional[str] = None
    results: Optional[list] = None
    player_pool: Optional[dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class JointResearchRequest(BaseModel):
    simulation_run_id: str = Field(..., min_length=1, max_length=128)
    optimizer_run_id: str | None = Field(default=None, min_length=1, max_length=128)
    num_simulations: int = Field(default=5000, ge=100, le=20000)
    seed: int = Field(default=603, ge=0, le=4294967295)
    threshold: float | None = Field(default=None, allow_inf_nan=False)
    allow_missing_cutoff: bool = False


class SimulationRunRequest(BaseModel):
    season: int = Field(..., ge=2000)
    week: int = Field(..., ge=1, le=25)
    slate: str = Field(..., min_length=1)
    contest_format: Literal["classic", "showdown"] = "classic"
    num_simulations: int = Field(default=1000, ge=1, le=20000)
    seed: int = 502
    salary_cap: int = Field(default=50000, ge=1)
    projection_run_id: Optional[str] = None
    ownership_run_id: Optional[str] = None


class SimulationPlayerResponse(BaseModel):
    player_id: str
    player_display_name: str
    position: str
    salary: int
    projection_mean: float
    optimal_lineup_count: int
    optimal_lineup_probability: float
    field_ownership: Optional[float] = None
    leverage_score: Optional[float] = None


class SimulationRunResponse(BaseModel):
    simulation_run_id: str
    simulation_model_id: str
    season: int
    week: int
    slate: str
    contest_format: str
    projection_run_id: str
    ownership_run_id: Optional[str] = None
    num_simulations: int
    successful_simulations: int
    seed: int
    status: str
    message: str
    data_cutoff_at: Optional[datetime] = None
    created_at: datetime
    rows: List[SimulationPlayerResponse]


class ClassicCashStackReplayRequest(BaseModel):
    season: int = Field(..., ge=2000)
    week: Optional[int] = Field(default=None, ge=1, le=25)
    slate: str = Field(default="SUNDAY_MAIN", min_length=1)
    projection_run_id: Optional[str] = None
    policy_ids: List[str] = Field(default_factory=list)


class ClassicCashStackReplayResponse(BaseModel):
    contract_id: str
    season: int
    requested_week: Optional[int] = None
    slate: str
    policy_ids: List[str]
    status: str
    weeks_requested: int
    weeks_completed: int
    steps: List[dict]
    failures: List[dict]
    aggregate: dict
    performance_claim_eligible: bool
    cash_performance_claim_eligible: bool = False
    evidence_status: str
    artifact_hash: str


class SlateReadinessCheckResponse(BaseModel):
    check_id: str
    category: str
    status: Literal["pass", "warn", "fail"]
    message: str
    value: Any = None
    threshold: Optional[str] = None
    applies_to: List[str]
    blocks: List[str]
    details: dict[str, Any] = Field(default_factory=dict)


class SlateReadinessGateResponse(BaseModel):
    status: Literal["pass", "warn", "fail"]
    score: int = Field(..., ge=0, le=100)
    summary: dict[str, int]
    blocking_checks: List[str]
    attention_checks: List[str]
    message: str


class SlateReadinessResponse(BaseModel):
    report_id: str
    contract_id: str
    season: int
    week: int
    slate: str
    generated_at: datetime
    status: Literal["pass", "warn", "fail"]
    score: int = Field(..., ge=0, le=100)
    summary: dict[str, int]
    gates: dict[str, SlateReadinessGateResponse]
    checks: List[SlateReadinessCheckResponse]


class DataQualityCheckResponse(BaseModel):
    quality_check_id: str
    quality_run_id: str
    check_id: str
    category: str
    status: Literal["pass", "warn", "fail"]
    severity: str
    table_name: Optional[str] = None
    check_name: str
    message: str
    value: Any = None
    threshold: Optional[str] = None
    affected_scope: dict[str, Any] = Field(default_factory=dict)
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class DataQualityRunResponse(BaseModel):
    quality_run_id: str
    report_id: Optional[str] = None
    contract_id: str
    trigger: str
    season: int
    week: Optional[int] = None
    slate: Optional[str] = None
    status: Literal["pass", "warn", "fail"]
    score: int = Field(..., ge=0, le=100)
    summary: dict[str, int]
    source_context: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    checks: List[DataQualityCheckResponse]


class DataQualityHistoryResponse(BaseModel):
    season: int
    week: Optional[int] = None
    slate: Optional[str] = None
    runs: List[DataQualityRunResponse]


BeliefScope = Literal["global", "contest_profile", "season", "weekly", "game", "player"]
BeliefDirection = Literal["boost", "fade", "prefer", "avoid", "monitor", "neutral"]


class BeliefCreateRequest(BaseModel):
    scope_type: BeliefScope
    subject_label: Optional[str] = None
    subject_id: Optional[str] = None
    season: Optional[int] = Field(default=None, ge=2000)
    week: Optional[int] = Field(default=None, ge=1, le=25)
    slate: Optional[str] = None
    contest_format: Optional[Literal["classic", "showdown"]] = None
    objective: Optional[Literal["cash", "gpp"]] = None
    direction: BeliefDirection = "neutral"
    strength: int = Field(default=3, ge=1, le=5)
    confidence: int = Field(default=50, ge=0, le=100)
    thought_text: str = Field(..., min_length=1, max_length=5000)
    evidence_text: Optional[str] = Field(default=None, max_length=5000)
    expires_at: Optional[datetime] = None
    is_retrospective: bool = False
    source: str = Field(default="manual", min_length=1, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BeliefRevisionRequest(BaseModel):
    subject_label: Optional[str] = None
    subject_id: Optional[str] = None
    season: Optional[int] = Field(default=None, ge=2000)
    week: Optional[int] = Field(default=None, ge=1, le=25)
    slate: Optional[str] = None
    contest_format: Optional[Literal["classic", "showdown"]] = None
    objective: Optional[Literal["cash", "gpp"]] = None
    direction: Optional[BeliefDirection] = None
    strength: Optional[int] = Field(default=None, ge=1, le=5)
    confidence: Optional[int] = Field(default=None, ge=0, le=100)
    thought_text: Optional[str] = Field(default=None, min_length=1, max_length=5000)
    evidence_text: Optional[str] = Field(default=None, max_length=5000)
    expires_at: Optional[datetime] = None
    is_retrospective: Optional[bool] = None
    source: Optional[str] = Field(default=None, min_length=1, max_length=100)
    metadata: Optional[dict[str, Any]] = None


class BeliefStatusRequest(BaseModel):
    status: Literal["active", "inactive"]


class BeliefResponse(BaseModel):
    belief_version_id: str
    belief_id: str
    belief_version: int
    supersedes_version_id: Optional[str] = None
    operation: Literal["created", "revised", "deactivated", "reactivated"]
    status: Literal["active", "inactive"]
    scope_type: BeliefScope
    subject_label: Optional[str] = None
    subject_id: Optional[str] = None
    season: Optional[int] = None
    week: Optional[int] = None
    slate: Optional[str] = None
    contest_format: Optional[str] = None
    objective: Optional[str] = None
    direction: BeliefDirection
    strength: int
    confidence: int
    thought_text: str
    evidence_text: Optional[str] = None
    expires_at: Optional[datetime] = None
    is_retrospective: bool
    is_expired: bool
    impact_status: str
    source: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class BeliefListSummary(BaseModel):
    total: int
    active: int
    inactive: int
    expired: int
    by_scope: dict[str, int] = Field(default_factory=dict)


class BeliefListResponse(BaseModel):
    rows: List[BeliefResponse]
    summary: BeliefListSummary


ThoughtCaptureContext = Literal["auto", "general", "slate", "player"]


class ThoughtCaptureRequest(BaseModel):
    context_type: ThoughtCaptureContext = "auto"
    raw_text: str = Field(..., min_length=1, max_length=20000)
    subject_label: Optional[str] = Field(default=None, max_length=160)
    subject_id: Optional[str] = None
    season: Optional[int] = Field(default=None, ge=2000)
    week: Optional[int] = Field(default=None, ge=1, le=25)
    slate: Optional[str] = None
    contest_format: Optional[Literal["classic", "showdown"]] = None
    objective: Optional[Literal["cash", "gpp"]] = None
    source: str = Field(default="thought_inbox", min_length=1, max_length=100)


class ThoughtCandidateDecisionRequest(BaseModel):
    decision: Literal["accepted", "rejected"]
    belief: Optional[BeliefCreateRequest] = None


class ThoughtCandidateResponse(BaseModel):
    candidate_id: str
    capture_id: str
    ordinal: int
    scope_type: BeliefScope
    subject_label: Optional[str] = None
    subject_id: Optional[str] = None
    season: Optional[int] = None
    week: Optional[int] = None
    slate: Optional[str] = None
    contest_format: Optional[str] = None
    objective: Optional[str] = None
    direction: BeliefDirection
    strength: int
    confidence: int
    thought_text: str
    extraction_reason: str
    status: Literal["pending", "accepted", "rejected"]
    decision_id: Optional[str] = None
    belief_id: Optional[str] = None
    belief_version_id: Optional[str] = None
    reviewed_payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    decided_at: Optional[datetime] = None


class ThoughtCaptureResponse(BaseModel):
    capture_id: str
    context_type: ThoughtCaptureContext
    raw_text: str
    subject_label: Optional[str] = None
    subject_id: Optional[str] = None
    season: Optional[int] = None
    week: Optional[int] = None
    slate: Optional[str] = None
    contest_format: Optional[str] = None
    objective: Optional[str] = None
    extraction_policy_id: str
    notices: List[str] = Field(default_factory=list)
    source: str
    created_at: datetime
    candidates: List[ThoughtCandidateResponse] = Field(default_factory=list)


class ThoughtCaptureListResponse(BaseModel):
    rows: List[ThoughtCaptureResponse]


class BeliefImpactPreviewRequest(BaseModel):
    target_player_id: Optional[str] = None
    season: int = Field(..., ge=2000)
    week: int = Field(..., ge=1, le=25)
    slate: Optional[str] = None
    contest_format: Optional[Literal["classic", "showdown"]] = None
    objective: Optional[Literal["cash", "gpp"]] = None


class BeliefImpactDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    note_text: Optional[str] = Field(default=None, max_length=5000)


class BeliefImpactPreviewResponse(BaseModel):
    preview_id: str
    belief_version_id: str
    belief_id: str
    policy_id: str
    season: int
    week: int
    slate: Optional[str] = None
    contest_format: Optional[str] = None
    objective: Optional[str] = None
    target_player_id: str
    target_label: str
    adjustment_pct: float
    baseline: dict[str, Any]
    proposed: dict[str, Any]
    delta: dict[str, Any]
    modifier: dict[str, Any]
    lineage: dict[str, Any]
    notices: List[str]
    status: Literal["pending", "approved", "rejected"]
    decision_id: Optional[str] = None
    note_text: Optional[str] = None
    approved_modifier: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    decided_at: Optional[datetime] = None


class BeliefImpactPreviewListResponse(BaseModel):
    rows: List[BeliefImpactPreviewResponse]


class DigitalTwinVariantSetCreateRequest(BaseModel):
    season: int = Field(..., ge=2000)
    week: int = Field(..., ge=1, le=25)
    slate: str = Field(..., min_length=1)
    contest_format: Optional[Literal["classic", "showdown"]] = None
    objective: Optional[Literal["cash", "gpp"]] = None
    projection_run_id: Optional[str] = None
    decision_cutoff_at: Optional[datetime] = None


class DigitalTwinVariantSetResponse(BaseModel):
    variant_set_id: str
    policy_id: str
    season: int
    week: int
    slate: str
    contest_format: Optional[str] = None
    objective: Optional[str] = None
    projection_run_id: str
    projection_data_cutoff_at: Optional[datetime] = None
    decision_cutoff_at: datetime
    status: Literal["completed"]
    created_at: datetime
    variant_ids: dict[str, str]
    artifact_hashes: dict[str, str]
    artifacts: dict[str, dict[str, Any]]
    comparison: dict[str, Any]


class DigitalTwinVariantSetListResponse(BaseModel):
    rows: List[DigitalTwinVariantSetResponse]


class DigitalTwinVariantReplayResponse(BaseModel):
    variant_set_id: str
    policy_id: str
    status: Literal["verified", "mismatch"]
    checks: dict[str, bool]
    stored_hashes: dict[str, str]
    recomputed_hashes: dict[str, str]
    comparison: dict[str, Any]


class LoadSummarySchema(BaseModel):
    dataset: str
    season: int
    week: Optional[int]
    rows_written: int


class LoadResponse(BaseModel):
    summaries: List[LoadSummarySchema]


class SlateLoadResponse(BaseModel):
    resource: str
    season: int
    week: int
    slate: str
    rows_written: int
    message: str
    completed_at: datetime


class PredictionRunRequest(BaseModel):
    season: int
    week: int
    positions: Optional[List[str]] = None
    slate: Optional[str] = None
    data_cutoff_at: Optional[datetime] = None


class PredictionRunResponse(BaseModel):
    season: int
    week: int
    rows_written: int
    message: str
    feature_run_id: Optional[str] = None
    model_run_id: Optional[str] = None
    projection_run_id: Optional[str] = None
    data_cutoff_at: Optional[datetime] = None
    target_persisted: bool = False
    calibration_metrics: dict[str, Any] = Field(default_factory=dict)


class ActivePredictionRunRequest(BaseModel):
    season: int = Field(..., ge=2000)
    week: int = Field(..., ge=1, le=25)
    slate: str = Field(..., min_length=1)
    projection_run_id: str = Field(..., min_length=1)
    approval_decision_id: str = Field(..., min_length=1)


class ActivePredictionRunResponse(BaseModel):
    projection_run_id: str
    model_run_id: str
    season: int
    week: int
    slate_id: str
    row_count: int
    data_cutoff_at: Optional[datetime] = None
    status: str
    created_at: datetime
    selection_reason: str
    active: bool


class ModelWeekBoundary(BaseModel):
    season: int = Field(..., ge=2000)
    week: int = Field(..., ge=1, le=25)


class ModelWeekWindow(BaseModel):
    start: ModelWeekBoundary
    end: ModelWeekBoundary


class ModelEvaluationDataWindow(BaseModel):
    training: ModelWeekWindow
    validation: ModelWeekWindow
    test: ModelWeekWindow


class ModelMetricGate(BaseModel):
    metric: str = Field(..., min_length=1)
    direction: Literal["minimize", "maximize"]
    champion_value: float
    challenger_value: float
    required_improvement: float = 0.0


class ModelChallengerEvaluationRequest(BaseModel):
    champion_projection_run_id: str = Field(..., min_length=1)
    challenger_projection_run_id: str = Field(..., min_length=1)
    data_window: ModelEvaluationDataWindow
    champion_code_hash: str = Field(
        ..., min_length=64, max_length=64, pattern=r"^[0-9a-fA-F]{64}$"
    )
    challenger_code_hash: str = Field(
        ..., min_length=64, max_length=64, pattern=r"^[0-9a-fA-F]{64}$"
    )
    gates: List[ModelMetricGate] = Field(..., min_length=1)
    evaluated_by: str = Field(..., min_length=1)
    evidence_uri: str = Field(..., min_length=1)
    notes: Optional[str] = None


class ModelChallengerEvaluationResponse(BaseModel):
    evaluation_id: str
    contract_id: str
    season: int
    week: int
    slate_id: str
    champion_projection_run_id: str
    challenger_projection_run_id: str
    data_window: dict[str, Any]
    champion_feature_set_hash: str
    challenger_feature_set_hash: str
    champion_code_hash: str
    challenger_code_hash: str
    gates: List[dict[str, Any]]
    gate_results: List[dict[str, Any]]
    status: Literal["passed", "blocked"]
    evaluation_hash: str
    evaluated_by: str
    evidence_uri: str
    notes: Optional[str] = None
    created_at: datetime


class ModelPromotionApprovalRequest(BaseModel):
    approved_by: str = Field(..., min_length=1)
    approval_reason: str = Field(..., min_length=1)


class ModelPromotionDecisionResponse(BaseModel):
    decision_id: str
    contract_id: str
    evaluation_id: str
    action: Literal["promotion", "rollback"]
    approved_by: str
    approval_reason: str
    previous_projection_run_id: str
    selected_projection_run_id: str
    rollback_of_decision_id: Optional[str] = None
    decision_hash: str
    selection_reason: str
    active: bool
    created_at: datetime


class OwnershipPayoutTier(BaseModel):
    min_rank: int = Field(..., ge=1)
    max_rank: int = Field(..., ge=1)
    payout: Optional[float] = Field(default=None, ge=0)
    prize_description: Optional[str] = None


class OwnershipLoadRequest(BaseModel):
    season: int = Field(..., ge=2000)
    week: int = Field(..., ge=1, le=25)
    slate: str = Field(..., min_length=1)
    path: str = Field(..., description="Path to ownership CSV/TSV file")
    contest_id: Optional[str] = None
    contest_name: Optional[str] = None
    contest_format: Optional[Literal["classic", "showdown"]] = None
    contest_type: Optional[Literal["cash", "gpp"]] = None
    entry_fee: Optional[float] = Field(default=None, ge=0)
    field_size: Optional[int] = Field(default=None, ge=1)
    max_entries_per_user: Optional[int] = Field(default=None, ge=1)
    prize_pool: Optional[float] = Field(default=None, ge=0)
    payout_tiers: List[OwnershipPayoutTier] = Field(default_factory=list)


class OwnershipRunRequest(BaseModel):
    season: int
    week: int
    slate: Optional[str] = None
    positions: Optional[List[str]] = None
    data_cutoff_at: Optional[datetime] = None


class OwnershipRunResponse(BaseModel):
    season: int
    week: int
    slate: Optional[str] = None
    rows_written: int
    message: str
    contest_id: Optional[str] = None
    source_file_id: Optional[str] = None
    target_persisted: bool = False
    ownership_run_id: Optional[str] = None
    data_cutoff_at: Optional[datetime] = None
    model_metrics: dict[str, Any] = Field(default_factory=dict)


class DraftKingsBatchImportRequest(BaseModel):
    directory: str
    season: int = Field(..., ge=2000)
    week: int = Field(..., ge=1, le=25)
    slate: str = Field(..., min_length=1)
    recursive: bool = False
    dry_run: bool = False


class DraftKingsBatchFileResponse(BaseModel):
    path: str
    file_type: str
    status: str
    season: int
    week: int
    slate: str
    rows_written: int
    source_file_id: Optional[str] = None
    contest_id: Optional[str] = None
    template_id: Optional[str] = None
    message: str


class DraftKingsBatchImportResponse(BaseModel):
    batch_id: str
    directory: str
    discovered: int
    imported: int
    deduplicated: int
    skipped: int
    failed: int
    dry_run: bool
    files: List[DraftKingsBatchFileResponse]


class PortfolioCreateRequest(BaseModel):
    portfolio_name: str = Field(..., min_length=1)
    optimizer_run_id: str = Field(..., min_length=1)
    template_id: str = Field(..., min_length=1)
    lineup_ids: Optional[List[str]] = None
    default_contest_id: Optional[str] = None


class PortfolioAssignmentResponse(BaseModel):
    assignment_id: str
    portfolio_id: str
    template_id: str
    template_row_number: int
    entry_id: str
    contest_id: str
    lineup_id: str
    portfolio_lineup_number: int


class PortfolioResponse(BaseModel):
    portfolio_id: str
    portfolio_name: str
    optimizer_run_id: str
    template_id: str
    season: int
    week: int
    slate: str
    contest_format: str
    objective: str
    status: str
    lineup_count: int
    assignment_count: int
    assignments: List[PortfolioAssignmentResponse]


class DraftKingsExportResponse(BaseModel):
    export_id: str
    portfolio_id: str
    contest_format: Literal["classic", "showdown"]
    file_name: str
    row_count: int
    content_sha256: str
    csv_content: str
    validation_id: str


class ExportValidationIssueResponse(BaseModel):
    code: str
    message: str
    lineup_number: Optional[int] = None
    player_id: Optional[str] = None


class ExportValidationResponse(BaseModel):
    validation_id: str
    portfolio_id: str
    status: Literal["passed", "failed"]
    checks_run: int
    errors: List[ExportValidationIssueResponse]
    warnings: List[ExportValidationIssueResponse]


class OwnershipProjectionRow(BaseModel):
    player_id: str
    player_master_id: Optional[str] = None
    player_display_name: str
    roster_position: Optional[str] = None
    projected_ownership: float
    actual_ownership: Optional[float] = None
    source: Optional[str] = None
    ownership_run_id: Optional[str] = None
    data_cutoff_at: Optional[datetime] = None
    salary: Optional[float] = None
    projection_mean: Optional[float] = None
    projection_p90: Optional[float] = None
    salary_percentile: Optional[float] = None
    projection_percentile: Optional[float] = None
    prior_player_ownership: Optional[float] = None
    contest_format: Optional[str] = None
    roster_slot: Optional[str] = None
    model_metrics_json: Optional[str] = None


class OwnershipProjectionListResponse(BaseModel):
    season: int
    week: int
    slate: Optional[str] = None
    rows: List[OwnershipProjectionRow]


class PastSlateAnalysisRequest(BaseModel):
    season: int
    week: int
    slate: str
    path: str
    top_n: int = 100


class PastSlatePlayerExposure(BaseModel):
    player_display_name: str
    roster_position: Optional[str] = None
    count: int
    pct: float


class PastSlateAnalysisResponse(BaseModel):
    season: int
    week: int
    slate: str
    lineups: int
    top_n: int
    exposures: List[PastSlatePlayerExposure]
    bucket_stats: List[dict]
    top_lineups: List[dict]
    message: str


class SlateLearningReportRequest(BaseModel):
    season: int = Field(..., ge=2000)
    week: int = Field(..., ge=1, le=25)
    slate: str = Field(..., min_length=1, max_length=64)
    entry_user: str = Field(..., min_length=1, max_length=128)


class SlateLearningReportResponse(BaseModel):
    report_id: str
    contract_id: str
    builder_version: str
    season: int
    week: int
    slate: str
    entry_user: str
    generated_at: datetime
    evidence_hash: str
    status: Literal["completed", "partial"]
    summary: dict[str, Any] = Field(default_factory=dict)
    portfolio_analysis: dict[str, Any] = Field(default_factory=dict)
    contests: List[dict[str, Any]] = Field(default_factory=list)
    entries: List[dict[str, Any]] = Field(default_factory=list)
    beliefs: List[dict[str, Any]] = Field(default_factory=list)
    agent_questions: List[dict[str, Any]] = Field(default_factory=list)
    learning_outcomes: dict[str, Any] = Field(default_factory=lambda: {
        "beliefs": {
            "total": 0, "theses_scored": 0, "supported": 0, "contradicted": 0,
            "helped": 0, "hurt": 0, "no_measurable_effect": 0, "unscored": 0,
            "by_scope": {}, "by_confidence_band": {},
        },
        "agent_answers": {
            "total": 0, "answered": 0, "helped": 0, "hurt": 0,
            "no_measurable_effect": 0, "unscored": 0,
        },
        "effect_tolerance_points": 0.25,
    })
    source_file_ids: List[str] = Field(default_factory=list)
    run_ids: dict[str, List[str]] = Field(default_factory=dict)
    missing_evidence: List[str] = Field(default_factory=list)
    interpretation: str


AgentQuestionAnswer = Literal[
    "support_model", "support_human", "lean_upside", "lean_downside", "no_change"
]


class AgentQuestionGenerateRequest(BaseModel):
    season: int = Field(..., ge=2000)
    week: int = Field(..., ge=1, le=25)
    slate: str = Field(..., min_length=1, max_length=64)
    variant_set_id: Optional[str] = None


class AgentQuestionAnswerRequest(BaseModel):
    answer: AgentQuestionAnswer
    answer_text: Optional[str] = Field(default=None, max_length=5000)


class AgentQuestionResponse(BaseModel):
    question_id: str
    policy_id: str
    variant_set_id: str
    season: int
    week: int
    slate: str
    trigger_type: Literal["model_human_disagreement", "high_value_uncertainty"]
    priority: int
    value_of_information_score: float
    subject_player_id: str
    subject_label: str
    question_text: str
    context: dict[str, Any] = Field(default_factory=dict)
    evidence_hash: str
    status: Literal["pending", "answered"]
    answer_id: Optional[str] = None
    answer: Optional[AgentQuestionAnswer] = None
    answer_text: Optional[str] = None
    resulting_modifier: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    answered_at: Optional[datetime] = None


class AgentQuestionListResponse(BaseModel):
    policy_id: str
    policy: dict[str, Any]
    rows: List[AgentQuestionResponse]
    summary: dict[str, int]

class BuildFeaturesRequest(BaseModel):
    season: int
    weeks: Optional[List[int]] = None
    future_week: Optional[int] = None


class BuildFeaturesResponse(BaseModel):
    season: int
    weeks: Optional[List[int]] = None
    rows_written: int
    message: str
    source_system: Optional[str] = None
    slates_total: Optional[int] = None
    slates_completed: Optional[int] = None
    slates_failed: Optional[int] = None
    rows: List[dict[str, Any]] = Field(default_factory=list)


class BuildFeatureMatrixRequest(BaseModel):
    season: int = Field(..., ge=2000)
    weeks: Optional[List[int]] = None
    slate: Optional[str] = None
    source_system: Literal["draftkings", "fanduel"] = "draftkings"


PipelineOperationStatus = Literal[
    "not_run",
    "queued",
    "running",
    "completed",
    "failed",
    "interrupted",
]


class PipelineOperationResult(BaseModel):
    status: PipelineOperationStatus
    status_at: Optional[datetime] = None
    job_id: Optional[str] = None
    run_id: Optional[str] = None
    scope: Literal["slate", "season"] = "slate"
    stage: Optional[str] = None
    progress_current: int = 0
    progress_total: int = 1
    progress_percent: float = 0.0
    message: Optional[str] = None
    error_message: Optional[str] = None
    rows_written: Optional[int] = None
    slice_outcome: Optional[dict[str, Any]] = None
    result: Optional[dict[str, Any]] = None


class PipelineOperationSummary(BaseModel):
    operation: Literal["features", "projections", "symbolic"]
    status: PipelineOperationStatus
    status_at: Optional[datetime] = None
    latest_attempt: Optional[PipelineOperationResult] = None
    last_success: Optional[PipelineOperationResult] = None


class ProjectionSelectionSummary(BaseModel):
    run_id: str
    status: PipelineOperationStatus
    status_at: Optional[datetime] = None
    rows_written: Optional[int] = None
    is_latest_success: bool = False


class ModelPipelineSummaryResponse(BaseModel):
    season: int
    week: int
    slate: str
    generated_at: datetime
    has_active_jobs: bool
    features: PipelineOperationSummary
    projections: PipelineOperationSummary
    symbolic: PipelineOperationSummary
    selected_projection: Optional[ProjectionSelectionSummary] = None


class ProcessUnmatchedRequest(BaseModel):
    season: Optional[int] = None
    week: Optional[int] = None
    source: Optional[str] = None


class ProcessUnmatchedResponse(BaseModel):
    added: int
    skipped_existing: int
    processed: int
    message: str


class PredictionRow(BaseModel):
    player_id: str
    player_display_name: str
    position: str
    recent_team: str
    opponent_team: str
    salary: Optional[int] = None
    season: int
    week: int
    predicted_mean: float
    predicted_p10: float
    predicted_p25: float
    predicted_p50: float
    predicted_p75: float
    predicted_p90: float
    model: str
    feature_run_id: Optional[str] = None
    model_run_id: Optional[str] = None
    projection_run_id: Optional[str] = None
    data_cutoff_at: Optional[datetime] = None
    game_id: Optional[str] = None
    calibration_method: str = ""
    calibration_position: str = ""
    calibration_role: str = ""
    calibration_sample_size: int = 0
    feature_inputs: dict[str, Any] = Field(default_factory=dict)
    last3_points: List[float] = []
    last3_avg: float = 0.0
    recent_median: float = 0.0
    recent_robust: float = 0.0
    delta_vs_last3: float = 0.0
    team_pos_avg: float = 0.0
    adj_mean: float = 0.0
    adj_mean_base: float = 0.0
    matchup_factor: float = 1.0
    adj_mean_final: float = 0.0


class PredictionListResponse(BaseModel):
    season: int
    week: int
    projection_run_id: Optional[str] = None
    rows: List[PredictionRow]


class WeeklyValidationRow(BaseModel):
    season: int
    week: int
    rows: int
    expected_rows: Optional[int] = None
    status: str  # ok | partial | missing


class ValidationResponse(BaseModel):
    table: str
    results: List[WeeklyValidationRow]


class StartingQBSelectionInput(BaseModel):
    player_master_id: str = Field(..., min_length=1, max_length=36)
    team: str = Field(..., min_length=2, max_length=16)
    source: str = Field(..., min_length=1, max_length=64)
    source_uri: Optional[str] = None
    observed_at: datetime


class StartingQBRequest(BaseModel):
    season: int
    week: int
    slate: str
    starters: Optional[List[StartingQBSelectionInput]] = None


class StartingQBResponse(BaseModel):
    season: int
    week: int
    slate: str
    rows_written: int
    message: str
    completed_at: datetime


class UnmatchedSalaryRow(BaseModel):
    season: int
    week: int
    slate: str
    name: str
    player_team: str
    created_at: datetime


class UnmatchedSalaryResponse(BaseModel):
    rows: List[UnmatchedSalaryRow]


class UnmatchedInjuryRow(BaseModel):
    season: int
    week: int
    slate: Optional[str]
    name: Optional[str]
    player_team: Optional[str]
    opponent: Optional[str]
    status: Optional[str]


class UnmatchedInjuryResponse(BaseModel):
    rows: List[UnmatchedInjuryRow]


class PostgresStartResponse(BaseModel):
    ok: bool
    message: str
    stdout: Optional[str] = None
    stderr: Optional[str] = None


class AgentRunRequest(BaseModel):
    season: int
    week: int
    slate: Optional[str] = None
    projection_run_id: Optional[str] = None


class NewsMonitorRunRequest(BaseModel):
    run_date: Optional[date] = None
    force: bool = False
    source_ids: Optional[List[str]] = None


class ManualNewsNoteRequest(BaseModel):
    run_date: Optional[date] = None
    title: str = Field(..., min_length=1)
    note_text: str = Field(..., min_length=1)
    source_link: Optional[str] = None


class ManualNewsNoteResponse(BaseModel):
    note_id: str
    run_date: date
    title: str
    source_link: Optional[str] = None
    created_at: datetime
    message: str


class NewsMonitorFeedbackUpsertRequest(BaseModel):
    run_date: date
    signal_key: str = Field(..., min_length=1)
    signal_type: str
    signal_text: str
    player_name: Optional[str] = None
    team: Optional[str] = None
    source_link: Optional[str] = None
    feedback_choice: Optional[str] = None
    note_text: str = ""


class NewsMonitorFeedbackResponse(BaseModel):
    feedback_id: str
    run_date: date
    signal_key: str
    signal_type: str
    signal_text: str
    player_name: Optional[str] = None
    team: Optional[str] = None
    source_link: Optional[str] = None
    feedback_choice: Optional[str] = None
    note_text: str = ""
    created_at: datetime
    updated_at: datetime


class NewsMonitorFeedbackListResponse(BaseModel):
    rows: List[NewsMonitorFeedbackResponse]


class NewsMonitorImportRequest(BaseModel):
    path: str = Field(..., min_length=1, description="Local CSV or JSON file path")
    run_date: Optional[date] = None
    source_id: str = Field(default="historical_import")
    source_name: str = Field(default="Historical Import")


class NewsMonitorSignal(BaseModel):
    signal_type: str
    signal_text: str
    dfs_relevance: str
    confidence: str
    player_name: Optional[str] = None
    team: Optional[str] = None
    source_link: Optional[str] = None


class NewsMonitorHeadline(BaseModel):
    source_id: str
    title: Optional[str] = None
    link: Optional[str] = None
    published_at: Optional[str] = None


class NewsMonitorSourceCheck(BaseModel):
    source_id: str
    source_name: str
    status: str
    items_seen: int
    items_inserted: int
    signals_inserted: int


class NewsMonitorSourceError(BaseModel):
    source_id: str
    error: str


class NewsMonitorReportSummary(BaseModel):
    high_priority_count: int
    items_needing_manual_review: int


class NewsMonitorReport(BaseModel):
    date: str
    summary: NewsMonitorReportSummary
    high_priority_signals: List[NewsMonitorSignal]
    injury_updates: List[NewsMonitorSignal]
    roster_moves: List[NewsMonitorSignal]
    depth_chart_notes: List[NewsMonitorSignal]
    manual_review: List[NewsMonitorSignal]
    team_headlines: List[NewsMonitorHeadline]
    sources_checked: List[NewsMonitorSourceCheck]
    source_errors: List[NewsMonitorSourceError]


class NewsMonitorRunResponse(BaseModel):
    run_id: str
    run_date: date
    status: str
    forced: bool
    skipped: bool
    message: str
    sources_checked: int
    items_ingested: int
    signals_extracted: int
    completed_at: datetime
    report: NewsMonitorReport


class RawFileRequest(BaseModel):
    season: int
    week: int
    slate: str
    path: str


class SymbolicRuleSchema(BaseModel):
    rule_id: str
    rule_name: str
    rule_type: str
    enabled: bool = True
    priority: int = 100
    version: int = 1
    condition_json: dict = Field(default_factory=dict)
    action_json: dict = Field(default_factory=dict)


class SymbolicRuleListResponse(BaseModel):
    rows: List[SymbolicRuleSchema]


class SymbolicRuleUpsertRequest(BaseModel):
    rule_id: str
    rule_name: str
    rule_type: str
    enabled: bool = True
    priority: int = 100
    version: int = 1
    condition_json: dict = Field(default_factory=dict)
    action_json: dict = Field(default_factory=dict)


class SymbolicRuleToggleRequest(BaseModel):
    enabled: bool


class SymbolicBacktestMetrics(BaseModel):
    rows: int
    base_mae: float
    adjusted_mae: float
    mae_delta: float
    base_rmse: float
    adjusted_rmse: float
    rmse_delta: float
    base_bias: float
    adjusted_bias: float
    improved_rows: int
    worse_rows: int
    unchanged_rows: int
    hit_rate: float


class SymbolicBacktestRuleMetrics(SymbolicBacktestMetrics):
    rule_id: str
    rule_name: str


class SymbolicBacktestResponse(BaseModel):
    filters: dict
    overall: SymbolicBacktestMetrics
    by_rule: List[SymbolicBacktestRuleMetrics]
    runs: List[dict]


class SymbolicLearningRequest(BaseModel):
    season: int = Field(..., ge=2000)
    week: int = Field(..., ge=1, le=25)
    rule_run_id: Optional[str] = None
    slate: Optional[str] = None


class SymbolicLearningRecommendation(BaseModel):
    rule_id: str
    action: str
    severity: str
    rationale: str
    rows: int
    mae_delta: float
    hit_rate: float


class SymbolicLearningRowsWritten(BaseModel):
    projection_snapshots: int
    rule_evaluations: int
    learning_runs: int


class SymbolicLearningResponse(BaseModel):
    learning_run_id: str
    status: str
    filters: dict
    overall: SymbolicBacktestMetrics
    by_rule: List[SymbolicBacktestRuleMetrics]
    recommendations: List[SymbolicLearningRecommendation]
    rows_written: SymbolicLearningRowsWritten
    message: str
