"""Fail-closed pre-generation contract for live Showdown evidence.

The consumed pool, including its original source clocks, is the authority.
Refreshing a projection never makes its underlying market/status evidence fresh.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import math
import re

from .replay import parse_slate_lock
from .slate_preparation import aware, digest
from .showdown_player_context import (CONTEXT_CONTRACT, NON_SCORING_SPECIALIST_ROLES,
                                     assess_availability, is_excluded_specialist, player_pool_diagnostic)

CONTRACT = "showdown_data_readiness_v1"
SOURCE_ACTIONS = {
    "salary_pool": "Load the current native Showdown salary pool and resolve its canonical identities.",
    "projection": "Rebuild a complete current projection set with model lineage and mean/P90 inputs.",
    "player_status": "Load current sourced pregame availability and role facts for the affected canonical player IDs.",
    "starting_qb": "Resolve one sourced starting QB per team with a current observation clock.",
    "market": "Refresh the baseline spread/total and rebuild projections so the consumed pool retains the market snapshot.",
    "ownership": "Refresh current CPT/FLEX ownership or choose a strategy that permits missing ownership.",
}


class ShowdownDataNotReady(ValueError):
    def __init__(self, readiness):
        self.readiness = readiness
        players = readiness.get("player_pool_readiness", {}).get("players", [])
        unknown = sorted({f"{p.get('player') or p['canonical_id']} ({p.get('team')})" for p in players
                          if p.get("disposition") == "unknown_availability"})
        messages = [f"Current availability is unverified for {', '.join(unknown)}."] if unknown else []
        descriptions = {"salary_pool":"Current salary identities or slate information need verification.",
            "projection":"Current projections could not be rebuilt or verified.",
            "player_status":"Current player availability or role evidence needs verification.",
            "starting_qb":"Current starting quarterbacks need verification.",
            "market":"Current game-market inputs need verification.",
            "ownership":"Required ownership inputs need verification."}
        messages.extend(descriptions.get(name,"Required source evidence needs verification.")
                        for name, check in readiness["required_sources"].items()
                        if check["status"] != "READY" and not (name == "player_status" and unknown))
        super().__init__("Showdown slate is not data-ready. "+" ".join(messages)+
                         " No lineups were generated. Review the saved readiness report for source details.")


def freshness_rules(settings):
    return {name: float(getattr(settings, f"showdown_{name}_max_age_hours"))
            for name in ("market", "projection", "player_status", "starting_qb", "salary_pool", "ownership")}


def requires_ownership(params):
    # Slot-ownership scoring has a hard dependency; the default v3 selector
    # explicitly supports projection-only ranking when role ownership is absent.
    return bool(params.get("ownership_required") or params.get("use_role_ownership"))


def is_live_slate(service, *, season, week, slate):
    now = datetime.now(UTC)
    if season >= now.year:
        return True
    # An NFL season crosses the calendar boundary. A prior-season identifier
    # with a future salary kickoff is still live, including January slates.
    if service.engine.dialect.name == "postgresql":
        from sqlalchemy import text
        with service.engine.connect() as connection:
            games = connection.execute(text("""
                SELECT DISTINCT game_info FROM public.curated_salary
                WHERE season=:season AND week=:week AND LOWER(slate)=LOWER(:slate)
                  AND source_system='draftkings'
            """), {"season": season, "week": week, "slate": slate}).scalars().all()
        kickoff = parse_slate_lock(games)
        return kickoff is not None and aware(kickoff) > now
    return False


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def assess_current_inputs(service, *, season, week, slate, projection_run_id):
    """Read-only preflight using generation's pool and evidence contract.

    This assesses saved inputs at the current clock. Run Optimizer still refreshes,
    validates and freezes its exact consumed evidence before solving.
    """
    from ..config import get_settings
    from .optimizer import _json_safe
    from .kicker_roles import assign_kicker_roles
    from .player_roles import resolve_player_roles

    now = datetime.now(UTC)
    pool = service._load_player_pool(season, week, slate,
        projection_run_id=projection_run_id, evidence_cutoff_at=now)
    pool, _ = assign_kicker_roles(pool)
    pool, _ = resolve_player_roles(pool)
    return evaluate_readiness(_json_safe(pool.to_dict("records")),
        season=season, week=week, slate=slate, projection_run_id=projection_run_id,
        evidence_cutoff=now, evaluated_at=now, rules=freshness_rules(get_settings()),
        require_canonical_context=True)


def native_matchup(rows, teams):
    """Retain verified native away/home order; alphabetical teams have no venue meaning."""
    from .market_snapshots import normalize_team
    pairs = set()
    for row in rows:
        match = re.match(r"^\s*([A-Za-z]{2,3})\s*@\s*([A-Za-z]{2,3})(?:\s|$)", str(row.get("game_id") or ""))
        if match:
            away, home = (normalize_team(match.group(1)), normalize_team(match.group(2)))
            if {away, home} == set(teams):
                pairs.add((away, home))
    if len(pairs) == 1:
        away, home = next(iter(pairs))
        return {"matchup": away + " @ " + home, "away_team": away, "home_team": home,
                "matchup_order_basis": "native_salary_game_info"}
    return {"matchup": " vs ".join(teams), "away_team": None, "home_team": None,
            "matchup_order_basis": "venue_order_unverified"}


def evaluate_readiness(rows, *, season, week, slate, projection_run_id,
                       evidence_cutoff, evaluated_at, rules, ownership_required=False,
                       ownership_attempted=False, refresh=None, require_canonical_context=False,
                       minimum_player_salary=None):
    """Deterministic, side-effect-free assessment of the exact consumed rows."""
    now, cutoff = aware(evaluated_at), aware(evidence_cutoff)
    teams = sorted({str(r.get("player_team") or r.get("team") or "") for r in rows} - {""})
    kickoff = parse_slate_lock(r.get("game_id") for r in rows)
    checks = {}

    def check(name, values, missing, stale, *, ids=(), sources=(), invalid=(), players=()):
        reasons = list(invalid)
        dates = []
        for value in values:
            try:
                date = aware(value) if value else None
            except (ValueError, TypeError, AttributeError):
                date = None
            if date is None:
                reasons.append(missing)
            else:
                dates.append(date)
                if date > cutoff or date > now:
                    reasons.append(f"{name}_after_cutoff")
                if (now - date).total_seconds() > rules[name] * 3600:
                    reasons.append(stale)
        if not values:
            reasons.append(missing)
        checks[name] = {"status": "NOT_READY" if reasons else "READY",
                        "reason_codes": sorted(set(reasons)),
                        "oldest_observed_at": min(dates).isoformat() if dates else None,
                        "newest_observed_at": max(dates).isoformat() if dates else None,
                        "source_ids": sorted({str(v) for v in ids if v}),
                        "sources": sorted({str(v) for v in sources if v}),
                        "affected_player_ids": sorted(set(players)), "max_age_hours": rules[name]}
        checks[name]["action"] = SOURCE_ACTIONS[name]

    salary_invalid = []
    if len(teams) != 2 or kickoff is None or len({r.get("game_id") for r in rows}) != 1:
        salary_invalid.append("slate_identity_unresolved")
    if kickoff and now >= aware(kickoff):
        salary_invalid.append("slate_locked")
    bad_salaries = [str(r.get("player_id")) for r in rows if not (
        r.get("player_id") and r.get("identity_resolved") is True
        and r.get("position") in {"QB", "RB", "WR", "TE", "K", "DST"}
        and number(r.get("salary")) is not None and number(r.get("salary")) > 0
        and r.get("dk_player_id") and r.get("dk_captain_id") and r.get("salary_source_row_id"))]
    if bad_salaries or not rows:
        salary_invalid.append("salary_pool_missing")
    if len(rows) < 6 or len(rows) != len({r.get("player_id") for r in rows}):
        salary_invalid.append("salary_pool_missing")
    check("salary_pool", [r.get("salary_source_observed_at") for r in rows],
          "salary_pool_missing", "salary_pool_stale", invalid=salary_invalid, players=bad_salaries,
          ids=[r.get("salary_source_row_id") for r in rows] + [r.get("salary_source_snapshot_id") for r in rows],
          sources=[r.get("salary_source_system") for r in rows])

    native_rows = rows
    dispositions = {str(r.get("player_id")): assess_availability(r, cutoff=cutoff, evaluated_at=now,
                    max_age_hours=rules["player_status"]) for r in native_rows}
    # An unavailable exclusion requires fresh source evidence. Unknown players
    # remain auditable and fail availability; they cannot silently be dropped.
    rows = [r for r in native_rows if dispositions[str(r.get("player_id"))][0] == "AVAILABLE"
            and not is_excluded_specialist(r, cutoff=cutoff, evaluated_at=now, max_age_hours=rules["player_status"])]
    bad_projection = [str(r.get("player_id")) for r in rows if not (
        projection_run_id and str(r.get("projection_run_id")) == str(projection_run_id)
        and r.get("projection_inputs_complete", True) is True
        and number(r.get("projection")) is not None and number(r.get("projection")) >= 0
        and number(r.get("p90")) is not None and number(r.get("p90")) >= 0
        and r.get("projection_model_version"))]
    missing_features = [str(r.get("player_id")) for r in rows if r.get("feature_inputs_complete", True) is not True]
    check("projection", [r.get("projection_observed_at") for r in rows],
          "projection_missing", "projection_stale", invalid=(["projection_missing"] if bad_projection else []) +
                  (["feature_missing"] if missing_features else []) +
                  (["generation_pool_too_small"] if len(rows) < 6 else []),
          players=sorted(set(bad_projection + missing_features)), ids=[projection_run_id], sources=[r.get("projection_model_version") for r in rows])

    # Availability and role have independent original observation clocks.
    individuals = [r for r in native_rows if r.get("position") != "DST"]
    bad_status, status_invalid, status_dates, excluded_status = [], [], [], []
    for r in individuals:
        pid = str(r.get("player_id"))
        state, reasons = dispositions[pid]
        reasons = list(reasons)
        row_dates = []
        if r.get("canonical_context_contract") == CONTEXT_CONTRACT:
            row_dates.append(r.get("availability_observed_at"))
            if state != "UNAVAILABLE":
                row_dates.append(r.get("role_observed_at"))
                if not r.get("canonical_role") or not r.get("role_source") or not r.get("role_source_ids"):
                    reasons.append("player_role_missing")
                reasons.extend(code for code in r.get("canonical_context_reason_codes") or [] if code.startswith("player_role"))
                if r.get("pregame_role_uncertain"):
                    reasons.append("player_role_unresolved")
                if r.get("canonical_role") in NON_SCORING_SPECIALIST_ROLES.values() and not is_excluded_specialist(
                        r, cutoff=cutoff, evaluated_at=now, max_age_hours=rules["player_status"]):
                    reasons.append("player_role_unresolved")
            if not r.get("pregame_context_run_id") or not r.get("pregame_context_source"):
                reasons.append("player_status_missing")
        else:
            if require_canonical_context:
                reasons.append("canonical_player_context_missing")
            row_dates.append(r.get("pregame_context_observed_at"))
            if not (r.get("pregame_context_source") and r.get("pregame_context_run_id")
                    and r.get("player_status_evidence_present") is True
                    and (r.get("official_availability_status") or r.get("pregame_injury_status")
                         or number(r.get("pregame_availability_probability")) is not None)
                    and (r.get("role_optimizer_eligible") is False or
                         (r.get("expected_depth_role") not in {None, "uncertain"} and not r.get("pregame_role_uncertain")))):
                reasons.append("player_status_missing")
        # Include clock-only violations in the per-player audit as well.
        clock_reasons = []
        for clock in ([r.get("availability_observed_at"), r.get("role_observed_at")] if
                      r.get("canonical_context_contract") == CONTEXT_CONTRACT and state != "UNAVAILABLE" else
                      [r.get("availability_observed_at")] if r.get("canonical_context_contract") == CONTEXT_CONTRACT else
                      [r.get("pregame_context_observed_at")]):
            try:
                date = aware(clock)
                if date > cutoff or date > now:
                    clock_reasons.append("player_status_after_cutoff")
                if (now-date).total_seconds() > rules["player_status"]*3600:
                    clock_reasons.append("player_status_stale")
            except (ValueError, TypeError, AttributeError):
                clock_reasons.append("player_status_missing")
        # A selection preference cannot establish a football fact. Retain the
        # unknown role/status and projection, but it need not block a player
        # pool whose bound salary floor makes this identity unselectable.
        salary = number(r.get("base_salary"))
        if salary is None:
            salary = number(r.get("salary"))
        if minimum_player_salary and salary is not None and 0 < salary < minimum_player_salary:
            excluded_status.append({"player_id": pid, "player": r.get("player_name") or r.get("name"),
                "salary": salary, "reason": "user_minimum_player_salary", "category": "user_preference",
                "availability_state": state, "player_status": r.get("player_status"),
                "canonical_role": r.get("canonical_role"), "role_source": r.get("role_source"),
                "availability_observed_at": r.get("availability_observed_at"),
                "role_observed_at": r.get("role_observed_at"),
                "reason_codes": sorted(set(reasons + clock_reasons)),
                "model_assessment": {"projection": r.get("projection"), "p90": r.get("p90")}})
        else:
            status_dates.extend(row_dates)
            if reasons or clock_reasons:
                bad_status.append(pid)
            status_invalid.extend(reasons)
    check("player_status", status_dates, "player_status_missing", "player_status_stale", invalid=status_invalid,
          players=bad_status, ids=[r.get("pregame_context_run_id") for r in individuals],
          sources=[r.get("availability_source") or r.get("pregame_context_source") for r in individuals] +
                  [r.get("role_source") for r in individuals])

    starters = [r for r in native_rows if r.get("position") == "QB" and r.get("is_starting_qb") is True]
    unresolved = [team for team in teams if len([r for r in starters if r.get("player_team") == team]) != 1]
    check("starting_qb", [r.get("starting_qb_observed_at") for r in starters],
          "starting_qb_unresolved", "starting_qb_stale",
          invalid=["starting_qb_unresolved"] if unresolved or len(teams) != 2 or
          any(not r.get("starting_qb_source") or (r.get("team_starting_qb_player_id") and
              str(r["team_starting_qb_player_id"]) != str(r.get("player_id"))) for r in starters) else [],
          ids=[r.get("player_id") for r in starters], sources=[r.get("starting_qb_source") for r in starters])

    market_invalid, markets = [], {}
    for team in teams:
        team_rows = [r for r in rows if (r.get("player_team") or r.get("team")) == team]
        if not team_rows:
            market_invalid.append("market_missing")
            continue
        quotes = {(number(r.get("team_spread_line")), number(r.get("game_total_line")),
                   str(r.get("market_observed_at")), r.get("market_source_system")) for r in team_rows}
        if len(quotes) != 1 or any(r.get("market_context_point_in_time_safe") is not True for r in team_rows):
            market_invalid.append("market_missing")
        spread, total = number(team_rows[0].get("team_spread_line")), number(team_rows[0].get("game_total_line"))
        if spread is None or total is None or total <= 0 or not team_rows[0].get("market_source_system"):
            market_invalid.append("market_missing")
        else:
            implied = (total - spread) / 2
            if implied <= 0 or any(number(r.get("team_implied_total")) is None or
                                   abs(number(r.get("team_implied_total")) - implied) > .05 for r in team_rows):
                market_invalid.append("market_missing")
            markets[team] = {"spread": spread, "total": total, "implied_total": implied}
    if len(markets) != 2 or (len(markets) == 2 and (
            abs(sum(q["spread"] for q in markets.values())) > .05 or
            len({q["total"] for q in markets.values()}) != 1)):
        market_invalid.append("market_missing")
    check("market", [r.get("market_observed_at") for r in rows], "market_missing", "market_stale",
          invalid=market_invalid, ids=[r.get("market_snapshot_row_id") for r in rows],
          players=[str(r.get("player_id")) for r in rows if any(r.get(field) is None for field in
                   ("market_observed_at", "game_total_line", "team_spread_line", "team_implied_total"))],
          sources=[r.get("market_source_system") for r in rows])

    ownership_available = bool(rows) and all(number(r.get("captain_ownership")) is not None and
        0 <= number(r.get("captain_ownership")) <= 100 and number(r.get("flex_ownership")) is not None and
        0 <= number(r.get("flex_ownership")) <= 100 and r.get("ownership_run_id") and
        r.get("ownership_source") for r in rows)
    ownership_reason = "ownership_missing_required" if ownership_required else "ownership_missing_optional"
    check("ownership", [r.get("ownership_observed_at") for r in rows], ownership_reason, "ownership_stale",
          invalid=[] if ownership_available else [ownership_reason],
          ids=[r.get("ownership_run_id") for r in rows], sources=[r.get("ownership_source") for r in rows])
    ownership = checks.pop("ownership")
    ownership.update(ownership_available=ownership_available, ownership_attempted=ownership_attempted,
                     ownership_source=ownership["sources"], ownership_observed_at=ownership["oldest_observed_at"],
                     ownership_fresh=ownership["status"] == "READY", required=ownership_required)
    if not ownership_required and ownership["status"] != "READY":
        ownership["status"] = "OPTIONAL_MISSING" if not ownership_available else "OPTIONAL_STALE"
    required, optional = dict(checks), {}
    (required if ownership_required else optional)["ownership"] = ownership
    reasons = sorted({code for c in required.values() for code in c["reason_codes"]})
    result = {"contract_id": CONTRACT, "slate_identifier": {"season": season, "week": week, "slate": slate},
            **native_matchup(native_rows, teams), "kickoff_at": aware(kickoff).isoformat() if kickoff else None,
            "evaluated_at": now.isoformat(), "evidence_cutoff": cutoff.isoformat(),
            "status": "NOT_READY" if reasons else "READY", "reason_codes": reasons,
            "required_sources": required, "optional_sources": optional, "ownership": ownership,
            "baseline_market": {"teams": markets,
                "favorite": next((t for t, q in markets.items() if q["spread"] < 0), None),
                "underdog": next((t for t, q in markets.items() if q["spread"] > 0), None),
                "pickem": len(markets) == 2 and all(q["spread"] == 0 for q in markets.values())},
            "refresh": deepcopy(refresh or {}),
            "selection_scope": {"minimum_player_salary": minimum_player_salary,
                "nonblocking_player_status_exclusions": excluded_status}}
    result["player_pool_readiness"] = player_pool_diagnostic(native_rows, readiness=result)
    result["generation_eligible_player_ids"] = [p["canonical_id"] for p in result["player_pool_readiness"]["players"] if p["generation_eligible"]]
    return result


def freeze_evidence(rows, readiness, *, optimizer_run_id, role_context=(), allow_incomplete_evidence=False):
    if readiness["status"] != "READY" and not allow_incomplete_evidence:
        raise ShowdownDataNotReady(readiness)
    value = {"contract_id": "showdown_frozen_evidence_v1", "optimizer_run_id": optimizer_run_id,
             "frozen_at": readiness["evaluated_at"], "evidence_cutoff": readiness["evidence_cutoff"],
             "non_production_override": allow_incomplete_evidence, "data_readiness": deepcopy(readiness),
             "player_pool": deepcopy(rows if allow_incomplete_evidence else [r for r in rows if str(r.get("player_id")) in
                 set(readiness.get("generation_eligible_player_ids", [str(r.get("player_id")) for r in rows]))]),
             "native_player_pool": deepcopy(rows), "role_context": deepcopy(list(role_context))}
    value["sha256"] = digest(value)
    return value


def validate_frozen_evidence(value):
    if value.get("contract_id") != "showdown_frozen_evidence_v1" or value.get("sha256") != digest(
            {k: v for k, v in value.items() if k != "sha256"}):
        raise ValueError("Frozen Showdown evidence checksum mismatch")
    return value["data_readiness"]


def refresh_completed_schedule_scores(engine, *, season, weeks):
    """Acquire missing final scores before rebuilding completed DST labels.

    Captures append source versions; missing or conflicting finals still block.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from ..models import RawNflSchedule
    from ..schemas import NflReadPySeasonRequest
    from ..services.source_capture import SourceCaptureService
    from .dst_scoring_reconciliation import require_completed_schedule_scores, DstScoringUnresolved

    def check():
        with Session(engine) as session:
            rows = session.scalars(select(RawNflSchedule).where(
                RawNflSchedule.source_system == 'nflreadpy', RawNflSchedule.season == season,
                RawNflSchedule.week.in_(weeks))).all()
            if not rows:
                raise DstScoringUnresolved('Missing completed-period schedule evidence')
            return require_completed_schedule_scores(
                [dict(game_id=r.game_id, raw_row_json=r.raw_row_json) for r in rows], now=datetime.now(UTC))
    try:
        return dict(status='verified_existing', **check())
    except DstScoringUnresolved:
        with Session(engine) as session:
            captured = SourceCaptureService(session).capture_and_ingest_nflreadpy_schedules(
                NflReadPySeasonRequest(season=season, weeks=sorted(set(weeks))))
            snapshot_id = captured.capture.snapshot.snapshot_id
        return dict(status='refreshed', snapshot_id=snapshot_id, **check())


