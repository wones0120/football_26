#!/usr/bin/env python3
"""Render the frozen clean-CAR portfolio diagnostic without rerunning solves."""

from __future__ import annotations

import json
from pathlib import Path


SOURCE = Path("artifacts/sunday-main-clean-car-portfolio-2026w3.json")
OUTPUT = Path("artifacts/sunday-main-clean-car-portfolio-2026w3.md")
LABELS = {
    "A_unrestricted": "A — unrestricted current five",
    "B_non_qb_max4": "B — all non-QB players at most four",
    "C_clean_car": "C — clean CAR/CLE diversification",
}


def f(value: float, digits: int = 2) -> str:
    return f"{value:,.{digits}f}"


def main() -> None:
    data = json.loads(SOURCE.read_text())
    portfolios = data["portfolios"]
    lines = [
        "# Sunday Main — clean CAR/CLE diversification portfolio",
        "",
        f"Frozen source run: `{data['source_optimizer_run_id']}`. Prelock projections, P90s, ownership, football weights, and context/correlation weights are unchanged. No game outcomes were used.",
        "",
        "The portfolio objective maximizes summed production selector score over the saved expanded diagnostic candidate universe, with five distinct QBs and at most six shared players per lineup pair. C also caps every non-QB at four appearances and CAR/CLE offensive exposure at four entries. These are diagnostic portfolio constraints, not production settings.",
        "",
        "## Screen and result",
        "",
        "| Joint mean/P90 loss allowance | C feasible? |",
        "|---:|:---:|",
    ]
    for item in data["screen_grid"]:
        lines.append(f"| {f(item['screen_gap'])} | {'Yes' if item['portfolio']['status'] == 'optimal' else 'No'} |")
    gap = data["car_free_exact_minimum_gap_interval"]
    lines += [
        "",
        f"The first feasible 0.01-point step is **{f(data['first_feasible_centipoint_screen'])}**. The exact CAR/CLE-free legal solve brackets the limiting joint loss between **{f(gap['lower'], 8)}** and **{f(gap['upper'], 8)}**; the feasible lineup's loss is **{f(gap['witness_joint_gap'], 8)}**. The full C portfolio is feasible at that witness loss. Thus the minimum is approximately **5.03266008** points, within solve tolerance.",
        "",
        f"Global legal maxima: mean **{f(data['unchanged_quality_maxima']['mean'], 3)}**, summed P90 **{f(data['unchanged_quality_maxima']['p90'], 3)}**. A and B retain the current five-point screen. C relaxes only the diagnostic screen.",
        "",
        "## Portfolio comparison",
        "",
        "| Portfolio | Sum mean | Sum P90 | Sum selector | Lowest mean | Lowest P90 | Max joint loss | QBs |",
        "|:---|---:|---:|---:|---:|---:|---:|:---|",
    ]
    for key, label in LABELS.items():
        p = portfolios[key]
        qbs = ", ".join(item["name"] for item in p["qb_exposure"])
        lines.append(
            f"| {label} | {f(p['mean_sum'], 3)} | {f(p['p90_sum'], 3)} | {f(p['selector_sum'], 6)} | "
            f"{f(p['minimum_mean'], 3)} | {f(p['minimum_p90'], 3)} | {f(p['maximum_joint_gap'], 3)} | {qbs} |"
        )
    lines += ["", "## Exact lineups", ""]
    for key, label in LABELS.items():
        p = portfolios[key]
        lines += [
            f"### {label}",
            "",
            "| # | QB | Rank | Salary | Mean | P90 | Selector | CAR/CLE offense? | Exact roster |",
            "|---:|:---|---:|---:|---:|---:|---:|:---:|:---|",
        ]
        for index, row in enumerate(p["lineups"], 1):
            roster = ", ".join(f"{player['name']} ({player['position']})" for player in row["roster"])
            car = "Yes" if any(player["team"] in {"CAR", "CLE"} and player["position"] in {"QB", "RB", "WR", "TE"} for player in row["roster"]) else "No"
            lines.append(
                f"| {index} | {row['qb']['name']} | {row.get('rank') or 'new exact'} | ${row['salary']:,} | "
                f"{f(row['mean'], 3)} | {f(row['p90'], 3)} | {f(row['objective_score'], 6)} | {car} | {roster} |"
            )
        lines += ["", "Pairwise overlap (including QB and DST):", "",
                  "| QB | " + " | ".join(row["qb"]["name"] for row in p["lineups"]) + " |",
                  "|:---|" + "---:|"*5]
        for row, overlaps in zip(p["lineups"], p["overlap"]):
            lines.append("| " + row["qb"]["name"] + " | " + " | ".join(str(value) for value in overlaps) + " |")
        lines.append("")
    lines += [
        "## Player exposure",
        "",
        "Each count is out of five; multiply by 20 for exposure percent.",
        "",
        "| Player | Pos | Team | A | B | C |",
        "|:---|:---:|:---:|---:|---:|---:|",
    ]
    exposures = {key: {row["player_id"]: row for row in p["player_exposure"]}
                 for key, p in portfolios.items()}
    all_players = {pid: row for table in exposures.values() for pid, row in table.items()}
    for pid, player in sorted(all_players.items(), key=lambda item: (
        -max(exposures[key].get(item[0], {}).get("appearances", 0) for key in LABELS),
        item[1]["name"],
    )):
        counts = [exposures[key].get(pid, {}).get("appearances", 0) for key in LABELS]
        lines.append(f"| {player['name']} | {player['position']} | {player['team']} | " + " | ".join(map(str, counts)) + " |")
    lines += [
        "",
        "## Game offensive exposure",
        "",
        "Each cell is entries with at least one offensive player / total offensive-player appearances. DST-only appearances are excluded.",
        "",
        "| Game | Total | A | B | C |",
        "|:---|---:|---:|---:|---:|",
    ]
    game_maps = {key: {row["game_id"]: row for row in p["game_offensive_exposure"]}
                 for key, p in portfolios.items()}
    game_ids = sorted(set().union(*(table.keys() for table in game_maps.values())))
    for gid in game_ids:
        row = next(table[gid] for table in game_maps.values() if gid in table)
        cells = []
        for key in LABELS:
            entry = game_maps[key][gid]
            cells.append(f"{entry['offense_entries']}/5 · {entry['offense_appearances']}")
        total = "—" if row["game_total"] is None else f"{f(row['game_total'], 1)}"
        lines.append(f"| {row['game']} | {total} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "## CAR/CLE-free replacement and quality cost",
        "",
        "C's Tyler Shough lineup is the CAR/CLE-free entry: Shough / Derrick Henry / De'Von Achane / Chris Olave / Parker Washington / Michael Wilson / Zay Flowers / Cade Otton / Dolphins DST. It has mean 137.624, P90 239.774, selector 5.266253 and a 5.032660-point loss from each global maximum.",
        "",
        "Relative to A's Shough entry, it removes Jalen Coker and Denzel Boston. The WR group gains Parker Washington, Michael Wilson, and Zay Flowers in place of Coker, Boston, and Devaughn Vele; De'Von Achane replaces Chase Brown at RB, and Cade Otton replaces Trey McBride at TE. QB, Henry, Olave, and Dolphins DST remain.",
        "",
        f"C versus A: selector {f(data['C_minus_A']['selector'], 6)}, summed mean {f(data['C_minus_A']['mean'], 3)}, summed P90 {f(data['C_minus_A']['p90'], 3)}. C versus B: selector {f(data['C_minus_B']['selector'], 6)}, summed mean {f(data['C_minus_B']['mean'], 3)}, summed P90 +{f(data['C_minus_B']['p90'], 3)}.",
        "",
        "C moves Coker, Boston, and Henry from 5/5 in A to 4/5 each. B already caps those players at 4/5 but still has CAR/CLE offense in all five entries. C removes that one-game exposure from one entry without demanding any BAL/DAL or BUF/LAC stack.",
        "",
        "The portfolio optimum is exact over the saved 278-candidate diagnostic universe. The no-CAR/CLE lineup and its minimum screen gap come from a full legal solve over frozen players; an unseen legal non-CAR lineup could change the portfolio optimum if the universe is expanded again. No production selector or UI setting changed.",
        "",
    ]
    OUTPUT.write_text("\n".join(lines))
    print(f"saved {OUTPUT}")


if __name__ == "__main__":
    main()
