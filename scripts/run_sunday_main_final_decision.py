#!/usr/bin/env python3
"""Merge, revalidate, and rescore the persistent Week 2 Sunday Main archive."""
from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from math import log
from pathlib import Path
from typing import Any, Mapping

from backend.app.db import engine
from backend.app.product_services.classic_small_field import describe_candidate
from backend.app.product_services.football_sanity_deficit import lineup_sanity_deficit
from backend.app.product_services.gpp_optimizer import run_gpp_pipeline
from backend.app.product_services.sunday_candidate_archive import (
    artifact_candidates,
    lineup_key,
    load_archive,
    merge_discoveries,
    persist_archive,
    validate_candidate,
)
from scripts.validate_sunday_candidate_exploration import latest_ownership, relative_percentiles
from scripts.validate_sunday_projection_robustness import prepare_pool


REQUIRED_REFRESH_DOMAINS = (
    "official_inactives", "starting_qbs", "roster_mapping", "injuries", "weather", "markets",
    "ownership", "role_opportunity", "projections", "new_candidates",
)
INJURY_FLAGS = {"Q", "QUESTIONABLE", "D", "DOUBTFUL", "OUT", "O"}


def _refresh_manifest(
    path: Path | None, *, require_complete: bool, refresh_after: datetime | None = None,
    require_official_inactives: bool = False,
    require_confirmed_starting_qbs: bool = False,
) -> dict[str, Any]:
    if path is None:
        if require_complete:
            raise ValueError("A refresh manifest is required for final selection")
        return {"status": "not_provided", "domains": {}, "missing": list(REQUIRED_REFRESH_DOMAINS)}
    payload = json.loads(path.read_text())
    contract_id = str(payload.get("contract_id") or "sunday_main_refresh_manifest_v1")
    required_domains = REQUIRED_REFRESH_DOMAINS if contract_id.endswith("_v2") else tuple(
        name for name in REQUIRED_REFRESH_DOMAINS if name != "roster_mapping"
    )
    domains = payload.get("domains") or {}
    missing = [name for name in required_domains if name not in domains]
    usable_states = {
        "complete", "current", "refreshed", "current_prelock_status",
        "not_yet_official", "official", "inferred", "confirmed",
        "mixed_inferred_confirmed",
    }
    incomplete = [
        name for name, row in domains.items()
        if name in required_domains
        and str((row or {}).get("status") or "").lower() not in usable_states
    ]
    verification_errors: list[str] = []
    if contract_id.endswith("_v2"):
        usable_verification = {"verified", "verified_unavailable"}
        for name in required_domains:
            row = domains.get(name) or {}
            verification = str(row.get("verification_state") or "").lower()
            if verification not in usable_verification:
                verification_errors.append(f"{name}:{verification or 'unspecified'}")
            if verification == "verified" and not str(row.get("source") or "").strip():
                verification_errors.append(f"{name}:source_missing")
        for claim in payload.get("claims") or []:
            claim_id = str(claim.get("claim_id") or "unnamed_claim")
            state = str(claim.get("verification_state") or "").lower()
            if state not in usable_verification:
                verification_errors.append(f"claim:{claim_id}:{state or 'unspecified'}")
            if state == "verified" and not str(claim.get("source") or "").strip():
                verification_errors.append(f"claim:{claim_id}:source_missing")
    evidence_errors = []
    inactive_evidence = str((domains.get("official_inactives") or {}).get("evidence_state") or "").lower()
    qb_evidence = str((domains.get("starting_qbs") or {}).get("evidence_state") or "").lower()
    if require_official_inactives and inactive_evidence != "official":
        evidence_errors.append(f"official_inactives:{inactive_evidence or 'unspecified'}")
    if require_confirmed_starting_qbs and qb_evidence not in {"confirmed", "official"}:
        evidence_errors.append(f"starting_qbs:{qb_evidence or 'unspecified'}")
    stale = []
    if refresh_after:
        for name in required_domains:
            value = str((domains.get(name) or {}).get("refreshed_at") or "")
            try:
                refreshed_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if refreshed_at.tzinfo is None:
                    refreshed_at = refreshed_at.replace(tzinfo=timezone.utc)
                if refreshed_at < refresh_after:
                    stale.append(name)
            except ValueError:
                stale.append(name)
    if require_complete and (
        missing or incomplete or stale or evidence_errors or verification_errors
    ):
        raise ValueError(
            "Sunday refresh evidence is incomplete: "
            + ", ".join([*(f"missing:{name}" for name in missing),
                          *(f"incomplete:{name}" for name in incomplete),
                          *(f"stale:{name}" for name in stale),
                          *(f"evidence:{value}" for value in evidence_errors),
                          *(f"verification:{value}" for value in verification_errors)])
        )
    return {**payload, "missing": missing, "incomplete": incomplete,
            "stale": stale, "evidence_errors": evidence_errors,
            "verification_errors": verification_errors,
            "status": "complete" if not missing and not incomplete and not stale
            and not evidence_errors and not verification_errors else "incomplete"}