def refresh_training_labels(engine, *, season, week, slate, preliminary_exclude_unknown=False):
    """Repair stale completed labels before taking the live projection cutoff."""
    from sqlalchemy.orm import Session
    from .canonical_projection_inputs import load_inputs, StaleTrainingOutcomeError
    from ..services.lineup_learning import LineupLearningService
    try:
        load_inputs(engine,season=season,week=week,slate=slate,cutoff=datetime.now(UTC),
            **({"preliminary_exclude_unknown": True} if preliminary_exclude_unknown else {}))
        return {"periods": [], "rows_written": 0}
    except StaleTrainingOutcomeError as exc:
        periods = exc.periods
    grouped = {}
    for prior_season,prior_week in periods:
        if (prior_season,prior_week) >= (season,week):
            raise ValueError("Training label repair must precede the target period")
        grouped.setdefault(prior_season,[]).append(prior_week)
    rows = 0
    schedule_receipts = []
    for prior_season,weeks in sorted(grouped.items()):
        schedule_receipts.append(refresh_completed_schedule_scores(engine, season=prior_season, weeks=weeks))
        with Session(engine) as session:
            result = LineupLearningService(session).rebuild_player_game_feature_matrix(
                source_system="draftkings",season_start=prior_season,season_end=prior_season,weeks=sorted(set(weeks)))
        if not result["slates_total"] or result["slates_failed"]:
            failures = [f"{r.get('season')}-W{r.get('week')} {r.get('slate')}: {r.get('error_message')}"
                        for r in result.get('rows', []) if r.get('status') == 'failed']
            raise ValueError("Completed training-label refresh did not rebuild every affected slice" +
                             (": " + "; ".join(failures) if failures else ""))
        rows += result["rows_written"]
    return {"periods": [{"season":s,"week":w} for s,w in periods], "rows_written":rows,
            "schedule_receipts": schedule_receipts}


