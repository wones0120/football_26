"""Pregame-safe descriptive Captain optimality evidence from saved Showdown oracles."""

from __future__ import annotations

from collections import Counter
from math import isfinite, sqrt
from typing import Any

import numpy as np
from sqlalchemy import text
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler


POSITIONS = ("QB", "RB", "WR", "TE", "DST", "K")
ARCHETYPES = ("Pocket-oriented", "Mobile", "High-rush / goal-line unverified")


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def _winner(row: dict) -> bool:
    return bool(row.get("selected_optimal_captain"))


def _wilson(successes: int, opportunities: int) -> list[float] | None:
    if opportunities <= 0:
        return None
    z = 1.96
    p = successes / opportunities
    denominator = 1 + z * z / opportunities
    center = (p + z * z / (2 * opportunities)) / denominator
    radius = z * sqrt((p * (1 - p) + z * z / (4 * opportunities)) / opportunities) / denominator
    return [max(0.0, center - radius), min(1.0, center + radius)]


def _rate(rows: list[dict], label: str) -> dict:
    wins = sum(_winner(row) for row in rows)
    n = len(rows)
    return {
        "label": label, "optimal_count": wins, "eligible_opportunities": n,
        "optimal_rate": wins / n if n else None,
        "wilson_95": _wilson(wins, n),
        "reliability": "limited" if n < 100 or wins < 10 else "moderate",
    }


def classify_qb_carries(carries: Any, thresholds: list[float]) -> str:
    value = _number(carries)
    if value is None:
        return "Unknown rushing role"
    if value <= thresholds[0]:
        return ARCHETYPES[0]
    if value <= thresholds[1]:
        return ARCHETYPES[1]
    return ARCHETYPES[2]


def _deduplicated_slates(dataset: dict) -> tuple[list[dict], list[dict], list[dict]]:
    selected: list[dict] = []
    duplicates: list[dict] = []
    seen: set[tuple] = set()
    for slate in sorted(dataset.get("slates", []), key=lambda row: (
        int(row["season"]), int(row["week"]), str(row["slate"])
    )):
        teams = tuple(sorted({str(player.get("team") or "") for player in slate["optimal_lineup"]}))
        key = (int(slate["season"]), int(slate["week"]), teams)
        if len(teams) != 2 or key in seen:
            duplicates.append({"season": key[0], "week": key[1], "slate": slate["slate"],
                               "teams": list(teams), "reason": "duplicate_or_invalid_matchup"})
            continue
        seen.add(key)
        selected.append(slate)
    selected_keys = {(row["season"], row["week"], row["slate"]) for row in selected}
    selected_captains = {
        (row["season"], row["week"], row["slate"]): row["optimal_lineup"][0]["player_id"]
        for row in selected
    }
    captain_rows = [
        {**row,
         "selected_optimal_captain": row["player_id"] == selected_captains[(row["season"], row["week"], row["slate"])],
         "co_optimal_captain": (regret := _number(row.get("captain_regret"))) is not None and abs(regret) < 1e-7}
        for row in dataset.get("forced_captains", [])
        if (row["season"], row["week"], row["slate"]) in selected_keys
        and row.get("forced_captain_feasible")
    ]
    return selected, captain_rows, duplicates


def _mark_pregame_starters(rows: list[dict], historical_inputs: dict) -> dict:
    """Identify a single QB per team from pregame evidence, leaving ambiguity visible."""
    evidence = {
        (int(row["season"]), int(row["week"]), str(row["slate"]), str(row["team"])): row
        for row in historical_inputs.get("starter_evidence", [])
        if str(row.get("status") or "").lower() not in {"out", "inactive", "ruled_out"}
    }
    grouped: dict[tuple, list[dict]] = {}
    for row in rows:
        if row["position"] == "QB":
            row["pregame_starter"] = False
            row["starter_evidence"] = "unverified"
            grouped.setdefault((row["season"], row["week"], row["slate"], row["team"]), []).append(row)
    ambiguous = []
    methods = Counter()
    pass_leader_mismatches = []
    for key, qbs in grouped.items():
        selected = None
        method = None
        explicit = evidence.get(key)
        if explicit:
            selected = next((row for row in qbs if str(row.get("player_master_id")) ==
                             str(explicit["player_master_id"])), None)
            if selected:
                method = f"pregame_{explicit.get('evidence_tier') or 'evidence'}"
        if selected is None:
            ranked = sorted(qbs, key=lambda row: (-float(row.get("flex_salary") or 0),
                                                 str(row.get("player_id"))))
            top = ranked[0]
            next_salary = float(ranked[1].get("flex_salary") or 0) if len(ranked) > 1 else 0.0
            attempts = _number(top.get("expected_pass_attempts"))
            if (float(top.get("flex_salary") or 0) - next_salary >= 1200
                    and attempts is not None and attempts >= 20
                    and not any((_number(other.get("expected_pass_attempts")) or 0) > attempts + 8
                                for other in ranked[1:])):
                selected, method = top, "salary_and_prior_pass_volume_inferred"
        if selected is None:
            ambiguous.append({"season": key[0], "week": key[1], "slate": key[2],
                              "team": key[3], "reason": "no pregame starter evidence or clear salary/prior-volume leader"})
            continue
        selected["pregame_starter"] = True
        selected["starter_evidence"] = method
        methods[method] += 1
        pass_leader = max(qbs, key=lambda row: _number(row.get("actual_pass_attempts")) or 0)
        if (pass_leader["player_id"] != selected["player_id"]
                and (_number(pass_leader.get("actual_pass_attempts")) or 0) >= 15):
            pass_leader_mismatches.append({"season": key[0], "week": key[1],
                                           "slate": key[2], "team": key[3],
                                           "pregame_pick": selected["player_name"],
                                           "postgame_pass_leader": pass_leader["player_name"]})
    return {"team_opportunities": len(grouped), "identified": sum(methods.values()),
            "methods": dict(methods), "ambiguous": ambiguous,
            "postgame_pass_leader_mismatches_for_audit_only": pass_leader_mismatches,
            "rule": "Use pre-kickoff identity evidence when present; otherwise require a $1,200 FLEX salary lead, at least 20 prior-three pass attempts, and no backup exceeding that prior volume by more than eight. Actual game usage is audit-only."}


