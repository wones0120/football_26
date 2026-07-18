from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal
from backend.app.models import CuratedSalary
from backend.app.schemas import RoleShockRequest
from backend.app.services.lineup_learning import LineupLearningService, PlayerPoolRow
from backend.app.services.simulation import SimulationService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Measure player-projection and top-lineup fragility under a manual, pre-lock "
            "role-shock scenario."
        )
    )
    parser.add_argument("--source-system", default="draftkings", choices=["draftkings", "fanduel"])
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--slate", type=str, default="sunday_main")
    identity = parser.add_mutually_exclusive_group(required=True)
    identity.add_argument("--player-master-id", type=str)
    identity.add_argument("--source-player-key", type=str)
    identity.add_argument("--player-name", type=str)
    parser.add_argument("--retained-opportunity-share", type=float, default=0.0)
    parser.add_argument(
        "--reallocation-scope",
        choices=["same_position", "skill_players"],
        default="same_position",
    )
    parser.add_argument("--max-recipient-multiplier", type=float, default=2.0)
    parser.add_argument("--iterations", type=int, default=3000)
    parser.add_argument("--candidate-lineups", type=int, default=2500)
    parser.add_argument("--selected-lineups", type=int, default=20)
    parser.add_argument("--min-salary-floor", type=int, default=43000)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument(
        "--output-json",
        type=str,
        default="docs/role_shock_fragility_2025_w18.json",
    )
    parser.add_argument(
        "--output-md",
        type=str,
        default="docs/role_shock_fragility_2025_w18.md",
    )
    return parser.parse_args()


def _git_metadata() -> tuple[str | None, bool | None]:
    revision_result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if revision_result.returncode != 0:
        return None, None
    status_result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    dirty = (
        bool(status_result.stdout.strip())
        if status_result.returncode == 0
        else None
    )
    return revision_result.stdout.strip() or None, dirty


def _resolve_identity(
    *,
    session: Session,
    source_system: str,
    season: int,
    week: int,
    slate: str,
    player_master_id: str | None,
    source_player_key: str | None,
    player_name: str | None,
) -> tuple[str | None, str | None, str]:
    salary_rows = session.execute(
        select(CuratedSalary).where(
            and_(
                CuratedSalary.source_system == source_system,
                CuratedSalary.season == season,
                CuratedSalary.week == week,
                CuratedSalary.slate == slate,
            )
        )
    ).scalars().all()
    matches = [
        row
        for row in salary_rows
        if (
            player_master_id
            and row.player_master_id == player_master_id
        )
        or (
            source_player_key
            and row.source_player_key == source_player_key
        )
        or (
            player_name
            and row.player_name.strip().casefold() == player_name.strip().casefold()
        )
    ]
    identities = {
        (row.player_master_id, row.source_player_key, row.player_name)
        for row in matches
    }
    if not identities:
        raise ValueError("Role-shock target was not found in the selected salary slice.")
    if len(identities) > 1:
        raise ValueError("Role-shock target is ambiguous in the selected salary slice.")
    return next(iter(identities))


def _projection_lookup(
    rows: list[dict[str, Any]],
    fallback: dict[str, tuple[float, float]],
) -> dict[str, tuple[float, float]]:
    result = dict(fallback)
    for row in rows:
        projection = (float(row["mean_points"]), float(row["p90_points"]))
        for key in (row.get("player_master_id"), row.get("source_player_key")):
            if key:
                result[str(key)] = projection
    return result


def _lineup_score(
    lineup: list[PlayerPoolRow],
    player_by_uid: dict[str, PlayerPoolRow],
) -> float:
    return float(
        sum(
            (0.65 * player_by_uid[player.uid].projected_mean_points)
            + (0.35 * player_by_uid[player.uid].projected_p90_points)
            for player in lineup
            if player.uid in player_by_uid
        )
    )


def _exposures(lineups: list[list[PlayerPoolRow]]) -> dict[str, float]:
    if not lineups:
        return {}
    counts = Counter(player.uid for lineup in lineups for player in lineup)
    return {
        uid: float(count / len(lineups))
        for uid, count in counts.items()
    }


