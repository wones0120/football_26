"""FastAPI API routes."""

from __future__ import annotations

from pathlib import Path
import subprocess
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from Database import NFLIngestionController, NFLDataSource
from Database.manager import NFLDatabaseManager
from Database.config import get_connection_string
from Database.aggregations import (
    calculate_and_insert_player_season_averages,
    build_team_weekly_aggregations,
)
from Database.scoring import build_weekly_scores
from Database.features import build_player_features
from Database.raw_ingest import (
    load_raw_weekly_stats,
    load_raw_schedules,
    load_raw_weekly_rosters,
    load_raw_salaries,
    load_raw_injuries,
)
from Database.curated_ingest import (
    curate_weekly_stats,
    curate_rosters,
    curate_salaries,
    curate_injuries,
    _ensure_table,
)
from ..product_services.predictions import PredictionsService
import pandas as pd
import polars as pl
from sqlalchemy import text

from ..product_dependencies import (
    get_ingestion_controller,
    get_optimizer_service,
    get_simulation_service,
    get_classic_cash_stack_replay_service,
    get_slate_readiness_service,
    get_data_quality_service,
    get_belief_service,
    get_belief_impact_service,
    get_digital_twin_variant_service,
    get_thought_inbox_service,
    get_slate_service,
    get_data_source,
    get_news_monitor_service,
    get_predictions_service,
    get_starting_qb_service,
    get_ownership_service,
    get_batch_import_service,
    get_portfolio_service,
    get_draftkings_export_service,
)
from ..product_schemas import (
    LoadResponse,
    LoadSummarySchema,
    BuildFeaturesRequest,
    BuildFeaturesResponse,
    OptimizerRunRequest,
    OptimizerStatusResponse,
    SimulationRunRequest,
    SimulationRunResponse,
    ClassicCashStackReplayRequest,
    ClassicCashStackReplayResponse,
    SlateReadinessResponse,
    DataQualityHistoryResponse,
    BeliefCreateRequest,
    BeliefRevisionRequest,
    BeliefStatusRequest,
    BeliefResponse,
    BeliefListResponse,
    BeliefImpactPreviewRequest,
    BeliefImpactDecisionRequest,
    BeliefImpactPreviewResponse,
    BeliefImpactPreviewListResponse,
    DigitalTwinVariantSetCreateRequest,
    DigitalTwinVariantSetResponse,
    DigitalTwinVariantSetListResponse,
    DigitalTwinVariantReplayResponse,
    ThoughtCaptureRequest,
    ThoughtCandidateDecisionRequest,
    ThoughtCandidateResponse,
    ThoughtCaptureResponse,
    ThoughtCaptureListResponse,
    SeasonLoadRequest,
    SlateLoadResponse,
    SlateRequest,
    WeekLoadRequest,
    PredictionRunRequest,
    PredictionRunResponse,
    ActivePredictionRunRequest,
    ActivePredictionRunResponse,
    OwnershipLoadRequest,
    OwnershipProjectionListResponse,
    OwnershipRunRequest,
    OwnershipRunResponse,
    DraftKingsBatchImportRequest,
    DraftKingsBatchImportResponse,
    PortfolioCreateRequest,
    PortfolioResponse,
    DraftKingsExportResponse,
    ExportValidationResponse,
    PastSlateAnalysisRequest,
    PastSlateAnalysisResponse,
    PredictionListResponse,
    StartingQBRequest,
    StartingQBResponse,
    ValidationResponse,
    WeeklyValidationRow,
    UnmatchedSalaryResponse,
    UnmatchedInjuryResponse,
    PostgresStartResponse,
    AgentRunRequest,
    ManualNewsNoteRequest,
    ManualNewsNoteResponse,
    NewsMonitorFeedbackListResponse,
    NewsMonitorFeedbackResponse,
    NewsMonitorFeedbackUpsertRequest,
    NewsMonitorImportRequest,
    NewsMonitorRunRequest,
    NewsMonitorRunResponse,
    RawFileRequest,
    ProcessUnmatchedRequest,
    ProcessUnmatchedResponse,
    SymbolicRuleSchema,
    SymbolicRuleListResponse,
    SymbolicRuleUpsertRequest,
    SymbolicRuleToggleRequest,
    SymbolicBacktestResponse,
    SymbolicLearningRequest,
    SymbolicLearningResponse,
)
from ..product_services.optimizer import OptimizerService
from ..product_services.simulations import SimulationService
from ..product_services.replay import (
    DEFAULT_CASH_STACK_POLICY_IDS,
    ClassicCashStackReplayService,
)
from ..product_services.readiness import SlateReadinessService
from ..product_services.data_quality import DataQualityService
from ..product_services.beliefs import BeliefService
from ..product_services.belief_impacts import BeliefImpactService
from ..product_services.digital_twin_variants import DigitalTwinVariantService
from ..product_services.thought_inbox import ThoughtInboxService
from ..product_services.news_monitor import NewsMonitorService
from ..product_services.ownership import OwnershipService
from ..product_services.batch_import import DraftKingsBatchImportService
from ..product_services.portfolio import PortfolioService
from ..product_services.draftkings_export import DraftKingsExportService
from ..product_services.slate import SlateDataService
from ..product_services.validation import fetch_weekly_row_counts, fetch_unmatched_salaries, fetch_unmatched_injuries
from ..product_services.validation import process_unmatched_players
from ..product_services.agent import NewsMatchupAgent
from ..product_services.starters import StartingQBService

router = APIRouter(prefix="/api")
agent = NewsMatchupAgent()
logger = logging.getLogger(__name__)


def _to_load_response(summaries) -> LoadResponse:
    payload = [
        LoadSummarySchema(
            dataset=summary.dataset,
            season=summary.season,
            week=summary.week,
            rows_written=summary.rows_written,
        )
        for summary in summaries
    ]
    return LoadResponse(summaries=payload)


def _record_load_quality(
    service: DataQualityService,
    *,
    trigger: str,
    season: int,
    week: int | None,
    slate: str | None,
    summaries,
    source_context: dict | None = None,
) -> None:
    """Persist load telemetry without turning an audit failure into a false load failure."""
    try:
        service.record_load(
            trigger=trigger,
            season=season,
            week=week,
            slate=slate,
            summaries=summaries,
            source_context=source_context,
        )
    except Exception:  # noqa: BLE001 - quality telemetry must not rewrite load outcomes
        logger.exception("Unable to persist data-quality history for %s", trigger)


