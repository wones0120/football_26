#!/usr/bin/env python3
"""Render the frozen game-environment diagnostic without accessing live data."""

from __future__ import annotations

import json
from pathlib import Path


SOURCE = Path("artifacts/sunday-main-game-environment-2026w3.json")
OUTPUT = Path("artifacts/sunday-main-game-environment-2026w3.md")


def roster(row: dict) -> str:
    return ", ".join(f"{player['position']} {player['name']}" for player in row["roster"])


def ownership(row: dict) -> str:
    own = row.get("ownership") or {}
    return (f"{own['ownership_sum']:.2f}%" if own.get("status") == "available"
            else "unavailable")


def portfolio_lines(title: str, result: dict, baseline: dict, gap: float | None = None) -> list[str]:
    lines = [f"### {title}", ""]
    if result["status"] != "optimal":
        return lines + [f"**{result['status']}** at the joint {gap:g}-point screen.", ""]
    selector = result["selector_sum"]
    lines += [
        f"Selector sum **{selector:.5f}** ({selector-baseline['selector_sum']:+.5f} vs A); "
        f"summed mean **{result['mean_sum']:.2f}** ({result['mean_sum']-baseline['mean_sum']:+.2f}); "
        f"summed P90 **{result['p90_sum']:.2f}** ({result['p90_sum']-baseline['p90_sum']:+.2f}). "
        + (f"CAR–CLE offensive entries **{result['car_offense_entries']}/5**; "
           f"largest individual joint loss **{result['max_joint_gap']:.2f}**."
           if "car_offense_entries" in result else ""), "",
        "| Rank | QB / primary game / stack | Exact roster | Salary | Mean | P90 | Selector | Ownership |",
        "|---:|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in result["lineups"]:
        rank = f"#{row['rank']}" if row.get("rank") else "new exact solve"
        lines.append(f"| {rank} | {row['qb']['name']} / {row['primary_game']} / "
                     f"{row['stack']['type']} | {roster(row)} | ${row['salary']:,} | "
                     f"{row['mean']:.2f} | {row['p90']:.2f} | "
                     f"{row['objective_score']:.5f} | {ownership(row)} |")
    if "overlap" in result:
        lines += ["", "Pairwise shared players, in table order:", "",
                  "| Lineup | 1 | 2 | 3 | 4 | 5 |", "|---:|---:|---:|---:|---:|---:|"]
        for i, row in enumerate(result["overlap"], 1):
            lines.append(f"| {i} | " + " | ".join(str(value) for value in row) + " |")
    lines.append("")
    return lines


def main() -> None:
    data = json.loads(SOURCE.read_text())
    model = data["projection_model_lineage"]
    lines = [
        "# Sunday Main game environment / high-total exposure audit", "",
        f"Frozen optimizer run `{data['source_optimizer_run_id']}`; prelock cutoff "
        f"`{data['source_data_cutoff_at']}`. No Week 3 results were used. "
        "No production projections, ownership, weights, or settings were changed.", "",
        "## 1. Market information flow", "",
        f"The frozen player projection run `{model['projection_run_id']}` uses "
        f"`{model['model_id']}` (`{model['model_run_id']}`). Its recorded feature list includes "
        "`game_total_line`, `team_spread_line`, `team_implied_total`, and "
        "`opponent_implied_total`. **Market totals are already explicit inputs to the player-mean model.** "
        "The canonical P90 is residual-calibrated around that market-informed mean, so market information "
        "also reaches P90. This frozen run uses the canonical path; the separate capped matchup factor "
        "in the legacy fallback path did not produce these projections.", "",
        "| Stage | Frozen information path |",
        "|---|---|",
        "| Mean projection | Pregame line and implied totals enter the trained V4.2 model as explicit features; opportunity adjustment follows. |",
        "| Player P90 | Position/role residual calibration is applied around the projected mean, retaining the market-informed location. |",
        "| Context score | Cutoff-safe game total, team total and spread trigger high-total, high-team-total, favorite/underdog and competitive-shootout signals; these add a small per-player optimizer adjustment. |",
        "| Correlation rules | Cutoff-safe market context scales QB/pass-catcher stack quality, shootout bring-backs and four-offense two-team game stacks; spread can suppress a high-total shootout signal. |",
        "| Stack scoring | The frozen Classic rule requires QB+1 for legal construction. QB/pass-catcher pair and qualifying double-stack rules enter the selector, multiplied by unchanged correlation weight 0.17. A bring-back is not automatically required. |",
        "| Candidate generation | Ordinary sequential MILP and injected global/QB-family constructions optimize the same market-informed player score and correlation rules; no separate high-total filter or forced stack is applied. |",
        "| Final portfolio | The diagnostic portfolio MILP maximizes the existing lineup selector subject to QB, overlap, quality and stated exposure constraints. Game total is not a separate portfolio term. |", "",
        "The saved feature list confirms the information path, although it does not prove a nonzero "
        "marginal effect for every individual player. A new unconditional high-total bonus would reuse "
        "information already available to projections and parts "
        "of context/correlation. This audit does not add one. The precise marginal portion of an individual "
        "player projection attributable to total cannot be isolated from this saved run without a separate "
        "counterfactual projection exercise.", "",
        "## 2. Game-level offensive exposure in the current five", "",
        "Ownership sum below adds the projected ownership of each offensive appearance across entries; "
        "it is not a portfolio win probability. DST-only means an entry used that game's defense and no offense.", "",
        "| Game | Total | Team implied totals | Any entry | Offense entry | 2+ offense | QB stack | Offensive appearances | DST-only | Appearance ownership sum |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    games = sorted(data["game_exposure"].items(),
                   key=lambda item: (-float(item[1]["game_total"] or 0), item[0]))
    for game, row in games:
        implied = ", ".join(f"{team} {line['implied_total']:.2f}"
                            for team, line in row["team_lines"].items())
        own = row["offense_ownership_sum_across_appearances"]
        marker = "**" if game in {"BAL-DAL", "BUF-LAC", "CAR-CLE"} else ""
        lines.append(f"| {marker}{game}{marker} | {row['game_total']:.1f} | {implied} | "
                     f"{row['any_entries']}/5 | {row['offense_entries']}/5 | "
                     f"{row['multi_offense_entries']}/5 | {row['qb_stack_entries']}/5 | "
                     f"{row['offense_appearances']} | {row['dst_only_entries']}/5 | "
                     f"{own:.2f}% |" if own is not None else
                     f"| {marker}{game}{marker} | {row['game_total']:.1f} | {implied} | "
                     f"{row['any_entries']}/5 | {row['offense_entries']}/5 | "
                     f"{row['multi_offense_entries']}/5 | {row['qb_stack_entries']}/5 | "
                     f"{row['offense_appearances']} | {row['dst_only_entries']}/5 | unavailable |")
    lines += ["", "Projected ownership of each offensive piece used (appearances × player ownership):", "",
              "| Game | Offensive pieces |", "|---|---|"]
    for game, row in games:
        pieces = ", ".join(f"{piece['name']} {piece['appearances']}×{piece['projected_ownership']:.2f}%"
                           for piece in row["offensive_pieces"])
        lines.append(f"| {game} | {pieces or 'none'} |")
    lines += [
        "", "**Key contrast:** BAL–DAL is in all five via Henry, with Zay Flowers in two, but no BAL–DAL "
        "QB stack. CAR–CLE has Coker and Boston in every lineup, Young in one. LAC–BUF appears only "
        "through one Chargers DST; it has zero offensive exposure.", "",
        "## 3. Exact high-total game counterfactuals", "",
        "The original joint screen permits at most five points of loss from each global maximum "
        f"(mean {data['quality_maxima']['mean']:.2f}; summed P90 {data['quality_maxima']['p90']:.2f}). "
        "When that is infeasible, the table uses the nearest exact legal solve and gives its minimum "
        "joint-gap interval. The six solves use unchanged scoring and no forced bring-back.", "",
        "| Construction | Joint-5 | Minimum required joint gap | QB | Mean | P90 | Selector | Mean/P90 loss | Salary | Ownership | Stack |",
        "|---|---|---:|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    labels = [
        ("A_BAL_DAL_QB_stack", "A. BAL–DAL QB stack"),
        ("B_BAL_DAL_offense_2", "B. BAL–DAL ≥2 offense"),
        ("C_BAL_DAL_offense_3", "C. BAL–DAL ≥3 offense"),
        ("D_LAC_BUF_QB_stack", "D. LAC–BUF QB stack"),
        ("E_LAC_BUF_offense_2", "E. LAC–BUF ≥2 offense"),
        ("F_LAC_BUF_offense_3", "F. LAC–BUF ≥3 offense"),
    ]
    for key, label in labels:
        result = data["counterfactuals"][key]
        at_five = result["at_joint_5"]
        row = at_five or result["closest_if_5_infeasible"]
        interval = result["minimum_joint_gap_interval"]
        gap_text = "≤5.00" if at_five else (f"{interval['lower']:.2f}–{interval['upper']:.2f}"
                                            if interval else "unavailable")
        lines.append(f"| {label} | {'yes' if at_five else 'no'} | {gap_text} | "
                     f"{row['qb']['name']} | {row['mean']:.2f} | {row['p90']:.2f} | "
                     f"{row['objective_score']:.5f} | "
                     f"{row['mean_loss_vs_global']:.2f}/{row['p90_loss_vs_global']:.2f} | "
                     f"${row['salary']:,} | {ownership(row)} | {row['stack']['type']} |")
    lines += ["", "Exact rosters and competitiveness against the top joint-5 lineup "
              "(Shough, selector 5.40963):", ""]
    for key, label in labels:
        result = data["counterfactuals"][key]
        row = result["at_joint_5"] or result["closest_if_5_infeasible"]
        lines.append(f"- **{label}:** {roster(row)}. Selector difference "
                     f"{row['objective_score']-5.409631069960057:+.5f}; "
                     f"joint loss {max(row['mean_loss_vs_global'], row['p90_loss_vs_global']):.2f}. "
                     + ("Meets the current screen." if result["at_joint_5"] else
                        "Requires screen relaxation."))
    lines += ["", "### Representative player-level value in the three games", "",
              "| Game | Player | Salary | Mean | P90 | Mean/$1k | Ownership |",
              "|---|---|---:|---:|---:|---:|---:|"]
    for game, rows in data["high_total_player_values"].items():
        for row in rows[:8]:
            lines.append(f"| {game} | {row['name']} ({row['team']} {row['position']}) | "
                         f"${row['salary']:,} | {row['mean']:.2f} | {row['p90']:.2f} | "
                         f"{row['value_per_1000']:.2f} | "
                         f"{row['ownership']:.2f}% |" if row['ownership'] is not None else
                         f"| {game} | {row['name']} ({row['team']} {row['position']}) | "
                         f"${row['salary']:,} | {row['mean']:.2f} | {row['p90']:.2f} | "
                         f"{row['value_per_1000']:.2f} | unavailable |")
    lines += ["", "## 4. CAR–CLE value dependence", "",
              "| Player | Mean/P90 | Salary; mean/$1k | Opportunity | Market and context | Correlation in current five | Ownership effect |",
              "|---|---|---|---|---|---|---|"]
    for name, row in data["opportunity"].items():
        rules = [(item["lineup_rank"], rule.get("objective_contribution"))
                 for item in row["correlation_rules_by_baseline_lineup"]
                 for rule in item["rules"]]
        correlation = (", ".join(f"#{rank}: {value:+.5f}" for rank, value in rules)
                       if rules else "0.00000 across all five")
        lines.append(f"| {name} | {row['mean']:.2f}/{row['p90']:.2f} | "
                     f"${row['salary']:,}; {row['value_per_1000']:.2f} | "
                     f"{row['projected_targets']:.2f} targets; "
                     f"{100*row['target_share_mean_3']:.1f}% recent target share; "
                     f"{row['role_class']} | Total {row['game_total']:.1f}, team {row['team_total']:.1f}; "
                     f"optimizer context adjustment {row['context_adjustment_points']:+.5f} points | "
                     f"{correlation} | {row['ownership']:.2f}% projected; "
                     "0.00000 ownership-selector contribution |")
    lines += ["", "These observed quantities separate the effects available in the frozen snapshot. "
              "The mean/P90 already carry an unseparated model response to the market features; "
              "the separate optimizer context and correlation amounts above are the incremental pieces.", "",
              "| Exclusion | Joint-5 result | Minimum required gap if excluded | Mean | P90 | Selector | Mean/P90 loss | Salary | Ownership | Exact roster |",
              "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
              ]
    for key, label in (("no_Coker", "No Coker"), ("no_Boston", "No Boston"),
                       ("neither_Coker_nor_Boston", "Neither"),
                       ("no_CAR_CLE_offense", "No CAR/CLE offense")):
        result = data["counterfactuals"][key]
        at_five = result["at_joint_5"]
        row = at_five or result["closest_if_5_infeasible"]
        interval = result["minimum_joint_gap_interval"]
        gap = "≤5.00" if at_five else f"{interval['lower']:.3f}–{interval['upper']:.3f}"
        lines.append(f"| {label} | {'yes' if at_five else 'no'} | {gap} | "
                     f"{row['mean']:.2f} | {row['p90']:.2f} | {row['objective_score']:.5f} | "
                     f"{row['mean_loss_vs_global']:.2f}/{row['p90_loss_vs_global']:.2f} | "
                     f"${row['salary']:,} | {ownership(row)} | {roster(row)} |")
    lines += ["", "The best no-CAR/CLE-offense construction misses the current screen by only "
              "about 0.033 joint-quality points. That boundary is exact to the stated binary-search interval; "
              "the 5-point screen remains unchanged.", "",
              "## 5. Five-entry portfolio alternatives", "",
              f"The portfolio search began with {data['portfolio_discovery']['saved_candidates']} saved "
              f"candidates plus {data['portfolio_discovery']['core_new_candidates']} prior exact core exclusions, "
              f"then ran {data['portfolio_discovery']['additional_requests']} additional QB/CAR-free solves. "
              f"It found {data['portfolio_discovery']['total_candidates']} unique legal lineups. "
              "Each portfolio MILP has five distinct QBs and overlap at most 6/9. "
              "The portfolio optimality claim is over this expanded diagnostic universe; the individual "
              "construction infeasibility claims above are exact legal solves.", "",
              "| Portfolio | Screen | Selector sum | Summed mean | Summed P90 | CAR–CLE offense | QBs |",
              "|---|---:|---:|---:|---:|---:|---|",
              ]
    baseline = data["portfolios"]["A_unrestricted"]
    portfolio_items = [
        ("A. current unrestricted", baseline, 5.0),
        ("B. non-QB max 4", data["portfolios"]["B_non_QB_cap4"], 5.0),
    ]
    for key, label in (("C_cap_CAR_CLE_4", "C. two high-total stacks, CAR ≤4"),
                       ("D_no_CAR_CLE_cap", "D. two high-total stacks, CAR uncapped")):
        branch = data["portfolios"][key]
        first = branch["first_feasible"]
        portfolio_items.append((label, first["result"] if first else branch["at_joint_5"],
                                first["screen_gap"] if first else 5.0))
    for label, result, gap in portfolio_items:
        if result["status"] != "optimal":
            lines.append(f"| {label} | {gap:.2f} | infeasible | — | — | — | — |")
            continue
        car_count = result.get("car_offense_entries")
        if car_count is None:
            car_count = sum(any(player["team"] in {"CAR", "CLE"} and player["position"] in {"QB", "RB", "WR", "TE"}
                                for player in row["roster"]) for row in result["lineups"])
        qbs = ", ".join(row["qb"]["name"].split()[-1] for row in result["lineups"])
        lines.append(f"| {label} | {gap:.2f} | {result['selector_sum']:.5f} | "
                     f"{result['mean_sum']:.2f} | {result['p90_sum']:.2f} | "
                     f"{car_count}/5 | {qbs} |")
    lines += ["", "C and D are infeasible at five. Both first become feasible near an **8.60-point joint "
              "screen** in this candidate universe: 3.60 points more allowance than the current rule. "
              "The exact LAC–BUF QB-stack lower/upper interval above brackets that boundary. "
              "CAR–CLE avoidance itself needs only about 5.033 points. Neither relaxation is recommended "
              "as a production change from one slate.", ""]
    for label, result, gap in portfolio_items:
        lines += portfolio_lines(label, result, baseline, gap)
    lines += ["## 6. Interpretation", "",
              "1. **Coker/Boston:** yes, their frozen player-level mean/P90 and salaries make them "
              "exceptional values despite a 42.5 total. Coker has 7.10 projected targets and only "
              "+0.04063 incremental context points; Boston has 2.83 projected targets and zero "
              "incremental context/correlation score in the current five. Ownership has zero selector weight.",
              "2. **BAL–DAL and LAC–BUF:** Henry is an excellent standalone BAL piece, but the BAL QBs "
              "cannot satisfy the joint-5 screen with a pass catcher. Josh Allen projects strongly but costs "
              "$8,000, and the BUF/LAC secondary partners carry lower per-dollar means than Coker/Boston. "
              "The LAC–BUF QB stack and even two-player offense fail the current quality screen. "
              "This is a player-level opportunity-cost result, not a blanket claim that every high-total player is overpriced.",
              "3. **Double counting:** game total, team implied totals and spread are recorded features of "
              "the frozen V4.2 projection model. They also enter bounded context and conditional "
              "correlation rules. Another unconditional high-total reward is unsupported by this audit.",
              "4. **Construction layer:** exact legal solves confirm that the missing high-total QB stacks "
              "are outside the unchanged quality screen; this is not merely omission by the 223-candidate "
              "generator. The selector uses summed player P90 plus rule-based correlation, so it may still "
              "miss some joint-tail shootout value. Historical prelock validation or lineup simulation, "
              "rather than this one slate's total, would be needed to establish that defect.", "",
              "**Decision:** keep production weights and the 5-point screen unchanged. The current five "
              "is more raw-quality compliant than forced BAL/LAC stack portfolios. Treat CAR–CLE "
              "concentration as a real shared failure path even though the player values are rational "
              "under frozen projections.", "",
              ]
    OUTPUT.write_text("\n".join(lines))
    print(f"saved {OUTPUT}")


if __name__ == "__main__":
    main()
