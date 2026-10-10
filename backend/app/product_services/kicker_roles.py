"""Point-in-time kicking duties, separate from salary and historical ability."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
from sqlalchemy import inspect, text

from Database.dst import normalize_team

VERSION = "kicker_role_gate_v1"
LINEAGE_COLUMNS = ["kicker_role", "kicker_role_eligible", "kicker_role_reason",
                   "kicker_role_evidence", "kicker_role_warning"]
INACTIVE = {"DEV", "PS", "PRA", "IR", "RES", "PUP", "NFI", "OUT", "INACTIVE", "SUSP"}


def load_kicker_evidence(engine, *, season: int, week: int, slate: str,
                         cutoff: datetime) -> dict[str, Any]:
    """Read immutable canonical evidence; never fetch today's chart for a replay."""
    result: dict[str, Any] = {"rosters": [], "usage": [], "context": [],
                             "cutoff": pd.Timestamp(cutoff).isoformat()}
    if engine.dialect.name != "postgresql":
        return result
    inspector = inspect(engine)
    params = {"season": season, "week": week, "slate": slate, "cutoff": cutoff}
    with engine.connect() as connection:
        if inspector.has_table("player_alias", schema="public"):
            if inspector.has_table("raw_nfl_weekly_roster", schema="public"):
                result["rosters"] = [dict(row) for row in connection.execute(text("""
                    SELECT DISTINCT ON (r.team, r.gsis_id)
                        a.player_master_id::TEXT AS player_id, r.team,
                        r.roster_status, r.depth_chart_position,
                        r.raw_nfl_weekly_roster_id AS evidence_id, r.created_at
                    FROM public.raw_nfl_weekly_roster r
                    JOIN public.player_alias a ON a.source_system = r.source_system
                      AND a.source_key = r.gsis_id
                    WHERE r.season = :season AND r.week = :week AND r.position = 'K'
                      AND r.created_at AT TIME ZONE 'UTC' <= :cutoff
                    ORDER BY r.team, r.gsis_id, r.created_at DESC,
                             r.raw_nfl_weekly_roster_id DESC
                """), params).mappings()]
            if inspector.has_table("raw_nfl_weekly_stat", schema="public"):
                result["usage"] = [dict(row) for row in connection.execute(text("""
                    SELECT DISTINCT ON (r.team, r.week, r.player_id)
                        a.player_master_id::TEXT AS player_id, r.team, r.week,
                        COALESCE(NULLIF(r.raw_row_json ->> 'fg_att', '')::FLOAT, 0) +
                        COALESCE(NULLIF(r.raw_row_json ->> 'pat_att', '')::FLOAT, 0) AS attempts,
                        r.raw_nfl_weekly_stat_id AS evidence_id, r.created_at
                    FROM public.raw_nfl_weekly_stat r
                    JOIN public.player_alias a ON a.source_system = r.source_system
                      AND a.source_key = r.player_id
                    WHERE r.season = :season AND r.week < :week
                      AND r.week >= :week - 3 AND r.position = 'K'
                      AND r.created_at AT TIME ZONE 'UTC' <= :cutoff
                    ORDER BY r.team, r.week, r.player_id, r.created_at DESC,
                             r.raw_nfl_weekly_stat_id DESC
                """), params).mappings()]
        if inspector.has_table("pregame_player_context", schema="public"):
            from .pregame_context import load_current_pregame_context
            result["context"] = [row for row in load_current_pregame_context(
                connection, season=season, week=week, slate=slate, cutoff=cutoff
            ) if row.get("position") == "K"]
    # Serialized evidence travels with frozen pools and persisted feature lineage.
    for rows in (result["rosters"], result["usage"], result["context"]):
        for row in rows:
            for key, value in row.items():
                if isinstance(value, datetime):
                    row[key] = value.isoformat()
    return result


