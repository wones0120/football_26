from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal
from backend.app.services.lineup_learning import (
    LineupLearningService,
    PlayerPoolRow,
    _zscore,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the pre-lock popularity and lineup-duplication proxies on historical "
            "classic slates without treating them as observed ownership."
        )
    )
    parser.add_argument("--source-system", default="draftkings", choices=["draftkings", "fanduel"])
    parser.add_argument("--season-start", type=int, default=2024)
    parser.add_argument("--season-end", type=int, default=2025)
    parser.add_argument("--slate", type=str, default=None)
    parser.add_argument("--candidate-lineups", type=int, default=2500)
    parser.add_argument("--selected-lineups", type=int, default=20)
    parser.add_argument("--min-salary-floor", type=int, default=43000)
    parser.add_argument("--penalties", type=str, default="0,0.25,0.5,0.75")
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--limit-slates", type=int, default=12)
    parser.add_argument(
        "--output-json",
        type=str,
        default="docs/popularity_proxy_validation_2024_2025.json",
    )
    parser.add_argument(
        "--output-md",
        type=str,
        default="docs/popularity_proxy_validation_2024_2025.md",
    )
    return parser.parse_args()


def _parse_penalties(raw: str) -> list[float]:
    values = sorted({float(value.strip()) for value in raw.split(",") if value.strip()})
    if not values or values[0] < 0.0 or values[-1] > 1.0:
        raise ValueError("--penalties must contain comma-separated values between 0 and 1.")
    if 0.0 not in values:
        values.insert(0, 0.0)
    return values


def _impute_projection_gaps(players: list[PlayerPoolRow]) -> None:
    by_position: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for player in players:
        if player.projected_mean_points > 0 and player.projected_p90_points > 0:
            by_position[player.position].append(
                (player.projected_mean_points, player.projected_p90_points)
            )
    all_pairs = [pair for pairs in by_position.values() for pair in pairs]
    global_mean = float(np.mean([pair[0] for pair in all_pairs] or [8.0]))
    global_p90 = float(np.mean([pair[1] for pair in all_pairs] or [14.0]))
    for player in players:
        if player.projected_mean_points > 0 and player.projected_p90_points > 0:
            continue
        position_pairs = by_position.get(player.position, [])
        if position_pairs:
            player.projected_mean_points = float(
                np.mean([pair[0] for pair in position_pairs])
            )
            player.projected_p90_points = float(
                np.mean([pair[1] for pair in position_pairs])
            )
        else:
            player.projected_mean_points = global_mean
            player.projected_p90_points = global_p90


def _max_player_exposure(lineups: list[list[PlayerPoolRow]]) -> float:
    if not lineups:
        return 0.0
    counts = Counter(player.uid for lineup in lineups for player in lineup)
    return float(max(counts.values(), default=0) / len(lineups))


def _mean(values: list[float]) -> float | None:
    return float(statistics.mean(values)) if values else None


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
    tracked_worktree_dirty = (
        bool(status_result.stdout.strip())
        if status_result.returncode == 0
        else None
    )
    return revision_result.stdout.strip() or None, tracked_worktree_dirty


