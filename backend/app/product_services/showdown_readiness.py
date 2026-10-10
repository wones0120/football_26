"""Reporting on consumed Showdown inputs, without a solve or source refresh."""
from .slate_preparation import aware
from .replay import parse_slate_lock


def assess_showdown_inputs(lineups, params, decision_at):
    rows = [row for lineup in lineups for row in lineup]
    prepared = params.get("prepared_input_evidence") or {}
    lock = parse_slate_lock(row.get("game_id") for row in rows)
    decision = aware(decision_at)
    checks = {}

    def add(name, status, reason):
        checks[name] = {"status": status, "reason": reason}

    runtime = params.get("strategy_runtime") or {}
    role_audit = runtime.get("current_slate_role_availability_audit") or {}
    role_questions = [r for r in role_audit.get("players", [])
        if r.get("role_optimizer_eligible") and
        (r.get("role_resolution_warning") or r.get("expected_depth_role") == "uncertain")]
    kicker_questions = (runtime.get("kicker_role_gate") or {}).get("warnings", [])
    add("Current slate roles and availability", "BLOCKER" if role_questions or kicker_questions else
        "PASS" if role_audit else "MISSING",
        f"{len(role_questions)} eligible players have unresolved roles/workload; " + "; ".join(kicker_questions)
        if role_questions or kicker_questions else "Canonical role audit retained." if role_audit else
        "Current player-pool role audit missing; salary is not participation evidence.")

    add("Prepared input dependency lineage", "PASS" if prepared else "UNEVALUATED",
        f"Verified preparation {prepared.get('prepared_input_job_id')}" if prepared else
        "No verified preparation was consumed. Use Operations preparation and rebuild.")
    add("Native draft group", "PASS" if prepared.get("native_draft_groups") else "UNEVALUATED",
        str(prepared.get("native_draft_groups")) if prepared.get("native_draft_groups") else
        "Operator-confirmed native draft group unavailable. Import salary evidence with its native draft-group ID.")
    add("Kickoff/pre-lock evidence", "UNEVALUATED" if lock is None else "BLOCKER" if decision >= lock else "PASS",
        lock.isoformat() if lock else "Salary kickoff unavailable. Review the native game and canonical schedule.")
    dates = [aware(row["market_observed_at"]) for row in rows if row.get("market_observed_at")]
    market_complete = bool(rows) and len(dates) == len(rows) and all(
        row.get("market_context_point_in_time_safe") is True and
        all(row.get(field) is not None for field in ("game_total_line", "team_spread_line", "team_implied_total"))
        for row in rows)
    # Reuse the preparation display's existing 6h/24h age bands. Quote
    # publication freshness remains separate and cannot be inferred here.
    age = (decision - min(dates)).total_seconds() / 3600 if dates else None
    freshness = "missing" if not market_complete else "stale" if age > 24 else "aging" if age > 6 else "fresh"
    invalid = any(date > decision for date in dates)
    add("Market observation age", "BLOCKER" if invalid else "MISSING" if not market_complete else
        "WARNING" if freshness != "fresh" else "PASS",
        f"{freshness}; oldest consumed observation age {age} hours. Capture nflverse markets and rebuild if needed.")
    add("Upstream market quote publication freshness", "UNEVALUATED",
        "nflverse observation/capture clocks do not verify sportsbook quote publication time.")
    add("Availability evidence", "PASS" if rows and all(row.get("pregame_context_source") and
        row.get("pregame_context_observed_at") for row in rows) else "MISSING",
        "Consumed source and observation fields retained below. Load sourced pregame evidence and rebuild where missing.")
    add("Current entry availability clearance", "UNEVALUATED",
        "Frozen designations, inferred starters and practice evidence do not establish current final clearance.")
    add("Role ownership", "PASS" if rows and all(row.get("captain_ownership") is not None and
        row.get("flex_ownership") is not None for row in rows) else "MISSING",
        params.get("strategy_runtime", {}).get("showdown_portfolio_policy", {}).get(
            "candidate_selection", {}).get("ownership_selection_status", "Role ownership unavailable; never substitute Classic ownership or zero."))
    for name in ("Salary publication freshness", "Current weather clearance", "Contest assignment / submission"):
        add(name, "UNEVALUATED", "Not evaluated by this consumed-input assessment.")
    game_id = rows[0].get("game_id") if rows else None
    evidence = [{k: row.get(k) for k in (
        "player_id", "name", "roster_position", "game_id", "salary_source_row_id",
        "salary_ingest_run_id", "salary_source_checksum", "salary_source_path",
        "projection_run_id", "projection_model_version", "data_cutoff_at",
        "market_source_system", "market_observed_at", "availability_override",
        "official_availability_status", "pregame_context_source", "pregame_context_observed_at")}
        for row in rows]
    return {"version": "showdown_consumed_input_readiness_v1", "entry_ready": False,
            "status": "BLOCKED" if any(c["status"] == "BLOCKER" for c in checks.values()) else "DEVELOPMENT_PREVIEW",
            "scope": "consumed saved Showdown inputs; current entry clearance unevaluated",
            "checks": checks, "reasons": [f"{k}: {v['reason']}" for k, v in checks.items() if v["status"] != "PASS"],
            "market_coverage": {"total_games": 1, "sourced_games": int(market_complete),
                "fresh_hours": 6, "stale_hours": 24, "stale_policy": "warning",
                "fresh_games": [game_id] if freshness == "fresh" else [],
                "aging_games": [game_id] if freshness == "aging" else [],
                "stale_games": [game_id] if freshness == "stale" else [],
                "missing_games": [game_id] if freshness == "missing" else [],
                "newest_observed_at": max(dates).isoformat() if dates else None,
                "games": [{"status": freshness, "age_hours": age,
                    "game_id": game_id,
                    "source": rows[0].get("market_source_system") if rows else None,
                    "observed_at": min(dates).isoformat() if dates else None}]},
            "consumed_evidence": evidence, "preparation_evidence": prepared,
            "current_slate_role_availability_audit": role_audit,
            "assessed_at": decision.isoformat(), "lock_at": lock.isoformat() if lock else None}
