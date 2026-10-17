"""Canonical, sourced Showdown availability/role facts and pool dispositions.

No absence, probability default, salary amount or prior-game result establishes
availability. Each fact retains its own observation/receipt clock and identity.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import json

from sqlalchemy import text
from sqlalchemy.orm import Session
from ..injury_scope import injury_slate_sql, injury_subset_membership_sql, SUNDAY_SUBSETS

from Database.dst import normalize_team
from Database.player_identity import normalize_position
from .player_roles import UNAVAILABLE, PRACTICE
from .salary_eligibility import normalize_salary_status
from .slate_preparation import aware

CONTEXT_CONTRACT = "canonical_showdown_player_context_v1"
AVAILABLE = {"ACT", "ACTIVE", "AVAILABLE", "HEALTHY", "Q", "QUESTIONABLE", "D", "DOUBTFUL", "P", "PROBABLE"}
# Only affirmative source positions supported here can establish a specialist.
# These are football roles, never aliases for a DraftKings roster position.
NON_SCORING_SPECIALIST_ROLES = {"LS": "long_snapper"}
CONTEXT_FIELDS = (
    "availability_state", "availability_status", "availability_source", "availability_observed_at",
    "availability_source_ids", "role_source", "role_observed_at", "role_source_ids",
    "canonical_context_reason_codes", "canonical_context_contract", "canonical_role",
    "dfs_position", "role_source_position",
    "expected_qb_package",
)


class PlayerContextUnresolved(ValueError):
    """A real canonical-source gap; refresh can report NOT_READY, not a build bug."""


def _state(status):
    status = normalize_salary_status(status)
    # nflverse roster dictionary: CUT means cut from this team's roster.
    # Keep ambiguous legacy codes unknown; a later active fact can supersede CUT.
    return "UNAVAILABLE" if status in UNAVAILABLE | PRACTICE | {"CUT"} else "AVAILABLE" if status in AVAILABLE else "UNKNOWN"


def _visible(fact, cutoff):
    try:
        return bool(fact.get("source") and fact.get("observed_at") and fact.get("received_at")
                    and aware(fact["observed_at"]) <= cutoff and aware(fact["received_at"]) <= cutoff)
    except (ValueError, TypeError, AttributeError):
        return False


def _latest(facts, value):
    if not facts:
        return None, False
    at = max(aware(f["observed_at"]) for f in facts)
    current = [f for f in facts if aware(f["observed_at"]) == at]
    conflict = len({value(f) for f in current}) > 1
    return sorted(current, key=lambda f: (str(f.get("source")), str(f.get("source_ids"))))[0], conflict


def sourced_depth_role(source_position, dfs_position, rank):
    """Classify sourced depth facts while preserving both position labels."""
    if source_position in NON_SCORING_SPECIALIST_ROLES:
        return "role", NON_SCORING_SPECIALIST_ROLES[source_position]
    aligned = normalize_position(source_position) == normalize_position(dfs_position)
    return ("role" if aligned else "role_position_conflict",
            "expected_starter" if float(rank) == 1 else "expected_backup")


def is_excluded_specialist(row, *, cutoff, evaluated_at, max_age_hours):
    """Require fresh, unambiguous canonical sourced non-scoring role evidence.

    Availability and native salary/identity validity are assessed separately.
    Missing, stale or conflicting roles cannot authorize this exclusion.
    """
    if not (row.get("canonical_context_contract") == CONTEXT_CONTRACT
            and NON_SCORING_SPECIALIST_ROLES.get(row.get("role_source_position")) == row.get("canonical_role")
            and row.get("canonical_role") in NON_SCORING_SPECIALIST_ROLES.values()
            and row.get("role_source") and row.get("role_source_ids")
            and not row.get("pregame_role_uncertain") and not row.get("role_uncertain")
            and not any(code.startswith("player_role") for code in row.get("canonical_context_reason_codes") or [])):
        return False
    try:
        observed = aware(row["role_observed_at"])
        return (observed <= aware(cutoff) and observed <= aware(evaluated_at)
                and (aware(evaluated_at) - observed).total_seconds() <= max_age_hours * 3600)
    except (KeyError, ValueError, TypeError, AttributeError):
        return False


def compose_player_contexts(salaries, facts, *, cutoff, max_age_hours):
    """Merge independent current facts once per canonical native salary player."""
    cutoff = aware(cutoff)
    # A starter observation describes the team's QB relationship, not just the
    # named player's role. Carry it to the other canonical QBs so a newer
    # starter supersedes their retained older starter assignments as well.
    # Preserve the original clocks/IDs, including when Main facts are reused.
    facts = list(facts)
    starters = [f for f in facts if f.get("kind") == "starting_qb"
                and f.get("role") == "expected_starter"
                and f.get("position") == "QB" and not f.get("team_starting_qb_player_id")]
    for salary in salaries:
        if salary.get("position") != "QB":
            continue
        pid = str(salary.get("player_id") or salary.get("player_master_id") or "")
        for starter in starters:
            if (str(starter.get("player_id")) != pid and
                    normalize_team(str(starter.get("team") or "")) == normalize_team(str(salary.get("team") or ""))):
                facts.append({**starter, "player_id": pid, "role": "expected_backup",
                              "team_starting_qb_player_id": str(starter["player_id"])})
    results = []
    for salary in salaries:
        pid = str(salary.get("player_id") or salary.get("player_master_id") or "")
        player_facts = [f for f in facts if str(f.get("player_id")) == pid
                        and normalize_team(str(f.get("team") or "")) == normalize_team(str(salary.get("team") or ""))
                        and str(f.get("position") or "").upper() == str(salary.get("position") or "").upper()]
        visible = [f for f in player_facts if _visible(f, cutoff)]
        current = [f for f in visible if (cutoff - aware(f["observed_at"])).total_seconds() <= max_age_hours * 3600]
        reasons = []
        roster, roster_conflict = _latest([f for f in current if f["kind"] == "roster_status"], lambda f: _state(f.get("status")))
        status, status_conflict = _latest([f for f in current if f["kind"] in {"game_status", "injury_status"}
                                         and _state(f.get("status")) != "UNKNOWN"], lambda f: normalize_salary_status(f.get("status")))
        # Generic ACT roster presence cannot clear a current sourced OUT report.
        # Conversely, roster IR/PS is unavailable despite an injury-only ACTIVE.
        if roster and _state(roster.get("status")) == "UNAVAILABLE":
            if not (status and status.get("game_active") is True and aware(status["observed_at"]) > aware(roster["observed_at"])):
                status = roster
        status = status or roster
        state = _state((status or {}).get("status"))
        # Roster membership cannot revoke an older game-specific OUT report.
        # Once that report expires, require a current game-status resolution.
        stale_game_out = [f for f in visible if f["kind"] in {"game_status", "injury_status"}
                          and _state(f.get("status")) == "UNAVAILABLE" and f not in current]
        if state == "AVAILABLE" and status is roster and stale_game_out:
            state = "UNKNOWN"
            reasons.append("player_status_stale")
        if roster_conflict or status_conflict:
            state = "UNKNOWN"; reasons.append("player_status_conflict")
        if state == "UNKNOWN":
            reasons.append("player_status_stale" if any(f["kind"] in {"roster_status", "game_status", "injury_status"} for f in visible)
                           and not any(f["kind"] in {"roster_status", "game_status", "injury_status"} for f in current)
                           else "player_status_missing")
        roles = [f for f in current if f["kind"] in {"role", "starting_qb"} and f.get("role")]
        # The established starting-QB relationship is authoritative for QB role.
        qb_roles = [f for f in roles if f["kind"] == "starting_qb"]
        role, role_conflict = _latest(qb_roles or roles, lambda f: f.get("role"))
        if role_conflict:
            role = None; reasons.append("player_role_conflict")
        if salary.get("position") == "DST":
            state = "AVAILABLE"
            role = {"role": "team_defense", "source": "canonical_team_defense", "observed_at": cutoff.isoformat(), "source_ids": [salary.get("salary_source_row_id")]}
            reasons = []
        elif state != "UNAVAILABLE" and not role:
            if any(f["kind"] == "role_position_conflict" for f in current):
                reasons.append("player_role_position_conflict")
            reasons.append("player_role_stale" if any(f["kind"] in {"role", "starting_qb"} for f in visible) else "player_role_missing")
        evidence = {
            "canonical_context_contract": CONTEXT_CONTRACT,
            "availability_state": state, "availability_status": (status or {}).get("status"),
            "availability_source": (status or {}).get("source"),
            "availability_observed_at": (status or {}).get("observed_at"),
            "availability_source_ids": (status or {}).get("source_ids", []),
            "canonical_role": (role or {}).get("role"), "expected_depth_role": (role or {}).get("role"),
            "dfs_position": salary.get("position"), "role_source_position": (role or {}).get("source_position"),
            "role_source": (role or {}).get("source"), "role_observed_at": (role or {}).get("observed_at"),
            "role_source_ids": (role or {}).get("source_ids", []),
            "starter_evidence": deepcopy(role), "roster_status": (roster or {}).get("status"),
            "canonical_context_reason_codes": sorted(set(reasons)),
            "source_facts": deepcopy(player_facts),
            "source_uris": sorted({str(f["source_uri"]) for f in player_facts if f.get("source_uri")}),
        }
        if status and type(status.get("game_active")) is bool:
            evidence["game_active"] = status["game_active"]
        chosen_times = [aware(f["observed_at"]) for f in (status, role) if f and f.get("observed_at")]
        context = {"player_id": pid, "player_master_id": pid, "team": salary.get("team"), "position": salary.get("position"),
                   "player_name": salary.get("player_name"), "injury_status": evidence["availability_status"] or "UNKNOWN",
                   "role_label": {"expected_starter":"STARTER", "expected_backup":"BACKUP", "rotation":"ROTATION"}.get((role or {}).get("role")),
                   "availability_probability": 0. if state == "UNAVAILABLE" else None,
                   "source": CONTEXT_CONTRACT, "source_uri": "football26://canonical-source-lineage",
                   "observed_at": max(chosen_times, default=cutoff), "evidence_json": evidence}
        results.append(context)
    return results


def attach_context_fields(frame, contexts):
    """Join canonical facts to salaries even when a player has no projection."""
    rows = frame.copy()
    attributes = rows.attrs
    rows.attrs = {}
    lookup = {str(c.get("player_master_id") or c.get("player_id")): c for c in contexts}
    for index, row in rows.iterrows():
        context = lookup.get(str(row["player_id"]), {})
        evidence = context.get("evidence_json") or {}
        if evidence.get("canonical_context_contract") != CONTEXT_CONTRACT:
            continue
        for field in CONTEXT_FIELDS:
            if field not in rows:
                rows[field] = None
            rows.at[index, field] = deepcopy(evidence.get(field))
        if evidence.get('expected_qb_package') is None:
            rows.at[index, 'expected_qb_package'] = (evidence.get('workload_context', {}).get('evidence_json') or {}).get('expected_qb_package')
        for field, value in {"pregame_context_source": context.get("source"), "pregame_context_run_id": context.get("context_run_id"),
                             "pregame_context_observed_at": context.get("observed_at"), "pregame_injury_status": context.get("injury_status"),
                             "expected_depth_role": evidence.get("canonical_role")}.items():
            rows.at[index, field] = value
    rows.attrs = attributes
    rows.attrs["role_context"] = deepcopy(contexts)
    return rows


def retained_workload_context(context):
    """Preserve DB-loaded source clocks as JSON evidence, without renewing them."""
    result = deepcopy(context)
    for field in ("observed_at", "received_at"):
        if isinstance(result.get(field), datetime):
            result[field] = result[field].isoformat()
    return result


def _positive_salary(value):
    from math import isfinite
    try:
        return isfinite(float(value)) and float(value) > 0
    except (TypeError, ValueError):
        return False


def assess_availability(row, *, cutoff, evaluated_at, max_age_hours):
    """Only current canonical affirmative evidence permits exclusion/eligibility."""
    if row.get("position") == "DST":
        return "AVAILABLE", []
    if row.get("canonical_context_contract") != CONTEXT_CONTRACT:
        # Archived/offline contracts retain their original assessment. Normal
        # live collectors always write the canonical contract before scoring.
        return "AVAILABLE", []
    reasons = [r for r in row.get("canonical_context_reason_codes") or [] if r.startswith("player_status")]
    state = row.get("availability_state", "UNKNOWN")
    try:
        observed = aware(row["availability_observed_at"])
        if observed > aware(cutoff) or observed > aware(evaluated_at):
            reasons.append("player_status_after_cutoff")
        if (aware(evaluated_at) - observed).total_seconds() > max_age_hours * 3600:
            reasons.append("player_status_stale")
    except (KeyError, ValueError, TypeError, AttributeError):
        reasons.append("player_status_missing")
    if not row.get("availability_source") or not row.get("availability_source_ids") or state not in {"AVAILABLE", "UNAVAILABLE"}:
        reasons.append("player_status_missing")
    return ("UNKNOWN" if reasons else state), sorted(set(reasons))


def player_pool_diagnostic(rows, *, readiness=None):
    """One auditable disposition for every native player; no postgame fields."""
    players = []
    for r in rows:
        state = r.get("availability_state") or ("AVAILABLE" if r.get("position") == "DST" else "UNKNOWN")
        if readiness:
            state, status_reasons = assess_availability(r, cutoff=readiness["evidence_cutoff"],
                evaluated_at=readiness["evaluated_at"], max_age_hours=readiness["required_sources"]["player_status"]["max_age_hours"])
        else:
            status_reasons = []
        specialist = bool(readiness and is_excluded_specialist(r, cutoff=readiness["evidence_cutoff"],
            evaluated_at=readiness["evaluated_at"], max_age_hours=readiness["required_sources"]["player_status"]["max_age_hours"]))
        invalid = not (r.get("player_id") and r.get("identity_resolved") is True and r.get("position") in {"QB", "RB", "WR", "TE", "K", "DST"}
                       and r.get("dk_player_id") and r.get("dk_captain_id") and r.get("salary_source_row_id")
                       and _positive_salary(r.get("salary")))
        disposition = ("invalid_salary_or_identity" if invalid else "explicitly_unavailable" if state == "UNAVAILABLE"
                       else "unknown_availability" if state == "UNKNOWN" else "explicitly_excluded_specialist" if specialist
                       else "generation_eligible")
        blockers = list(r.get("canonical_context_reason_codes") or []) + status_reasons
        if invalid: blockers.append("salary_pool_missing")
        market = bool(r.get("market_context_point_in_time_safe") and all(r.get(k) is not None for k in ("team_spread_line", "game_total_line", "team_implied_total")))
        feature = bool(r.get("feature_inputs_complete", r.get("projection_inputs_complete", r.get("projection_run_id"))))
        projection = bool(r.get("projection_inputs_complete", r.get("projection_run_id")))
        if disposition == "generation_eligible":
            if not market: blockers.append("market_missing")
            if not feature: blockers.append("feature_missing")
            if not projection: blockers.append("projection_missing")
        for name,check in ((readiness or {}).get("required_sources") or {}).items():
            if name in {"player_status", "projection"}:
                continue
            if str(r.get("player_id")) in check.get("affected_player_ids", []):
                blockers.extend(check["reason_codes"])
        players.append({"player": r.get("player_name") or r.get("name"), "team": r.get("player_team") or r.get("team"),
            "position": r.get("position"), "canonical_id": r.get("player_id"), "canonical_identity_resolved": r.get("identity_resolved") is True,
            "dfs_position": r.get("dfs_position") or r.get("position"), "canonical_role": r.get("canonical_role"),
            "role_source_position": r.get("role_source_position"),
            "salary_row_id": r.get("salary_source_row_id"), "availability_state": state,
            "dk_player_id": r.get("dk_player_id"), "dk_captain_id": r.get("dk_captain_id"),
            "status": r.get("availability_status"), "status_source": r.get("availability_source"), "status_observed_at": r.get("availability_observed_at"),
            "status_source_ids": r.get("availability_source_ids") or [], "role": r.get("canonical_role") or r.get("expected_depth_role"),
            "role_source": r.get("role_source"), "role_observed_at": r.get("role_observed_at"), "role_source_ids": r.get("role_source_ids") or [],
            "starting_qb": r.get("is_starting_qb") is True, "disposition": disposition, "generation_eligible": disposition == "generation_eligible",
            "exclusion_reason": (f"sourced_{r.get('availability_status')}" if disposition == "explicitly_unavailable" else
                                 "unsupported_non_scoring_specialist_role" if disposition == "explicitly_excluded_specialist" else None),
            "market_ready": market, "market_snapshot_id": r.get("market_snapshot_row_id"), "canonical_game_id": r.get("canonical_game_id"),
            "feature_ready": feature, "projection_ready": projection, "projection_run_id": r.get("projection_run_id"),
            "ownership_ready": r.get("captain_ownership") is not None and r.get("flex_ownership") is not None,
            "ownership_required": bool((readiness or {}).get("ownership", {}).get("required")), "blockers": sorted(set(blockers))})
    eligible = [p for p in players if p["generation_eligible"]]
    return {"contract_id": "showdown_player_pool_readiness_v1",
        "status": (readiness or {}).get("status"), "readiness_blockers": (readiness or {}).get("reason_codes", []),
        "projection_build_status": ((readiness or {}).get("refresh", {}).get("projection") or {}).get("status"),
        "summary": {
        "native_salary_players": len(players), "canonical_resolved": sum(p["canonical_identity_resolved"] for p in players),
        "explicitly_unavailable": sum(p["disposition"] == "explicitly_unavailable" for p in players),
        "explicitly_excluded_specialist": sum(p["disposition"] == "explicitly_excluded_specialist" for p in players),
        "generation_eligible": len(eligible), "unknown_availability": sum(p["disposition"] == "unknown_availability" for p in players),
        "invalid_salary_or_identity": sum(p["disposition"] == "invalid_salary_or_identity" for p in players),
        "projection_rows_required": len(eligible), "projection_rows_present": sum(p["projection_ready"] for p in eligible),
        "feature_rows_present": sum(p["feature_ready"] for p in eligible), "market_rows_present": sum(p["market_ready"] for p in eligible)}, "players": players}


def match_source_player(row, key, source_lookup, salary_lookup):
    """Native source ID plus team resolves identity before position labels."""
    matches = [pid for pid in source_lookup.get(str(key), set()) if
               normalize_team(str(salary_lookup[pid]["team"])) == normalize_team(str(row.get("team") or ""))]
    return matches[0] if len(matches) == 1 else None


def transferred_roster_facts(rows, source_lookup, salary_lookup, *, cutoff):
    """An exclusive current native-ID roster assignment invalidates the old team.

    Never turn a name match or roster absence into an exclusion. Conflicting
    latest assignments and ambiguous native aliases remain unresolved.
    """
    by_key = {}
    for row in rows:
        if (row.get('observed_at') and row.get('received_at') and row.get('snapshot_id')
                and aware(row['observed_at']) <= cutoff and aware(row['received_at']) <= cutoff):
            by_key.setdefault(str(row['gsis_id']), []).append(row)
    facts = []
    for key, history in by_key.items():
        ids = source_lookup.get(key, set())
        if len(ids) != 1:
            continue
        pid = next(iter(ids))
        salary = salary_lookup.get(pid)
        if not salary:
            continue
        newest = max(aware(r['observed_at']) for r in history)
        latest = [r for r in history if aware(r['observed_at']) == newest]
        assignments = {(normalize_team(str(r['team'])), normalize_position(str(r['position'])),
                        normalize_salary_status(r['roster_status'])) for r in latest}
        if len(assignments) != 1:
            continue
        team, position, status = next(iter(assignments))
        if (not team or team == normalize_team(salary['team'])
                or position != normalize_position(salary['position']) or status not in {'ACT', 'ACTIVE'}):
            continue
        row = max(latest, key=lambda r: aware(r['received_at']))
        facts.append(dict(player_id=pid, team=salary['team'], position=salary['position'],
            source_position=position, kind='roster_status', status='CUT',
            source='nflreadpy_weekly_roster_team_transfer', current_team=team,
            observed_at=newest.isoformat(), received_at=aware(row['received_at']).isoformat(),
            source_ids=[str(row['snapshot_id']), str(row['raw_nfl_weekly_roster_id']), key],
            source_uri=row['source_uri'], observation_basis='exclusive_native_id_roster_assignment_to_other_team'))
    return facts


def shared_sunday_source_facts(connection, *, season, week, slate, cutoff, salaries):
    """Reuse Main's original football evidence, never its derived assessments."""
    from .pregame_context import load_current_pregame_context

    if slate.upper() not in SUNDAY_SUBSETS:
        return []
    members = {(str(s['player_id']), normalize_team(s['team']), s['position'].upper()) for s in salaries}
    contexts = load_current_pregame_context(connection, season=season, week=week,
        slate='SUNDAY_MAIN', cutoff=cutoff, include_source_history=True)
    facts = {}
    for context in contexts:
        evidence = context.get('evidence_json') or {}
        if evidence.get('canonical_context_contract') != CONTEXT_CONTRACT:
            continue
        for fact in evidence.get('source_facts', []):
            member = (str(fact.get('player_id')), normalize_team(str(fact.get('team') or '')),
                      str(fact.get('position') or '').upper())
            if member in members and _visible(fact, cutoff):
                facts[json.dumps(fact, sort_keys=True, default=str)] = fact
    return list(facts.values())