def _refresh_player_sources(service, *, season, week, slate, games, lock, attempt,
                            official_require_complete_coverage=True, resolve_identities=None):
    """Shared live player collectors; composing context retains original clocks."""
    from sqlalchemy.orm import Session
    from ..schemas import NflReadPySeasonRequest
    from ..services.source_capture import SourceCaptureService, capture_nflreadpy_datasets, DEFAULT_NFLREADPY_LICENSE
    from .starters import StartingQBService
    from .showdown_player_context import refresh_canonical_context
    from .official_injuries import refresh_official_injuries

    def availability():
        with Session(service.engine) as session:
            capture = SourceCaptureService(session)
            roster = capture.capture_and_ingest_nflreadpy_weekly_rosters(
                NflReadPySeasonRequest(season=season, weeks=[week]), slate=slate, slate_lock_at=lock)
            return {"snapshot_id": roster.capture.snapshot.snapshot_id, "rows": roster.ingest.rows_curated}
    attempt("player_status", availability)
    if resolve_identities is not None and not resolve_identities():
        return False
    # This existing collector retains injury reports as raw source evidence. The
    # canonical projections still require sourced pregame context; raw capture
    # alone cannot clear availability or role readiness.
    def injuries():
        with Session(service.engine) as session:
            snapshots = capture_nflreadpy_datasets(SourceCaptureService(session), ["injuries"],
                season=season, week=week, slate=slate, slate_lock_at=lock,
                source_license=DEFAULT_NFLREADPY_LICENSE)
            return {"snapshot_ids": [s.snapshot.snapshot_id for s in snapshots]}
    attempt("injuries", injuries)
    attempt("official_player_status", lambda: refresh_official_injuries(service.engine,
        season=season, week=week, slate=slate, games=games, slate_lock_at=lock,
        require_complete_team_coverage=official_require_complete_coverage))
    attempt("starting_qb", lambda: vars(StartingQBService(service.connection_string).derive_starters(season, week, slate)))
    attempt("canonical_player_context", lambda: refresh_canonical_context(service.engine,
            season=season, week=week, slate=slate))
    return True


