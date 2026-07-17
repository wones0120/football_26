from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db_session
from ..schemas import (
    ActualTopLineupBuildRequest,
    ActualTopLineupBuildResponse,
    ActualTopLineupLearningRequest,
    ActualTopLineupLearningResponse,
    AutoDiscoverIngestRequest,
    AutoDiscoverIngestResponse,
    BenchmarkRunListResponse,
    BenchmarkSuiteRunRequest,
    BenchmarkSuiteRunResponse,
    BacktestRangeABRequest,
    BacktestRangeABResponse,
    BacktestWeekABResponse,
    BacktestWeekRequest,
    BacktestWeekResponse,
    CuratedSalarySliceResponse,
    HealthResponse,
    IngestRunListResponse,
    IngestResultResponse,
    InjuryIngestRequest,
    LineupLearningRequest,
    LineupLearningResponse,
    ModelDefaultsResponse,
    UltimateLineupRequest,
    UltimateLineupResponse,
    NflReadPyBootstrapRequest,
    NflReadPySeasonRequest,
    OptimalVsPredictedBacktestRequest,
    OptimalVsPredictedBacktestResponse,
    PlayerMasterResponse,
    PlayerMasterUpsertRequest,
    ResolveUnresolvedRequest,
    SalaryIngestRequest,
    SimulateWeekRequest,
    SimulateWeekResponse,
    SeasonCoverageResponse,
    UnresolvedListResponse,
    UnresolvedRowResponse,
    UnresolvedTriageResponse,
)
from ..services.benchmarks import (
    build_model_defaults_response,
    list_benchmark_runs,
    resolve_benchmark_artifact,
    run_benchmark_suite,
)
from ..services.ingest import IngestService
from ..services.lineup_learning import LineupLearningService
from ..services.simulation import SimulationService


router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        app_env=settings.app_env,
        timestamp=datetime.now(UTC),
    )


@router.get("/model/defaults", response_model=ModelDefaultsResponse)
def model_defaults() -> ModelDefaultsResponse:
    settings = get_settings()
    return ModelDefaultsResponse(**build_model_defaults_response(settings))


@router.get("/benchmarks/runs", response_model=BenchmarkRunListResponse)
def benchmark_runs(limit: int = Query(default=10, ge=1, le=50)) -> BenchmarkRunListResponse:
    return BenchmarkRunListResponse(rows=[*list_benchmark_runs(limit=limit)])


@router.get("/benchmarks/runs/{run_name}/artifacts/{artifact_name}")
def benchmark_artifact(run_name: str, artifact_name: str) -> FileResponse:
    path = resolve_benchmark_artifact(run_name, artifact_name)
    if path is None:
        raise HTTPException(status_code=404, detail="Benchmark artifact not found")
    return FileResponse(path)


@router.post("/benchmarks/run-suite", response_model=BenchmarkSuiteRunResponse)
def benchmark_run_suite(request: BenchmarkSuiteRunRequest) -> BenchmarkSuiteRunResponse:
    settings = get_settings()
    request = request.model_copy(
        update={
            "showdown_captain_model_path": request.showdown_captain_model_path
            or settings.showdown_captain_model_path,
            "showdown_captain_prior_strength": request.showdown_captain_prior_strength
            if request.showdown_captain_prior_strength is not None
            else settings.showdown_captain_prior_strength,
        }
    )
    payload = run_benchmark_suite(request)
    return BenchmarkSuiteRunResponse(**payload)


@router.post("/ingest/salaries", response_model=IngestResultResponse)
def ingest_salaries(
    request: SalaryIngestRequest,
    session: Session = Depends(get_db_session),
) -> IngestResultResponse:
    service = IngestService(session)
    result = service.ingest_salaries(request)
    if result.status == "failed":
        raise HTTPException(status_code=422, detail=result.error_message or "Salary ingest failed")
    return result


@router.post("/ingest/injuries", response_model=IngestResultResponse)
def ingest_injuries(
    request: InjuryIngestRequest,
    session: Session = Depends(get_db_session),
) -> IngestResultResponse:
    service = IngestService(session)
    result = service.ingest_injuries(request)
    if result.status == "failed":
        raise HTTPException(status_code=422, detail=result.error_message or "Injury ingest failed")
    return result