def _append_unmatched_summary(
    summaries: list,
    source: str,
    season: int,
    week: int | None = None,
    slate: str | None = None,
) -> None:
    """Optionally append unmatched counts from curated_unmatched (or injuries-specific table)."""
    try:
        engine = NFLDatabaseManager(get_connection_string()).engine
        # Ensure the table exists so a 0-count still returns a summary row
        if source == "injuries":
            table = "curated_injuries_unmatched"
            ddl = """
            CREATE TABLE IF NOT EXISTS curated_injuries_unmatched (
                season INT,
                week INT,
                slate TEXT,
                source TEXT,
                nickname TEXT,
                first_name TEXT,
                last_name TEXT,
                team TEXT,
                opponent TEXT,
                injury_indicator TEXT,
                injury_details TEXT
            );
            """
        elif source == "rosters":
            table = "curated_rosters_unmatched"
            ddl = """
            CREATE TABLE IF NOT EXISTS curated_rosters_unmatched (
                season INT,
                week INT,
                source TEXT,
                player_id TEXT,
                player_name TEXT,
                player_display_name TEXT,
                team TEXT,
                position TEXT,
                position_group TEXT,
                headshot_url TEXT
            );
            """
        else:
            table = "curated_unmatched"
            ddl = """
            CREATE TABLE IF NOT EXISTS curated_unmatched (
                id BIGSERIAL PRIMARY KEY,
                source TEXT,
                season INT,
                week INT,
                slate TEXT,
                add_to_player_master TEXT
            );
            """
        with engine.begin() as conn:
            conn.execute(text(ddl))
        where = ["season = :season"]
        params = {"season": season}
        if source != "injuries":
            where.insert(0, "source = :source")
            params["source"] = source
        if week is not None:
            where.append("week = :week")
            params["week"] = week
        if slate is not None:
            where.append("slate = :slate")
            params["slate"] = slate
        where_clause = " AND ".join(where)
        with engine.begin() as conn:
            cnt = conn.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE {where_clause}"),
                params,
            ).scalar()
        summaries.append(
            LoadSummarySchema(
                dataset=f"unmatched_{source}",
                season=season,
                week=week,
                rows_written=cnt,
            )
        )
    except Exception:
        # If table missing or query fails, skip silently
        pass


def _delete_curated(table: str, season: int, week: int | None = None, slate: str | None = None) -> None:
    """Delete existing curated rows for the given keys to avoid stale data."""
    engine = NFLDatabaseManager(get_connection_string()).engine
    where = ["season = :season"]
    params = {"season": season}
    if week is not None:
        where.append("week = :week")
        params["week"] = week
    if slate is not None:
        where.append("slate = :slate")
        params["slate"] = slate
    where_clause = " AND ".join(where)
    try:
        with engine.begin() as conn:
            conn.execute(text(f"DELETE FROM {table} WHERE {where_clause}"), params)
    except Exception:
        # Table may not exist yet; skip
        return


@router.post("/season/load", response_model=LoadResponse)
def load_season(
    request: SeasonLoadRequest,
    controller: NFLIngestionController = Depends(get_ingestion_controller),
    quality_service: DataQualityService = Depends(get_data_quality_service),
) -> LoadResponse:
    try:
        summaries = controller.run_season(
            season=request.season,
            datasets=request.datasets,
        )
    except ValueError as exc:  # dataset validation errors
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    _record_load_quality(
        quality_service,
        trigger="season_load",
        season=request.season,
        week=None,
        slate=None,
        summaries=summaries,
    )
    return _to_load_response(summaries)


@router.post("/week/load", response_model=LoadResponse)
def load_week(
    request: WeekLoadRequest,
    controller: NFLIngestionController = Depends(get_ingestion_controller),
    quality_service: DataQualityService = Depends(get_data_quality_service),
) -> LoadResponse:
    try:
        summaries = controller.run_week(
            season=request.season,
            week=request.week,
            datasets=request.datasets,
        )
        connection_string = get_connection_string()
        db_manager = NFLDatabaseManager(connection_string)
        engine = db_manager.engine

        # Build DK scoring table for this week
        scored_rows = build_weekly_scores(
            season=request.season,
            weeks=[request.week],
            connection_string=connection_string,
        )

        # Run aggregation pipeline based on nfl_weekly_data_with_scores
        # Use weekly data with scores for player season averages (DK metrics)
        with engine.connect() as connection:
            weekly_scores_pd = pd.read_sql(
                text(
                    "SELECT * FROM nfl_weekly_data_with_scores WHERE season = :season"
                ),
                connection,
                params={"season": request.season},
            )
        weekly_scores_df = pl.from_pandas(weekly_scores_pd)

        calculate_and_insert_player_season_averages(
            weekly_stats_with_scores=weekly_scores_df,
            db_manager=db_manager,
            season=request.season,
        )

        # Use full weekly data for team-level offense/defense so it's not slate-limited
        with engine.connect() as connection:
            weekly_pd = pd.read_sql(
                text("SELECT * FROM nfl_weekly_data WHERE season = :season"),
                connection,
                params={"season": request.season},
            )
        weekly_df = pl.from_pandas(weekly_pd)

        build_team_weekly_aggregations(
            weekly_stats_with_scores=weekly_df,
            db_manager=db_manager,
            season=request.season,
            weeks=[request.week],
        )

        # Build predictive feature store rows for modeling
        feature_rows = build_player_features(
            season=request.season,
            weeks=[request.week],
            connection_string=connection_string,
        )

        # Append simple summaries for aggregated tables
        extra = []
        with engine.connect() as connection:
            # season-level
            ps_count = connection.execute(
                text(
                    "SELECT COUNT(*) FROM player_season_averages WHERE season = :season"
                ),
                {"season": request.season},
            ).scalar_one()
            extra.append(
                type(
                    "Summary",
                    (),
                    dict(
                        dataset="player_season_averages",
                        season=request.season,
                        week=None,
                        rows_written=int(ps_count),
                    ),
                )()
            )
            # weekly aggregations
            for table in [
                "team_weekly_offense",
                "team_weekly_defense",
                "team_weekly_position_offense",
                "team_weekly_position_defense",
            ]:
                count = connection.execute(
                    text(
                        f"SELECT COUNT(*) FROM {table} "
                        "WHERE season = :season AND week = :week"
                    ),
                    {"season": request.season, "week": request.week},
                ).scalar_one()
                extra.append(
                    type(
                        "Summary",
                        (),
                        dict(
                            dataset=table,
                            season=request.season,
                            week=request.week,
                            rows_written=int(count),
                        ),
                    )()
                )
            # scored weekly table
            extra.append(
                type(
                    "Summary",
                    (),
                    dict(
                        dataset="nfl_weekly_data_with_scores",
                        season=request.season,
                        week=request.week,
                        rows_written=int(scored_rows),
                    ),
                )()
            )
            extra.append(
                type(
                    "Summary",
                    (),
                    dict(
                        dataset="predictive_features",
                        season=request.season,
                        week=request.week,
                        rows_written=int(feature_rows),
                    ),
                )()
            )
        summaries = summaries + extra
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    _record_load_quality(
        quality_service,
        trigger="week_load",
        season=request.season,
        week=request.week,
        slate=None,
        summaries=summaries,
    )
    return _to_load_response(summaries)


