"""Pregame offensive-opportunity centrality, independent of DFS outputs.

Centrality uses only opportunity evidence. It deliberately excludes fantasy
points, projections, ceilings, salaries, ownership, and lineup information.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import LinearRegression

SKILL_POSITIONS = {"RB", "WR", "TE"}
FORMULATIONS = ("max_dimension", "max_plus_dual", "monotonic_fitted")
CORE_SCORE_GRID = (0.50, 0.60, 0.70, 0.80, 0.85, 0.90)
CORE_RANK_GRID = (1, 2, 3)
DUAL_SCORE_GRID = (0.35, 0.45, 0.55, 0.65, 0.75)


def _number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if np.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _weighted_available(inputs: list[tuple[str, float, Any]]) -> tuple[float | None, dict]:
    known = [(name, weight, float(np.clip(value, 0, 1)))
             for name, weight, raw in inputs
             if (value := _number(raw)) is not None]
    weight = sum(item[1] for item in known)
    score = sum(item_weight * value for _, item_weight, value in known) / weight if weight else None
    return score, {"available": {name: value for name, _, value in known},
                   "weights_used": {name: item_weight / weight for name, item_weight, _ in known} if weight else {},
                   "missing": [name for name, _, raw in inputs if _number(raw) is None]}


def _anchored_dimension(anchor_name: str, anchor: Any,
                        supports: list[tuple[str, float, Any]]) -> tuple[float | None, dict]:
    """Let volume share define centrality and participation modestly confirm it."""
    share = _number(anchor)
    support, evidence = _weighted_available(supports)
    if share is None:
        # Participation alone suggests involvement but cannot establish ownership
        # of rushing or receiving opportunity.
        score = 0.20 * support if support is not None else None
        method = "participation-only fallback capped at 20%"
    else:
        score = float(np.clip(share * (0.85 + 0.15 * support), 0, 1)) if support is not None else float(np.clip(share, 0, 1))
        method = "opportunity share anchored; participation confirms at 15%"
    evidence["anchor"] = {anchor_name: share}
    evidence["method"] = method
    return score, evidence


def blend_share(values: list[float]) -> dict:
    observed = [float(value) for value in values if _number(value) is not None]
    if not observed:
        return {"value": None, "baseline8": None, "recent3": None, "last": None,
                "trend": None, "weights": {}, "games": 0}
    baseline = float(np.mean(observed[-8:]))
    recent = float(np.mean(observed[-3:]))
    last = observed[-1]
    if len(observed) >= 8:
        weights = {"baseline8": 0.40, "recent3": 0.45, "last": 0.15}
    elif len(observed) >= 3:
        weights = {"baseline8": 0.25, "recent3": 0.60, "last": 0.15}
    else:
        weights = {"baseline8": 0.0, "recent3": 0.85, "last": 0.15}
    value = weights["baseline8"] * baseline + weights["recent3"] * recent + weights["last"] * last
    prior3 = float(np.mean(observed[-4:-1])) if len(observed) >= 2 else None
    return {"value": value, "baseline8": baseline, "recent3": recent, "last": last,
            "trend": last - prior3 if prior3 is not None else None,
            "weights": weights, "games": len(observed)}


def formulation_scores(receiving: float, rushing: float, fitted_model=None) -> dict[str, float | None]:
    receiving = max(0.0, float(receiving or 0.0))
    rushing = max(0.0, float(rushing or 0.0))
    maximum, minimum = max(receiving, rushing), min(receiving, rushing)
    scores = {"max_dimension": maximum,
              "max_plus_dual": min(1.0, maximum + 0.20 * minimum),
              "monotonic_fitted": None}
    if fitted_model is not None:
        features = pd.DataFrame([[receiving, rushing, minimum]],
                                columns=["receiving_centrality", "rushing_centrality", "dual"])
        scores["monotonic_fitted"] = float(np.clip(fitted_model.predict(features)[0], 0, 1))
    return scores


def role_class(score: float | None, receiving_raw: float | None = None,
               rushing_raw: float | None = None) -> str:
    if score is None:
        return "unavailable"
    receiving_raw = receiving_raw or 0.0
    rushing_raw = rushing_raw or 0.0
    substantial = receiving_raw >= 0.15 or rushing_raw >= 0.25
    dominant = receiving_raw >= 0.25 or rushing_raw >= 0.45 or (
        receiving_raw >= 0.15 and rushing_raw >= 0.15)
    return ("offensive centerpiece" if score >= 0.90 and dominant else
            "core offensive player" if score >= 0.70 and substantial else
            "meaningful secondary" if score >= 0.45 and (receiving_raw >= 0.08 or rushing_raw >= 0.12) else
            "complementary" if score >= 0.20 else "peripheral")


def historical_prediction_rows(weekly: pd.DataFrame) -> pd.DataFrame:
    """Create next-game predictions from each team's prior three rosters and usage."""
    data = weekly.copy()
    data["position"] = data["position"].fillna("").astype(str).str.upper()
    data = data.loc[data["position"].isin(SKILL_POSITIONS) & data["player_master_id"].notna()].copy()
    data["period"] = data["season"].astype(int) * 100 + data["week"].astype(int)
    for column in ("targets", "carries"):
        data[column] = pd.to_numeric(data[column], errors="coerce").fillna(0.0)
    team_games = {}
    for (team, period), group in data.groupby(["team", "period"]):
        target_total, carry_total = group["targets"].sum(), group["carries"].sum()
        observed = {}
        for player_id, player in group.groupby("player_master_id"):
            row = player.iloc[-1]
            observed[str(player_id)] = {"position": row["position"],
                "target_share": float(player["targets"].sum() / target_total) if target_total > 0 else 0.0,
                "carry_share": float(player["carries"].sum() / carry_total) if carry_total > 0 else 0.0,
                "targets": float(player["targets"].sum()), "carries": float(player["carries"].sum())}
        team_games[(team, int(period))] = observed
    rows = []
    for team in sorted(data["team"].dropna().unique()):
        periods = sorted(period for observed_team, period in team_games if observed_team == team)
        histories: dict[str, dict[str, list[float] | str]] = defaultdict(
            lambda: {"target_share": [], "carry_share": [], "position": ""})
        recent_rosters: list[set[str]] = []
        for period in periods:
            actual = team_games[(team, period)]
            eligible = set().union(*recent_rosters[-3:]) if recent_rosters else set()
            total_actual_targets = sum(item["targets"] for item in actual.values())
            total_actual_carries = sum(item["carries"] for item in actual.values())
            covered_targets = sum(actual.get(player_id, {}).get("targets", 0) for player_id in eligible)
            covered_carries = sum(actual.get(player_id, {}).get("carries", 0) for player_id in eligible)
            for player_id in sorted(eligible):
                history = histories[player_id]
                receiving = blend_share(history["target_share"])
                rushing = blend_share(history["carry_share"])
                if receiving["value"] is None and rushing["value"] is None:
                    continue
                actual_row = actual.get(player_id, {})
                actual_receiving = float(actual_row.get("target_share", 0))
                actual_rushing = float(actual_row.get("carry_share", 0))
                rows.append({"season": period // 100, "week": period % 100, "period": period,
                    "team": team, "player_id": player_id, "position": history["position"],
                    "receiving_centrality_raw": receiving["value"] or 0.0,
                    "rushing_centrality_raw": rushing["value"] or 0.0,
                    "target_blend": receiving, "carry_blend": rushing,
                    "actual_target_share": actual_receiving, "actual_carry_share": actual_rushing,
                    "actual_targets": actual_row.get("targets", 0),
                    "actual_carries": actual_row.get("carries", 0),
                    "team_target_coverage": covered_targets / total_actual_targets if total_actual_targets else None,
                    "team_carry_coverage": covered_carries / total_actual_carries if total_actual_carries else None})
            current_ids = set(actual)
            recent_rosters.append(current_ids)
            for player_id in sorted(set(histories) | current_ids):
                row = actual.get(player_id)
                if row is not None:
                    histories[player_id]["position"] = row["position"]
                    histories[player_id]["target_share"].append(row["target_share"])
                    histories[player_id]["carry_share"].append(row["carry_share"])
                else:
                    histories[player_id]["target_share"].append(0.0)
                    histories[player_id]["carry_share"].append(0.0)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    groups = frame.groupby(["period", "team"])
    for source, output in (("receiving_centrality_raw", "receiving_centrality"),
                           ("rushing_centrality_raw", "rushing_centrality"),
                           ("actual_target_share", "actual_receiving_normalized"),
                           ("actual_carry_share", "actual_rushing_normalized")):
        maximum = groups[source].transform("max")
        frame[output] = np.where(maximum > 0, frame[source] / maximum, 0.0)
    frame["actual_overall"] = frame[["actual_receiving_normalized", "actual_rushing_normalized"]].max(axis=1) + 0.20 * frame[["actual_receiving_normalized", "actual_rushing_normalized"]].min(axis=1)
    frame["max_dimension"] = frame[["receiving_centrality", "rushing_centrality"]].max(axis=1)
    frame["max_plus_dual"] = np.clip(
        frame["max_dimension"] + 0.20 * frame[["receiving_centrality", "rushing_centrality"]].min(axis=1), 0, 1)
    frame["monotonic_fitted"] = np.nan
    return frame


