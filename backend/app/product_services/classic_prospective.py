"""Frozen, pregame-only Classic small-field experiment contracts and risk controls."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
from math import floor, isfinite
import json
from pathlib import Path
from statistics import mean, median
from typing import Any, Mapping, Sequence

from .gpp_optimizer import Player, _build_lineup


SNAPSHOT_CONTRACT = "classic_solver_snapshot_v2"
CLASSIC_RUN_INPUT_CONTRACT = "classic_run_solver_inputs_v1"
EXPERIMENT_CONTRACT = "classic_prospective_structural_coverage_v1"
RISK_BUCKETS = ("out", "doubtful", "questionable_elevated", "questionable_full_role", "normal")
DEFAULT_RISK_POLICY = {
    "elevated_candidate_cap": 0.25,
    "elevated_selected_cap": 0.40,
    "full_role_candidate_cap": 0.50,
    "full_role_selected_cap": 0.60,
    "max_elevated_per_lineup": 1,
    "selected_lineups_with_elevated_cap": 0.60,
    "non_elite_candidate_cap": 0.70,
    "elite_candidate_cap": 0.90,
    "elite_report_threshold": 0.80,
    "viable_qb_top_fraction": 0.60,
    "min_qb_family_candidates": 2,
    "min_mean_from_best": 10.0,
    "min_p90_from_best": 15.0,
    "high_p90_percentile": 0.95,
    "high_p90_low_exposure": 0.05,
}
PREGAME_ROW_FIELDS = (
    "player_id", "name", "player_name", "player_team", "opponent_team", "position",
    "game_id", "game_info",
    "salary", "projection", "p90", "ownership", "ownership_run_id",
    "game_total_line", "team_implied_total", "team_spread_line",
    "player_status", "roster_status", "pregame_injury_status", "injury_status",
    "official_availability_status", "injury_observed_at", "practice_participation", "practice_trend",
    "practice_observed_at", "expected_workload_status", "expected_workload_observed_at",
    "team_targets_mean_3_available", "team_carries_mean_3_available",
    "pregame_context_observed_at",
    "pregame_availability_probability", "pregame_start_probability",
    "pregame_expected_snaps", "pregame_expected_routes", "pregame_expected_carries",
    "pregame_expected_targets", "pregame_role_label", "pregame_role_uncertain",
    "salary_source_row_id", "salary_ingest_run_id", "salary_source_system",
    "salary_source_path", "salary_source_checksum", "salary_source_observed_at",
    "projection_run_id", "data_cutoff_at", "ownership_observed_at",
    "pregame_context_run_id", "pregame_context_source", "market_source_system",
    "market_observed_at",
    "availability_override", "is_starting_qb", "market_context_point_in_time_safe",
)


def _safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, float) and not isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe(item) for item in (sorted(value) if isinstance(value, set) else value)]
    if hasattr(value, "item"):
        return _safe(value.item())
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def digest_payload(payload: Mapping[str, Any]) -> str:
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode()).hexdigest()


def freeze_classic_run_input(*, run_id: str, season: int, week: int, slate: str,
                             created_at: datetime, cutoff: datetime | None,
                             projection_run_id: str | None, strategy: str,
                             rows: Sequence[Mapping[str, Any]], params: Mapping[str, Any]) -> dict:
    """Save the final cutoff-safe solver frame for every Classic strategy."""
    forbidden = {"actual_points", "actual_score", "actual_rank", "postgame"}
    safe_rows = [_safe({key: value for key, value in row.items() if key not in forbidden})
                 for row in rows]
    code_files = ("optimizer.py", "gpp_optimizer.py", "classic_small_field.py",
                  "rule_library.py", "lineup_correlation_scoring.py")
    payload = {"metadata": {"optimizer_run_id": run_id, "season": season, "week": week,
                             "slate": slate,
                             "created_at": created_at.replace(tzinfo=created_at.tzinfo or UTC).isoformat(),
                             "data_cutoff_at": cutoff.isoformat() if cutoff else None,
                             "projection_run_id": projection_run_id, "strategy": strategy,
                             "code_sha256": {name: sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
                                             for name in code_files}},
               "final_solver_rows": safe_rows,
               "parameters": _safe({key: value for key, value in params.items() if key != "strategy_runtime"})}
    return {"contract": CLASSIC_RUN_INPUT_CONTRACT, "sha256": digest_payload(payload),
            "payload": payload}


def freeze_solver_snapshot(*, run_id: str, season: int, week: int, slate: str,
                           created_at: datetime, cutoff: datetime | None,
                           projection_run_id: str | None, strategy: str,
                           players: Sequence[Player], pool_rows: Sequence[Mapping[str, Any]],
                           source_pool_rows: Sequence[Mapping[str, Any]] = (),
                           options: Mapping[str, Any], resolved_config: Any,
                           policy_ids: Mapping[str, Any] | None = None) -> dict:
    """Freeze every solver input and source fact used by the prospective experiment."""
    rows = [{key: _safe(row.get(key)) for key in PREGAME_ROW_FIELDS}
            for row in pool_rows]
    if len({str(row["player_id"]) for row in rows}) != len(rows):
        raise ValueError("Frozen Classic pool has duplicate canonical player IDs")
    code_files = ("gpp_optimizer.py", "classic_small_field.py", "classic_prospective.py",
                  "lineup_correlation_scoring.py", "rule_library.py", "classic_portfolio_policy.py")
    code_hashes = {name: sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
                   for name in code_files}
    payload = {
        "metadata": {"optimizer_run_id": run_id, "season": season, "week": week,
                     "slate": slate, "created_at": created_at.replace(tzinfo=created_at.tzinfo or UTC).isoformat(),
                     "data_cutoff_at": cutoff.isoformat() if cutoff else None,
                     "decision_cutoff_at": created_at.replace(tzinfo=created_at.tzinfo or UTC).isoformat(),
                     "projection_run_id": projection_run_id, "strategy": strategy,
                     "ownership_run_ids": sorted({str(row["ownership_run_id"]) for row in rows
                                                  if row.get("ownership_run_id")}),
                     "salary_sources": sorted({(str(row.get("salary_source_system")),
                                                str(row.get("salary_ingest_run_id"))) for row in rows}),
                     "policy_ids": _safe(dict(policy_ids or {})),
                     "code_sha256": code_hashes},
        "players": [{**_safe(asdict(player)), "tags": sorted(player.tags)} for player in players],
        "pool_rows": rows,
        "source_pool_rows": [{key: _safe(row.get(key)) for key in PREGAME_ROW_FIELDS}
                             for row in source_pool_rows],
        "options": _safe(dict(options)),
        "resolved_config": _safe(asdict(resolved_config)),
        "eligible_player_ids": sorted(str(player.player_id) for player in players),
    }
    return {"contract": SNAPSHOT_CONTRACT, "sha256": digest_payload(payload), "payload": payload}


def validate_solver_snapshot(snapshot: Mapping[str, Any]) -> None:
    if snapshot.get("contract") != SNAPSHOT_CONTRACT or not isinstance(snapshot.get("payload"), dict):
        raise ValueError("Classic solver snapshot contract is missing")
    if snapshot.get("sha256") != digest_payload(snapshot["payload"]):
        raise ValueError("Classic solver snapshot hash mismatch")
    payload = snapshot["payload"]
    if len(payload["players"]) != len(payload["eligible_player_ids"]):
        raise ValueError("Classic solver snapshot player count mismatch")
    forbidden = {"actual_points", "actual_score", "actual_rank", "postgame"}
    if any(forbidden.intersection(row) for row in
           [*payload["pool_rows"], *(payload.get("source_pool_rows") or [])]):
        raise ValueError("Postgame field in Classic solver snapshot")


def validate_classic_run_input(snapshot: Mapping[str, Any]) -> None:
    if snapshot.get("contract") != CLASSIC_RUN_INPUT_CONTRACT or not isinstance(snapshot.get("payload"), dict):
        raise ValueError("Classic run solver input snapshot contract is missing")
    if digest_payload(snapshot["payload"]) != snapshot.get("sha256"):
        raise ValueError("Classic run solver input snapshot hash mismatch")


def guard_prelock_persistence(experiment: Mapping[str, Any] | None,
                              first_kickoff_at: str | None,
                              database_time: datetime,
                              snapshot_sha256: str) -> dict | None:
    """Only label all three arms frozen when the database write precedes kickoff."""
    if not experiment or experiment.get("status") != "prelock_frozen":
        return dict(experiment) if experiment else None
    kickoff = _timestamp(first_kickoff_at)
    if kickoff and kickoff.tzinfo and database_time.tzinfo and database_time < kickoff:
        return dict(experiment)
    return {"status": "not_frozen_prelock",
            "reason": "database_persistence_at_or_after_saved_kickoff",
            "frozen_snapshot_sha256": snapshot_sha256}


def slate_kickoff_evidence_pool(rows: Sequence[Mapping[str, Any]]) -> dict:
    """Use every saved slate game, including games absent from generated lineups."""
    games = sorted({str(row.get("game_id") or row.get("game_info"))
                    for row in rows if row.get("game_id") or row.get("game_info")})
    return {"status": "slate_source_pool", "candidates": [{"games_represented": games}]}


def replay_frozen_generation(snapshot: Mapping[str, Any]) -> tuple[list[list[Player]], dict]:
    """Rebuild the original generator from frozen values, never querying current slate tables."""
    validate_solver_snapshot(snapshot)
    from .gpp_optimizer import run_gpp_pipeline, tag_players
    from .classic_small_field import expand_candidate_discovery

    payload = snapshot["payload"]
    for name, expected in payload["metadata"]["code_sha256"].items():
        if sha256((Path(__file__).parent / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Frozen generator code changed: {name}")
    players = [Player(**{**row, "tags": set(row.get("tags") or [])}) for row in payload["players"]]
    options = payload["options"]
    meta = payload["metadata"]
    result = run_gpp_pipeline(
        season=meta["season"], week=meta["week"], slate=meta["slate"],
        num_lineups=options["candidate_target"], players=players,
        ownership_available=options["ownership_available"],
        max_exposure=options["generation_max_exposure"],
        enforce_single_te=options["enforce_single_te"],
        avoid_dst_opponents=options["avoid_dst_opponents"],
        large_gpp=options["large_gpp"],
        minimum_uniqueness=options["minimum_uniqueness"],
        max_from_team=options["max_players_per_team"],
        max_from_game=options["max_players_per_game"],
        stack_templates=options["stack_templates"],
        maximum_exposure_by_player={pid: 1.0 for pid in options["locked_player_ids"]},
        minimum_exposure_by_player={pid: 1.0 for pid in options["locked_player_ids"]},
        include_control_comparisons=False,
        long_shot_mode=options["long_shot_mode"],
        candidate_aware_ownership=options["candidate_aware_ownership"],
        solver_backend=options["solver_backend"],
        precompute_correlation_terms=True,
    )
    if _safe(asdict(result.config)) != payload["resolved_config"]:
        raise ValueError("Frozen generator resolved config differs from saved config")
    tag_players(players, result.config.tag_thresholds)
    expanded, discovery = expand_candidate_discovery(
        result, players,
        enforce_single_te=options["enforce_single_te"],
        avoid_dst_opponents=options["avoid_dst_opponents"],
        locked_player_ids=set(options["locked_player_ids"]),
        starting_qb_ids=set(options["starting_qb_ids"]) or None,
        max_workers=options["candidate_discovery"]["max_workers"],
        solver_backend=options["solver_backend"],
    )
    return expanded, discovery


def resolve_risk_policy(config: Mapping[str, Any] | None = None) -> dict:
    policy = dict(DEFAULT_RISK_POLICY)
    for key, value in (config or {}).items():
        if key not in policy:
            raise ValueError(f"Unknown Classic risk control: {key}")
        if key in {"max_elevated_per_lineup", "min_qb_family_candidates"}:
            if type(value) is not int or value < 0:
                raise ValueError(f"{key} must be a non-negative integer")
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
            raise ValueError(f"{key} must be a finite non-negative number")
        elif key.endswith("cap") or key in {"viable_qb_top_fraction", "high_p90_percentile",
                                          "high_p90_low_exposure", "elite_report_threshold"}:
            if value > 1:
                raise ValueError(f"{key} must be at most 1")
        policy[key] = value
    return policy


def _timestamp(value: Any) -> datetime | None:
    try:
        return value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _utc_naive(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value


def classify_availability(row: Mapping[str, Any], cutoff: datetime | None) -> dict:
    statuses = [str(row.get(key) or "").strip().upper() for key in
                ("official_availability_status", "pregame_injury_status", "injury_status", "player_status")]
    priority = ("OUT", "INACTIVE", "IR", "PUP", "SUSPENDED", "DOUBTFUL", "D",
                "QUESTIONABLE", "Q")
    designation = next((status for status in priority if status in statuses),
                       next((status for status in statuses if status), ""))
    observed = _timestamp(row.get("injury_observed_at") or row.get("pregame_context_observed_at")
                          or row.get("salary_source_observed_at"))
    if cutoff and observed and _utc_naive(observed) > _utc_naive(cutoff):
        raise ValueError("Availability evidence is later than the optimizer cutoff")
    practice = str(row.get("practice_participation") or "").strip().upper()
    practice_trend = str(row.get("practice_trend") or "").strip().upper()
    workload = str(row.get("expected_workload_status") or "").strip().upper()
    practice_at = _timestamp(row.get("practice_observed_at"))
    workload_at = _timestamp(row.get("expected_workload_observed_at"))
    if cutoff and any(timestamp and _utc_naive(timestamp) > _utc_naive(cutoff)
                      for timestamp in (practice_at, workload_at)):
        raise ValueError("Practice or workload evidence is later than the optimizer cutoff")
    if designation in {"OUT", "INACTIVE", "IR", "PUP", "SUSPENDED"}:
        bucket = "out"
    elif designation in {"DOUBTFUL", "D"}:
        bucket = "doubtful"
    elif designation in {"QUESTIONABLE", "Q"}:
        bucket = ("questionable_full_role" if practice == "FULL" and practice_at and
                  workload in {"FULL", "NORMAL", "NO_RESTRICTION"} and workload_at else
                  "questionable_elevated")
    else:
        bucket = "normal"
    return {"bucket": bucket, "designation": designation or None,
            "evidence_timestamp": observed.isoformat() if observed else None,
            "practice_status": practice or None, "practice_trend": practice_trend or None,
            "practice_observed_at": practice_at.isoformat() if practice_at else None,
            "workload_status": workload or None,
            "workload_observed_at": workload_at.isoformat() if workload_at else None,
            "workload_confidence": ("supported_full_role" if bucket == "questionable_full_role" else
                                    "uncertain" if bucket == "questionable_elevated" else "not_applicable"),
            "evidence_gap": bucket == "questionable_elevated" and not
                            (practice and workload and practice_at and workload_at)}


def classify_pool(rows: Sequence[Mapping[str, Any]], cutoff: datetime | None) -> dict[str, dict]:
    return {str(row["player_id"]): classify_availability(row, cutoff) for row in rows}


def resolve_overrides(overrides: Mapping[str, Any] | None, player_ids: set[str]) -> dict[str, dict]:
    output = {}
    for pid, raw in (overrides or {}).items():
        if str(pid) not in player_ids or not isinstance(raw, dict) or not str(raw.get("reason") or "").strip():
            raise ValueError("Classic availability override needs a canonical player ID and reason")
        allowed = {"reason", "allow_doubtful", "candidate_cap", "selected_cap"}
        if set(raw) - allowed:
            raise ValueError("Unknown Classic availability override field")
        item = {"reason": str(raw["reason"]).strip(), "allow_doubtful": raw.get("allow_doubtful", False)}
        if type(item["allow_doubtful"]) is not bool:
            raise ValueError("allow_doubtful must be boolean")
        for key in ("candidate_cap", "selected_cap"):
            value = raw.get(key)
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
                    raise ValueError(f"{key} must be in [0, 1]")
                item[key] = float(value)
        output[str(pid)] = item
    return output


def risk_exposure(candidates: Sequence[Mapping[str, Any]], classifications: Mapping[str, dict]) -> dict:
    counts = Counter(pid for row in candidates for pid in row["player_ids"])
    questionable = {pid for pid, risk in classifications.items() if risk["bucket"].startswith("questionable")}
    elevated = {pid for pid, risk in classifications.items() if risk["bucket"] == "questionable_elevated"}
    n = len(candidates)
    q_per = Counter(len(set(row["player_ids"]) & questionable) for row in candidates)
    high_per = Counter(len(set(row["player_ids"]) & elevated) for row in candidates)
    questionable_appearances = sum(counts[pid] for pid in questionable)
    return {"lineup_count": n, "questionable_player_appearances": questionable_appearances,
            "questionable_appearances_per_100_lineups": 100 * questionable_appearances / n if n else 0,
            "questionable_per_lineup": dict(sorted(q_per.items())),
            "elevated_per_lineup": dict(sorted(high_per.items())),
            "pct_with_at_least": {str(k): 100 * sum(v for count, v in q_per.items() if count >= k) / n if n else 0
                                  for k in (1, 2, 3)},
            "by_bucket": {bucket: sum(counts[pid] for pid, risk in classifications.items()
                                      if risk["bucket"] == bucket) for bucket in RISK_BUCKETS},
            "by_bucket_per_100_lineups": {
                bucket: 100 * sum(counts[pid] for pid, risk in classifications.items()
                                  if risk["bucket"] == bucket) / n if n else 0
                for bucket in RISK_BUCKETS},
            "by_player": {pid: {"count": counts[pid], "percent": 100 * counts[pid] / n if n else 0,
                                "bucket": risk["bucket"]} for pid, risk in classifications.items()
                          if risk["bucket"] != "normal"}}


def _top_fraction(players: Sequence[Player], field: str, fraction: float) -> set[str]:
    by_position: dict[str, list[Player]] = defaultdict(list)
    for player in players:
        by_position[player.position].append(player)
    return {player.player_id for group in by_position.values()
            for player in sorted(group, key=lambda item: (-getattr(item, field), item.player_id))
            [:max(1, floor(len(group) * fraction))]}


def core_classes(players: Sequence[Player], risks: Mapping[str, dict]) -> dict[str, str]:
    high_mean = _top_fraction(players, "projection", 0.20)
    high_p90 = _top_fraction(players, "ceiling", 0.20)
    by_position: dict[str, list[Player]] = defaultdict(list)
    for player in players:
        by_position[player.position].append(player)
    high_value = {player.player_id for group in by_position.values()
                  for player in sorted(group, key=lambda p: (-p.projection / max(p.salary / 1000, 1), p.player_id))
                  [:max(1, floor(len(group) * 0.30))]}
    return {player.player_id: (
        "elevated_risk_questionable" if risks[player.player_id]["bucket"] == "questionable_elevated" else
        "questionable_full_role" if risks[player.player_id]["bucket"] == "questionable_full_role" else
        "elite_high_confidence" if player.player_id in high_mean & high_p90 & high_value
        and risks[player.player_id]["bucket"] == "normal" else
        "low_owned_value" if player.ownership is not None and player.ownership < 5
        and player.player_id in high_value else "ordinary_core"
    ) for player in players}


def high_p90_low_exposure(players: Sequence[Player], candidates: Sequence[Mapping[str, Any]],
                          risks: Mapping[str, dict], policy: Mapping[str, Any]) -> list[dict]:
    top = _top_fraction(players, "ceiling", 1 - policy["high_p90_percentile"])
    counts = Counter(pid for row in candidates for pid in row["player_ids"])
    return [{"player_id": player.player_id, "name": player.name,
             "candidate_count": counts[player.player_id],
             "candidate_pct": counts[player.player_id] / max(1, len(candidates)),
             "diagnosis": "legal_solve_needed_to_separate_salary_from_generation_concentration"}
            for player in players if player.player_id in top
            and risks[player.player_id]["bucket"] not in {"out", "doubtful"}
            and counts[player.player_id] / max(1, len(candidates)) < policy["high_p90_low_exposure"]]


def _family(row: Mapping[str, Any]) -> tuple[int, int]:
    stack = row.get("stack") or {}
    return int(stack.get("partner_count") or 0), int(stack.get("bring_back_count") or 0)


def _family_counts(rows: Sequence[Mapping[str, Any]]) -> dict:
    output = defaultdict(Counter)
    for row in rows:
        partners, backs = _family(row)
        output[str(row["qb"]["player_id"])][f"QB+{partners}+{backs}back"] += 1
    return {pid: dict(counts) for pid, counts in sorted(output.items())}


def viable_qbs(players: Sequence[Player], risks: Mapping[str, dict], policy: Mapping[str, Any],
               starting_ids: set[str] | None = None) -> list[Player]:
    qbs = [p for p in players if p.position == "QB" and
           risks[p.player_id]["bucket"] not in {"out", "doubtful"} and
           (not starting_ids or p.player_id in starting_ids)]
    if not qbs:
        return []
    top_count = max(1, floor(len(qbs) * policy["viable_qb_top_fraction"]))
    def leaders(key):
        return {p.player_id for p in sorted(qbs, key=lambda p: (-key(p), p.player_id))[:top_count]}
    qualifying = (leaders(lambda p: p.projection) | leaders(lambda p: p.ceiling) |
                  leaders(lambda p: p.projection / max(p.salary / 1000, 1)) |
                  leaders(lambda p: p.game_total or 0) |
                  leaders(lambda p: p.team_total or 0))
    return sorted((p for p in qbs if p.player_id in qualifying), key=lambda p: p.player_id)


def _candidate_concentrations(rows: Sequence[Mapping[str, Any]], players: Sequence[Player],
                              classes: Mapping[str, str], risks: Mapping[str, dict],
                              policy: Mapping[str, Any], overrides: Mapping[str, dict]) -> list[dict]:
    counts = Counter(pid for row in rows for pid in row["player_ids"])
    by_id = {p.player_id: p for p in players}
    n = len(rows)
    output = []
    for pid, count in counts.most_common():
        core_class = classes[pid]
        evidence = by_id[pid]
        output.append({"player_id": pid, "name": evidence.name, "count": count,
                       "percent": count / n if n else 0, "core_class": core_class,
                       "risk_bucket": risks[pid]["bucket"],
                       "above_80_reason": (
                           "elite: top 20% position mean and P90, top 30% value, normal availability"
                           if core_class == "elite_high_confidence" else
                           "explicit user override: " + overrides[pid]["reason"] if pid in overrides else
                           "unjustified concentration; review candidate cap"
                       ) if n and count / n > policy["elite_report_threshold"] else None})
    return output


def _summary(rows: Sequence[Mapping[str, Any]], classifications: Mapping[str, dict]) -> dict:
    from .optimizer_coverage import lineup_diversity

    return {"diversity": lineup_diversity(rows),
            "stack_families": dict(Counter(f"QB+{_family(row)[0]}+{_family(row)[1]}back" for row in rows)),
            "by_qb_family": _family_counts(rows),
            "qb_exposure": dict(Counter(str(row["qb"]["player_id"]) for row in rows)),
            "game_exposure": dict(Counter(str(row.get("primary_game")) for row in rows)),
            "mean_distribution": sorted(float(row["mean"]) for row in rows),
            "p90_distribution": sorted(float(row["p90"]) for row in rows),
            "ownership_distribution": sorted(float(row["ownership_sum"]) for row in rows
                                             if row.get("ownership_sum") is not None),
            "mean_sum": sum(float(row["mean"]) for row in rows),
            "p90_sum": sum(float(row["p90"]) for row in rows),
            "ownership_sum": sum(float(row["ownership_sum"]) for row in rows
                                 if row.get("ownership_sum") is not None),
            "leverage_sum": sum(float(row.get("leverage_sum") or 0) for row in rows),
            "player_exposure": dict(Counter(pid for row in rows for pid in row["player_ids"])),
            "risk": risk_exposure(rows, classifications),
            "coverage_status": "pregame_only"}


def _portfolio(rows: Sequence[dict], count: int, max_exposure: float,
               locked_ids: set[str], maximums: dict[str, float], minimums: dict[str, float],
               *, overlap: int | None = None, risk_ids: set[str] | None = None,
               enforce_locked_caps: set[str] | None = None,
               max_objective_loss: float | None = None,
               risk_budget: float = 1.0, solver_backend: str = "bundled") -> tuple[list[dict], dict]:
    from .classic_small_field import _select_global, portfolio_summary

    indexes = _select_global(list(rows), count, max_exposure, locked_ids,
                             maximums, minimums, solver_backend=solver_backend,
                             max_lineup_overlap=overlap,
                             max_objective_loss=max_objective_loss,
                             max_lineups_with_any_player_ids=(risk_ids, risk_budget) if risk_ids is not None else None,
                             enforce_maximum_for_locked_ids=enforce_locked_caps)
    selected = [rows[index] for index in indexes]
    return selected, portfolio_summary(selected, candidate_count=len(rows),
                                       constraints={"max_lineup_overlap": overlap,
                                                    "risk_budget": risk_budget if risk_ids is not None else None})


def run_prospective_experiment(*, snapshot: Mapping[str, Any], production_candidates: Sequence[dict],
                               production_selected_ranks: Sequence[int], players: Sequence[Player],
                               source_rows: Sequence[Mapping[str, Any]], config: Any,
                               selected_count: int, max_exposure: float,
                               locked_ids: set[str], maximums: dict[str, float],
                               minimums: dict[str, float], ownership_available: bool,
                               enforce_single_te: bool, avoid_dst_opponents: bool,
                               solver_backend: str, risk_config: Mapping[str, Any] | None = None,
                               override_config: Mapping[str, Any] | None = None) -> dict:
    """Run exactly one structural generator and one original-pool overlap shadow."""
    validate_solver_snapshot(snapshot)
    policy = resolve_risk_policy(risk_config)
    payload = snapshot["payload"]
    if ([{**_safe(asdict(player)), "tags": sorted(player.tags)} for player in players]
            != payload["players"] or
            [{key: _safe(row.get(key)) for key in PREGAME_ROW_FIELDS} for row in source_rows]
            != payload["pool_rows"] or
            _safe(asdict(config)) != payload["resolved_config"]):
        raise ValueError("Prospective shadow inputs differ from the frozen solver snapshot")
    cutoff = _timestamp(payload["metadata"].get("decision_cutoff_at"))
    risks = classify_pool(source_rows, cutoff)
    overrides = resolve_overrides(override_config, set(risks))
    classes = core_classes(players, risks)
    originals = list(production_candidates)
    production_selected = [row for row in originals if row["rank"] in set(production_selected_ranks)]
    overlap_selected, overlap_portfolio = _portfolio(
        originals, selected_count, max_exposure, locked_ids, maximums, minimums,
        overlap=6,
        max_objective_loss=(payload["options"].get("portfolio_constraints") or {}).get("max_objective_loss"),
        solver_backend=solver_backend)
    from .classic_small_field import describe_candidate, portfolio_summary
    from .lineup_correlation_scoring import build_format_specific_terms, build_lineup_correlation_terms
    from .rule_library import resolve_strategy_profile

    eligible = [p for p in players if risks[p.player_id]["bucket"] != "out" and
                (risks[p.player_id]["bucket"] != "doubtful" or
                 overrides.get(p.player_id, {}).get("allow_doubtful"))]
    elevated = {pid for pid, risk in risks.items() if risk["bucket"] == "questionable_elevated"}
    source = {str(row["player_id"]): dict(row) for row in source_rows}
    game_totals = sorted({float(p.game_total) for p in players if p.game_total is not None})
    viable = viable_qbs(eligible, risks, policy,
                       set(payload["options"].get("starting_qb_ids") or []))
    profile = resolve_strategy_profile(contest_format="classic", objective="gpp")
    correlation_terms = build_lineup_correlation_terms(eligible, profile=profile)
    format_terms = build_format_specific_terms(eligible, profile=profile)
    pool_by_key = {tuple(sorted(row["player_ids"])): row for row in originals}
    discovery = []
    best_mean = max((row["mean"] for row in originals), default=0)
    best_p90 = max((row["p90"] for row in originals), default=0)
    families = ((1, 0), (1, 1), (2, 0), (2, 1))
    def solve(label: str, qb_id: str | None, family: tuple[int, int] | None,
              blocked: list[set[int]]) -> dict | None:
        rules = config.stack_rules
        if family is not None:
            from dataclasses import replace
            rules = replace(rules, min_pass_catchers=family[0], min_bring_backs=family[1])
        indexes = _build_lineup(
            eligible, config, None, blocked,
            enforce_single_te=enforce_single_te,
            avoid_dst_opponents=avoid_dst_opponents,
            stack_rules=rules, required_player_ids=({qb_id} | locked_ids) if qb_id else locked_ids,
            exact_pass_catchers=family[0] if family else None,
            exact_bring_backs=family[1] if family else None,
            minimum_mean=best_mean - policy["min_mean_from_best"],
            minimum_p90=best_p90 - policy["min_p90_from_best"],
            maximum_player_groups=[(elevated, policy["max_elevated_per_lineup"])],
            precomputed_correlation_terms=correlation_terms,
            precomputed_format_terms=format_terms,
            solver_backend=solver_backend,
        )
        if indexes is None:
            discovery.append({"request": label, "status": "infeasible_or_quality_floor"})
            return None
        roster = [eligible[index] for index in indexes]
        row = describe_candidate(roster, all_players=players, config=config,
                                 pool_by_id=source, ownership_available=ownership_available,
                                 game_totals=game_totals, candidate_aware_ownership=True)
        row["discovery_sources"] = [label]
        key = tuple(sorted(row["player_ids"]))
        discovery.append({"request": label, "status": "duplicate" if key in pool_by_key else "new",
                          "player_ids": list(key)})
        pool_by_key.setdefault(key, row)
        return row
    by_index = {p.player_id: i for i, p in enumerate(eligible)}
    def quality_eligible(row: Mapping[str, Any]) -> bool:
        return (row["mean"] >= best_mean - policy["min_mean_from_best"] and
                row["p90"] >= best_p90 - policy["min_p90_from_best"])
    for qb in viable:
        for family in families:
            matching = [row for row in pool_by_key.values()
                        if row["qb"]["player_id"] == qb.player_id and _family(row) == family
                        and quality_eligible(row)]
            blocked = [{by_index[pid] for pid in row["player_ids"] if pid in by_index}
                       for row in matching[:8]]
            for attempt in range(max(0, policy["min_qb_family_candidates"] - len(matching))):
                row = solve(f"qb:{qb.player_id}:{family[0]}:{family[1]}:{attempt}", qb.player_id,
                            family, blocked)
                if row is None:
                    break
                blocked.append({by_index[pid] for pid in row["player_ids"] if pid in by_index})
    p90_flags = high_p90_low_exposure(players, originals, risks, policy)
    for flag in p90_flags:
        pid = flag["player_id"]
        if pid in by_index:
            row = solve(f"high_p90:{pid}", pid, None, [])
            flag["legal_quality_solve"] = row is not None
            if row is None:
                legal_indexes = _build_lineup(
                    eligible, config, None, [],
                    enforce_single_te=enforce_single_te,
                    avoid_dst_opponents=avoid_dst_opponents,
                    required_player_ids={pid} | locked_ids,
                    maximum_player_groups=[(elevated, policy["max_elevated_per_lineup"])],
                    precomputed_correlation_terms=correlation_terms,
                    precomputed_format_terms=format_terms,
                    solver_backend=solver_backend,
                )
                flag["legal_without_quality_floor"] = legal_indexes is not None
                flag["diagnosis"] = ("legal_but_below_shadow_quality_floor" if legal_indexes else
                                      "salary_roster_or_other_solver_constraint_infeasible")
            else:
                flag["legal_without_quality_floor"] = True
                flag["diagnosis"] = "generation_or_objective_concentration"
    # Admit a fixed-size shadow pool with explicit per-player risk and core budgets.
    target = len(originals)
    potential = sorted(pool_by_key.values(), key=lambda row: (-row["objective_score"],
                                                              tuple(sorted(row["player_ids"]))))
    caps = {}
    exception_evidence = {}
    top_mean = _top_fraction(players, "projection", 0.20)
    top_p90 = _top_fraction(players, "ceiling", 0.20)
    for player in players:
        pid = player.player_id
        bucket = risks[pid]["bucket"]
        cap = (0.0 if bucket == "out" or
               bucket == "doubtful" and not overrides.get(pid, {}).get("allow_doubtful") else
               policy["elevated_candidate_cap"] if bucket == "questionable_elevated" else
               policy["full_role_candidate_cap"] if bucket == "questionable_full_role" else
               1.0 if classes[pid] == "elite_high_confidence" else policy["non_elite_candidate_cap"])
        requested_cap = overrides.get(pid, {}).get("candidate_cap", cap)
        if (bucket == "normal" and classes[pid] != "elite_high_confidence" and
                requested_cap > policy["non_elite_candidate_cap"]):
            evidence = [label for condition, label in (
                (pid in top_mean, "top_20_percent_position_mean"),
                (pid in top_p90, "top_20_percent_position_p90"),
            ) if condition]
            if not evidence:
                raise ValueError("Non-elite core exception needs saved top-tier pregame evidence")
            exception_evidence[pid] = evidence
        caps[pid] = requested_cap
    def build_candidate_pool(cap_map: Mapping[str, float], max_elevated: int) -> tuple[list[dict], Counter]:
        admitted: list[dict] = []
        admitted_keys: set[tuple[str, ...]] = set()
        frequencies: Counter = Counter()
        def admit(row: dict) -> bool:
            ids = set(row["player_ids"])
            key = tuple(sorted(ids))
            if (key in admitted_keys or len(ids & elevated) > max_elevated or
                    any(frequencies[pid] >= floor(cap_map[pid] * target) for pid in ids)):
                return False
            admitted.append(row)
            admitted_keys.add(key)
            frequencies.update(ids)
            return True
        for qb in viable:
            for family in families:
                matches = [row for row in potential if row["qb"]["player_id"] == qb.player_id
                           and _family(row) == family and quality_eligible(row)]
                accepted = 0
                for row in matches:
                    if accepted >= policy["min_qb_family_candidates"]:
                        break
                    if admit(row):
                        accepted += 1
        for row in potential:
            if len(admitted) >= target:
                break
            admit(row)
        # Recheck against the actual denominator when a fixed-target pool underfills.
        while admitted:
            over = {pid for pid, count in frequencies.items()
                    if count > floor(cap_map[pid] * len(admitted))}
            if not over:
                break
            removed = min((row for row in admitted if over.intersection(row["player_ids"])),
                          key=lambda row: (row["objective_score"], tuple(sorted(row["player_ids"]))))
            admitted.remove(removed)
            frequencies.subtract(set(removed["player_ids"]))
        admitted.sort(key=lambda row: (-row["objective_score"], tuple(sorted(row["player_ids"]))))
        return [{**row, "rank": rank} for rank, row in enumerate(admitted, 1)], frequencies
    chosen, counts = build_candidate_pool(caps, policy["max_elevated_per_lineup"])
    no_risk_caps = {pid: (0.0 if risks[pid]["bucket"] == "out" else
                          1.0 if classes[pid] == "elite_high_confidence" else
                          policy["non_elite_candidate_cap"])
                    for pid in caps}
    comparison_pool, _ = build_candidate_pool(no_risk_caps, 9)
    # A fixed-target count may be impossible; never silently relax a cap.
    family_requirements = [{"qb_id": qb.player_id, "family": f"QB+{family[0]}+{family[1]}back",
                            "minimum": policy["min_qb_family_candidates"],
                            "legal_quality_candidates": sum(row["qb"]["player_id"] == qb.player_id and
                                                            _family(row) == family and quality_eligible(row)
                                                            for row in potential),
                            "saved_shadow_candidates": sum(row["qb"]["player_id"] == qb.player_id and
                                                           _family(row) == family and quality_eligible(row)
                                                           for row in chosen)}
                           for qb in viable for family in families]
    shadow_maximums = dict(maximums)
    for pid, risk in risks.items():
        cap = (0.0 if risk["bucket"] == "out" or
               risk["bucket"] == "doubtful" and not overrides.get(pid, {}).get("allow_doubtful") else
               policy["elevated_selected_cap"] if risk["bucket"] == "questionable_elevated" else
               policy["full_role_selected_cap"] if risk["bucket"] == "questionable_full_role" else None)
        if cap is not None:
            shadow_maximums[pid] = min(shadow_maximums.get(pid, 1.0),
                                       overrides.get(pid, {}).get("selected_cap", cap))
    selected, selected_portfolio = _portfolio(
        chosen, selected_count, max_exposure, locked_ids, shadow_maximums, minimums,
        risk_ids=elevated, risk_budget=policy["selected_lineups_with_elevated_cap"],
        enforce_locked_caps={pid for pid, risk in risks.items() if risk["bucket"].startswith("questionable")},
        solver_backend=solver_backend)
    unguarded, _ = _portfolio(comparison_pool, selected_count, max_exposure, locked_ids,
                             maximums, minimums, solver_backend=solver_backend)
    def totals(rows):
        return {"mean": sum(row["mean"] for row in rows), "p90": sum(row["p90"] for row in rows)}
    guarded_total, unguarded_total = totals(selected), totals(unguarded)
    risk_rows = []
    production_risk = risk_exposure(originals, risks)
    shadow_risk = risk_exposure(chosen, risks)
    selected_risk = risk_exposure(selected, risks)
    for player in players:
        pid = player.player_id
        risk = risks[pid]
        if risk["bucket"] == "normal":
            continue
        risk_rows.append({"player_id": pid, "player": player.name, **risk,
                          "production_candidate_exposure": production_risk["by_player"][pid]["percent"],
                          "production_selected_exposure": risk_exposure(production_selected, risks)["by_player"][pid]["percent"],
                          "candidate_exposure": shadow_risk["by_player"][pid]["percent"],
                          "selected_exposure": selected_risk["by_player"][pid]["percent"],
                          "candidate_cap": caps[pid],
                          "selected_cap": shadow_maximums.get(pid),
                          "candidate_cap_binding": caps[pid] > 0 and
                                                   counts[pid] >= floor(caps[pid] * len(chosen)),
                          "selected_cap_binding": (shadow_maximums[pid] > 0 and
                                                   selected_risk["by_player"][pid]["count"] >=
                                                   floor(shadow_maximums[pid] * selected_count))
                          if pid in shadow_maximums else False,
                          "override": overrides.get(pid)})
    for row in payload.get("source_pool_rows") or []:
        pid = str(row.get("player_id") or "")
        if not pid or pid in risks:
            continue
        try:
            risk = classify_availability(row, cutoff)
        except ValueError:
            continue  # Later evidence is not used in the frozen pregame report.
        if risk["bucket"] == "normal":
            continue
        risk_rows.append({"player_id": pid, "player": row.get("name") or row.get("player_name") or pid,
                          **risk, "candidate_exposure": 0.0, "selected_exposure": 0.0,
                          "production_candidate_exposure": 0.0,
                          "production_selected_exposure": 0.0,
                          "candidate_cap": 0.0, "selected_cap": 0.0,
                          "candidate_cap_binding": False, "selected_cap_binding": False,
                          "eligibility": "excluded_before_candidate_generation", "override": None})
    experiment = {
        "contract": EXPERIMENT_CONTRACT,
        "frozen_snapshot_sha256": snapshot["sha256"],
        "status": "prelock_frozen",
        "policy": policy,
        "overrides": overrides,
        "production": {"candidate_manifest_sha256": digest_payload({"rosters": [row["player_ids"] for row in originals]}),
                       "candidates": originals, "selected_ranks": list(production_selected_ranks),
                       "selected": production_selected, "pregame": _summary(originals, risks),
                       "selected_pregame": _summary(production_selected, risks),
                       "selected_portfolio": portfolio_summary(production_selected, candidate_count=len(originals))},
        "shadow_generation": {"candidate_manifest_sha256": digest_payload({"rosters": [row["player_ids"] for row in chosen]}),
                              "candidates": chosen, "selected_ranks": [row["rank"] for row in selected],
                              "selected": selected, "selected_portfolio": selected_portfolio,
                              "selection_status": "complete" if len(selected) == selected_count else "infeasible_under_frozen_caps",
                              "candidate_target": target, "candidate_underfill": max(0, target - len(chosen)),
                              "pregame": _summary(chosen, risks),
                              "selected_pregame": _summary(selected, risks),
                              "viable_qb_ids": [p.player_id for p in viable],
                              "structural_discovery": discovery,
                              "family_requirements": family_requirements,
                              "core_exception_evidence": exception_evidence,
                              "core_concentration": _candidate_concentrations(chosen, players, classes, risks, policy, overrides),
                              "high_p90_low_exposure": p90_flags,
                              "risk_policy_tradeoff": {"mean_points_sacrificed": unguarded_total["mean"] - guarded_total["mean"]
                                                       if selected and unguarded else None,
                                                       "ceiling_points_sacrificed": unguarded_total["p90"] - guarded_total["p90"]
                                                       if selected and unguarded else None,
                                                       "comparison": "same discovered candidates and core policy, without questionable/doubtful candidate or portfolio risk caps"}},
        "shadow_portfolio": {"candidate_manifest_sha256": digest_payload({"rosters": [row["player_ids"] for row in originals]}),
                             "selected_ranks": [row["rank"] for row in overlap_selected],
                             "selected": overlap_selected, "selected_portfolio": overlap_portfolio,
                             "selection_status": "complete" if len(overlap_selected) == selected_count else "infeasible_overlap_six",
                             "pregame": _summary(overlap_selected, risks),
                             "constraints": {"max_lineup_overlap": 6, "distinct_qb_paths": False,
                                             "selector_weights": "identical_to_production"}},
        "portfolio_pregame_delta_overlap_minus_production": {
            "mean_sum": sum(row["mean"] for row in overlap_selected) - sum(row["mean"] for row in production_selected)
            if overlap_selected and production_selected else None,
            "p90_sum": sum(row["p90"] for row in overlap_selected) - sum(row["p90"] for row in production_selected)
            if overlap_selected and production_selected else None,
            "ownership_sum": sum(row["ownership_sum"] for row in overlap_selected) - sum(row["ownership_sum"] for row in production_selected)
            if overlap_selected and production_selected and all(row.get("ownership_sum") is not None
                                                               for row in overlap_selected + production_selected) else None,
        },
        "availability_risk": {"players": risk_rows, "production_candidate": production_risk,
                              "shadow_candidate": shadow_risk, "shadow_selected": selected_risk,
                              "production_selected": risk_exposure(production_selected, risks)},
        "postgame": {"status": "pending_actuals"},
    }
    frozen_experiment = _safe(experiment)
    return {**frozen_experiment, "sha256": digest_payload(frozen_experiment)}


def evaluate_postgame(experiment: Mapping[str, Any], actuals: Mapping[str, float],
                      field_lines: Mapping[str, Mapping[str, float]]) -> dict:
    """Attach outcomes later without changing any pre-lock candidate or selector definition."""
    if digest_payload({key: value for key, value in experiment.items() if key != "sha256"}) != experiment.get("sha256"):
        raise ValueError("Frozen prospective experiment hash mismatch")
    def score(row: Mapping[str, Any]) -> float | None:
        ids = row["player_ids"]
        return round(sum(actuals[pid] for pid in ids), 2) if all(pid in actuals for pid in ids) else None
    def quantile(values: list[float], fraction: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        index = fraction * (len(ordered) - 1)
        low = floor(index)
        return ordered[low] + (ordered[min(low + 1, len(ordered) - 1)] - ordered[low]) * (index - low)
    output = {"status": "evaluated", "frozen_snapshot_sha256": experiment["frozen_snapshot_sha256"],
              "field_thresholds": dict(field_lines), "arms": {}}
    for arm in ("production", "shadow_generation", "shadow_portfolio"):
        content = experiment[arm]
        candidates = content.get("candidates") if arm != "shadow_portfolio" else experiment["production"]["candidates"]
        selected = content["selected"]
        candidate_scores = [value for row in candidates if (value := score(row)) is not None]
        selected_scores = [value for row in selected if (value := score(row)) is not None]
        best_generated = max(candidate_scores, default=None)
        best_selected = max(selected_scores, default=None)
        output["arms"][arm] = {
            "candidate_count": len(candidates), "scoreable_count": len(candidate_scores),
            "scoreable_fraction": len(candidate_scores) / len(candidates) if candidates else 0,
            "best_generated_actual": best_generated,
            "generated_actual_percentiles": {f"p{int(q * 100)}": quantile(candidate_scores, q)
                                             for q in (.90, .95, .99)},
            "field_thresholds_reached": {
                contest_id: {label: sum(value >= threshold for value in candidate_scores)
                             for label, threshold in thresholds.items()}
                for contest_id, thresholds in field_lines.items()},
            "selected_scoreable_count": len(selected_scores),
            "best_selected_actual": best_selected,
            "average_selected_actual": mean(selected_scores) if selected_scores else None,
            "median_selected_actual": median(selected_scores) if selected_scores else None,
            "selection_regret_lower_bound": (best_generated - best_selected
                                             if best_generated is not None and best_selected is not None else None),
            "selected_field_thresholds_attained": {
                contest_id: {label: any(value >= threshold for value in selected_scores)
                             for label, threshold in thresholds.items()}
                for contest_id, thresholds in field_lines.items()},
            "selected_concentration": risk_exposure(selected, {
                pid: {"bucket": row["bucket"]} for pid, row in
                ((item["player_id"], item) for item in experiment["availability_risk"]["players"])
            }),
            "selected_player_exposure": dict(Counter(pid for row in selected for pid in row["player_ids"])),
        }
    if any(row["scoreable_fraction"] < .90 for row in output["arms"].values()):
        output["status"] = "partial_actuals_below_90_percent_gate"
    return output
