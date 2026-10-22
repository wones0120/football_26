"""App preparation adapter: established collectors, pipeline, and durable lineage.

No optimizer is invoked here. Weather is retained as evidence only: the current
projection feature contract does not consume it.
"""
from __future__ import annotations

import errno
import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from uuid import NAMESPACE_URL, uuid4, uuid5

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select, text
from sqlalchemy.orm import load_only
from ..injury_scope import injury_slate_sql, injury_subset_membership_sql

from ..config import get_settings
from ..models import CuratedSalary, OperationalJob, RawNflSchedule, SourceSnapshot
from ..services.historical_weather import schedule_kickoff_at
from ..services.job_queue import PermanentJobError
from ..services.slate_weather import SlateWeatherService
from .market_snapshots import canonical_team
from .pregame_context import load_current_pregame_context

PREPARATION_JOB = "slate_preparation"
ROOT = Path(__file__).resolve().parents[3]


class SlatePreparationRequest(BaseModel):
    season: int = Field(ge=2000)
    week: int = Field(ge=1, le=25)
    slate: str = Field(min_length=1, max_length=64)
    action: Literal["salary", "injuries", "markets", "weather", "rebuild", "prepare"]
    contest_format: Literal["classic", "showdown"] = "classic"
    ownership_required: bool = False
    preliminary_research: bool = False
    path: str | None = None
    injury_source: Literal["draftkings", "fanduel"] = "fanduel"
    native_draft_group: str | None = None
    allow_free_weather_evaluation: bool = False
    # The ordinary prediction schema validates these scenario choices below.
    availability_overrides: list[dict] = Field(default_factory=list, max_length=50)
    assume_questionable_out: bool = False
    minimum_player_salary: int | None = Field(default=None, ge=0, le=50000, strict=True)
    include_workload_forecast: bool = False
    learned_opportunities: bool = False
    opportunity_yards: bool = False
    scenario_first_captain: bool = False
    scenario_mode: dict | None = None
    reuse_prepared_input_job_id: str | None = Field(default=None, pattern=r"^[0-9a-f-]{36}$")
    analyst_mode: Literal["AUTO", "MANUAL", "BASELINE"] = "AUTO"
    analyst_packet_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    analyst_strategy: Literal["MERGED_SCENARIOS", "CONSTRUCTION"] = "MERGED_SCENARIOS"

    @model_validator(mode="after")
    def validate_preliminary_scope(self):
        from .optimizer_scenario_mode import config
        self.scenario_mode=config(self.scenario_mode)
        if self.scenario_first_captain:
            self.opportunity_yards=True
        if self.opportunity_yards:
            self.learned_opportunities=True
        if self.learned_opportunities:
            if self.action!='prepare' or self.contest_format!='showdown' or self.scenario_mode or self.preliminary_research or self.reuse_prepared_input_job_id:
                raise ValueError('Learned opportunities require normal Showdown Prepare without another scenario mode')
            self.include_workload_forecast=True
        if self.scenario_mode:
            if self.action!='prepare' or self.preliminary_research or self.reuse_prepared_input_job_id:
                raise ValueError('Scenario mode requires normal Prepare')
            self.include_workload_forecast=True
        if self.reuse_prepared_input_job_id and (self.action != "prepare" or self.preliminary_research):
            raise ValueError("Research recheck requires normal preparation")
        if self.preliminary_research and (self.contest_format != "classic" or self.action not in {"prepare", "rebuild"}
                or self.availability_overrides or self.assume_questionable_out):
            raise ValueError("Preliminary research requires Classic preparation without availability overrides")
        return self


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str,
                                     separators=(",", ":")).encode()).hexdigest()


def aware(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def scope(request):
    return {"season": request.season, "week": request.week, "slate": request.slate}


def same_scope(payload, request):
    return (payload.get("season"), payload.get("week"), str(payload.get("slate", "")).lower()) == (
        request.season, request.week, request.slate.lower())


def slate_games(session, request, salaries=None):
    salaries = salaries if salaries is not None else list(session.scalars(select(CuratedSalary).where(
        CuratedSalary.season == request.season, CuratedSalary.week == request.week,
        func.lower(CuratedSalary.slate) == request.slate.lower(),
        CuratedSalary.source_system == "draftkings")))
    if not salaries:
        raise ValueError("Load the correct DraftKings salary CSV for this season/week/slate first.")
    pairs = {frozenset((canonical_team(r.team or ""), canonical_team(r.opponent or ""))) for r in salaries}
    schedules = list(session.scalars(select(RawNflSchedule).where(
        RawNflSchedule.season == request.season, RawNflSchedule.week == request.week,
        RawNflSchedule.source_system == "nflreadpy").order_by(
            RawNflSchedule.created_at, RawNflSchedule.raw_nfl_schedule_id)))
    latest = {r.game_id: r for r in schedules if r.game_id}
    games = []
    for pair in pairs:
        matches = [r for r in latest.values() if frozenset((canonical_team(r.home_team), canonical_team(r.away_team))) == pair]
        if len(matches) != 1 or schedule_kickoff_at(matches[0]) is None:
            raise ValueError("Salary games do not uniquely match the canonical schedule with kickoff times. Load/review schedules.")
        r = matches[0]
        games.append({"game_id": r.game_id, "home_team": r.home_team, "away_team": r.away_team,
                      "kickoff_at": schedule_kickoff_at(r).isoformat()})
    return sorted(games, key=lambda r: r["game_id"])


def require_prelock(games, now=None):
    now = now or datetime.now(UTC)
    lock = min(aware(r["kickoff_at"]) for r in games)
    if now >= lock:
        raise ValueError(f"Slate lock has passed ({lock.isoformat()}); this pregame preparation path is blocked. Use the existing late-swap workflow for locked entries.")
    return lock


def source_manifest(session, request, cutoff=None):
    """Row IDs/content and original source clocks, not a synthetic refresh date."""
    cutoff = cutoff or datetime.now(UTC)
    params = {**scope(request), "cutoff": cutoff}
    def rows(sql):
        return [dict(r) for r in session.execute(text(sql), params).mappings()]

    salaries = rows("""
        SELECT s.*, r.source_checksum, r.source_path, r.started_at AS imported_at,
               r.completed_at, r.status AS ingest_status, r.rows_unresolved,
               evidence.snapshot_id, evidence.observed_at AS source_observed_at,
               evidence.captured_at, evidence.observation_basis, evidence.metadata_json
        FROM public.curated_salary s JOIN public.ingest_run r USING (ingest_run_id)
        LEFT JOIN public.source_snapshot_ingest_run link ON link.ingest_run_id=r.ingest_run_id
        LEFT JOIN public.source_snapshot evidence ON evidence.snapshot_id=link.snapshot_id
        WHERE s.season=:season AND s.week=:week AND LOWER(s.slate)=LOWER(:slate)
          AND s.source_system='draftkings' ORDER BY s.curated_salary_id
    """)
    injuries = rows(f"""
        SELECT i.*, r.source_checksum, r.source_path, r.started_at AS imported_at,
               r.status AS ingest_status, r.rows_unresolved
        FROM public.curated_injury i JOIN public.ingest_run r USING (ingest_run_id)
        WHERE i.season=:season AND i.week=:week AND {injury_slate_sql('i.slate')}
          AND {injury_subset_membership_sql('i.player_master_id', 'i.team')}
        ORDER BY i.curated_injury_id
    """)
    starters = rows("""
        SELECT * FROM public.starting_qb_evidence WHERE season=:season AND week=:week
          AND LOWER(slate)=LOWER(:slate) ORDER BY starting_qb_id
    """)
    context = load_current_pregame_context(session, **scope(request), cutoff=cutoff)
    games = slate_games(session, request)
    game_ids = {g["game_id"] for g in games}
    markets = rows("""
        SELECT DISTINCT ON (m.game_id) m.*, s.content_sha256, s.observation_basis,
               s.captured_at, s.artifact_path, s.source_uri
        FROM target.market_snapshot m JOIN public.source_snapshot s
          ON s.snapshot_id=m.source_snapshot_id
        JOIN public.ingest_run r ON r.ingest_run_id=m.ingest_run_id
        WHERE m.season=:season AND m.week=:week AND r.status='completed'
          AND m.observed_at<=:cutoff AND m.ingested_at<=:cutoff
        ORDER BY m.game_id, m.observed_at DESC, m.market_snapshot_id DESC
    """)
    markets = [r for r in markets if r["game_id"] in game_ids]
    # Include schedule identity/lock in the hash to detect an incompatible scope.
    manifest = {"scope": scope(request), "games": games, "salaries": salaries,
                "injuries": injuries, "starters": starters, "availability": context, "markets": markets}
    from .opportunity_source_publication import prepared_context
    # Salary actors precede all user eligibility/exposure preferences. Historical
    # team denominators and excluded actors are never reassigned to survivors.
    manifest["opportunity_source"] = prepared_context(session, season=request.season,week=request.week,
        teams=sorted({canonical_team(str(t)) for g in games for t in (g.get("teams") or [g.get("home_team"),g.get("away_team")]) if t}),
        actor_ids=sorted({str(s["player_master_id"]) for s in salaries if s.get("player_master_id")}),cutoff=cutoff)
    return json.loads(json.dumps(manifest, default=str))


def capture_source(request, games):
    lock = require_prelock(games)
    args = [sys.executable, str(ROOT / "scripts" / (
        "capture_nflverse_markets.py" if request.action == "markets" else "capture_current_weather_forecasts.py")),
        "--season", str(request.season), "--week", str(request.week), "--slate", request.slate]
    if request.action == "markets":
        args += ["--provider", "espn"]
    if request.action == "weather":
        args += ["--slate-lock-at", lock.isoformat(), "--apply", "--verify-artifacts"]
        for game in games:
            args += ["--game-id", game["game_id"]]
        if request.allow_free_weather_evaluation:
            args += ["--allow-free-evaluation"]
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=900)
    if result.returncode:
        raise PermanentJobError(f"{request.action} capture failed: {result.stderr[-4000:]} {result.stdout[-4000:]}")
    return json.loads(result.stdout)