def refresh_projection_player_context(service, *, season, week, slate, progress=None):
    """Refresh only live native Showdown inputs before a direct projection cutoff.

    Classic and historical replay keep their saved inputs. Collector outages
    leave the scoring gate to assess saved evidence; identity ambiguity blocks.
    """
    from sqlalchemy import inspect, text
    from sqlalchemy.orm import Session
    from .slate_preparation import SlatePreparationRequest, slate_games
    from .showdown_player_context import PlayerContextUnresolved
    from nflreadpy.config import CacheMode, update_config

    if service.engine.dialect.name != "postgresql" or not inspect(service.engine).has_table("curated_salary"):
        return None
    if not is_live_slate(
        service, season=season, week=week, slate=slate
    ):
        return None
    with service.engine.connect() as connection:
        native_showdown = connection.execute(text("""
            SELECT COALESCE(BOOL_OR(roster_position='CPT'),FALSE)
               AND COALESCE(BOOL_OR(roster_position='FLEX'),FALSE)
            FROM public.curated_salary
            WHERE season=:season AND week=:week AND LOWER(slate)=LOWER(:slate)
              AND source_system='draftkings'
        """), {"season":season,"week":week,"slate":slate}).scalar_one()
    if not native_showdown:
        return None
    request = SlatePreparationRequest(season=season,week=week,slate=slate,action="rebuild")
    with Session(service.engine) as session:
        games = slate_games(session,request)
    lock = min(aware(game["kickoff_at"]) for game in games)
    if datetime.now(UTC) >= lock:
        return None
    report = {}
    def attempt(name, action):
        if progress:
            progress(f"refresh_{name}",1,4,f"Refreshing Showdown {name} evidence.")
        try:
            report[name] = {"status":"completed","result":action()}
        except PlayerContextUnresolved as exc:
            report[name] = {"status":"blocked","reason":str(exc)}
        except Exception as exc:
            report[name] = {"status":"ERROR","reason":f"{type(exc).__name__}: {str(exc)[:1000]}"}
    update_config(cache_mode=CacheMode.OFF,verbose=False)
    _refresh_player_sources(service,season=season,week=week,slate=slate,games=games,lock=lock,attempt=attempt)
    if report["official_player_status"]["status"] == "blocked":
        raise PlayerContextUnresolved(report["official_player_status"]["reason"])
    if report["canonical_player_context"]["status"] != "completed":
        raise PlayerContextUnresolved(
            "Current player context could not be refreshed. " + report["canonical_player_context"]["reason"])
    return report