def attach_walk_forward_fitted(rows: pd.DataFrame, min_rows: int = 500) -> pd.DataFrame:
    output = rows.copy()
    output["monotonic_fitted"] = np.nan
    for period in sorted(output["period"].unique()):
        prior = output.loc[output["period"].lt(period)]
        current = output.loc[output["period"].eq(period)]
        if len(prior) < min_rows:
            continue
        model = LinearRegression(positive=True)
        features = prior[["receiving_centrality", "rushing_centrality"]].copy()
        features["dual"] = features.min(axis=1)
        model.fit(features, prior["actual_overall"])
        current_features = current[["receiving_centrality", "rushing_centrality"]].copy()
        current_features["dual"] = current_features.min(axis=1)
        output.loc[current.index, "monotonic_fitted"] = np.clip(model.predict(current_features), 0, 1)
    return output


def _spearman(groups, predicted, actual) -> dict:
    values = []
    for _, group in groups:
        if len(group) < 2 or group[actual].nunique() < 2 or group[predicted].nunique() < 2:
            continue
        correlation = spearmanr(group[predicted], group[actual]).statistic
        if np.isfinite(correlation):
            values.append(float(correlation))
    return {"groups": len(values), "mean": float(np.mean(values)) if values else None,
            "median": float(np.median(values)) if values else None}