def _qb_validation(rows: list[dict]) -> dict:
    """Chronological, diagnostic QB logistic comparison; never authorizes scoring alone."""
    train = [dict(row) for row in rows if int(row["season"]) == 2024]
    test = [dict(row) for row in rows if int(row["season"]) >= 2025]
    positives = sum(_winner(row) for row in train)
    if not train or not test or positives == 0 or positives == len(train):
        return {"status": "unavailable", "training_rows": len(train),
                "training_optimal_qbs": positives, "test_rows": len(test)}

    # Derive validation archetype boundaries from training opportunities only.
    # The descriptive full-sample archetypes below serve a different purpose.
    training_carries = sorted(value for row in train
                              if (value := _number(row.get("expected_carries"))) is not None)
    validation_thresholds = ([float(value) for value in np.quantile(training_carries, [1 / 3, 2 / 3])]
                             if training_carries else [0.0, 0.0])
    for row in (*train, *test):
        label = classify_qb_carries(row.get("expected_carries"), validation_thresholds)
        row["validation_archetype_mobile"] = float(label == ARCHETYPES[1])
        row["validation_archetype_high_rush"] = float(label == ARCHETYPES[2])
        row["validation_archetype_unknown"] = float(label == "Unknown rushing role")

    def fit(feature_names: tuple[str, ...]) -> dict:
        def matrix(data: list[dict]) -> np.ndarray:
            return np.asarray([[np.nan if (value := _number(row.get(name))) is None else value
                                for name in feature_names] for row in data], dtype=float)
        imputer = SimpleImputer(strategy="median")
        train_x = imputer.fit_transform(matrix(train))
        test_x = imputer.transform(matrix(test))
        scale = StandardScaler()
        train_x = scale.fit_transform(train_x)
        test_x = scale.transform(test_x)
        train_y = np.asarray([int(_winner(row)) for row in train])
        test_y = np.asarray([int(_winner(row)) for row in test])
        model = LogisticRegression(C=0.5, max_iter=500)
        model.fit(train_x, train_y)
        probabilities = model.predict_proba(test_x)[:, 1]
        calibration = []
        for lo, hi in ((0.0, 0.05), (0.05, 0.15), (0.15, 1.01)):
            indices = [index for index, value in enumerate(probabilities) if lo <= value < hi]
            calibration.append({"range": f"{lo:.2f}–{min(hi, 1.0):.2f}", "count": len(indices),
                                "predicted": float(np.mean(probabilities[indices])) if indices else None,
                                "observed": float(np.mean(test_y[indices])) if indices else None})
        calibration_error = sum(
            row["count"] * abs(row["predicted"] - row["observed"])
            for row in calibration if row["count"]
        ) / len(test)
        return {
            "features": list(feature_names),
            "standardized_coefficients": dict(zip(feature_names, [float(x) for x in model.coef_[0]])),
            "holdout_brier": float(brier_score_loss(test_y, probabilities)),
            "holdout_log_loss": float(log_loss(test_y, probabilities)),
            "holdout_auc": float(roc_auc_score(test_y, probabilities)) if len(set(test_y)) == 2 else None,
            "holdout_calibration_error": float(calibration_error), "calibration": calibration,
        }

    base_features = ("flex_salary", "projected_mean", "team_implied_total")
    base = fit(base_features)
    rushing = fit((*base_features, "expected_carries"))
    td_proxy = fit((*base_features, "expected_carries", "recent_rushing_tds", "recent_passing_tds"))
    archetype = fit((*base_features, "validation_archetype_mobile", "validation_archetype_high_rush",
                     "validation_archetype_unknown"))
    measured = fit((*base_features, "expected_carries", "recent_rushing_yards",
                    "recent_rushing_tds", "recent_passing_tds", "recent_team_rushing_td_share",
                    "expected_pass_attempts", "teammate_target_concentration"))
    return {
        "status": "exploratory_insufficient_training_events" if positives < 10 else "evaluated",
        "training_period": "2024", "holdout_period": "2025-2026 Week 2",
        "training_rows": len(train), "training_optimal_qbs": positives,
        "test_rows": len(test), "test_optimal_qbs": sum(_winner(row) for row in test),
        "validation_archetype_thresholds_recent_carries": validation_thresholds,
        "base": base, "with_recent_carries": rushing, "with_td_proxy": td_proxy,
        "with_archetype": archetype, "all_measured_features": measured,
        "full_supported": measured,
        "unavailable_comparison": "Base + actual goal-line/inside-5 role cannot be fitted because no pregame historical play-by-play feature exists",
        "interpretation": "Associations and held-out scores are not causal; the training event count is too small for a production archetype weight.",
    }