@router.post("/raw/week/stats", response_model=LoadResponse)
def load_raw_week_stats(
    request: WeekLoadRequest,
    quality_service: DataQualityService = Depends(get_data_quality_service),
) -> LoadResponse:
    """Load raw weekly stats from source, then build curated weekly stats."""
    summaries = []
    rows_stats = load_raw_weekly_stats(season=request.season, weeks=[request.week])
    summaries.append(
        LoadSummarySchema(
            dataset="raw_weekly_stats",
            season=request.season,
            week=request.week,
            rows_written=rows_stats,
        )
    )
    _delete_curated("curated_weekly_stats", season=request.season, week=request.week)
    curated_stats = curate_weekly_stats(season=request.season, weeks=[request.week])
    if curated_stats > 0:
        summaries.append(
            LoadSummarySchema(
                dataset="curated_weekly_stats",
                season=request.season,
                week=request.week,
                rows_written=curated_stats,
            )
        )
    _append_unmatched_summary(summaries, source="weekly_stats", season=request.season, week=request.week)
    _record_load_quality(
        quality_service,
        trigger="raw_weekly_stats_load",
        season=request.season,
        week=request.week,
        slate=None,
        summaries=summaries,
    )
    return LoadResponse(summaries=summaries)


@router.post("/raw/week/rosters", response_model=LoadResponse)
def load_raw_week_rosters(
    request: WeekLoadRequest,
    quality_service: DataQualityService = Depends(get_data_quality_service),
) -> LoadResponse:
    """Load raw weekly rosters from source, then build curated weekly rosters."""
    summaries = []
    rows_rosters = load_raw_weekly_rosters(season=request.season, weeks=[request.week])
    summaries.append(
        LoadSummarySchema(
            dataset="raw_weekly_rosters",
            season=request.season,
            week=request.week,
            rows_written=rows_rosters,
        )
    )
    _delete_curated("curated_weekly_rosters", season=request.season, week=request.week)
    curated_rosters = curate_rosters(season=request.season, weeks=[request.week])
    if curated_rosters > 0:
        summaries.append(
            LoadSummarySchema(
                dataset="curated_weekly_rosters",
                season=request.season,
                week=request.week,
                rows_written=curated_rosters,
            )
        )
    _append_unmatched_summary(summaries, source="rosters", season=request.season, week=request.week)
    _record_load_quality(
        quality_service,
        trigger="raw_weekly_rosters_load",
        season=request.season,
        week=request.week,
        slate=None,
        summaries=summaries,
    )
    return LoadResponse(summaries=summaries)


@router.post("/raw/season/load", response_model=LoadResponse)
def load_raw_season(
    request: SeasonLoadRequest,
    quality_service: DataQualityService = Depends(get_data_quality_service),
) -> LoadResponse:
    """Load raw schedules for a season, then build curated version."""
    summaries = []
    rows_sched = load_raw_schedules(season=request.season)
    summaries.append(
        LoadSummarySchema(
            dataset="raw_schedules",
            season=request.season,
            week=None,
            rows_written=rows_sched,
        )
    )
    # Curated schedules (direct copy for now)
    from Database.curated_ingest import _ensure_table
    import pandas as pd
    import sqlalchemy
    engine = sqlalchemy.create_engine(get_connection_string())
    with engine.begin() as conn:
        raw_sched = pd.read_sql(
            text("SELECT * FROM raw_schedules WHERE season = :season"),
            conn,
            params={"season": request.season},
        )
    if not raw_sched.empty:
        _ensure_table(engine, "curated_schedules", raw_sched)
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM curated_schedules WHERE season = :season"), {"season": request.season})
            raw_sched.to_sql("curated_schedules", conn, if_exists="append", index=False)
        summaries.append(
            LoadSummarySchema(
                dataset="curated_schedules",
                season=request.season,
                week=None,
                rows_written=len(raw_sched),
            )
        )
    _record_load_quality(
        quality_service,
        trigger="raw_season_load",
        season=request.season,
        week=None,
        slate=None,
        summaries=summaries,
    )
    return LoadResponse(summaries=summaries)


@router.post("/raw/salaries/load", response_model=LoadResponse)
def load_raw_salaries_api(
    request: RawFileRequest,
    quality_service: DataQualityService = Depends(get_data_quality_service),
) -> LoadResponse:
    """Load a raw salaries CSV into raw_salaries using provided path, then curate."""
    path = Path(request.path).expanduser()
    if not path.exists():
        raise HTTPException(status_code=400, detail=f"Salary file not found: {path}")
    summaries: list[LoadSummarySchema] = []
    rows = load_raw_salaries(path, season=request.season, week=request.week, slate=request.slate)
    summaries.append(
        LoadSummarySchema(
            dataset="raw_salaries",
            season=request.season,
            week=request.week,
            rows_written=rows,
        )
    )
    try:
        _delete_curated("curated_salaries", season=request.season, week=request.week, slate=request.slate)
        curated_rows = curate_salaries(season=request.season, week=request.week, slate=request.slate)
        if curated_rows > 0:
            summaries.append(
                LoadSummarySchema(
                    dataset="curated_salaries",
                    season=request.season,
                    week=request.week,
                    rows_written=curated_rows,
                )
            )
    except ValueError:
        _delete_curated("curated_salaries", season=request.season, week=request.week, slate=request.slate)
    _append_unmatched_summary(summaries, source="salaries", season=request.season, week=request.week, slate=request.slate)
    _record_load_quality(
        quality_service,
        trigger="raw_salary_load",
        season=request.season,
        week=request.week,
        slate=request.slate,
        summaries=summaries,
        source_context={"path": str(path)},
    )
    return _to_load_response(summaries)


@router.post("/raw/injuries/load", response_model=LoadResponse)
def load_raw_injuries_api(
    request: RawFileRequest,
    quality_service: DataQualityService = Depends(get_data_quality_service),
) -> LoadResponse:
    """Load a raw injuries CSV into raw_injuries using provided path, then curate."""
    path = Path(request.path).expanduser()
    if not path.exists():
        raise HTTPException(status_code=400, detail=f"Injury file not found: {path}")
    rows = load_raw_injuries(path, season=request.season, week=request.week, slate=request.slate)
    summaries: list[LoadSummarySchema] = []
    try:
        _delete_curated("curated_injuries_unmatched", season=request.season, week=request.week, slate=request.slate)
        _delete_curated("curated_injuries", season=request.season, week=request.week, slate=request.slate)
        curated_rows = curate_injuries(season=request.season, week=request.week, slate=request.slate)
        summaries.append(
            LoadSummarySchema(
                dataset="raw_injuries",
                season=request.season,
                week=request.week,
                rows_written=rows,
            )
        )
        summaries.append(
            LoadSummarySchema(
                dataset="curated_injuries",
                season=request.season,
                week=request.week,
                rows_written=curated_rows,
            )
        )
    except ValueError:
        _delete_curated("curated_injuries_unmatched", season=request.season, week=request.week, slate=request.slate)
        _delete_curated("curated_injuries", season=request.season, week=request.week, slate=request.slate)
        summaries.append(
            LoadSummarySchema(
                dataset="raw_injuries",
                season=request.season,
                week=request.week,
                rows_written=rows,
            )
        )
    _append_unmatched_summary(summaries, source="injuries", season=request.season, week=request.week, slate=request.slate)
    _record_load_quality(
        quality_service,
        trigger="raw_injury_load",
        season=request.season,
        week=request.week,
        slate=request.slate,
        summaries=summaries,
        source_context={"path": str(path)},
    )
    return _to_load_response(summaries)


