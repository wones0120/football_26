#!/usr/bin/env python3
"""Render the saved frozen RB/DST audit without rescoring any player."""

from __future__ import annotations

import json
from pathlib import Path


SOURCE = Path("artifacts/week3-rb-dst-audit.json")
OUTPUT = Path("artifacts/week3-rb-dst-audit.md")


def n(value, digits=2):
    return "—" if value is None else f"{value:.{digits}f}"


def corr(value):
    if value["pearson_r"] is None:
        return "—"
    return f"{n(value['pearson_r'], 3)} [{n(value['ci95'][0], 3)}, {n(value['ci95'][1], 3)}]"


def main() -> None:
    data = json.loads(SOURCE.read_text())
    history = data["historical"]
    lines = [
        "# Week 3 Sunday Main — RB projection and RB/DST game-script audit",
        "",
        f"Frozen optimizer run `{data['source_optimizer_run_id']}`; projection run `{data['source_projection_run_id']}`; cutoff `{data['source_data_cutoff_at']}`. No Week 3 outcomes, player edits, production-weight changes, or ESPN blending.",
        "",
        f"Mean model: **{data['model']['model_name']}**, version **{data['model']['model_version']}**. The frozen model's feature list includes game total, team spread, team implied total, and opponent implied total, so market information is already embedded in the point estimate. The fitted tree artifact URI is {data['model']['artifact_uri'] or 'unavailable'}, so exact SHAP and market-input rescoring are unavailable. The saved role grid contains one-feature model probes only; they are diagnostic associations, not causal effects.",
        "",
        "## Materially relevant RBs",
        "",
        "Recent snaps, carries, targets and target share use the frozen lagged three-game features. Receiving strength is the existing optimizer diagnostic on a 0–1 scale. Full trend fields and role counterfactual grids are in the JSON artifact.",
        "",
        "| RB | Salary | Mean | P90 | Role | Snap | Carries | Targets | Target share | Rec strength | Snap trend | Rush-share trend | Target-share trend | Implied | Spread | Total | H/A |",
        "|:---|---:|---:|---:|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|",
    ]
    for rb in data["rb_material"]:
        lines.append(
            f"| {rb['name']} | ${rb['salary']:,} | {n(rb['mean'])} | {n(rb['p90'])} | "
            f"{rb['role_class'] or '—'} | {n(rb['snap_share_mean_3'], 3)} | "
            f"{n(rb['carries_mean_3'])} | {n(rb['targets_mean_3'])} | "
            f"{n(rb['target_share_mean_3'], 3)} | {n(rb['receiving_role_strength'], 3)} | "
            f"{n(rb['recent_trend']['snap_share_trend'], 3)} | "
            f"{n(rb['recent_trend']['rush_share_trend'], 3)} | "
            f"{n(rb['recent_trend']['target_share_trend'], 3)} | "
            f"{n(rb['team_implied_total'])} | {n(rb['spread'], 1)} | "
            f"{n(rb['game_total'], 1)} | {rb['home_away']} |"
        )
    achane = next(row for row in data["rb_material"] if row["name"] == "De'Von Achane")
    role_grid = achane["role_counterfactual_grid"] or {}
    probes = role_grid.get("importance") or []
    lines += [
        "",
        "### Projection explanation and benchmark limits",
        "",
        "Achane's 16.47 mean and 26.90 player P90 combine a measured centerpiece role (77.3% recent snap share, 10.16 carries, 3.35 targets, 13.9% target share) with a poor market setting (Miami +11.5, 17.0 implied points). His receiving strength is 0.498. The tree directly uses lagged snap share and the measured role score; carries and targets inform role/opportunity features rather than entering as separate tree columns. The projection is internally explainable as workload and receiving opportunity surviving a low team total; the saved data do not establish that 16.47 is calibrated correctly.",
        "",
        f"One saved Achane role-importance probe lowered the input and moved the model mean by {n(min((item['delta'] for item in probes), default=0), 3)} points; the baseline remains 16.468. This is a controlled one-feature response, not an estimate of what a real role change would cause. Neutral-spread and league-average-implied-total rescoring cannot be reproduced from the saved fitted-model artifact because no artifact URI was persisted.",
        "",
        "Henry's 21.54 mean comes with 19.93 recent carries and a 27.75 team implied total. Gibbs (18.49) and Walker (18.05) retain high projected opportunity and P90 but cost $8,800 and $7,400; Taylor (17.47) has a smaller recent target role and only 20.5 team implied points. These are feature-level explanations, not proof of player-level model calibration.",
        "",
        f"**ESPN Week 3 benchmark:** {data['espn_week3_benchmark']['status']}. {data['espn_week3_benchmark']['reason']} Therefore no valid Week 3 ESPN deltas, full matched-RB mean bias, or receiving-heavy archetype bias estimate can be reported. The saved Week 2 capture is not a Week 3 comparator.",
        "",
        "The frozen model's saved walk-forward role calibration offers a separate internal check. Predicted-minus-actual mean error is positive 0.689 points across 282 RB offensive-centerpiece rows and negative 0.007 across 271 RB primary-option rows. This does not show broad underprojection for those role classes; it does not isolate receiving-heavy backs or validate Achane specifically. Full role-class rows are preserved in JSON.",
        "",
        "## Current RB + same-team DST candidate behavior",
        "",
        "The current Classic rule gives a **positive** RB+DST bonus only when point-in-time market data show a favorite stronger than three points; bonus strength grows with favorite status and lower game total. It gives **zero** RB+DST contribution to underdogs and near-pick'em teams; it never gives an explicit negative RB+DST penalty. Receiving role is not part of this particular bonus. Other lineup rules can still contribute separately.",
        "",
        f"Across the saved {data['candidate_universe_count']} candidates, {len(data['same_team_rb_dst'])} contain a same-team RB+DST pair. The table lists every one; repeated Achane/Dolphins appearances are distinct lineups.",
        "",
        "| Candidate rank | RB + DST | Script | Team / opp implied | Prior carries / targets | Role | RB+DST selector | Mean | P90 | Selector |",
        "|---:|:---|:---|---:|---:|:---|---:|---:|---:|---:|",
    ]
    for row in data["same_team_rb_dst"]:
        lines.append(
            f"| {row['rank'] or 'new exact'} | {row['rb']} + {row['dst']} | "
            f"{row['bucket']} ({n(row['spread'], 1)}) | "
            f"{n(row['team_total'])} / {n(row['opponent_total'])} | "
            f"{n(row['rushing_role'])} / {n(row['receiving_role'])} | {row['role']} | "
            f"{n(row['correlation_bonus'], 4)} | {n(row['mean'])} | {n(row['p90'])} | {n(row['selector'], 6)} |"
        )
    lines += [
        "",
        "All 12 saved pairs are Achane + Dolphins DST, with Miami a large underdog. The RB+DST rule contributes **0.0000** to each. This candidate concentration cannot describe the rule's behavior for favorite RB/DST constructions; that behavior is traced from production rule code above.",
        "",
        "## Historical RB–DST relationship",
        "",
        f"Method: {history['method']}. The paired sample has **{history['source_rows']['paired_eligible']} RB games** from **{history['overall']['games']} games**. Historical market fields come from the pregame feature matrix; RB role uses only native weekly stats from earlier games. Scores are same-game DraftKings actuals used only as outcomes. The market matrix is backfilled, not an original lock-time capture, which limits claims about a production rule.",
        "",
        "| Stratum | RB games | Games | Pearson r [game-bootstrap 95% CI] |",
        "|:---|---:|---:|:---|",
        f"| Overall | {history['overall']['n']} | {history['overall']['games']} | {corr(history['overall'])} |",
    ]
    for name in ("favorite >=6", "favorite 2–5.5", "near pick'em",
                 "underdog 2–5.5", "underdog >=6"):
        row = history["by_spread"].get(name)
        if row:
            lines.append(f"| {name} | {row['n']} | {row['games']} | {corr(row)} |")
    for name in ("workhorse rushing", "receiving-heavy", "committee/other"):
        row = history["by_role"].get(name)
        if row:
            lines.append(f"| {name} | {row['n']} | {row['games']} | {corr(row)} |")
    for label, key in (("Large underdog, prior targets ≥3", "large_underdog_receiving"),
                       ("Large underdog, prior targets <3", "large_underdog_low_receiving")):
        row = history[key]
        lines.append(f"| {label} | {row['n']} | {row['games']} | {corr(row)} |")
    lines += [
        "",
        "Large favorites show a modest positive association; large underdogs do not show a reliable positive or negative association. The large-underdog receiving split is imprecise, so it does not establish a protective receiving effect. Role-by-spread cells and separate 2024/2025 checks are preserved in JSON. The evidence supports displaying game-script context, but does not justify adding a negative underdog penalty or retuning the existing favorite bonus from this audit alone.",
        "",
        "## Exact Achane/Miami counterfactuals",
        "",
        "Each solve keeps the other four clean-CAR portfolio entries, Shough at QB, no CAR/CLE offense, every non-QB at most 4/5, and overlap at most 6/9. A is the current fixed entry. No B–E alternative meets the 5.04 joint screen; the shown lineup is the exact highest-selector solution at an approximately minimal feasible joint mean/P90 screen found by 12-step bisection for that exclusion.",
        "",
        "| Case | 5.04 feasible? | Closest joint loss | Salary | Mean | P90 | Selector | Context / positive corr | RB+DST script | Δ mean / P90 / selector vs A | Exact roster |",
        "|:---|:---:|---:|---:|---:|---:|---:|---:|:---|:---|:---|",
    ]
    for name, row in data["achane_alternatives"].items():
        lineup = row["lineup"]
        roster = ", ".join(f"{player['name']} ({player['position']})"
                           for player in lineup["roster"])
        same_team = [rb for rb in lineup["rbs"] if rb["same_team_dst"]]
        pair_script = (f"{same_team[0]['name']} + DST, underdog {n(same_team[0]['spread'], 1)}; bonus 0"
                       if same_team else "No same-team RB+DST")
        lines.append(
            f"| {name} | {'Yes' if row['status'] in {'current','feasible_at_5_04'} else 'No'} | "
            f"{n(row['minimum_joint_gap'], 3)} | ${lineup['salary']:,} | "
            f"{n(lineup['mean'], 3)} | {n(lineup['p90'], 3)} | {n(lineup['objective_score'], 6)} | "
            f"{n(lineup['components']['context'], 4)} / {n(lineup['correlation_positive'], 4)} | "
            f"{pair_script} | "
            f"{n(row.get('mean_delta_vs_current'), 3)} / {n(row.get('p90_delta_vs_current'), 3)} / "
            f"{n(row.get('selector_delta_vs_current'), 6)} | {roster} |"
        )
    lines += [
        "",
        "B keeps Dolphins DST and replaces Achane with Chase Brown; its closest joint loss is 5.848, driven by P90. C, D, and E select the same no-Miami lineup, replacing Dolphins DST with Commanders DST and dropping Achane; each needs a 6.055 joint allowance. All five cases have the same +0.0612 positive correlation contribution; the RB+DST pair contributes zero to A. Context falls from 0.0727 in A to 0.0653 in B and 0.0585 in C–E. The unchanged optimizer still prefers A under the diagnostic constraints. Achane + Dolphins DST is therefore a real portfolio fragility flag, but avoiding it has a measured quality cost rather than an automatic football veto.",
        "",
        "## Product behavior and decision",
        "",
        "New Classic small-field optimizer runs persist `rb_dst_diagnostics` in their saved report. The UI shows **Player why · RB projection and role**, **Lineup football sanity · warning only**, and **Portfolio flagged-construction exposure**. Flags show their evidence, informational status, and the strongest saved-candidate alternative with mean/P90/selector cost. The diagnostic rules do not change scoring, feasibility, ownership, or projections. Existing frozen runs retain their original persisted report; this audit's exact frozen results are preserved in JSON and Markdown.",
        "",
        "**Production change supported by evidence:** none. Keep the current weights and player projections. A same-team underdog RB+DST warning is useful; the historical samples do not support a new penalty or an RB-specific exception.",
        "",
    ]
    OUTPUT.write_text("\n".join(lines))
    print(f"saved {OUTPUT}")


if __name__ == "__main__":
    main()