def build_optimality_report(dataset: dict, game_dates: dict[tuple, str] | None = None,
                            *, historical_inputs: dict | None = None) -> dict:
    slates, rows, duplicates = _deduplicated_slates(dataset)
    game_dates = game_dates or {}
    historical_inputs = historical_inputs or {}
    prior_features = {
        (int(row["season"]), int(row["week"]), str(row["slate"]), str(row["player_master_id"])): row
        for row in historical_inputs.get("qb_prior_features", [])
    }
    feature_fields = ("prior_games", "last_prior_game", "recent_carries", "recent_rushing_yards",
                      "recent_rushing_tds", "recent_passing_tds", "recent_team_rushing_td_share")
    for row in rows:
        if row["position"] != "QB":
            continue
        feature = prior_features.get((int(row["season"]), int(row["week"]), str(row["slate"]),
                                      str(row.get("player_master_id"))), {})
        if feature.get("last_prior_game") is not None and tuple(feature["last_prior_game"]) >= (
                int(row["season"]), int(row["week"])):
            raise ValueError("QB prior feature is not strictly before the historical slate")
        row.update({field: feature.get(field) for field in feature_fields})
    starter_coverage = _mark_pregame_starters(rows, historical_inputs)
    slate_details = []
    for slate in slates:
        players = slate["optimal_lineup"]
        teams = sorted({str(player.get("team") or "") for player in players})
        captain = players[0]
        captain_row = next((row for row in rows if row["season"] == slate["season"]
                            and row["week"] == slate["week"] and row["slate"] == slate["slate"]
                            and row["player_id"] == captain["player_id"]), None)
        game_rows = [row for row in rows if row["season"] == slate["season"]
                     and row["week"] == slate["week"] and row["slate"] == slate["slate"]]
        slate_details.append({
            "season": slate["season"], "week": slate["week"], "slate": slate["slate"],
            "game_date": game_dates.get((slate["season"], slate["week"], tuple(teams))),
            "teams": teams, "game_total": _number(captain_row.get("game_total")) if captain_row else None,
            "team_market": {team: {
                "spread": _number(next((row.get("team_spread") for row in game_rows if row["team"] == team), None)),
                "implied_total": _number(next((row.get("team_implied_total") for row in game_rows if row["team"] == team), None)),
            } for team in teams},
            "optimal_captain": captain["name"], "optimal_captain_id": captain["player_id"],
            "optimal_captain_position": captain["position"],
            "captain_salary": captain_row.get("captain_salary") if captain_row else None,
            "captain_actual_points": captain_row.get("actual_points") if captain_row else None,
            "optimal_lineup_score": slate["optimal_score"],
            "pregame_identified_starting_qbs": [
                {"player_id": row["player_id"], "name": row["player_name"], "team": row["team"],
                 "evidence": row["starter_evidence"]}
                for row in game_rows if row["position"] == "QB" and row["pregame_starter"]
            ],
            "co_optimal_captains": [
                {"player_id": row["player_id"], "name": row["player_name"], "position": row["position"]}
                for row in game_rows if row["co_optimal_captain"]
            ],
            "tournament_winning_captain": None, "top_one_percent_captain_distribution": None,
            "source_slate": slate["slate"],
        })

    positions = []
    for position in POSITIONS:
        subset = [row for row in rows if row["position"] == position]
        rate = _rate(subset, position)
        rate["slate_optimal_share"] = rate["optimal_count"] / len(slates) if slates else None
        rate["slate_share_wilson_95"] = _wilson(rate["optimal_count"], len(slates))
        positions.append(rate)
    qbs = [row for row in rows if row["position"] == "QB"]
    target_groups: dict[tuple, list[float]] = {}
    for row in rows:
        if row["position"] in {"WR", "TE"} and (targets := _number(row.get("expected_targets"))) is not None:
            key = (row["season"], row["week"], row["slate"], row["team"])
            target_groups.setdefault(key, []).append(targets)
    for row in qbs:
        targets = target_groups.get((row["season"], row["week"], row["slate"], row["team"]), [])
        row["teammate_target_concentration"] = (
            max(targets) / sum(targets) if len(targets) >= 2 and sum(targets) > 0 else None
        )
    known_carries = sorted(float(row["expected_carries"]) for row in qbs
                           if _number(row.get("expected_carries")) is not None)
    thresholds = [float(x) for x in np.quantile(known_carries, [1 / 3, 2 / 3])] if known_carries else [0.0, 0.0]
    for row in qbs:
        row["archetype"] = classify_qb_carries(row.get("expected_carries"), thresholds)
        row["archetype_mobile"] = float(row["archetype"] == ARCHETYPES[1])
        row["archetype_high_rush"] = float(row["archetype"] == ARCHETYPES[2])
        row["archetype_unknown"] = float(row["archetype"] == "Unknown rushing role")
    starter_qbs = [row for row in qbs if row["pregame_starter"]]
    archetype_labels = (*ARCHETYPES, "Unknown rushing role")
    archetypes = [_rate([row for row in qbs if row["archetype"] == label], label)
                  for label in archetype_labels]
    starter_archetypes = [_rate([row for row in starter_qbs if row["archetype"] == label], label)
                          for label in archetype_labels]

    def bucket(name: str, predicate, population: list[dict] | None = None) -> dict:
        return _rate([row for row in (qbs if population is None else population) if predicate(row)], name)

    rush_edges = (("0–2", 0, 2), ("2–4", 2, 4), ("4–6", 4, 6), ("6–8", 6, 8), ("8+", 8, float("inf")))
    rush_buckets = [bucket(name, lambda row, lo=lo, hi=hi:
                   (value := _number(row.get("expected_carries"))) is not None
                   and value >= lo and (value < hi if hi != float("inf") else True))
                    for name, lo, hi in rush_edges]
    rush_buckets.append(bucket("Unavailable", lambda row: _number(row.get("expected_carries")) is None))
    starter_rush_buckets = [bucket(name, lambda row, lo=lo, hi=hi:
                            (value := _number(row.get("expected_carries"))) is not None
                            and value >= lo and (value < hi if hi != float("inf") else True), starter_qbs)
                            for name, lo, hi in rush_edges]
    starter_rush_buckets.append(bucket("Unavailable", lambda row: _number(row.get("expected_carries")) is None,
                                      starter_qbs))
    favorite_buckets = [bucket("Favorite", lambda row: (v := _number(row.get("team_spread"))) is not None and v < 0),
                        bucket("Underdog/tied", lambda row: (v := _number(row.get("team_spread"))) is not None and v >= 0)]
    starter_favorite_buckets = [bucket("Favorite", lambda row: (v := _number(row.get("team_spread"))) is not None and v < 0,
                                       starter_qbs),
                                bucket("Underdog/tied", lambda row: (v := _number(row.get("team_spread"))) is not None and v >= 0,
                                       starter_qbs)]
    implied_values = [_number(row.get("team_implied_total")) for row in qbs]
    implied_values = [value for value in implied_values if value is not None]
    implied_edges = [float(x) for x in np.quantile(implied_values, [0.25, 0.5, 0.75])] if implied_values else []
    implied_buckets = []
    starter_implied_buckets = []
    if implied_edges:
        bounds = [-float("inf"), *implied_edges, float("inf")]
        for index in range(4):
            lo, hi = bounds[index:index + 2]
            implied_buckets.append(bucket(f"Q{index + 1}: {lo:g} to {hi:g}",
                lambda row, lo=lo, hi=hi: (v := _number(row.get("team_implied_total"))) is not None and lo <= v < hi))
            starter_implied_buckets.append(bucket(f"Q{index + 1}: {lo:g} to {hi:g}",
                lambda row, lo=lo, hi=hi: (v := _number(row.get("team_implied_total"))) is not None and lo <= v < hi,
                starter_qbs))
    def quartile_buckets(feature: str, population: list[dict] | None = None) -> list[dict]:
        values = [_number(row.get(feature)) for row in qbs]
        values = [value for value in values if value is not None]
        if not values:
            return []
        bounds = [-float("inf"), *[float(v) for v in np.quantile(values, [0.25, 0.5, 0.75])], float("inf")]
        return [bucket(f"Q{index + 1}: {bounds[index]:g} to {bounds[index + 1]:g}",
                       lambda row, lo=bounds[index], hi=bounds[index + 1]:
                       (v := _number(row.get(feature))) is not None and lo <= v < hi, population)
                for index in range(4)]
    def td_buckets(population: list[dict]) -> list[dict]:
        return [bucket("0 prior-three rush TD/game", lambda row: _number(row.get("recent_rushing_tds")) == 0,
                       population),
                bucket(">0 to 0.33 prior-three rush TD/game",
                       lambda row: (v := _number(row.get("recent_rushing_tds"))) is not None and 0 < v <= 1 / 3,
                       population),
                bucket(">0.33 prior-three rush TD/game",
                       lambda row: (v := _number(row.get("recent_rushing_tds"))) is not None and v > 1 / 3,
                       population),
                bucket("Unavailable", lambda row: _number(row.get("recent_rushing_tds")) is None, population)]

    def game_key(row: dict) -> tuple:
        return (row["season"], row["week"], row["slate"])

    starters_by_game: dict[tuple, list[dict]] = {}
    for row in starter_qbs:
        starters_by_game.setdefault(game_key(row), []).append(row)
    complete_games = {key: team_rows for key, team_rows in starters_by_game.items()
                      if len({row["team"] for row in team_rows}) == 2}
    starter_coverage["complete_two_team_games"] = len(complete_games)

    def game_share(label: str, predicate) -> dict:
        eligible_games = [team_rows for team_rows in complete_games.values()
                          if any(predicate(row) for row in team_rows)]
        wins = sum(any(_winner(row) and predicate(row) for row in team_rows)
                   for team_rows in eligible_games)
        return {"label": label, "optimal_count": wins, "eligible_games": len(eligible_games),
                "optimal_game_share": wins / len(eligible_games) if eligible_games else None,
                "wilson_95": _wilson(wins, len(eligible_games)),
                "reliability": "limited" if len(eligible_games) < 100 or wins < 10 else "moderate"}

    starter_game_shares = [
        game_share("Either identified starting QB", lambda row: True),
        game_share("Favorite starting QB", lambda row: (v := _number(row.get("team_spread"))) is not None and v < 0),
        game_share("Underdog/tied starting QB", lambda row: (v := _number(row.get("team_spread"))) is not None and v >= 0),
        *[game_share(f"{label} starting QB", lambda row, label=label: row["archetype"] == label)
          for label in archetype_labels],
    ]
    coverage = {name: {"observed": sum(_number(row.get(name)) is not None for row in qbs), "eligible_qbs": len(qbs)}
                for name in ("expected_carries", "expected_pass_attempts", "red_zone_share", "goal_line_share",
                             "team_implied_total", "flex_salary", "projected_mean", "teammate_target_concentration",
                             "recent_rushing_yards", "recent_rushing_tds", "recent_passing_tds",
                             "recent_team_rushing_td_share")}
    games_by_season = dict(sorted(Counter(int(row["season"]) for row in slates).items()))
    actual_source_counts = dict(sorted(Counter(str(row.get("actual_source") or "legacy_unspecified")
                                            for row in rows).items()))
    return {
        "method": "unrestricted actual-score DraftKings Showdown oracle; deduplicated by season/week/matchup",
        "source_generated_at": dataset.get("generated_at"),
        "source_system": dataset.get("source_system"),
        "slate_count": len(slates), "eligible_captain_opportunities": len(rows),
        "games_by_season": games_by_season,
        "actual_source_counts": actual_source_counts,
        "actual_score_missingness_note": "Oracle scoring assigns zero to salary rows absent from both matched actual-stat sources; this may mean inactivity or a source gap, so those zeros are not independently verified. The two-team usage completion gate excludes wholly unplayed games.",
        "salary_years": historical_inputs.get("salary_years", []),
        "excluded_games": dataset.get("skipped_slates", []),
        "latest_completed_period": (list(max((int(row["season"]), int(row["week"])) for row in slates))
                                    if slates else None),
        "duplicates_removed": duplicates,
        "games_with_captain_ties": sum(
            sum(row["co_optimal_captain"] for row in rows
                if (row["season"], row["week"], row["slate"]) ==
                (slate["season"], slate["week"], slate["slate"])) > 1
            for slate in slates
        ),
        "slates": slate_details,
        "positions": positions,
        "qb_archetype_thresholds_recent_carries": thresholds,
        "qb_archetypes": archetypes,
        "starter_qb_count": len(starter_qbs),
        "starter_identification": starter_coverage,
        "starter_qb_archetypes": starter_archetypes,
        "starter_qb_overall": _rate(starter_qbs, "Pregame-identified starting QBs"),
        "starter_qb_game_shares": starter_game_shares,
        "qb_buckets": {"recent_carries": rush_buckets, "favorite_status": favorite_buckets,
                       "team_implied_total": implied_buckets,
                       "passing_volume": quartile_buckets("expected_pass_attempts"),
                       "projected_mean": quartile_buckets("projected_mean"),
                       "qb_salary": quartile_buckets("flex_salary"),
                       "recent_rushing_tds": td_buckets(qbs),
                       "recent_rushing_yards": quartile_buckets("recent_rushing_yards"),
                       "teammate_target_concentration": quartile_buckets("teammate_target_concentration")},
        "starter_qb_buckets": {"recent_carries": starter_rush_buckets,
                               "favorite_status": starter_favorite_buckets,
                               "team_implied_total": starter_implied_buckets,
                               "passing_volume": quartile_buckets("expected_pass_attempts", starter_qbs),
                               "projected_mean": quartile_buckets("projected_mean", starter_qbs),
                               "qb_salary": quartile_buckets("flex_salary", starter_qbs),
                               "recent_rushing_tds": td_buckets(starter_qbs),
                               "recent_rushing_yards": quartile_buckets("recent_rushing_yards", starter_qbs),
                               "teammate_target_concentration": quartile_buckets("teammate_target_concentration", starter_qbs)},
        "goal_line_buckets": {"status": "unavailable", "reason": "No historical pregame red-zone/inside-5/design-run play-by-play features in the source snapshot"},
        "qb_opportunities": [{key: row.get(key) for key in (
            "season", "week", "slate", "player_id", "player_master_id", "player_name", "team",
            "pregame_starter", "starter_evidence", "archetype", "expected_carries", "recent_carries",
            "recent_rushing_yards", "recent_rushing_tds", "recent_passing_tds",
            "recent_team_rushing_td_share", "projected_mean", "flex_salary", "captain_salary",
            "team_implied_total", "team_spread", "game_total", "selected_optimal_captain",
            "co_optimal_captain", "last_prior_game")}
                             for row in qbs],
        "feature_coverage": coverage,
        "qb_statistical_validation": _qb_validation(qbs),
        "starter_qb_statistical_validation": _qb_validation(starter_qbs),
        "historical_cpt_ownership": {"status": "unavailable", "reason": "No matched historical actual field CPT ownership in the oracle dataset; saved ownership projections are not field outcomes"},
        "unavailable_features": ["model projected rushing yards", "model rushing TD expectation",
                                 "red-zone carries", "inside-10 carries", "inside-5 carries", "goal-line carry share",
                                 "passing TD expectation", "designed-run rate", "scramble rate"],
        "missing_data_report": {
            "model projected rushing yards": "No archived prelock rushing-yard component from the fitted projection model; prior-three observed yards are shown separately",
            "model rushing TD expectation": "No archived prelock rushing-TD component; prior-three observed TD rate is shown separately",
            "passing TD expectation": "No archived prelock passing-TD component; prior-three observed TD rate is shown separately",
            "red-zone carries": "No historical play-by-play location data in the local database",
            "inside-10 carries": "No historical play-by-play location data in the local database",
            "inside-5 carries": "No historical play-by-play location data in the local database",
            "goal-line carry share": "No historical play-by-play location data in the local database",
            "designed-run rate": "Weekly box scores do not distinguish designed runs from scrambles",
            "scramble rate": "Weekly box scores do not distinguish scrambles from designed runs",
        },
        "historical_feature_note": "Prior-three-game rushing yards/TDs and passing TDs are observed pregame proxies, not model projections. Goal-line/design/scramble roles remain unavailable.",
        "prior_application": {"status": "shadow_only", "archetype_multiplier": 1.0,
                              "reason": "Only three 2024 optimal-QB events train the chronological holdout; no reliable out-of-sample scoring lift established"},
        "full_optimizer_validation": {"status": "unavailable", "reason": "The saved oracle has actual-score forced-Captain solves but no archived prelock full candidate pools for a time-safe A/B/C portfolio replay"},
        "scope_note": "All-QB rates include backups. Starter-only rates use pre-kickoff identity evidence or a clearly separated salary/prior-volume inference; ambiguous teams are excluded. No actual game usage selects starters.",
    }