def formulation_metrics(rows: pd.DataFrame, score: str) -> dict:
    frame = rows.dropna(subset=[score]).copy()
    recalls = {1: [], 2: [], 3: []}
    false_core, predicted_core = 0, 0
    receiving_top1, rushing_top1, dual_recognized, dual_count = [], [], 0, 0
    for _, group in frame.groupby(["period", "team"]):
        for k in recalls:
            count = min(k, len(group))
            predicted = set(group.nlargest(count, score)["player_id"])
            actual = set(group.nlargest(count, "actual_overall")["player_id"])
            recalls[k].append(len(predicted & actual) / count)
        if group["actual_target_share"].sum() > 0:
            receiving_top1.append(
                group.nlargest(1, "receiving_centrality").iloc[0]["player_id"]
                == group.nlargest(1, "actual_target_share").iloc[0]["player_id"])
        if group["actual_carry_share"].sum() > 0:
            rushing_top1.append(
                group.nlargest(1, "rushing_centrality").iloc[0]["player_id"]
                == group.nlargest(1, "actual_carry_share").iloc[0]["player_id"])
        actual_dual = group.loc[group["actual_target_share"].ge(0.15) & group["actual_carry_share"].ge(0.15)]
        dual_count += len(actual_dual)
        predicted_top3 = set(group.nlargest(min(3, len(group)), score)["player_id"])
        dual_recognized += sum(player_id in predicted_top3 for player_id in actual_dual["player_id"])
        core = group.loc[group[score].ge(0.70) & (
            group["receiving_centrality_raw"].ge(0.15)
            | group["rushing_centrality_raw"].ge(0.25))]
        predicted_core += len(core)
        false_core += int(core["actual_overall"].lt(0.45).sum())
    groups = frame.groupby(["period", "team"])
    by_position = {}
    for position, subset in frame.groupby("position"):
        by_position[position] = {
            "rows": len(subset),
            "receiving_rank": _spearman(subset.groupby(["period", "team"]), "receiving_centrality", "actual_target_share"),
            "rushing_rank": _spearman(subset.groupby(["period", "team"]), "rushing_centrality", "actual_carry_share"),
            "overall_rank": _spearman(subset.groupby(["period", "team"]), score, "actual_overall")}
    return {"rows": len(frame), "team_games": groups.ngroups,
        "receiving_spearman": _spearman(groups, "receiving_centrality", "actual_target_share"),
        "rushing_spearman": _spearman(groups, "rushing_centrality", "actual_carry_share"),
        "overall_spearman": _spearman(groups, score, "actual_overall"),
        "top_1_recall": float(np.mean(recalls[1])) if recalls[1] else None,
        "top_2_recall": float(np.mean(recalls[2])) if recalls[2] else None,
        "top_3_recall": float(np.mean(recalls[3])) if recalls[3] else None,
        "receiving_top_1_recall": float(np.mean(receiving_top1)) if receiving_top1 else None,
        "rushing_top_1_recall": float(np.mean(rushing_top1)) if rushing_top1 else None,
        "dual_threat_top_3_recall": dual_recognized / dual_count if dual_count else None,
        "actual_dual_threat_rows": dual_count,
        "false_core_rate": false_core / predicted_core if predicted_core else None,
        "predicted_core_rows": predicted_core,
        "target_coverage": float(frame.groupby(["period", "team"])["team_target_coverage"].first().dropna().mean()),
        "carry_coverage": float(frame.groupby(["period", "team"])["team_carry_coverage"].first().dropna().mean()),
        "by_position": by_position}


