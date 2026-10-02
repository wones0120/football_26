#!/usr/bin/env python3
"""Freeze a pre-lock, read-only Classic thesis analysis for a saved optimizer run."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path

from sqlalchemy import create_engine, text

from Database.config import get_connection_string
from backend.app.product_services.classic_prospective import digest_payload
from backend.app.product_services.classic_thesis_shadow import (
    CONTRACT, analyze_saved_candidates, diagnose_zero_candidate_players,
)


def _fmt(value: float | None, places: int = 2) -> str:
    return "—" if value is None else f"{value:.{places}f}"


def render_report(shadow: dict) -> str:
    source = shadow["source"]
    families = shadow["families"]
    portfolios = shadow["shadow_portfolios"]
    production = shadow["production_five"]
    by_rank = {row["rank"]: row for row in shadow["candidate_universe"]}
    by_id = {family["thesis_id"]: family for family in families}
    lines = ["# Week 4 dynamic thesis portfolio shadow", "",
             f"Source optimizer run: `{source['optimizer_run_id']}`. Decision cutoff: {source['decision_cutoff_at']}. "
             f"First saved slate kickoff: {source['first_kickoff_at']}.", "",
             f"Frozen shadow SHA-256: `{shadow['sha256']}`. Candidate universe SHA-256: "
             f"`{source['candidate_universe_sha256']}`.", "",
             "Timestamp note: the optimizer table's `created_at` was read back with a local offset "
             "that differs from the frozen solver metadata. The solver snapshot's UTC decision cutoff above "
             "and the thesis table's database `decision_cutoff_at` are the authoritative pre-lock times; "
             "the redundant `run_created_at` display in the JSON should not be used for chronology.", "",
             "## Definition and evidence", "",
             "A broad directional thesis is one canonical game, one canonical QB, one QB pass-catcher count "
             "(QB+1/2/3), and whether the lineup has an opposing bring-back. Different bring-back players, "
             "bring-back counts, and one-off players remain variants within that thesis. Every candidate retains "
             "its exact bring-back identities and roles. The canonical game key sorts the two canonical teams; "
             "display order comes from the saved DraftKings away@home game string. Thus Lawrence and Burrow "
             "are separate directional theses in the same JAX@CIN game.", "",
             "Market archetypes appear only when the saved candidate marks market context safe and its frozen QB "
             "row has a source. No unsupported directional game script is inferred. No postgame data is loaded.", "",
             "## Discovered families and quality frontier", "",
             "Best 1/3/5 mean and P90 are averages of the top selector-ranked variants in each family. "
             "P90 is a sum of player quantiles, not lineup P90. Depth near the global frontier counts "
             "candidates no more than the stated selector-point tolerance below the global best. "
             "A negative mean/P90 'drop' means the later selector-ranked variant projects higher on that "
             "separate axis. The cheap-risk count is a pregame evidence-gap proxy: a skill player at or below "
             "$4,500 with uncertain role or no saved expected routes, targets, or carries. It is not a "
             "validated failure probability.", "",
             "| Thesis | Game | Stack / bring-back | N | Best rank | Peak selector | Peak mean | Peak P90 | "
             "Within .05/.10/.15/.20 | Top 5/10/20% | Best 1/3/5 mean | Best 1/3/5 P90 | "
             "Ranks 2/3/5 | Drop to 3/5 selector | Drop to 3/5 mean | Drop to 3/5 P90 | "
             "Q / elevated rate | Best risk gaps / cheap | Ownership | Market / correlation | Pareto |",
             "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | --- | --- |"]
    for family in families:
        d, k, risk = family["depth"], family["best_k"], family["risk"]
        depth = "/".join(str(d[f"within_{v:.2f}"]) for v in (0.05, 0.10, 0.15, 0.20))
        top = "/".join(str(d[f"top_{v}%"]) for v in (5, 10, 20))
        means = "/".join(_fmt(k[str(v)]["mean"], 1) for v in (1, 3, 5))
        p90s = "/".join(_fmt(k[str(v)]["p90"], 1) for v in (1, 3, 5))
        ranks = "/".join(str(d["ranks"][str(v)] or "—") for v in (2, 3, 5))
        drops = f"{_fmt(d['selector_drop_to_3'], 3)}/{_fmt(d['selector_drop_to_5'], 3)}"
        mean_drops = f"{_fmt(d['mean_drop_to_3'], 1)}/{_fmt(d['mean_drop_to_5'], 1)}"
        p90_drops = f"{_fmt(d['p90_drop_to_3'], 1)}/{_fmt(d['p90_drop_to_5'], 1)}"
        label = f"{family['qb']} ({family['qb_team']})"
        stack = family["stack_family"] + (" + BB" if family["bring_back_presence"] else "")
        lines.append(f"| {label} | {family['game']} | {stack} | {family['count']} | "
                     f"{family['best_rank']} | {_fmt(family['peak_selector'], 3)} | "
                     f"{_fmt(family['peak_mean'], 1)} | {_fmt(family['peak_p90'], 1)} | "
                     f"{depth} | {top} | {means} | {p90s} | {ranks} | {drops} | "
                     f"{mean_drops} | {p90_drops} | "
                     f"{risk['questionable_candidate_rate']:.0%}/{risk['elevated_candidate_rate']:.0%} | "
                     f"{risk['best_availability_evidence_gaps']}/{risk['best_fragile_cheap_dependencies']} | "
                     f"{risk['ownership_complete_rate']:.0%} | "
                     f"{family['market_archetype'] or 'unavailable'} / "
                     f"{_fmt(family['structure']['best_correlation_component'], 3)} | "
                     f"{family['pareto_status']} |")
    lines += ["", "### Pareto interpretation", "",
              "A thesis is dominated only if another is at least as good on peak selector, peak mean, peak P90, "
              "depth within 0.10, best-lineup elevated dependencies and evidence gaps, and ownership completeness, "
              "with at least one strict improvement. This deliberately conservative rule does not reduce quality to "
              "one new weighted score.", ""]
    for family in families:
        if family["dominated_by"]:
            winner = [f"{by_id[item]['qb']} {by_id[item]['stack_family']}"
                      for item in family["dominated_by"][:3]]
            winner_family = by_id[family["dominated_by"][0]]
            lines.append(f"- {family['qb']} {family['stack_family']} "
                         f"{'with' if family['bring_back_presence'] else 'without'} bring-back is dominated by "
                         f"{', '.join(winner)} under the listed axes. The first dominator's peak selector/mean/P90 "
                         f"is {_fmt(winner_family['peak_selector'], 3)}/{_fmt(winner_family['peak_mean'], 1)}/"
                         f"{_fmt(winner_family['peak_p90'], 1)} versus "
                         f"{_fmt(family['peak_selector'], 3)}/{_fmt(family['peak_mean'], 1)}/"
                         f"{_fmt(family['peak_p90'], 1)} here; its within-0.10 depth is "
                         f"{winner_family['depth']['within_0.10']} versus {family['depth']['within_0.10']}.")
        else:
            lines.append(f"- {family['qb']} {family['stack_family']} "
                         f"{'with' if family['bring_back_presence'] else 'without'} bring-back survives: "
                         f"{'; '.join(family['frontier_reasons'])}.")
    lines += ["", "## Viability by predeclared selector tolerance", "",
              "| Selector gap | Qualifying theses | Non-dominated qualifiers | Canonical games among qualifiers |",
              "| ---: | ---: | ---: | ---: |"]
    for tolerance, result in shadow["viability"].items():
        games = {by_id[item]["game_key"] for item in result["qualified_theses"]}
        lines.append(f"| {tolerance} | {result['qualified_count']} | {result['frontier_count']} | {len(games)} |")
    lines += ["", "## Shadow portfolios and allocation", "",
              "For each size, the joint integer program first maximizes the number of represented non-dominated "
              "quality-qualified theses, then distinct canonical games among those theses, then the saved selector "
              "sum. It enforces saved player exposure, 60% QB exposure, at least two QB paths for multi-entry "
              "portfolios, and questionable-player limits. It tries .05, .10, "
              ".15, .20 predeclared selector tolerances in order, then all saved candidates if necessary. Pairwise "
              "overlap is capped at six; 10/20-entry shadows may relax it to seven or eight only if needed. "
              "These are shadow choices; production's user-selected overlap four and distinct-QB constraints remain "
              "untouched. No equal allocation or fixed thesis count is imposed.", "",
              "| Entries | Status | Selector tolerance | Overlap cap | Selector sum | Mean sum | P90 sum | "
              "Directional theses | Canonical games | Rank list |",
              "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for size in (1, 3, 5, 10, 20):
        p = portfolios[str(size)]
        lines.append(f"| {size} | {p['status']} | {p['quality_tolerance'] if p['quality_tolerance'] is not None else 'all saved'} | "
                     f"{p['max_overlap_constraint'] or '—'} | {_fmt(p['selector_sum'], 3)} | "
                     f"{_fmt(p['mean_sum'], 1)} | {_fmt(p['p90_sum'], 1)} | "
                     f"{len(p['thesis_allocation'])} | {len(p['canonical_game_exposure'])} | "
                     f"{', '.join(map(str, p['selected_ranks'])) or '—'} |")
        lines += ["", f"### {size}-entry allocation", ""]
        for thesis_id, n in p["thesis_allocation"].items():
            family = by_id[thesis_id]
            lines.append(f"- {family['qb']} / {family['game']} / {family['stack_family']} "
                         f"{'with' if family['bring_back_presence'] else 'without'} bring-back: {n}")
        lines.append("- Canonical games: " + (", ".join(f"{game} {n}" for game, n in
                                                 p["canonical_game_exposure"].items()) or "none"))
        o = p["overlap"]
        lines.append(f"- Within-thesis overlap: average {_fmt(o['within_average'])}, maximum "
                     f"{o['within_max'] if o['within_max'] is not None else '—'} "
                     f"({o['within_pairs']} pairs). Across-thesis: average {_fmt(o['across_average'])}, "
                     f"maximum {o['across_max'] if o['across_max'] is not None else '—'} "
                     f"({o['across_pairs']} pairs).")
    shadow_five = portfolios["5"]
    lines += ["", "## Current production five versus thesis-based shadow five", "",
              "Production used the user's max shared players = 4 and distinct QB paths = true. "
              "The thesis shadow allows repeat QBs within its documented overlap and exposure limits. "
              "This comparison measures the consequence of different portfolio construction rules; it does not "
              "show that either wins more contests.", "",
              "| Metric | Saved production | Thesis shadow | Shadow minus production |",
              "| --- | ---: | ---: | ---: |"]
    for label, key in (("Selector sum", "selector_sum"), ("Projected mean sum", "mean_sum"),
                       ("Summed player P90", "p90_sum")):
        lines.append(f"| {label} | {_fmt(production[key], 3)} | {_fmt(shadow_five[key], 3)} | "
                     f"{_fmt(shadow_five[key] - production[key], 3)} |")
    for label, key in (("Directional QBs", "directional_qb_exposure"),
                       ("Canonical games", "canonical_game_exposure"),
                       ("Stack families", "stack_family_exposure")):
        lines.append(f"| {label} | {len(production[key])} | {len(shadow_five[key])} | "
                     f"{len(shadow_five[key]) - len(production[key])} |")
    for label, key in (("Questionable lineups", "questionable_lineups"),
                       ("Elevated-questionable lineups", "elevated_lineups")):
        lines.append(f"| {label} | {production[key]} | {shadow_five[key]} | "
                     f"{shadow_five[key] - production[key]} |")
    lines += ["", f"Production ranks: {production['selected_ranks']}. Shadow ranks: "
              f"{shadow_five['selected_ranks']}.", "",
              "| Player exposure | Production | Shadow |", "| --- | ---: | ---: |"]
    player_names = {pid: roster.get("name", pid) for row in shadow["candidate_universe"]
                    for pid, roster in row["roster"].items()}
    for pid in sorted(set(production["player_exposure"]) | set(shadow_five["player_exposure"]),
                      key=lambda pid: player_names.get(pid, pid)):
        lines.append(f"| {player_names.get(pid, pid)} | {production['player_exposure'].get(pid, 0)}/5 | "
                     f"{shadow_five['player_exposure'].get(pid, 0)}/5 |")
    lines += ["", "### Five shadow representatives and joint-selection tradeoffs", ""]
    for lineup in shadow_five["lineups"]:
        row = by_rank[lineup["rank"]]
        family = by_id[row["thesis_id"]]
        best_rank = family["best_rank"]
        best_row = by_rank[best_rank]
        roster = ", ".join(row["roster"][pid]["name"] for pid in row["player_ids"])
        others = [by_rank[other["rank"]] for other in shadow_five["lineups"]
                  if other["rank"] != lineup["rank"]]
        selected_overlap = max((len(set(row["player_ids"]) & set(other["player_ids"]))
                                for other in others), default=0)
        best_overlap = max((len(set(best_row["player_ids"]) & set(other["player_ids"]))
                            for other in others), default=0)
        lines.append(f"- Rank {row['rank']}: {row['qb']} / {row['game']} / "
                     f"{row['stack_family']} + {row['bring_back_count']} bring-back(s); "
                     f"selector {_fmt(row['selector'], 3)}, mean {_fmt(row['mean'], 1)}, "
                     f"P90 {_fmt(row['p90'], 1)}. Roster: {roster}. "
                     f"Thesis peak rank {best_rank}; selector cost vs peak "
                     f"{_fmt(best_row['selector'] - row['selector'], 3)}; max overlap with other "
                     f"shadow entries {selected_overlap} versus {best_overlap} for the thesis peak.")
    lines += ["", "## High-P90 players with zero candidate exposure", "",
              "Each row uses a controlled required-player solve under frozen pregame roster/stack rules. "
              "A legal forced lineup is diagnostic only; it never enters production or the shadow candidate universe. "
              "A quality-floor classification uses the predeclared 0.20 selector gap. Salary remaining is reported "
              "as opportunity-cost evidence, not a causal attribution.", "",
              "| Player | P90 | Salary | Cause | Forced QB / stack | Selector | Equivalent rank | "
              "Mean | Lineup P90 sum | Frontier gap | Salary remaining |",
              "| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for row in shadow.get("zero_candidate_diagnostics") or []:
        forced = row.get("forced_candidate") or {}
        lines.append(f"| {row['player']} ({row['position']}) | {_fmt(row['p90'], 1)} | "
                     f"{row['salary']} | {row['cause']} | "
                     f"{forced.get('qb', '—')} / {forced.get('stack_family', '—')} | "
                     f"{_fmt(forced.get('selector'), 3)} | {forced.get('global_equivalent_rank', '—')} | "
                     f"{_fmt(forced.get('mean'), 1)} | {_fmt(forced.get('p90'), 1)} | "
                     f"{_fmt(forced.get('selector_gap'), 3)} | "
                     f"{forced.get('salary_cap_remaining', '—')} |")
    lines += ["", "## Prospective learning contract and limits", "",
              f"The frozen snapshot retains all {len(shadow['candidate_universe'])} canonical rosters, thesis membership, pregame frontier and "
              "risk metrics, viability counts, all five shadow sizes, allocations, selected representatives, "
              "game exposure, and source hashes. Future post-slate results belong in separate data and must "
              "never revise this snapshot. Reserved outcomes are actual best and mean by thesis, depth reliability, "
              "best game-environment coverage, portfolio score distributions, regret against the best scoreable "
              "candidate, and field percentile when verified contest data exists.", "",
              "The thesis definition, dominance axes, selector tolerances, and lexicographic allocation are "
              "pregame hypotheses. They have not been calibrated against outcomes. Different portfolio constraints "
              "make production/shadow deltas descriptive, not evidence of superiority.", "",
              "## Does the current candidate pool support five genuinely strong theses?", ""]
    viable = shadow["viability"]["0.20"]
    games = {by_id[item]["game_key"] for item in viable["qualified_theses"]}
    verdict = "YES" if viable["frontier_count"] >= 5 and len(games) >= 3 else "BORDERLINE" if viable["frontier_count"] >= 5 else "NO"
    lines.append(f"**{verdict}.** At the predeclared 0.20 selector tolerance, "
                 f"{viable['qualified_count']} directional stack families qualify, "
                 f"{viable['frontier_count']} survive Pareto screening, and they cover "
                 f"{len(games)} canonical games. This is pregame quality/depth evidence only.")
    lines += ["", "## If the user entered only five lineups, which shadow representatives would the thesis system select?", "",
              "The shadow selects:", ""]
    for index, lineup in enumerate(shadow_five["lineups"], 1):
        lines.append(f"{index}. Rank **{lineup['rank']}** — {lineup['qb']}, {lineup['game']}, "
                     f"{lineup['stack_family']} with {lineup['bring_back_count']} bring-back(s).")
    lines += ["", "Their full canonical-ID-backed rosters and joint-selection tradeoffs are listed above. "
              "These do **not** replace production selections.", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("optimizer_run_id")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    engine = create_engine(get_connection_string())
    with engine.connect() as connection:
        run = connection.execute(text("""
            SELECT status, strategy, created_at, constraint_config_json
            FROM target.optimizer_run WHERE optimizer_run_id = :run_id
        """), {"run_id": args.optimizer_run_id}).mappings().first()
        if not run or run["status"] != "completed" or run["strategy"] != "classic_small_field_gpp":
            raise SystemExit("A completed saved Classic small-field optimizer run is required")
        params = run["constraint_config_json"]
        report = params["strategy_runtime"]["classic_small_field"]
        frozen = report["frozen_solver_snapshot"]
        if (report.get("prospective_experiment") or {}).get("status") != "prelock_frozen":
            raise SystemExit("The source optimizer run lacks a frozen pre-lock experiment")
        try:
            stored = connection.execute(text("""
                SELECT shadow_json FROM target.classic_dynamic_thesis_shadow_v3
                WHERE optimizer_run_id = :run_id
            """), {"run_id": args.optimizer_run_id}).scalar_one_or_none()
        except Exception:
            stored = None  # Migration may not yet be applied during --dry-run.
    if stored and not args.dry_run:
        shadow = stored
        print(f"Reusing immutable thesis shadow {shadow['sha256']}")
    else:
        candidates = report["all_candidates"]
        risk_rows = report["prospective_experiment"]["availability_risk"]["players"]
        shadow = analyze_saved_candidates(
            optimizer_run_id=args.optimizer_run_id,
            run_created_at=run["created_at"].isoformat(), snapshot=frozen,
            candidates=candidates, selected_ranks=report["selected_ranks"],
            risk_rows=risk_rows, max_exposure=float(params["max_exposure"]),
            risk_policy=report["production_controls"]["policy"],
            first_kickoff_at=report["prelock_timing"]["first_saved_kickoff_at"],
        )
        body = {key: value for key, value in shadow.items() if key != "sha256"}
        body["zero_candidate_diagnostics"] = diagnose_zero_candidate_players(
            snapshot=frozen, candidates=candidates, risk_rows=risk_rows,
            candidate_caps=report["production_controls"]["candidate_caps"])
        shadow = {**body, "sha256": digest_payload(body)}
        if not args.dry_run:
            with engine.begin() as connection:
                database_time = connection.execute(text("SELECT clock_timestamp()")).scalar_one()
                if database_time < datetime.fromisoformat(shadow["source"]["decision_cutoff_at"]):
                    raise SystemExit("Refusing to freeze a thesis shadow before the saved optimizer decision")
                if database_time >= datetime.fromisoformat(shadow["source"]["first_kickoff_at"]):
                    raise SystemExit("Refusing to freeze a thesis shadow at or after the saved first kickoff")
                connection.execute(text("""
                    INSERT INTO target.classic_dynamic_thesis_shadow_v3
                        (optimizer_run_id, supersedes_shadow_sha256,
                         source_solver_sha256, candidate_universe_sha256,
                         shadow_sha256, shadow_json, decision_cutoff_at, first_kickoff_at)
                    VALUES (:run_id,
                            (SELECT shadow_sha256 FROM target.classic_dynamic_thesis_shadow_v2
                             WHERE optimizer_run_id = :run_id),
                            :solver_sha, :candidate_sha, :shadow_sha,
                            CAST(:shadow AS JSONB), :decision_at, :kickoff_at)
                    ON CONFLICT (optimizer_run_id) DO NOTHING
                """), {"run_id": args.optimizer_run_id,
                       "solver_sha": shadow["source"]["solver_snapshot_sha256"],
                       "candidate_sha": shadow["source"]["candidate_universe_sha256"],
                       "shadow_sha": shadow["sha256"],
                       "shadow": json.dumps(shadow, sort_keys=True, allow_nan=False),
                       "decision_at": shadow["source"]["decision_cutoff_at"],
                       "kickoff_at": shadow["source"]["first_kickoff_at"]})
                saved = connection.execute(text("""
                    SELECT shadow_sha256, shadow_json FROM target.classic_dynamic_thesis_shadow_v3
                    WHERE optimizer_run_id = :run_id
                """), {"run_id": args.optimizer_run_id}).mappings().one()
                if saved["shadow_sha256"] != shadow["sha256"]:
                    raise SystemExit("Another immutable shadow with different content is already saved")
                shadow = saved["shadow_json"]
    if shadow["contract"] != CONTRACT or shadow["sha256"] != digest_payload(
            {key: value for key, value in shadow.items() if key != "sha256"}):
        raise SystemExit("Frozen thesis shadow failed its content hash check")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(shadow, indent=2, sort_keys=True, allow_nan=False) + "\n")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(render_report(shadow))
    print(f"{shadow['contract']} {shadow['sha256']} "
          f"{len(shadow['candidate_universe'])} candidates "
          f"{len(shadow['families'])} theses "
          f"portfolios={[(key, value['status'], value['entries']) for key, value in shadow['shadow_portfolios'].items()]}")


if __name__ == "__main__":
    main()