def import_file(session, request):
    from types import SimpleNamespace
    import pandas as pd
    from ..schemas import InjuryIngestRequest, SalaryIngestRequest
    from ..services.ingest import IngestService
    from ..services.source_capture import SourceCaptureService

    if not request.path:
        raise ValueError("Enter the local source CSV path.")
    source = "draftkings" if request.action == "salary" else request.injury_source
    service = IngestService(session)
    if request.action == "salary":
        if not request.native_draft_group or not request.native_draft_group.strip():
            raise ValueError("Confirm the native DraftKings draft-group ID for this file.")
        normalized = service._normalize_salary_rows(source, pd.read_csv(Path(request.path).expanduser()))
        games = slate_games(session, request, [SimpleNamespace(**r) for r in normalized])
    else:
        games = slate_games(session, request)
    lock = require_prelock(games)
    capture_service = SourceCaptureService(session)
    capture = capture_service.capture_file(request.path, source_system=source,
        dataset="salary" if request.action == "salary" else "injury",
        **scope(request), slate_lock_at=lock, source_license="Operator-supplied file; upstream terms apply",
        metadata={"native_draft_group": request.native_draft_group, "publication_time": None,
                  "capture_mode": "manual_file_import"})
    if capture.pre_lock is not True:
        raise ValueError("File captured after slate lock; pregame import blocked.")
    schema = SalaryIngestRequest if request.action == "salary" else InjuryIngestRequest
    ingest_request = schema(source_system=source, **scope(request), path=capture.snapshot.artifact_path)
    run_id = str(uuid5(NAMESPACE_URL, f"slate-preparation/{capture.snapshot.snapshot_id}"))
    result = (service.ingest_salaries if request.action == "salary" else service.ingest_injuries)(
        ingest_request, ingest_run_id=run_id)
    capture_service.link_ingest_run(capture.snapshot.snapshot_id, result.ingest_run_id)
    if result.status != "completed":
        raise ValueError(result.error_message or "File ingest failed. Review unresolved identities.")
    return {"ingest": result.model_dump(mode="json"), "snapshot_id": capture.snapshot.snapshot_id,
            "source_sha256": capture.snapshot.content_sha256,
            "captured_at": capture.snapshot.captured_at.isoformat(), "publication_time": None,
            "native_draft_group": request.native_draft_group}


def verify_consumption(manifest, feature_rows, source_versions):
    """Compare the actual immutable scoring frame with the intended sources."""
    salary_ids = {int(r["curated_salary_id"]) for r in manifest["salaries"]}
    used_salaries = {int(i) for i in source_versions.get("salary_row_ids", [])}
    if not used_salaries or not used_salaries <= salary_ids:
        raise ValueError("Projection salary lineage is missing or refers to another input set.")
    markets = {r["game_id"]: str(r["market_snapshot_id"]) for r in manifest["markets"]}
    contexts = {str(r["player_master_id"]): str(r["pregame_player_context_id"]) for r in manifest["availability"]}
    verified_market, verified_context, verified_starter = set(), set(), set()
    for row in feature_rows:
        feature = row["feature_json"]
        expected_market = markets.get(row["game_id"])
        if expected_market:
            if str(feature.get("market_snapshot_row_id")) != expected_market:
                raise ValueError(f"New market evidence was not consumed for {row['game_id']}.")
            verified_market.add(expected_market)
        expected_context = contexts.get(str(row["player_id"]))
        if expected_context:
            if str(feature.get("pregame_context_row_id")) != expected_context:
                raise ValueError(f"Availability evidence was not consumed for {row['player_id']}.")
            verified_context.add(expected_context)
        starter_id = feature.get("team_starting_qb_player_id")
        if starter_id:
            verified_starter.add(str(starter_id))
    if not feature_rows or set(markets.values()) - verified_market:
        raise ValueError("Feature lineage does not cover every captured slate market.")
    expected_starters = {str(r["player_master_id"]) for r in manifest["starters"]}
    if expected_starters - verified_starter:
        raise ValueError("Starting-QB evidence was not consumed by the scoring features.")
    return {"salary_row_ids": sorted(used_salaries), "market_snapshot_ids": sorted(verified_market),
            "availability_row_ids": sorted(verified_context), "starter_player_ids": sorted(verified_starter),
            "weather_consumed": False, "injury_csv_consumed": False,
            "limitation": "Injury CSV import is evidence only; canonical projections consume sourced pregame context. Weather is not in the projection feature contract."}


