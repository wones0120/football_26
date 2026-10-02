#!/usr/bin/env python3
"""Render the persisted Saturday prelock portfolio and exact outage alternatives."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy import text

from backend.app.db import engine
from scripts.audit_sunday_main_portfolio_frontier import load_frozen
from scripts.finalize_sunday_main_portfolio_2026w3 import COKER, FLOWERS, OUTPUT


REPORT = OUTPUT.with_suffix(".md")
SLOTS = ("QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST")


def _name(player: dict) -> str:
    return str(player["name"])


def _metric(value: float | None, decimals: int = 2) -> str:
    return "unavailable" if value is None else f"{value:.{decimals}f}"


def _kickoff(player: dict) -> str:
    value = str(player.get("game_id") or "")
    return value.split(" ", 1)[1] if " " in value else "unavailable"


def _roster(lineup: dict) -> str:
    return " / ".join(_name(player) for player in lineup["roster"])


def _portfolio(name: str, scenario: dict, *, guard: float,
               injury_status: dict[str, dict]) -> list[str]:
    lines = [f"## {name}", ""]
    if scenario["status"] != "optimal":
        return lines + [f"No five-entry portfolio: {scenario['status']}", ""]
    lines += [
        f"Application optimizer run: `{scenario['optimizer_run_id']}`. "
        f"Joint guard {guard:.2f}; five distinct QBs; overlap at most 6/9; "
        f"non-QB exposure cap {scenario['exposure_limit']}/5.",
        f"Portfolio sum: mean **{scenario['mean_sum']:.2f}**, summed P90 **{scenario['p90_sum']:.2f}**, "
        f"selector **{scenario['score_sum']:.4f}**.", "",
        "| # | QB | RB | RB | WR | WR | WR | TE | FLEX | DST | Salary | Mean | Sum P90 | Selector | Own sum | Primary game / stack | Mean loss | P90 loss | Questionable | FLEX kickoff ET |",
        "|---:|---|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---|---|",
    ]
    for number, lineup in enumerate(scenario["lineups"], 1):
        roster = lineup["roster"]
        assert tuple(player["roster_position"] for player in roster) == SLOTS
        questionable = [player["name"] for player in roster
                        if str(injury_status.get(player["player_id"], {}).get("injury_status") or "").upper()
                        in {"Q", "QUESTIONABLE", "D", "DOUBTFUL"}]
        cells = [str(number), *(_name(player) for player in roster),
                 f"${lineup['salary']:,.0f}", _metric(lineup["mean"]), _metric(lineup["p90"]),
                 _metric(lineup["selector"], 4),
                 _metric(lineup["ownership"].get("ownership_sum")),
                 f"{lineup['primary_game']} / {lineup['stack']['type']}",
                 _metric(lineup["mean_loss"], 3), _metric(lineup["p90_loss"], 3),
                 ", ".join(questionable) or "none", _kickoff(roster[7])]
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["", "### Exposure", "", "| Player | Entries | Exposure |", "|---|---:|---:|"]
    counts = Counter(player["name"] for lineup in scenario["lineups"] for player in lineup["roster"])
    for player, count in counts.most_common():
        lines.append(f"| {player} | {count}/5 | {20*count}% |")
    lines += ["", "QB exposure: " + ", ".join(
        f"{lineup['qb']['name']} 1/5" for lineup in scenario["lineups"]), ""]
    games: dict[str, dict] = defaultdict(lambda: {"entries": set(), "appearances": 0, "dst_only": set()})
    for index, lineup in enumerate(scenario["lineups"], 1):
        for player in lineup["roster"]:
            game = str(player.get("game_id") or "unavailable").split(" ", 1)[0]
            if player["position"] == "DST":
                games[game]["dst_only"].add(index)
            else:
                games[game]["entries"].add(index)
                games[game]["appearances"] += 1
    lines += ["| Game | Offensive entries | Offensive appearances | DST entries |",
              "|---|---:|---:|---:|"]
    for game, values in sorted(games.items(), key=lambda item: (-len(item[1]["entries"]), item[0])):
        lines.append(f"| {game} | {len(values['entries'])}/5 | {values['appearances']} | {len(values['dst_only'])}/5 |")
    lines += ["", "Pairwise overlap (shared players of 9):", "",
              "| Entry | 1 | 2 | 3 | 4 | 5 |", "|---:|---:|---:|---:|---:|---:|"]
    ids = [set(player["player_id"] for player in lineup["roster"])
           for lineup in scenario["lineups"]]
    for i in range(5):
        lines.append("| " + str(i+1) + " | " + " | ".join(
            "—" if i == j else str(len(ids[i] & ids[j])) for j in range(5)) + " |")
    lines += [""]
    return lines


def main() -> None:
    report = json.loads(OUTPUT.read_text())
    frozen = load_frozen(report["source_optimizer_run_id"])
    source_eligible = {player.player_id for player in frozen["players"]}
    report["snapshot_out_players"] = [row for row in report.get("snapshot_out_players", [])
                                       if row["player_id"] in source_eligible]
    with engine.connect() as connection:
        ownership = connection.execute(text("""
            SELECT data_cutoff_at FROM target.ownership_model_run
            WHERE ownership_run_id=:run_id
        """), {"run_id": report["ownership_run_id"]}).scalar_one()
        injury_rows = connection.execute(text("""
            SELECT DISTINCT ON (player_id) player_id, injury_status, injury_details, as_of
            FROM target.snapshot_injury_status
            WHERE season=2026 AND week=3 AND UPPER(slate)='SUNDAY_MAIN'
              AND as_of <= :source_created_at
            ORDER BY player_id, as_of DESC
        """), {"source_created_at": frozen["run"]["created_at"]}).mappings().all()
    injury_status = {str(row["player_id"]): dict(row) for row in injury_rows}
    report["ownership_cutoff_at"] = str(ownership)
    report["market_cutoff_at"] = None
    report["market_cutoff_note"] = (
        "Market values are frozen in the Friday projection feature snapshot; "
        "no independent market observation time is stored for this run."
    )
    active = report["scenarios"]["active"]
    coker = report["scenarios"]["coker_out"]
    flowers = report["scenarios"]["flowers_out"]
    both = report["scenarios"]["both_out"]
    lines = [
        "# FINAL 5 TO ENTER TONIGHT — Week 3 Sunday Main",
        "",
        "These are the injury-corrected, application-persisted lineups. They use no game outcomes and no projection edits.",
        "They are for the saved run's **DraftKings Classic nine-slot contract**, which includes FLEX. "
        "Verify the exact contest template before uploading if tonight's contest uses another roster format.",
        "",
        "## Source freshness",
        "",
        f"- Projection cutoff: **{report['projection_cutoff_at']}**; run `{report['projection_run_id']}`.",
        f"- Injury/status cutoff: **{report['injury_snapshot_cutoff_at']}**; source {', '.join(report['injury_source'])}.",
        f"- Ownership cutoff: **{ownership}**; run `{report['ownership_run_id']}`.",
        f"- Market cutoff: **not independently recorded**. {report['market_cutoff_note']}",
        f"- Saturday injury status removed {', '.join(row['name'] for row in report['snapshot_out_players'])} "
        "from the run's nominally eligible player pool.",
        "",
        f"Expanded discovery found **{report['candidate_count']}** unique legal candidates; "
        f"global legal maxima are mean **{report['global_mean']:.3f}** and summed P90 **{report['global_p90']:.3f}**. "
        f"The 5.05 joint guard admitted {report['guarded_candidate_count']} candidates.",
        "",
    ]
    lines += _portfolio("FINAL 5 TO ENTER TONIGHT — Coker active/full role", active,
                        guard=report["guard"], injury_status=injury_status)
    lines += ["### Correlation governor check", "",
              "| Entry | QB | Strongest same-QB raw/control mean | P90 | Selected mean sacrifice | P90 sacrifice | Correlation/context gain | Flag |",
              "|---:|---|---:|---:|---:|---:|---:|---|"]
    for index, lineup in enumerate(active["lineups"], 1):
        control = lineup["strongest_same_qb_raw_control"]
        both_loss = control["mean_sacrifice"] > 1e-6 and control["p90_sacrifice"] > 1e-6
        lines.append(f"| {index} | {lineup['qb']['name']} | {control['mean']:.2f} | {control['p90']:.2f} | "
                     f"{control['mean_sacrifice']:.2f} | {control['p90_sacrifice']:.2f} | "
                     f"{control['correlation_context_gain']:.4f} | "
                     f"{'**Loses both**' if both_loss else 'No two-metric sacrifice'} |")
    lines += ["", "### Football-sanity and availability warnings", "",
              "- All selected players carry `current_week_context_missing`; no linked current-week role evidence was available in this run.",
              "- Jalen Coker is Q (ankle) in the Saturday snapshot and all five lineups. The run flags `injury_information_not_incorporated` for him.",
              "- Zay Flowers is Q (hamstring) but appears in zero active lineups.",
              "- The run's injury filter missed four players marked OUT; this final discovery excluded them before selection.",
              "- A position-level football-core classification is unavailable for this Week 3 snapshot; no unsupported role verdict was added.",
              "",
              "### Why universal core exposure remains", "",
              "Henry, Coker, and Boston each appear 5/5. An all-non-QB maximum 4/5 is infeasible inside the 5.05 guard and 6/9 overlap. "
              "In the expanded candidate universe, the lowest guard permitting that cap with five QBs is 9.909; "
              "its portfolio loses 12.90 mean and 13.36 summed P90 versus the final five.",
              "",
              "## Exact injury contingencies", "",
              "A credible limited-role report has no quantified projection in the frozen inputs. "
              "Use the relevant OUT portfolio as the conservative exact alternative; this does not assert a limited-role mean.",
              "",
    ]
    lines += _portfolio("Coker OUT / Coker credible limited role", coker,
                        guard=coker.get("quality_guard_used", report["guard"]), injury_status=injury_status)
    lines += _portfolio("Flowers OUT / Flowers credible limited role", flowers,
                        guard=flowers.get("quality_guard_used", report["guard"]), injury_status=injury_status)
    lines += _portfolio("Both OUT / both credible limited role", both,
                        guard=both.get("quality_guard_used", report["guard"]), injury_status=injury_status)
    lines += ["## Contingency quality cost", "",
              "| Scenario | Selector change | Mean change | P90 change | Joint guard used |",
              "|---|---:|---:|---:|---:|"]
    for name, scenario in (("Coker OUT", coker), ("Flowers OUT", flowers), ("Both OUT", both)):
        lines.append(f"| {name} | {scenario['score_sum']-active['score_sum']:+.4f} | "
                     f"{scenario['mean_sum']-active['mean_sum']:+.2f} | "
                     f"{scenario['p90_sum']-active['p90_sum']:+.2f} | "
                     f"{scenario.get('quality_guard_used', report['guard']):.2f} |")
    lines += ["", "**Operational note:** The OUT portfolios require a wider diagnostic quality guard. "
              "They are conditional fallbacks, not an endorsement of changing production weights or player projections.", ""]
    OUTPUT.write_text(json.dumps(report, indent=2, default=str, allow_nan=False)+"\n")
    REPORT.write_text("\n".join(lines))
    print(REPORT)


if __name__ == "__main__":
    main()