@router.post("/ingest/auto-discover/salaries", response_model=AutoDiscoverIngestResponse)
def auto_discover_salaries(
    request: AutoDiscoverIngestRequest,
    session: Session = Depends(get_db_session),
) -> AutoDiscoverIngestResponse:
    service = IngestService(session)
    return service.ingest_discovered_files(request, source_table="salary")


@router.post("/ingest/auto-discover/injuries", response_model=AutoDiscoverIngestResponse)
def auto_discover_injuries(
    request: AutoDiscoverIngestRequest,
    session: Session = Depends(get_db_session),
) -> AutoDiscoverIngestResponse:
    service = IngestService(session)
    return service.ingest_discovered_files(request, source_table="injury")


@router.post("/ingest/nflreadpy/bootstrap", response_model=IngestResultResponse)
def bootstrap_nflreadpy(
    request: NflReadPyBootstrapRequest,
    session: Session = Depends(get_db_session),
) -> IngestResultResponse:
    service = IngestService(session)
    result = service.bootstrap_nflreadpy(request)
    if result.status == "failed":
        raise HTTPException(status_code=422, detail=result.error_message or "nflreadpy bootstrap failed")
    return result


@router.post("/ingest/nflreadpy/schedules", response_model=IngestResultResponse)
def ingest_nflreadpy_schedules(
    request: NflReadPySeasonRequest,
    session: Session = Depends(get_db_session),
) -> IngestResultResponse:
    service = IngestService(session)
    result = service.ingest_nflreadpy_schedules(request)
    if result.status == "failed":
        raise HTTPException(status_code=422, detail=result.error_message or "nflreadpy schedule ingest failed")
    return result


@router.post("/ingest/nflreadpy/weekly-stats", response_model=IngestResultResponse)
def ingest_nflreadpy_weekly_stats(
    request: NflReadPySeasonRequest,
    session: Session = Depends(get_db_session),
) -> IngestResultResponse:
    service = IngestService(session)
    result = service.ingest_nflreadpy_weekly_stats(request)
    if result.status == "failed":
        raise HTTPException(status_code=422, detail=result.error_message or "nflreadpy weekly stats ingest failed")
    return result