def verify_artifacts(manifest, session=None):
    storage_replicas = []
    checked = set()

    def verify_file(path_value, checksum, snapshot_id, error):
        key = (path_value, checksum, snapshot_id)
        if key in checked:
            return
        path = Path(path_value or "")
        try:
            valid = path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == checksum
        except OSError as exc:
            if exc.errno not in {errno.EPERM, errno.EACCES, errno.EDEADLK}:
                raise
            from ..services.source_capture import SnapshotIntegrityError, verify_local_snapshot_replica
            snapshot = session.get(SourceSnapshot, snapshot_id) if session and snapshot_id else None
            if (not snapshot or snapshot.artifact_path != str(path)
                    or snapshot.content_sha256 != checksum):
                raise ValueError("Preparation cannot read the saved source file. Restore worker access "
                                 "or provision a verified local copy of this exact snapshot.") from exc
            try:
                replica = verify_local_snapshot_replica(snapshot)
            except (OSError, SnapshotIntegrityError) as replica_error:
                raise ValueError("Preparation cannot read the saved source file and no valid local "
                                 "copy is available. Restore worker access or provision a verified "
                                 "local copy of this exact snapshot.") from replica_error
            storage_replicas.append({"snapshot_id": snapshot.snapshot_id,
                                     "original_artifact_path": snapshot.artifact_path,
                                     "verified_artifact_path": replica.artifact_path,
                                     "content_sha256": snapshot.content_sha256})
            valid = True
        if not valid:
            raise ValueError(error)
        checked.add(key)

    for row in manifest["markets"]:
        verify_file(row["artifact_path"], row["content_sha256"], row.get("source_snapshot_id"),
                    "Market source artifact missing or checksum mismatch; recapture source evidence.")
    for row in manifest["salaries"]:
        if row["ingest_status"] != "completed" or not row["source_checksum"]:
            raise ValueError("Salary ingest is incomplete or lacks a source checksum. Reload the correct CSV.")
        verify_file(row["source_path"], row["source_checksum"], row.get("snapshot_id"),
                    "Salary source artifact missing or checksum mismatch. Reload the correct CSV.")
    if len({r.get("ingest_run_id") for r in manifest["salaries"]}) > 1:
        raise ValueError("Salary scope contains rows from multiple imports. The canonical loader would mix files; resolve the salary scope with the complete correct DraftKings CSV before rebuilding.")
    return storage_replicas


def preparation_jobs(session, request):
    # History/status checks need metadata, not every saved multi-megabyte audit.
    return list(session.scalars(select(OperationalJob).where(
        OperationalJob.job_type == PREPARATION_JOB,
        OperationalJob.request_json['season'].as_integer() == request.season,
        OperationalJob.request_json['week'].as_integer() == request.week,
        func.lower(OperationalJob.request_json['slate'].as_string()) == request.slate.lower(),
    ).options(load_only(OperationalJob.job_id, OperationalJob.request_json, OperationalJob.status,
        OperationalJob.stage, OperationalJob.progress_message, OperationalJob.error_message,
        OperationalJob.created_at, OperationalJob.completed_at)).order_by(OperationalJob.created_at.desc())))


def preparation_summary(result):
    if not result:
        return result
    summary = {k: v for k, v in result.items() if k not in {
        'source_manifest', 'source_refresh', 'data_readiness', 'calibration_metrics'}}
    # Handoffs retain their compatibility IDs and user-facing findings. The
    # complete dependency snapshot/candidate pool belongs to the saved audit,
    # not every status refresh. Selection still reads the original result_json.
    from .browser_payloads import readiness_summary
    if result.get('analyst_handoff'):
        summary['analyst_handoff']=readiness_summary(result['analyst_handoff'],
            omit=('research_dependency_snapshot','selection_candidates'))
    if result.get('analyst_intent_handoffs'):
        summary['analyst_intent_handoffs']={intent:readiness_summary(handoff,
            omit=('research_dependency_snapshot','selection_candidates'))
            for intent,handoff in result['analyst_intent_handoffs'].items()}
    if 'data_readiness' in result:
        summary['data_readiness'] = {k: v for k, v in result['data_readiness'].items()
            if k in {'status', 'reason_codes'}}
    if 'source_refresh' in result:
        summary['source_refresh'] = {k: {field: v[field] for field in ('status', 'reason') if field in v}
            for k, v in result['source_refresh'].items() if isinstance(v, dict)}
    # Status is a display projection, not another copy of the immutable audit.
    # Selection/validation still reads the original persisted result_json.
    if result.get('workload_forecast'):
        forecast = result['workload_forecast']
        summary['workload_forecast'] = {k: forecast[k] for k in (
            'sha256', 'version', 'source_cutoff_at', 'domain', 'learned_opportunities',
            'scales', 'normalization_policy', 'yardage_model') if k in forecast}
        if forecast.get('yardage_model'):
            summary['workload_forecast']['yardage_model']={k:v for k,v in forecast['yardage_model'].items()
                if k in {'version','selection_weights','method','prior_attempts','limitations','accounting','validation','status'}}
        if forecast.get('scenario_first'):
            summary['workload_forecast']['scenario_first']={k:v for k,v in forecast['scenario_first'].items()
                if k in {'version','seed','market','implied_points','construction_policy','selection_policy','world_count','assumptions','likelihood','historical_complete_team_games'}}
        if forecast.get('learned_model_consumption'):
            learned=forecast['learned_model_consumption']
            summary['workload_forecast']['learned_model_consumption']={
                family:{k:v for k,v in learned[family].items() if k in {'model_publication_record_id','model_refs'}}
                for family in ('team','player')}
        summary['workload_forecast']['players'] = [
            {k: p[k] for k in ('player_master_id', 'name', 'native_id', 'native_salary_actor',
                'position', 'utility', 'counts', 'reasons', 'projected_yards', 'efficiency', 'receiving_team_reconciliation_factor', 'scenario_role_evidence') if k in p}
            for p in forecast.get('players', [])]
    if result.get('scenario_mode'):
        scenario = result['scenario_mode']
        summary['scenario_mode'] = {k: scenario[k] for k in (
            'version', 'sha256', 'config', 'status', 'issue', 'changed_player_count',
            'limitations', 'scoring_basis', 'new_model_primary', 'full_game_simulator_consumed') if k in scenario}
        summary['scenario_mode']['players'] = [
            {k: p[k] for k in ('player_master_id', 'name', 'team', 'baseline_mean',
                'conditional_mean', 'delta', 'supported_components', 'missing_evidence') if k in p}
            for p in scenario.get('players', [])]
        primary = scenario.get('primary_model_forecast')
        if primary:
            compact = {k: primary[k] for k in ('version', 'source', 'physical_count_budgets',
                'dst_expert', 'all_player_audit', 'limitations') if k in primary}
            if primary.get('all_player_audit'):
                compact['all_player_audit'] = {k: v for k, v in primary['all_player_audit'].items()
                    if k != 'players'}
            for field in ('team_model_consumption', 'player_model_consumption'):
                compact[field] = {k: v for k, v in primary.get(field, {}).items()
                    if k in {'model_publication_record_id', 'model_refs'}}
            compact['scoring_head'] = {k: v for k, v in primary.get('scoring_head', {}).items()
                if k in {'version', 'feature_columns'}}
            summary['scenario_mode']['primary_model_forecast'] = compact
    return summary


