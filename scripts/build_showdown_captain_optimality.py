"""Summarize saved, actual-score Showdown Captain oracles before the target slate."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Database.config import get_connection_string
from backend.app.services.lineup_learning import _canonical_team
from backend.app.product_services.showdown_captain_optimality import build_optimality_report


def schedule_dates() -> dict[tuple, str]:
    dates: dict[tuple, str] = {}
    with create_engine(get_connection_string()).connect() as connection:
        rows = connection.execute(text("""
            SELECT season, week, home_team, away_team, raw_row_json ->> 'gameday' AS gameday
            FROM raw_nfl_schedule
            WHERE season BETWEEN 2024 AND 2026 AND week IS NOT NULL
              AND home_team IS NOT NULL AND away_team IS NOT NULL
            ORDER BY raw_nfl_schedule_id DESC
        """)).mappings()
        for row in rows:
            key = (int(row["season"]), int(row["week"]),
                   tuple(sorted((_canonical_team(row["home_team"]),
                                 _canonical_team(row["away_team"])))))
            if row["gameday"] and key not in dates:
                dates[key] = str(row["gameday"])
    return dates


def capture_historical_inputs(dataset: dict) -> dict:
    """Freeze source-keyed, strictly prior-game QB evidence for offline rebuilding."""
    qb_rows = [row for row in dataset.get("forced_captains", []) if row.get("position") == "QB"]
    master_ids = sorted({str(row["player_master_id"]) for row in qb_rows if row.get("player_master_id")})
    with create_engine(get_connection_string()).connect() as connection:
        schedule_rows = list(connection.execute(text("""
            SELECT season, week, home_team, away_team, raw_row_json ->> 'gameday' AS gameday,
                   raw_row_json ->> 'gametime' AS gametime
            FROM raw_nfl_schedule WHERE season BETWEEN 2024 AND 2026
            ORDER BY raw_nfl_schedule_id DESC
        """)).mappings())
        evidence_rows = list(connection.execute(text("""
            SELECT season, week, slate, team, player_master_id, status, source,
                   evidence_tier, created_at
            FROM starting_qb_evidence WHERE season BETWEEN 2024 AND 2026
        """)).mappings())
        stat_rows = list(connection.execute(text("""
            SELECT a.player_master_id, s.raw_nfl_weekly_stat_id, s.season, s.week,
                   s.team, s.raw_row_json
            FROM player_alias a JOIN raw_nfl_weekly_stat s ON s.player_id = a.source_key
            WHERE a.source_system = 'nflreadpy' AND a.player_master_id = ANY(:ids)
              AND s.season BETWEEN 2022 AND 2026 AND s.position = 'QB'
            ORDER BY s.raw_nfl_weekly_stat_id DESC
        """), {"ids": master_ids}).mappings()) if master_ids else []
        team_td_rows = list(connection.execute(text("""
            WITH latest AS (
              SELECT DISTINCT ON (season, week, player_id) season, week, team, raw_row_json
              FROM raw_nfl_weekly_stat
              WHERE season BETWEEN 2022 AND 2026 AND player_id IS NOT NULL
              ORDER BY season, week, player_id, raw_nfl_weekly_stat_id DESC
            )
            SELECT season, week, team,
                   SUM(COALESCE(NULLIF(raw_row_json ->> 'rushing_tds', '')::numeric, 0)) AS team_rushing_tds
            FROM latest GROUP BY season, week, team
        """)).mappings())
        salary_years = [dict(row) for row in connection.execute(text("""
            SELECT season, COUNT(DISTINCT (week, slate)) AS slate_slices, COUNT(*) AS salary_rows
            FROM curated_salary WHERE source_system = 'draftkings'
            GROUP BY season ORDER BY season
        """)).mappings()]

    schedule: dict[tuple, dict] = {}
    for row in schedule_rows:
        teams = tuple(sorted((_canonical_team(row["home_team"]), _canonical_team(row["away_team"]))))
        key = (int(row["season"]), int(row["week"]), teams)
        if len(set(teams)) == 2 and row["gameday"] and key not in schedule:
            schedule[key] = {"season": key[0], "week": key[1], "teams": list(teams),
                             "game_date": str(row["gameday"]), "game_time_et": row["gametime"]}
    slate_schedule = {}
    for slate in dataset.get("slates", []):
        teams = tuple(sorted({str(player.get("team") or "") for player in slate["optimal_lineup"]}))
        slate_schedule[(int(slate["season"]), int(slate["week"]), str(slate["slate"]))] = schedule.get(
            (int(slate["season"]), int(slate["week"]), teams)
        )
    starters = []
    for row in evidence_rows:
        key = (int(row["season"]), int(row["week"]), str(row["slate"]))
        game = slate_schedule.get(key)
        kickoff = None
        if game and game.get("game_time_et"):
            kickoff = datetime.fromisoformat(f"{game['game_date']}T{game['game_time_et']}")
        observed = row["created_at"].replace(tzinfo=None) if row["created_at"] else None
        if kickoff is None or observed is None or observed > kickoff:
            continue
        starters.append({"season": key[0], "week": key[1], "slate": key[2],
                         "team": _canonical_team(row["team"]),
                         "player_master_id": str(row["player_master_id"]),
                         "status": row["status"], "source": row["source"],
                         "evidence_tier": row["evidence_tier"],
                         "observed_at_et": observed.isoformat(),
                         "kickoff_at_et": kickoff.isoformat()})

    histories: dict[str, dict[tuple[int, int], dict]] = defaultdict(dict)
    for row in stat_rows:
        payload = row["raw_row_json"] or {}
        if payload.get("season_type") not in (None, "REG"):
            continue
        key = (int(row["season"]), int(row["week"]))
        histories[str(row["player_master_id"])].setdefault(key, {
            "team": _canonical_team(row["team"]), "carries": payload.get("carries"),
            "rushing_yards": payload.get("rushing_yards"),
            "rushing_tds": payload.get("rushing_tds"),
            "passing_tds": payload.get("passing_tds"),
        })
    team_tds = {(int(row["season"]), int(row["week"]), _canonical_team(row["team"])):
                float(row["team_rushing_tds"]) for row in team_td_rows if row["team"]}

    def average(values: list) -> float | None:
        numeric = [float(value) for value in values if value is not None]
        return float(mean(numeric)) if numeric else None

    prior_features = []
    for row in qb_rows:
        master_id = row.get("player_master_id")
        if not master_id:
            continue
        cutoff = (int(row["season"]), int(row["week"]))
        history = histories.get(str(master_id), {})
        recent_keys = sorted((key for key in history if key < cutoff), reverse=True)[:3]
        recent = [history[key] for key in recent_keys]
        numerator = sum(float(item["rushing_tds"]) for item in recent if item["rushing_tds"] is not None)
        denominators = [team_tds.get((*key, history[key]["team"])) for key in recent_keys]
        denominator = sum(value for value in denominators if value is not None)
        prior_features.append({
            "season": cutoff[0], "week": cutoff[1], "slate": row["slate"],
            "player_master_id": str(master_id), "prior_games": len(recent),
            "last_prior_game": list(recent_keys[0]) if recent_keys else None,
            "recent_carries": average([item["carries"] for item in recent]),
            "recent_rushing_yards": average([item["rushing_yards"] for item in recent]),
            "recent_rushing_tds": average([item["rushing_tds"] for item in recent]),
            "recent_passing_tds": average([item["passing_tds"] for item in recent]),
            "recent_team_rushing_td_share": numerator / denominator if denominator > 0 else None,
        })
    return {"captured_at": datetime.now(UTC).isoformat(), "source": "local raw_nfl_weekly_stat/player_alias, raw_nfl_schedule, starting_qb_evidence, curated_salary",
            "timestamp_timezone": "America/New_York", "time_safety": "Only games before each target season/week; starter evidence observed before scheduled kickoff",
            "salary_years": salary_years, "schedule": list(schedule.values()),
            "starter_evidence": starters, "qb_prior_features": prior_features,
            "feature_source_note": "Recent 3-game observed rates are pregame proxies, not model projections or goal-line usage"}


def percent(value: float | None) -> str:
    return "Unavailable" if value is None else f"{value:.1%}"


def markdown(report: dict) -> str:
    def interval(row: dict, field: str = "wilson_95") -> str:
        ci = row.get(field)
        return f"{percent(ci[0])}–{percent(ci[1])}" if ci else "Unavailable"

    def rate_table(title: str, rows: list[dict], denominator: str = "eligible_opportunities") -> list[str]:
        result = ["", f"## {title}", "", "| Group | Optimal CPT | Sample | Rate | 95% Wilson interval | Reliability |",
                  "|---|---:|---:|---:|---:|---|"]
        for row in rows:
            result.append(f"| {row['label']} | {row['optimal_count']} | {row[denominator]} | "
                          f"{percent(row.get('optimal_rate', row.get('optimal_game_share')))} | {interval(row)} | {row['reliability']} |")
        return result

    lines = ["# Historical Showdown Captain Optimality", "",
             f"**{report['slate_count']} unique legal actual-score games**; {len(report['duplicates_removed'])} duplicate removed, "
             f"{report['games_with_captain_ties']} tied-optimum game preserved.", "",
             "Games by season: " + ", ".join(f"{season}: {count}" for season, count in report["games_by_season"].items()) + ".",
             "DraftKings salary coverage: " + ", ".join(str(row["season"]) for row in report["salary_years"]) + "; no earlier salary slates are stored.",
             "Player actual-score source rows: " + ", ".join(f"{source} {count}" for source, count in report["actual_source_counts"].items()) + ".",
             report["actual_score_missingness_note"],
             "Excluded: " + "; ".join(f"{row['season']} W{row['week']} {row['slate']}: {row['reason']}"
                                       for row in report["excluded_games"]) + ".", "",
             "Position shares use one deterministic optimum per game. The QB opportunity tables include backups unless labeled starter-only.",
             "", "## Overall positions", "",
             "| Position | Optimal Captains | Games | Game share | Game-share 95% interval | Eligible opportunities | Opportunity rate | Reliability |",
             "|---|---:|---:|---:|---:|---:|---:|---|"]
    for row in report["positions"]:
        lines.append(f"| {row['label']} | {row['optimal_count']} | {report['slate_count']} | "
                     f"{percent(row['slate_optimal_share'])} | {interval(row, 'slate_share_wilson_95')} | "
                     f"{row['eligible_opportunities']} | {percent(row['optimal_rate'])} | {row['reliability']} |")
    starter = report["starter_identification"]
    lines += ["", "## Starter identification", "",
              f"{starter['identified']}/{starter['team_opportunities']} team-QB opportunities identified before kickoff; "
              f"{starter['complete_two_team_games']}/{report['slate_count']} games have both starters identified. "
              f"Methods: {starter['methods']}. {len(starter['ambiguous'])} team opportunities remain ambiguous.", "",
              starter["rule"], "",
              f"Postgame pass-leader mismatches, audit only: {len(starter['postgame_pass_leader_mismatches_for_audit_only'])}. "
              "Actual usage never selects the starter label.", "",
              f"Recent-carry tercile boundaries: {report['qb_archetype_thresholds_recent_carries'][0]:.2f} and "
              f"{report['qb_archetype_thresholds_recent_carries'][1]:.2f}. These describe volume; goal-line role is unverified."]
    lines += rate_table("All eligible QB archetypes", report["qb_archetypes"])
    lines += rate_table("Pregame-identified starter QB archetypes", report["starter_qb_archetypes"])
    game_rows = report["starter_qb_game_shares"]
    lines += ["", "## Starter QB game shares", "", "| Group | Optimal-CPT games | Games with group | Game share | 95% Wilson interval | Reliability |",
              "|---|---:|---:|---:|---:|---|"]
    for row in game_rows:
        lines.append(f"| {row['label']} | {row['optimal_count']} | {row['eligible_games']} | "
                     f"{percent(row['optimal_game_share'])} | {interval(row)} | {row['reliability']} |")
    bucket_titles = {"recent_carries": "Rushing-volume buckets", "recent_rushing_tds": "Prior rushing-TD buckets",
                     "favorite_status": "Favorite versus underdog", "team_implied_total": "Team implied total",
                     "qb_salary": "QB salary", "projected_mean": "QB projected mean",
                     "recent_rushing_yards": "Prior rushing yards", "passing_volume": "Prior pass volume",
                     "teammate_target_concentration": "Teammate target concentration"}
    for key, title in bucket_titles.items():
        lines += rate_table(f"All QB: {title}", report["qb_buckets"].get(key, []))
        lines += rate_table(f"Starter QB: {title}", report["starter_qb_buckets"].get(key, []))
    lines += ["", "## Goal-line evidence", "", report["goal_line_buckets"]["reason"], "",
              report["historical_feature_note"]]
    for population, key in (("All QB", "qb_statistical_validation"),
                            ("Starter QB", "starter_qb_statistical_validation")):
        validation = report[key]
        lines += ["", f"## Chronological validation: {population}", "",
                  f"{validation['status']}; train {validation['training_rows']} ({validation['training_optimal_qbs']} optimal), "
                  f"holdout {validation['test_rows']} ({validation['test_optimal_qbs']} optimal).", "",
                  "| Model | Holdout AUC | Brier | Log loss | Calibration error |",
                  "|---|---:|---:|---:|---:|"]
        for label, name in (("A base", "base"), ("B + carries", "with_recent_carries"),
                            ("C + prior TD proxy", "with_td_proxy"), ("D + archetype", "with_archetype"),
                            ("E full supported", "full_supported")):
            model = validation[name]
            lines.append(f"| {label} | {model['holdout_auc']:.3f} | {model['holdout_brier']:.4f} | "
                         f"{model['holdout_log_loss']:.4f} | {model['holdout_calibration_error']:.4f} |")
        lines += ["", "Calibration bins and standardized coefficients are in the JSON artifact. "
                  "These sparse estimates do not authorize a production prior."]
    lines += ["", "## Missing data and status", "",
              "Unavailable: " + ", ".join(report["unavailable_features"]) + ".",
              *[f"- **{feature}:** {reason}" for feature, reason in report["missing_data_report"].items()],
              "Actual historical field CPT ownership, tournament-winning Captains, and top-1% distributions are unavailable.",
              "The QB archetype prior remains **shadow-only**; live rankings and eligibility are unchanged.", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="artifacts/showdown-oracle-dataset.json")
    parser.add_argument("--output-json", default="docs/showdown_captain_optimality_2024_2026.json")
    parser.add_argument("--output-md", default="docs/showdown_captain_optimality_2024_2026.md")
    parser.add_argument("--dates-from-report", help="Reuse saved game dates when the schedule database is unavailable")
    parser.add_argument("--input-snapshot", default="docs/showdown_captain_historical_inputs_2024_2026.json")
    parser.add_argument("--refresh-inputs", action="store_true", help="Capture a new immutable-source read from the local database")
    args = parser.parse_args()
    dataset_path = ROOT / args.dataset
    raw = dataset_path.read_bytes()
    dataset = json.loads(raw)
    input_path = ROOT / args.input_snapshot
    if args.refresh_inputs:
        inputs = capture_historical_inputs(dataset)
        input_path.write_text(json.dumps(inputs, indent=2, sort_keys=True), encoding="utf-8")
    elif input_path.exists():
        inputs = json.loads(input_path.read_text(encoding="utf-8"))
    else:
        inputs = {}
    if args.dates_from_report and not inputs:
        existing = json.loads((ROOT / args.dates_from_report).read_text(encoding="utf-8"))
        dates = {(int(row["season"]), int(row["week"]), tuple(row["teams"])): row["game_date"]
                 for row in existing.get("slates", []) if row.get("game_date")}
    else:
        dates = {(int(row["season"]), int(row["week"]), tuple(row["teams"])): row["game_date"]
                 for row in inputs.get("schedule", []) if row.get("game_date")}
        if not dates:
            dates = schedule_dates()
    report = build_optimality_report(dataset, dates, historical_inputs=inputs)
    report["source_artifact"] = args.dataset
    report["source_sha256"] = hashlib.sha256(raw).hexdigest()
    report["historical_input_artifact"] = args.input_snapshot if inputs else None
    report["historical_input_sha256"] = hashlib.sha256(input_path.read_bytes()).hexdigest() if inputs and input_path.exists() else None
    json_path = ROOT / args.output_json
    md_path = ROOT / args.output_md
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(markdown(report), encoding="utf-8")
    print(json.dumps({"slates": report["slate_count"], "json": str(json_path),
                      "report": str(md_path), "prior": report["prior_application"]["status"]}))


if __name__ == "__main__":
    main()
