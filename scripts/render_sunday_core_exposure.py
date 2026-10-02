#!/usr/bin/env python3
"""Render the frozen prelock core-exposure diagnostic as a readable report."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


SOURCE = Path("artifacts/sunday-main-core-exposure-2026w3.json")
OUTPUT = Path("artifacts/sunday-main-core-exposure-2026w3.md")


def money(value: float) -> str:
    return f"${value:,.0f}"


def portfolio_section(title: str, result: dict, baseline: dict) -> list[str]:
    lines = [f"### {title}", ""]
    if result["status"] != "optimal":
        lines += [f"**{result['status']}** under the unchanged 5-point joint screen, one QB per lineup, five distinct QBs, and overlap at most 6/9.", ""]
        return lines
    lines += [
        f"Selector **{result['selector_sum']:.5f}** ({result['selector_sum']-baseline['selector_sum']:+.5f}); "
        f"summed mean **{result['mean_sum']:.2f}** ({result['mean_sum']-baseline['mean_sum']:+.2f}); "
        f"summed P90 **{result['p90_sum']:.2f}** ({result['p90_sum']-baseline['p90_sum']:+.2f}). "
        f"Lowest lineup mean **{result['minimum_mean']:.2f}**; lowest lineup P90 **{result['minimum_p90']:.2f}**.", "",
        "| Frozen rank | QB / primary game / stack | Exact roster | Salary | Mean | P90 | Selector |",
        "|---:|---|---|---:|---:|---:|---:|",
    ]
    for row in result["lineups"]:
        rank = f"#{row['rank']}" if row["rank"] else "new exact solve"
        roster = ", ".join(f"{player['position']} {player['name']}" for player in row["roster"])
        lines.append(f"| {rank} | {row['qb']['name']} / {row['primary_game']} / {row['stack']['type']} "
                     f"| {roster} | {money(row['salary'])} | {row['mean']:.2f} | "
                     f"{row['p90']:.2f} | {row['objective_score']:.5f} |")
    lines += ["", "Pairwise shared players (row/column lineup order above):", "",
              "| Lineup | " + " | ".join(str(i) for i in range(1, 6)) + " |",
              "|---:|" + "---:|" * 5]
    for i, counts in enumerate(result["overlap"], 1):
        lines.append(f"| {i} | " + " | ".join(str(count) for count in counts) + " |")
    lines += ["", "Player exposures:", "",
              "| Player | Position | Entries | Exposure |",
              "|---|---|---:|---:|"]
    for player in result["exposure"]:
        lines.append(f"| {player['name']} | {player['position']} | "
                     f"{player['appearances']}/5 | {20*player['appearances']}% |")
    lines += ["", "Game exposure (at least one rostered player from the game):", "",
              "| Game | Entries |", "|---|---:|"]
    games = Counter()
    for row in result["lineups"]:
        for game in set(row["games_represented"]):
            games[game.split(" 09/")[0]] += 1
    for game, count in games.most_common():
        lines.append(f"| {game} | {count}/5 |")
    lines.append("")
    return lines


def main() -> None:
    data = json.loads(SOURCE.read_text())
    baseline = data["unrestricted"]
    lines = [
        "# Sunday Main five-entry core exposure / fragility audit", "",
        f"Frozen run `{data['source_optimizer_run_id']}`; cutoff "
        f"`{data['source_data_cutoff_at']}`. No Week 3 outcomes used. "
        "Football projections, P90, scoring weights, ownership, and the joint 5-point screen were unchanged.", "",
        "## Method and limits", "",
        "The starting universe contained 223 saved diagnostic candidates, including 23 that passed both quality guards. "
        f"I solved {data['discovery']['core_exclusion_requests']} exact QB/core-exclusion requests against the frozen player pool; "
        f"{data['discovery']['feasible_core_exclusion_requests']} were feasible. I enumerated up to "
        f"{data['discovery']['alternate_solves_per_feasible_request']} further exact solutions per feasible request. "
        f"The resulting universe has {data['discovery']['candidate_count']} unique legal lineups, "
        f"{data['discovery']['eligible_candidate_count']} under the joint guard. The portfolio MILP maximizes the unchanged "
        "selector over those candidates, requires five distinct QBs and at most six shared players per pair. "
        "Its optimality is over this expanded diagnostic universe; it is not a proof over every legal five-lineup combination. "
        "The QB/core exclusion infeasibility findings are exact legal solves.", "",
        "## Current exposure: ranks 3 / 19 / 40 / 81 / 118", "",
        f"Value rank is mean per $1,000 salary among {data['value_rank_basis']['player_count']} "
        "frozen included non-QB/non-DST players. Role class comes from the saved projection run's "
        "linked feature run; ownership comes from the frozen ownership run.", "",
        "| Player | Entries | Mean | P90 | Salary | Ownership | Value rank | Role class | Main selection driver |",
        "|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    why = {
        "Derrick Henry": "Elite RB raw quality; one-off in these five, with no required QB stack; expensive but projects 2.80 points/$1k.",
        "Jalen Coker": "Top-two salary value and primary receiving role; Bryce stack partner in one entry, one-off in four.",
        "Denzel Boston": "Low salary and top-five value; Bryce bring-back by construction but the saved 42.5 game total fires no explicit bring-back rule bonus.",
        "Chase Brown": "Strong one-off RB quality at $6,600; no selected QB stack dependence.",
        "Cade Otton": "Best mean/$1k salary value; cheap TE enables expensive RB/WR choices, with no selected QB stack dependence.",
    }
    for row in data["exposure"]:
        lines.append(f"| {row['name']} | {row['appearances']}/5 ({row['exposure_pct']}%) | "
                     f"{row['mean']:.2f} | {row['p90']:.2f} | {money(row['salary'])} | "
                     f"{row['ownership']:.2f}% | #{row['value_rank']} | {row['role_class']} | "
                     f"{why[row['name']]} |")
    lines += [
        "", "**Cause separation.** Henry is chiefly raw elite quality; Coker and Boston are strong salary values. "
        "The only direct QB stack dependency among the universal three is Young–Coker. Boston is a Young bring-back "
        "but its explicit bring-back rule contribution is zero in this frozen slate. "
        "The ordinary candidate set magnified concentration: all 23 previously saved joint-5 candidates contained "
        "Henry and Coker, while 19 contained Boston. Exact exclusions found legal alternatives, so their presence was "
        "not a player-feasibility rule or ownership exposure cap. No ownership exposure cap was imposed in these "
        "portfolio solves. Distinct-QB and joint-quality constraints make "
        "Coker especially hard to remove.", "",
        "### Exact absence feasibility by QB family", "",
        "| Player excluded | Qualifying QB families under joint 5-point screen |",
        "|---|---|",
    ]
    for name in ("Derrick Henry", "Jalen Coker", "Denzel Boston"):
        qbs = [row["qb_name"] for row in data["core_exclusion_request_results"]
               if row["excluded"] == [name] and row["feasible"]]
        lines.append(f"| {name} | {', '.join(qbs)} |")
    lines += ["", "No five-point lineup omits both Coker and Boston for any of the seven qualifying QB families. "
              "Thus every legal screened QB path in this audit still uses a CAR–CLE player.", "",
              "## Independent leave-one-out limits", ""]
    lines += portfolio_section("A. Unrestricted baseline", baseline, baseline)
    for name in ("Derrick Henry", "Jalen Coker", "Denzel Boston"):
        for cap in (4, 3):
            result = data["independent_caps"][name][str(cap)]
            lines += portfolio_section(f"{name}: maximum {cap}/5", result, baseline)
    lines += ["## Minimum diversification: every non-QB at most 4/5", ""]
    lines += portfolio_section("Strongest found with universal non-QB cap", data["all_non_qb_cap4"], baseline)
    lines += [
        "## Structural failure paths", "",
        "- Current five: a Henry, Coker, or Boston individual failure touches every entry. "
        "BAL–DAL and CAR–CLE game-level failures each touch all five. Chase Brown and Cade Otton each touch three.",
        "- All-non-QB-cap-four five: a Henry failure spares Bryce Young; a Coker failure spares Tyler Shough; "
        "a Boston failure spares Trevor Lawrence. These surviving entries retain their separate QB stacks, "
        "but each still depends on at least one other common core player.",
        "- CAR–CLE still touches all five reduced-concentration entries, because every screened QB family "
        "requires Coker or Boston. BAL–DAL falls to four entries; NYJ–DET rises to four. "
        "The cap moves some shared game risk rather than removing it.", "",
        "## Decision", "",
        "- Boston at 4/5 costs 0.01239 selector points and 0.74 summed mean points: very little. "
        "At 3/5 the cost remains small (0.05290 selector points).",
        "- Henry at 4/5 costs 0.08257 selector points: modest. At 3/5 the cost is 0.20557: material.",
        "- Coker at 4/5 costs 0.10484 selector points: moderate. At 3/5 it is infeasible "
        "with five distinct QBs and the unchanged joint five-point screen.",
        "- The strongest all-non-QB-cap-four five costs 0.24892 selector points (0.93%), "
        "2.58 summed mean points, and 5.76 summed P90 points against the unrestricted five. "
        "It removes every 100% single-player exposure but retains 100% CAR–CLE game exposure. "
        "That is a moderate score cost for a narrower reduction in structural risk, not five independent game theses.", "",
        "**Portfolio choice:** the unrestricted five is the raw-score leader. For five actual entries, "
        "the all-non-QB-cap-four five is the better individual-failure balance among the tested sets: "
        "it keeps five distinct QB paths and gives one lineup a way through each core player's failure "
        "for a 0.93% selector cost. It remains fragile to a CAR–CLE game failure, so the exposure cap "
        "should be understood as partial protection rather than a new independent game thesis.", "",
        "These are prelock structural comparisons. No win probabilities or actual game outcomes were used.", "",
    ]
    OUTPUT.write_text("\n".join(lines))
    print(f"saved {OUTPUT}")


if __name__ == "__main__":
    main()