def preparation_input_summary(manifest):
    """Keep source IDs/statuses/clocks without repeating nested context audits."""
    summary = dict(manifest)
    for dataset in ('availability', 'starters'):
        summary[dataset] = []
        for row in manifest.get(dataset, []):
            compact = {k: v for k, v in row.items() if k != 'evidence_json'}
            evidence = row.get('evidence_json') or {}
            compact['evidence_json'] = {k: evidence[k] for k in (
                'canonical_context_contract', 'roster_status', 'canonical_role',
                'expected_depth_role', 'availability_state', 'availability_status',
                'binding_roster_unavailability', 'canonical_context_reason_codes',
                'practice_participation', 'expected_workload_status', 'observed_at') if k in evidence}
            resolution = evidence.get('designation_resolution')
            if resolution:
                compact['evidence_json']['designation_resolution'] = {
                    k: resolution[k] for k in ('contract', 'status', 'effective_designation',
                        'evaluated_at') if k in resolution}
            compact['evidence_detail_omitted'] = True
            summary[dataset].append(compact)
    return summary


def preparation_status(session, request):
    now = datetime.now(UTC)
    jobs = preparation_jobs(session, request)
    job_views = [
        {"job_id": j.job_id, "action": j.request_json["action"], "status": j.status,
         "stage": j.stage, "message": j.progress_message, "error": j.error_message,
         "result": {"audit_url": f"/api/jobs/{j.job_id}"} if j.status == 'completed' else None,
         "checkpoint": ({"preparation_result": preparation_summary(
             (j.checkpoint_json or {}).get('preparation_result'))} if j.status == 'failed' else None),
         "audit_url": f"/api/jobs/{j.job_id}",
         "completed_at": str(j.completed_at) if j.completed_at else None} for j in jobs[:10]]
    try:
        manifest = source_manifest(session, request, now)
    except ValueError as exc:
        # A failed first import must remain visible even without usable salaries.
        return {"server_time": now.isoformat(), "scope": scope(request), "inputs": {},
                "jobs": job_views, "latest_build": None, "build_current": False,
                "entry_ready": False, "limitations": [str(exc)]}
    source_hash = digest(manifest)
    weather = SlateWeatherService(session, stale_after=timedelta(
        minutes=get_settings().weather_forecast_stale_after_minutes)).report(
            source_system="draftkings", **scope(request))
    from ..services.ingest import IngestService
    freshness = IngestService(session).get_data_freshness(source_system="draftkings", **scope(request))
    for r in manifest["markets"]:
        age = (now - aware(r["observed_at"])).total_seconds() / 3600
        r["freshness"] = "fresh" if age <= 6 else "aging" if age <= 24 else "stale"
        r["quote_publication_time"] = None
        r["quote_freshness"] = "unknown; capture_clock does not verify current sportsbook quotes"
    # Hash the source selection before adding transient display assessments.
    latest_build = next((j for j in jobs if j.request_json.get("action") in {"rebuild", "prepare"}), None)
    build = latest_build.result_json if latest_build and latest_build.status == "completed" else None
    current_build = bool(build and source_hash == build.get("source_sha256") and
                         not any(j.created_at > latest_build.created_at for j in jobs))
    build_issue = None
    if current_build and latest_build.request_json.get("action") == "prepare":
        try:
            validate_prepared_optimizer(session, {**scope(request),
                "contest_format": latest_build.request_json["contest_format"],
                "projection_run_id": build["projection_run_id"],
                "params": {"prepared_input_job_id": latest_build.job_id,
                           "minimum_player_salary": latest_build.request_json.get("minimum_player_salary"),
                           "scenario_mode": latest_build.request_json.get("scenario_mode"),
                           "availability_overrides": latest_build.request_json.get("availability_overrides", []),
                           "assume_questionable_out": latest_build.request_json.get("assume_questionable_out", False)}})
        except ValueError as exc:
            current_build = False
            build_issue = str(exc)
    consumed = (build or {}).get("consumption", {})
    keys = {"salaries": ("curated_salary_id", "salary_row_ids"),
            "markets": ("market_snapshot_id", "market_snapshot_ids"),
            "availability": ("pregame_player_context_id", "availability_row_ids"),
            "starters": ("player_master_id", "starter_player_ids")}
    for dataset, (row_key, consumed_key) in keys.items():
        ids = {str(v) for v in consumed.get(consumed_key, [])}
        for r in manifest[dataset]:
            r["consumed_by_latest_prepared_build"] = current_build and str(r[row_key]) in ids
            r["consumed_projection_run_id"] = build.get("projection_run_id") if r["consumed_by_latest_prepared_build"] else None
    for r in manifest["injuries"]:
        r["consumed_by_latest_prepared_build"] = False
    for r in manifest["starters"]:
        r["observed_at"] = (r.get("evidence_json") or {}).get("observed_at")
    return {"server_time": now.isoformat(), "scope": scope(request), "inputs": preparation_input_summary(manifest),
            "lock_at": min(aware(r["kickoff_at"]) for r in manifest["games"]).isoformat(),
            "prelock": all(now < aware(r["kickoff_at"]) for r in manifest["games"]),
            "weather": weather, "load_freshness": freshness.model_dump(mode="json"), "jobs": job_views,
            "latest_build": {**preparation_summary(latest_build.result_json),
                "prepared_input_job_id": latest_build.job_id, "audit_url": f"/api/jobs/{latest_build.job_id}"}
                if latest_build and latest_build.status == "completed" and latest_build.result_json else None,
            "build_current": current_build, "build_issue": build_issue,
            "entry_ready": False, "limitations": [
                "Official final availability clearance remains unverified. Practice, designation, starter evidence and workload are separate facts.",
                "Salary publication time/freshness policy unavailable; import time is not source publication time. Check the native DraftKings draft group.",
                "ESPN sportsbook retrieval (and legacy nflverse captures) has no upstream quote-publication time. Exact quote age remains unknown.",
                "Weather has venue/roof and forecast timing evidence, but is not consumed by projections. No scoring change is made."]}