def _dimension_core_candidate(
    rows: pd.DataFrame,
    *,
    predicted: str,
    actual: str,
    threshold: float,
    rank_limit: int,
) -> dict[str, float | int]:
    """Evaluate a dimension rule against next-game team opportunity leaders."""
    top_1_hits = top_1_total = top_2_hits = top_2_total = 0
    predicted_total = true_positive = team_games = 0
    for _, group in rows.groupby(["period", "team"]):
        if group[actual].sum() <= 0:
            continue
        team_games += 1
        ranked = group.sort_values(
            [predicted, "player_id"], ascending=[False, True]
        ).copy()
        ranked["dimension_rank"] = np.arange(1, len(ranked) + 1)
        selected = set(
            ranked.loc[
                ranked[predicted].ge(threshold)
                & ranked["dimension_rank"].le(rank_limit),
                "player_id",
            ].astype(str)
        )
        actual_top_1 = set(group.nlargest(1, actual)["player_id"].astype(str))
        actual_top_2 = set(
            group.nlargest(min(2, len(group)), actual)["player_id"].astype(str)
        )
        top_1_hits += len(selected & actual_top_1)
        top_1_total += len(actual_top_1)
        top_2_hits += len(selected & actual_top_2)
        top_2_total += len(actual_top_2)
        predicted_total += len(selected)
        true_positive += len(selected & actual_top_2)
    top_1_recall = top_1_hits / top_1_total if top_1_total else 0.0
    top_2_recall = top_2_hits / top_2_total if top_2_total else 0.0
    precision = true_positive / predicted_total if predicted_total else 0.0
    false_core_rate = 1.0 - precision if predicted_total else 0.0
    objective = 0.40 * top_1_recall + 0.40 * top_2_recall + 0.20 * precision
    return {
        "threshold": threshold,
        "rank_limit": rank_limit,
        "team_games": team_games,
        "predicted_core_rows": predicted_total,
        "cores_per_team": predicted_total / team_games if team_games else 0.0,
        "top_1_recall": top_1_recall,
        "top_2_recall": top_2_recall,
        "precision_vs_top_2": precision,
        "false_core_rate": false_core_rate,
        "selection_objective": objective,
    }