def refresh_canonical_context(engine, *, season, week, slate, cutoff=None):
    """Normalize existing canonical/snapshot sources; persist through context API."""
    from ..services.source_capture import SourceCaptureService, fetch_nflreadpy_dataset, DEFAULT_NFLREADPY_LICENSE
    from .pregame_context import PregameContextService, load_current_pregame_context
    from .slate_preparation import SlatePreparationRequest, slate_games, require_prelock
    import pandas as pd
    from ..config import get_settings

    cutoff = aware(cutoff or datetime.now(UTC))
    params = {"season": season, "week": week, "slate": slate, "cutoff": cutoff}
    with engine.connect() as connection:
        salaries = [dict(r) for r in connection.execute(text("""
            SELECT DISTINCT ON (s.player_master_id) s.player_master_id AS player_id, s.player_name, s.team, s.position,
                   s.player_status, s.curated_salary_id AS salary_source_row_id, s.ingest_run_id,
                   COALESCE(snapshot.observed_at,s.created_at AT TIME ZONE 'UTC') AS observed_at,
                   s.created_at AT TIME ZONE 'UTC' AS received_at, snapshot.snapshot_id
            FROM public.curated_salary s
            LEFT JOIN LATERAL (
                SELECT ss.snapshot_id,ss.observed_at FROM public.source_snapshot_ingest_run link
                JOIN public.source_snapshot ss USING(snapshot_id)
                WHERE link.ingest_run_id=s.ingest_run_id AND ss.observed_at <= :cutoff AND ss.captured_at <= :cutoff
                ORDER BY ss.captured_at,ss.snapshot_id LIMIT 1
            ) snapshot ON TRUE
            WHERE s.season=:season AND s.week=:week AND LOWER(s.slate)=LOWER(:slate)
              AND s.source_system='draftkings' AND s.player_master_id IS NOT NULL AND s.created_at AT TIME ZONE 'UTC' <= :cutoff
            ORDER BY s.player_master_id, CASE WHEN s.roster_position='FLEX' THEN 0 ELSE 1 END, s.created_at DESC, s.curated_salary_id DESC
        """), params).mappings()]
        aliases = [dict(r) for r in connection.execute(text("""
            SELECT player_master_id, source_system, source_key FROM public.player_alias
            WHERE source_system IN ('nflreadpy','nflverse') AND player_master_id=ANY(:ids)
        """), {"ids": [r["player_id"] for r in salaries]}).mappings()]
        # A newly received source report may have an earlier publication clock
        # than the latest derived context's role clock. Merge original facts;
        # selecting only one context would hide that valid status supplement.
        contexts = load_current_pregame_context(connection, **params, include_source_history=True)
        shared_facts = shared_sunday_source_facts(connection, **params, salaries=salaries)
        roster_rows = [dict(r) for r in connection.execute(text("""
            SELECT roster.gsis_id, roster.team, roster.position, roster.roster_status,
                   roster.raw_nfl_weekly_roster_id, snapshot.snapshot_id, snapshot.observed_at, snapshot.captured_at AS received_at,
                   snapshot.source_uri FROM public.raw_nfl_weekly_roster roster
            JOIN public.source_snapshot_ingest_run link USING(ingest_run_id)
            JOIN public.source_snapshot snapshot USING(snapshot_id)
            JOIN public.ingest_run ingest ON ingest.ingest_run_id=roster.ingest_run_id AND ingest.status='completed'
            WHERE roster.season=:season AND roster.week=:week AND roster.created_at AT TIME ZONE 'UTC' <= :cutoff
              AND snapshot.observed_at <= :cutoff AND snapshot.captured_at <= :cutoff
        """), params).mappings()]
        injuries = [dict(r) for r in connection.execute(text(f"""
            SELECT i.player_master_id AS player_id,i.team,i.position,i.injury_status,i.curated_injury_id,
                   i.created_at AT TIME ZONE 'UTC' AS received_at,
                   COALESCE(snapshot.observed_at,i.created_at AT TIME ZONE 'UTC') AS observed_at,
                   snapshot.snapshot_id,run.source_path AS source_uri,i.source_system
            FROM public.curated_injury i JOIN public.ingest_run run USING(ingest_run_id)
            LEFT JOIN public.source_snapshot_ingest_run link USING(ingest_run_id)
            LEFT JOIN public.source_snapshot snapshot USING(snapshot_id)
            WHERE i.season=:season AND i.week=:week AND {injury_slate_sql('i.slate')} AND run.status='completed'
              AND {injury_subset_membership_sql('i.player_master_id', 'i.team')}
        """), params).mappings()]
        raw_injury_snapshots = [dict(r) for r in connection.execute(text("""
            SELECT * FROM public.source_snapshot WHERE season=:season AND week=:week AND dataset='injuries'
              AND LOWER(slate)=LOWER(:slate) AND observed_at <= :cutoff AND captured_at <= :cutoff
            ORDER BY captured_at DESC LIMIT 1
        """), params).mappings()]
        starters = [dict(r) for r in connection.execute(text("""
            SELECT * FROM public.starting_qb_evidence WHERE season=:season AND week=:week AND LOWER(slate)=LOWER(:slate)
              AND created_at AT TIME ZONE 'UTC' <= :cutoff
        """), params).mappings()]
    salary_lookup = {r["player_id"]: r for r in salaries}
    source_lookup = {}
    for alias in aliases:
        source_lookup.setdefault(alias["source_key"], set()).add(alias["player_master_id"])
    facts = transferred_roster_facts(roster_rows, source_lookup, salary_lookup, cutoff=cutoff)
    facts.extend(shared_facts)
    def add(row, *, pid, kind, source, status=None, role=None, observed=None, received=None, ids=(), uri=None, **extra):
        if pid not in salary_lookup: return
        facts.append({"player_id": pid, "team": normalize_team(str(row.get("team") or "")),
                      "position": str(salary_lookup[pid].get("position") or "").upper(),
                      "source_position": str(row.get("position") or "").upper(), "kind": kind, "source": source,
                      "status": normalize_salary_status(status), "role": role,
                      "observed_at": aware(observed).isoformat() if observed else None,
                      "received_at": aware(received).isoformat() if received else None,
                      "source_ids": [str(i) for i in ids if i is not None], "source_uri": uri, **extra})
    def match(row, key):
        return match_source_player(row,key,source_lookup,salary_lookup)
    for r in salaries:
        status = normalize_salary_status(r["player_status"])
        if status:
            add(r, pid=r["player_id"], kind="roster_status" if status in {"IR","PUP","NFI","PS","PRA","DEV","RES","RESERVE"} else "game_status",
                source="draftkings_salary_status", status=status, observed=r["observed_at"], received=r["received_at"],
                ids=[r["salary_source_row_id"],r["ingest_run_id"],r["snapshot_id"]],uri="football26://native-salary-import")
    for r in roster_rows:
        add(r,pid=match(r,r["gsis_id"]),kind="roster_status",source="nflreadpy_weekly_rosters",status=r["roster_status"],
            observed=r["observed_at"],received=r["received_at"],ids=[r["snapshot_id"],r["raw_nfl_weekly_roster_id"]],uri=r["source_uri"])
    for r in injuries:
        add(r,pid=r["player_id"],kind="injury_status",source=r["source_system"],status=r["injury_status"],
            observed=r["observed_at"],received=r["received_at"],ids=[r["curated_injury_id"],r["snapshot_id"]],uri=r["source_uri"])
    for snapshot in raw_injury_snapshots:
        frame = pd.read_csv(snapshot["artifact_path"])
        for r in frame.to_dict("records"):
            add(r,pid=match(r,r.get("gsis_id")),kind="injury_status",source="nflreadpy_injuries",status=r.get("report_status"),
                observed=snapshot["observed_at"],received=snapshot["captured_at"],ids=[snapshot["snapshot_id"],r.get("gsis_id")],uri=snapshot["source_uri"])
    # Preserve independent manually sourced context facts/workload fields. A
    # previous derived context is never treated as a fresh external observation.
    previous = {}
    for r in contexts:
        e = r.get("evidence_json") or {}
        if e.get("canonical_context_contract") == CONTEXT_CONTRACT:
            facts.extend(e.get("source_facts", []))
            previous.setdefault(str(r["player_master_id"]), e.get("workload_context", {}))
            continue
        previous.setdefault(str(r["player_master_id"]), r)
        add(r,pid=r["player_master_id"],kind="game_status",source=r["source"],status=r.get("injury_status") or ("ACTIVE" if e.get("game_active") is True else "INACTIVE" if e.get("game_active") is False or r.get("availability_probability") == 0 else None),
            observed=r["observed_at"],received=r["received_at"],ids=[r["context_run_id"],r["pregame_player_context_id"]],uri=r.get("source_uri"),game_active=e.get("game_active"))
        role = e.get("expected_depth_role") or {"STARTER":"expected_starter","LEAD":"expected_starter","PRIMARY":"expected_starter","BACKUP":"expected_backup","SECONDARY":"expected_backup","ROTATION":"rotation","COMMITTEE":"rotation"}.get(r.get("role_label"))
        if role: add(r,pid=r["player_master_id"],kind="role",source=r["source"],role=role,observed=r["observed_at"],received=r["received_at"],ids=[r["context_run_id"],r["pregame_player_context_id"]],uri=r.get("source_uri"))
    depth_error = None
    try:
        depth,version = fetch_nflreadpy_dataset("depth_charts",season=season,week=None)
        depth["observed_at"] = pd.to_datetime(depth["dt"],utc=True,errors="coerce")
        teams = {normalize_team(r["team"]) for r in salaries}
        depth = depth.loc[depth["team"].map(normalize_team).isin(teams) & depth["observed_at"].notna() & depth["observed_at"].le(cutoff)].copy()
        depth = depth.loc[depth["observed_at"].eq(depth.groupby("team")["observed_at"].transform("max"))]
        with Session(engine) as session:
            games = slate_games(session,SlatePreparationRequest(season=season,week=week,slate=slate,action="rebuild"))
            capture = SourceCaptureService(session).capture_dataframe(depth.drop(columns="observed_at"),
                artifact_name=f"nflverse_player_depth_{season}_{week}_{slate}.csv",source_system="nflreadpy",dataset="player_depth_charts",
                season=season,week=week,slate=slate,source_license=DEFAULT_NFLREADPY_LICENSE,
                source_uri=f"nflreadpy://depth_charts/{season}",slate_lock_at=require_prelock(games),metadata={"nflreadpy_version":version})
        for r in depth.to_dict("records"):
            r["position"] = str(r.get("pos_abb") or "").upper().replace("PK","K")
            if pd.isna(r.get("pos_rank")): continue
            pid = match(r,r.get("gsis_id"))
            if pid is None: continue
            kind, role = sourced_depth_role(r["position"], salary_lookup[pid]["position"], r["pos_rank"])
            add(r,pid=pid,kind=kind,source="nflreadpy_depth_charts",role=role,
                observed=r["dt"],received=capture.snapshot.captured_at,ids=[capture.snapshot.snapshot_id,r.get("gsis_id")],uri=capture.snapshot.source_uri)
    except (OSError,RuntimeError,ValueError,KeyError) as exc:
        depth_error = f"{type(exc).__name__}: {exc}"
    # Capture receipt is after our initial read. Set the transform cutoff once
    # all source reads complete; nested facts still retain their original clocks.
    cutoff = datetime.now(UTC)
    for r in starters:
        e = r.get("evidence_json") or {}
        salary = salary_lookup.get(str(r["player_master_id"]))
        if salary and e.get("observed_at"):
            add(salary,pid=salary["player_id"],kind="starting_qb",source=r["source"],role="expected_starter",
                observed=e["observed_at"],received=r["created_at"],ids=[r["starting_qb_id"]],uri=e.get("source_uri"))
    # Deduplicate retained original facts instead of recursively growing lineage.
    import json
    facts = list({json.dumps(f,sort_keys=True,default=str):f for f in facts}.values())
    contexts = compose_player_contexts(salaries,facts,cutoff=cutoff,max_age_hours=get_settings().showdown_player_status_max_age_hours)
    service = PregameContextService(engine=engine); run_ids = []
    for context in contexts:
        old = previous.get(context["player_id"],{})
        context["evidence_json"]["workload_context"] = retained_workload_context(old)
        for key in ("role_uncertain", "newly_assigned_role", "depth_chart_conflict", "practice_report", "expected_qb_package", "role_change"):
            if key in (old.get("evidence_json") or {}):
                context["evidence_json"][key] = deepcopy(old["evidence_json"][key])
        practice = context["evidence_json"].get("practice_report") or {}
        if practice.get("observed_at"):
            # The containing record must include the latest retained fact clock;
            # independent availability/role clocks stay unchanged for freshness.
            practice_at = aware(practice["observed_at"])
            if practice_at <= cutoff:
                context["observed_at"] = max(aware(context["observed_at"]), practice_at)
        player = {"player_id":context["player_id"],"injury_status":context["injury_status"],"role_label":context["role_label"],"evidence":context["evidence_json"]}
        old_is_current = bool(old.get("observed_at") and old.get("received_at") and
            aware(old["observed_at"]) <= cutoff and aware(old["received_at"]) <= cutoff and
            (cutoff-aware(old["observed_at"])).total_seconds() <= get_settings().showdown_player_status_max_age_hours*3600)
        for field in ("availability_probability","start_probability","carry_share","target_share","expected_snaps","expected_routes","expected_carries","expected_targets","red_zone_share","goal_line_share"):
            player[field] = context.get(field) if context.get(field) is not None else old.get(field) if old_is_current else None
        run = service.create_run({"season":season,"week":week,"slate":slate,"source":CONTEXT_CONTRACT,
            "source_uri":context["source_uri"],"observed_at":context["observed_at"],"players":[player]})
        run_ids.append(run["context_run_id"])
    return {"context_run_ids":sorted(set(run_ids)),"rows":len(contexts),"availability_counts":{s:sum(c["evidence_json"]["availability_state"]==s for c in contexts) for s in ("AVAILABLE","UNAVAILABLE","UNKNOWN")},
            "depth_error":depth_error,"source_fact_count":len(facts)}