def validate_prepared_optimizer(session, payload, *, verify_current=True):
    """Check saved preparation on enqueue; audit current sources on the worker."""
    job_id = (payload.get("params") or {}).get("prepared_input_job_id")
    from types import SimpleNamespace
    from .showdown_data_readiness import is_live_slate
    live_required = (payload.get("contest_format") == "showdown" or payload.get("strategy") in
        {"classic_large_gpp_v1", "classic_single_lineup_v1", "captain_single_lineup_v1"}) and is_live_slate(
            SimpleNamespace(engine=session.bind), season=payload["season"],
            week=payload["week"], slate=payload["slate"])
    if not job_id:
        if live_required:
            raise ValueError("Prepare slate for optimization first. Resolve source checks upstream before running the optimizer.")
        return
    job = session.get(OperationalJob, job_id)
    if not job or job.status != "completed" or job.request_json.get("action") not in {"rebuild", "prepare"}:
        raise ValueError("Preparation is missing, still running, or failed. Rebuild features and projections first.")
    request = SlatePreparationRequest.model_validate(job.request_json)
    if request.preliminary_research:
        raise ValueError("Preliminary preparations require the frozen preliminary research workflow; they cannot certify normal optimization")
    if live_required and request.action != "prepare":
        raise ValueError("Prepare slate for optimization first. A projection rebuild alone does not certify source readiness.")
    if not same_scope(payload, request):
        raise ValueError("Prepared inputs belong to another season/week/slate.")
    result = job.result_json or {}
    from .analyst_preparation import bind_handoff, handoff_for_intent
    if payload.get("strategy") or payload.get("objective") or (payload.get("params") or {}).get("analyst_handoff_mode"):
        bind_handoff(payload, result)
    if request.action == "prepare":
        if payload.get("contest_format") != request.contest_format:
            raise ValueError("Prepared inputs belong to another contest format. Prepare this slate first.")
        if (result.get("data_readiness") or {}).get("status") != "READY":
            raise ValueError("Slate preparation is not READY. Resolve its source checks first.")
    if payload.get("projection_run_id") != result.get("projection_run_id"):
        raise ValueError("Optimizer projection does not match the prepared input set.")
    expected_scenario = {"availability_overrides": request.availability_overrides,
                         "assume_questionable_out": request.assume_questionable_out}
    params = payload.get("params") or {}
    from .optimizer_scenario_mode import config as scenario_config, verify as verify_scenario
    if scenario_config(params.get("scenario_mode")) != request.scenario_mode:
        raise ValueError("Scenario changed; Prepare slate again")
    if request.scenario_mode:
        verify_scenario(result.get("scenario_mode"), request.scenario_mode, result["projection_run_id"])
    if request.contest_format == "showdown" and (params.get("minimum_player_salary") or 0) < (request.minimum_player_salary or 0):
        raise ValueError("Minimum player salary was lowered after preparation. Prepare slate again to verify the newly eligible players.")
    from ..product_schemas import PredictionRunRequest
    scenario = PredictionRunRequest(**scope(request), availability_overrides=params.get("availability_overrides", []))
    if digest(expected_scenario) != digest({"availability_overrides": [r.model_dump(mode="json") for r in scenario.availability_overrides],
                                          "assume_questionable_out": params.get("assume_questionable_out", False) if request.action == "prepare" or payload.get("contest_format") == "showdown" or payload.get("strategy") == "classic_single_lineup_v1" else params.get("exclude_questionable", False)}):
        raise ValueError("Availability scenario changed; rebuild projections using the current controls.")
    others = preparation_jobs(session, request)
    if any(j.job_id != job_id and same_scope(j.request_json, request) and
           (j.status in {"queued", "running"} or j.created_at > job.created_at) for j in others):
        raise ValueError("A newer preparation action exists. Review its status and rebuild before optimizing.")
    if not verify_current:
        # Do not hash files, scan features or assess live evidence before the
        # durable queue receipt. The worker must complete all of those checks
        # before generation; this path does not issue trusted source evidence.
        return None
    current = source_manifest(session, request)
    require_prelock(current["games"])
    verify_artifacts(current, session)
    if digest(current) != result.get("source_sha256"):
        raise ValueError("Source inputs changed after preparation. Rebuild features and projections.")
    if digest(result.get("source_manifest")) != result.get("source_sha256"):
        raise ValueError("Prepared source manifest checksum mismatch.")
    proof = projection_proof(session, result)
    if digest(proof) != result.get("projection_lineage_sha256"):
        raise ValueError("Prepared projection/feature lineage changed or is incomplete.")
    if request.action == "prepare":
        from .optimizer import OptimizerService
        service = OptimizerService()
        service.engine = session.bind
        from .showdown_data_readiness import requires_ownership
        readiness = assess_prepared_inputs(service, request.model_copy(update={
            "ownership_required": request.ownership_required or requires_ownership(params)}), result)
        if readiness["status"] != "READY":
            raise ValueError("Prepared evidence is no longer ready. Prepare slate again: " + ", ".join(readiness["reason_codes"]))
    if params.get("workload_comparison") and not result.get("workload_forecast"):
        raise ValueError("Prepare with explicit offensive workload forecasts before this comparison")
    return {"action": request.action, "ownership_run_id": result.get("ownership_run_id"),
            "workload_forecast": result.get("workload_forecast"),
            "scenario_mode": result.get("scenario_mode"),
            "data_cutoff_at": result.get("data_cutoff_at"), "source_refresh": result.get("source_refresh", {}),
            "prepared_input_job_id": job_id, "projection_run_id": result["projection_run_id"],
            "feature_run_id": result["feature_run_id"], "source_sha256": result["source_sha256"],
            "projection_lineage_sha256": result["projection_lineage_sha256"],
            "analyst_handoff": handoff_for_intent(result,params.get("analyst_optimization_intent","MIXED")),
            "analyst_intent_handoffs": result.get("analyst_intent_handoffs", {}),
            "consumption": result["consumption"], "limitations": result["limitations"],
            "games": result["source_manifest"]["games"],
            "native_draft_groups": sorted({str((r.get("metadata_json") or {}).get("native_draft_group"))
                for r in result["source_manifest"]["salaries"] if (r.get("metadata_json") or {}).get("native_draft_group")}),
            "market_clocks": [{k: r.get(k) for k in ("game_id", "source", "observed_at", "captured_at", "observation_basis", "content_sha256")}
                              for r in result["source_manifest"]["markets"]]}


def projection_proof(session, result):
    params = {"projection": result["projection_run_id"], "feature": result["feature_run_id"]}
    run = session.execute(text("""
        SELECT p.projection_run_id, p.model_run_id, p.season, p.week, p.slate_id, p.status,
               m.feature_run_id, f.source_versions_json
        FROM target.projection_run p JOIN target.model_run m USING (model_run_id)
        JOIN target.feature_generation_run f USING (feature_run_id)
        WHERE p.projection_run_id=:projection AND m.feature_run_id=:feature
    """), params).mappings().one()
    features = [dict(r) for r in session.execute(text("""
        SELECT game_id, player_id, feature_json FROM target.feature_player_game
        WHERE feature_run_id=:feature ORDER BY game_id, player_id
    """), params).mappings()]
    run = dict(run)
    if isinstance(run["source_versions_json"], str):
        run["source_versions_json"] = json.loads(run["source_versions_json"])
    for row in features:
        if isinstance(row["feature_json"], str):
            row["feature_json"] = json.loads(row["feature_json"])
    return {"run": run, "features": features}