def calibrate_dimension_core(
    rows: pd.DataFrame,
    *,
    predicted: str,
    actual: str,
) -> dict[str, Any]:
    """Select a transparent score/rank rule from chronological prediction rows."""
    candidates = [
        _dimension_core_candidate(
            rows,
            predicted=predicted,
            actual=actual,
            threshold=threshold,
            rank_limit=rank_limit,
        )
        for threshold in CORE_SCORE_GRID
        for rank_limit in CORE_RANK_GRID
    ]
    selected = max(
        candidates,
        key=lambda row: (
            row["selection_objective"],
            -row["false_core_rate"],
            row["threshold"],
            -row["rank_limit"],
        ),
    )
    return {
        "selected": selected,
        "candidates": sorted(
            candidates,
            key=lambda row: (-row["selection_objective"], row["false_core_rate"]),
        ),
        "objective": (
            "0.40 * next-game top-1 recall + 0.40 * next-game top-2 recall "
            "+ 0.20 * precision versus next-game top two"
        ),
    }


def _dual_core_candidate(
    rows: pd.DataFrame,
    *,
    receiving_threshold: float,
    rushing_threshold: float,
) -> dict[str, float | int]:
    predicted_total = actual_total = true_positive = team_games = 0
    for _, group in rows.groupby(["period", "team"]):
        team_games += 1
        predicted = group.loc[
            group["receiving_centrality"].ge(receiving_threshold)
            & group["rushing_centrality"].ge(rushing_threshold)
        ]
        actual = group.loc[
            group["actual_target_share"].ge(0.15)
            & group["actual_carry_share"].ge(0.15)
        ]
        predicted_ids = set(predicted["player_id"].astype(str))
        actual_ids = set(actual["player_id"].astype(str))
        predicted_total += len(predicted_ids)
        actual_total += len(actual_ids)
        true_positive += len(predicted_ids & actual_ids)
    precision = true_positive / predicted_total if predicted_total else 0.0
    recall = true_positive / actual_total if actual_total else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "receiving_threshold": receiving_threshold,
        "rushing_threshold": rushing_threshold,
        "team_games": team_games,
        "actual_dual_rows": actual_total,
        "predicted_core_rows": predicted_total,
        "precision": precision,
        "recall": recall,
        "false_core_rate": 1.0 - precision if predicted_total else 0.0,
        "selection_objective": f1,
    }


def calibrate_core_thresholds(rows: pd.DataFrame) -> dict[str, Any]:
    """Calibrate independent football core dimensions from next-game usage."""
    usable = rows.dropna(
        subset=[
            "receiving_centrality",
            "rushing_centrality",
            "actual_target_share",
            "actual_carry_share",
        ]
    ).copy()
    receiving = calibrate_dimension_core(
        usable,
        predicted="receiving_centrality",
        actual="actual_target_share",
    )
    rushing = calibrate_dimension_core(
        usable,
        predicted="rushing_centrality",
        actual="actual_carry_share",
    )
    overall_rows = usable.dropna(subset=["monotonic_fitted", "actual_overall"])
    overall = calibrate_dimension_core(
        overall_rows,
        predicted="monotonic_fitted",
        actual="actual_overall",
    )
    dual_candidates = [
        _dual_core_candidate(
            usable,
            receiving_threshold=receiving_threshold,
            rushing_threshold=rushing_threshold,
        )
        for receiving_threshold in DUAL_SCORE_GRID
        for rushing_threshold in DUAL_SCORE_GRID
    ]
    dual_selected = max(
        dual_candidates,
        key=lambda row: (
            row["selection_objective"],
            -row["false_core_rate"],
            row["receiving_threshold"] + row["rushing_threshold"],
        ),
    )
    return {
        "receiving": receiving,
        "rushing": rushing,
        "dual_threat": {
            "selected": dual_selected,
            "candidates": sorted(
                dual_candidates,
                key=lambda row: (-row["selection_objective"], row["false_core_rate"]),
            ),
            "actual_definition": "next-game target share >= 0.15 and carry share >= 0.15",
            "objective": "F1 precision/recall for next-game dual-threat usage",
        },
        "overall": overall,
        "membership": (
            "overall_core is the union of receiving_core, rushing_core, "
            "dual_threat_core, and calibrated overall-score core"
        ),
    }