def current_qb_analysis(pool_rows: list[dict], report: dict, family_rows: list[dict] | None = None) -> list[dict]:
    families = {str(row.get("captain_name")): row for row in (family_rows or [])}
    archetypes = {row["label"]: row for row in report.get("qb_archetypes", [])}
    starter_archetypes = {row["label"]: row for row in report.get("starter_qb_archetypes", [])}
    buckets = report.get("qb_buckets", {}).get("recent_carries", [])
    starter_buckets = {row["label"]: row for row in report.get("starter_qb_buckets", {}).get("recent_carries", [])}
    td_buckets = {row["label"]: row for row in report.get("starter_qb_buckets", {}).get("recent_rushing_tds", [])}
    output = []
    for row in pool_rows:
        if str(row.get("position") or "").upper() != "QB":
            continue
        carries = _number(row.get("pregame_expected_carries"))
        source = "pregame_expected_carries"
        if carries is None:
            carries = _number(row.get("carries_mean_3"))
            source = "carries_mean_3" if carries is not None else "unavailable"
        archetype = classify_qb_carries(carries, report["qb_archetype_thresholds_recent_carries"])
        rush_bucket = next((bucket for bucket in buckets if bucket["label"] == "Unavailable" and carries is None
                            or carries is not None and bucket["label"] != "Unavailable" and
                            ((bucket["label"] == "8+" and carries >= 8) or
                             (bucket["label"] != "8+" and float(bucket["label"].split("–")[0]) <= carries < float(bucket["label"].split("–")[1])))), None)
        name = str(row.get("name") or row.get("player_display_name") or "")
        family = families.get(name, {})
        spread = _number(row.get("team_spread_line"))
        salary = _number(row.get("salary"))
        starter_group = starter_archetypes.get(archetype, {})
        recent_rush_tds = _number(row.get("rushing_tds_mean_3"))
        td_label = ("Unavailable" if recent_rush_tds is None else
                    "0 prior-three rush TD/game" if recent_rush_tds == 0 else
                    ">0 to 0.33 prior-three rush TD/game" if recent_rush_tds <= 1 / 3 else
                    ">0.33 prior-three rush TD/game")
        starter_rush_bucket = starter_buckets.get(rush_bucket["label"] if rush_bucket else "Unavailable", {})
        td_bucket = td_buckets.get(td_label, {})
        output.append({
            "qb": name, "team": row.get("player_team"), "archetype": archetype,
            "starter_status": "selected_starting_qb", "starter_evidence_tier": row.get("starter_qb_evidence_tier"),
            "starter_source": row.get("starter_qb_source"),
            "mean": _number(row.get("projection")), "p90": _number(row.get("p90")),
            "flex_salary": salary, "captain_salary": salary * 1.5 if salary is not None else None,
            "recent_carries": carries, "recent_carries_source": source,
            "projected_rushing_yards": _number(row.get("projected_rushing_yards")),
            "recent_rushing_yards": _number(row.get("rushing_yards_mean_3")),
            "rushing_td_expectation": _number(row.get("projected_rushing_tds")),
            "recent_rushing_tds": recent_rush_tds,
            "goal_line_role": _number(row.get("pregame_goal_line_share")),
            "red_zone_role": _number(row.get("pregame_red_zone_share")),
            "designed_run_rate": _number(row.get("designed_run_rate")),
            "scramble_rate": _number(row.get("scramble_rate")),
            "team_implied_total": _number(row.get("team_implied_total")),
            "team_spread": spread, "favorite_status": "favorite" if spread is not None and spread < 0 else "underdog/tied" if spread is not None else "unavailable",
            "historical_archetype_rate": archetypes.get(archetype, {}).get("optimal_rate"),
            "historical_archetype_count": archetypes.get(archetype, {}).get("optimal_count"),
            "historical_archetype_opportunities": archetypes.get(archetype, {}).get("eligible_opportunities"),
            "historical_starter_archetype_rate": starter_group.get("optimal_rate"),
            "historical_starter_archetype_count": starter_group.get("optimal_count"),
            "historical_starter_archetype_opportunities": starter_group.get("eligible_opportunities"),
            "historical_starter_reliability": starter_group.get("reliability"),
            "historical_rush_bucket": rush_bucket.get("label") if rush_bucket else None,
            "historical_rush_bucket_rate": rush_bucket.get("optimal_rate") if rush_bucket else None,
            "historical_starter_rush_bucket_rate": starter_rush_bucket.get("optimal_rate"),
            "historical_starter_rush_bucket_count": starter_rush_bucket.get("optimal_count"),
            "historical_starter_rush_bucket_opportunities": starter_rush_bucket.get("eligible_opportunities"),
            "historical_starter_td_bucket": td_label,
            "historical_starter_td_bucket_rate": td_bucket.get("optimal_rate"),
            "historical_starter_td_bucket_count": td_bucket.get("optimal_count"),
            "historical_starter_td_bucket_opportunities": td_bucket.get("eligible_opportunities"),
            "existing_position_prior_multiplier": _number(row.get("captain_objective_multiplier")),
            "archetype_prior_adjustment": 0.0,
            "prior_status": report["prior_application"]["status"],
            "best_family_rank": family.get("rank"), "best_family_selector": family.get("selector"),
            "captain_position_prior_contribution": family.get("captain_position_prior_contribution"),
            "best_family_mean": family.get("mean"), "best_family_p90": family.get("p90"),
            "selected": family.get("selected"), "family_reason": family.get("reason"),
        })
    return output