def execute_preparation(context, payload, *, refresh_training_before_cutoff=False):
    from types import SimpleNamespace
    from ..db import SessionLocal
    from ..product_schemas import PredictionRunRequest
    from ..services.job_handlers import _feature_matrix_handler, _projection_handler
    request = SlatePreparationRequest.model_validate(payload)
    checkpoint = dict(context.checkpoint)
    try:
        if request.action == "prepare":
            return prepare_optimizer_inputs(context, request)
        if request.action in {"salary", "injuries"}:
            context.progress("import", 0, 1, "Importing immutable source file through canonical ingest.")
            with SessionLocal() as session:
                result = import_file(session, request)
            return {"action": request.action, "operation": "Imported source evidence", **scope(request), **result}
        with SessionLocal() as session:
            games = slate_games(session, request)
            require_prelock(games)
        if request.action in {"markets", "weather"}:
            context.progress("capture", 0, 1, f"Fetching new {request.action} source evidence.")
            result = capture_source(request, games)
            return {"action": request.action, "operation": "Fetched new source evidence", **scope(request),
                    "collector_result": result, "quote_publication_time": None,
                    "limitation": "Capture time is not provider publication time; weather is evidence only."}

        if not checkpoint.get("projection_run_id"):
            checkpoint.update({"projection_run_id": str(uuid4()), "feature_run_id": str(uuid4()),
                               "model_run_id": str(uuid4())})
            context.progress("dependencies", 0, 4, "Allocated new dependent build IDs.", checkpoint=checkpoint)
        # Explicit cutoff prevents the projection handler from fetching/deriving new
        # starters or automatically rebuilding historical labels behind this snapshot.
        with SessionLocal() as session:
            manifest = source_manifest(session, request)
            storage_replicas = verify_artifacts(manifest, session) or []
            require_prelock(manifest["games"])
        if checkpoint.get("source_sha256") and checkpoint["source_sha256"] != digest(manifest):
            raise ValueError("Inputs changed during an interrupted preparation. Start a new rebuild.")
        if not checkpoint.get("matrix_completed"):
            _feature_matrix_handler(context, {**scope(request), "weeks": [request.week]})
            checkpoint["matrix_completed"] = True
            context.progress("features", 1, 4, "Rebuilt features.", checkpoint=checkpoint)
        if refresh_training_before_cutoff and not checkpoint.get("data_cutoff_at"):
            # The label audit loads canonical inputs, including this slate's
            # features. Run it after those features exist and before freezing
            # the cutoff so prior-week repairs remain time-safe.
            from .showdown_data_readiness import refresh_training_labels
            context.progress("training_labels", 1, 4, "Verifying completed prior-week training labels.")
            with SessionLocal() as session:
                refresh_training_labels(session.get_bind(), **scope(request),
                    **({"preliminary_exclude_unknown": True} if request.preliminary_research else {}))
        cutoff = checkpoint.get("data_cutoff_at") or datetime.now(UTC).isoformat()
        checkpoint.update(source_sha256=digest(manifest), data_cutoff_at=cutoff)
        context.progress("projections", 2, 4, "Rebuilding projections from the frozen source selection.", checkpoint=checkpoint)
        prediction = PredictionRunRequest(**scope(request), data_cutoff_at=cutoff,
            availability_overrides=request.availability_overrides,
            assume_questionable_out=request.assume_questionable_out)

        def projection_progress(stage, current, total, message, **kwargs):
            context.progress(stage, current, total, message, checkpoint=checkpoint)
        child = SimpleNamespace(run_id=checkpoint["projection_run_id"], checkpoint=checkpoint,
                                progress=projection_progress)
        result = _projection_handler(child, prediction.model_dump(mode="json"),
            **({"preliminary_exclude_unknown": True} if request.preliminary_research else {}))
        if any(result.get(k) != checkpoint[k] for k in ("projection_run_id", "feature_run_id", "model_run_id")):
            raise ValueError("Dependent pipeline reused an older build. Start a new preparation.")
        with SessionLocal() as session:
            current = source_manifest(session, request)
            require_prelock(current["games"])
            if digest(current) != digest(manifest):
                raise ValueError("Source inputs changed during preparation; rebuild before the next solve.")
            proof = projection_proof(session, result)
            run = proof["run"]
            if (run["status"] != "completed" or not same_scope({**run, "slate": run["slate_id"]}, request)):
                raise ValueError("Dependent projection run is incomplete or belongs to another slate.")
            consumption = verify_consumption(manifest, proof["features"], run["source_versions_json"])
            # Annotate only this newly allocated feature run. Original saved builds
            # and optimizer readiness/history are never updated.
            lineage = {"source_sha256": digest(manifest), "source_manifest": manifest,
                       "verified_storage_replicas": storage_replicas,
                       "consumption": consumption, "prepared_at": datetime.now(UTC).isoformat()}
            session.execute(text("""
                UPDATE target.feature_generation_run SET source_versions_json =
                    source_versions_json || CAST(:lineage AS JSONB)
                WHERE feature_run_id=:feature
            """), {"feature": result["feature_run_id"], "lineage": json.dumps({"slate_preparation": lineage})})
            session.commit()
            proof = projection_proof(session, result)
        context.progress("verified", 4, 4, "Rebuilt projections; source-to-feature-to-projection lineage verified.", checkpoint=checkpoint)
        return {**result, **scope(request), "action": "rebuild", "operation": "Rebuilt features and projections",
                **lineage, "projection_lineage_sha256": digest(proof), "entry_ready": False,
                "limitations": ["Final availability clearance unverified", "Quote publication time unknown",
                                "Salary publication freshness unverified", "Weather not consumed by projections"]}
    except (ValueError, LookupError) as exc:
        raise PermanentJobError(str(exc)) from exc


def assess_prepared_inputs(service, request, result):
    """Read-only assessment of explicit prepared runs; never select a fallback."""
    from . import classic_data_readiness as classic
    from . import showdown_data_readiness as showdown
    from .optimizer import _json_safe
    from .kicker_roles import assign_kicker_roles
    from .player_roles import resolve_player_roles

    cutoff = aware(result["data_cutoff_at"])
    pool = service._load_player_pool(request.season, request.week, request.slate,
        projection_run_id=result["projection_run_id"], ownership_run_id=result.get("ownership_run_id"),
        evidence_cutoff_at=cutoff, require_explicit_runs=True)
    pool, _ = assign_kicker_roles(pool)
    pool, _ = resolve_player_roles(pool)
    arguments = dict(**scope(request), projection_run_id=result["projection_run_id"],
        evidence_cutoff=cutoff, evaluated_at=datetime.now(UTC),
        refresh=result.get("source_refresh", {}))
    if request.contest_format == "classic":
        evidence = classic.read_evidence(service, **scope(request),
            projection_run_id=result["projection_run_id"], cutoff=cutoff)
        return classic.evaluate_readiness(_json_safe(pool.to_dict("records")), **arguments,
            rules=classic.freshness_rules(get_settings()), evidence=_json_safe(evidence))
    contexts = {str(r.get("player_master_id")): r for r in pool.attrs.get("role_context", [])}
    pool["player_status_evidence_present"] = [bool(
        (context := contexts.get(str(row.get("player_id")), {})).get("source")
        and (context.get("injury_status") or (context.get("evidence_json") or {}).get("roster_status")
             or type((context.get("evidence_json") or {}).get("game_active")) is bool))
        for row in pool.to_dict("records")]
    return showdown.evaluate_readiness(_json_safe(pool.to_dict("records")), **arguments,
        rules=showdown.freshness_rules(get_settings()), ownership_required=request.ownership_required,
        ownership_attempted=True, require_canonical_context=True,
        minimum_player_salary=request.minimum_player_salary)