def apply_core_membership(
    rows: list[dict],
    calibration: dict[str, Any],
) -> list[dict]:
    """Attach independent core flags and their union to current player rows."""
    output = [dict(row) for row in rows]
    for team in sorted({row["team"] for row in output}):
        members = [row for row in output if row["team"] == team]
        receiving_rank = {
            row["player_id"]: index + 1
            for index, row in enumerate(
                sorted(
                    members,
                    key=lambda item: (
                        -(item.get("receiving_centrality") or 0.0),
                        item["player_id"],
                    ),
                )
            )
        }
        rushing_rank = {
            row["player_id"]: index + 1
            for index, row in enumerate(
                sorted(
                    members,
                    key=lambda item: (
                        -(item.get("rushing_centrality") or 0.0),
                        item["player_id"],
                    ),
                )
            )
        }
        overall_rank = {
            row["player_id"]: index + 1
            for index, row in enumerate(
                sorted(
                    members,
                    key=lambda item: (
                        -(item.get("overall_centrality") or 0.0),
                        item["player_id"],
                    ),
                )
            )
        }
        receive_rule = calibration["receiving"]["selected"]
        rush_rule = calibration["rushing"]["selected"]
        overall_rule = calibration["overall"]["selected"]
        dual_rule = calibration["dual_threat"]["selected"]
        for row in members:
            row["receiving_rank"] = receiving_rank[row["player_id"]]
            row["rushing_rank"] = rushing_rank[row["player_id"]]
            row["overall_rank"] = overall_rank[row["player_id"]]
            row["receiving_core"] = bool(
                (row.get("receiving_centrality") or 0.0) >= receive_rule["threshold"]
                and row["receiving_rank"] <= receive_rule["rank_limit"]
            )
            row["rushing_core"] = bool(
                (row.get("rushing_centrality") or 0.0) >= rush_rule["threshold"]
                and row["rushing_rank"] <= rush_rule["rank_limit"]
            )
            row["dual_threat_core"] = bool(
                (row.get("receiving_centrality") or 0.0)
                >= dual_rule["receiving_threshold"]
                and (row.get("rushing_centrality") or 0.0)
                >= dual_rule["rushing_threshold"]
            )
            row["overall_score_core"] = bool(
                (row.get("overall_centrality") or 0.0) >= overall_rule["threshold"]
                and row["overall_rank"] <= overall_rule["rank_limit"]
            )
            row["overall_core"] = bool(
                row["receiving_core"]
                or row["rushing_core"]
                or row["dual_threat_core"]
                or row["overall_score_core"]
            )
            if row["dual_threat_core"] or (
                row["receiving_core"] and row["rushing_core"]
            ):
                classification = "offensive centerpiece"
            elif row["receiving_core"]:
                classification = "core receiving player"
            elif row["rushing_core"]:
                classification = "core rushing player"
            elif row["overall_score_core"]:
                classification = "core offensive player"
            elif (row.get("overall_centrality") or 0.0) >= 0.45:
                classification = "meaningful secondary"
            elif (row.get("overall_centrality") or 0.0) >= 0.20:
                classification = "complementary"
            else:
                classification = "peripheral"
            row["football_classification"] = classification
    return sorted(
        output,
        key=lambda row: (row["team"], -(row.get("overall_centrality") or -1.0)),
    )