def load_current_qb_prior_features(engine, pool_rows: list[dict], *, season: int, week: int) -> dict[str, dict]:
    """Read only games strictly before this slate, joined by canonical identity."""
    master_ids = sorted({str(row.get("player_master_id") or row.get("player_id"))
                         for row in pool_rows if row.get("player_master_id") or row.get("player_id")})
    if not master_ids:
        return {}
    with engine.connect() as connection:
        stats = connection.execute(text("""
            SELECT a.player_master_id, s.season, s.week, s.raw_row_json
            FROM player_alias a JOIN raw_nfl_weekly_stat s ON s.player_id = a.source_key
            WHERE a.source_system = 'nflreadpy' AND a.player_master_id = ANY(:ids)
              AND (s.season < :season OR (s.season = :season AND s.week < :week))
              AND s.position = 'QB'
            ORDER BY s.raw_nfl_weekly_stat_id DESC
        """), {"ids": master_ids, "season": season, "week": week}).mappings()
        history: dict[str, dict[tuple[int, int], dict]] = {}
        for row in stats:
            payload = row["raw_row_json"] or {}
            if payload.get("season_type") not in (None, "REG"):
                continue
            history.setdefault(str(row["player_master_id"]), {}).setdefault(
                (int(row["season"]), int(row["week"])), payload
            )
    result = {}
    for master_id, games in history.items():
        recent_keys = sorted(games, reverse=True)[:3]
        recent = [games[key] for key in recent_keys]
        def average(field: str) -> float | None:
            values = [_number(row.get(field)) for row in recent]
            observed = [value for value in values if value is not None]
            return sum(observed) / len(observed) if observed else None
        result[master_id] = {"rushing_yards_mean_3": average("rushing_yards"),
                             "rushing_tds_mean_3": average("rushing_tds"),
                             "passing_tds_mean_3": average("passing_tds"),
                             "prior_games": len(recent),
                             "last_prior_game": list(recent_keys[0]) if recent_keys else None}
    return result