def recheck_saved_preparation(session, request, *, current_job_id):
    """Rebind research only after revalidating identical frozen numerical inputs."""
    parent = session.get(OperationalJob, request.reuse_prepared_input_job_id)
    if not parent or parent.status != "completed" or parent.request_json.get("action") != "prepare":
        raise ValueError("Research recheck requires a completed normal preparation")
    original = SlatePreparationRequest.model_validate(parent.request_json)
    excluded = {"reuse_prepared_input_job_id", "analyst_mode", "analyst_packet_sha256", "analyst_strategy"}
    if original.model_dump(exclude=excluded) != request.model_dump(exclude=excluded):
        raise ValueError("Research recheck cannot change scope, source or forecast settings")
    for job in preparation_jobs(session, request):
        if job.job_id not in {parent.job_id, current_job_id} and job.created_at > parent.created_at:
            raise ValueError("A newer preparation action exists; research recheck cannot skip it")
    result = deepcopy(parent.result_json or {})
    current = source_manifest(session, request)
    require_prelock(current["games"])
    verify_artifacts(current, session)
    if digest(current) != result.get("source_sha256") or digest(result.get("source_manifest")) != result.get("source_sha256"):
        raise ValueError("Source inputs changed; a full preparation is required")
    if digest(projection_proof(session, result)) != result.get("projection_lineage_sha256"):
        raise ValueError("Frozen projection lineage changed; a full preparation is required")
    if request.include_workload_forecast:
        receipt = result.get("workload_forecast") or {}
        if digest({k:v for k,v in receipt.items() if k != "sha256"}) != receipt.get("sha256"):
            raise ValueError("Frozen count receipt checksum mismatch")
    for field in ("analyst_handoff", "analyst_intent_handoffs"):
        result.pop(field, None)
    result["research_recheck"] = {"parent_prepared_input_job_id": parent.job_id,
        "checked_at": datetime.now(UTC).isoformat(), "numerical_inputs_reused": True,
        "projection_run_id": result["projection_run_id"], "source_sha256": result["source_sha256"],
        "forecast_sha256": (result.get("workload_forecast") or {}).get("sha256"),
        "source_capture_or_model_fit_performed": False}
    return result


