"""Auditable, replaceable conditioning of Showdown player distributions.

These are discovery assumptions, not probabilities or a joint game simulation.
The interface returns a separate player pool per game condition so a future
simulation filter can replace this heuristic without changing portfolio selection.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd


METHOD_VERSION = "market_margin_role_conditioning_v1"
DEFAULT_DECISIVE_MARGIN = 14.0


@dataclass(frozen=True)
class GameScenario:
    scenario_id: str
    label: str
    winner: str | None
    margin_threshold: float
    market_total: float | None
    market_spread_by_team: dict[str, float]
    market_implied_by_team: dict[str, float]
    conditioned_implied_by_team: dict[str, float]
    market_source: str | None = None
    market_observed_at: str | None = None
    method_version: str = METHOD_VERSION

    def audit(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "label": self.label,
            "conditioned_winner": self.winner,
            "decisive_margin_threshold": self.margin_threshold,
            "market_total": self.market_total,
            "market_spread_by_team": dict(self.market_spread_by_team),
            "market_implied_by_team": dict(self.market_implied_by_team),
            "conditioned_implied_by_team": dict(self.conditioned_implied_by_team),
            "market_source": self.market_source,
            "market_observed_at": self.market_observed_at,
            "adjustment_method": self.method_version,
        }


def _market_value(frame: pd.DataFrame, team: str, column: str) -> float | None:
    if column not in frame:
        return None
    values = pd.to_numeric(
        frame.loc[frame["player_team"].astype(str).str.upper() == team, column],
        errors="coerce",
    ).dropna()
    values = values[values.map(math.isfinite)]
    return float(values.median()) if not values.empty else None


def define_game_scenarios(pool: pd.DataFrame, margin: float = DEFAULT_DECISIVE_MARGIN) -> list[GameScenario]:
    """Build baseline and two 14+ point conditions from cutoff-safe market lines.

    A missing/inconsistent market fails closed for decisive conditioning. The
    caller can still retain its unchanged baseline candidate generation.
    """
    if not math.isfinite(margin) or margin < 7 or margin > 35:
        raise ValueError("showdown_decisive_margin must be between 7 and 35")
    teams = sorted(pool["player_team"].dropna().astype(str).str.upper().unique())
    if len(teams) != 2:
        raise ValueError("Showdown game scenarios require exactly two teams")
    source = next((str(value) for value in pool.get("market_source_system", pd.Series(dtype="object")).dropna() if str(value).strip()), None)
    observed = next((str(value) for value in pool.get("market_observed_at", pd.Series(dtype="object")).dropna() if str(value).strip()), None)
    totals = {team: _market_value(pool, team, "game_total_line") for team in teams}
    spreads = {team: _market_value(pool, team, "team_spread_line") for team in teams}
    implied = {team: _market_value(pool, team, "team_implied_total") for team in teams}
    available_totals = [value for value in totals.values() if value is not None]
    total = sum(available_totals) / len(available_totals) if available_totals else None
    if total is not None:
        for team in teams:
            if implied[team] is None and spreads[team] is not None:
                implied[team] = (total - spreads[team]) / 2
    baseline = GameScenario(
        "baseline", "BASELINE / MARKET SCRIPT", None, margin, total,
        {team: value for team, value in spreads.items() if value is not None},
        {team: value for team, value in implied.items() if value is not None},
        {team: value for team, value in implied.items() if value is not None},
        source, observed,
    )
    if "market_context_point_in_time_safe" in pool:
        market_mask = pd.Series(False, index=pool.index)
        for field in ("game_total_line", "team_implied_total"):
            if field in pool:
                market_mask |= pd.to_numeric(pool[field], errors="coerce").notna()
        market_rows = pool.loc[market_mask]
        if market_rows["market_context_point_in_time_safe"].map(
            lambda value: str(value).strip().lower() not in {"true", "1"}
        ).any():
            return [baseline]
    if total is None or total <= margin or any(implied[team] is None or implied[team] <= 0 for team in teams):
        return [baseline]
    if len(available_totals) == 2 and abs(available_totals[0] - available_totals[1]) > 2:
        return [baseline]
    if abs(sum(implied.values()) - total) > 3:
        return [baseline]
    if any(
        spreads[team] is not None
        and abs(float(spreads[team]) + float(implied[team]) - float(implied[teams[1 - index]])) > 3
        for index, team in enumerate(teams)
    ):
        return [baseline]
    scenarios = [baseline]
    for index, winner in enumerate(teams):
        loser = teams[1 - index]
        # A fixed 14-point boundary is the least extreme outcome satisfying
        # the event. Keep a market favorite's already larger expected margin.
        target_margin = max(margin, float(implied[winner]) - float(implied[loser]))
        conditioned = {
            winner: (total + target_margin) / 2,
            loser: (total - target_margin) / 2,
        }
        scenarios.append(GameScenario(
            f"team_{'a' if index == 0 else 'b'}_decisive_win",
            f"{winner} DECISIVE WIN", winner, margin, total,
            dict(baseline.market_spread_by_team),
            dict(baseline.market_implied_by_team), conditioned,
            source, observed,
        ))
    return scenarios


def condition_player_pool(pool: pd.DataFrame, scenario: GameScenario) -> pd.DataFrame:
    """Shift mean and P90 through bounded scoring and role-volume factors.

    This is a deliberately conservative sensitivity model. Team scoring moves
    with the conditional implied total, while role-volume changes can run in
    the opposite direction. No lineup objective bonus or roster-count rule is
    introduced. The original distribution and every component are retained.
    """
    frame = pool.copy(deep=True)
    frame["baseline_projection"] = pd.to_numeric(frame["projection"], errors="coerce").fillna(0)
    frame["baseline_p90"] = pd.to_numeric(frame["p90"], errors="coerce").fillna(0)
    frame["projection"] = frame["baseline_projection"].astype(float)
    frame["p90"] = frame["baseline_p90"].astype(float)
    for field in ("team_implied_total", "team_spread_line", "game_total_line"):
        if field in frame:
            frame[f"baseline_{field}"] = frame[field]
            frame[field] = pd.to_numeric(frame[field], errors="coerce").astype(float)
    if "optimizer_context_ceiling_score" in frame:
        frame["optimizer_context_ceiling_score"] = pd.to_numeric(
            frame["optimizer_context_ceiling_score"], errors="coerce"
        ).fillna(0).astype(float)
        frame["baseline_optimizer_context_ceiling_score"] = frame["optimizer_context_ceiling_score"]
    conditioned_margin = (
        0.0 if scenario.winner is None else
        scenario.conditioned_implied_by_team[scenario.winner]
        - next(value for team, value in scenario.conditioned_implied_by_team.items() if team != scenario.winner)
    )
    adjustments = []
    for index, row in frame.iterrows():
        team = str(row.get("player_team") or "").upper()
        position = str(row.get("position") or "").upper()
        role = str(row.get("role_label") or row.get("depth_chart_role") or "").lower()
        receiving_rb = position == "RB" and any(term in role for term in ("receiving", "pass", "third"))
        winner = scenario.winner == team
        baseline_total = scenario.market_implied_by_team.get(team)
        conditioned_total = scenario.conditioned_implied_by_team.get(team)
        scoring_delta = (
            (conditioned_total / baseline_total - 1)
            if scenario.winner and baseline_total and conditioned_total is not None else 0.0
        )
        # Scoring response and volume response are distinct. In particular,
        # losing pass catchers may rise despite a lower team TD expectation.
        if scenario.winner is None:
            scoring_weight, volume_delta, reason = 0.0, 0.0, "market baseline"
        elif position in {"DST", "D", "DEF"}:
            scoring_weight, volume_delta = 0.15, 0.12 if winner else -0.12
            reason = "increased DST sack/turnover environment" if winner else "reduced DST scoring environment"
        elif position in {"K", "KICKER"}:
            scoring_weight, volume_delta = 0.35, 0.02 if winner else -0.06
            reason = "conditioned kicker scoring environment" if winner else "trailing-team fourth-down tendency"
        elif position == "QB":
            scoring_weight, volume_delta = 0.45, -0.07 if winner else 0.10
            reason = "reduced late-game winning-team passing" if winner else "losing-team pass-volume increase"
        elif position in {"WR", "TE"}:
            scoring_weight, volume_delta = 0.40, -0.06 if winner else 0.11
            reason = "reduced late-game winning-team passing" if winner else "losing-team pass-volume increase"
        elif position == "RB" and receiving_rb:
            scoring_weight, volume_delta = 0.40, 0.01 if winner else 0.08
            reason = "winning-team scoring/TD redistribution" if winner else "losing-team receiving-RB opportunity"
        elif position == "RB":
            scoring_weight, volume_delta = 0.45, 0.10 if winner else -0.13
            reason = "winning-team rush-volume increase" if winner else "reduced trailing-team RB rushing"
        else:
            scoring_weight, volume_delta, reason = 0.35, 0.0, "scoring/TD redistribution"
        scoring_component = max(-0.12, min(0.12, scoring_weight * scoring_delta))
        factor = max(0.78, min(1.22, 1 + scoring_component + volume_delta))
        baseline_mean = float(row["baseline_projection"])
        baseline_p90 = float(row["baseline_p90"])
        conditioned_mean = max(0.0, baseline_mean * factor)
        # Preserve the player's original spread ratio; conditional variance
        # cannot be inferred from a team margin alone.
        conditioned_p90 = max(conditioned_mean, baseline_p90 * factor)
        frame.at[index, "projection"] = conditioned_mean
        frame.at[index, "p90"] = conditioned_p90
        if scenario.winner and team in scenario.conditioned_implied_by_team:
            if "team_implied_total" in frame:
                frame.at[index, "team_implied_total"] = scenario.conditioned_implied_by_team[team]
            if "team_spread_line" in frame:
                frame.at[index, "team_spread_line"] = -conditioned_margin if team == scenario.winner else conditioned_margin
        if "optimizer_context_ceiling_score" in frame:
            frame.at[index, "optimizer_context_ceiling_score"] = (
                float(row["baseline_optimizer_context_ceiling_score"])
                + conditioned_p90 - baseline_p90
            )
        adjustments.append({
            "reason": reason, "scoring_component": scoring_component,
            "volume_component": volume_delta, "applied_multiplier": factor,
            "market_implied_total": baseline_total,
            "conditioned_implied_total": conditioned_total,
            "baseline_mean": baseline_mean, "scenario_mean": conditioned_mean,
            "baseline_p90": baseline_p90, "scenario_p90": conditioned_p90,
            "delta_mean": conditioned_mean - baseline_mean,
            "delta_p90": conditioned_p90 - baseline_p90,
        })
    frame["showdown_scenario_adjustment"] = adjustments
    frame["showdown_scenario_id"] = scenario.scenario_id
    return frame