def _roster_mapping_preflight(
    players: list[Any], pool_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Reconcile salary/projection teams with current roster and starter evidence."""
    rows: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for player in players:
        player_id = str(player.player_id)
        source = pool_by_id.get(player_id, {})
        salary_team = str(player.team or "").strip().upper()
        current_team = str(
            source.get("player_team") or source.get("recent_team")
            or source.get("team") or ""
        ).strip().upper()
        starter = bool(source.get("is_starting_qb")) if player.position == "QB" else None
        evidence_tier = (
            str(source.get("starting_qb_evidence_tier") or "").strip().lower() or None
        )
        reasons: list[str] = []
        if not current_team:
            reasons.append("current_team_unavailable")
        elif current_team != salary_team:
            reasons.append(f"team_mismatch:{salary_team}:{current_team}")
        if player.position == "QB" and not starter:
            reasons.append("eligible_qb_not_marked_starter")
        row = {
            "player_id": player_id, "player": player.name, "position": player.position,
            "salary_team": salary_team, "current_team": current_team or None,
            "opponent": str(source.get("opponent_team") or "").strip().upper() or None,
            "is_starting_qb": starter, "starting_qb_evidence_tier": evidence_tier,
            "reasons": reasons,
        }
        rows.append(row)
        if reasons:
            conflicts.append(row)
    return {
        "status": "passed" if not conflicts else "failed",
        "players_checked": len(rows), "conflict_count": len(conflicts),
        "confirmed_starting_qbs": sum(
            row["position"] == "QB" and row["is_starting_qb"]
            and row["starting_qb_evidence_tier"] == "confirmed" for row in rows
        ),
        "inferred_starting_qbs": sum(
            row["position"] == "QB" and row["is_starting_qb"]
            and row["starting_qb_evidence_tier"] == "inferred" for row in rows
        ),
        "conflicts": conflicts,
    }


def _core_rows(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text())
    return {str(row["player_id"]): row for row in payload["players"]}


def _status(row: Mapping[str, Any]) -> str:
    for field in ("pregame_injury_status", "player_status", "injury_status", "roster_status"):
        value = str(row.get(field) or "").strip().upper()
        if value:
            return value
    return "Unavailable"


def _candidate_report(
    player_ids: list[str], *, players_by_id: Mapping[str, Any], all_players: list[Any],
    config: Any, pool_by_id: dict[str, dict[str, Any]], core_by_id: dict[str, dict[str, Any]],
    ownership_by_id: Mapping[str, float], game_totals: list[float], discoveries: list[dict[str, Any]],
) -> dict[str, Any]:
    lineup = [players_by_id[player_id] for player_id in player_ids]
    row = describe_candidate(
        lineup, all_players=all_players, config=config, pool_by_id=pool_by_id,
        ownership_available=False, game_totals=game_totals,
    )
    for roster_player in row["roster"]:
        player_id = str(roster_player["player_id"])
        player = players_by_id[player_id]
        core = core_by_id.get(player_id, {})
        roster_player.update({
            "salary": int(player.salary),
            "projection": float(player.projection),
            "p90": float(player.ceiling),
            "ownership": ownership_by_id.get(player_id),
            "football_role": core.get("football_classification") or "Unavailable",
            "role_confidence": core.get("current_evidence_confidence"),
            "injury_status": _status(pool_by_id.get(player_id, {})),
        })
    missing_ownership = [player.name for player in lineup if str(player.player_id) not in ownership_by_id]
    row["ownership_complete"] = not missing_ownership
    row["ownership_missing_players"] = missing_ownership
    row["ownership_sum"] = (
        sum(float(ownership_by_id[str(player.player_id)]) for player in lineup)
        if not missing_ownership else None
    )
    row["log_ownership"] = (
        sum(log(max(.01, float(ownership_by_id[str(player.player_id)])) / 100.0) for player in lineup)
        if not missing_ownership else None
    )
    row["sanity"] = lineup_sanity_deficit(
        row["roster"], core_by_id=core_by_id,
        player_pool=[{
            "player_id": player.player_id, "name": player.name, "team": player.team,
            "position": player.position, "salary": player.salary, "projection": player.projection,
        } for player in all_players],
    )
    row["injury_flags"] = [{
        "player": player.name, "status": _status(pool_by_id.get(str(player.player_id), {})),
    } for player in lineup if _status(pool_by_id.get(str(player.player_id), {})) in INJURY_FLAGS]
    row["archive_sources"] = sorted({str(item["source"]) for item in discoveries})
    row["projection_robustness_history"] = [
        {"source": item["source"], "source_path": item["source_path"], "source_rank": item.get("source_rank")}
        for item in discoveries
        if any(token in str(item["source"]).lower() for token in ("robust", "exploration", "shortlist", "board"))
    ]
    return row


def _compact(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "rank": row["rank"], "lineup_key": row["lineup_key"],
        "full_roster": row["roster"], "salary": row["salary"],
        "mean": row["mean"], "p90": row["p90"],
        "selector_objective": row["objective_score"],
        "relative_chalk": row.get("relative_chalk"),
        "ownership_sum": row.get("ownership_sum"),
        "qb": row["qb"], "stack": row["stack"],
        "football_sanity": row["sanity"], "injury_flags": row["injury_flags"],
        "projection_robustness_history": row["projection_robustness_history"],
        "archive_sources": row["archive_sources"],
        "objective_decomposition": row.get("components") or {},
    }


def _best_stack_family(ranked: list[dict[str, Any]], *, partners: int | None = None,
                       bring_back: bool | None = None) -> dict[str, Any] | None:
    for row in ranked:
        stack = row["stack"]
        if partners is not None and int(stack.get("partner_count") or 0) != partners:
            continue
        has_bring_back = int(stack.get("bring_back_count") or 0) > 0
        if bring_back is not None and has_bring_back != bring_back:
            continue
        return _compact(row)
    return None


def _rank_impact(ranked: list[dict[str, Any]], baseline: Mapping[str, Any] | None,
                 board_payload: Mapping[str, Any]) -> dict[str, Any]:
    prior = list((baseline or {}).get("ranked_candidates") or [])
    current_by_key = {row["lineup_key"]: row for row in ranked}
    prior_top = [str(row["lineup_key"]) for row in prior[:20]]
    current_top = [str(row["lineup_key"]) for row in ranked[:20]]
    prior_top_set = set(prior_top)
    board_ranks = {}
    for configured in board_payload["lineups"]:
        key = lineup_key(configured["player_ids"])
        board_ranks[configured["label"]] = {
            "before": next((row.get("rank") for row in prior if row.get("lineup_key") == key), None),
            "after": current_by_key.get(key, {}).get("rank"),
        }
    old_winner = prior[0]["lineup_key"] if prior else None
    return {
        "top_20_overlap_count": len(prior_top_set & set(current_top)),
        "top_20_overlap_lineup_keys": [key for key in current_top if key in prior_top_set],
        "previous_number_one": {
            "lineup_key": old_winner,
            "before_rank": 1 if old_winner else None,
            "after_rank": current_by_key.get(old_winner, {}).get("rank") if old_winner else None,
        },
        "board_ranks": board_ranks,
        "best_no_bring_back": _best_stack_family(ranked, bring_back=False),
        "best_qb_plus_1": _best_stack_family(ranked, partners=1),
        "best_qb_plus_2_no_bring_back": _best_stack_family(ranked, partners=2, bring_back=False),
        "best_qb_plus_2_with_bring_back": _best_stack_family(ranked, partners=2, bring_back=True),
    }


def _player_inputs(
    player_ids: set[str], players_by_id: Mapping[str, Any], pool_by_id: Mapping[str, Mapping[str, Any]],
    core_by_id: Mapping[str, Mapping[str, Any]], ownership_by_id: Mapping[str, float],
) -> dict[str, dict[str, Any]]:
    output = {}
    for player_id in sorted(player_ids):
        player = players_by_id.get(player_id)
        source = pool_by_id.get(player_id, {})
        core = core_by_id.get(player_id, {})
        usage = core.get("current_usage") or {}
        output[player_id] = {
            "player": player.name if player else source.get("name"),
            "team": player.team if player else source.get("player_team"),
            "position": player.position if player else source.get("position"),
            "projection": player.projection if player else None,
            "p90": player.ceiling if player else None,
            "ownership": ownership_by_id.get(player_id),
            "status": _status(source),
            "role_classification": core.get("football_classification"),
            "role_confidence": core.get("current_evidence_confidence"),
            "overall_centrality": core.get("overall_centrality"),
            "week_1_targets": usage.get("week_1_targets"),
            "week_1_carries": usage.get("week_1_carries"),
            "week_1_snap_share": usage.get("week_1_snap_share"),
        }
    return output


def _changes(current: Mapping[str, Any], baseline: Mapping[str, Any] | None) -> dict[str, Any]:
    if not baseline:
        return {"status": "baseline_created", "player_input_changes": [], "lineup_changes": []}
    player_changes = []
    prior_players = baseline.get("player_inputs") or {}
    for player_id, row in current["player_inputs"].items():
        old = prior_players.get(player_id)
        if not old:
            player_changes.append({"player_id": player_id, "player": row["player"], "change": "new_player"})
            continue
        fields = {}
        for field in ("projection", "p90", "ownership", "status", "role_classification",
                      "role_confidence", "overall_centrality", "week_1_targets",
                      "week_1_carries", "week_1_snap_share"):
            if old.get(field) != row.get(field):
                fields[field] = {"before": old.get(field), "after": row.get(field)}
        if fields:
            player_changes.append({"player_id": player_id, "player": row["player"], "fields": fields})
    old_lineups = {row["lineup_key"]: row for row in baseline.get("ranked_candidates", [])}
    lineup_changes = []
    for row in current["ranked_candidates"]:
        old = old_lineups.get(row["lineup_key"])
        if not old:
            lineup_changes.append({"lineup_key": row["lineup_key"], "change": "new_lineup", "rank": row["rank"]})
            continue
        fields = {}
        for field in ("rank", "selector_objective", "mean", "p90", "relative_chalk",
                      "football_sanity_deficit"):
            if old.get(field) != row.get(field):
                fields[field] = {"before": old.get(field), "after": row.get(field)}
        if fields:
            lineup_changes.append({"lineup_key": row["lineup_key"], "fields": fields})
    current_keys = {row["lineup_key"] for row in current["ranked_candidates"]}
    for lineup_key_value, old in old_lineups.items():
        if lineup_key_value not in current_keys:
            lineup_changes.append({
                "lineup_key": lineup_key_value,
                "change": "invalidated_or_removed",
                "previous_rank": old.get("rank"),
            })
    return {"status": "available", "player_input_changes": player_changes, "lineup_changes": lineup_changes}


def _movement_reason(current: Mapping[str, Any], previous: Mapping[str, Any] | None) -> str:
    if not previous:
        return "Initial archived-union baseline."
    reasons = []
    if current["mean"] != previous.get("mean"):
        reasons.append(f"mean {current['mean'] - float(previous.get('mean') or 0):+.2f}")
    if current["p90"] != previous.get("p90"):
        reasons.append(f"P90 {current['p90'] - float(previous.get('p90') or 0):+.2f}")
    if current.get("relative_chalk") != previous.get("relative_chalk"):
        reasons.append("ownership/chalk changed")
    sanity = current.get("football_sanity") or current.get("sanity") or {}
    if sanity.get("total_football_sanity_deficit") != previous.get("football_sanity_deficit"):
        reasons.append("football-sanity evidence changed")
    if reasons:
        return ", ".join(reasons)
    if current.get("rank") == previous.get("rank"):
        return "No material movement."
    return "Movement came from other candidates entering or leaving the legal union."


def _markdown(payload: Mapping[str, Any]) -> str:
    lines = ["# Sunday Main final decision pipeline", "",
             f"Projection run: `{payload['projection_run_id']}`", "",
             "## Archive", ""]
    for key, value in payload["archive_counts"].items():
        lines.append(f"- {key.replace('_', ' ').title()}: {value}")
    legality = payload["legality_fix_impact"]
    lines += ["", "## Archive legality fix", "",
              f"- Previous legal count: {legality['previous_legal_count']}",
              f"- New legal count: {legality['new_legal_count']}",
              f"- Restored bring-back-missing candidates: {legality['restored_bring_back_missing_count']}",
              f"- Still invalid: {legality['still_invalid_count']}",
              f"- Remaining reasons: {legality['remaining_reason_counts']}", ""]
    lines += ["", "## Top 10", "",
              "| Rank | QB | Stack | Salary | Mean | P90 | Objective | Chalk | Sanity |",
              "|---:|---|---|---:|---:|---:|---:|---:|---:|"]
    for row in payload["top_10"]:
        lines.append(
            f"| {row['rank']} | {row['qb']['name']} | {row['stack']['type']} | {row['salary']} | "
            f"{row['mean']:.2f} | {row['p90']:.2f} | {row['selector_objective']:.4f} | "
            f"{row['relative_chalk'] if row['relative_chalk'] is not None else 'Unavailable'} | "
            f"{row['football_sanity']['total_football_sanity_deficit']:.3f} |"
        )
    lines += ["", "## A / B / C board", ""]
    for row in payload["board"]:
        roster = (
            ", ".join(player["name"] for player in row["lineup"]["full_roster"])
            if row.get("lineup") else "Invalidated under current inputs"
        )
        lines += [f"### {row['label']}", "", roster, "", f"- Today rank: {row['today_rank']}",
                  f"- Current refreshed rank: {row['current_rank']}", f"- Movement: {row['movement']}",
                  f"- Reason: {row['movement_reason']}", ""]
    lines += ["## Serious consideration", ""]
    for row in payload["serious_consideration"]:
        lines += [f"### Rank {row['rank']} — {row['qb']['name']} / {row['stack']['type']}", "",
                  "| Player | Pos | Salary | Projection | P90 | Ownership | Football role | Injury |",
                  "|---|---|---:|---:|---:|---:|---|---|"]
        for player in row["full_roster"]:
            ownership = player.get("ownership")
            lines.append(
                f"| {player['name']} | {player['position']} | {player['salary']} | "
                f"{player['projection']:.2f} | {player['p90']:.2f} | "
                f"{ownership if ownership is not None else 'Unavailable'} | "
                f"{player['football_role']} | {player['injury_status']} |"
            )
        lines.append("")
    lines += ["## Decision questions", ""]
    for index, answer in enumerate(payload["decision_questions"], 1):
        lines.append(f"{index}. {answer}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--projection-run-id", required=True)
    parser.add_argument("--current-artifact", action="append", type=Path, default=[])
    parser.add_argument("--historical-artifact", action="append", type=Path, default=[])
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--board", type=Path, required=True)
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--refresh-manifest", type=Path)
    parser.add_argument("--require-complete-refresh", action="store_true")
    parser.add_argument("--require-official-inactives", action="store_true")
    parser.add_argument("--require-confirmed-starting-qbs", action="store_true")
    parser.add_argument("--refresh-after", help="Require every refresh domain at or after this ISO timestamp")
    parser.add_argument("--require-lineage-match", action="store_true")
    parser.add_argument("--require-roster-preflight", action="store_true")
    parser.add_argument("--baseline-report", type=Path)
    parser.add_argument("--entry-count", type=int)
    parser.add_argument("--refresh-id", default="")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    observed_at = datetime.now(timezone.utc).isoformat()
    refresh_id = args.refresh_id or observed_at.replace(":", "").replace("+00:00", "Z")
    refresh_after = (
        datetime.fromisoformat(args.refresh_after.replace("Z", "+00:00"))
        if args.refresh_after else None
    )
    if refresh_after and refresh_after.tzinfo is None:
        refresh_after = refresh_after.replace(tzinfo=timezone.utc)
    manifest = _refresh_manifest(
        args.refresh_manifest, require_complete=args.require_complete_refresh,
        refresh_after=refresh_after,
        require_official_inactives=args.require_official_inactives,
        require_confirmed_starting_qbs=args.require_confirmed_starting_qbs,
    )
    board_payload = json.loads(args.board.read_text())
    archive = load_archive(args.archive, season=2026, week=2, slate="SUNDAY_MAIN")
    discoveries = []
    current_keys: set[str] = set()
    for path in args.current_artifact:
        rows = artifact_candidates(path, source=f"current:{path}")
        discoveries.extend(rows)
        current_keys.update(row["lineup_key"] for row in rows)
    for path in args.historical_artifact:
        discoveries.extend(artifact_candidates(path, source=f"historical:{path}"))
    board_rows = artifact_candidates(args.board, source=f"board:{args.board}")
    discoveries.extend(board_rows)
    merge_counts = merge_discoveries(archive, discoveries, observed_at=observed_at)
    previous_validations = {
        key: dict(candidate.get("current_validation") or {})
        for key, candidate in archive["candidates"].items()
    }

    players, pool_by_id = prepare_pool(args.projection_run_id, None)
    players_by_id = {str(player.player_id): player for player in players}
    roster_preflight = _roster_mapping_preflight(players, pool_by_id)
    if args.require_roster_preflight and roster_preflight["status"] != "passed":
        raise ValueError(
            "Current roster mapping preflight failed: "
            + ", ".join(
                f"{row['player']} ({'; '.join(row['reasons'])})"
                for row in roster_preflight["conflicts"][:20]
            )
        )
    ownership_by_id, ownership_run = latest_ownership()
    if args.require_lineage_match:
        projection_manifest_id = str(manifest["domains"]["projections"].get("run_id") or "")
        ownership_manifest_id = str(manifest["domains"]["ownership"].get("run_id") or "")
        current_ownership_id = str(ownership_run.get("ownership_run_id") or "")
        if projection_manifest_id != args.projection_run_id:
            raise ValueError(
                f"Refresh manifest projection run {projection_manifest_id!r} does not match "
                f"requested run {args.projection_run_id!r}"
            )
        if ownership_manifest_id != current_ownership_id:
            raise ValueError(
                f"Refresh manifest ownership run {ownership_manifest_id!r} does not match "
                f"latest run {current_ownership_id!r}"
            )
    core_by_id = _core_rows(args.core)
    seed = run_gpp_pipeline(
        2026, 2, "SUNDAY_MAIN", num_lineups=1, engine=engine, players=players,
        ownership_available=False, max_exposure=1.0, enforce_single_te=True,
        avoid_dst_opponents=True, large_gpp=True, minimum_uniqueness=2,
        max_from_team=4, max_from_game=5, include_control_comparisons=False,
    )
    config = seed.config
    legal = []
    invalidated = []
    for key, candidate in archive["candidates"].items():
        validation = validate_candidate(
            candidate["player_ids"], players_by_id=players_by_id, pool_by_id=pool_by_id,
            single_te=True, excluded_opponents={"DEN"}, max_from_team=4,
            max_from_game=5, avoid_dst_opponents=True, require_bring_back=False,
        )
        validation.update({"refresh_id": refresh_id, "projection_run_id": args.projection_run_id,
                           "validated_at": observed_at})
        candidate["current_validation"] = validation
        if validation["legal"]:
            legal.append(candidate)
        else:
            invalidated.append({"lineup_key": key, **validation})

    game_totals = sorted({float(player.game_total) for player in players if player.game_total is not None})
    ranked = []
    for candidate in legal:
        row = _candidate_report(
            candidate["player_ids"], players_by_id=players_by_id, all_players=players,
            config=config, pool_by_id=pool_by_id, core_by_id=core_by_id,
            ownership_by_id=ownership_by_id, game_totals=game_totals,
            discoveries=candidate["discoveries"],
        )
        row["lineup_key"] = candidate["lineup_key"]
        ranked.append(row)
    ranked.sort(key=lambda row: (
        -float(row["objective_score"]), -float(row["mean"]), str(row["lineup_key"]),
    ))
    complete = [row for row in ranked if row["ownership_complete"]]
    percentiles = relative_percentiles([float(row["log_ownership"]) for row in complete])
    for row in ranked:
        row["relative_chalk"] = None
    for row, percentile in zip(complete, percentiles, strict=True):
        row["relative_chalk"] = percentile
    for rank, row in enumerate(ranked, 1):
        row["rank"] = rank

    restored = []
    for row in ranked:
        previous = previous_validations.get(row["lineup_key"], {})
        if "bring_back_missing" in (previous.get("reasons") or []):
            restored.append(row)
    remaining_reason_counts: dict[str, int] = {}
    for row in invalidated:
        for reason in row["reasons"]:
            reason_class = str(reason).split(":", 1)[0]
            remaining_reason_counts[reason_class] = remaining_reason_counts.get(reason_class, 0) + 1
    previous_legal_count = sum(bool(row.get("legal")) for row in previous_validations.values())
    legality_fix_impact = {
        "previous_legal_count": previous_legal_count,
        "new_legal_count": len(ranked),
        "restored_bring_back_missing_count": len(restored),
        "still_invalid_count": len(invalidated),
        "remaining_reason_counts": dict(sorted(remaining_reason_counts.items())),
    }

    prior_archive_keys = {
        key for key, candidate in archive["candidates"].items()
        if candidate["first_seen_at"] != observed_at
    }
    retained_prior = sum(row["lineup_key"] in prior_archive_keys for row in ranked)
    archive_counts = {
        "archive_candidate_count": len(archive["candidates"]),
        "newly_generated_unique_candidate_count": len(current_keys),
        "new_archive_candidate_count": merge_counts["new_archive_candidates"],
        "retained_prior_legal_candidate_count": retained_prior,
        "invalidated_candidate_count": len(invalidated),
        "duplicates_removed": merge_counts["duplicates_removed"],
        "legal_union_candidate_count": len(ranked),
    }
    archive["refresh_history"].append({
        "refresh_id": refresh_id, "observed_at": observed_at,
        "projection_run_id": args.projection_run_id, "counts": archive_counts,
        "refresh_manifest_status": manifest["status"],
    })
    snapshot = persist_archive(args.archive, archive, refresh_id=refresh_id)

    all_ids = {player_id for candidate in archive["candidates"].values() for player_id in candidate["player_ids"]}
    player_inputs = _player_inputs(all_ids, players_by_id, pool_by_id, core_by_id, ownership_by_id)
    ranked_compact = [{
        "lineup_key": row["lineup_key"], "rank": row["rank"],
        "selector_objective": row["objective_score"], "mean": row["mean"], "p90": row["p90"],
        "relative_chalk": row["relative_chalk"],
        "football_sanity_deficit": row["sanity"]["total_football_sanity_deficit"],
    } for row in ranked]
    current_state = {"player_inputs": player_inputs, "ranked_candidates": ranked_compact}
    baseline = json.loads(args.baseline_report.read_text()) if args.baseline_report else None
    change_report = _changes(current_state, baseline)
    rank_impact = _rank_impact(ranked, baseline, board_payload)
    ranked_by_key = {row["lineup_key"]: row for row in ranked}
    prior_by_key = {row["lineup_key"]: row for row in (baseline or {}).get("ranked_candidates", [])}

    board = []
    for configured in board_payload["lineups"]:
        key = lineup_key(configured["player_ids"])
        row = ranked_by_key.get(key)
        if row is None:
            board.append({"label": configured["label"], "today_rank": configured["today_rank"],
                          "current_rank": None, "movement": None,
                          "movement_reason": archive["candidates"][key]["current_validation"]["reasons"],
                          "lineup": None})
            continue
        current_rank = int(row["rank"])
        previous = prior_by_key.get(key)
        board.append({
            "label": configured["label"], "interpretation": configured["interpretation"],
            "today_rank": configured["today_rank"], "current_rank": current_rank,
            "movement": int(configured["today_rank"]) - current_rank,
            "movement_reason": _movement_reason(row, previous),
            "lineup": _compact(row),
        })

    serious_keys = {row["lineup_key"] for row in ranked[:10]} | {
        lineup_key(row["player_ids"]) for row in board_payload["lineups"]
    }
    serious = [_compact(row) for row in ranked if row["lineup_key"] in serious_keys]
    restored_top_10 = [_compact(row) for row in restored if int(row["rank"]) <= 10]
    no_bring_back_audit = []
    for row in ranked:
        if int(row["stack"].get("bring_back_count") or 0) > 0:
            continue
        candidate = archive["candidates"][row["lineup_key"]]
        no_bring_back_audit.append({
            "rank": row["rank"], "qb": row["qb"], "stack": row["stack"],
            "lineup_key": row["lineup_key"], "full_roster": row["roster"],
            "validation": candidate["current_validation"],
            "previous_validation": previous_validations.get(row["lineup_key"]),
            "archive_sources": row["archive_sources"],
        })
        if len(no_bring_back_audit) >= 10:
            break
    brissett_qb2 = next((row for row in ranked
                         if row["qb"]["name"] == "Jacoby Brissett"
                         and int(row["stack"].get("partner_count") or 0) == 2
                         and int(row["stack"].get("bring_back_count") or 0) == 0), None)
    qb_best: dict[str, dict[str, Any]] = {}
    for row in ranked:
        qb_best.setdefault(row["qb"]["name"], row)
    qb_order = sorted(qb_best.values(), key=lambda row: -row["objective_score"])
    board_map = {row["label"]: row for row in board}
    top10_names = [player["name"] for row in ranked[:10] for player in row["roster"]]
    new_top = [row for row in ranked[:10] if row["lineup_key"] not in {
        lineup_key(item["player_ids"]) for item in board_payload["lineups"]
    }]
    contest_answer = (
        f"Use the current top {args.entry_count} legal union lineup(s), then map them to the configured contests."
        if args.entry_count else
        "Contest entry count/assignment was not supplied; final contest lineup mapping remains pending."
    )
    questions = [
        (f"Refresh evidence is {manifest['status']}; {len(change_report['player_input_changes'])} player input changes "
         f"and {len(change_report['lineup_changes'])} lineup changes were detected."),
        f"Best QB family is {qb_order[0]['qb']['name']} with objective {qb_order[0]['objective_score']:.4f}; "
        f"the next family is {qb_order[1]['qb']['name']} at a {qb_order[0]['objective_score'] - qb_order[1]['objective_score']:.4f} gap.",
        "Henry / Brown / Coker / Olave top-10 appearances: " + ", ".join(
            f"{name}={top10_names.count(name)}/10" for name in ("Derrick Henry", "Chase Brown", "Jalen Coker", "Chris Olave")
        ) + ".",
        f"Michael Wilson appears in {top10_names.count('Michael Wilson')}/10 top lineups; retain only if that current rank/value still justifies the documented model disagreement.",
        f"A current rank is {board_map['A']['current_rank']}; " + ("it remains #1." if board_map["A"]["current_rank"] == 1 else "it does not remain #1."),
        f"B current rank is {board_map['B']['current_rank']}; robustness remains diagnostic and its current metrics are shown on the board.",
        f"C current rank is {board_map['C']['current_rank']}; it remains a legal projection-risk hedge." if board_map["C"]["current_rank"] else "C is no longer legal.",
        (f"{len(new_top)} non-board candidate(s) are in the current top 10; compare them in the serious-consideration table before replacing A/B/C."),
        contest_answer,
    ]
    payload = {
        "contract_id": "sunday_main_final_decision_v1", "generated_at": observed_at,
        "refresh_id": refresh_id, "projection_run_id": args.projection_run_id,
        "archive_path": str(args.archive), "archive_snapshot": str(snapshot),
        "archive_counts": archive_counts, "refresh_manifest": manifest,
        "roster_mapping_preflight": roster_preflight,
        "controlled_refresh_passes": manifest.get("controlled_refresh_passes") or [],
        "legality_fix_impact": legality_fix_impact, "rank_impact": rank_impact,
        "restored_top_10": restored_top_10,
        "previously_legal_no_bring_back_audit": no_bring_back_audit,
        "former_brissett_qb2_no_bring_back": _compact(brissett_qb2) if brissett_qb2 else None,
        "ownership_run_id": str(ownership_run.get("ownership_run_id") or "") or None,
        "invalidated_candidates": invalidated, "player_inputs": player_inputs,
        "ranked_candidates": ranked_compact, "top_10": [_compact(row) for row in ranked[:10]],
        "serious_consideration": serious, "board": board,
        "change_report": change_report, "decision_questions": questions,
        "production_projection_changes": "None made by this pipeline",
        "production_selector_changes": "None made by this pipeline",
    }
    args.output.write_text(json.dumps(payload, indent=2, default=str, allow_nan=False) + "\n")
    args.output.with_suffix(".md").write_text(_markdown(payload))
    print(json.dumps({"output": str(args.output), "archive": str(args.archive),
                      "counts": archive_counts, "top_lineup": payload["top_10"][0]["lineup_key"]}, indent=2))


if __name__ == "__main__":
    main()