def add_shadow_qb_family_ranks(family_report: dict, historical_report: dict,
                               *, prior_strength: float) -> dict:
    """Re-rank saved candidates hypothetically; never alter the live selector."""
    metrics = family_report.get("ranked_metrics") or []
    starter = historical_report.get("starter_qb_overall") or {}
    starter_n = int(starter.get("eligible_opportunities") or 0)
    starter_wins = int(starter.get("optimal_count") or 0)
    if starter_n == 0 or not metrics:
        return {"status": "unavailable", "reason": "No starter sample or saved candidate metrics"}
    baseline = (starter_wins + 0.5) / (starter_n + 1.0)
    groups = {row["label"]: row for row in historical_report.get("starter_qb_archetypes", [])}
    qbs = {row["qb"]: row for row in historical_report.get("current_qbs", [])}
    strength = min(max(float(prior_strength), 0.0), 1.0)
    for row in metrics:
        qb = qbs.get(row.get("captain_name"))
        group = groups.get(qb.get("archetype")) if qb else None
        n = int(group.get("eligible_opportunities") or 0) if group else 0
        if n:
            smoothed = (int(group.get("optimal_count") or 0) + 0.5) / (n + 1.0)
            factor = 1.0 - strength + strength * (smoothed / baseline)
        else:
            factor = 1.0
        row["shadow_qb_cpt_factor"] = factor
        row["shadow_qb_cpt_adjustment"] = float(row.get("captain_objective_score") or 0) * (factor - 1.0)
        row["hypothetical_selector"] = float(row["selector"]) + row["shadow_qb_cpt_adjustment"]
    by_shadow = sorted(metrics, key=lambda row: (-row["hypothetical_selector"], row["rank"]))
    shadow_rank = {int(row["rank"]): index + 1 for index, row in enumerate(by_shadow)}
    for row in metrics:
        row["shadow_rank"] = shadow_rank[int(row["rank"])]
    for family in family_report.get("family_rows") or []:
        candidate = next((row for row in metrics if row["rank"] == family.get("rank")), None)
        if candidate:
            family.update({key: candidate[key] for key in (
                "shadow_qb_cpt_factor", "shadow_qb_cpt_adjustment", "hypothetical_selector", "shadow_rank")})
    return {"status": "diagnostic_unvalidated", "strength": strength,
            "formula": "Jeffreys-smoothed starter-archetype opportunity rate divided by smoothed all-starter rate; blend at existing Captain-prior strength; replace only the saved CPT objective contribution. Candidate re-rank only; portfolio is unchanged.",
            "sample_warning": "Starter labels include salary/prior-volume inference; small cells and no out-of-sample portfolio lift. Do not enable for selection."}