def prepare_optimizer_inputs(context, request):
    """Own all repair/build work upstream; a blocked attempt retains its audit."""
    from .optimizer import OptimizerService, _json_safe
    from . import classic_data_readiness as classic
    from . import showdown_data_readiness as showdown

    if request.preliminary_research and (request.contest_format != "classic" or request.availability_overrides or request.assume_questionable_out):
        raise ValueError("Preliminary preparation requires Classic without projection availability overrides")
    service = OptimizerService()
    if request.reuse_prepared_input_job_id:
        from ..db import SessionLocal
        with SessionLocal() as session:
            result = recheck_saved_preparation(session, request, current_job_id=context.job_id)
    else:
        gate = classic if request.contest_format == "classic" else showdown
        if request.learned_opportunities or (request.scenario_mode or {}).get('scoring_mode')=='new_model_primary':
            from .primary_model_source import ensure_source
            ensure_source(service.engine,**scope(request))
        refreshed = gate.refresh_live_sources(service, **scope(request),
            params={"availability_overrides": request.availability_overrides,
                    "assume_questionable_out": request.assume_questionable_out, "refresh_ownership": True,
                    "ownership_required": request.ownership_required, "preliminary_research": request.preliminary_research,
                    "include_workload_forecast": request.include_workload_forecast},
            progress=context.progress)
        build = (refreshed["report"].get("projection", {}).get("result") or {})
        result = {**build, **scope(request), "action": "prepare", "contest_format": request.contest_format,
                  "projection_run_id": refreshed["projection_run_id"],
                  "ownership_run_id": refreshed["ownership_run_id"],
                  "availability_overrides": request.availability_overrides,
                  "assume_questionable_out": request.assume_questionable_out,
                  "minimum_player_salary": request.minimum_player_salary,
                  "data_cutoff_at": aware(refreshed["data_cutoff_at"]).isoformat(),
                  "source_refresh": _json_safe(refreshed["report"]), "preliminary_research": request.preliminary_research}
        if request.include_workload_forecast:result["workload_participation_refresh"]=refreshed["report"].get("workload_participation")
    context.progress("source_checks", 0, 1, "Checking prepared inputs before optimization.",
                     checkpoint={"preparation_result": result})
    if not result["projection_run_id"]:
        reason = (refreshed["report"].get("projection", {}).get("reason", "No verified projection")
                  if not request.reuse_prepared_input_job_id else "No verified frozen projection")
        raise ValueError("Slate preparation blocked: " + str(reason))
    readiness = assess_prepared_inputs(service, request, result)
    result["data_readiness"] = readiness
    result["opportunity_source_context"] = result.get("source_manifest", {}).get("opportunity_source")
    from .analyst_preparation import prepare_handoff
    cached_analyst_rows=None
    def analyst_rows():
        nonlocal cached_analyst_rows
        if cached_analyst_rows is not None:return cached_analyst_rows
        prepared_pool = service._load_player_pool(request.season, request.week, request.slate,
            projection_run_id=result["projection_run_id"], ownership_run_id=result.get("ownership_run_id"),
            evidence_cutoff_at=aware(result["data_cutoff_at"]), require_explicit_runs=True)
        from .kicker_roles import assign_kicker_roles
        from .player_roles import resolve_player_roles
        prepared_pool, _ = assign_kicker_roles(prepared_pool)
        prepared_pool, _ = resolve_player_roles(prepared_pool)
        cached_analyst_rows=_json_safe(prepared_pool.to_dict("records"))
        return cached_analyst_rows
    from .analyst_personal_context import load_inputs
    if request.include_workload_forecast and not request.reuse_prepared_input_job_id:
        from .workload_count_forecast import prepare_receipt
        try:
            result["workload_forecast"] = prepare_receipt(service.engine, analyst_rows(),
                season=request.season, week=request.week, cutoff=aware(result["data_cutoff_at"]),
                projection_run_id=result["projection_run_id"],opportunity_source_context=result.get("opportunity_source_context"),
                games=result["source_manifest"]["games"],markets=result["source_manifest"].get("markets",[]))
        except ValueError as exc:
            if not request.scenario_mode:raise
            result["scenario_workload_issue"]=str(exc)
    if request.learned_opportunities:
        from .primary_model_forecast import prepare as prepare_primary
        context.progress('learned_opportunities',0,1,'Forecasting published learned attempts/targets; no point scoring heads.')
        result['workload_forecast']=prepare_primary(service.engine,result.get('workload_forecast'),analyst_rows(),
            **scope(request),cutoff=aware(result['data_cutoff_at']),games=result['source_manifest']['games'],
            markets=result['source_manifest'].get('markets',[]),
            scenario={'team':'','passing_factor':1.,'rushing_factor':1.},counts_only=True)
        if request.opportunity_yards:
            from .opportunity_yards import add_yards
            from .workload_count_forecast import load_history
            result['workload_forecast']=add_yards(result['workload_forecast'],
                load_history(service.engine,season=request.season,week=request.week,cutoff=aware(result['data_cutoff_at'])),
                before_period=request.season*100+request.week,cutoff=aware(result['data_cutoff_at']))
    if request.scenario_first_captain:
        from .captain_game_cases import build as build_cases, load_history as load_case_history
        context.progress('shared_scoring_cases',0,1,'Building market-first shared scoring cases and sourced player/kicking roles.')
        result['workload_forecast']=build_cases(result['workload_forecast'],
            load_case_history(service.engine,season=request.season,week=request.week,cutoff=aware(result['data_cutoff_at'])),analyst_rows(),
            before_period=request.season*100+request.week,cutoff=aware(result['data_cutoff_at']),
            games=result['source_manifest']['games'],markets=result['source_manifest'].get('markets',[]))
    if request.scenario_mode:
        from .optimizer_scenario_mode import prepare as prepare_scenario
        from .workload_count_forecast import load_history
        forecast=result.get("workload_forecast")
        weekly=load_history(service.engine,season=request.season,week=request.week,cutoff=aware(result["data_cutoff_at"])) if forecast and not forecast.get("component_response") else None
        result["scenario_mode"]=prepare_scenario(request.scenario_mode,forecast,analyst_rows(),
            before_period=request.season*100+request.week,cutoff=aware(result["data_cutoff_at"]),
            projection_run_id=result["projection_run_id"],weekly=weekly)
        if request.scenario_mode.get('scoring_mode')=='new_model_primary':
            from .primary_model_forecast import prepare as prepare_primary
            context.progress('new_model_forecast',0,1,'Scoring published team/player models and complete DK heads; incumbent retained for comparison.')
            primary=prepare_primary(service.engine,forecast,analyst_rows(),**scope(request),
                cutoff=aware(result['data_cutoff_at']),games=result['source_manifest']['games'],
                markets=result['source_manifest'].get('markets',[]),scenario=request.scenario_mode)
            report=result['scenario_mode']
            report.update(primary_model_forecast=primary,players=primary['players'],new_model_primary=True,
                scoring_basis=primary['scoring_basis'],team_model_consumption=primary['team_model_consumption'],
                count_budgets=primary['physical_count_budgets'],shared_budgets=primary['physical_count_budgets'],
                component_response_sha256=None,
                limitations=primary['limitations'],status='NEW_MODELS_PRIMARY',issue=None)
            report['changed_player_count']=sum(p['delta'] is not None and abs(p['delta'])>1e-9 for p in report['players'])
            from .evaluation_record import digest as scenario_digest
            report['sha256']=scenario_digest({k:v for k,v in report.items() if k!='sha256'})
        if result.get("scenario_workload_issue"):
            result["scenario_mode"]["limitations"].append(result["scenario_workload_issue"])
            from .evaluation_record import digest as scenario_digest
            result["scenario_mode"]["sha256"]=scenario_digest({k:v for k,v in result["scenario_mode"].items() if k!="sha256"})
    personal_context_inputs = _json_safe(load_inputs(service.engine))
    result["analyst_handoff"] = prepare_handoff(request=request, result=result,
        row_loader=analyst_rows, checked_at=datetime.now(UTC).isoformat(), personal_context_inputs=personal_context_inputs)
    if request.analyst_mode=="AUTO":
        result["analyst_intent_handoffs"]={intent:prepare_handoff(request=request,result=result,
            row_loader=analyst_rows,checked_at=datetime.now(UTC).isoformat(),optimization_intent=intent,personal_context_inputs=personal_context_inputs)
            for intent in ("EXPECTED_GAME","CONTRARIAN")}
    context.progress("analyst_checks", 1, 1, "Checked published Analyst research against the prepared scope and fresh canonical evidence.",
        checkpoint={"preparation_result": result})
    context.progress("readiness", 1, 1, "Prepared source checks saved.",
                     checkpoint={"preparation_result": result})
    if request.preliminary_research:
        # A completed research build retains the failed normal report. Freeze still
        # verifies salary identity, fresh markets and projection/ownership lineage.
        result["entry_ready"] = False
        return result
    if readiness["status"] != "READY":
        error = classic.ClassicDataNotReady if request.contest_format == "classic" else showdown.ShowdownDataNotReady
        raise error(readiness)
    return result


def run_weekly_preparation(session_factory, request, *, idempotency_key):
    """Execute a durable child job inline so a single worker cannot deadlock.

    Reserve the job in the enqueue transaction; the ordinary worker executor owns
    heartbeat, progress, completion and failure. Weekly retries reuse this job.
    """
    from ..services.job_queue import enqueue_job
    from ..worker import execute_claimed_job

    from ..product_schemas import PredictionRunRequest
    scenario = PredictionRunRequest(**scope(request), availability_overrides=request.availability_overrides,
                                    assume_questionable_out=request.assume_questionable_out)
    request = request.model_copy(update={"availability_overrides": [
        row.model_dump(mode="json") for row in scenario.availability_overrides]})
    worker_id = f"weekly-preparation-{uuid4()}"
    with session_factory() as session:
        job, _ = enqueue_job(session, job_type=PREPARATION_JOB,
            idempotency_key=f"weekly-preparation:{idempotency_key}",
            request_payload=request.model_dump(mode="json"), run_id=str(uuid4()),
            max_attempts=1, checkpoint={}, commit=False)
        job = session.scalar(select(OperationalJob).where(
            OperationalJob.job_id == job.job_id).with_for_update())
        if job.status == "completed" or (job.status == "running" and job.lease_expires_at
                and aware(job.lease_expires_at) > datetime.now(UTC)):
            session.expunge(job)
            return job
        # Retry reservation remains in this locked transaction: another worker
        # must never see a queued child that this worker is about to execute.
        job.max_attempts = max(job.max_attempts, job.attempt_count + 1)
        job.error_message = None
        job.result_json = None
        job.completed_at = None
        now = datetime.now(UTC).replace(tzinfo=None)
        job.status = "running"
        job.stage = "starting"
        job.attempt_count += 1
        job.locked_by = worker_id
        job.started_at = now
        job.lease_expires_at = now + timedelta(seconds=300)
        session.commit()
        job_id, payload, run_id, checkpoint = job.job_id, job.request_json, job.run_id, job.checkpoint_json
    execute_claimed_job(job_id=job_id, job_type=PREPARATION_JOB, request_payload=payload,
        worker_id=worker_id, run_id=run_id, checkpoint=checkpoint, lease_seconds=300)
    with session_factory() as session:
        job = session.get(OperationalJob, job_id)
        session.expunge(job)
        return job
