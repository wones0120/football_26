#!/usr/bin/env python3
"""Read-only, point-in-time audit of original Classic candidate pools."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import text

from backend.app.db import engine
from backend.app.product_services.optimizer_coverage import (
    evaluate_selector, portfolio_grid, pregame_coverage, selector_scores,
    validate_generation_input_snapshot,
)
from backend.app.product_services.optimizer_effectiveness import (
    actual_points_by_player, candidate_signature, chronological_validation,
    extract_saved_pool, field_benchmarks, score_signature,
)

SUNDAY_RUN = "2ef9ee7e-d2a1-4cc4-bf88-b89e5f40a2c5"
MIN_SCOREABLE_FRACTION = .90


def _r(value: float | None, places: int = 2) -> str:
    return "unavailable" if value is None else f"{value:.{places}f}"


def _load(connection):
    runs = [dict(row) for row in connection.execute(text("""
        SELECT optimizer_run_id, season, week, slate_id, contest_format, strategy,
               status, created_at AS optimizer_created_at, data_cutoff_at,
               projection_run_id, constraint_config_json
        FROM target.optimizer_run WHERE status='completed' AND contest_format='classic'
        ORDER BY season, week, slate_id, created_at
    """)).mappings()]
    contests = [dict(row) for row in connection.execute(text("""
        SELECT contest_id, season, week, slate_id, contest_format, field_size
        FROM target.dfs_contest WHERE contest_format='classic'
    """)).mappings()]
    actual_rows = [dict(row) for row in connection.execute(text("""
        SELECT c.season, c.week, c.slate_id, o.player_id, o.roster_position,
               o.actual_points, o.resolution_status, o.player_display_name
        FROM target.contest_ownership_observation o
        JOIN target.dfs_contest c USING (contest_id)
        WHERE c.contest_format='classic'
    """)).mappings()]
    score_rows = [dict(row) for row in connection.execute(text("""
        SELECT c.contest_id, e.entry_points
        FROM target.dfs_contest_entry_result e JOIN target.dfs_contest c USING (contest_id)
        WHERE c.contest_format='classic'
    """)).mappings()]
    ownership_rows = [dict(row) for row in connection.execute(text("""
        SELECT ownership_run_id, player_id, projected_ownership, created_at, data_cutoff_at
        FROM target.ownership_projection WHERE season=2026 AND week=3 AND upper(slate_id)='SUNDAY_MAIN'
    """)).mappings()]
    monday_imported = bool(connection.execute(text("""
        SELECT EXISTS(SELECT 1 FROM target.dfs_contest
                      WHERE season=2026 AND week=3 AND upper(slate_id)='MONDAY_NIGHT')
    """)).scalar())
    return runs, contests, actual_rows, score_rows, ownership_rows, monday_imported


def _benchmarks(contests, score_rows):
    by_contest = {}
    for row in score_rows:
        by_contest.setdefault(str(row["contest_id"]), []).append(row)
    return {str(row["contest_id"]): field_benchmarks(row, by_contest.get(str(row["contest_id"]), []), [])
            for row in contests}


def build_audit(runs, contests, observations, score_rows, ownership_rows, monday_imported):
    benchmark = _benchmarks(contests, score_rows)
    groups = {}
    for row in observations:
        groups.setdefault((row["season"], row["week"], row["slate_id"].upper()), []).append(row)
    contest_groups = {}
    for contest in contests:
        contest_groups.setdefault((contest["season"], contest["week"], contest["slate_id"].upper()), []).append(contest)
    excluded, evaluated = [], []
    sunday = None
    for run in runs:
        fmt = str(run["contest_format"]).lower()
        pool = extract_saved_pool(run["constraint_config_json"], fmt)
        if pool["status"] != "original_candidate_pool":
            continue
        timing = chronological_validation(run, pool)
        key = (run["season"], run["week"], run["slate_id"].upper())
        actuals = actual_points_by_player(groups.get(key, []), fmt)
        candidates = pool["candidates"]
        scoreable = sum(score_signature(candidate_signature(row, fmt), actuals)[0] is not None
                        for row in candidates)
        summary = {"run_id": str(run["optimizer_run_id"]), "season": run["season"],
                   "week": run["week"], "slate": run["slate_id"], "candidate_count": len(candidates),
                   "scoreable_count": scoreable, "timing": timing,
                   "pool_sha256": pool["sha256"],
                   "saved_manifest_present": bool(((run["constraint_config_json"].get("strategy_runtime") or {})
                                                   .get("candidate_pool_manifest") or {}).get("sha256"))}
        if timing["status"] != "predecision":
            excluded.append({**summary, "reason": timing["reason"]})
            continue
        if scoreable / len(candidates) < MIN_SCOREABLE_FRACTION:
            excluded.append({**summary, "reason": "insufficient_resolved_actuals"})
            continue
        config = run["constraint_config_json"]
        runtime = config.get("strategy_runtime") or {}
        report = runtime.get("classic_small_field") or {}
        selected_ranks = report.get("selected_ranks") or []
        lines = {str(contest["contest_id"]): {
            label: value for label, value in benchmark[str(contest["contest_id"])].get("thresholds", {}).items()
            if label in {"top_1_percent", "top_5_percent", "top_10_percent", "top_20_percent"}}
            for contest in contest_groups.get(key, [])
            if benchmark[str(contest["contest_id"])]["status"] == "available"}
        variants = {name: evaluate_selector(candidates, scores, actuals, lines)
                    for name, scores in selector_scores(candidates).items()}
        result = {**summary, "selected_ranks": selected_ranks, "variants": variants,
                  "field_thresholds": lines}
        if summary["run_id"] == SUNDAY_RUN:
            scored_candidates = [(row, score_signature(candidate_signature(row, "classic"), actuals)[0])
                                 for row in candidates]
            best_candidate_row, best_candidate_actual = max(
                ((row, score) for row, score in scored_candidates if score is not None),
                key=lambda pair: pair[1],
            )
            ownership_run_id = config.get("ownership_run_id")
            pinned_ownership = {str(row["player_id"]): float(row["projected_ownership"])
                                for row in ownership_rows if str(row["ownership_run_id"]) == ownership_run_id
                                and row["created_at"] <= run["optimizer_created_at"]
                                and row["data_cutoff_at"] <= row["created_at"]}
            sunday = {
                **result,
                "coverage": pregame_coverage(candidates, selected_ranks,
                                             runtime.get("player_pool", {}).get("rows", []), pinned_ownership),
                "discovery": report.get("candidate_discovery"),
                "generation_replay_gate": validate_generation_input_snapshot(
                    report.get("frozen_generation_inputs")),
                "generation_shadows": {label: {"status": "not_run", "reason": "complete_frozen_generation_inputs_absent",
                                               "candidate_label": "retrospective_shadow"}
                                       for label in ("G1", "G2", "G3", "G4", "G5")},
                "best_scoreable_candidate": {"rank": best_candidate_row["rank"],
                                             "actual_points": best_candidate_actual,
                                             "mean": best_candidate_row["mean"],
                                             "p90": best_candidate_row["p90"]},
                "pool_funnel": {k: v for k, v in (runtime.get("player_pool") or {}).items()
                                if k.endswith("_count")},
                "context_trigger_counts": (runtime.get("context_scoring") or {}).get("trigger_counts", {}),
                "portfolio_grid": portfolio_grid(candidates, actuals, count=len(selected_ranks),
                                                 max_exposure=float(config.get("max_exposure", 1.0)),
                                                 original_selected_ranks=selected_ranks,
                                                 thresholds=lines),
                "selected_candidates": [{"rank": row["rank"], "qb": row["qb"]["name"],
                                         "family": row["stack"]["type"],
                                         "bring_backs": row["stack"]["bring_back_count"],
                                         "score": row["objective_score"],
                                         "actual_points": score_signature(
                                             candidate_signature(row, "classic"), actuals)[0]}
                                        for row in candidates if row["rank"] in selected_ranks],
                "highest_p90_omitted": [{"rank": row["rank"], "qb": row["qb"]["name"],
                                         "p90": row["p90"], "mean": row["mean"]}
                                        for row in sorted(candidates, key=lambda row: -row["p90"])
                                        if row["rank"] not in selected_ranks][:10],
                "geno_candidates": [{"rank": row["rank"], "family": row["stack"]["type"],
                                      "mean": row["mean"], "p90": row["p90"],
                                      "objective": row["objective_score"],
                                      "sources": row.get("discovery_sources", [])}
                                     for row in candidates if row["qb"]["name"] == "Geno Smith"],
            }
        evaluated.append(result)
    return {"contract": "original_saved_pools_only", "scoreable_fraction_gate": MIN_SCOREABLE_FRACTION,
            "evaluated_classic_runs": evaluated, "excluded_saved_pool_runs": excluded,
            "sunday": sunday,
            "monday_week3_contests_imported": monday_imported}


def markdown(audit):
    rows = audit["evaluated_classic_runs"]
    sunday = audit["sunday"]
    missing_count = sunday["candidate_count"] - sunday["scoreable_count"]
    baseline = next(row for row in sunday["portfolio_grid"]
                    if row["max_overlap"] is None and not row["distinct_qb_paths"]
                    and row["max_objective_loss"] is None)
    best_generated = (sunday["variants"]["A_existing"]["selection_regret_lower_bound"]
                      + sunday["variants"]["A_existing"]["top_k"]["5"]["best_actual"])
    overlap_six = next(row for row in sunday["portfolio_grid"]
                       if row["max_overlap"] == 6 and not row["distinct_qb_paths"]
                       and row["max_objective_loss"] is None)
    distinct_qbs = next(row for row in sunday["portfolio_grid"]
                        if row["max_overlap"] is None and row["distinct_qb_paths"]
                        and row["max_objective_loss"] is None)
    top_ten_lines = [contest["top_10_percent"] for contest in sunday["field_thresholds"].values()]
    lines = ["# Week 3 frozen-pool selector and generation coverage audit", "",
             "Read-only retrospective shadow evaluation. Candidate pools were read directly from saved runs and hashed at audit time;",
             "older runs without a persisted manifest cannot be independently hash-matched to their creation state. Eligible runs required",
             "saved kickoff evidence after both run creation and data cutoff. Actuals were joined only after ranking.",
             f"Runs below {MIN_SCOREABLE_FRACTION:.0%} resolved candidate coverage were excluded. No production weights or defaults changed.",
             "", "## Executive summary", "",
             f"- Sunday shows both a scoreable generation gap and a selection gap: the best scoreable generated lineup reached {_r(best_generated)}, while the saved portfolio reached {_r(baseline['best_scoreable_actual'])}. {missing_count} of {sunday['candidate_count']} candidates remain unscored, so the generation ceiling is a lower bound.",
             "- Cross-slate evidence is unavailable: all eligible scored Classic pools are Week 3 Sunday Main research runs with highly overlapping inputs.",
             "- Geno was eligible and four QB-family constructions were legal; two were sequential and two were added by exact-family discovery. His strongest saved selector rank was 118. This is an objective/search concentration finding, not a case for forcing him.",
             "- Bring-backs existed in 105 of 212 candidates. The original portfolio objective plus 80% player exposure cap selected five no-bring-back lineups. This is selection, not absent legal generation.",
             "- No safe original-input generator replay is claimed. The saved run does not contain a complete immutable solver-input snapshot for all 535 eligible players. The G1–G5 generation shadows remain pending.",
             "", "## Eligible historical frozen Classic pools", "",
             "| Run | Slate | Scoreable / saved | A top 5 best | B top 5 best | C top 5 best | E top 5 best |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    for row in rows:
        variants = row["variants"]
        lines.append("| " + " | ".join((row["run_id"][:8], f"{row['season']} W{row['week']} {row['slate']}",
                   f"{row['scoreable_count']}/{row['candidate_count']}",
                   *(_r(variants[key]["top_k"]["5"]["best_actual"]) for key in
                     ("A_existing", "B_mean", "C_ceiling", "E_without_context_correlation")))) + " |")
    lines += ["", "These five are the only saved Classic pools with both strict timing and at least 90% resolved actuals.",
              "Four 2026 W2 Sunday Main pools pass timing but have no imported Sunday Main actuals; later W2 Sunday Late pools fail timing.",
              "These Week 3 runs are related research runs, not five independent slate observations.",
              "", "### Full cross-run variant comparison", "",
              "| Run | Selector | Top-5 best | Top-5 avg | Spearman | Regret ≥ |",
              "| --- | --- | ---: | ---: | ---: | ---: |"]
    for row in rows:
        for name, result in row["variants"].items():
            lines.append("| " + " | ".join((row["run_id"][:8], name,
                         _r(result["top_k"]["5"]["best_actual"]), _r(result["top5_average"]),
                         _r(result["spearman"], 3), _r(result["selection_regret_lower_bound"]))) + " |")
    lines += ["", "## Sunday frozen-pool selector comparison", "",
              "All top-K values are observed among scoreable original candidates. Regret is a lower bound.",
              "Selector A ranks by the saved objective; its raw top five differ from the globally selected five (ranks 1, 3, 7, 10, 58) because production applies an 80% player exposure cap.",
              "Mean/ceiling blends use within-pool min–max normalization. E subtracts only saved context and correlation components.",
              "", "| Selector | Top 1 | Top 3 | Top 5 | Top 10 | Top 20 | Top-5 avg | Spearman | Pearson | Regret ≥ |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for key, value in sunday["variants"].items():
        lines.append("| " + " | ".join([key] + [_r(value["top_k"][str(k)]["best_actual"]) for k in (1, 3, 5, 10, 20)] +
                    [_r(value["top5_average"]), _r(value["spearman"], 3), _r(value["pearson"], 3),
                     _r(value["selection_regret_lower_bound"])]) + " |")
    lines += ["", "No variant's raw top five reached the top-20% field line in any of the three imported contests. The structured JSON contains top-5 medians, actual-rank bounds, and per-contest top-20/10/5/1% attainment.",
              "The saved objective did not demonstrate a repeatable advantage over mean or ceiling on these related Week 3 pools; its full-pool Spearman was 0.027 versus 0.110 for mean and 0.257 for summed ceiling in the target run. This does not establish a better production weight.",
              f"The strongest scoreable saved candidate was pregame rank {sunday['best_scoreable_candidate']['rank']} with {_r(sunday['best_scoreable_candidate']['actual_points'])} actual points. Its saved mean/P90 were {_r(sunday['best_scoreable_candidate']['mean'])}/{_r(sunday['best_scoreable_candidate']['p90'])}.",
              "", "### Original selected portfolio", "",
              "| Saved rank | QB | Stack | Bring-backs | Actual |",
              "| ---: | --- | --- | ---: | ---: |"]
    for row in sunday["selected_candidates"]:
        lines.append("| " + " | ".join((str(row["rank"]), row["qb"], row["family"],
                     str(row["bring_backs"]), _r(row["actual_points"]))) + " |")
    lines += [
              "", "## Sunday candidate coverage", "",
              "All 25 eligible QBs have at least one saved candidate. Ranks are among those 25 eligible QBs; ownership is from the pinned pregame run.",
              "",
              "| QB | Salary | Mean / rank | P90 / rank | Own % / rank | Total / rank | Team total | Spread | Generated | Selected | Stack families |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for qb in sunday["coverage"]["qb"]:
        lines.append("| " + " | ".join((qb["name"], str(qb["salary"]),
                     f"{_r(qb['mean'])} / #{qb.get('mean_rank', '—')}",
                     f"{_r(qb['p90'])} / #{qb.get('p90_rank', '—')}",
                     f"{_r(qb['ownership'])} / #{qb.get('ownership_rank', '—')}",
                     f"{_r(qb['game_total'])} / #{qb.get('game_total_rank', '—')}", _r(qb["team_total"]),
                     _r(qb["spread"]), str(qb["candidate_count"]), str(qb["selected_count"]),
                     ", ".join(f"{k}: {v}" for k, v in qb["families"].items()))) + " |")
    lines += ["", "### Stack-family distribution", "",
              "| Family | Generated | Selected |", "| --- | ---: | ---: |"]
    for family, count in sorted(sunday["coverage"]["stack_families"].items()):
        lines.append(f"| {family} | {count} ({100*count/212:.1f}%) | {sunday['coverage']['selected_stack_families'].get(family, 0)} |")
    lines += ["", "The imported top-1% fields used Geno at QB in 87/159, 48/80, and 84/179 lineups. This is postgame context only; it was not used to define any shadow rank or family target.",
              "", "### Pregame game-environment exposure", "",
              "Counts are candidate lineups containing the listed role in each game; QB, opposing bring-back, and full-stack counts refer to the game's primary QB path.",
              "| Game | Total | Team implied totals | QB | Pass catcher | Bring-back | RB | DST | Full stack |",
              "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for game in sunday["coverage"]["games"]:
        totals = ", ".join(f"{team} {_r(value)}" for team, value in (game.get("team_totals") or {}).items())
        lines.append("| " + " | ".join((game["game"], _r(game.get("game_total")), totals,
                     *(str(game.get(field, 0)) for field in ("qb", "pass_catcher", "bring_back", "rb", "dst", "full_stack")))) + " |")
    lines += ["", "The 52.5-total BAL–DAL game had 11 primary-QB candidates and the 50.5-total BUF–LAC game had 8, while 48.5-total DET–NYJ had 66. This shows uneven exploration before portfolio selection; saved evidence does not isolate salary optimization from correlation scoring as its cause.",
              "Saved context-rule trigger counts are available only for the whole eligible player pool, not by game; the exact aggregate counts are in the JSON artifact."]
    lines += ["", "### High-ceiling players with little generated exposure", "",
              "The following descriptive screen uses saved P90 percentile ≥95 among all 535 eligible players and fewer than 5% of generated candidates; it does not use actual points.",
              "| Player | Position | Mean | P90 | Ownership | Salary | Generated | Selected | Game total |",
              "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for player in sorted((row for row in sunday["coverage"]["players"]
                          if (row["p90_percentile"] or 0) >= 95 and row["candidate_pct"] < 5),
                         key=lambda row: -(row["p90"] or 0)):
        lines.append("| " + " | ".join((str(player["name"]), str(player["position"]), _r(player["mean"]),
                     _r(player["p90"]), _r(player["ownership"]), str(player["salary"]),
                     str(player["candidate_count"]), str(player["selected_count"]),
                     _r((player["game_environment"] or {}).get("game_total")))) + " |")
    lines += ["", "A separate low-owned screen (ownership <5%, P90 percentile ≥85, at most four generated candidates) includes Brock Bowers (P90 24.70, ownership 4.2%, zero candidates) and Rashee Rice (P90 23.70, ownership 3.3%, zero candidates). Their eligibility and individual ceilings are saved; the absence of a forced legal solve prevents assigning salary, roster, or policy causality."]
    d = sunday["coverage"]["diversity"]
    lines += ["", "## Candidate similarity and funnel", "",
              f"- Distinct rosters: {d['unique_roster_count']}/{d['candidate_count']}; average pairwise overlap: {_r(d['average_pairwise_overlap'])} of 9.",
              f"- Distinct QB paths: {d['qb_count']}; effective QB/game/stack families: {_r(d['effective_family_count'])} across {d['construction_family_count']} observed families.",
              *[f"- Candidate pairs sharing at least {k} players: {_r(100*v)}%." for k, v in d["shared_at_least"].items()],
              f"- Source pool {sunday['pool_funnel'].get('source_pool_count')}; optimizer eligible {sunday['pool_funnel'].get('optimizer_eligible_count')}; sequential {sunday['discovery']['sequential_count']}; expanded/saved {sunday['discovery']['unique_count']}; selected {len(sunday['selected_ranks'])}.",
              "- Sequential generation produced two Geno paths; exact QB-family discovery added two. All four legal paths were retained in the 212 saved candidates, ranked 118, 124, 133, and 139. No later pruning removed them.",
              "- Geno's saved QB mean 17.62 and P90 28.34 ranked 10th of 25; salary $4,900, ownership 1.44%, game total 48.5, implied team total 21.0, spread +6.5. One Geno lineup had mean 138.06 and summed P90 240.69 versus selected rank 1's 135.96 and 239.19, yet its full objective was 5.3109 versus 5.4383. QB-stack, context and correlation contributions account for the rank gap in this comparison; ownership's soft objective contribution was zero.",
              "- The first bring-back candidate was objective rank 2. It shared Amon-Ra St. Brown, Jalen Coker, Derrick Henry, and Denzel Boston with four of five selected lineups, so it could not simply be added without changing another lineup under the 80% exposure cap. The exact global selector reproduced ranks 1, 3, 7, 10, 58.",
              "- Theoretical legal roster count, intermediate solver alternatives, and rejected quality-floor paths were not persisted. The existing architecture does not enumerate those stages.",
              "", "## Portfolio diversification shadow", "",
              "The JSON records all 40 predeclared overlap × distinct-QB × objective-loss configurations, including infeasible cases, exposures, overlap matrices, mean/P90 sacrifice, and actual capture.",
              "Every F configuration keeps the saved candidate scores, so full-pool Pearson/Spearman and raw top-10/top-20 capture equal Selector A; the portfolio rows report selected top-1/3/5 capture separately.",
              "| Overlap | Distinct QB | Loss | Status | Ranks | Best scoreable | Avg scoreable | Regret ≥ | Top-20% fields | Mean sacrifice | Ceiling sacrifice |",
              "| ---: | --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for row in sunday["portfolio_grid"]:
        lines.append("| " + " | ".join((str(row["max_overlap"] or "off"), str(row["distinct_qb_paths"]),
                     str(row["max_objective_loss"] if row["max_objective_loss"] is not None else "unrestricted"),
                     row["status"], ",".join(map(str, row["ranks"])), _r(row["best_scoreable_actual"]),
                     _r(row["average_scoreable_actual"]), _r(row["selection_regret_lower_bound"]),
                     str(sum(values.get("top_20_percent", False) for values in row["field_attainment_top5"].values())),
                     _r(row["mean_sacrifice"]), _r(row["ceiling_sacrifice"]))) + " |")
    lines += ["", "## Interpretation and remaining uncertainty", "",
              f"The scoreable generation pool is the binding top-10% limitation: its best {_r(best_generated)} was below each imported contest's top-10% line ({_r(min(top_ten_lines))}–{_r(max(top_ten_lines))}). Selection also lost at least {_r(best_generated - baseline['best_scoreable_actual'])} points relative to that scoreable pool best. The {missing_count} unscored candidates prevent a definitive full-pool generation conclusion.",
              f"Overlap ≤6 in shadow portfolio selection increased the best scoreable selected actual from {_r(baseline['best_scoreable_actual'])} to {_r(overlap_six['best_scoreable_actual'])} while distinct-QB selection reduced it to {_r(distinct_qbs['best_scoreable_actual'])}. This one-slate, incomplete-actual result does not support a default change.",
              "All 212 rosters were distinct, but 208 contained Derrick Henry and 186 contained Jalen Coker. The 105 observed QB/game/stack families have an effective count of 27.24, indicating substantial core concentration despite broad QB labels.",
              "Geno's four paths are best classified as search concentration plus objective-policy ranking, with competitive whole-lineup mean/P90 in one saved path. The causal effect of a larger Geno search remains unmeasured. Bring-back absence in the final five is portfolio-selection-limited, not a missing legal family. Other high-P90 player omissions without a forced legal solve remain insufficient evidence for a causal label.",
              "", "## Actual resolution and Monday", "",
              f"Caleb Douglas, Bub Means, Mason Taylor, and Sincere McCormick have no Week 3 canonical DK actual in the imported Sunday observations or Week 3 canonical fact actuals. Earlier-week observations cannot establish their Week 3 scores. {missing_count} affected candidates remain unscored.",
              ("Week 3 Monday Night standings are imported; run the Showdown effectiveness workflow."
               if audit["monday_week3_contests_imported"] else
               "Week 3 Monday Night standings are not imported; Monday effectiveness remains pending. The existing Learning UI refreshes a weekly report after a successful standings import when a DraftKings username is supplied."),
              "", "## Shadow generation experiments", "",
              "G1–G5 were not run. The original save includes eligible IDs, projection/P90, context summaries and candidate rosters, but not a complete immutable per-player solver-input snapshot with ownership, market and constraint state. Rebuilding from current tables could silently mix later inputs. The new run report records a more explicit generation funnel; a frozen replay contract is still needed before safe generation shadows.",
              "", "## Evidence-based next experiment", "",
              "Prospectively persist a complete pre-lock solver input snapshot and run one predeclared structural-coverage shadow against the same next Classic slate. Keep the production selector and generator defaults fixed; compare original and shadow candidate families before scoring, then score both after actuals resolve.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, default=Path("artifacts/week3-selector-generation-audit.json"))
    parser.add_argument("--markdown", type=Path, default=Path("docs/WEEK3_SELECTOR_AND_GENERATION_COVERAGE_AUDIT.md"))
    args = parser.parse_args()
    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        audit = build_audit(*_load(connection))
    args.json.write_text(json.dumps(audit, indent=2, default=str, allow_nan=False) + "\n")
    args.markdown.write_text(markdown(audit))
    print(json.dumps({"evaluated_runs": len(audit["evaluated_classic_runs"]),
                      "excluded_pools": len(audit["excluded_saved_pool_runs"]),
                      "sunday_candidates": audit["sunday"]["candidate_count"]}))


if __name__ == "__main__":
    main()
