"""Canonical football roles; salary presence never establishes participation."""
from __future__ import annotations

import pandas as pd

VERSION = "current_slate_role_availability_v1"
LINEAGE_COLUMNS = ["role_availability", "expected_depth_role", "role_starter_evidence",
                   "role_change", "role_optimizer_eligible", "role_confidence",
                   "role_resolution_warning", "role_rostered", "role_active"]
UNAVAILABLE = {"IR", "PUP", "NFI", "O", "OUT", "INACTIVE", "SUSP", "SUSPENDED", "RES", "RESERVE"}
PRACTICE = {"PS", "PRA", "DEV", "PRACTICE_SQUAD"}


def clean(value):
    return None if value is None or (isinstance(value, float) and pd.isna(value)) else value


def resolve_player_roles(frame, contexts=None):
    """Resolve each UUID independently from retained, cutoff-safe evidence.

    Contexts are selected by the canonical loader, which gates observation and
    receipt clocks. The same fields travel with saved optimizer pools. Active
    roster membership is separate from game-day clearance and expected depth.
    """
    rows = frame.copy()
    attributes = rows.attrs
    rows.attrs = {}
    # Structured source lineage is a scalar object, not a pandas assignment
    # mapping. Allocate object columns before assigning dict/list evidence.
    for column in ("role_starter_evidence", "role_change"):
        if column not in rows:
            rows[column] = pd.Series(None,index=rows.index,dtype=object)
        else:
            rows[column] = rows[column].astype(object)
    contexts = contexts if contexts is not None else attributes.get("role_context", [])
    if isinstance(contexts, pd.DataFrame):
        contexts = contexts.to_dict("records")
    lookup = {str(r.get("player_master_id") or r.get("player_id")): r for r in contexts}
    report = {"version": VERSION, "players": [], "warnings": [], "entry_ready": False}
    for index, row in rows.iterrows():
        pid = str(row["player_id"])
        context = lookup.get(pid, {})
        facts = clean(context.get("evidence_json")) or context.get("evidence") or {}
        sourced = bool(context.get("source") and (context.get("source_uri") or facts.get("source_uris")))
        position = str(row.get("position") or "").upper()
        status = str(clean(context.get("injury_status")) or clean(row.get("pregame_injury_status")) or
                     clean(row.get("player_status")) or "").upper()
        roster = str((facts.get("roster_status") if sourced else None) or
                     clean(row.get("roster_status")) or "").upper()
        depth = str((facts.get("expected_depth_role") if sourced else None) or
                    clean(row.get("expected_depth_role")) or "uncertain").lower()
        evidence = facts.get("starter_evidence") if sourced else clean(row.get("role_starter_evidence"))
        warning = None
        availability = "uncertain"
        rostered = roster in {"ACT", *PRACTICE, *UNAVAILABLE}
        on_active_roster = roster == "ACT"
        # role_active denotes active-roster membership. Only game_active in
        # sourced facts establishes game-day clearance (availability='active').
        active = on_active_roster or (sourced and facts.get("game_active") is True)
        probability = clean(context.get("availability_probability"))
        if probability is None:
            probability = clean(row.get("pregame_availability_probability"))
        eligible = True
        if (status in UNAVAILABLE or roster in UNAVAILABLE or probability == 0
                or (sourced and facts.get("game_active") is False)):
            availability, eligible, active = "unavailable", False, False
        elif roster in PRACTICE and not (sourced and facts.get("game_active") is True):
            availability, eligible, active = "unavailable", False, False
            warning = "Practice squad; current game elevation/activation required."
        elif on_active_roster or active:
            availability = "active" if sourced and facts.get("game_active") is True else "rostered"
        if position == "DST":
            availability, depth, active, rostered = "active", "team_defense", True, True
        if position == "QB":
            starter = clean(row.get("team_starting_qb_player_id"))
            if starter:
                depth = "expected_starter" if pid == str(starter) else "expected_backup"
            if depth == "expected_backup" and not (sourced and facts.get("expected_qb_package") is True):
                eligible = False
                warning = "Backup QB without sourced expected package."
        if position == "K" and clean(row.get("kicker_role")):
            depth = "expected_starter" if row["kicker_role"] == "primary" else "expected_backup" if row["kicker_role"] == "backup" else "uncertain"
            eligible = eligible and bool(row.get("kicker_role_eligible", False))
        if availability == "uncertain" or depth == "uncertain":
            warning = warning or "Current availability/depth evidence unresolved; preview only."
        if sourced and facts.get("role_uncertain"):
            warning = "Promotion workload unresolved; no sourced snap/red-zone/target split."
        values = dict(role_availability=availability, expected_depth_role=depth,
                      role_starter_evidence=evidence, role_change=facts.get("role_change") if sourced else clean(row.get("role_change")),
                      role_optimizer_eligible=eligible, role_confidence="high" if not warning and sourced else "medium" if on_active_roster or position == "DST" else "low",
                      role_resolution_warning=warning, role_rostered=rostered, role_active=active)
        for key, value in values.items():
            rows.at[index, key] = value
        report["players"].append(dict(player_id=pid, player=row.get("name", row.get("player_display_name")),
                                     team=row.get("player_team", row.get("recent_team")), position=position, **values))
        if warning:
            report["warnings"].append(dict(player_id=pid, reason=warning))
    rows.attrs = attributes
    rows.attrs["role_availability_audit"] = report
    return rows, report
