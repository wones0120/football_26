#!/usr/bin/env python3
"""Render preserved Week 3 prelock and Week 2 historical audit JSON to Markdown."""
from __future__ import annotations

import json
from pathlib import Path


SUNDAY = Path("artifacts/sunday-main-quality-governed-portfolio-2026w3.json")
HISTORY = Path("artifacts/historical-classic-quality-guard-eligibility-2026w1-w2.json")
OUTPUT = Path("artifacts/sunday-main-quality-governed-portfolio-2026w3.md")


def f(value, digits=2):
    return "—" if value is None else f"{value:.{digits}f}"


def main() -> None:
    data = json.loads(SUNDAY.read_text())
    history = json.loads(HISTORY.read_text())
    rows = {row["rank"]: row for row in data["candidates"]}
    shadows = ("production", "context50", "correlation50", "both50", "both0")
    lines = [
        "# Sunday Main quality-governed portfolio audit",
        "",
        f"Frozen optimizer run: `{data['source_optimizer_run_id']}`; cutoff: {data['source_data_cutoff_at']}.",
        "Week 3 game outcomes were not used. Football projections, base scoring weights, and production settings were not retuned.",
        "",
        "## Candidate discovery and ownership",
        "",
        "The promoted candidate stage deduplicates by canonical player IDs and injects global highest mean, global highest P90, global selector, every QB family, and four exact stack constructions per QB before final selection. The frozen replay produced 212 unique lineups from 120 sequential candidates and 128 legal injections. Both global raw-quality lineups were absent from the sequential 120.",
        "",
        f"The additional joint-quality and guard solves produced {data['candidate_count']} unique diagnostic lineups. Every lineup uses the frozen football weights `{data['base_football_weights']}`. No ownership value was imputed for a missing player.",
        "",
        f"Old slate-wide behavior hid ownership for all candidates because coverage was 522/535. Corrected candidate-level evaluation has {data['ownership_old_vs_corrected']['corrected_complete_candidates']} complete lineups and {data['ownership_old_vs_corrected']['corrected_incomplete_candidates']} incomplete lineups in this diagnostic universe. The top 20 scoring ranks did not change: the frozen profile has no soft ownership term, no optimal-lineup probabilities, and no active ownership cap. Complete lineups now show ownership and relative chalk; incomplete lineups show those terms as unavailable.",
        "",
        "## Exact quality guard frontier",
        "",
        f"Global legal maxima: mean **{f(data['global_mean'])}**, summed P90 **{f(data['global_p90'])}**. Guards are exact legal solves; each uses the unchanged production selector within its stated floor.",
        "",
        "| Guard | Winner | Mean | P90 | Selector | Mean loss | P90 loss |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for label, rank in data["quality_guards"].items():
        row = rows[rank] if rank else None
        lines.append(f"| {label} | {row['qb']['name'] if row else 'infeasible'} (#{rank}) | "
                     f"{f(row['mean']) if row else '—'} | {f(row['p90']) if row else '—'} | "
                     f"{f(row['objective_score'],4) if row else '—'} | "
                     f"{f(row['mean_loss_vs_global']) if row else '—'} | "
                     f"{f(row['p90_loss_vs_global']) if row else '—'} |")
    lines += [
        "",
        "The selected lineup changes at a 7-point mean allowance and at P90 allowances of 3 and 7. The 3–6 mean guards and 5-point P90 guard select Tyler Shough; a 7-point allowance selects Jared Goff. These are diagnostics, not a permanent threshold choice.",
        "",
        "Each candidate JSON row records both global raw-quality losses, the raw weighted objective sacrifice, context/correlation gain relative to the best raw weighted quality lineup, and their ratio when the gain is positive.",
        "",
        "## Historical prelock validation",
        "",
        "Week 2 Sunday Main has one eligible prelock small-field snapshot. Its 310 eligible player projections and market features replayed the saved 120 selector scores exactly. Historical actual DK scores already existed in `public.player_game_feature_matrix` for all 310 canonical player IDs; no new score ingest was required for this validation. The target fact table has not yet been populated for that week.",
        "",
        "| Week 2 construction | Mean | P90 | Actual DK score | Effect vs production |",
        "|---|---:|---:|---:|---|",
    ]
    wk2 = history["week_2"]
    for name, row in (("Production selected", wk2["production_selected"]),
                      ("Global highest mean", wk2["global_highest_mean_legal"])):
        lines.append(f"| {name} | {f(row['mean'])} | {f(row['p90'])} | {f(row['actual_score'])} | — |")
    for gap, row in wk2["mean_guard_frontier"].items():
        lines.append(f"| Mean within {gap} | {f(row['mean'])} | {f(row['p90'])} | "
                     f"{f(row['actual_score'])} | {row['guard_effect']} "
                     f"({f(row['actual_delta_vs_production'])}) |")
    lines += [
        "",
        "The 3-point guard hurt by 9.30 actual points; 4–7 selected the production lineup. Week 1 has resolved actuals but no saved small-field candidate snapshot. Week 2 Sunday Late candidate runs were all created after its 4:05 p.m. first kickoff, so they are excluded from prelock validation. One eligible slate cannot establish a permanent guard. No Week 2 Sunday Main in-game disruption event is recorded in the outcome-event table; untagged score differences are not adjudicated as normal variance. Recorded events for other slates remain separate in the JSON audit.",
        "",
        "## Every viable QB: joint mean and P90 screen",
        "",
        "A QB qualifies only when one legal lineup is within the stated number of points of **both** global maxima. The closest-gap column is an exact binary-search upper bound on the minimum of the larger mean/P90 loss (about 0.01-point precision), not merely the best old candidate.",
        "",
        "| QB | 5-point result | Best selector rank | Closest joint gap if excluded | First relaxation that qualifies |",
        "|---|---|---:|---:|---|",
    ]
    qualifying = []
    for family in data["qb_families"]:
        ranks = family["joint_guard_best_rank"]
        rank5 = ranks["5"]
        if rank5:
            qualifying.append((family, rows[rank5]))
        first = "5" if rank5 else "6" if ranks["6"] else "7" if ranks["7"] else "none through 7"
        lines.append(f"| {family['qb']} | {'qualifies' if rank5 else 'excluded'} | "
                     f"{rank5 or '—'} | {f(family['closest_minimax_gap']) if not rank5 else '—'} | {first} |")
    lines += ["", "### Closest legal construction for each excluded QB", "",
              "| QB | Rank and roster | Salary | Mean | P90 | Mean loss | P90 loss | Joint gap |",
              "|---|---|---:|---:|---:|---:|---:|---:|"]
    for family in data["qb_families"]:
        rank = family["closest_exact_attempt_rank"]
        if rank is None:
            continue
        row = rows[rank]
        roster = ", ".join(player["name"] for player in row["roster"])
        lines.append(f"| {family['qb']} | #{rank}: {roster} | ${row['salary']:,} | "
                     f"{f(row['mean'])} | {f(row['p90'])} | "
                     f"{f(row['mean_loss_vs_global'])} | {f(row['p90_loss_vs_global'])} | "
                     f"{f(family['closest_minimax_gap'])} |")
    lines += ["", "### Seven QB families within 5 points of both maxima", "",
              "Shadow rank order below: production / context50 / correlation50 / both50 / both0.", "",
              "| QB and roster | Salary | Mean | P90 | Mean loss | P90 loss | Selector | Ownership / chalk percentile | Stack; primary game | Shadow ranks |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---|---|" ]
    for family, row in qualifying:
        owner = row["ownership"]
        ownership = (f"{f(owner['ownership_sum'])} / {f(owner['relative_chalk'],0)}%"
                     if owner["status"] == "available" else "unavailable")
        roster = ", ".join(player["name"] for player in row["roster"])
        ranks = "/".join(str(row["shadow_ranks"][key]) for key in shadows)
        lines.append(f"| **{family['qb']}**: {roster} | ${row['salary']:,} | {f(row['mean'])} | "
                     f"{f(row['p90'])} | {f(row['mean_loss_vs_global'])} | "
                     f"{f(row['p90_loss_vs_global'])} | {f(row['objective_score'],4)} | "
                     f"{ownership} | {row['stack']['type']}; {row['primary_game']} | {ranks} |")
    lines += [
        "",
        "At 6 points, no new QB family enters. At 7, Patrick Mahomes, Kirk Cousins, and Kyler Murray become feasible. Five high-quality distinct QB paths already exist at 5 points, so the portfolio does not need that relaxation.",
        "",
        "## Distinct portfolio frontier: one lineup per QB, overlap at most 6/9",
        "",
    ]
    strong = rows[data["portfolios"]["5"]["3"]["ranks"][0]]
    for count in (3, 4, 5):
        ranks = data["portfolios"]["5"][str(count)]["ranks"]
        chosen = [rows[rank] for rank in ranks]
        lines += [f"### Best {count}-entry portfolio", "",
                  "| Rank | QB and game thesis | Roster | Salary | Mean | P90 | Selector | Mean/P90 cost vs strongest | Ownership / chalk | Robustness ranks |",
                  "|---:|---|---|---:|---:|---:|---:|---|---|---|"]
        for row in chosen:
            owner = row["ownership"]
            own = (f"{f(owner['ownership_sum'])} / {f(owner['relative_chalk'],0)}%"
                   if owner["status"] == "available" else "unavailable")
            names = ", ".join(player["name"] for player in row["roster"])
            robustness = "/".join(str(row["shadow_ranks"][key]) for key in shadows)
            lines.append(f"| {row['rank']} | {row['qb']['name']}; {row['primary_game']}; "
                         f"{row['stack']['type']} | {names} | ${row['salary']:,} | "
                         f"{f(row['mean'])} | {f(row['p90'])} | {f(row['objective_score'],4)} | "
                         f"{f(strong['mean']-row['mean'])}/{f(strong['p90']-row['p90'])} | "
                         f"{own} | {robustness} |")
        lines += ["", "Pairwise shared-player counts (same rank order):", "",
                  "| Rank | " + " | ".join(str(rank) for rank in ranks) + " |",
                  "|---|" + "---:|"*len(ranks)]
        for left in chosen:
            counts = [len(set(left["player_ids"]) & set(right["player_ids"]))
                      for right in chosen]
            lines.append(f"| {left['rank']} | " + " | ".join(map(str, counts)) + " |")
        lines.append("")
    lines += [
        "The optimization maximizes summed production selector within the preserved candidate universe, subject to one QB per lineup and the 6/9 overlap limit. A negative P90 cost in the tables means a P90 gain. This is a quality frontier, not a calibrated payout or ROI estimate.",
        "",
        "**Entry 2:** Jacoby Brissett with Michael Wilson and Trey McBride profits if Arizona's passing scores concentrate in that pair, while the New Orleans stack does not dominate. Its selector costs 0.0337 versus Shough; the QB/game path is distinct despite six shared players.",
        "",
        "**Entry 3:** Bryce Young with Jalen Coker and Cleveland bring-back Denzel Boston profits from a CAR–CLE passing exchange. Its P90 exceeds Shough by 3.57 in the best three-entry version. It shares only three players with each of the first two entries.",
        "",
        "**Entry 4:** Trevor Lawrence with Parker Washington adds a Jacksonville passing path against New England: Jacksonville passing efficiency or a Washington spike must beat the New Orleans, Arizona, and Carolina QB paths. The five-point 4-entry optimum replaces the Bryce roster at rank 33 with rank 40 to respect overlap. Trevor's mean/P90 costs versus the strongest Shough lineup are 2.56/−1.96, and selector cost is 0.0702. This is a different QB/game outcome.",
        "",
        "**Entry 5:** Jared Goff with Amon-Ra St. Brown adds a Detroit passing path against the Jets: concentrated Goff-to-St. Brown production must outrun the other QB stacks. Its mean/P90 costs versus Shough are 2.03/0.09, and selector cost is 0.0948. It shares core one-offs but changes the QB and correlated receiver, so it is a plausible additional profit path rather than roster churn.",
        "",
        "**Decision:** Lineup quality supports all five entries under the diagnostic five-point joint screen and 6/9 overlap rule. Entries 4 and 5 carry separate QB/game theses; neither required relaxing to 6 or 7 points. This does not establish the profitable entry count without a contest payout and field model. No stack/context weights or permanent quality threshold were changed.",
        "",
    ]
    OUTPUT.write_text("\n".join(lines))
    print(OUTPUT)


if __name__ == "__main__":
    main()
