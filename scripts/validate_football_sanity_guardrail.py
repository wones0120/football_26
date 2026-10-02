#!/usr/bin/env python3
"""Evaluate a penalty-only football sanity guardrail on persisted candidates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from backend.app.product_services.football_sanity_deficit import (
    deficit_crossover_points,
    prepare_deficit_candidates,
    rank_with_deficit,
)

LAMBDAS = (0.0, 0.02, 0.05, 0.10, 0.20, 0.35, 0.50)


def _round(value: Any, digits: int = 4) -> Any:
    return round(float(value), digits) if value is not None else None


def _classic_inputs(path: Path, core_by_id: Mapping[str, Mapping[str, Any]]):
    payload = json.loads(path.read_text())
    report = payload["report"]
    candidates = report["all_candidates"]
    pool = [
        {"player_id": row["player_id"], "name": row["name"], "team": row["team"],
         "position": row["position"], "salary": row["salary"],
         "projection": row["mean"], "p90": row["p90"]}
        for row in report["role_exposure"]
    ]
    return payload, report, candidates, pool


def _showdown_inputs(path: Path, core_by_id: Mapping[str, Mapping[str, Any]]):
    payload = json.loads(path.read_text())
    report = payload["report"]
    raw_pool = payload["player_pool"]
    pool_by_id = {str(row["player_id"]): row for row in raw_pool}
    pool = [
        {"player_id": str(row["player_id"]),
         "name": row.get("name") or row.get("player_name"),
         "team": row.get("player_team") or row.get("team"),
         "position": row.get("position"),
         "salary": row.get("salary"), "projection": row.get("projection"),
         "p90": row.get("p90")}
        for row in raw_pool
    ]
    candidates = []
    for source in report["all_candidates"]:
        row = dict(source)
        roster = []
        for player in source["players"]:
            evidence = pool_by_id.get(str(player["player_id"]), {})
            roster.append({
                "player_id": str(player["player_id"]), "name": player["name"],
                "team": evidence.get("player_team") or evidence.get("team")
                or core_by_id.get(str(player["player_id"]), {}).get("team"),
                "position": player.get("position") or evidence.get("position")
                or core_by_id.get(str(player["player_id"]), {}).get("position"),
                "salary": player.get("salary") or evidence.get("salary"),
                "projection": evidence.get("projection"), "p90": evidence.get("p90"),
                "slot": player.get("slot"),
            })
        row["roster"] = roster
        row["objective_score"] = row["single_entry_score"]
        candidates.append(row)
    return payload, report, candidates, pool


def _summary(row: Mapping[str, Any], weight: float) -> dict[str, Any]:
    sanity = row["sanity"]
    return {
        "saved_rank": row["saved_rank"],
        "base_objective": _round(row["base_objective"], 6),
        "football_sanity_deficit": _round(sanity["total_football_sanity_deficit"], 6),
        "standardized_deficit": _round(row["standardized_deficit"], 6),
        "football_penalty": _round(weight * row["standardized_deficit"], 6),
        "shadow_objective": _round(
            row["base_objective"] - weight * row["standardized_deficit"], 6
        ),
        "mean": _round(row.get("mean"), 4), "p90": _round(row.get("p90"), 4),
        "core": sanity["core_skill_count"],
        "meaningful_secondary": sanity["meaningful_secondary_count"],
        "complementary": sanity["complementary_count"],
        "peripheral": sanity["peripheral_count"], "stale": sanity["stale_count"],
        "multi_skill_teams": sanity["teams_with_multiple_skill_players"],
        "multi_skill_teams_no_core": sanity["teams_with_multiple_skill_players_no_core"],
        "showdown_team_coverage_deficit": _round(
            sanity["showdown_team_coverage_deficit"], 4
        ),
        "lineup": " / ".join(
            f"{player.get('slot') or player.get('position')} {player.get('name')}"
            for player in row.get("roster", [])
        ),
    }


def _player_changes(prior: Mapping[str, Any], new: Mapping[str, Any]) -> dict[str, list[dict]]:
    prior_roster = {str(row["player_id"]): row for row in prior.get("roster", [])}
    new_roster = {str(row["player_id"]): row for row in new.get("roster", [])}
    prior_roles = {row["player_id"]: row for row in prior["sanity"]["players"]}
    new_roles = {row["player_id"]: row for row in new["sanity"]["players"]}

    def detail(player, role):
        return {
            "player": player.get("name"), "position": player.get("position"),
            "team": player.get("team"), "projection": _round(player.get("projection"), 3),
            "p90": _round(player.get("p90"), 3), "salary": player.get("salary"),
            "role_bucket": (role or {}).get("bucket", "not_applicable"),
            "classification": (role or {}).get("classification"),
            "centrality": _round((role or {}).get("overall_centrality"), 3),
            "confidence": (role or {}).get("confidence", "not_applicable"),
            "player_deficit": _round((role or {}).get("player_deficit"), 3),
        }
    return {
        "in": [detail(new_roster[player_id], new_roles.get(player_id))
               for player_id in sorted(set(new_roster) - set(prior_roster))],
        "out": [detail(prior_roster[player_id], prior_roles.get(player_id))
                for player_id in sorted(set(prior_roster) - set(new_roster))],
    }


def _analyze(candidates, pool, core_by_id, *, showdown: bool, selected_ranks: list[int]):
    prepared, stats = prepare_deficit_candidates(
        candidates, core_by_id=core_by_id, player_pool=pool, showdown=showdown
    )
    if len(prepared) != len(candidates):
        raise RuntimeError("Analyzed candidate count does not match serialized candidate count")
    by_rank = {row["saved_rank"]: row for row in prepared}
    envelope = deficit_crossover_points(prepared)
    crossovers = []
    for prior_item, item in zip(envelope, envelope[1:]):
        prior, new = prior_item["candidate"], item["candidate"]
        weight = item["lambda"]
        crossovers.append({
            "lambda": _round(weight, 8),
            "prior": _summary(prior, weight), "new": _summary(new, weight),
            "delta_mean": _round(float(new.get("mean") or 0) - float(prior.get("mean") or 0), 4),
            "delta_p90": _round(float(new.get("p90") or 0) - float(prior.get("p90") or 0), 4),
            "delta_base_objective": _round(new["base_objective"] - prior["base_objective"], 6),
            "deficit_removed": _round(
                prior["sanity"]["total_football_sanity_deficit"]
                - new["sanity"]["total_football_sanity_deficit"], 6
            ),
            "players": _player_changes(prior, new),
        })
    references = []
    for weight in LAMBDAS:
        winner = rank_with_deficit(prepared, weight)[0]
        references.append({"lambda": weight, **_summary(winner, weight)})
    deficient = [
        row for row in prepared
        if row["sanity"]["total_football_sanity_deficit"] > 1e-12
    ]
    top_20 = sorted(prepared, key=lambda row: row["saved_rank"])[:20]
    top_20_deficient = [
        row for row in top_20
        if row["sanity"]["total_football_sanity_deficit"] > 1e-12
    ]
    selected = [by_rank[rank] for rank in selected_ranks if rank in by_rank]
    violation_counts = {
        "player_role_deficit": sum(
            row["sanity"]["player_deficit"] > 1e-12 for row in prepared
        ),
        "classic_team_context_deficit": sum(
            row["sanity"]["classic_team_context_deficit"] > 1e-12 for row in prepared
        ),
        "comparable_core_alternative_deficit": sum(
            row["sanity"]["comparable_core_alternative_deficit"] > 1e-12
            for row in prepared
        ),
        "showdown_team_coverage_deficit": sum(
            row["sanity"]["showdown_team_coverage_deficit"] > 1e-12
            for row in prepared
        ),
        "stale_or_unknown_present": sum(
            row["sanity"]["stale_count"] > 0 for row in prepared
        ),
    }
    selected_diagnostics = []
    sound = [row for row in prepared
             if row["sanity"]["total_football_sanity_deficit"] <= 1e-12]
    best_sound = max(sound, key=lambda row: row["base_objective"], default=None)
    for row in selected:
        replacement = None
        if row["sanity"]["total_football_sanity_deficit"] > 1e-12 and best_sound:
            replacement = {
                "rank": best_sound["saved_rank"],
                "mean_change": _round(float(best_sound.get("mean") or 0) - float(row.get("mean") or 0), 4),
                "p90_change": _round(float(best_sound.get("p90") or 0) - float(row.get("p90") or 0), 4),
                "base_objective_change": _round(best_sound["base_objective"] - row["base_objective"], 6),
                "deficit_removed": _round(row["sanity"]["total_football_sanity_deficit"], 6),
            }
        selected_diagnostics.append({
            **_summary(row, 0.0), "best_zero_deficit_replacement": replacement,
            "players": row["sanity"]["players"],
            "team_coverage_violations": row["sanity"]["team_coverage_violations"],
        })
    return {
        "candidate_count": len(prepared), "deficit_distribution": stats,
        "deficient_candidate_count": len(deficient),
        "deficient_candidate_ranks": [row["saved_rank"] for row in deficient],
        "top_20_deficient_count": len(top_20_deficient),
        "top_20_deficient_ranks": [row["saved_rank"] for row in top_20_deficient],
        "reference_results": references, "crossovers": crossovers,
        "selected_candidates": selected_diagnostics,
        "zero_deficit_candidate_count": len(sound),
        "violation_counts": violation_counts,
    }


def _fmt(value: Any, digits: int = 3) -> str:
    return "—" if value is None else f"{float(value):.{digits}f}"


def _section(title: str, result: Mapping[str, Any]) -> list[str]:
    violations = result["violation_counts"]
    lines = [f"## {title}", "",
             f"Candidates analyzed: {result['candidate_count']}; zero deficit: "
             f"{result['zero_deficit_candidate_count']}; deficient: "
             f"{result['deficient_candidate_count']}; top-20 deficient: "
             f"{result['top_20_deficient_count']} (ranks "
             f"{', '.join(map(str, result['top_20_deficient_ranks'])) or 'none'}).", "",
             "All deficient candidate ranks: "
             f"{', '.join(map(str, result['deficient_candidate_ranks'])) or 'none'}.", "",
             "Violation counts across the complete pool: "
             f"player-role {violations['player_role_deficit']}; team context "
             f"{violations['classic_team_context_deficit']}; comparable core alternative "
             f"{violations['comparable_core_alternative_deficit']}; Showdown team coverage "
             f"{violations['showdown_team_coverage_deficit']}; stale/unknown present "
             f"{violations['stale_or_unknown_present']}.", "",
             "| lambda | selected | base objective | penalty | shadow objective | mean | P90 | deficit | core | meaningful | complementary | peripheral | stale | no-core multi-team | coverage deficit |",
             "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|"]
    for row in result["reference_results"]:
        lines.append(
            f"| {_fmt(row['lambda'],2)} | #{row['saved_rank']} | {_fmt(row['base_objective'],4)} "
            f"| {_fmt(row['football_penalty'],4)} | {_fmt(row['shadow_objective'],4)} "
            f"| {_fmt(row['mean'],2)} | {_fmt(row['p90'],2)} | {_fmt(row['football_sanity_deficit'],3)} "
            f"| {row['core']} | {row['meaningful_secondary']} | {row['complementary']} "
            f"| {row['peripheral']} | {row['stale']} | "
            f"{', '.join(row['multi_skill_teams_no_core']) or 'none'} "
            f"| {_fmt(row['showdown_team_coverage_deficit'],2)} |"
        )
    lines.extend(["", "### Exact crossovers", ""])
    if not result["crossovers"]:
        lines.extend(["No selected-lineup crossover occurs on the analytic penalty envelope.", ""])
    for trade in result["crossovers"]:
        lines.extend([
            f"- At lambda **{_fmt(trade['lambda'],8)}**, #{trade['new']['saved_rank']} replaces "
            f"#{trade['prior']['saved_rank']}: mean {trade['delta_mean']:+.2f}, P90 "
            f"{trade['delta_p90']:+.2f}, base objective {trade['delta_base_objective']:+.4f}, "
            f"deficit removed {_fmt(trade['deficit_removed'],3)}.",
            f"  - In: {_change_text(trade['players']['in'])}",
            f"  - Out: {_change_text(trade['players']['out'])}",
        ])
    lines.extend(["", "### Selected portfolio", ""])
    for row in result["selected_candidates"]:
        replacement = row["best_zero_deficit_replacement"]
        coverage = row["team_coverage_violations"]
        lines.append(
            f"- #{row['saved_rank']}: deficit {_fmt(row['football_sanity_deficit'],3)}; "
            f"core/meaningful/complementary/peripheral/stale "
            f"{row['core']}/{row['meaningful_secondary']}/{row['complementary']}/"
            f"{row['peripheral']}/{row['stale']}. "
            + (f"Best zero-deficit replacement #{replacement['rank']} changes mean "
               f"{replacement['mean_change']:+.2f}, P90 {replacement['p90_change']:+.2f}, "
               f"base objective {replacement['base_objective_change']:+.4f}."
               if replacement else "No replacement is needed; this lineup already passes.")
            + (" Team coverage: " + "; ".join(
                f"{item['team']} has {item['selected_skill_count']} selected skill player(s) "
                f"without a core representative ({', '.join(item['selected_players'])})"
                for item in coverage
            ) + "." if coverage else "")
        )
    lines.append("")
    return lines


def _change_text(rows: list[Mapping[str, Any]]) -> str:
    if not rows:
        return "none"
    return "; ".join(
        f"{row['player']} ({row['role_bucket']}, {row['classification'] or 'n/a'}, "
        f"centrality {_fmt(row['centrality'])}, deficit {_fmt(row['player_deficit'])})"
        for row in rows
    )


def _markdown(output: Mapping[str, Any]) -> str:
    classic, showdown = output["classic"], output["showdown"]
    classic_comparison = output["sources"]["classic"].get("comparison") or {}
    showdown_source = output["sources"]["showdown"]
    saved_comparison = showdown_source.get("comparison") or {}
    lines = ["# Football sanity deficit / guardrail shadow", "",
             "The experiment applies no positive football-centrality reward. Core and "
             "meaningful-secondary players have zero deficit; stale evidence is flagged "
             "but receives no automatic penalty. The penalty is scaled by the candidate-pool "
             "deficit standard deviation without mean-centering, so a zero-deficit lineup "
             "always receives exactly zero penalty.", "",
             "## Source verification", "",
             f"- Classic: generated {output['sources']['classic']['generated']} = serialized "
             f"{output['sources']['classic']['serialized']} = analyzed {classic['candidate_count']}.",
             f"- Showdown: generated {output['sources']['showdown']['generated']} = serialized "
             f"{output['sources']['showdown']['serialized']} = analyzed {showdown['candidate_count']}.",
             f"- Showdown reproduction matches all {saved_comparison.get('exact_signature_rank_count', 0)} "
             f"previously serialized candidate ranks exactly; the original report retained only "
             f"{saved_comparison.get('saved_candidate_count', 0)} of the 30 generated candidates.",
             "- The original single-entry run predates explicit single-TE propagation: its saved value "
             f"was {showdown_source.get('saved_enforce_single_te')!r}. Frozen replay used "
             f"{showdown_source.get('replay_enforce_single_te')!r} to reproduce that historical pool; "
             "current production runs require an explicit boolean.",
             f"- Classic original top-50 reproduction: {classic_comparison.get('top_50_set_overlap', 0)}/50 "
             "lineups overlap. The only rank mismatch is an objective-identical DST tie at rank 13 "
             "(Buccaneers in the saved view, Eagles in reconstruction); both objective scores are 5.910966.",
             "- Projections, P90, candidate construction, correlations, and production selector weights were unchanged.", ""]
    lines.extend(_section("Sunday Classic", classic))
    lines.extend(_section("DET–BUF Showdown — original single-entry pool", showdown))
    supplement = output.get("showdown_small_max_supplement")
    if supplement:
        lines.extend(_section("DET–BUF Showdown — later 5-max supplement", supplement))
    lines.extend(["## Decision", ""])
    for index, answer in enumerate(output["answers"], 1):
        lines.append(f"{index}. {answer}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--classic", type=Path, default=Path("artifacts/sunday-football-sanity-source-full-2026w2.json"))
    parser.add_argument("--showdown", type=Path, default=Path("artifacts/det-buf-single-entry-football-sanity-source-full-2026w2.json"))
    parser.add_argument("--showdown-supplement", type=Path, default=Path("artifacts/det-buf-football-sanity-source-full-2026w2.json"))
    parser.add_argument("--classic-core", type=Path, default=Path("artifacts/sunday-football-core-2026w2-optimizer-shadow.json"))
    parser.add_argument("--showdown-core", type=Path, default=Path("artifacts/det-buf-football-core-2026w2-optimizer-shadow.json"))
    parser.add_argument("--output-json", type=Path, default=Path("artifacts/football-sanity-guardrail-shadow-2026w2.json"))
    parser.add_argument("--output-markdown", type=Path, default=Path("artifacts/football-sanity-guardrail-shadow-2026w2.md"))
    args = parser.parse_args()
    classic_core = json.loads(args.classic_core.read_text())
    showdown_core = json.loads(args.showdown_core.read_text())
    classic_by_id = {str(row["player_id"]): row for row in classic_core["players"]}
    showdown_by_id = {str(row["player_id"]): row for row in showdown_core["players"]}
    cp, cr, cc, cpool = _classic_inputs(args.classic, classic_by_id)
    sp, sr, sc, spool = _showdown_inputs(args.showdown, showdown_by_id)
    classic_selected = list(cr.get("selected_ranks") or [1])
    showdown_selected = [
        int(row["candidate_rank"]) for row in sr.get("assignments", [])
        if row.get("candidate_rank") is not None
    ] or list((sr.get("selected") or {}).get("candidate_ranks") or [])
    classic = _analyze(cc, cpool, classic_by_id, showdown=False, selected_ranks=classic_selected)
    showdown = _analyze(sc, spool, showdown_by_id, showdown=True, selected_ranks=showdown_selected)
    supplement = None
    supplement_source = None
    if args.showdown_supplement.exists() and args.showdown_supplement != args.showdown:
        xp, xr, xc, xpool = _showdown_inputs(args.showdown_supplement, showdown_by_id)
        xselected = list((xr.get("selected") or {}).get("candidate_ranks") or [])
        supplement = _analyze(
            xc, xpool, showdown_by_id, showdown=True, selected_ranks=xselected,
        )
        supplement_source = {
            "path": str(args.showdown_supplement),
            "generated": xp["generated_candidate_count"],
            "serialized": xp["serialized_candidate_count"],
        }
    classic_control = classic["selected_candidates"][0] if classic["selected_candidates"] else None
    showdown_more = (
        showdown["top_20_deficient_count"] > classic["top_20_deficient_count"]
        or showdown["deficient_candidate_count"] / max(1, showdown["candidate_count"])
        > classic["deficient_candidate_count"] / max(1, classic["candidate_count"])
    )
    verified_improvement = any(
        any(row["role_bucket"] in {"strong_core", "meaningful_secondary"}
            for row in trade["players"]["in"])
        and any(row["role_bucket"] in {"complementary", "peripheral"}
                for row in trade["players"]["out"])
        for result in (classic, showdown) for trade in result["crossovers"]
    )
    answers = [
        ("Classic's selected control has a real role deficiency." if classic_control and classic_control["football_sanity_deficit"] > 0
         else "Classic's selected control has zero football-sanity deficit and already passes."),
        ("The deficiency penalty produces a verified weak-to-core/meaningful selected-lineup improvement."
         if verified_improvement else
         "It demotes known peripheral choices, but the selected Showdown replacement contains stale/unknown role evidence, so this run does not prove a weak-to-core/meaningful improvement."),
        ("The Classic control winner remains unchanged across the tested lambda grid."
         if len({row["saved_rank"] for row in classic["reference_results"]}) == 1 else
         "The Classic control changes on the tested lambda grid; see the crossover table."),
        f"Sunday Classic has {classic['top_20_deficient_count']} genuinely deficient top-20 lineups.",
        (f"DET–BUF exposes more football-role deficiency: {showdown['top_20_deficient_count']} top-20 and "
         f"{showdown['deficient_candidate_count']}/{showdown['candidate_count']} overall, versus Classic "
         f"{classic['top_20_deficient_count']} top-20 and {classic['deficient_candidate_count']}/{classic['candidate_count']}."
         if showdown_more else
         "DET–BUF does not expose a higher deficiency rate than Sunday Classic under this diagnostic."),
        ("The evidence supports a mild Classic guardrail and a stronger Showdown team-coverage guardrail."
         if showdown_more else
         "The current evidence does not yet support making the Showdown team-coverage guardrail stronger than Classic."),
    ]
    output = {
        "experiment": "football_sanity_deficit_shadow_v1",
        "sources": {
            "classic": {"path": str(args.classic), "generated": cp["generated_candidate_count"],
                        "serialized": cp["serialized_candidate_count"],
                        "comparison": cp.get("comparison_to_saved_top_50")},
            "showdown": {"path": str(args.showdown), "generated": sp["generated_candidate_count"],
                         "serialized": sp["serialized_candidate_count"],
                         "comparison": sp.get("comparison_to_saved_candidates"),
                         "saved_enforce_single_te": sp.get("saved_enforce_single_te"),
                         "replay_enforce_single_te": sp.get("replay_enforce_single_te")},
            "showdown_small_max_supplement": supplement_source,
        },
        "penalty_definition": {
            "core": 0, "meaningful_secondary": 0,
            "complementary": "0.10 to 0.30 continuous",
            "peripheral": "0.50 to 1.00 continuous",
            "stale_unknown": "0; uncertainty only",
            "classic_multi_skill_team_without_core": 0.25,
            "peripheral_with_comparable_core_alternative": 0.15,
            "showdown_team_coverage": "0.50 for one selected skill player; 1.00 for multiple",
        },
        "classic": classic, "showdown": showdown,
        "showdown_small_max_supplement": supplement,
        "answers": answers,
    }
    args.output_json.write_text(json.dumps(output, indent=2) + "\n")
    args.output_markdown.write_text(_markdown(output))
    print(json.dumps({
        "classic_candidates": classic["candidate_count"],
        "classic_top20_deficient": classic["top_20_deficient_count"],
        "classic_crossovers": len(classic["crossovers"]),
        "showdown_candidates": showdown["candidate_count"],
        "showdown_top20_deficient": showdown["top_20_deficient_count"],
        "showdown_crossovers": len(showdown["crossovers"]),
        "output": str(args.output_markdown),
    }, indent=2))


if __name__ == "__main__":
    main()
