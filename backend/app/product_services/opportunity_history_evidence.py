"""Shared original-count history contract; no forecasts or preference filters.

This adapter describes the source universe used by count inference. It does not
turn missing participants into zero, treat allocated proxies as observations, or
assert that revised historical sources existed at their original game locks.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from Database.player_identity import normalize_position

VERSION = "opportunity_history_evidence_v1"
CHANNELS = ("pass_attempts", "rush_attempts", "targets")
POSITIONS = {"QB", "RB", "WR", "TE"}


def _records(frame):
    # JSON converts NaN/NaT to null and numpy scalars to normal JSON values.
    return json.loads(frame.to_json(orient="records"))


def source_history(weekly, *, before_period, cutoff=None):
    """Validate original source grain and retain unmapped actors in the budget.

    Imported-at is a present availability bound, not original pregame proof.
    Caller must supply the full source actor universe, not a salary subset.
    """
    rows = weekly.loc[weekly.period < before_period].copy()
    rows["position"] = rows.position.map(normalize_position)
    if rows.loc[rows.player_master_id.notna()].duplicated(["player_master_id", "period"]).any():
        raise ValueError("Duplicate canonical player-game workload rows")
    if "source_player_id" in rows:
        if rows.duplicated(["source_player_id", "period"]).any():
            raise ValueError("Duplicate native player-game workload rows")
    for channel in CHANNELS:
        numeric = pd.to_numeric(rows[channel], errors="coerce")
        if ((numeric.dropna() < 0).any() or numeric.isin([float("inf"), float("-inf")]).any()
                or (rows[channel].notna() & numeric.isna()).any()):
            raise ValueError(f"Invalid original count: {channel}")
        rows[channel] = numeric
    if cutoff is not None and "imported_at" in rows:
        clocks = pd.to_datetime(rows.imported_at, utc=True, errors="coerce")
        if (rows.imported_at.notna() & clocks.isna()).any():
            raise ValueError("Invalid original history import clock")
        if (clocks > pd.to_datetime(cutoff, utc=True)).any():
            raise ValueError("Original history imported after decision cutoff")
    return rows.sort_values(["period", "team", "player_master_id"], kind="stable")


def team_history(weekly):
    """Conserved observed channels, including unmapped and FB-normalized rows."""
    records = []
    for (period, team), rows in weekly.groupby(["period", "team"], sort=True):
        rows = rows.loc[rows.position.isin(POSITIONS)]
        record = {"period": int(period), "team": team}
        for channel in CHANNELS:
            values = rows[channel]
            record[channel] = float(values.sum()) if len(values) and values.notna().all() else float("nan")
        records.append(record)
    return pd.DataFrame(records, columns=["period", "team", *CHANNELS])


def select_role_window(weekly, actor, games, *, before_period, verified_gaps=()):
    """Conditional-active window; sparse returns require closed absence evidence.

    Current-role evidence must already have passed the Prepare canonical clock
    and role checks. This helper cannot infer a current role from salary presence.
    Primary NOT_ACTIVE gaps are retained as facts, never measured zero counts.
    """
    pid = str(actor["player_master_id"]); team = actor["team"]
    history = weekly.loc[weekly.player_master_id.astype(str).eq(pid)].sort_values("period")
    same = history.loc[history.team.eq(team)].tail(3)
    info = {"status": "unknown", "reason": None, "verified_inactive_gaps": [],
            "missing_periods": [], "current_role_evidence": actor.get("current_role_evidence"),
            "current_role_validation": "upstream Prepare required; not inferred here"}
    if history.empty or history.iloc[-1].team != team or len(same) < 2:
        info["reason"] = "insufficient supported same-team role or team volume"
        return same, info
    recent = games.loc[games.team.eq(team)].sort_values("period").tail(3)
    if len(same) < 3 or same.period.tolist() != recent.period.tolist():
        window = games.loc[games.team.eq(team) & games.period.between(int(same.iloc[0].period), int(recent.iloc[-1].period))]
        missing = set(window.period) - set(same.period)
        proof = [g for g in verified_gaps if g.get("kind") in {"official_gamebook_not_active_v1", "official_ir_interval_v1"}
                 and g.get("player_master_id") == pid and g.get("team") == team and g.get("period") in missing]
        info["missing_periods"] = sorted(int(p) for p in missing)
        role = actor.get("current_role_evidence") or {}
        if (int(same.iloc[-1].period) != int(recent.iloc[-1].period)
                or any(int(p)//100 != before_period//100 for p in same.period)
                or not role.get("source_ids") or not role.get("source_uri")
                or not missing or set(g["period"] for g in proof) != missing):
            info["reason"] = "missing participant in recent team-game window; no complete primary inactive/current-role proof"
            return same, info
        info["verified_inactive_gaps"] = proof
        info["status"] = ("sparse_two_active_games_across_verified_inactive_gaps" if len(same) == 2
                          else "observed_active_games_across_verified_inactive_gaps")
        info["observed_game_count"] = len(same)
    else:
        info["status"] = "observed_recent_team_games"
    return same, info


def build_history_evidence(weekly, actors, *, before_period, verified_gaps=(), cutoff=None):
    """Freeze an auditable full-source measurement view for existing consumers."""
    rows = source_history(weekly, before_period=before_period, cutoff=cutoff)
    if len({str(a["player_master_id"]) for a in actors}) != len(actors):
        raise ValueError("Duplicate canonical forecast actors")
    games = team_history(rows)
    teams = {}
    for team in sorted({a["team"] for a in actors}):
        recent = games.loc[games.team.eq(team)].tail(8)
        coverage = []
        for period in recent.period:
            group = rows.loc[rows.team.eq(team) & rows.period.eq(period) & rows.position.isin(POSITIONS)]
            unmapped = group.loc[group.player_master_id.isna()]
            coverage.append({"period": int(period), "source_actor_rows": len(group),
                "unmapped_source_actor_rows": len(unmapped),
                "missing_component_rows": {c: int(group[c].isna().sum()) for c in CHANNELS},
                "unmapped_observed_counts": {c: float(unmapped[c].sum()) if len(unmapped) and unmapped[c].notna().all() else None for c in CHANNELS}})
        teams[team] = {"recent_observed_games": _records(recent), "coverage": coverage}
    evidence = []
    for actor in actors:
        window, selection = select_role_window(rows, actor, games, before_period=before_period, verified_gaps=verified_gaps)
        fields = [c for c in ("period", "team", "position", "source_player_id", "source_id", "imported_at", *CHANNELS) if c in window]
        evidence.append({"player_master_id": str(actor["player_master_id"]), "team": actor["team"],
            "position": normalize_position(actor["position"]), "role_window": selection,
            "observed_games": _records(window[fields]), "observed_kind": "original_source_counts",
            "participation_basis": "source stat rows; a row or measured zero does not independently certify snaps/participation",
            "allocated_proxy": None, "forecast": None})
    canonical = rows.sort_values(["period", "team", "player_master_id"], kind="stable").to_json(orient="records")
    return {"version": VERSION, "before_period": before_period,
        "producer_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "decision_cutoff_at": str(cutoff) if cutoff is not None else None,
        "source_history_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
        "source_actor_game_rows": len(rows), "unmapped_actor_game_rows": int(rows.player_master_id.isna().sum()),
        "source_periods": sorted(int(p) for p in rows.period.unique()),
        "chronology": "import cutoff bounded when supplied; revised source is not original pregame proof",
        "clock_coverage": {"event": "season/week period; exact event clock not supplied",
            "publication": "not supplied", "capture": "not supplied",
            "received": "per-row imported_at when supplied", "decision": "decision_cutoff_at"},
        "universe": "full supplied source before preferences; unmapped actors retained in team budgets",
        "teams": teams, "actors": evidence}
