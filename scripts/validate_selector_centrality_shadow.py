#!/usr/bin/env python3
"""Run a selector-only football-centrality shadow over persisted candidates.

This script reads serialized optimizer output and never generates candidates or
changes projections.  Its output is diagnostic only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from backend.app.product_services.centrality_shadow import (
    crossover_points,
    prepare_candidates,
    ranked_at_lambda,
)


REFERENCE_LAMBDAS = (0.0, 0.02, 0.05, 0.10, 0.20, 0.35, 0.50)
MATERIAL_MEAN_LOSS = 3.0
MATERIAL_P90_LOSS = 5.0
MATERIAL_BASE_LOSS = 0.10


def _round(value: Any, digits: int = 4) -> Any:
    return round(float(value), digits) if value is not None else None


def _report_from_saved_run(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    results = payload.get("results")
    if not isinstance(results, list) or not results or not isinstance(results[0], list):
        raise ValueError("Saved run does not contain the expected selected-lineup result shape")
    if not results[0] or not isinstance(results[0][0], dict):
        raise ValueError("Saved run contains no selected lineup player records")
    report = results[0][0].get("classic_small_field_report")
    if not isinstance(report, dict):
        raise ValueError("Saved run does not contain classic_small_field_report")
    return report


def _names(candidate: Mapping[str, Any]) -> str:
    return " / ".join(str(row.get("name")) for row in candidate.get("roster", []))


def _football_names(candidate: Mapping[str, Any], core_by_id: Mapping[str, Mapping[str, Any]]) -> dict:
    groups = {"high_current_core": [], "peripheral": [], "stale": []}
    for player in candidate.get("roster", []):
        if str(player.get("position") or "").upper() not in {"RB", "WR", "TE"}:
            continue
        core = core_by_id.get(str(player.get("player_id")), {})
        confidence = core.get("current_evidence_confidence")
        if confidence == "high_current" and core.get("overall_core"):
            groups["high_current_core"].append(player.get("name"))
        if core.get("football_classification") == "peripheral":
            groups["peripheral"].append(player.get("name"))
        if confidence == "stale_2025_primary":
            groups["stale"].append(player.get("name"))
    return groups


def _summary(candidate: Mapping[str, Any], weight: float) -> dict[str, Any]:
    components = candidate.get("components") or {}
    football = candidate["football"]
    return {
        "saved_rank": candidate.get("rank"),
        "candidate_id": candidate["candidate_id"],
        "lineup": _names(candidate),
        "base_objective": _round(candidate["base_objective"], 6),
        "football_centrality": _round(football["football_centrality"], 6),
        "average_overall_centrality": _round(football["average_overall_centrality"], 6),
        "football_z": _round(candidate["football_z"], 6),
        "football_contribution": _round(weight * candidate["football_z"], 6),
        "shadow_objective": _round(
            candidate["base_objective"] + weight * candidate["football_z"], 6
        ),
        "mean": _round(candidate.get("mean"), 4),
        "p90": _round(candidate.get("p90"), 4),
        "salary": candidate.get("salary"),
        "qb": (candidate.get("qb") or {}).get("name"),
        "stack": (candidate.get("stack") or {}).get("type"),
        "correlation_contribution": _round(
            float(candidate.get("correlation_positive") or 0)
            - float(candidate.get("correlation_negative") or 0), 6
        ),
        "context_contribution": _round(components.get("context") or 0, 6),
        "high_current_core_count": football["high_current_core_count"],
        "receiving_core_count": football["receiving_core_count"],
        "rushing_core_count": football["rushing_core_count"],
        "offensive_centerpiece_count": football["offensive_centerpiece_count"],
        "peripheral_count": football["peripheral_count"],
        "stale_evidence_count": football["stale_evidence_count"],
    }


def _player_detail(
    player: Mapping[str, Any],
    role_by_id: Mapping[str, Mapping[str, Any]],
    core_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    player_id = str(player.get("player_id"))
    role = role_by_id.get(player_id, {})
    core = core_by_id.get(player_id, {})
    return {
        "player": player.get("name"),
        "position": player.get("position"),
        "team": player.get("team"),
        "projection": _round(role.get("mean"), 4),
        "p90": _round(role.get("p90"), 4),
        "salary": role.get("salary", player.get("salary")),
        "overall_centrality": _round(core.get("overall_centrality"), 4),
        "receiving_centrality": _round(core.get("receiving_centrality"), 4),
        "rushing_centrality": _round(core.get("rushing_centrality"), 4),
        "classification": core.get("football_classification"),
        "confidence": core.get("current_evidence_confidence", "not_applicable"),
    }


def _trade(
    control: Mapping[str, Any],
    candidate: Mapping[str, Any],
    weight: float,
    role_by_id: Mapping[str, Mapping[str, Any]],
    core_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    control_ids = set(control["player_ids"])
    candidate_ids = set(candidate["player_ids"])
    roster = {str(row.get("player_id")): row for row in candidate.get("roster", [])}
    control_roster = {str(row.get("player_id")): row for row in control.get("roster", [])}
    return {
        "lambda_required": _round(weight, 8),
        "control": _summary(control, weight),
        "new": _summary(candidate, weight),
        "delta": {
            "mean": _round(candidate.get("mean", 0) - control.get("mean", 0), 4),
            "p90": _round(candidate.get("p90", 0) - control.get("p90", 0), 4),
            "base_objective": _round(
                candidate["base_objective"] - control["base_objective"], 6
            ),
            "football_centrality": _round(
                candidate["football"]["football_centrality"]
                - control["football"]["football_centrality"], 6
            ),
        },
        "players_in": [
            _player_detail(roster[player_id], role_by_id, core_by_id)
            for player_id in sorted(candidate_ids - control_ids)
        ],
        "players_out": [
            _player_detail(control_roster[player_id], role_by_id, core_by_id)
            for player_id in sorted(control_ids - candidate_ids)
        ],
        "control_football_players": _football_names(control, core_by_id),
        "new_football_players": _football_names(candidate, core_by_id),
    }


def _top_20_diagnostic(candidates: list[dict], weight: float) -> dict[str, Any]:
    base_ranked = ranked_at_lambda(candidates, 0.0)
    ranked = ranked_at_lambda(candidates, weight)
    base_top_ids = {row["candidate_id"] for row in base_ranked[:20]}
    current_top = ranked[:20]
    current_ids = {row["candidate_id"] for row in current_top}
    base_positions = {row["candidate_id"]: index + 1 for index, row in enumerate(base_ranked)}
    positions = {row["candidate_id"]: index + 1 for index, row in enumerate(ranked)}
    movements = [
        {
            "candidate_id": row["candidate_id"],
            "saved_rank": row.get("rank"),
            "lineup": _names(row),
            "base_rank": base_positions[row["candidate_id"]],
            "shadow_rank": positions[row["candidate_id"]],
            "movement": base_positions[row["candidate_id"]] - positions[row["candidate_id"]],
        }
        for row in ranked
    ]
    count = len(current_top) or 1
    return {
        "lambda": weight,
        "control_top_20_overlap": len(base_top_ids & current_ids),
        "average_mean": _round(sum(row["mean"] for row in current_top) / count, 4),
        "average_p90": _round(sum(row["p90"] for row in current_top) / count, 4),
        "average_football_centrality": _round(
            sum(row["football"]["football_centrality"] for row in current_top) / count, 6
        ),
        "average_high_current_core_count": _round(
            sum(row["football"]["high_current_core_count"] for row in current_top) / count, 3
        ),
        "average_peripheral_count": _round(
            sum(row["football"]["peripheral_count"] for row in current_top) / count, 3
        ),
        "largest_risers": sorted(movements, key=lambda row: (-row["movement"], row["base_rank"]))[:5],
        "largest_fallers": sorted(movements, key=lambda row: (row["movement"], row["base_rank"]))[:5],
    }


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "—"
    if isinstance(value, int):
        return str(value)
    return f"{float(value):.{digits}f}"


def _markdown(output: Mapping[str, Any]) -> str:
    lines = [
        "# Sunday Main selector-only football centrality shadow",
        "",
        "## Scope and source consistency",
        "",
        f"- Saved optimizer job: `{output['source']['job_id']}`",
        f"- Saved candidate artifact SHA-256: `{output['source']['sha256']}`",
        f"- Declared candidates: {output['source']['declared_candidate_count']}",
        f"- Exactly serialized candidates analyzed: {output['source']['serialized_candidate_count']}",
        "- Candidate generation invoked: **No**",
        "- Projection or production optimizer behavior changed: **No**",
        f"- Sutton reconciliation: {output['source_consistency']['sutton_explanation']}",
        "",
        "> Limitation: the saved report serialized only the top 50 of 120 candidates. "
        "The analysis is exact for those 50 saved lineups, but cannot prove the full-pool "
        "crossover order for the 70 lineups that were not persisted.",
        "",
        "## Standardization",
        "",
        f"Pool mean centrality: {_fmt(output['standardization']['mean'], 6)}; "
        f"population SD: {_fmt(output['standardization']['std'], 6)}. Only high-current "
        "RB/WR/TE evidence contributes; stale evidence is excluded from the average and "
        "receives no bonus or penalty.",
        "",
        "## Decision table",
        "",
        "| lambda | saved candidate | base obj | football contribution | shadow obj | mean | P90 | influence centrality | raw avg centrality | core | rec core | rush core | centerpiece | peripheral | stale |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in output["decision_table"]:
        lines.append(
            f"| {_fmt(row['lambda'], 6)} | #{row['saved_rank']} | {_fmt(row['base_objective'], 4)} "
            f"| {_fmt(row['football_contribution'], 4)} | {_fmt(row['shadow_objective'], 4)} "
            f"| {_fmt(row['mean'], 2)} | {_fmt(row['p90'], 2)} "
            f"| {_fmt(row['football_centrality'], 4)} | {_fmt(row['average_overall_centrality'], 4)} "
            f"| {row['high_current_core_count']} | {row['receiving_core_count']} "
            f"| {row['rushing_core_count']} | {row['offensive_centerpiece_count']} "
            f"| {row['peripheral_count']} | {row['stale_evidence_count']} |"
        )
    lines.extend(["", "## Exact crossover trades within the persisted pool", ""])
    for index, trade in enumerate(output["crossover_trades"], 1):
        new = trade["new"]
        delta = trade["delta"]
        lines.extend([
            f"### {index}. Candidate #{new['saved_rank']} at lambda {_fmt(trade['lambda_required'], 8)}",
            "",
            f"Control lineup: {trade['control']['lineup']}",
            "",
            f"New lineup: {new['lineup']}",
            "",
            f"Versus control: mean {delta['mean']:+.2f}, P90 {delta['p90']:+.2f}, "
            f"base objective {delta['base_objective']:+.4f}, centrality "
            f"{delta['football_centrality']:+.4f}.",
            "",
            "| side | base obj | influence centrality | raw avg | z | contribution | mean | P90 | salary | QB / stack | corr | context | core | rec | rush | centerpiece | peripheral | stale |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for label in ("control", "new"):
            row = trade[label]
            lines.append(
                f"| {label.title()} | {_fmt(row['base_objective'],4)} | {_fmt(row['football_centrality'],4)} "
                f"| {_fmt(row['average_overall_centrality'],4)} | {_fmt(row['football_z'],3)} "
                f"| {_fmt(row['football_contribution'],4)} "
                f"| {_fmt(row['mean'],2)} | {_fmt(row['p90'],2)} | {row['salary']} "
                f"| {row['qb']} / {row['stack']} | {_fmt(row['correlation_contribution'],4)} "
                f"| {_fmt(row['context_contribution'],4)} | {row['high_current_core_count']} "
                f"| {row['receiving_core_count']} | {row['rushing_core_count']} "
                f"| {row['offensive_centerpiece_count']} | {row['peripheral_count']} "
                f"| {row['stale_evidence_count']} |"
            )
        for label in ("control", "new"):
            groups = trade[f"{label}_football_players"]
            lines.extend([
                "",
                f"{label.title()} football groups: high-current core "
                f"{', '.join(groups['high_current_core']) or 'none'}; peripheral "
                f"{', '.join(groups['peripheral']) or 'none'}; stale "
                f"{', '.join(groups['stale']) or 'none'}.",
            ])
        lines.extend(["", "**Players in**", "", _player_table(trade["players_in"]), "", "**Players out**", "", _player_table(trade["players_out"]), ""])
    lines.extend(["## Top-20 movement", ""])
    for row in output["top_20_movement"]:
        risers = ", ".join(f"#{item['saved_rank']} ({item['movement']:+d})" for item in row["largest_risers"])
        fallers = ", ".join(f"#{item['saved_rank']} ({item['movement']:+d})" for item in row["largest_fallers"])
        lines.extend([
            f"### lambda {_fmt(row['lambda'], 2)}",
            "",
            f"Overlap {row['control_top_20_overlap']}/20; average mean {_fmt(row['average_mean'],2)}; "
            f"P90 {_fmt(row['average_p90'],2)}; centrality {_fmt(row['average_football_centrality'],4)}; "
            f"high-current core count {_fmt(row['average_high_current_core_count'],2)}; "
            f"peripheral count {_fmt(row['average_peripheral_count'],2)}.",
            "",
            f"Largest risers: {risers}. Largest fallers: {fallers}.",
            "",
        ])
    lines.extend(["## Answers", ""])
    for index, answer in enumerate(output["answers"], 1):
        lines.append(f"{index}. {answer}")
    return "\n".join(lines) + "\n"


def _player_table(players: list[Mapping[str, Any]]) -> str:
    if not players:
        return "No player changes."
    lines = [
        "| player | pos | mean | P90 | salary | overall | receiving | rushing | classification | confidence |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in players:
        lines.append(
            f"| {row['player']} | {row['position']} | {_fmt(row['projection'],2)} | {_fmt(row['p90'],2)} "
            f"| {row['salary']} | {_fmt(row['overall_centrality'],3)} | {_fmt(row['receiving_centrality'],3)} "
            f"| {_fmt(row['rushing_centrality'],3)} | {row['classification'] or 'not applicable'} "
            f"| {row['confidence']} |"
        )
    return "\n".join(lines)


def build_report(saved_path: Path, core_path: Path, core_report_path: Path) -> dict[str, Any]:
    saved_bytes = saved_path.read_bytes()
    saved = json.loads(saved_bytes)
    report = _report_from_saved_run(saved)
    core_payload = json.loads(core_path.read_text())
    core_report = json.loads(core_report_path.read_text())
    if core_payload.get("contract") != "football_core_shadow_v1":
        raise ValueError("Core artifact is not the canonical football_core_shadow_v1 contract")
    if core_payload.get("projection_changed") or core_payload.get("optimizer_changed"):
        raise ValueError("Core artifact indicates production projection or optimizer changes")
    core_by_id = {str(row["player_id"]): row for row in core_payload["players"]}
    role_by_id = {str(row["player_id"]): row for row in report.get("role_exposure", [])}
    serialized = report.get("top_50") or []
    if not serialized:
        raise ValueError("Saved report does not serialize any candidates")
    candidates, standardization = prepare_candidates(serialized, core_by_id)
    control = ranked_at_lambda(candidates, 0.0)[0]
    envelope = crossover_points(candidates, maximum_lambda=100.0)
    changes = [row for row in envelope if row["candidate_id"] != control["candidate_id"]]
    trades = [
        _trade(control, row["candidate"], row["lambda"], role_by_id, core_by_id)
        for row in changes
    ]
    decision_weights = sorted(set(REFERENCE_LAMBDAS) | {row["lambda"] for row in changes})
    decision_table = []
    for weight in decision_weights:
        selected = ranked_at_lambda(candidates, weight + (1e-9 if weight else 0))[0]
        row = _summary(selected, weight)
        row["lambda"] = _round(weight, 8)
        decision_table.append(row)

    sutton = next(
        (row for row in core_payload["players"] if row.get("player") == "Courtland Sutton"), None
    )
    sanity = (core_report.get("sanity_checks") or {}).get("DEN") or []
    sanity_sutton = next((row for row in sanity if row.get("player") == "Courtland Sutton"), None)
    consistent = bool(
        sutton and sanity_sutton
        and abs(float(sutton["receiving_centrality"]) - float(sanity_sutton["receiving_centrality"])) < 1e-9
        and abs(float(sutton["overall_centrality"]) - float(sanity_sutton["overall_centrality"])) < 1e-9
    )
    consistency = {
        "consistent": consistent,
        "canonical_shadow": sutton,
        "sanity_section": sanity_sutton,
        "sutton_explanation": (
            "Both sections now use the canonical saved pregame Sunday snapshot; Sutton is "
            f"receiving {_fmt(sutton.get('receiving_centrality'),3)} / overall "
            f"{_fmt(sutton.get('overall_centrality'),3)}. The prior lower values came from "
            "a Week-1-only snapshot used by the explicit sanity helper."
            if consistent else "Sutton remains inconsistent; abort tuning and inspect the core report sources."
        ),
    }
    if not consistent:
        raise ValueError(consistency["sutton_explanation"])

    first = trades[0] if trades else None
    too_influential = next(
        (
            trade for trade in trades
            if -trade["delta"]["mean"] >= MATERIAL_MEAN_LOSS
            or -trade["delta"]["p90"] >= MATERIAL_P90_LOSS
            or -trade["delta"]["base_objective"] >= MATERIAL_BASE_LOSS
        ),
        None,
    )
    if first:
        sensible = (
            first["delta"]["football_centrality"] > 0
            and first["delta"]["base_objective"] <= 0
            and -first["delta"]["base_objective"] < MATERIAL_BASE_LOSS
            and -first["delta"]["mean"] < MATERIAL_MEAN_LOSS
            and -first["delta"]["p90"] < MATERIAL_P90_LOSS
        )
        answers = [
            f"Within the 50 persisted candidates, the control first changes at lambda {first['lambda_required']:.8f} to saved candidate #{first['new']['saved_rank']}.",
            f"At that first change, mean changes {first['delta']['mean']:+.2f}, P90 {first['delta']['p90']:+.2f}, and base selector objective {first['delta']['base_objective']:+.4f}.",
            f"Lineup football centrality improves {first['delta']['football_centrality']:+.4f}; the new lineup has {first['new']['high_current_core_count']} high-current overall-core and {first['new']['peripheral_count']} peripheral skill players.",
            "The first change looks like a sensible selector tie-break within the stated diagnostic thresholds." if sensible else "The first change exceeds at least one diagnostic tie-break threshold, so it is more than a small tie-break.",
            (
                f"The term first becomes clearly too influential by the transparent diagnostic thresholds "
                f"(mean loss >= {MATERIAL_MEAN_LOSS}, P90 loss >= {MATERIAL_P90_LOSS}, or base-objective loss >= {MATERIAL_BASE_LOSS}) "
                f"at lambda {too_influential['lambda_required']:.8f}, selecting candidate #{too_influential['new']['saved_rank']}."
                if too_influential else
                "No persisted-pool crossover reaches the defined material-sacrifice thresholds over the analytic envelope."
            ),
            "The 50 persisted candidates are sufficient for provisional selector-only testing, but the saved artifact is not rich enough to answer this for the complete 120-candidate pool because 70 candidates were not serialized. Persisting all candidates is the next prerequisite; candidate generation should remain unchanged for this experiment.",
        ]
    else:
        answers = [
            "No crossover occurs within the 50 persisted candidates.",
            "No mathematical quality is sacrificed because the control remains selected.",
            "No selected-lineup football-awareness gain occurs.",
            "There is no first change to judge as a tie-break.",
            "No excessive-influence crossover appears on the persisted-pool envelope.",
            "The saved artifact is insufficient for a full-pool conclusion because 70 of 120 candidates were not serialized.",
        ]
    return {
        "experiment": "selector_only_football_centrality_shadow_v1",
        "source": {
            "path": str(saved_path),
            "sha256": hashlib.sha256(saved_bytes).hexdigest(),
            "job_id": saved.get("job_id"),
            "projection_run_id": saved.get("projection_run_id"),
            "declared_candidate_count": report.get("candidate_count"),
            "serialized_candidate_count": len(serialized),
            "candidate_ids_sha256": hashlib.sha256(
                "\n".join(row["candidate_id"] for row in candidates).encode()
            ).hexdigest(),
            "candidate_generation_invoked": False,
        },
        "core_source": {
            "path": str(core_path),
            "contract": core_payload.get("contract"),
            "projection_run_id": core_payload.get("projection_run_id"),
            "centrality_formulation": core_payload.get("centrality_formulation"),
        },
        "source_consistency": consistency,
        "signal": {
            "positions": ["RB", "WR", "TE"],
            "primary": "continuous overall_centrality",
            "positive_evidence": "high_current only",
            "stale_treatment": "excluded from numerator and denominator; no bonus or penalty",
            "diagnostic_only": [
                "receiving_core", "rushing_core", "dual_threat_core", "football_classification"
            ],
        },
        "standardization": standardization,
        "reference_results": [
            {"lambda": weight, **_summary(ranked_at_lambda(candidates, weight)[0], weight)}
            for weight in REFERENCE_LAMBDAS
        ],
        "crossover_trades": trades,
        "decision_table": decision_table,
        "top_20_movement": [_top_20_diagnostic(candidates, weight) for weight in REFERENCE_LAMBDAS],
        "diagnostic_materiality_thresholds": {
            "mean_loss": MATERIAL_MEAN_LOSS,
            "p90_loss": MATERIAL_P90_LOSS,
            "base_objective_loss": MATERIAL_BASE_LOSS,
        },
        "answers": answers,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--saved-run", type=Path, default=Path("artifacts/sunday-role-diagnostic-2026w2.json"))
    parser.add_argument("--core", type=Path, default=Path("artifacts/sunday-football-core-2026w2-optimizer-shadow.json"))
    parser.add_argument("--core-report", type=Path, default=Path("artifacts/sunday-football-core-2026w2.json"))
    parser.add_argument("--output-json", type=Path, default=Path("artifacts/sunday-selector-centrality-shadow-2026w2.json"))
    parser.add_argument("--output-markdown", type=Path, default=Path("artifacts/sunday-selector-centrality-shadow-2026w2.md"))
    args = parser.parse_args()
    result = build_report(args.saved_run, args.core, args.core_report)
    args.output_json.write_text(json.dumps(result, indent=2) + "\n")
    args.output_markdown.write_text(_markdown(result))
    print(json.dumps({
        "json": str(args.output_json),
        "markdown": str(args.output_markdown),
        "serialized_candidates": result["source"]["serialized_candidate_count"],
        "crossovers": len(result["crossover_trades"]),
        "sutton_consistent": result["source_consistency"]["consistent"],
    }, indent=2))


if __name__ == "__main__":
    main()