def _render_markdown(payload: dict[str, Any]) -> str:
    metadata = payload["metadata"]
    summaries = payload["penalty_summary"]
    baseline = next(row for row in summaries if row["penalty"] == 0.0)

    lines = [
        "# Popularity and Duplication Proxy Validation",
        "",
        (
            f"- Source: `{metadata['source_system']}`  "
            f"Seasons: `{metadata['season_start']}-{metadata['season_end']}`  "
            f"Classic slates: `{metadata['slates_completed']}`"
        ),
        (
            f"- Candidates requested/slate: `{metadata['candidate_lineups_requested']}`  "
            f"Generated mean: `{metadata['candidate_lineups_generated_mean']:.0f}` "
            f"(range `{metadata['candidate_lineups_generated_min']}-"
            f"{metadata['candidate_lineups_generated_max']}`)  "
            f"Selected/slate: `{metadata['selected_lineups']}`  "
            f"Seed: `{metadata['random_seed']}`"
        ),
        "",
        "This is a pre-lock popularity proxy, not observed ownership. Historical actual points are used only to measure the cost of diversification after each slate.",
        "",
        "## Method",
        "",
        "- Player popularity proxy: position-relative salary, projection, ceiling, and value ranks plus implied-total and generated-candidate-exposure ranks.",
        "- Lineup duplication risk: 60% top-five player proxy pressure, 25% generated pair-concentration pressure, and 15% salary-cap usage.",
        "- Penalty: a caller-selected zero-to-one weight applied to standardized proxy risk; zero leaves ranking unchanged.",
        "",
        "## Penalty Comparison",
        "",
        "| Penalty | Duplication risk | Projected blend | Actual mean | Best actual | Max player exposure |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summaries:
        lines.append(
            f"| {row['penalty']:.2f} | {row['mean_duplication_risk']:.3f} | "
            f"{row['mean_projected_blend_points']:.2f} | {row['mean_actual_points']:.2f} | "
            f"{row['mean_best_actual_points']:.2f} | {row['mean_max_player_exposure']:.1%} |"
        )

    lines.extend(["", "## Tradeoffs Versus No Penalty", ""])
    for row in summaries:
        if row["penalty"] == 0.0:
            continue
        risk_change = (
            (row["mean_duplication_risk"] / baseline["mean_duplication_risk"]) - 1.0
            if baseline["mean_duplication_risk"] > 0
            else 0.0
        )
        projection_change = (
            (
                row["mean_projected_blend_points"]
                / baseline["mean_projected_blend_points"]
            )
            - 1.0
            if baseline["mean_projected_blend_points"] > 0
            else 0.0
        )
        actual_change = row["mean_actual_points"] - baseline["mean_actual_points"]
        lines.append(
            f"- Penalty `{row['penalty']:.2f}`: risk `{risk_change:+.1%}`, "
            f"projection `{projection_change:+.1%}`, actual points `{actual_change:+.2f}`."
        )
    lines.extend(
        [
            "",
            "No penalty is promoted automatically. Use these results to choose an explicit GPP diversification setting and keep the default at zero.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    penalties = _parse_penalties(args.penalties)
    season_start = min(args.season_start, args.season_end)
    season_end = max(args.season_start, args.season_end)
    rng = np.random.default_rng(args.random_seed)
    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    with SessionLocal() as session:
        service = LineupLearningService(session)
        slices = service._fetch_available_slate_slices(
            source_system=args.source_system,
            season_start=season_start,
            season_end=season_end,
            slate_filter=args.slate,
        )
        classic_slices = [
            slice_key
            for slice_key in slices
            if service._classify_slate_type(
                source_system=args.source_system,
                season=slice_key[0],
                week=slice_key[1],
                slate=slice_key[2],
            )
            == "classic"
        ]
        if args.limit_slates > 0:
            classic_slices = classic_slices[-args.limit_slates :]

        for index, (season, week, slate) in enumerate(classic_slices, start=1):
            print(
                f"[popularity_proxy] {index}/{len(classic_slices)} "
                f"{season}-W{week:02d} {slate}",
                flush=True,
            )
            projection_lookup, dst_projection_lookup = (
                service._compute_player_projection_lookup(
                    source_system=args.source_system,
                    season=season,
                    week=week,
                    slate=slate,
                )
            )
            pool = service._fetch_slate_player_pool(
                source_system=args.source_system,
                season=season,
                week=week,
                slate=slate,
                projection_lookup=projection_lookup,
                dst_projection_lookup=dst_projection_lookup,
            )
            _impute_projection_gaps(pool)
            candidates = service._generate_candidate_lineups_adaptive(
                players=pool,
                requested_lineups=args.candidate_lineups,
                min_salary_floor=args.min_salary_floor,
                rng=rng,
            )
            if len(candidates) < args.selected_lineups:
                skipped.append(
                    {
                        "season": season,
                        "week": week,
                        "slate": slate,
                        "reason": f"only {len(candidates)} candidates generated",
                    }
                )
                continue

            popularity, _candidate_exposure = service._classic_player_popularity_proxy(
                players=pool,
                candidate_lineups=candidates,
            )
            risks = service._classic_lineup_duplication_risk_scores(
                lineups=candidates,
                popularity_by_uid=popularity,
            )
            projected_points = np.asarray(
                [
                    sum(
                        (0.65 * player.projected_mean_points)
                        + (0.35 * player.projected_p90_points)
                        for player in lineup
                    )
                    for lineup in candidates
                ],
                dtype=float,
            )
            actual_points = np.asarray(
                [sum(player.actual_points for player in lineup) for lineup in candidates],
                dtype=float,
            )
            base_scores = _zscore(projected_points)

            for penalty in penalties:
                adjusted_scores = service._apply_duplication_risk_penalty(
                    composite_scores=base_scores,
                    duplication_risk_scores=risks,
                    penalty_strength=penalty,
                )
                selected_idx = np.argsort(-adjusted_scores)[: args.selected_lineups]
                selected = [candidates[int(raw_idx)] for raw_idx in selected_idx]
                rows.append(
                    {
                        "season": season,
                        "week": week,
                        "slate": slate,
                        "penalty": penalty,
                        "candidate_lineups": len(candidates),
                        "mean_duplication_risk": float(np.mean(risks[selected_idx])),
                        "mean_projected_blend_points": float(
                            np.mean(projected_points[selected_idx])
                        ),
                        "mean_actual_points": float(np.mean(actual_points[selected_idx])),
                        "best_actual_points": float(np.max(actual_points[selected_idx])),
                        "max_player_exposure": _max_player_exposure(selected),
                    }
                )

    penalty_summary: list[dict[str, Any]] = []
    for penalty in penalties:
        penalty_rows = [row for row in rows if row["penalty"] == penalty]
        if not penalty_rows:
            continue
        penalty_summary.append(
            {
                "penalty": penalty,
                "slates": len(penalty_rows),
                "mean_duplication_risk": _mean(
                    [row["mean_duplication_risk"] for row in penalty_rows]
                ),
                "mean_projected_blend_points": _mean(
                    [row["mean_projected_blend_points"] for row in penalty_rows]
                ),
                "mean_actual_points": _mean(
                    [row["mean_actual_points"] for row in penalty_rows]
                ),
                "mean_best_actual_points": _mean(
                    [row["best_actual_points"] for row in penalty_rows]
                ),
                "mean_max_player_exposure": _mean(
                    [row["max_player_exposure"] for row in penalty_rows]
                ),
            }
        )
    if not penalty_summary:
        raise ValueError("No historical classic slates produced enough candidate lineups.")

    code_revision, tracked_worktree_dirty = _git_metadata()
    baseline_rows = [row for row in rows if row["penalty"] == 0.0]
    generated_counts = [int(row["candidate_lineups"]) for row in baseline_rows]
    metadata = {
        "generated_at": datetime.now(UTC).isoformat(),
        "code_revision": code_revision,
        "tracked_worktree_dirty": tracked_worktree_dirty,
        "source_system": args.source_system,
        "season_start": season_start,
        "season_end": season_end,
        "slate_filter": args.slate,
        "candidate_lineups_requested": args.candidate_lineups,
        "candidate_lineups_generated_mean": _mean(
            [float(count) for count in generated_counts]
        ),
        "candidate_lineups_generated_min": min(generated_counts, default=0),
        "candidate_lineups_generated_max": max(generated_counts, default=0),
        "selected_lineups": args.selected_lineups,
        "min_salary_floor": args.min_salary_floor,
        "penalties": penalties,
        "random_seed": args.random_seed,
        "limit_slates": args.limit_slates,
        "slates_completed": len({(row["season"], row["week"], row["slate"]) for row in rows}),
        "slates_skipped": len(skipped),
        "ownership_claim": "popularity_proxy_not_observed_ownership",
    }
    payload = {
        "metadata": metadata,
        "penalty_summary": penalty_summary,
        "slate_rows": rows,
        "skipped": skipped,
    }
    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    output_md.write_text(_render_markdown(payload), encoding="utf-8")
    print(json.dumps({"metadata": metadata, "penalty_summary": penalty_summary}, indent=2))


if __name__ == "__main__":
    main()