@router.get("/ingest/runs", response_model=IngestRunListResponse)
def list_ingest_runs(
    limit: int = Query(default=50, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> IngestRunListResponse:
    service = IngestService(session)
    return IngestRunListResponse(rows=service.list_runs(limit=limit))


@router.get("/coverage/season", response_model=SeasonCoverageResponse)
def season_coverage(session: Session = Depends(get_db_session)) -> SeasonCoverageResponse:
    service = IngestService(session)
    return SeasonCoverageResponse(rows=service.list_season_coverage())


@router.get("/coverage/curated-salary-slices", response_model=CuratedSalarySliceResponse)
def curated_salary_slices(
    season: int | None = Query(default=None, ge=2000),
    source_system: str | None = Query(default=None),
    limit: int = Query(default=2000, ge=1, le=10000),
    session: Session = Depends(get_db_session),
) -> CuratedSalarySliceResponse:
    service = IngestService(session)
    return CuratedSalarySliceResponse(
        rows=service.list_curated_salary_slices(
            season=season,
            source_system=source_system,
            limit=limit,
        )
    )


@router.post("/simulate/week", response_model=SimulateWeekResponse)
def simulate_week(
    request: SimulateWeekRequest,
    session: Session = Depends(get_db_session),
) -> SimulateWeekResponse:
    service = SimulationService(session)
    result = service.simulate_week(request)
    if result.status == "failed":
        raise HTTPException(status_code=422, detail=result.error_message or "simulation failed")
    return result


@router.post("/simulate/backtest-week", response_model=BacktestWeekResponse)
def simulate_backtest_week(
    request: BacktestWeekRequest,
    session: Session = Depends(get_db_session),
) -> BacktestWeekResponse:
    service = SimulationService(session)
    try:
        return service.backtest_week(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/simulate/backtest-week-ab", response_model=BacktestWeekABResponse)
def simulate_backtest_week_ab(
    request: BacktestWeekRequest,
    session: Session = Depends(get_db_session),
) -> BacktestWeekABResponse:
    service = SimulationService(session)
    try:
        return service.backtest_week_ab(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/simulate/backtest-range-ab", response_model=BacktestRangeABResponse)
def simulate_backtest_range_ab(
    request: BacktestRangeABRequest,
    session: Session = Depends(get_db_session),
) -> BacktestRangeABResponse:
    service = SimulationService(session)
    try:
        return service.backtest_range_ab(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/lineups/learn-walk-forward", response_model=LineupLearningResponse)
def lineups_learn_walk_forward(
    request: LineupLearningRequest,
    session: Session = Depends(get_db_session),
) -> LineupLearningResponse:
    service = LineupLearningService(session)
    try:
        return service.run_walk_forward_learning(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/lineups/actual-top/build", response_model=ActualTopLineupBuildResponse)
def lineups_build_actual_top(
    request: ActualTopLineupBuildRequest,
    session: Session = Depends(get_db_session),
) -> ActualTopLineupBuildResponse:
    service = LineupLearningService(session)
    try:
        return service.build_actual_top_lineups(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/lineups/actual-top/learn", response_model=ActualTopLineupLearningResponse)
def lineups_learn_from_actual_top(
    request: ActualTopLineupLearningRequest,
    session: Session = Depends(get_db_session),
) -> ActualTopLineupLearningResponse:
    service = LineupLearningService(session)
    try:
        return service.run_actual_top_lineup_learning(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/lineups/ultimate", response_model=UltimateLineupResponse)
def lineups_generate_ultimate(
    request: UltimateLineupRequest,
    session: Session = Depends(get_db_session),
) -> UltimateLineupResponse:
    service = LineupLearningService(session)
    try:
        return service.build_ultimate_lineups(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/lineups/optimal-vs-predicted", response_model=OptimalVsPredictedBacktestResponse)
def lineups_optimal_vs_predicted(
    request: OptimalVsPredictedBacktestRequest,
    session: Session = Depends(get_db_session),
) -> OptimalVsPredictedBacktestResponse:
    service = LineupLearningService(session)
    try:
        return service.run_optimal_vs_predicted_backtest(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/unresolved", response_model=UnresolvedListResponse)
def list_unresolved(
    status: str = Query(default="open"),
    source_system: str | None = Query(default=None),
    season: int | None = Query(default=None),
    week: int | None = Query(default=None),
    slate: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=5000),
    session: Session = Depends(get_db_session),
) -> UnresolvedListResponse:
    service = IngestService(session)
    rows = service.list_unresolved(
        status=status,
        source_system=source_system,
        season=season,
        week=week,
        slate=slate,
        limit=limit,
    )
    return UnresolvedListResponse(rows=rows)


@router.get("/unresolved/triage", response_model=UnresolvedTriageResponse)
def unresolved_triage(
    lookback_hours: int = Query(default=24, ge=1, le=8760),
    source_system: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
    session: Session = Depends(get_db_session),
) -> UnresolvedTriageResponse:
    service = IngestService(session)
    return service.unresolved_triage(
        lookback_hours=lookback_hours,
        source_system=source_system,
        limit=limit,
    )


@router.post("/unresolved/{unresolved_id}/resolve", response_model=UnresolvedRowResponse)
def resolve_unresolved(
    unresolved_id: str,
    request: ResolveUnresolvedRequest,
    session: Session = Depends(get_db_session),
) -> UnresolvedRowResponse:
    service = IngestService(session)
    try:
        return service.resolve_unresolved(unresolved_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/player-master/upsert", response_model=PlayerMasterResponse)
def upsert_player_master(
    request: PlayerMasterUpsertRequest,
    session: Session = Depends(get_db_session),
) -> PlayerMasterResponse:
    service = IngestService(session)
    return service.upsert_player_master(request)