def refresh_live_sources(service, *, season, week, slate, params, progress=None,
                         label="Showdown", salary_refresher=None, ownership_required=False,
                         official_require_complete_coverage=True, player_context_supplement=None):
    """Reuse canonical collectors/builders. Failed collectors never certify data."""
    from types import SimpleNamespace
    from sqlalchemy.orm import Session
    from .slate_preparation import (SlatePreparationRequest, slate_games, require_prelock,
                                    capture_source, execute_preparation)
    from .ownership import OwnershipService
    from .showdown_player_context import PlayerContextUnresolved
    from Database.player_identity import repair_salary_identities
    from nflreadpy.config import CacheMode, update_config

    request = SlatePreparationRequest(season=season, week=week, slate=slate, action="rebuild",
        availability_overrides=params.get("availability_overrides", []),
        assume_questionable_out=params.get("assume_questionable_out", False),
        preliminary_research=params.get("preliminary_research", False))
    report = {}
    def emit(stage, message, **kwargs):
        if progress:
            progress(stage, 0, 1, message, **kwargs)
    def attempt(name, action):
        emit(f"refresh_{name}", f"Refreshing {label} {name} evidence.")
        try:
            report[name] = {"status": "completed", "result": action()}
        except PlayerContextUnresolved as exc:
            report[name] = {"status": "blocked", "reason": str(exc)}
        except Exception as exc:
            # Re-read and evaluate saved evidence even if a provider is down.
            # Error text is intentionally bounded; source services own detailed logs.
            cause = exc
            while cause is not None and not isinstance(cause, PlayerContextUnresolved):
                cause = cause.__cause__
            report[name] = {"status": "blocked" if cause is not None else "ERROR",
                            "reason": f"{type(exc).__name__}: {str(exc)[:1000]}"}

    try:
        with Session(service.engine) as session:
            games = slate_games(session, request)
            lock = require_prelock(games)
    except ValueError as exc:
        report["projection"] = {"status": "ERROR", "reason": str(exc)}
        return {"projection_run_id": None, "data_cutoff_at": datetime.now(UTC),
                "ownership_run_id": None, "report": report}
    def resolve_identities():
        attempt("salary_pool", salary_refresher or (lambda: vars(repair_salary_identities(service.engine, season=season, week=week, slate=slate))))
        salary_result = report["salary_pool"].get("result") or {}
        identity = salary_result.get("identity_repair", salary_result)
        return report["salary_pool"]["status"] == "completed" and not identity.get("salary_rows_quarantined", 0)
    update_config(cache_mode=CacheMode.OFF, verbose=False)
    attempt("market", lambda: capture_source(request.model_copy(update={"action": "markets"}), games))
    if report["market"]["status"] != "completed":
        report["projection"] = {"status": "blocked", "reason":
            "Current sportsbook spreads/totals could not be refreshed: " + report["market"]["reason"]}
        return {"projection_run_id": None, "data_cutoff_at": datetime.now(UTC),
                "ownership_run_id": None, "report": report}
    from .historical_prerequisites import refresh_history
    attempt("historical_participation", lambda: refresh_history(service.engine,
        season=season, week=week, slate=slate, lock=lock))
    if report["historical_participation"]["status"] != "completed":
        report["projection"] = {"status": "blocked", "reason":
            "Prior-week stats/snaps could not be completed: " + report["historical_participation"]["reason"]}
        return {"projection_run_id": None, "data_cutoff_at": datetime.now(UTC),
                "ownership_run_id": None, "report": report}
    if params.get("include_workload_forecast"):
        from .workload_gamebook_participation import refresh_slate_gaps
        attempt("workload_participation", lambda: refresh_slate_gaps(service.engine,
            season=season,week=week,slate=slate,target_lock_at=lock,progress=progress))
    # Refresh roster identities first; new provider IDs must be available to the
    # same resolver used by import before status joins or dependent builds run.
    resolved = _refresh_player_sources(service, season=season, week=week, slate=slate, games=games, lock=lock, attempt=attempt,
        official_require_complete_coverage=official_require_complete_coverage, resolve_identities=resolve_identities)
    if not resolved:
        report["projection"] = {"status": "blocked", "reason":
            "Salary identity resolution must complete before building projections. Review the unresolved identity queue."}
        return {"projection_run_id": None, "data_cutoff_at": datetime.now(UTC),
                "ownership_run_id": None, "report": report}
    if player_context_supplement is None and label == 'Showdown':
        from .classic_official_context import supplement_unresolved_context
        player_context_supplement = lambda: supplement_unresolved_context(service.engine,
            season=season, week=week, slate=slate, contest_format='showdown')
    if player_context_supplement:
        attempt('official_context_supplement', player_context_supplement)
    checkpoint = {}
    def build_progress(stage, current, total, message, **kwargs):
        if kwargs.get("checkpoint") is not None:
            checkpoint.update(kwargs["checkpoint"])
        if progress:
            progress(stage, current, total, message, **kwargs)
    context = SimpleNamespace(checkpoint=checkpoint, run_id=None, progress=build_progress)
    if report["official_player_status"]["status"] == "blocked" and not request.preliminary_research:
        report["projection"] = {"status":"blocked", "reason":report["official_player_status"]["reason"]}
    else:
        attempt("projection", lambda: execute_preparation(context, request.model_dump(mode="json"),
            refresh_training_before_cutoff=True))
    build = report["projection"].get("result") or {}
    projection_id = build.get("projection_run_id")
    cutoff = build.get("data_cutoff_at") or checkpoint.get("data_cutoff_at") or datetime.now(UTC).isoformat()
    if ownership_required and not projection_id:
        report["ownership"] = {"status": "blocked", "reason": "No verified new projection; ownership cannot fall back to an older build."}
    elif params.get("refresh_ownership", True) or requires_ownership(params) or ownership_required:
        attempt("ownership", lambda: vars(OwnershipService(service.connection_string).run_projection_model(
            season, week, slate, data_cutoff_at=aware(cutoff), projection_run_id=projection_id)))
    ownership_id = ((report.get("ownership") or {}).get("result") or {}).get("ownership_run_id")
    return {"projection_run_id": projection_id, "data_cutoff_at": aware(cutoff),
            "ownership_run_id": ownership_id, "report": report}