def score_current_players(target: pd.DataFrame, formulation: str = "max_plus_dual",
                          fitted_model=None) -> list[dict]:
    """Score a current slate from pregame role evidence only."""
    skill = target.loc[target["position"].astype(str).str.upper().isin(SKILL_POSITIONS)].copy()
    team_column = "recent_team" if "recent_team" in skill else "team"
    output = []
    for team, players in skill.groupby(team_column):
        route_max = pd.to_numeric(players.get("pregame_expected_routes"), errors="coerce").max()
        for row in players.to_dict("records"):
            target_share = _number(row.get("pregame_effective_target_share"))
            if target_share is None:
                target_share = _number(row.get("target_share_mean_3"))
            carry_share = _number(row.get("pregame_effective_carry_share"))
            if carry_share is None:
                carry_share = _number(row.get("carry_share_mean_3"))
            snap = _number(row.get("snap_share_mean_3")) if row.get("snap_share_mean_3_available") is not False else None
            routes = _number(row.get("pregame_expected_routes"))
            route_index = routes / route_max if routes is not None and route_max and route_max > 0 else None
            red_zone = _number(row.get("pregame_red_zone_share"))
            goal_line = _number(row.get("pregame_goal_line_share"))
            receiving, receiving_evidence = _anchored_dimension(
                "target_share", target_share,
                [("snap_share", 0.60, snap), ("route_participation_index", 0.40, route_index)])
            rushing, rushing_evidence = _anchored_dimension(
                "carry_share", carry_share,
                [("snap_share", 0.60, snap),
                 ("red_zone_or_goal_line_share", 0.40, goal_line if goal_line is not None else red_zone)])
            evidence_count = (len(receiving_evidence["available"]) + len(rushing_evidence["available"])
                              + int(target_share is not None) + int(carry_share is not None))
            history = _number(row.get("player_games_history")) or 0
            confidence = ("high" if evidence_count >= 4 and history >= 3 else
                          "medium" if evidence_count >= 2 and history >= 2 else
                          "low" if evidence_count else "unavailable")
            output.append({"team": str(team), "player_id": str(row.get("player_id")),
                "player": row.get("player_display_name") or row.get("player_name"),
                "position": str(row.get("position")), "receiving_centrality_raw": receiving,
                "rushing_centrality_raw": rushing, "evidence_confidence": confidence,
                "recent_target_share": target_share, "recent_carry_share": carry_share,
                "snap_share": snap, "target_trend": _number(row.get("target_share_trend")),
                "carry_trend": _number(row.get("rush_share_trend")),
                "snap_trend": _number(row.get("snap_share_trend")),
                "receiving_evidence": receiving_evidence, "rushing_evidence": rushing_evidence,
                "formulation": formulation})
    for team in {row["team"] for row in output}:
        members = [row for row in output if row["team"] == team]
        receive_max = max((row["receiving_centrality_raw"] or 0) for row in members)
        rush_max = max((row["rushing_centrality_raw"] or 0) for row in members)
        for row in members:
            row["receiving_centrality"] = ((row["receiving_centrality_raw"] or 0) / receive_max
                                             if receive_max > 0 else 0.0)
            row["rushing_centrality"] = ((row["rushing_centrality_raw"] or 0) / rush_max
                                          if rush_max > 0 else 0.0)
            scores = formulation_scores(row["receiving_centrality"], row["rushing_centrality"], fitted_model)
            row["overall_centrality"] = scores.get(formulation)
            row["role_classification"] = role_class(
                row["overall_centrality"], row["receiving_centrality_raw"],
                row["rushing_centrality_raw"])
    return sorted(output, key=lambda row: (row["team"], -(row["overall_centrality"] or -1)))