def _render_markdown(payload: dict[str, Any]) -> str:
    metadata = payload["metadata"]
    summary = payload["summary"]
    impacts = payload["role_shock_impacts"]
    exposure_changes = payload["largest_exposure_changes"]
    lines = [
        "# Role-Shock Lineup Fragility",
        "",
        (
            f"- Slice: `{metadata['source_system']} {metadata['season']}-W"
            f"{metadata['week']:02d} {metadata['slate']}`"
        ),
        (
            f"- Target: `{metadata['target_player_name']}`  "
            f"Retained opportunity: `{metadata['retained_opportunity_share']:.0%}`  "
            f"Scope: `{metadata['reallocation_scope']}`"
        ),
        (
            f"- Simulation iterations: `{metadata['iterations']}`  "
            f"Candidates generated/requested: `{metadata['candidate_lineups_generated']}/"
            f"{metadata['candidate_lineups_requested']}`  "
            f"Selected: `{metadata['selected_lineups']}`"
        ),
        "",
        "This is a manually triggered pre-lock stress test, not a claim that an injury or role change occurred historically.",
        "The comparison reranks one shared candidate set by 65% simulated mean plus 35% simulated P90 without applying portfolio exposure caps.",
        "",
        "## Portfolio Fragility",
        "",
        f"- Top-lineup overlap after reoptimization: `{summary['top_lineup_overlap_rate']:.1%}`.",
        (
            f"- Baseline portfolio scored under the shock: "
            f"`{summary['baseline_portfolio_scenario_score']:.2f}` projected-blend points."
        ),
        (
            f"- Reoptimized shock portfolio: `{summary['scenario_portfolio_score']:.2f}` "
            f"(`{summary['scenario_reoptimization_lift']:+.2f}` lift)."
        ),
        (
            f"- Target exposure: `{summary['target_baseline_exposure']:.1%}` baseline to "
            f"`{summary['target_scenario_exposure']:.1%}` scenario."
        ),
        "",
        "## Projection Impacts",
        "",
        "| Player | Role | Opportunity × | Projection × | Mean Δ | P90 Δ |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in impacts:
        lines.append(
            f"| {row['player_name']} | {row['shock_role']} | "
            f"{row['opportunity_multiplier']:.2f} | {row['projection_multiplier']:.2f} | "
            f"{row['mean_points_delta']:+.2f} | {row['p90_points_delta']:+.2f} |"
        )
    lines.extend(
        [
            "",
            "## Largest Exposure Changes",
            "",
            "| Player | Position | Baseline | Scenario | Delta |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for row in exposure_changes:
        lines.append(
            f"| {row['player_name']} | {row['position']} | "
            f"{row['baseline_exposure']:.1%} | {row['scenario_exposure']:.1%} | "
            f"{row['exposure_delta']:+.1%} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    with SessionLocal() as session:
        target_master_id, target_source_key, target_name = _resolve_identity(
            session=session,
            source_system=args.source_system,
            season=args.season,
            week=args.week,
            slate=args.slate,
            player_master_id=args.player_master_id,
            source_player_key=args.source_player_key,
            player_name=args.player_name,
        )
        shock = RoleShockRequest(
            player_master_id=target_master_id,
            source_player_key=target_source_key,
            retained_opportunity_share=args.retained_opportunity_share,
            reallocation_scope=args.reallocation_scope,
            max_recipient_multiplier=args.max_recipient_multiplier,
        )
        simulation_service = SimulationService(session)
        (
            _baseline_considered,
            baseline_rows,
            _baseline_player_map,
            _baseline_ids,
            _baseline_impacts,
            baseline_warnings,
        ) = simulation_service._simulate_salary_slice(
            source_system=args.source_system,
            season=args.season,
            week=args.week,
            slate=args.slate,
            iterations=args.iterations,
            min_history_games=4,
            prior_weight=12.0,
            noise_scale=0.12,
            random_seed=args.random_seed,
            use_calibration=True,
        )
        (
            _scenario_considered,
            scenario_rows,
            _scenario_player_map,
            _scenario_ids,
            role_shock_impacts,
            scenario_warnings,
        ) = simulation_service._simulate_salary_slice(
            source_system=args.source_system,
            season=args.season,
            week=args.week,
            slate=args.slate,
            iterations=args.iterations,
            min_history_games=4,
            prior_weight=12.0,
            noise_scale=0.12,
            random_seed=args.random_seed,
            use_calibration=True,
            role_shocks=[shock],
        )

        lineup_service = LineupLearningService(session)
        fallback_projection, dst_projection = (
            lineup_service._compute_player_projection_lookup(
                source_system=args.source_system,
                season=args.season,
                week=args.week,
                slate=args.slate,
            )
        )
        baseline_lookup = _projection_lookup(baseline_rows, fallback_projection)
        scenario_lookup = _projection_lookup(scenario_rows, fallback_projection)
        baseline_pool = lineup_service._fetch_slate_player_pool(
            source_system=args.source_system,
            season=args.season,
            week=args.week,
            slate=args.slate,
            projection_lookup=baseline_lookup,
            dst_projection_lookup=dst_projection,
        )
        scenario_pool = lineup_service._fetch_slate_player_pool(
            source_system=args.source_system,
            season=args.season,
            week=args.week,
            slate=args.slate,
            projection_lookup=scenario_lookup,
            dst_projection_lookup=dst_projection,
        )
        candidates = lineup_service._generate_candidate_lineups_adaptive(
            players=baseline_pool,
            requested_lineups=args.candidate_lineups,
            min_salary_floor=args.min_salary_floor,
            rng=np.random.default_rng(args.random_seed + 1),
        )

    if len(candidates) < args.selected_lineups:
        raise ValueError(
            f"Only {len(candidates)} candidate lineups were generated; "
            f"{args.selected_lineups} are required."
        )
    baseline_by_uid = {player.uid: player for player in baseline_pool}
    scenario_by_uid = {player.uid: player for player in scenario_pool}
    baseline_scores = np.asarray(
        [_lineup_score(lineup, baseline_by_uid) for lineup in candidates],
        dtype=float,
    )
    scenario_scores = np.asarray(
        [_lineup_score(lineup, scenario_by_uid) for lineup in candidates],
        dtype=float,
    )
    baseline_idx = np.argsort(-baseline_scores)[: args.selected_lineups]
    scenario_idx = np.argsort(-scenario_scores)[: args.selected_lineups]
    baseline_selected = [candidates[int(index)] for index in baseline_idx]
    scenario_selected = [candidates[int(index)] for index in scenario_idx]
    baseline_signatures = {
        tuple(sorted(player.uid for player in lineup))
        for lineup in baseline_selected
    }
    scenario_signatures = {
        tuple(sorted(player.uid for player in lineup))
        for lineup in scenario_selected
    }
    overlap_rate = float(
        len(baseline_signatures & scenario_signatures) / args.selected_lineups
    )
    baseline_exposure = _exposures(baseline_selected)
    scenario_exposure = _exposures(scenario_selected)
    all_uids = set(baseline_exposure) | set(scenario_exposure)
    identity_rows = {player.uid: player for player in baseline_pool}
    exposure_changes = [
        {
            "uid": uid,
            "player_name": identity_rows[uid].name,
            "team": identity_rows[uid].team,
            "position": identity_rows[uid].position,
            "baseline_exposure": float(baseline_exposure.get(uid, 0.0)),
            "scenario_exposure": float(scenario_exposure.get(uid, 0.0)),
            "exposure_delta": float(
                scenario_exposure.get(uid, 0.0) - baseline_exposure.get(uid, 0.0)
            ),
        }
        for uid in all_uids
        if uid in identity_rows
    ]
    exposure_changes.sort(
        key=lambda row: abs(float(row["exposure_delta"])),
        reverse=True,
    )
    target_uid = target_master_id or target_source_key or ""
    baseline_portfolio_scenario_score = float(
        statistics.mean(float(scenario_scores[int(index)]) for index in baseline_idx)
    )
    scenario_portfolio_score = float(
        statistics.mean(float(scenario_scores[int(index)]) for index in scenario_idx)
    )
    code_revision, dirty = _git_metadata()
    metadata = {
        "generated_at": datetime.now(UTC).isoformat(),
        "code_revision": code_revision,
        "tracked_worktree_dirty": dirty,
        "source_system": args.source_system,
        "season": args.season,
        "week": args.week,
        "slate": args.slate,
        "target_player_master_id": target_master_id,
        "target_source_player_key": target_source_key,
        "target_player_name": target_name,
        "retained_opportunity_share": args.retained_opportunity_share,
        "reallocation_scope": args.reallocation_scope,
        "max_recipient_multiplier": args.max_recipient_multiplier,
        "iterations": args.iterations,
        "candidate_lineups_requested": args.candidate_lineups,
        "candidate_lineups_generated": len(candidates),
        "selected_lineups": args.selected_lineups,
        "min_salary_floor": args.min_salary_floor,
        "random_seed": args.random_seed,
        "scenario_claim": "manual_prelock_stress_test_not_historical_injury",
    }
    payload = {
        "metadata": metadata,
        "summary": {
            "top_lineup_overlap_rate": overlap_rate,
            "baseline_portfolio_score": float(np.mean(baseline_scores[baseline_idx])),
            "baseline_portfolio_scenario_score": baseline_portfolio_scenario_score,
            "scenario_portfolio_score": scenario_portfolio_score,
            "scenario_reoptimization_lift": (
                scenario_portfolio_score - baseline_portfolio_scenario_score
            ),
            "target_baseline_exposure": float(baseline_exposure.get(target_uid, 0.0)),
            "target_scenario_exposure": float(scenario_exposure.get(target_uid, 0.0)),
        },
        "role_shock_impacts": role_shock_impacts,
        "largest_exposure_changes": exposure_changes[:15],
        "baseline_warnings": baseline_warnings,
        "scenario_warnings": scenario_warnings,
    }
    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    output_md.write_text(_render_markdown(payload), encoding="utf-8")
    print(json.dumps({"metadata": metadata, "summary": payload["summary"]}, indent=2))


if __name__ == "__main__":
    main()