def assign_kicker_roles(frame: pd.DataFrame, evidence: dict | None = None
                        ) -> tuple[pd.DataFrame, dict]:
    """Resolve across all team evidence, including kickers absent from salaries.

    Explicit sourced duties override a roster assumption. Otherwise use a unique
    K1, unique active-roster kicker, or unique most-recent prior-game kicker.
    Missing/conflicting identities fail closed; salary never breaks a tie.
    """
    rows = frame.copy()
    evidence = evidence or rows.attrs.get("kicker_evidence", {})
    report = {"version": VERSION, "teams": [], "warnings": [], "excluded_player_ids": []}
    for column, default in zip(LINEAGE_COLUMNS, [None, True, None, None, None]):
        rows[column] = default
    if rows.empty or "position" not in rows:
        return rows, report
    mask = rows["position"].astype(str).str.upper().eq("K")
    team_col = "player_team" if "player_team" in rows else "recent_team"
    if team_col not in rows:
        team_col = "team"
    team_keys = rows.get(team_col, pd.Series("", index=rows.index)).map(normalize_team)
    cutoff = pd.to_datetime(evidence.get("cutoff"), utc=True, errors="coerce")
    from .replay import parse_slate_lock
    lock = parse_slate_lock(rows.get("game_info", rows.get("game_id", pd.Series(dtype=str))))
    if lock is not None and pd.notna(cutoff):
        cutoff = min(cutoff, pd.Timestamp(lock))

    def visible(record):
        times = [record.get(k) for k in ("created_at", "observed_at", "received_at") if record.get(k)]
        return pd.notna(cutoff) and bool(times) and all(
            pd.notna(at := pd.to_datetime(value, utc=True, errors="coerce")) and at <= cutoff
            for value in times)

    for team in sorted(set(team_keys.loc[mask])):
        indexes = rows.index[mask & team_keys.eq(team)]
        rosters = [r for r in evidence.get("rosters", [])
                   if normalize_team(r.get("team")) == team and visible(r)]
        usage = [r for r in evidence.get("usage", [])
                 if normalize_team(r.get("team")) == team and visible(r) and float(r.get("attempts") or 0) > 0]
        contexts = [r for r in evidence.get("context", [])
                    if normalize_team(r.get("team")) == team and visible(r)]
        statuses = {str(r["player_id"]): str(r.get("roster_status") or "").upper() for r in rosters}
        explicit, shared, denied = set(), set(), set()
        for context in contexts:
            pid = str(context.get("player_master_id") or context.get("player_id"))
            facts = context.get("evidence_json") or {}
            role = str(facts.get("kicker_role") or context.get("role_label") or "").lower()
            sourced = bool(context.get("source") and (context.get("source_uri") or facts.get("source_uris")))
            if context.get("availability_probability") == 0 or facts.get("expected_kicking_duties") is False:
                denied.add(pid)
            elif sourced and role in {"primary_kicker", "starting_kicker", "k1", "primary", "starter", "starting"}:
                explicit.add(pid)
            elif sourced and facts.get("expected_kicking_duties") is True:
                shared.add(pid)
            elif role in {"backup_kicker", "backup"}:
                denied.add(pid)
        available = lambda pid: pid not in denied and statuses.get(pid) not in INACTIVE
        # Pregame replacement duties may supersede a development designation,
        # but never an IR/PUP/NFI/out designation without activation evidence.
        hard_unavailable = {"IR", "RES", "PUP", "NFI", "OUT", "INACTIVE", "SUSP"}
        explicit = {pid for pid in explicit if pid not in denied and statuses.get(pid) not in hard_unavailable}
        shared = {pid for pid in shared if pid not in denied and statuses.get(pid) not in hard_unavailable}
        ranked = {str(r["player_id"]) for r in rosters
                  if str(r.get("depth_chart_position") or "").upper() in {"K1", "STARTER", "STARTING"}
                  and available(str(r["player_id"]))}
        active = {pid for pid, status in statuses.items() if status == "ACT" and pid not in denied}
        recent = set()
        if usage:
            last_week = max(int(r["week"]) for r in usage)
            recent = {str(r["player_id"]) for r in usage if int(r["week"]) == last_week and available(str(r["player_id"]))}
        primary, reason, warning = None, "kicker_primary_uncertain", None
        if explicit:
            candidates, reason = explicit, "sourced_pregame_primary_kicker"
        elif ranked:
            candidates, reason = ranked, "current_depth_chart_k1"
        elif len(active) == 1:
            candidates, reason = active, "unique_current_active_roster_kicker"
        else:
            candidates, reason = recent, "recent_prior_kicking_usage"
        if len(candidates) == 1:
            primary = next(iter(candidates))
            if reason == "recent_prior_kicking_usage":
                warning = f"{team}: primary kicker inferred from recent usage; confirm current pregame duties."
        else:
            reason = "kicker_primary_uncertain"
            warning = f"{team}: primary kicker identity uncertain/conflicting; unresolved kickers excluded. Supply sourced pregame duties."
        allowed = ({primary} if primary else set()) | shared
        consumed = {"rosters": rosters, "usage": usage, "context": contexts,
                    "cutoff": evidence.get("cutoff"), "primary_player_id": primary}
        report["teams"].append({"team": team, "primary_player_id": primary,
                                "allowed_player_ids": sorted(allowed), "reason": reason,
                                "evidence": consumed})
        if warning:
            report["warnings"].append(warning)
        for index in indexes:
            pid = str(rows.at[index, "player_id"])
            eligible = pid in allowed and pid not in denied
            rows.at[index, "kicker_role"] = "primary" if pid == primary else "explicit_duties" if eligible else "backup" if primary else "uncertain"
            rows.at[index, "kicker_role_eligible"] = eligible
            rows.at[index, "kicker_role_reason"] = reason if pid == primary else "sourced_pregame_kicking_duties" if eligible else "backup_kicker_without_expected_duties" if primary else "kicker_primary_uncertain"
            rows.at[index, "kicker_role_evidence"] = consumed
            rows.at[index, "kicker_role_warning"] = warning
            if not eligible:
                report["excluded_player_ids"].append(pid)
    rows.attrs["kicker_role_gate"] = report
    return rows, report