@router.post("/slate/salaries", response_model=SlateLoadResponse)
def load_slate_salaries(
    request: SlateRequest,
    service: SlateDataService = Depends(get_slate_service),
    quality_service: DataQualityService = Depends(get_data_quality_service),
) -> SlateLoadResponse:
    result = service.load_salaries(
        season=request.season,
        week=request.week,
        slate=request.slate,
        source=None,
    )
    _record_load_quality(
        quality_service,
        trigger="slate_salary_load",
        season=request.season,
        week=request.week,
        slate=request.slate,
        summaries=[{"dataset": "slate_salaries", **result.__dict__}],
    )
    return SlateLoadResponse(**result.__dict__)


@router.post("/slate/injuries", response_model=SlateLoadResponse)
def load_slate_injuries(
    request: SlateRequest,
    service: SlateDataService = Depends(get_slate_service),
    quality_service: DataQualityService = Depends(get_data_quality_service),
) -> SlateLoadResponse:
    result = service.load_injuries(
        season=request.season,
        week=request.week,
        slate=request.slate,
        source=None,
    )
    _record_load_quality(
        quality_service,
        trigger="slate_injury_load",
        season=request.season,
        week=request.week,
        slate=request.slate,
        summaries=[{"dataset": "slate_injuries", **result.__dict__}],
    )
    return SlateLoadResponse(**result.__dict__)


@router.post("/ownership/load", response_model=OwnershipRunResponse)
def load_ownership(
    request: OwnershipLoadRequest,
    service: OwnershipService = Depends(get_ownership_service),
    quality_service: DataQualityService = Depends(get_data_quality_service),
) -> OwnershipRunResponse:
    try:
        result = service.load_contest_standings(
            season=request.season,
            week=request.week,
            slate=request.slate,
            path=request.path,
            contest_id=request.contest_id,
            contest_name=request.contest_name,
            contest_format=request.contest_format,
            contest_type=request.contest_type,
            entry_fee=request.entry_fee,
            field_size=request.field_size,
            max_entries_per_user=request.max_entries_per_user,
            prize_pool=request.prize_pool,
            payout_tiers=[tier.dict() for tier in request.payout_tiers],
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _record_load_quality(
        quality_service,
        trigger="ownership_load",
        season=request.season,
        week=request.week,
        slate=request.slate,
        summaries=[{"dataset": "ownership", **result.__dict__}],
        source_context={"path": request.path},
    )
    return OwnershipRunResponse(**result.__dict__)


@router.post("/imports/draftkings/batch", response_model=DraftKingsBatchImportResponse)
def batch_import_draftkings(
    request: DraftKingsBatchImportRequest,
    service: DraftKingsBatchImportService = Depends(get_batch_import_service),
    quality_service: DataQualityService = Depends(get_data_quality_service),
) -> DraftKingsBatchImportResponse:
    try:
        result = service.import_directory(
            request.directory,
            season=request.season,
            week=request.week,
            slate=request.slate,
            recursive=request.recursive,
            dry_run=request.dry_run,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    batch_checks = []
    for row in result.files:
        status = (
            "fail" if row.status == "failed"
            else "warn" if row.status in {"skipped", "unrecognized"}
            else "pass"
        )
        batch_checks.append(
            {
                **row.__dict__,
                "dataset": f"draftkings_{row.file_type}",
                "status": status,
                "threshold": "imported, deduplicated, or recognized dry-run file",
            }
        )
    _record_load_quality(
        quality_service,
        trigger="draftkings_batch_dry_run" if request.dry_run else "draftkings_batch_import",
        season=request.season,
        week=request.week,
        slate=request.slate,
        summaries=batch_checks,
        source_context={"batch_id": result.batch_id, "directory": result.directory},
    )
    return DraftKingsBatchImportResponse(**result.as_dict())


@router.post("/portfolios", response_model=PortfolioResponse)
def create_portfolio(
    request: PortfolioCreateRequest,
    service: PortfolioService = Depends(get_portfolio_service),
) -> PortfolioResponse:
    try:
        result = service.create_portfolio(
            portfolio_name=request.portfolio_name,
            optimizer_run_id=request.optimizer_run_id,
            template_id=request.template_id,
            lineup_ids=request.lineup_ids,
            default_contest_id=request.default_contest_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PortfolioResponse(**result.as_dict())


@router.get("/portfolios/{portfolio_id}", response_model=PortfolioResponse)
def get_portfolio(
    portfolio_id: str,
    service: PortfolioService = Depends(get_portfolio_service),
) -> PortfolioResponse:
    result = service.get_portfolio(portfolio_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return PortfolioResponse(**result.as_dict())


@router.post(
    "/portfolios/{portfolio_id}/exports/draftkings",
    response_model=DraftKingsExportResponse,
)
def generate_draftkings_export(
    portfolio_id: str,
    service: DraftKingsExportService = Depends(get_draftkings_export_service),
) -> DraftKingsExportResponse:
    try:
        result = service.generate_export(portfolio_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return DraftKingsExportResponse(**result.as_dict())


@router.post(
    "/portfolios/{portfolio_id}/exports/draftkings/validate",
    response_model=ExportValidationResponse,
)
def validate_draftkings_export(
    portfolio_id: str,
    service: DraftKingsExportService = Depends(get_draftkings_export_service),
) -> ExportValidationResponse:
    try:
        result = service.validate_portfolio(portfolio_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ExportValidationResponse(**result.as_dict())


@router.get("/exports/{export_id}/download")
def download_draftkings_export(
    export_id: str,
    service: DraftKingsExportService = Depends(get_draftkings_export_service),
) -> Response:
    result = service.get_export(export_id)
    if result is None:
        raise HTTPException(status_code=404, detail="DraftKings export not found")
    return Response(
        content=result.csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{result.file_name}"'},
    )


@router.post("/ownership/run", response_model=OwnershipRunResponse)
def run_ownership_model(
    request: OwnershipRunRequest,
    service: OwnershipService = Depends(get_ownership_service),
) -> OwnershipRunResponse:
    result = service.run_projection_model(
        season=request.season,
        week=request.week,
        slate=request.slate,
        positions=request.positions,
        data_cutoff_at=request.data_cutoff_at,
    )
    payload = {**result.__dict__, "model_metrics": result.model_metrics or {}}
    return OwnershipRunResponse(**payload)


@router.get("/ownership/latest", response_model=OwnershipProjectionListResponse)
def get_latest_ownership(
    season: int,
    week: int,
    slate: str | None = None,
    limit: int = 500,
    service: OwnershipService = Depends(get_ownership_service),
) -> OwnershipProjectionListResponse:
    rows = service.fetch_projected_ownership(season=season, week=week, slate=slate, limit=limit)
    return OwnershipProjectionListResponse(season=season, week=week, slate=slate, rows=rows)


@router.post("/ownership/analyze-past", response_model=PastSlateAnalysisResponse)
def analyze_past_ownership(
    request: PastSlateAnalysisRequest,
    service: OwnershipService = Depends(get_ownership_service),
) -> PastSlateAnalysisResponse:
    try:
        result = service.analyze_past_slate(
            season=request.season,
            week=request.week,
            slate=request.slate,
            path=request.path,
            top_n=request.top_n,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PastSlateAnalysisResponse(**result)


@router.post("/predict/run", response_model=PredictionRunResponse)
def run_predictions(
    request: PredictionRunRequest,
    service: PredictionsService = Depends(get_predictions_service),
) -> PredictionRunResponse:
    slate_for_prediction = request.slate
    if request.slate:
        connection_string = get_connection_string()
        db_manager = NFLDatabaseManager(connection_string)
        with db_manager.engine.connect() as connection:
            salary_count = connection.execute(
                text(
                    "SELECT COUNT(*) FROM curated_salaries "
                    "WHERE season = :season AND week = :week AND slate = :slate"
                ),
                {"season": request.season, "week": request.week, "slate": request.slate},
            ).scalar_one()
        if salary_count == 0:
            logging.warning(
                "No curated_salaries found for season=%s week=%s slate=%s; running projections without slate filter.",
                request.season,
                request.week,
                request.slate,
            )
            slate_for_prediction = None

    # Ensure inputs exist: compute DK scoring and feature store for the whole season.
    scored_rows = build_weekly_scores(
        season=request.season,
        weeks=None,
        connection_string=get_connection_string(),
    )
    if scored_rows == 0:
        raise HTTPException(
            status_code=422,
            detail=f"No weekly stats found for season {request.season}. Load any completed week first.",
        )

    feature_rows = build_player_features(
        season=request.season,
        weeks=None,
        connection_string=get_connection_string(),
    )
    if feature_rows == 0:
        # If the target week has no rows yet, attempt a future-week build using historical data
        try:
            feature_rows = build_player_features(
                season=request.season,
                weeks=None,
                future_week=request.week,
                connection_string=get_connection_string(),
            )
        except Exception:
            feature_rows = 0
    if feature_rows == 0:
        raise HTTPException(
            status_code=422,
            detail=(
                f"No predictive features available for season {request.season} "
                f"week {request.week}. Load stats and salaries, then retry."
            ),
        )

    try:
        result = service.train_and_predict(
            season=request.season,
            week=request.week,
            positions=request.positions,
            slate=slate_for_prediction,
            data_cutoff_at=request.data_cutoff_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    message = "Predictions generated" if result.records else "No predictions generated"
    return PredictionRunResponse(
        season=request.season,
        week=request.week,
        rows_written=len(result.records),
        message=message,
        feature_run_id=result.feature_run_id,
        model_run_id=result.model_run_id,
        projection_run_id=result.projection_run_id,
        data_cutoff_at=result.data_cutoff_at,
        target_persisted=result.target_persisted,
        calibration_metrics=result.calibration_metrics or {},
    )




@router.post("/features/build", response_model=BuildFeaturesResponse)
def build_features(
    request: BuildFeaturesRequest,
    quality_service: DataQualityService = Depends(get_data_quality_service),
) -> BuildFeaturesResponse:
    rows = build_player_features(
        season=request.season,
        weeks=request.weeks,
        future_week=request.future_week,
        connection_string=get_connection_string(),
    )
    if request.future_week:
        weeks_desc = f"future week {request.future_week} (using history)"
    else:
        weeks_desc = "all weeks" if not request.weeks else f"weeks {request.weeks}"
    message = f"Built {rows} feature rows for season {request.season} ({weeks_desc})"
    quality_week = request.future_week or (request.weeks[0] if request.weeks and len(request.weeks) == 1 else None)
    _record_load_quality(
        quality_service,
        trigger="feature_build",
        season=request.season,
        week=quality_week,
        slate=None,
        summaries=[
            {
                "dataset": "predictive_features",
                "season": request.season,
                "week": quality_week,
                "rows_written": rows,
                "message": message,
            }
        ],
        source_context={"weeks": request.weeks, "future_week": request.future_week},
    )
    return BuildFeaturesResponse(
        season=request.season,
        weeks=request.weeks,
        rows_written=rows,
        message=message,
    )


@router.post("/agent/run")
def run_agent(request: AgentRunRequest) -> dict:
    proj, adjustments, config, traces = agent.run(
        request.season,
        request.week,
        slate=request.slate,
        projection_run_id=request.projection_run_id,
    )
    return {
        "season": request.season,
        "week": request.week,
        "rule_run_id": config.rule_run_id,
        "projection_run_id": config.projection_run_id,
        "target_persisted": config.target_persisted,
        "adjusted_rows": len(adjustments),
        "adjustments": [adj.__dict__ for adj in adjustments],
        "config": config.__dict__,
        "trace_rows": len(traces),
        "traces": [trace.__dict__ for trace in traces],
    }


@router.get("/agent/rules", response_model=SymbolicRuleListResponse)
def list_agent_rules(include_disabled: bool = True) -> SymbolicRuleListResponse:
    rows = agent.list_rules(include_disabled=include_disabled)
    payload = [
        SymbolicRuleSchema(
            rule_id=row.rule_id,
            rule_name=row.rule_name,
            rule_type=row.rule_type,
            enabled=row.enabled,
            priority=row.priority,
            version=row.version,
            condition_json=row.condition_json,
            action_json=row.action_json,
        )
        for row in rows
    ]
    return SymbolicRuleListResponse(rows=payload)


@router.post("/agent/rules", response_model=SymbolicRuleSchema)
def upsert_agent_rule(request: SymbolicRuleUpsertRequest) -> SymbolicRuleSchema:
    try:
        row = agent.upsert_rule(
            rule_id=request.rule_id,
            rule_name=request.rule_name,
            rule_type=request.rule_type,
            enabled=request.enabled,
            priority=request.priority,
            version=request.version,
            condition_json=request.condition_json,
            action_json=request.action_json,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SymbolicRuleSchema(
        rule_id=row.rule_id,
        rule_name=row.rule_name,
        rule_type=row.rule_type,
        enabled=row.enabled,
        priority=row.priority,
        version=row.version,
        condition_json=row.condition_json,
        action_json=row.action_json,
    )


@router.patch("/agent/rules/{rule_id}/enabled", response_model=SymbolicRuleSchema)
def set_agent_rule_enabled(rule_id: str, request: SymbolicRuleToggleRequest) -> SymbolicRuleSchema:
    row = agent.set_rule_enabled(rule_id=rule_id, enabled=request.enabled)
    if not row:
        raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")
    return SymbolicRuleSchema(
        rule_id=row.rule_id,
        rule_name=row.rule_name,
        rule_type=row.rule_type,
        enabled=row.enabled,
        priority=row.priority,
        version=row.version,
        condition_json=row.condition_json,
        action_json=row.action_json,
    )


@router.get("/agent/backtest", response_model=SymbolicBacktestResponse)
def backtest_agent(
    season: int | None = None,
    week: int | None = None,
    rule_run_id: str | None = None,
    slate: str | None = None,
) -> SymbolicBacktestResponse:
    return SymbolicBacktestResponse(
        **agent.backtest(
            season=season,
            week=week,
            rule_run_id=rule_run_id,
            slate=slate,
        )
    )


@router.post("/agent/learning/evaluate", response_model=SymbolicLearningResponse)
def evaluate_agent_learning(request: SymbolicLearningRequest) -> SymbolicLearningResponse:
    return SymbolicLearningResponse(
        **agent.evaluate_learning(
            season=request.season,
            week=request.week,
            rule_run_id=request.rule_run_id,
            slate=request.slate,
        )
    )


@router.get("/predict/latest", response_model=PredictionListResponse)
def get_latest_predictions(
    season: int,
    week: int,
    limit: int = 1000,
    slate: str | None = None,
    projection_run_id: str | None = None,
    service: PredictionsService = Depends(get_predictions_service),
) -> PredictionListResponse:
    rows = service.fetch_predictions(
        season=season,
        week=week,
        limit=limit,
        slate=slate,
        projection_run_id=projection_run_id,
    )
    selected_run_id = rows[0].get("projection_run_id") if rows else projection_run_id
    return PredictionListResponse(
        season=season,
        week=week,
        projection_run_id=selected_run_id,
        rows=rows,
    )


@router.post("/predict/active", response_model=ActivePredictionRunResponse)
def select_active_prediction_run(
    request: ActivePredictionRunRequest,
    service: PredictionsService = Depends(get_predictions_service),
) -> ActivePredictionRunResponse:
    try:
        selected = service.select_active_prediction_run(
            season=request.season,
            week=request.week,
            slate=request.slate,
            projection_run_id=request.projection_run_id,
            selection_reason=request.selection_reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ActivePredictionRunResponse(**selected)


@router.get("/data/unmatched-salaries", response_model=UnmatchedSalaryResponse)
def get_unmatched_salaries(
    season: int | None = None,
    week: int | None = None,
    slate: str | None = None,
    limit: int = 50,
) -> UnmatchedSalaryResponse:
    rows = fetch_unmatched_salaries(season=season, week=week, slate=slate, limit=limit)
    return UnmatchedSalaryResponse(rows=rows)


@router.get("/data/unmatched-injuries", response_model=UnmatchedInjuryResponse)
def get_unmatched_injuries(
    season: int | None = None,
    week: int | None = None,
    slate: str | None = None,
    limit: int = 50,
) -> UnmatchedInjuryResponse:
    rows = fetch_unmatched_injuries(season=season, week=week, slate=slate, limit=limit)
    return UnmatchedInjuryResponse(rows=rows)


@router.post("/data/unmatched/process", response_model=ProcessUnmatchedResponse)
def process_unmatched_api(
    request: ProcessUnmatchedRequest,
    quality_service: DataQualityService = Depends(get_data_quality_service),
) -> ProcessUnmatchedResponse:
    result = process_unmatched_players(
        season=request.season,
        week=request.week,
        source=request.source,
    )
    message = f"Processed {result['processed']} unmatched rows; added {result['added']}; skipped existing {result['skipped_existing']}."
    if request.season is not None:
        _record_load_quality(
            quality_service,
            trigger="identity_repair",
            season=request.season,
            week=request.week,
            slate=None,
            summaries=[
                {
                    "dataset": f"player_master_{request.source}",
                    "rows_written": result["added"],
                    "status": "pass" if result["processed"] > 0 else "warn",
                    "threshold": "> 0 unmatched rows inspected",
                    "message": message,
                }
            ],
            source_context=result,
        )
    return ProcessUnmatchedResponse(
        added=result["added"],
        skipped_existing=result["skipped_existing"],
        processed=result["processed"],
        message=message,
    )


@router.get("/data/validate", response_model=ValidationResponse)
def validate_weekly_data(table: str = "nfl_weekly_data_with_scores") -> ValidationResponse:
    """
    Return row counts per season/week (ascending) for a given table, filling missing weeks with zero.
    """
    rows = fetch_weekly_row_counts(table_name=table)
    return ValidationResponse(
        table=table,
        results=[WeeklyValidationRow(**row) for row in rows],
    )


@router.get("/slate/readiness", response_model=SlateReadinessResponse)
def get_slate_readiness(
    season: int = Query(..., ge=2000),
    week: int = Query(..., ge=1, le=25),
    slate: str = Query(..., min_length=1),
    record: bool = Query(False),
    service: SlateReadinessService = Depends(get_slate_readiness_service),
    quality_service: DataQualityService = Depends(get_data_quality_service),
) -> SlateReadinessResponse:
    report = service.report(season=season, week=week, slate=slate)
    if record:
        try:
            quality_service.record_readiness(report, trigger="readiness_preflight")
        except Exception:  # noqa: BLE001 - a telemetry failure must not hide readiness results
            logger.exception("Unable to persist slate-readiness quality history")
    return SlateReadinessResponse(**report)


@router.get("/data/quality/history", response_model=DataQualityHistoryResponse)
def get_data_quality_history(
    season: int = Query(..., ge=2000),
    week: int | None = Query(None, ge=1, le=25),
    slate: str | None = Query(None, min_length=1),
    limit: int = Query(20, ge=1, le=100),
    service: DataQualityService = Depends(get_data_quality_service),
) -> DataQualityHistoryResponse:
    return DataQualityHistoryResponse(
        **service.history(season=season, week=week, slate=slate, limit=limit)
    )


@router.get("/digital-twin/beliefs", response_model=BeliefListResponse)
def get_digital_twin_beliefs(
    season: int | None = Query(None, ge=2000),
    week: int | None = Query(None, ge=1, le=25),
    slate: str | None = Query(None, min_length=1),
    include_inactive: bool = Query(True),
    limit: int = Query(200, ge=1, le=500),
    service: BeliefService = Depends(get_belief_service),
) -> BeliefListResponse:
    return BeliefListResponse(
        **service.list(
            season=season,
            week=week,
            slate=slate,
            include_inactive=include_inactive,
            limit=limit,
        )
    )


@router.get("/digital-twin/thought-captures", response_model=ThoughtCaptureListResponse)
def get_digital_twin_thought_captures(
    season: int | None = Query(None, ge=2000),
    week: int | None = Query(None, ge=1, le=25),
    slate: str | None = Query(None, min_length=1),
    limit: int = Query(20, ge=1, le=100),
    service: ThoughtInboxService = Depends(get_thought_inbox_service),
) -> ThoughtCaptureListResponse:
    return ThoughtCaptureListResponse(
        rows=service.list(season=season, week=week, slate=slate, limit=limit)
    )


@router.post("/digital-twin/thought-captures", response_model=ThoughtCaptureResponse)
def create_digital_twin_thought_capture(
    request: ThoughtCaptureRequest,
    service: ThoughtInboxService = Depends(get_thought_inbox_service),
) -> ThoughtCaptureResponse:
    try:
        result = service.capture(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ThoughtCaptureResponse(**result)


@router.post(
    "/digital-twin/thought-candidates/{candidate_id}/decision",
    response_model=ThoughtCandidateResponse,
)
def decide_digital_twin_thought_candidate(
    candidate_id: str,
    request: ThoughtCandidateDecisionRequest,
    service: ThoughtInboxService = Depends(get_thought_inbox_service),
) -> ThoughtCandidateResponse:
    try:
        result = service.decide(
            candidate_id,
            request.decision,
            request.belief.model_dump() if request.belief else None,
        )
    except ValueError as exc:
        status_code = 404 if str(exc).startswith("Thought candidate not found:") else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return ThoughtCandidateResponse(**result)


@router.post("/digital-twin/beliefs", response_model=BeliefResponse)
def create_digital_twin_belief(
    request: BeliefCreateRequest,
    service: BeliefService = Depends(get_belief_service),
) -> BeliefResponse:
    try:
        result = service.create(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return BeliefResponse(**result)


@router.post("/digital-twin/beliefs/{belief_id}/revisions", response_model=BeliefResponse)
def revise_digital_twin_belief(
    belief_id: str,
    request: BeliefRevisionRequest,
    service: BeliefService = Depends(get_belief_service),
) -> BeliefResponse:
    try:
        result = service.revise(belief_id, request.model_dump(exclude_unset=True))
    except ValueError as exc:
        status_code = 404 if str(exc).startswith("Belief not found:") else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return BeliefResponse(**result)


@router.post("/digital-twin/beliefs/{belief_id}/status", response_model=BeliefResponse)
def set_digital_twin_belief_status(
    belief_id: str,
    request: BeliefStatusRequest,
    service: BeliefService = Depends(get_belief_service),
) -> BeliefResponse:
    try:
        result = service.set_status(belief_id, request.status)
    except ValueError as exc:
        status_code = 404 if str(exc).startswith("Belief not found:") else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return BeliefResponse(**result)


@router.get("/digital-twin/impact-previews", response_model=BeliefImpactPreviewListResponse)
def get_digital_twin_impact_previews(
    belief_id: str | None = Query(None, min_length=1),
    season: int | None = Query(None, ge=2000),
    week: int | None = Query(None, ge=1, le=25),
    slate: str | None = Query(None, min_length=1),
    limit: int = Query(200, ge=1, le=500),
    service: BeliefImpactService = Depends(get_belief_impact_service),
) -> BeliefImpactPreviewListResponse:
    return BeliefImpactPreviewListResponse(
        rows=service.list(
            belief_id=belief_id,
            season=season,
            week=week,
            slate=slate,
            limit=limit,
        )
    )


@router.post(
    "/digital-twin/beliefs/{belief_id}/impact-previews",
    response_model=BeliefImpactPreviewResponse,
)
def create_digital_twin_impact_preview(
    belief_id: str,
    request: BeliefImpactPreviewRequest,
    service: BeliefImpactService = Depends(get_belief_impact_service),
) -> BeliefImpactPreviewResponse:
    try:
        result = service.create_preview(belief_id, request.model_dump())
    except ValueError as exc:
        status_code = 404 if str(exc).startswith(("Belief not found:", "Impact preview not found:")) else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return BeliefImpactPreviewResponse(**result)


@router.post(
    "/digital-twin/impact-previews/{preview_id}/decision",
    response_model=BeliefImpactPreviewResponse,
)
def decide_digital_twin_impact_preview(
    preview_id: str,
    request: BeliefImpactDecisionRequest,
    service: BeliefImpactService = Depends(get_belief_impact_service),
) -> BeliefImpactPreviewResponse:
    try:
        result = service.decide(preview_id, request.decision, request.note_text)
    except ValueError as exc:
        status_code = 404 if str(exc).startswith("Impact preview not found:") else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return BeliefImpactPreviewResponse(**result)


@router.get(
    "/digital-twin/variant-sets",
    response_model=DigitalTwinVariantSetListResponse,
)
def get_digital_twin_variant_sets(
    season: int | None = Query(None, ge=2000),
    week: int | None = Query(None, ge=1, le=25),
    slate: str | None = Query(None, min_length=1),
    limit: int = Query(20, ge=1, le=200),
    service: DigitalTwinVariantService = Depends(get_digital_twin_variant_service),
) -> DigitalTwinVariantSetListResponse:
    return DigitalTwinVariantSetListResponse(
        rows=service.list(season=season, week=week, slate=slate, limit=limit)
    )


@router.post(
    "/digital-twin/variant-sets",
    response_model=DigitalTwinVariantSetResponse,
)
def create_digital_twin_variant_set(
    request: DigitalTwinVariantSetCreateRequest,
    service: DigitalTwinVariantService = Depends(get_digital_twin_variant_service),
) -> DigitalTwinVariantSetResponse:
    try:
        result = service.create(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return DigitalTwinVariantSetResponse(**result)


@router.post(
    "/digital-twin/variant-sets/{variant_set_id}/replay",
    response_model=DigitalTwinVariantReplayResponse,
)
def replay_digital_twin_variant_set(
    variant_set_id: str,
    service: DigitalTwinVariantService = Depends(get_digital_twin_variant_service),
) -> DigitalTwinVariantReplayResponse:
    try:
        result = service.replay(variant_set_id)
    except ValueError as exc:
        status_code = 404 if str(exc).startswith("Digital Twin variant set not found:") else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return DigitalTwinVariantReplayResponse(**result)


@router.post("/optimizer/run", response_model=OptimizerStatusResponse)
def run_optimizer(
    request: OptimizerRunRequest,
    service: OptimizerService = Depends(get_optimizer_service),
) -> OptimizerStatusResponse:
    job = service.run_job(
        season=request.season,
        week=request.week,
        slate=request.slate,
        strategy=request.strategy,
        params=request.params,
        contest_format=request.contest_format,
        objective=request.objective,
        projection_run_id=request.projection_run_id,
        rule_run_id=request.rule_run_id,
        data_cutoff_at=request.data_cutoff_at,
    )
    return OptimizerStatusResponse(
        job_id=job.job_id,
        status=job.status,
        contest_format=job.contest_format,
        objective=job.objective,
        projection_run_id=job.projection_run_id,
        rule_run_id=job.rule_run_id,
        data_cutoff_at=job.data_cutoff_at,
        lineage_persisted=job.lineage_persisted,
        message=job.message,
        results=job.results,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.post("/simulations/run", response_model=SimulationRunResponse)
def run_slate_simulation(
    request: SimulationRunRequest,
    service: SimulationService = Depends(get_simulation_service),
) -> SimulationRunResponse:
    try:
        result = service.run(**request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SimulationRunResponse(**result.__dict__)


@router.get("/simulations/latest", response_model=SimulationRunResponse)
def get_latest_slate_simulation(
    season: int,
    week: int,
    slate: str,
    contest_format: str = "classic",
    projection_run_id: str | None = None,
    service: SimulationService = Depends(get_simulation_service),
) -> SimulationRunResponse:
    result = service.fetch_latest(
        season=season,
        week=week,
        slate=slate,
        contest_format=contest_format,
        projection_run_id=projection_run_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Slate simulation not found")
    return SimulationRunResponse(**result.__dict__)


@router.post(
    "/replay/classic-cash/stack-policies",
    response_model=ClassicCashStackReplayResponse,
)
def replay_classic_cash_stack_policies(
    request: ClassicCashStackReplayRequest,
    service: ClassicCashStackReplayService = Depends(
        get_classic_cash_stack_replay_service
    ),
) -> ClassicCashStackReplayResponse:
    try:
        report = service.run(
            season=request.season,
            week=request.week,
            slate=request.slate,
            projection_run_id=request.projection_run_id,
            policy_ids=tuple(request.policy_ids or DEFAULT_CASH_STACK_POLICY_IDS),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ClassicCashStackReplayResponse(**report)


@router.get("/optimizer/results/{job_id}", response_model=OptimizerStatusResponse)
def get_optimizer_results(
    job_id: str,
    service: OptimizerService = Depends(get_optimizer_service),
) -> OptimizerStatusResponse:
    job = service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return OptimizerStatusResponse(
        job_id=job.job_id,
        status=job.status,
        contest_format=job.contest_format,
        objective=job.objective,
        projection_run_id=job.projection_run_id,
        rule_run_id=job.rule_run_id,
        data_cutoff_at=job.data_cutoff_at,
        lineage_persisted=job.lineage_persisted,
        message=job.message,
        results=job.results,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.post("/news-monitor/run", response_model=NewsMonitorRunResponse)
def run_news_monitor(
    request: NewsMonitorRunRequest,
    service: NewsMonitorService = Depends(get_news_monitor_service),
) -> NewsMonitorRunResponse:
    result = service.run_daily(
        run_date=request.run_date,
        force=request.force,
        source_ids=request.source_ids,
    )
    return NewsMonitorRunResponse(
        run_id=result.run_id,
        run_date=result.run_date,
        status=result.status,
        forced=result.forced,
        skipped=result.skipped,
        message=result.message,
        sources_checked=result.sources_checked,
        items_ingested=result.items_ingested,
        signals_extracted=result.signals_extracted,
        completed_at=result.completed_at,
        report=result.report,
    )


@router.get("/news-monitor/report/{run_date}", response_model=NewsMonitorRunResponse)
def get_news_monitor_report(
    run_date: str,
    service: NewsMonitorService = Depends(get_news_monitor_service),
) -> NewsMonitorRunResponse:
    try:
        target_date = pd.Timestamp(run_date).date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="run_date must be YYYY-MM-DD") from exc
    report = service.get_report(target_date)
    if report is None:
        raise HTTPException(status_code=404, detail=f"No completed news-monitor report found for {run_date}")
    return NewsMonitorRunResponse(**report)


@router.post("/news-monitor/manual-note", response_model=ManualNewsNoteResponse)
def add_news_monitor_manual_note(
    request: ManualNewsNoteRequest,
    service: NewsMonitorService = Depends(get_news_monitor_service),
) -> ManualNewsNoteResponse:
    result = service.add_manual_note(
        run_date=request.run_date,
        title=request.title,
        note_text=request.note_text,
        source_link=request.source_link,
    )
    return ManualNewsNoteResponse(**result)


@router.get("/news-monitor/feedback/{run_date}", response_model=NewsMonitorFeedbackListResponse)
def get_news_monitor_feedback(
    run_date: str,
    service: NewsMonitorService = Depends(get_news_monitor_service),
) -> NewsMonitorFeedbackListResponse:
    try:
        target_date = pd.Timestamp(run_date).date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="run_date must be YYYY-MM-DD") from exc
    rows = service.list_feedback(target_date)
    return NewsMonitorFeedbackListResponse(rows=rows)


@router.post("/news-monitor/feedback", response_model=NewsMonitorFeedbackResponse)
def upsert_news_monitor_feedback(
    request: NewsMonitorFeedbackUpsertRequest,
    service: NewsMonitorService = Depends(get_news_monitor_service),
) -> NewsMonitorFeedbackResponse:
    result = service.upsert_feedback(
        run_date=request.run_date,
        signal_key=request.signal_key,
        signal_type=request.signal_type,
        signal_text=request.signal_text,
        feedback_choice=request.feedback_choice,
        note_text=request.note_text,
        player_name=request.player_name,
        team=request.team,
        source_link=request.source_link,
    )
    return NewsMonitorFeedbackResponse(**result)


@router.post("/news-monitor/import-history", response_model=NewsMonitorRunResponse)
def import_news_monitor_history(
    request: NewsMonitorImportRequest,
    service: NewsMonitorService = Depends(get_news_monitor_service),
) -> NewsMonitorRunResponse:
    try:
        result = service.import_history(
            path=request.path,
            run_date=request.run_date,
            source_id=request.source_id,
            source_name=request.source_name,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return NewsMonitorRunResponse(
        run_id=result.run_id,
        run_date=result.run_date,
        status=result.status,
        forced=result.forced,
        skipped=result.skipped,
        message=result.message,
        sources_checked=result.sources_checked,
        items_ingested=result.items_ingested,
        signals_extracted=result.signals_extracted,
        completed_at=result.completed_at,
        report=result.report,
    )


@router.get("/meta/current")
def get_current_context(
    data_source: NFLDataSource = Depends(get_data_source),
) -> dict:
    try:
        context = data_source.get_current_context()
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "season": context.season,
        "week": context.week,
        "provider": data_source.provider.value,
    }


@router.post("/starters/qb", response_model=StartingQBResponse)
def derive_starting_qbs(
    request: StartingQBRequest,
    quality_service: DataQualityService = Depends(get_data_quality_service),
) -> StartingQBResponse:
    """Derive starting QBs from rosters/injuries and persist to starting_qbs."""
    service = StartingQBService()
    result = service.derive_starters(season=request.season, week=request.week, slate=request.slate)
    _record_load_quality(
        quality_service,
        trigger="starting_qb_load",
        season=request.season,
        week=request.week,
        slate=request.slate,
        summaries=[{"dataset": "starting_qbs", **result.__dict__}],
    )
    return StartingQBResponse(
        season=result.season,
        week=result.week,
        slate=result.slate,
        rows_written=result.rows_written,
        message=result.message,
        completed_at=result.completed_at,
    )


@router.post("/slate/starting-qbs", response_model=StartingQBResponse)
def load_starting_qbs(
    request: StartingQBRequest,
    service: StartingQBService = Depends(get_starting_qb_service),
    quality_service: DataQualityService = Depends(get_data_quality_service),
) -> StartingQBResponse:
    result = service.derive_starters(
        season=request.season,
        week=request.week,
        slate=request.slate,
    )
    _record_load_quality(
        quality_service,
        trigger="starting_qb_load",
        season=request.season,
        week=request.week,
        slate=request.slate,
        summaries=[{"dataset": "starting_qbs", **result.__dict__}],
    )
    return StartingQBResponse(
        season=result.season,
        week=result.week,
        slate=result.slate,
        rows_written=result.rows_written,
        message=result.message,
        completed_at=result.completed_at,
    )


@router.post("/utils/postgres/start", response_model=PostgresStartResponse)
def start_postgres() -> PostgresStartResponse:
    """
    Kick off the local start_postgres.sh helper to start a dev Postgres instance.
    """
    script_path = Path(__file__).resolve().parents[3] / "start_postgres.sh"
    if not script_path.exists():
        raise HTTPException(
            status_code=404,
            detail="start_postgres.sh not found in repo root.",
        )

    try:
        result = subprocess.run(
            ["/bin/bash", str(script_path)],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to execute start_postgres.sh: {exc}") from exc

    ok = result.returncode == 0
    message = "PostgreSQL started" if ok else "Failed to start PostgreSQL"
    return PostgresStartResponse(
        ok=ok,
        message=message,
        stdout=result.stdout.strip(),
        stderr=result.stderr.strip(),
    )
