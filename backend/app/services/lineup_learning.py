from __future__ import annotations

import math
from itertools import combinations
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable

import numpy as np
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

try:
    from pulp import LpBinary, LpMaximize, LpProblem, LpStatus, LpVariable, PULP_CBC_CMD, lpSum, value

    HAS_PULP = True
except Exception:  # noqa: BLE001
    HAS_PULP = False

from ..models import (
    ActualTopLineup,
    ActualTopLineupPlayer,
    CuratedSalary,
    PlayerAlias,
    RawNflSchedule,
    RawNflWeeklyStat,
)
from ..schemas import (
    ActualTopLineupBuildRequest,
    ActualTopLineupBuildResponse,
    ActualTopLineupBuildSliceResponse,
    ActualTopLineupLearningRequest,
    ActualTopLineupLearningResponse,
    ActualTopLineupLearningSlateRowResponse,
    LineupLearningFeatureInsightRowResponse,
    LineupLearningRequest,
    LineupLearningResponse,
    LineupLearningSlateResultRowResponse,
    UltimateLineupExposureRowResponse,
    UltimateLineupPlayerRowResponse,
    UltimateLineupRequest,
    UltimateLineupResponse,
    UltimateLineupRowResponse,
)
from .matching import normalize_position
from .simulation import calculate_dk_points


DK_SALARY_CAP = 50000
FEATURE_NAMES = [
    "salary_used",
    "salary_left",
    "avg_salary",
    "qb_team_receivers",
    "qb_team_skill_players",
    "qb_opponent_players",
    "game_stack_size",
    "max_players_same_team",
    "unique_teams",
    "cheap_count",
    "value_count",
    "stud_count",
    "double_stack_flag",
    "bringback_flag",
    "lineup_projected_mean",
    "lineup_projected_p90",
    "qb_game_total_line",
    "qb_game_spread_abs",
    "qb_team_implied_total",
    "qb_opp_implied_total",
    "qb_has_vegas_line",
    "double_stack_x_total_line",
    "bringback_x_total_line",
    "game_stack_x_total_line",
    "double_stack_x_close_spread",
    "bringback_x_close_spread",
]

PATTERN_FEATURE_INDEX = {name: idx for idx, name in enumerate(FEATURE_NAMES)}
TOP_TARGET_PERCENTILE = 98.0
CEILING_TARGET_PERCENTILE = 90.0
BUST_TARGET_PERCENTILE = 35.0

TEAM_ALIASES = {
    "JAX": "JAC",
    "WSH": "WAS",
    "WFT": "WAS",
    "LA": "LAR",
    "STL": "LAR",
    "SD": "LAC",
    "OAK": "LV",
}


@dataclass
class PlayerPoolRow:
    uid: str
    name: str
    team: str | None
    opponent: str | None
    position: str
    salary: int
    actual_points: float
    projected_mean_points: float = 0.0
    projected_p90_points: float = 0.0
    game_total_line: float | None = None
    team_spread_line: float | None = None
    team_implied_total: float | None = None
    opponent_implied_total: float | None = None
    player_master_id: str | None = None
    source_player_key: str | None = None


@dataclass
class LogisticTargetModel:
    weights: np.ndarray
    bias: float
    mean: np.ndarray
    std: np.ndarray
    positive_rate: float
    training_rows: int
    has_signal: bool


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _sigmoid(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(values, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def _normalize_pool_position(raw_position: str | None) -> str | None:
    if raw_position is None:
        return None
    cleaned = raw_position.strip().upper()
    if cleaned in {"D/ST", "DST", "DEF", "D"}:
        return "DST"

    normalized = normalize_position(raw_position)
    if not normalized:
        return None
    if normalized in {"QB", "RB", "WR", "TE"}:
        return normalized
    if normalized in {"DST", "DEF"}:
        return "DST"
    return None


def _canonical_team(team: str | None) -> str | None:
    if team is None:
        return None
    cleaned = team.strip().upper()
    if not cleaned:
        return None
    return TEAM_ALIASES.get(cleaned, cleaned)


def _slice_ordinal(season: int, week: int) -> int:
    return (season * 25) + week


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return float(number)


def _lineup_satisfies_roster_rules(lineup: list[PlayerPoolRow]) -> bool:
    if len(lineup) != 9:
        return False
    if len({row.uid for row in lineup}) != 9:
        return False

    counts: dict[str, int] = defaultdict(int)
    for row in lineup:
        counts[row.position] += 1

    if counts.get("QB", 0) != 1:
        return False
    if counts.get("DST", 0) != 1:
        return False
    if counts.get("RB", 0) < 2:
        return False
    if counts.get("WR", 0) < 3:
        return False
    if counts.get("TE", 0) < 1:
        return False
    if counts.get("RB", 0) + counts.get("WR", 0) + counts.get("TE", 0) != 7:
        return False

    dst = next((row for row in lineup if row.position == "DST"), None)
    if dst is None:
        return False
    dst_team = dst.team
    dst_opponent = dst.opponent
    if dst_team is None and dst_opponent is None:
        return True

    for row in lineup:
        if row.position == "DST":
            continue
        # Do not roster offensive players against the selected defense.
        if dst_team and row.opponent and row.opponent == dst_team:
            return False
        if dst_opponent and row.team and row.team == dst_opponent:
            return False
    return True


def _points_allowed_bonus(points_allowed: float) -> float:
    if points_allowed <= 0:
        return 10.0
    if points_allowed <= 6:
        return 7.0
    if points_allowed <= 13:
        return 4.0
    if points_allowed <= 20:
        return 1.0
    if points_allowed <= 27:
        return 0.0
    if points_allowed <= 34:
        return -1.0
    return -4.0


class LineupLearningService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._game_context_cache: dict[tuple[int, int], dict[str, dict[str, float]]] = {}
        self._dst_actual_cache: dict[tuple[int, int], dict[str, float]] = {}
        self._dst_projection_cache: dict[tuple[int, int], dict[str, tuple[float, float]]] = {}
        self._player_projection_cache: dict[
            tuple[str, int, int, str],
            tuple[dict[str, tuple[float, float]], dict[str, tuple[float, float]]],
        ] = {}

    def _game_context_by_team(self, *, season: int, week: int) -> dict[str, dict[str, float]]:
        cache_key = (season, week)
        cached = self._game_context_cache.get(cache_key)
        if cached is not None:
            return cached

        rows = self.session.execute(
            select(RawNflSchedule).where(
                and_(
                    RawNflSchedule.season == season,
                    RawNflSchedule.week == week,
                )
            )
        ).scalars().all()

        context: dict[str, dict[str, float]] = {}
        for row in rows:
            payload = row.raw_row_json or {}
            home_team = _canonical_team(row.home_team or payload.get("home_team"))
            away_team = _canonical_team(row.away_team or payload.get("away_team"))
            if not home_team or not away_team:
                continue

            total_line = _safe_float(payload.get("total_line"))
            if total_line is None:
                total_line = _safe_float(payload.get("total"))
            spread_line = _safe_float(payload.get("spread_line"))

            home_implied: float | None = None
            away_implied: float | None = None
            if total_line is not None and spread_line is not None:
                # `spread_line` is home-team spread from nflverse schedules.
                home_implied = (total_line / 2.0) - (spread_line / 2.0)
                away_implied = (total_line / 2.0) + (spread_line / 2.0)

            home_ctx: dict[str, float] = {"has_vegas_line": 0.0}
            away_ctx: dict[str, float] = {"has_vegas_line": 0.0}
            if total_line is not None:
                home_ctx["game_total_line"] = total_line
                away_ctx["game_total_line"] = total_line
            if spread_line is not None:
                home_ctx["team_spread_line"] = spread_line
                away_ctx["team_spread_line"] = -spread_line
            if home_implied is not None and away_implied is not None:
                home_ctx["team_implied_total"] = home_implied
                home_ctx["opponent_implied_total"] = away_implied
                away_ctx["team_implied_total"] = away_implied
                away_ctx["opponent_implied_total"] = home_implied
            if total_line is not None and spread_line is not None:
                home_ctx["has_vegas_line"] = 1.0
                away_ctx["has_vegas_line"] = 1.0

            context[home_team] = home_ctx
            context[away_team] = away_ctx

        self._game_context_cache[cache_key] = context
        return context

    def _fetch_available_slate_slices(
        self,
        *,
        source_system: str,
        season_start: int,
        season_end: int,
        slate_filter: str | None,
    ) -> list[tuple[int, int, str]]:
        filters = [
            CuratedSalary.source_system == source_system,
            CuratedSalary.season >= season_start,
            CuratedSalary.season <= season_end,
        ]
        if slate_filter:
            filters.append(CuratedSalary.slate == slate_filter)

        rows = self.session.execute(
            select(CuratedSalary.season, CuratedSalary.week, CuratedSalary.slate)
            .where(and_(*filters))
            .group_by(CuratedSalary.season, CuratedSalary.week, CuratedSalary.slate)
            .order_by(CuratedSalary.season, CuratedSalary.week, CuratedSalary.slate)
        ).all()
        return [(int(season), int(week), str(slate)) for season, week, slate in rows]

    def _compute_dst_actual_points(self, *, season: int, week: int) -> dict[str, float]:
        cache_key = (season, week)
        cached = self._dst_actual_cache.get(cache_key)
        if cached is not None:
            return cached

        schedule_rows = self.session.execute(
            select(RawNflSchedule).where(
                and_(
                    RawNflSchedule.season == season,
                    RawNflSchedule.week == week,
                )
            )
        ).scalars().all()
        points_allowed_by_team: dict[str, float] = {}
        opponent_by_team: dict[str, str] = {}
        for row in schedule_rows:
            home_team = _canonical_team(row.home_team)
            away_team = _canonical_team(row.away_team)
            payload = row.raw_row_json or {}
            home_score = payload.get("home_score")
            away_score = payload.get("away_score")
            try:
                home_score_num = float(home_score)
                away_score_num = float(away_score)
            except (TypeError, ValueError):
                continue
            if home_team and away_team:
                points_allowed_by_team[home_team] = away_score_num
                points_allowed_by_team[away_team] = home_score_num
                opponent_by_team[home_team] = away_team
                opponent_by_team[away_team] = home_team

        offense_agg_rows = self.session.execute(
            select(
                RawNflWeeklyStat.team,
                RawNflWeeklyStat.raw_row_json,
            ).where(
                and_(
                    RawNflWeeklyStat.season == season,
                    RawNflWeeklyStat.week == week,
                )
            )
        ).all()

        sacks_allowed_by_team: dict[str, float] = defaultdict(float)
        interceptions_thrown_by_team: dict[str, float] = defaultdict(float)
        fumbles_lost_by_team: dict[str, float] = defaultdict(float)
        dst_tds_by_team: dict[str, float] = defaultdict(float)

        for team, payload in offense_agg_rows:
            team_key = _canonical_team(team)
            if not team_key:
                continue
            raw = payload or {}
            def num(key: str) -> float:
                value = raw.get(key)
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return 0.0

            sacks_allowed_by_team[team_key] += num("sacks_suffered")
            interceptions_thrown_by_team[team_key] += num("passing_interceptions")
            fumbles_lost_by_team[team_key] += (
                num("fumbles_lost")
                + num("rushing_fumbles_lost")
                + num("receiving_fumbles_lost")
                + num("sack_fumbles_lost")
            )
            # `def_tds` and `special_teams_tds` appear on player rows and can be aggregated by team.
            dst_tds_by_team[team_key] += (num("def_tds") + num("special_teams_tds"))

        dst_points: dict[str, float] = {}
        for defense_team, opponent_team in opponent_by_team.items():
            points_allowed = points_allowed_by_team.get(defense_team)
            if points_allowed is None:
                continue
            sacks = sacks_allowed_by_team.get(opponent_team, 0.0)
            interceptions = interceptions_thrown_by_team.get(opponent_team, 0.0)
            fumbles_lost = fumbles_lost_by_team.get(opponent_team, 0.0)
            dst_tds = dst_tds_by_team.get(defense_team, 0.0)
            total = (
                _points_allowed_bonus(points_allowed)
                + sacks
                + (2.0 * interceptions)
                + (2.0 * fumbles_lost)
                + (6.0 * dst_tds)
            )
            dst_points[defense_team] = max(total, -10.0)

        self._dst_actual_cache[cache_key] = dst_points
        return dst_points

    def _fetch_slate_player_pool(
        self,
        *,
        source_system: str,
        season: int,
        week: int,
        slate: str,
        projection_lookup: dict[str, tuple[float, float]] | None = None,
        dst_projection_lookup: dict[str, tuple[float, float]] | None = None,
    ) -> list[PlayerPoolRow]:
        salary_rows = self.session.execute(
            select(CuratedSalary).where(
                and_(
                    CuratedSalary.source_system == source_system,
                    CuratedSalary.season == season,
                    CuratedSalary.week == week,
                    CuratedSalary.slate == slate,
                )
            )
        ).scalars().all()
        if not salary_rows:
            return []

        dst_points_by_team = self._compute_dst_actual_points(season=season, week=week)
        game_context_by_team = self._game_context_by_team(season=season, week=week)

        actual_points_by_master: dict[str, float] = {}
        master_ids = sorted({row.player_master_id for row in salary_rows if row.player_master_id})
        if master_ids:
            alias_rows = self.session.execute(
                select(PlayerAlias.player_master_id, PlayerAlias.source_key).where(
                    and_(
                        PlayerAlias.source_system == "nflreadpy",
                        PlayerAlias.player_master_id.in_(master_ids),
                    )
                )
            ).all()
            player_id_to_masters: dict[str, set[str]] = defaultdict(set)
            for player_master_id, source_key in alias_rows:
                if source_key:
                    player_id_to_masters[source_key].add(player_master_id)
            tracked_player_ids = sorted(player_id_to_masters.keys())

            if tracked_player_ids:
                stats_rows = self.session.execute(
                    select(RawNflWeeklyStat).where(
                        and_(
                            RawNflWeeklyStat.season == season,
                            RawNflWeeklyStat.week == week,
                            RawNflWeeklyStat.player_id.in_(tracked_player_ids),
                        )
                    )
                ).scalars().all()

                for row in stats_rows:
                    if not row.player_id:
                        continue
                    points = calculate_dk_points(row.raw_row_json or {})
                    if not math.isfinite(points):
                        continue
                    for master_id in player_id_to_masters.get(row.player_id, set()):
                        actual_points_by_master[master_id] = max(
                            actual_points_by_master.get(master_id, 0.0),
                            points,
                        )

        pool: list[PlayerPoolRow] = []
        for row in salary_rows:
            normalized_position = _normalize_pool_position(row.position)
            if not normalized_position:
                continue
            salary_value = int(row.salary or 0)
            if salary_value <= 0:
                continue
            uid = row.player_master_id or row.source_player_key or f"{row.normalized_name}:{row.team}:{row.position}"
            if not uid:
                continue
            team_key = _canonical_team(row.team)
            opponent_key = _canonical_team(row.opponent)
            context = game_context_by_team.get(team_key or "", {})
            points = actual_points_by_master.get(row.player_master_id or "", 0.0)
            projected_mean = 0.0
            projected_p90 = 0.0
            key_candidates = [row.player_master_id, row.source_player_key]
            for key in key_candidates:
                if not key or projection_lookup is None:
                    continue
                if key in projection_lookup:
                    projected_mean, projected_p90 = projection_lookup[key]
                    break
            if normalized_position == "DST":
                points = dst_points_by_team.get(team_key or "", 0.0)
                if dst_projection_lookup and team_key and team_key in dst_projection_lookup:
                    projected_mean, projected_p90 = dst_projection_lookup[team_key]
            pool.append(
                PlayerPoolRow(
                    uid=uid,
                    name=row.player_name,
                    team=team_key,
                    opponent=opponent_key,
                    position=normalized_position,
                    salary=salary_value,
                    actual_points=float(points),
                    projected_mean_points=float(projected_mean),
                    projected_p90_points=float(projected_p90),
                    game_total_line=_safe_float(context.get("game_total_line")),
                    team_spread_line=_safe_float(context.get("team_spread_line")),
                    team_implied_total=_safe_float(context.get("team_implied_total")),
                    opponent_implied_total=_safe_float(context.get("opponent_implied_total")),
                    player_master_id=row.player_master_id,
                    source_player_key=row.source_player_key,
                )
            )

        # Keep one entry per player uid, retaining the highest salary variant if duplicates exist.
        deduped: dict[str, PlayerPoolRow] = {}
        for row in pool:
            existing = deduped.get(row.uid)
            if existing is None or row.salary > existing.salary:
                deduped[row.uid] = row
        return list(deduped.values())

    def _sample_weighted_unique(
        self,
        rows: list[PlayerPoolRow],
        count: int,
        selected: set[str],
        rng: np.random.Generator,
    ) -> list[PlayerPoolRow] | None:
        eligible = [row for row in rows if row.uid not in selected]
        if len(eligible) < count:
            return None
        weights = np.asarray([max(1000, row.salary) ** 0.6 for row in eligible], dtype=float)
        weights = weights / np.sum(weights)
        idxs = rng.choice(len(eligible), size=count, replace=False, p=weights)
        return [eligible[int(idx)] for idx in idxs]

    def _lineup_features(self, lineup: list[PlayerPoolRow]) -> np.ndarray:
        qb = next(row for row in lineup if row.position == "QB")
        offense = [row for row in lineup if row.position != "DST"]
        skill = [row for row in offense if row.position != "QB"]
        salary_used = float(sum(row.salary for row in lineup))
        salary_left = float(DK_SALARY_CAP - salary_used)
        avg_salary = salary_used / len(lineup)
        lineup_projected_mean = float(sum(row.projected_mean_points for row in lineup))
        lineup_projected_p90 = float(sum(row.projected_p90_points for row in lineup))
        qb_team = qb.team
        qb_opp = qb.opponent
        qb_team_skill = [row for row in skill if qb_team and row.team == qb_team]
        qb_team_receivers = [row for row in qb_team_skill if row.position in {"WR", "TE"}]
        qb_opp_players = [row for row in skill if qb_opp and row.team == qb_opp]
        game_stack_size = sum(
            1
            for row in offense
            if (qb_team and row.team == qb_team) or (qb_opp and row.team == qb_opp)
        )
        team_counts: dict[str, int] = defaultdict(int)
        for row in offense:
            if row.team:
                team_counts[row.team] += 1
        max_team = float(max(team_counts.values())) if team_counts else 0.0
        unique_teams = float(len(team_counts))
        cheap_count = float(sum(1 for row in lineup if row.salary <= 4500))
        value_count = float(sum(1 for row in lineup if 4500 < row.salary <= 6500))
        stud_count = float(sum(1 for row in lineup if row.salary >= 7000))
        double_stack = 1.0 if len(qb_team_receivers) >= 2 else 0.0
        bringback = 1.0 if len(qb_opp_players) >= 1 else 0.0
        qb_total_line = float(qb.game_total_line or 0.0)
        qb_spread_abs = float(abs(qb.team_spread_line or 0.0))
        qb_team_implied_total = float(qb.team_implied_total or 0.0)
        qb_opp_implied_total = float(qb.opponent_implied_total or 0.0)
        qb_has_vegas_line = 1.0 if qb.game_total_line is not None and qb.team_spread_line is not None else 0.0
        close_spread_strength = 1.0 / (1.0 + qb_spread_abs)

        return np.asarray(
            [
                salary_used,
                salary_left,
                avg_salary,
                float(len(qb_team_receivers)),
                float(len(qb_team_skill)),
                float(len(qb_opp_players)),
                float(game_stack_size),
                max_team,
                unique_teams,
                cheap_count,
                value_count,
                stud_count,
                double_stack,
                bringback,
                lineup_projected_mean,
                lineup_projected_p90,
                qb_total_line,
                qb_spread_abs,
                qb_team_implied_total,
                qb_opp_implied_total,
                qb_has_vegas_line,
                double_stack * qb_total_line,
                bringback * qb_total_line,
                float(game_stack_size) * qb_total_line,
                double_stack * close_spread_strength,
                bringback * close_spread_strength,
            ],
            dtype=float,
        )

    def _qb_game_stack_archetype(self, lineup: list[PlayerPoolRow]) -> tuple[str, str | None]:
        qb = next((row for row in lineup if row.position == "QB"), None)
        if qb is None:
            return "unknown", None
        skill = [row for row in lineup if row.position in {"RB", "WR", "TE"}]
        qb_team_receivers = sum(
            1 for row in skill if qb.team and row.team == qb.team and row.position in {"WR", "TE"}
        )
        bringback = 1 if any(qb.opponent and row.team == qb.opponent for row in skill) else 0
        if qb_team_receivers >= 2 and bringback:
            archetype = "double_with_bringback"
        elif qb_team_receivers >= 2:
            archetype = "double_no_bringback"
        elif qb_team_receivers == 1 and bringback:
            archetype = "single_with_bringback"
        elif qb_team_receivers == 1:
            archetype = "single_no_bringback"
        else:
            archetype = "naked_qb"
        if qb.team and qb.opponent:
            matchup_key = "@".join(sorted([qb.team, qb.opponent]))
        else:
            matchup_key = None
        return archetype, matchup_key

    def _summarize_matchup_stack_rules(
        self,
        *,
        candidate_lineups: list[list[PlayerPoolRow]],
        ranking_scores: np.ndarray,
    ) -> list[str]:
        by_matchup: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for idx, lineup in enumerate(candidate_lineups):
            archetype, matchup_key = self._qb_game_stack_archetype(lineup)
            if matchup_key is None:
                continue
            by_matchup[matchup_key][archetype].append(float(ranking_scores[idx]))

        min_samples = max(40, len(candidate_lineups) // 2000)
        rules: list[tuple[str, str, float, int]] = []
        for matchup_key, archetype_map in by_matchup.items():
            best_name: str | None = None
            best_mean = -1.0
            best_n = 0
            for archetype, values in archetype_map.items():
                n = len(values)
                if n < min_samples:
                    continue
                mean_score = float(np.mean(values))
                if mean_score > best_mean:
                    best_name = archetype
                    best_mean = mean_score
                    best_n = n
            if best_name is not None:
                rules.append((matchup_key, best_name, best_mean, best_n))

        rules.sort(key=lambda row: row[2], reverse=True)
        summary: list[str] = []
        for matchup_key, archetype, mean_score, sample_n in rules[:8]:
            summary.append(
                f"Matchup stack rule ({matchup_key}): {archetype} (learned score {mean_score:.4f}, n={sample_n})."
            )
        return summary

    def _player_conflicts_with_dst(self, player: PlayerPoolRow, dst: PlayerPoolRow) -> bool:
        if player.position == "DST":
            return False
        if dst.team and player.opponent and player.opponent == dst.team:
            return True
        if dst.opponent and player.team and player.team == dst.opponent:
            return True
        return False

    def _pareto_filter_players(self, players: list[PlayerPoolRow]) -> list[PlayerPoolRow]:
        if not players:
            return []
        ordered = sorted(players, key=lambda row: (int(row.salary), -float(row.actual_points)))
        kept: list[PlayerPoolRow] = []
        best_points = -1e18
        for row in ordered:
            points = float(row.actual_points)
            if points > (best_points + 1e-9):
                kept.append(row)
                best_points = max(best_points, points)
        return kept

    def _position_dp_exact(
        self,
        *,
        players: list[PlayerPoolRow],
        max_pick: int,
        budget_units: int,
        salary_step: int,
    ) -> tuple[list[list[float]], list[list[tuple[PlayerPoolRow, ...] | None]]]:
        neg_inf = -1e18
        points: list[list[float]] = [
            [neg_inf for _ in range(budget_units + 1)]
            for _ in range(max_pick + 1)
        ]
        choices: list[list[tuple[PlayerPoolRow, ...] | None]] = [
            [None for _ in range(budget_units + 1)]
            for _ in range(max_pick + 1)
        ]
        points[0][0] = 0.0
        choices[0][0] = ()

        for player in players:
            cost = int(player.salary // salary_step)
            gain = float(player.actual_points)
            if cost < 0 or cost > budget_units:
                continue
            for pick_count in range(max_pick - 1, -1, -1):
                cur_points_row = points[pick_count]
                nxt_points_row = points[pick_count + 1]
                cur_choice_row = choices[pick_count]
                nxt_choice_row = choices[pick_count + 1]
                for salary_units in range(budget_units - cost, -1, -1):
                    base = cur_points_row[salary_units]
                    if base <= neg_inf / 2:
                        continue
                    base_choice = cur_choice_row[salary_units]
                    if base_choice is None:
                        continue
                    next_salary = salary_units + cost
                    next_points = base + gain
                    if next_points > nxt_points_row[next_salary]:
                        nxt_points_row[next_salary] = next_points
                        nxt_choice_row[next_salary] = base_choice + (player,)

        return points, choices

    def optimize_actual_lineup(
        self,
        *,
        players: list[PlayerPoolRow],
    ) -> tuple[list[PlayerPoolRow], float, int] | None:
        if not players:
            return None

        if HAS_PULP:
            variables: dict[int, LpVariable] = {
                idx: LpVariable(f"p_{idx}", lowBound=0, upBound=1, cat=LpBinary)
                for idx in range(len(players))
            }
            model = LpProblem("optimal_actual_lineup", LpMaximize)
            model += lpSum(
                float(players[idx].actual_points) * variables[idx]
                for idx in range(len(players))
            )

            qb_idx = [idx for idx, row in enumerate(players) if row.position == "QB"]
            rb_idx = [idx for idx, row in enumerate(players) if row.position == "RB"]
            wr_idx = [idx for idx, row in enumerate(players) if row.position == "WR"]
            te_idx = [idx for idx, row in enumerate(players) if row.position == "TE"]
            dst_idx = [idx for idx, row in enumerate(players) if row.position == "DST"]
            skill_idx = rb_idx + wr_idx + te_idx
            offense_idx = qb_idx + skill_idx

            if not qb_idx or len(rb_idx) < 2 or len(wr_idx) < 3 or not te_idx or not dst_idx:
                return None

            model += lpSum(variables[idx] for idx in qb_idx) == 1
            model += lpSum(variables[idx] for idx in dst_idx) == 1
            model += lpSum(variables[idx] for idx in rb_idx) >= 2
            model += lpSum(variables[idx] for idx in wr_idx) >= 3
            model += lpSum(variables[idx] for idx in te_idx) >= 1
            model += lpSum(variables[idx] for idx in skill_idx) == 7
            model += lpSum(variables[idx] for idx in range(len(players))) == 9
            model += lpSum(int(players[idx].salary) * variables[idx] for idx in range(len(players))) <= DK_SALARY_CAP

            for offense_i in offense_idx:
                offense_player = players[offense_i]
                for dst_i in dst_idx:
                    dst_player = players[dst_i]
                    if self._player_conflicts_with_dst(offense_player, dst_player):
                        model += variables[offense_i] + variables[dst_i] <= 1

            status = model.solve(PULP_CBC_CMD(msg=False))
            status_name = LpStatus.get(status, "")
            if status_name in {"Optimal", "Integer Feasible"}:
                lineup = [
                    players[idx]
                    for idx in range(len(players))
                    if value(variables[idx]) is not None and value(variables[idx]) > 0.5
                ]
                if len(lineup) == 9 and _lineup_satisfies_roster_rules(lineup):
                    points = float(sum(float(row.actual_points) for row in lineup))
                    salary = int(sum(int(row.salary) for row in lineup))
                    return lineup, points, salary

        return self._optimize_actual_lineup_dp(players=players)

    def _optimize_actual_lineup_dp(
        self,
        *,
        players: list[PlayerPoolRow],
    ) -> tuple[list[PlayerPoolRow], float, int] | None:
        if not players:
            return None

        salaries = [int(row.salary) for row in players if int(row.salary) > 0]
        if not salaries:
            return None
        salary_step = 0
        for salary in salaries:
            salary_step = salary if salary_step == 0 else math.gcd(salary_step, salary)
        if salary_step <= 0:
            salary_step = 1
        cap_units = DK_SALARY_CAP // salary_step

        dst_pool = [row for row in players if row.position == "DST"]
        if not dst_pool:
            return None

        best_lineup: list[PlayerPoolRow] | None = None
        best_points = -1e18
        best_salary_used = 0

        for dst in dst_pool:
            dst_cost = int(dst.salary // salary_step)
            if dst_cost > cap_units:
                continue
            remaining_after_dst = cap_units - dst_cost

            qb_pool = [
                row for row in players
                if row.position == "QB" and not self._player_conflicts_with_dst(row, dst)
            ]
            rb_pool = [
                row for row in players
                if row.position == "RB" and not self._player_conflicts_with_dst(row, dst)
            ]
            wr_pool = [
                row for row in players
                if row.position == "WR" and not self._player_conflicts_with_dst(row, dst)
            ]
            te_pool = [
                row for row in players
                if row.position == "TE" and not self._player_conflicts_with_dst(row, dst)
            ]
            if len(qb_pool) < 1 or len(rb_pool) < 2 or len(wr_pool) < 3 or len(te_pool) < 1:
                continue

            rb_pool = self._pareto_filter_players(rb_pool)
            wr_pool = self._pareto_filter_players(wr_pool)
            te_pool = self._pareto_filter_players(te_pool)
            if len(rb_pool) < 2 or len(wr_pool) < 3 or len(te_pool) < 1:
                continue

            rb_points, rb_choices = self._position_dp_exact(
                players=rb_pool,
                max_pick=3,
                budget_units=remaining_after_dst,
                salary_step=salary_step,
            )
            wr_points, wr_choices = self._position_dp_exact(
                players=wr_pool,
                max_pick=4,
                budget_units=remaining_after_dst,
                salary_step=salary_step,
            )
            te_points, te_choices = self._position_dp_exact(
                players=te_pool,
                max_pick=2,
                budget_units=remaining_after_dst,
                salary_step=salary_step,
            )

            skill_exact_points = [-1e18 for _ in range(remaining_after_dst + 1)]
            skill_exact_choices: list[tuple[PlayerPoolRow, ...] | None] = [None for _ in range(remaining_after_dst + 1)]
            structures = [(2, 3, 2), (2, 4, 1), (3, 3, 1)]
            for rb_need, wr_need, te_need in structures:
                rw_points = [-1e18 for _ in range(remaining_after_dst + 1)]
                rw_choices: list[tuple[PlayerPoolRow, ...] | None] = [None for _ in range(remaining_after_dst + 1)]
                for rb_salary in range(remaining_after_dst + 1):
                    rb_val = rb_points[rb_need][rb_salary]
                    if rb_val <= -1e17:
                        continue
                    rb_choice = rb_choices[rb_need][rb_salary]
                    if rb_choice is None:
                        continue
                    max_wr_salary = remaining_after_dst - rb_salary
                    for wr_salary in range(max_wr_salary + 1):
                        wr_val = wr_points[wr_need][wr_salary]
                        if wr_val <= -1e17:
                            continue
                        wr_choice = wr_choices[wr_need][wr_salary]
                        if wr_choice is None:
                            continue
                        total_rw_salary = rb_salary + wr_salary
                        total_rw_points = rb_val + wr_val
                        if total_rw_points > rw_points[total_rw_salary]:
                            rw_points[total_rw_salary] = total_rw_points
                            rw_choices[total_rw_salary] = rb_choice + wr_choice

                te_prefix_points = [-1e18 for _ in range(remaining_after_dst + 1)]
                te_prefix_choices: list[tuple[PlayerPoolRow, ...] | None] = [None for _ in range(remaining_after_dst + 1)]
                running_te_points = -1e18
                running_te_choice: tuple[PlayerPoolRow, ...] | None = None
                for budget in range(remaining_after_dst + 1):
                    val = te_points[te_need][budget]
                    if val > running_te_points:
                        running_te_points = val
                        running_te_choice = te_choices[te_need][budget]
                    te_prefix_points[budget] = running_te_points
                    te_prefix_choices[budget] = running_te_choice

                for budget in range(remaining_after_dst + 1):
                    best_val = skill_exact_points[budget]
                    best_choice = skill_exact_choices[budget]
                    for rw_salary in range(budget + 1):
                        rw_val = rw_points[rw_salary]
                        if rw_val <= -1e17:
                            continue
                        te_val = te_prefix_points[budget - rw_salary]
                        if te_val <= -1e17:
                            continue
                        rw_choice = rw_choices[rw_salary]
                        te_choice = te_prefix_choices[budget - rw_salary]
                        if rw_choice is None or te_choice is None:
                            continue
                        total_val = rw_val + te_val
                        if total_val > best_val:
                            best_val = total_val
                            best_choice = rw_choice + te_choice
                    skill_exact_points[budget] = best_val
                    skill_exact_choices[budget] = best_choice

            skill_prefix_points = [-1e18 for _ in range(remaining_after_dst + 1)]
            skill_prefix_choices: list[tuple[PlayerPoolRow, ...] | None] = [None for _ in range(remaining_after_dst + 1)]
            running_points = -1e18
            running_choice: tuple[PlayerPoolRow, ...] | None = None
            for budget in range(remaining_after_dst + 1):
                val = skill_exact_points[budget]
                if val > running_points:
                    running_points = val
                    running_choice = skill_exact_choices[budget]
                skill_prefix_points[budget] = running_points
                skill_prefix_choices[budget] = running_choice

            for qb in qb_pool:
                qb_cost = int(qb.salary // salary_step)
                remaining_for_skills = remaining_after_dst - qb_cost
                if remaining_for_skills < 0:
                    continue
                skill_points = skill_prefix_points[remaining_for_skills]
                skill_choice = skill_prefix_choices[remaining_for_skills]
                if skill_points <= -1e17 or skill_choice is None:
                    continue
                lineup = [qb, *list(skill_choice), dst]
                if not _lineup_satisfies_roster_rules(lineup):
                    continue
                lineup_points = float(qb.actual_points + dst.actual_points + skill_points)
                lineup_salary_used = int(sum(row.salary for row in lineup))
                if lineup_salary_used > DK_SALARY_CAP:
                    continue
                if (
                    lineup_points > best_points
                    or (
                        abs(lineup_points - best_points) <= 1e-9
                        and lineup_salary_used > best_salary_used
                    )
                ):
                    best_points = lineup_points
                    best_salary_used = lineup_salary_used
                    best_lineup = lineup

        if best_lineup is None:
            return None
        return best_lineup, float(best_points), int(best_salary_used)

    def _generate_lineups_for_slate(
        self,
        *,
        players: list[PlayerPoolRow],
        lineups_target: int,
        rng: np.random.Generator,
    ) -> tuple[np.ndarray, np.ndarray, list[list[PlayerPoolRow]]]:
        by_pos: dict[str, list[PlayerPoolRow]] = defaultdict(list)
        for player in players:
            by_pos[player.position].append(player)

        skill_pool_count = len(by_pos["RB"]) + len(by_pos["WR"]) + len(by_pos["TE"])
        if (
            len(by_pos["QB"]) < 1
            or len(by_pos["RB"]) < 2
            or len(by_pos["WR"]) < 3
            or len(by_pos["TE"]) < 1
            or len(by_pos["DST"]) < 1
            or skill_pool_count < 7
        ):
            raise ValueError("Insufficient position coverage for lineup generation.")

        feature_rows: list[np.ndarray] = []
        point_rows: list[float] = []
        generated_lineups: list[list[PlayerPoolRow]] = []
        lineup_keys: set[tuple[str, ...]] = set()
        max_attempts = max(lineups_target * 20, 8000)
        min_salary_floor = 43000
        attempts = 0
        while len(feature_rows) < lineups_target and attempts < max_attempts:
            attempts += 1
            selected: set[str] = set()
            qb_pick = self._sample_weighted_unique(by_pos["QB"], 1, selected, rng)
            if qb_pick is None:
                continue
            selected.update(row.uid for row in qb_pick)
            rb_picks = self._sample_weighted_unique(by_pos["RB"], 2, selected, rng)
            if rb_picks is None:
                continue
            selected.update(row.uid for row in rb_picks)
            wr_picks = self._sample_weighted_unique(by_pos["WR"], 3, selected, rng)
            if wr_picks is None:
                continue
            selected.update(row.uid for row in wr_picks)
            te_pick = self._sample_weighted_unique(by_pos["TE"], 1, selected, rng)
            if te_pick is None:
                continue
            selected.update(row.uid for row in te_pick)
            flex_pool = by_pos["RB"] + by_pos["WR"] + by_pos["TE"]
            flex_pick = self._sample_weighted_unique(flex_pool, 1, selected, rng)
            if flex_pick is None:
                continue
            selected.update(row.uid for row in flex_pick)
            dst_pick = self._sample_weighted_unique(by_pos["DST"], 1, selected, rng)
            if dst_pick is None:
                continue

            lineup = qb_pick + rb_picks + wr_picks + te_pick + flex_pick + dst_pick
            if not _lineup_satisfies_roster_rules(lineup):
                continue
            salary_total = sum(row.salary for row in lineup)
            if salary_total > DK_SALARY_CAP or salary_total < min_salary_floor:
                continue

            key = tuple(sorted(row.uid for row in lineup))
            if key in lineup_keys:
                continue
            lineup_keys.add(key)

            feature_rows.append(self._lineup_features(lineup))
            point_rows.append(float(sum(row.actual_points for row in lineup)))
            generated_lineups.append(lineup)

        if len(feature_rows) < 120:
            raise ValueError("No valid lineups generated for this slate.")

        return np.vstack(feature_rows), np.asarray(point_rows, dtype=float), generated_lineups

    def _compute_dst_projection_lookup(
        self,
        *,
        season: int,
        week: int,
    ) -> dict[str, tuple[float, float]]:
        cache_key = (season, week)
        cached = self._dst_projection_cache.get(cache_key)
        if cached is not None:
            return cached

        week_rows = self.session.execute(
            select(RawNflSchedule.season, RawNflSchedule.week)
            .where(
                or_(
                    RawNflSchedule.season < season,
                    and_(
                        RawNflSchedule.season == season,
                        RawNflSchedule.week < week,
                    ),
                )
            )
            .group_by(RawNflSchedule.season, RawNflSchedule.week)
        ).all()
        by_team: dict[str, list[float]] = defaultdict(list)
        for prior_season, prior_week in week_rows:
            if prior_week is None:
                continue
            try:
                points_map = self._compute_dst_actual_points(
                    season=int(prior_season),
                    week=int(prior_week),
                )
            except Exception:  # noqa: BLE001
                continue
            for team, points in points_map.items():
                by_team[team].append(float(points))

        lookup: dict[str, tuple[float, float]] = {}
        for team, values in by_team.items():
            if not values:
                continue
            arr = np.asarray(values, dtype=float)
            lookup[team] = (float(np.mean(arr)), float(np.percentile(arr, 90)))
        self._dst_projection_cache[cache_key] = lookup
        return lookup

    def _compute_player_projection_lookup(
        self,
        *,
        source_system: str,
        season: int,
        week: int,
        slate: str,
    ) -> tuple[dict[str, tuple[float, float]], dict[str, tuple[float, float]]]:
        cache_key = (source_system, season, week, slate)
        cached = self._player_projection_cache.get(cache_key)
        if cached is not None:
            return cached

        salary_rows = self.session.execute(
            select(CuratedSalary).where(
                and_(
                    CuratedSalary.source_system == source_system,
                    CuratedSalary.season == season,
                    CuratedSalary.week == week,
                    CuratedSalary.slate == slate,
                )
            )
        ).scalars().all()
        if not salary_rows:
            empty = ({}, {})
            self._player_projection_cache[cache_key] = empty
            return empty

        master_ids = sorted({row.player_master_id for row in salary_rows if row.player_master_id})
        alias_rows = []
        if master_ids:
            alias_rows = self.session.execute(
                select(PlayerAlias.player_master_id, PlayerAlias.source_key).where(
                    and_(
                        PlayerAlias.source_system == "nflreadpy",
                        PlayerAlias.player_master_id.in_(master_ids),
                    )
                )
            ).all()

        player_id_to_masters: dict[str, set[str]] = defaultdict(set)
        for player_master_id, source_key in alias_rows:
            if source_key:
                player_id_to_masters[source_key].add(player_master_id)

        tracked_player_ids = sorted(player_id_to_masters.keys())
        stats_rows = []
        if tracked_player_ids:
            stats_rows = self.session.execute(
                select(RawNflWeeklyStat).where(
                    and_(
                        RawNflWeeklyStat.player_id.in_(tracked_player_ids),
                        or_(
                            RawNflWeeklyStat.season < season,
                            and_(RawNflWeeklyStat.season == season, RawNflWeeklyStat.week < week),
                        ),
                    )
                )
            ).scalars().all()

        points_by_master: dict[str, list[float]] = defaultdict(list)
        points_by_position: dict[str, list[float]] = defaultdict(list)
        for stat in stats_rows:
            points = calculate_dk_points(stat.raw_row_json or {})
            if not math.isfinite(points):
                continue
            position = _normalize_pool_position(stat.position)
            if position:
                points_by_position[position].append(float(points))
            if stat.player_id:
                for master_id in player_id_to_masters.get(stat.player_id, set()):
                    points_by_master[master_id].append(float(points))

        global_points: list[float] = []
        for values in points_by_position.values():
            global_points.extend(values)
        if not global_points:
            global_points = [8.0]

        lookup: dict[str, tuple[float, float]] = {}
        for row in salary_rows:
            position = _normalize_pool_position(row.position)
            if position == "DST":
                continue
            series = points_by_master.get(row.player_master_id or "", [])
            if not series:
                series = points_by_position.get(position or "", [])
            if not series:
                series = global_points
            arr = np.asarray(series, dtype=float)
            mean_val = float(np.mean(arr))
            p90_val = float(np.percentile(arr, 90))
            for key in [row.player_master_id, row.source_player_key]:
                if key:
                    lookup[key] = (mean_val, p90_val)

        dst_lookup = self._compute_dst_projection_lookup(season=season, week=week)
        result = (lookup, dst_lookup)
        self._player_projection_cache[cache_key] = result
        return result

    def _collect_training_lineup_chunks(
        self,
        *,
        source_system: str,
        season: int,
        week: int,
        training_start_season: int,
        training_window_slates: int,
        training_lineups_per_slate: int,
        rng: np.random.Generator,
    ) -> tuple[list[np.ndarray], list[np.ndarray], int, int]:
        target_ord = _slice_ordinal(season, week)
        slices = self._fetch_available_slate_slices(
            source_system=source_system,
            season_start=training_start_season,
            season_end=season,
            slate_filter=None,
        )
        historical = [item for item in slices if _slice_ordinal(item[0], item[1]) < target_ord]

        x_chunks_recent: list[np.ndarray] = []
        points_chunks_recent: list[np.ndarray] = []
        slates_used = 0
        for hist_season, hist_week, hist_slate in reversed(historical):
            try:
                projection_lookup, dst_projection_lookup = self._compute_player_projection_lookup(
                    source_system=source_system,
                    season=hist_season,
                    week=hist_week,
                    slate=hist_slate,
                )
                pool = self._fetch_slate_player_pool(
                    source_system=source_system,
                    season=hist_season,
                    week=hist_week,
                    slate=hist_slate,
                    projection_lookup=projection_lookup,
                    dst_projection_lookup=dst_projection_lookup,
                )
                x_slate, points_slate, _ = self._generate_lineups_for_slate(
                    players=pool,
                    lineups_target=training_lineups_per_slate,
                    rng=rng,
                )
            except Exception:  # noqa: BLE001
                continue
            if float(np.max(points_slate)) <= 0.0:
                continue
            if float(np.std(points_slate)) < 1e-9:
                continue
            x_chunks_recent.append(x_slate)
            points_chunks_recent.append(points_slate)
            slates_used += 1
            if slates_used >= training_window_slates:
                break

        # Keep chronological order for any time-aware downstream analysis.
        x_chunks = list(reversed(x_chunks_recent))
        points_chunks = list(reversed(points_chunks_recent))
        total_rows = int(sum(chunk.shape[0] for chunk in x_chunks))
        return x_chunks, points_chunks, slates_used, total_rows

    def _fit_percentile_model(
        self,
        *,
        x_chunks: list[np.ndarray],
        points_chunks: list[np.ndarray],
        percentile: float,
        tail: str,
    ) -> LogisticTargetModel:
        x_parts: list[np.ndarray] = []
        y_parts: list[np.ndarray] = []
        for x_slate, points_slate in zip(x_chunks, points_chunks):
            threshold = float(np.percentile(points_slate, percentile))
            if not math.isfinite(threshold):
                continue
            if tail == "upper":
                y_slate = (points_slate >= threshold).astype(float)
            else:
                y_slate = (points_slate <= threshold).astype(float)
            pos_rate = float(np.mean(y_slate))
            if pos_rate <= 0.0 or pos_rate >= 1.0:
                continue
            x_parts.append(x_slate)
            y_parts.append(y_slate)

        if not x_parts:
            dim = len(FEATURE_NAMES)
            return LogisticTargetModel(
                weights=np.zeros(dim, dtype=float),
                bias=0.0,
                mean=np.zeros(dim, dtype=float),
                std=np.ones(dim, dtype=float),
                positive_rate=0.0,
                training_rows=0,
                has_signal=False,
            )

        x_train = np.vstack(x_parts)
        y_train = np.concatenate(y_parts)
        weights, bias, mean, std = self._fit_logistic(x_train, y_train)
        has_signal = float(np.max(np.abs(weights))) > 1e-8
        return LogisticTargetModel(
            weights=weights,
            bias=float(bias),
            mean=mean,
            std=std,
            positive_rate=float(np.mean(y_train)),
            training_rows=int(len(y_train)),
            has_signal=has_signal,
        )

    def _predict_target_model(self, model: LogisticTargetModel, x_rows: np.ndarray) -> np.ndarray:
        if x_rows.size == 0:
            return np.asarray([], dtype=float)
        x_norm = (x_rows - model.mean) / model.std
        return _sigmoid(x_norm @ model.weights + model.bias)

    def _fit_blend_weights(
        self,
        *,
        points_train: np.ndarray,
        policy_scores: np.ndarray,
        ceiling_scores: np.ndarray,
        quality_scores: np.ndarray,
    ) -> tuple[np.ndarray, float]:
        if len(points_train) < 200:
            return np.asarray([1.0, 0.0, 0.0], dtype=float), 0.0

        y_mean = float(np.mean(points_train))
        y_std = float(np.std(points_train))
        if y_std < 1e-9:
            return np.asarray([1.0, 0.0, 0.0], dtype=float), 0.0
        y_norm = (points_train - y_mean) / y_std

        x = np.column_stack([policy_scores, ceiling_scores, quality_scores])
        x_mean = np.mean(x, axis=0)
        x_std = np.std(x, axis=0)
        x_std = np.where(x_std < 1e-6, 1.0, x_std)
        x_scaled = (x - x_mean) / x_std

        design = np.column_stack([x_scaled, np.ones(len(x_scaled), dtype=float)])
        reg = 0.05
        gram = design.T @ design
        for idx in range(3):
            gram[idx, idx] += reg
        rhs = design.T @ y_norm
        try:
            coeff = np.linalg.solve(gram, rhs)
        except np.linalg.LinAlgError:
            coeff = np.linalg.pinv(gram) @ rhs

        weights_scaled = coeff[:3]
        intercept_scaled = float(coeff[3])
        weights = weights_scaled / x_std
        intercept = intercept_scaled - float(np.dot(weights, x_mean))
        return weights.astype(float), float(intercept)

    def _lineup_key(self, lineup: list[PlayerPoolRow]) -> str:
        return "|".join(sorted(row.uid for row in lineup))

    def _canonical_slot_order(self, lineup: list[PlayerPoolRow]) -> list[tuple[int, str, PlayerPoolRow]]:
        qb_rows = [row for row in lineup if row.position == "QB"]
        dst_rows = [row for row in lineup if row.position == "DST"]
        rb_rows = sorted([row for row in lineup if row.position == "RB"], key=lambda row: row.salary, reverse=True)
        wr_rows = sorted([row for row in lineup if row.position == "WR"], key=lambda row: row.salary, reverse=True)
        te_rows = sorted([row for row in lineup if row.position == "TE"], key=lambda row: row.salary, reverse=True)

        ordered: list[tuple[int, str, PlayerPoolRow]] = []
        if qb_rows:
            ordered.append((0, "QB", qb_rows[0]))
        if len(rb_rows) >= 1:
            ordered.append((1, "RB1", rb_rows[0]))
        if len(rb_rows) >= 2:
            ordered.append((2, "RB2", rb_rows[1]))
        if len(wr_rows) >= 1:
            ordered.append((3, "WR1", wr_rows[0]))
        if len(wr_rows) >= 2:
            ordered.append((4, "WR2", wr_rows[1]))
        if len(wr_rows) >= 3:
            ordered.append((5, "WR3", wr_rows[2]))
        if te_rows:
            ordered.append((6, "TE", te_rows[0]))

        used_ids = {id(row) for _idx, _slot, row in ordered}
        flex_candidates = [row for row in lineup if row.position in {"RB", "WR", "TE"} and id(row) not in used_ids]
        if flex_candidates:
            flex_row = sorted(flex_candidates, key=lambda row: row.salary, reverse=True)[0]
            ordered.append((7, "FLEX", flex_row))
        if dst_rows:
            ordered.append((8, "DST", dst_rows[0]))
        ordered.sort(key=lambda row: row[0])
        return ordered

    def _optimize_top_actual_lineups(
        self,
        *,
        players: list[PlayerPoolRow],
        top_k: int,
    ) -> list[tuple[list[PlayerPoolRow], float, int]]:
        if top_k <= 0 or not players:
            return []
        objective_scores = np.asarray([float(row.actual_points) for row in players], dtype=float)
        results = self._optimize_top_lineups_by_linear_scores(
            players=players,
            objective_scores=objective_scores,
            top_k=top_k,
            solver_name="top_actual_lineups",
        )
        if results:
            return results
        if not HAS_PULP:
            best = self.optimize_actual_lineup(players=players)
            if best is None:
                return []
            return [best]
        return []

    def _optimize_top_projected_lineups(
        self,
        *,
        players: list[PlayerPoolRow],
        top_k: int,
    ) -> list[tuple[list[PlayerPoolRow], float, int]]:
        if top_k <= 0 or not players:
            return []
        objective_scores = np.asarray(
            [
                (0.65 * float(max(0.0, row.projected_mean_points)))
                + (0.35 * float(max(0.0, row.projected_p90_points)))
                for row in players
            ],
            dtype=float,
        )
        return self._optimize_top_lineups_by_linear_scores(
            players=players,
            objective_scores=objective_scores,
            top_k=top_k,
            solver_name="top_projected_lineups",
        )

    def _optimize_top_lineups_by_linear_scores(
        self,
        *,
        players: list[PlayerPoolRow],
        objective_scores: np.ndarray,
        top_k: int,
        solver_name: str,
    ) -> list[tuple[list[PlayerPoolRow], float, int]]:
        if not HAS_PULP:
            return []
        if len(objective_scores) != len(players):
            return []

        variables: dict[int, LpVariable] = {
            idx: LpVariable(f"p_{idx}", lowBound=0, upBound=1, cat=LpBinary)
            for idx in range(len(players))
        }
        model = LpProblem(solver_name, LpMaximize)
        model += lpSum(float(objective_scores[idx]) * variables[idx] for idx in range(len(players)))

        qb_idx = [idx for idx, row in enumerate(players) if row.position == "QB"]
        rb_idx = [idx for idx, row in enumerate(players) if row.position == "RB"]
        wr_idx = [idx for idx, row in enumerate(players) if row.position == "WR"]
        te_idx = [idx for idx, row in enumerate(players) if row.position == "TE"]
        dst_idx = [idx for idx, row in enumerate(players) if row.position == "DST"]
        skill_idx = rb_idx + wr_idx + te_idx
        offense_idx = qb_idx + skill_idx

        if not qb_idx or len(rb_idx) < 2 or len(wr_idx) < 3 or not te_idx or not dst_idx:
            return []

        model += lpSum(variables[idx] for idx in qb_idx) == 1
        model += lpSum(variables[idx] for idx in dst_idx) == 1
        model += lpSum(variables[idx] for idx in rb_idx) >= 2
        model += lpSum(variables[idx] for idx in wr_idx) >= 3
        model += lpSum(variables[idx] for idx in te_idx) >= 1
        model += lpSum(variables[idx] for idx in skill_idx) == 7
        model += lpSum(variables[idx] for idx in range(len(players))) == 9
        model += lpSum(int(players[idx].salary) * variables[idx] for idx in range(len(players))) <= DK_SALARY_CAP

        for offense_i in offense_idx:
            offense_player = players[offense_i]
            for dst_i in dst_idx:
                dst_player = players[dst_i]
                if self._player_conflicts_with_dst(offense_player, dst_player):
                    model += variables[offense_i] + variables[dst_i] <= 1

        results: list[tuple[list[PlayerPoolRow], float, int]] = []
        seen_keys: set[str] = set()
        for _rank in range(top_k):
            status = model.solve(PULP_CBC_CMD(msg=False))
            status_name = LpStatus.get(status, "")
            if status_name not in {"Optimal", "Integer Feasible"}:
                break

            lineup_idx = [
                idx
                for idx in range(len(players))
                if value(variables[idx]) is not None and value(variables[idx]) > 0.5
            ]
            lineup = [players[idx] for idx in lineup_idx]
            if len(lineup) != 9 or not _lineup_satisfies_roster_rules(lineup):
                break

            lineup_key = self._lineup_key(lineup)
            if lineup_key in seen_keys:
                break
            seen_keys.add(lineup_key)

            points = float(sum(float(row.actual_points) for row in lineup))
            salary = int(sum(int(row.salary) for row in lineup))
            results.append((lineup, points, salary))

            # No-good cut: prevent selecting this exact lineup again.
            model += lpSum(variables[idx] for idx in lineup_idx) <= 8

        return results

    def _clear_actual_top_lineups_for_slice(
        self,
        *,
        source_system: str,
        season: int,
        week: int,
        slate: str,
    ) -> None:
        lineup_ids = self.session.execute(
            select(ActualTopLineup.actual_top_lineup_id).where(
                and_(
                    ActualTopLineup.source_system == source_system,
                    ActualTopLineup.season == season,
                    ActualTopLineup.week == week,
                    ActualTopLineup.slate == slate,
                )
            )
        ).scalars().all()
        if lineup_ids:
            self.session.query(ActualTopLineupPlayer).filter(
                ActualTopLineupPlayer.actual_top_lineup_id.in_(lineup_ids)
            ).delete(synchronize_session=False)
            self.session.query(ActualTopLineup).filter(
                ActualTopLineup.actual_top_lineup_id.in_(lineup_ids)
            ).delete(synchronize_session=False)

    def _load_top_lineup_keys_for_slice(
        self,
        *,
        source_system: str,
        season: int,
        week: int,
        slate: str,
        top_k: int,
    ) -> set[str]:
        rows = self.session.execute(
            select(ActualTopLineup.lineup_key).where(
                and_(
                    ActualTopLineup.source_system == source_system,
                    ActualTopLineup.season == season,
                    ActualTopLineup.week == week,
                    ActualTopLineup.slate == slate,
                    ActualTopLineup.lineup_rank <= top_k,
                )
            )
        ).scalars().all()
        return {str(row) for row in rows if row}

    def _load_stored_top_lineups_for_slice(
        self,
        *,
        source_system: str,
        season: int,
        week: int,
        slate: str,
        top_k: int,
        pool: list[PlayerPoolRow],
    ) -> list[list[PlayerPoolRow]]:
        headers = self.session.execute(
            select(ActualTopLineup).where(
                and_(
                    ActualTopLineup.source_system == source_system,
                    ActualTopLineup.season == season,
                    ActualTopLineup.week == week,
                    ActualTopLineup.slate == slate,
                    ActualTopLineup.lineup_rank <= top_k,
                )
            ).order_by(ActualTopLineup.lineup_rank)
        ).scalars().all()
        if not headers:
            return []

        lineup_ids = [row.actual_top_lineup_id for row in headers]
        players_rows = self.session.execute(
            select(ActualTopLineupPlayer).where(
                ActualTopLineupPlayer.actual_top_lineup_id.in_(lineup_ids)
            )
        ).scalars().all()
        by_lineup: dict[int, list[ActualTopLineupPlayer]] = defaultdict(list)
        for row in players_rows:
            by_lineup[row.actual_top_lineup_id].append(row)

        by_master: dict[str, PlayerPoolRow] = {}
        by_source: dict[str, PlayerPoolRow] = {}
        by_tuple: dict[tuple[str, str | None, str, int], PlayerPoolRow] = {}
        for row in pool:
            if row.player_master_id and row.player_master_id not in by_master:
                by_master[row.player_master_id] = row
            if row.source_player_key and row.source_player_key not in by_source:
                by_source[row.source_player_key] = row
            key = (row.name, row.team, row.position, int(row.salary))
            if key not in by_tuple:
                by_tuple[key] = row

        resolved: list[list[PlayerPoolRow]] = []
        for header in headers:
            slot_rows = sorted(
                by_lineup.get(header.actual_top_lineup_id, []),
                key=lambda row: row.slot_index,
            )
            if len(slot_rows) != 9:
                continue
            lineup: list[PlayerPoolRow] = []
            used_ids: set[str] = set()
            failed = False
            for slot in slot_rows:
                candidate: PlayerPoolRow | None = None
                if slot.player_master_id:
                    candidate = by_master.get(slot.player_master_id)
                if candidate is None and slot.source_player_key:
                    candidate = by_source.get(slot.source_player_key)
                if candidate is None:
                    candidate = by_tuple.get(
                        (slot.player_name, _canonical_team(slot.team), slot.position, int(slot.salary))
                    )
                if candidate is None or candidate.uid in used_ids:
                    failed = True
                    break
                lineup.append(candidate)
                used_ids.add(candidate.uid)
            if failed or not _lineup_satisfies_roster_rules(lineup):
                continue
            resolved.append(lineup)

        return resolved

    def build_actual_top_lineups(
        self,
        request: ActualTopLineupBuildRequest,
        progress_hook: Callable[[str], None] | None = None,
    ) -> ActualTopLineupBuildResponse:
        season_start = min(request.season_start, request.season_end)
        season_end = max(request.season_start, request.season_end)
        slices = self._fetch_available_slate_slices(
            source_system=request.source_system,
            season_start=season_start,
            season_end=season_end,
            slate_filter=request.slate,
        )
        if request.limit_slates > 0:
            slices = slices[: request.limit_slates]

        rows: list[ActualTopLineupBuildSliceResponse] = []
        rows_written = 0
        slates_completed = 0
        if progress_hook is not None:
            progress_hook(
                f"[build_actual_top] start source={request.source_system} "
                f"seasons={season_start}-{season_end} slates={len(slices)} top_k={request.top_k}"
            )
        for index, (season, week, slate) in enumerate(slices, start=1):
            try:
                existing_count = self.session.execute(
                    select(ActualTopLineup.actual_top_lineup_id).where(
                        and_(
                            ActualTopLineup.source_system == request.source_system,
                            ActualTopLineup.season == season,
                            ActualTopLineup.week == week,
                            ActualTopLineup.slate == slate,
                        )
                    )
                ).all()
                if len(existing_count) >= request.top_k and not request.overwrite_existing:
                    rows.append(
                        ActualTopLineupBuildSliceResponse(
                            source_system=request.source_system,
                            season=season,
                            week=week,
                            slate=slate,
                            status="skipped_existing",
                            rows_written=0,
                        )
                    )
                    if progress_hook is not None:
                        progress_hook(
                            f"[build_actual_top] {index}/{len(slices)} {season} W{week:02d} {slate} "
                            "status=skipped_existing rows=0"
                        )
                    continue

                if request.overwrite_existing or len(existing_count) > 0:
                    self._clear_actual_top_lineups_for_slice(
                        source_system=request.source_system,
                        season=season,
                        week=week,
                        slate=slate,
                    )

                projection_lookup, dst_projection_lookup = self._compute_player_projection_lookup(
                    source_system=request.source_system,
                    season=season,
                    week=week,
                    slate=slate,
                )
                pool = self._fetch_slate_player_pool(
                    source_system=request.source_system,
                    season=season,
                    week=week,
                    slate=slate,
                    projection_lookup=projection_lookup,
                    dst_projection_lookup=dst_projection_lookup,
                )
                top_lineups = self._optimize_top_actual_lineups(players=pool, top_k=request.top_k)
                if not top_lineups:
                    rows.append(
                        ActualTopLineupBuildSliceResponse(
                            source_system=request.source_system,
                            season=season,
                            week=week,
                            slate=slate,
                            status="failed",
                            rows_written=0,
                            error_message="No feasible top actual lineups found.",
                        )
                    )
                    self.session.rollback()
                    continue

                for rank, (lineup, points, salary_used) in enumerate(top_lineups, start=1):
                    header = ActualTopLineup(
                        source_system=request.source_system,
                        season=season,
                        week=week,
                        slate=slate,
                        lineup_rank=rank,
                        actual_points=float(points),
                        salary_used=int(salary_used),
                        lineup_key=self._lineup_key(lineup),
                        created_at=utcnow_naive(),
                    )
                    self.session.add(header)
                    self.session.flush()

                    for slot_index, roster_slot, player in self._canonical_slot_order(lineup):
                        self.session.add(
                            ActualTopLineupPlayer(
                                actual_top_lineup_id=header.actual_top_lineup_id,
                                slot_index=int(slot_index),
                                roster_slot=roster_slot,
                                position=player.position,
                                player_master_id=player.player_master_id,
                                source_player_key=player.source_player_key,
                                player_name=player.name,
                                team=player.team,
                                salary=int(player.salary),
                                actual_points=float(player.actual_points),
                                created_at=utcnow_naive(),
                            )
                        )

                self.session.commit()
                wrote = len(top_lineups)
                rows_written += wrote
                slates_completed += 1
                rows.append(
                    ActualTopLineupBuildSliceResponse(
                        source_system=request.source_system,
                        season=season,
                        week=week,
                        slate=slate,
                        status="ok",
                        rows_written=wrote,
                    )
                )
                if progress_hook is not None:
                    progress_hook(
                        f"[build_actual_top] {index}/{len(slices)} {season} W{week:02d} {slate} "
                        f"status=ok rows={wrote} total_rows={rows_written}"
                    )
            except Exception as exc:  # noqa: BLE001
                self.session.rollback()
                rows.append(
                    ActualTopLineupBuildSliceResponse(
                        source_system=request.source_system,
                        season=season,
                        week=week,
                        slate=slate,
                        status="failed",
                        rows_written=0,
                        error_message=str(exc),
                    )
                )
                if progress_hook is not None:
                    progress_hook(
                        f"[build_actual_top] {index}/{len(slices)} {season} W{week:02d} {slate} "
                        f"status=failed error={exc}"
                    )

        if progress_hook is not None:
            progress_hook(
                f"[build_actual_top] done slates_completed={slates_completed}/{len(slices)} "
                f"rows_written={rows_written}"
            )

        return ActualTopLineupBuildResponse(
            source_system=request.source_system,
            season_start=season_start,
            season_end=season_end,
            slate=request.slate,
            top_k=request.top_k,
            slates_total=len(slices),
            slates_completed=slates_completed,
            slates_failed=len(slices) - slates_completed,
            rows_written=rows_written,
            rows=rows,
        )

    def run_actual_top_lineup_learning(
        self,
        request: ActualTopLineupLearningRequest,
        progress_hook: Callable[[str], None] | None = None,
    ) -> ActualTopLineupLearningResponse:
        season_start = min(request.season_start, request.season_end)
        season_end = max(request.season_start, request.season_end)
        slices = self._fetch_available_slate_slices(
            source_system=request.source_system,
            season_start=season_start,
            season_end=season_end,
            slate_filter=request.slate,
        )
        rng = np.random.default_rng(request.random_seed)
        history_x: list[np.ndarray] = []
        history_y: list[np.ndarray] = []
        rows: list[ActualTopLineupLearningSlateRowResponse] = []
        selected_points_total = 0.0
        random_points_total = 0.0
        slates_evaluated = 0
        last_weights: np.ndarray | None = None

        if progress_hook is not None:
            progress_hook(
                f"[learn_actual_top] start source={request.source_system} "
                f"seasons={season_start}-{season_end} slates={len(slices)} "
                f"top_k_label={request.top_k_label} candidates_per_slate={request.candidate_lineups_per_slate}"
            )
        for index, (season, week, slate) in enumerate(slices, start=1):
            try:
                top_keys = self._load_top_lineup_keys_for_slice(
                    source_system=request.source_system,
                    season=season,
                    week=week,
                    slate=slate,
                    top_k=request.top_k_label,
                )
                if not top_keys:
                    msg = "No stored top actual lineups for this slate."
                    rows.append(
                        ActualTopLineupLearningSlateRowResponse(
                            season=season,
                            week=week,
                            slate=slate,
                            generated_lineups=0,
                            positives_in_pool=0,
                            selected_lineups=0,
                            selected_mean_actual_points=None,
                            random_mean_actual_points=None,
                            uplift_points=None,
                            error_message=msg,
                        )
                    )
                    if progress_hook is not None:
                        progress_hook(
                            f"[learn_actual_top] {index}/{len(slices)} {season} W{week:02d} {slate} "
                            f"status=skipped reason={msg} eval={slates_evaluated}"
                        )
                    continue

                projection_lookup, dst_projection_lookup = self._compute_player_projection_lookup(
                    source_system=request.source_system,
                    season=season,
                    week=week,
                    slate=slate,
                )
                pool = self._fetch_slate_player_pool(
                    source_system=request.source_system,
                    season=season,
                    week=week,
                    slate=slate,
                    projection_lookup=projection_lookup,
                    dst_projection_lookup=dst_projection_lookup,
                )
                candidate_lineups = self._generate_candidate_lineups_adaptive(
                    players=pool,
                    requested_lineups=request.candidate_lineups_per_slate,
                    min_salary_floor=36000,
                    rng=rng,
                )
                stored_top_lineups = self._load_stored_top_lineups_for_slice(
                    source_system=request.source_system,
                    season=season,
                    week=week,
                    slate=slate,
                    top_k=request.top_k_label,
                    pool=pool,
                )
                if stored_top_lineups:
                    seen_candidate_keys = {self._lineup_key(lineup) for lineup in candidate_lineups}
                    for top_lineup in stored_top_lineups:
                        key = self._lineup_key(top_lineup)
                        if key not in seen_candidate_keys:
                            candidate_lineups.append(top_lineup)
                            seen_candidate_keys.add(key)

                x_slate = np.vstack([self._lineup_features(lineup) for lineup in candidate_lineups])
                points_slate = np.asarray(
                    [sum(player.actual_points for player in lineup) for lineup in candidate_lineups],
                    dtype=float,
                )
                y_slate = np.asarray(
                    [1.0 if self._lineup_key(lineup) in top_keys else 0.0 for lineup in candidate_lineups],
                    dtype=float,
                )
                positives = int(np.sum(y_slate))
                if positives <= 0 or positives >= len(y_slate):
                    msg = "No usable positive labels in generated candidate pool."
                    rows.append(
                        ActualTopLineupLearningSlateRowResponse(
                            season=season,
                            week=week,
                            slate=slate,
                            generated_lineups=len(candidate_lineups),
                            positives_in_pool=positives,
                            selected_lineups=0,
                            selected_mean_actual_points=None,
                            random_mean_actual_points=None,
                            uplift_points=None,
                            error_message=msg,
                        )
                    )
                    if progress_hook is not None:
                        progress_hook(
                            f"[learn_actual_top] {index}/{len(slices)} {season} W{week:02d} {slate} "
                            f"status=skipped gen={len(candidate_lineups)} pos={positives} reason={msg}"
                        )
                    continue

                train_rows = int(sum(chunk.shape[0] for chunk in history_x))
                selected_n = min(request.selection_size, len(candidate_lineups))
                if len(history_x) >= request.min_training_slates and train_rows >= request.min_training_rows:
                    x_train = np.vstack(history_x)
                    y_train = np.concatenate(history_y)
                    weights, bias, mean, std = self._fit_logistic(x_train, y_train)
                    last_weights = weights
                    probs = _sigmoid(((x_slate - mean) / std) @ weights + bias)
                    selected_idx = np.argsort(-probs)[:selected_n]

                    random_runs = 5
                    random_means: list[float] = []
                    for _ in range(random_runs):
                        random_idx = rng.choice(len(points_slate), size=selected_n, replace=False)
                        random_means.append(float(np.mean(points_slate[random_idx])))
                    selected_mean = float(np.mean(points_slate[selected_idx]))
                    random_mean = float(np.mean(random_means))
                    uplift = selected_mean - random_mean
                    selected_points_total += selected_mean
                    random_points_total += random_mean
                    slates_evaluated += 1
                    rows.append(
                        ActualTopLineupLearningSlateRowResponse(
                            season=season,
                            week=week,
                            slate=slate,
                            generated_lineups=len(candidate_lineups),
                            positives_in_pool=positives,
                            selected_lineups=selected_n,
                            selected_mean_actual_points=selected_mean,
                            random_mean_actual_points=random_mean,
                            uplift_points=uplift,
                            error_message=None,
                        )
                    )
                    if progress_hook is not None:
                        progress_hook(
                            f"[learn_actual_top] {index}/{len(slices)} {season} W{week:02d} {slate} "
                            f"status=evaluated gen={len(candidate_lineups)} pos={positives} "
                            f"uplift={uplift:.2f} eval={slates_evaluated}"
                        )
                else:
                    msg = "Warm-up slate used for training only."
                    rows.append(
                        ActualTopLineupLearningSlateRowResponse(
                            season=season,
                            week=week,
                            slate=slate,
                            generated_lineups=len(candidate_lineups),
                            positives_in_pool=positives,
                            selected_lineups=0,
                            selected_mean_actual_points=None,
                            random_mean_actual_points=None,
                            uplift_points=None,
                            error_message=msg,
                        )
                    )
                    if progress_hook is not None:
                        progress_hook(
                            f"[learn_actual_top] {index}/{len(slices)} {season} W{week:02d} {slate} "
                            f"status=warmup gen={len(candidate_lineups)} pos={positives} "
                            f"train_rows={train_rows}"
                        )

                history_x.append(x_slate)
                history_y.append(y_slate)
                while len(history_x) > request.training_window_slates:
                    history_x.pop(0)
                    history_y.pop(0)
            except Exception as exc:  # noqa: BLE001
                rows.append(
                    ActualTopLineupLearningSlateRowResponse(
                        season=season,
                        week=week,
                        slate=slate,
                        generated_lineups=0,
                        positives_in_pool=0,
                        selected_lineups=0,
                        selected_mean_actual_points=None,
                        random_mean_actual_points=None,
                        uplift_points=None,
                        error_message=str(exc),
                    )
                )
                if progress_hook is not None:
                    progress_hook(
                        f"[learn_actual_top] {index}/{len(slices)} {season} W{week:02d} {slate} "
                        f"status=failed error={exc}"
                    )

        mean_selected = (selected_points_total / slates_evaluated) if slates_evaluated > 0 else None
        mean_random = (random_points_total / slates_evaluated) if slates_evaluated > 0 else None
        insights: list[LineupLearningFeatureInsightRowResponse] = []
        if last_weights is not None:
            ranked = sorted(
                enumerate(last_weights),
                key=lambda pair: abs(float(pair[1])),
                reverse=True,
            )
            for index, weight in ranked[:8]:
                insights.append(
                    LineupLearningFeatureInsightRowResponse(
                        feature_name=FEATURE_NAMES[index],
                        weight=float(weight),
                        direction="positive" if weight > 0 else "negative",
                    )
                )

        discovered_patterns = [
            f"Top-lineup label source: stored historical top-{request.top_k_label} actual lineups per slate.",
            f"Walk-forward evaluated slates: {slates_evaluated}/{len(slices)}.",
        ]
        if mean_selected is not None and mean_random is not None:
            discovered_patterns.append(
                f"Average selected vs random actual points: {mean_selected:.2f} vs {mean_random:.2f} (uplift {(mean_selected - mean_random):.2f})."
            )
        if insights:
            discovered_patterns.append(
                f"Strongest learned signal: {insights[0].feature_name} ({insights[0].weight:.3f})."
            )

        if progress_hook is not None:
            progress_hook(
                f"[learn_actual_top] done evaluated={slates_evaluated}/{len(slices)} "
                f"mean_selected={mean_selected if mean_selected is not None else 'NA'} "
                f"mean_random={mean_random if mean_random is not None else 'NA'}"
            )

        return ActualTopLineupLearningResponse(
            source_system=request.source_system,
            season_start=season_start,
            season_end=season_end,
            slate=request.slate,
            top_k_label=request.top_k_label,
            candidate_lineups_per_slate=request.candidate_lineups_per_slate,
            slates_total=len(slices),
            slates_evaluated=slates_evaluated,
            slates_warmup_or_failed=len(slices) - slates_evaluated,
            mean_selected_points=mean_selected,
            mean_random_points=mean_random,
            points_uplift=(mean_selected - mean_random) if mean_selected is not None and mean_random is not None else None,
            discovered_patterns=discovered_patterns,
            feature_insights=insights,
            rows=rows,
        )

    def _fit_policy_for_target(
        self,
        *,
        source_system: str,
        season: int,
        week: int,
        training_start_season: int,
        training_window_slates: int,
        training_lineups_per_slate: int,
        min_training_slates: int,
        min_training_rows: int,
        rng: np.random.Generator,
    ) -> tuple[np.ndarray, float, np.ndarray, np.ndarray, int, int, float]:
        target_ord = _slice_ordinal(season, week)
        slices = self._fetch_available_slate_slices(
            source_system=source_system,
            season_start=training_start_season,
            season_end=season,
            slate_filter=None,
        )
        historical = [
            item
            for item in slices
            if _slice_ordinal(item[0], item[1]) < target_ord
        ]

        x_chunks: list[np.ndarray] = []
        y_chunks: list[np.ndarray] = []
        slates_used = 0
        for hist_season, hist_week, hist_slate in reversed(historical):
            try:
                projection_lookup, dst_projection_lookup = self._compute_player_projection_lookup(
                    source_system=source_system,
                    season=hist_season,
                    week=hist_week,
                    slate=hist_slate,
                )
                pool = self._fetch_slate_player_pool(
                    source_system=source_system,
                    season=hist_season,
                    week=hist_week,
                    slate=hist_slate,
                    projection_lookup=projection_lookup,
                    dst_projection_lookup=dst_projection_lookup,
                )
                x_slate, points_slate, _ = self._generate_lineups_for_slate(
                    players=pool,
                    lineups_target=training_lineups_per_slate,
                    rng=rng,
                )
            except Exception:  # noqa: BLE001
                continue
            if float(np.max(points_slate)) <= 0.0:
                continue
            if float(np.std(points_slate)) < 1e-9:
                continue
            threshold = float(np.percentile(points_slate, TOP_TARGET_PERCENTILE))
            if not math.isfinite(threshold) or threshold <= 0.0:
                continue
            y_slate = (points_slate >= threshold).astype(float)
            positive_rate = float(np.mean(y_slate))
            if positive_rate <= 0.0 or positive_rate >= 1.0:
                continue
            x_chunks.append(x_slate)
            y_chunks.append(y_slate)
            slates_used += 1
            if slates_used >= training_window_slates:
                break

        total_rows = int(sum(chunk.shape[0] for chunk in x_chunks))
        if slates_used < min_training_slates or total_rows < min_training_rows:
            zero_weights = np.zeros(len(FEATURE_NAMES), dtype=float)
            return zero_weights, 0.0, np.zeros(len(FEATURE_NAMES)), np.ones(len(FEATURE_NAMES)), slates_used, total_rows, 0.0

        x_train = np.vstack(list(reversed(x_chunks)))
        y_train = np.concatenate(list(reversed(y_chunks)))
        weights, bias, mean, std = self._fit_logistic(x_train, y_train)
        return weights, bias, mean, std, slates_used, total_rows, float(np.mean(y_train))

    def _generate_candidate_lineups(
        self,
        *,
        players: list[PlayerPoolRow],
        candidate_lineups: int,
        min_salary_floor: int,
        rng: np.random.Generator,
        min_required_lineups: int | None = None,
        max_attempts_multiplier: int = 6,
    ) -> list[list[PlayerPoolRow]]:
        by_pos: dict[str, list[PlayerPoolRow]] = defaultdict(list)
        for player in players:
            by_pos[player.position].append(player)
        if (
            len(by_pos["QB"]) < 1
            or len(by_pos["RB"]) < 2
            or len(by_pos["WR"]) < 3
            or len(by_pos["TE"]) < 1
            or len(by_pos["DST"]) < 1
        ):
            raise ValueError("Insufficient player pool for lineup construction.")

        def weighted_pick(rows: list[PlayerPoolRow], count: int, selected: set[str]) -> list[PlayerPoolRow] | None:
            eligible = [row for row in rows if row.uid not in selected]
            if len(eligible) < count:
                return None
            weights = np.asarray(
                [
                    max(0.5, row.projected_p90_points + 0.4 * row.projected_mean_points)
                    * (6000.0 / max(2000.0, float(row.salary))) ** 0.2
                    for row in eligible
                ],
                dtype=float,
            )
            if float(np.sum(weights)) <= 0:
                weights = np.ones(len(eligible), dtype=float)
            weights = weights / np.sum(weights)
            idx = rng.choice(len(eligible), size=count, replace=False, p=weights)
            return [eligible[int(i)] for i in idx]

        lineups: list[list[PlayerPoolRow]] = []
        seen_keys: set[tuple[str, ...]] = set()
        attempts = 0
        max_attempts = max(candidate_lineups * max_attempts_multiplier, 12000)
        while len(lineups) < candidate_lineups and attempts < max_attempts:
            attempts += 1
            selected: set[str] = set()
            qb = weighted_pick(by_pos["QB"], 1, selected)
            if qb is None:
                continue
            selected.update(row.uid for row in qb)
            rb = weighted_pick(by_pos["RB"], 2, selected)
            if rb is None:
                continue
            selected.update(row.uid for row in rb)
            wr = weighted_pick(by_pos["WR"], 3, selected)
            if wr is None:
                continue
            selected.update(row.uid for row in wr)
            te = weighted_pick(by_pos["TE"], 1, selected)
            if te is None:
                continue
            selected.update(row.uid for row in te)
            flex_pool = by_pos["RB"] + by_pos["WR"] + by_pos["TE"]
            flex = weighted_pick(flex_pool, 1, selected)
            if flex is None:
                continue
            selected.update(row.uid for row in flex)
            dst = weighted_pick(by_pos["DST"], 1, selected)
            if dst is None:
                continue

            lineup = qb + rb + wr + te + flex + dst
            if not _lineup_satisfies_roster_rules(lineup):
                continue
            salary = int(sum(row.salary for row in lineup))
            if salary > DK_SALARY_CAP or salary < min_salary_floor:
                continue
            key = tuple(sorted(row.uid for row in lineup))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            lineups.append(lineup)

        min_required = min_required_lineups
        if min_required is None:
            min_required = min(candidate_lineups, max(200, candidate_lineups // 30))
        min_required = max(1, int(min_required))
        if len(lineups) < min_required:
            raise ValueError(
                f"Could not generate enough valid candidate lineups ({len(lineups)}). "
                "Try lower min_salary_floor or a larger player pool."
            )
        return lineups

    def _enumerate_candidate_lineups_small_pool(
        self,
        *,
        players: list[PlayerPoolRow],
        limit: int,
        min_salary_floor: int,
    ) -> list[list[PlayerPoolRow]]:
        by_pos: dict[str, list[PlayerPoolRow]] = defaultdict(list)
        for player in players:
            by_pos[player.position].append(player)
        if (
            len(by_pos["QB"]) < 1
            or len(by_pos["RB"]) < 2
            or len(by_pos["WR"]) < 3
            or len(by_pos["TE"]) < 1
            or len(by_pos["DST"]) < 1
        ):
            return []

        n_qb = len(by_pos["QB"])
        n_rb = len(by_pos["RB"])
        n_wr = len(by_pos["WR"])
        n_te = len(by_pos["TE"])
        n_dst = len(by_pos["DST"])
        skill_count = n_rb + n_wr + n_te
        if skill_count < 7:
            return []

        try:
            approx = (
                n_qb
                * math.comb(n_rb, 2)
                * math.comb(n_wr, 3)
                * n_te
                * (skill_count - 6)
                * n_dst
            )
        except ValueError:
            return []
        if approx > 3_000_000:
            # Not a tiny slate; enumeration would be too expensive.
            return []

        lineups: list[list[PlayerPoolRow]] = []
        seen_keys: set[tuple[str, ...]] = set()
        target = max(1, int(limit))
        salary_floor = max(0, int(min_salary_floor))
        rb_rows = by_pos["RB"]
        wr_rows = by_pos["WR"]
        te_rows = by_pos["TE"]
        dst_rows = by_pos["DST"]
        for qb in by_pos["QB"]:
            for rb_pair in combinations(rb_rows, 2):
                rb_ids = {row.uid for row in rb_pair}
                for wr_triplet in combinations(wr_rows, 3):
                    wr_ids = {row.uid for row in wr_triplet}
                    for te in te_rows:
                        if te.uid in rb_ids or te.uid in wr_ids:
                            continue
                        used_ids = {qb.uid, te.uid, *rb_ids, *wr_ids}
                        flex_pool = [
                            row
                            for row in (rb_rows + wr_rows + te_rows)
                            if row.uid not in used_ids
                        ]
                        if not flex_pool:
                            continue
                        for flex in flex_pool:
                            if flex.uid in used_ids:
                                continue
                            for dst in dst_rows:
                                if dst.uid in used_ids or dst.uid == flex.uid:
                                    continue
                                lineup = [qb, *list(rb_pair), *list(wr_triplet), te, flex, dst]
                                if not _lineup_satisfies_roster_rules(lineup):
                                    continue
                                salary = int(sum(row.salary for row in lineup))
                                if salary > DK_SALARY_CAP or salary < salary_floor:
                                    continue
                                key = tuple(sorted(row.uid for row in lineup))
                                if key in seen_keys:
                                    continue
                                seen_keys.add(key)
                                lineups.append(lineup)
                                if len(lineups) >= target:
                                    return lineups
        return lineups

    def _generate_candidate_lineups_adaptive(
        self,
        *,
        players: list[PlayerPoolRow],
        requested_lineups: int,
        min_salary_floor: int,
        rng: np.random.Generator,
    ) -> list[list[PlayerPoolRow]]:
        target = max(100, int(requested_lineups))
        base_floor = max(0, int(min_salary_floor))
        attempts_plan: list[tuple[int, int, int, int]] = [
            (target, base_floor, min(target, max(200, target // 30)), 6),
            (min(target, 2200), max(28000, base_floor - 3000), 120, 8),
            (min(target, 1600), 24000, 100, 10),
            (min(target, 1200), 20000, 80, 12),
            (min(target, 900), 12000, 60, 14),
            (min(target, 700), 0, 40, 18),
            (min(target, 500), 0, 25, 24),
        ]
        seen_plan: set[tuple[int, int, int, int]] = set()
        plan: list[tuple[int, int, int, int]] = []
        for item in attempts_plan:
            normalized = (
                max(100, int(item[0])),
                max(0, int(item[1])),
                max(1, int(item[2])),
                max(1, int(item[3])),
            )
            if normalized not in seen_plan:
                seen_plan.add(normalized)
                plan.append(normalized)

        last_error: Exception | None = None
        for candidate_count, floor_value, min_required, attempts_multiplier in plan:
            try:
                return self._generate_candidate_lineups(
                    players=players,
                    candidate_lineups=candidate_count,
                    min_salary_floor=floor_value,
                    rng=rng,
                    min_required_lineups=min_required,
                    max_attempts_multiplier=attempts_multiplier,
                )
            except ValueError as exc:
                last_error = exc
                continue

        enum_target = max(120, min(requested_lineups, 600))
        enumerated = self._enumerate_candidate_lineups_small_pool(
            players=players,
            limit=enum_target,
            min_salary_floor=0,
        )
        if len(enumerated) >= 20:
            return enumerated

        solver_target = max(120, min(requested_lineups, 200))
        projected_candidates = self._optimize_top_projected_lineups(
            players=players,
            top_k=solver_target,
        )
        if projected_candidates:
            projected_lineups = [lineup for lineup, _obj, _salary in projected_candidates]
            if len(projected_lineups) >= 20:
                return projected_lineups
            last_error = ValueError(
                "Projected MILP fallback produced too few candidate lineups "
                f"({len(projected_lineups)})."
            )

        if last_error is not None:
            raise ValueError(
                f"Adaptive candidate generation failed after {len(plan)} strategies: {last_error}"
            ) from last_error
        raise ValueError("Adaptive candidate generation failed with unknown error.")

    def _fit_logistic(self, x_train: np.ndarray, y_train: np.ndarray) -> tuple[np.ndarray, float, np.ndarray, np.ndarray]:
        mean = np.mean(x_train, axis=0)
        std = np.std(x_train, axis=0)
        std = np.where(std < 1e-6, 1.0, std)
        xs = (x_train - mean) / std

        pos_rate = float(np.mean(y_train))
        if pos_rate <= 0 or pos_rate >= 1:
            return np.zeros(xs.shape[1], dtype=float), 0.0, mean, std

        bias = math.log(pos_rate / (1.0 - pos_rate))
        weights = np.zeros(xs.shape[1], dtype=float)
        lr = 0.06
        l2 = 0.0002
        for _ in range(360):
            logits = xs @ weights + bias
            probs = _sigmoid(logits)
            error = probs - y_train
            grad_w = (xs.T @ error) / len(xs) + (l2 * weights)
            grad_b = float(np.mean(error))
            weights -= lr * grad_w
            bias -= lr * grad_b
        return weights, bias, mean, std

    def run_walk_forward_learning(self, request: LineupLearningRequest) -> LineupLearningResponse:
        season_start = min(request.season_start, request.season_end)
        season_end = max(request.season_start, request.season_end)
        slices = self._fetch_available_slate_slices(
            source_system=request.source_system,
            season_start=season_start,
            season_end=season_end,
            slate_filter=request.slate,
        )
        if not slices:
            raise ValueError(
                f"No curated salary slices found for {request.source_system} seasons {season_start}-{season_end}."
            )

        rng = np.random.default_rng(request.random_seed)
        history_x: list[np.ndarray] = []
        history_y: list[np.ndarray] = []
        slate_rows: list[LineupLearningSlateResultRowResponse] = []
        pattern_counts: dict[str, int] = defaultdict(int)
        pattern_success_counts: dict[str, float] = defaultdict(float)
        global_success_total = 0.0
        global_row_total = 0

        selected_points_total = 0.0
        random_points_total = 0.0
        selected_top_rate_total = 0.0
        random_top_rate_total = 0.0
        evaluated_slates = 0
        discovered_weights: np.ndarray | None = None

        for season, week, slate in slices:
            try:
                projection_lookup, dst_projection_lookup = self._compute_player_projection_lookup(
                    source_system=request.source_system,
                    season=season,
                    week=week,
                    slate=slate,
                )
                pool = self._fetch_slate_player_pool(
                    source_system=request.source_system,
                    season=season,
                    week=week,
                    slate=slate,
                    projection_lookup=projection_lookup,
                    dst_projection_lookup=dst_projection_lookup,
                )
                x_slate, points_slate, _ = self._generate_lineups_for_slate(
                    players=pool,
                    lineups_target=request.lineups_per_slate,
                    rng=rng,
                )
            except Exception as exc:  # noqa: BLE001
                slate_rows.append(
                    LineupLearningSlateResultRowResponse(
                        season=season,
                        week=week,
                        slate=slate,
                        generated_lineups=0,
                        selected_lineups=0,
                        mean_selected_points=None,
                        mean_random_points=None,
                        selected_top1pct_rate=None,
                        random_top1pct_rate=None,
                        uplift_points=None,
                        uplift_top1pct_rate=None,
                        error_message=str(exc),
                    )
                )
                continue

            top_threshold = float(np.percentile(points_slate, 98.0))
            y_slate = (points_slate >= top_threshold).astype(float)
            global_success_total += float(np.sum(y_slate))
            global_row_total += int(len(y_slate))
            double_stack_mask = x_slate[:, PATTERN_FEATURE_INDEX["double_stack_flag"]] >= 0.5
            bringback_mask = x_slate[:, PATTERN_FEATURE_INDEX["bringback_flag"]] >= 0.5
            cheap_two_mask = x_slate[:, PATTERN_FEATURE_INDEX["cheap_count"]] >= 2.0
            no_bringback_mask = x_slate[:, PATTERN_FEATURE_INDEX["qb_opponent_players"]] <= 0.0
            pattern_masks = {
                "double_stack": double_stack_mask,
                "bringback": bringback_mask,
                "double_stack_with_bringback": np.logical_and(double_stack_mask, bringback_mask),
                "cheap_count_ge_2": cheap_two_mask,
                "no_qb_bringback": no_bringback_mask,
            }
            for name, mask in pattern_masks.items():
                count = int(np.sum(mask))
                if count <= 0:
                    continue
                pattern_counts[name] += count
                pattern_success_counts[name] += float(np.sum(y_slate[mask]))

            selected_n = min(request.selection_size, len(points_slate))
            if selected_n < 1:
                selected_n = max(1, len(points_slate) // 20)

            train_rows = int(sum(chunk.shape[0] for chunk in history_x))
            if len(history_x) >= request.min_training_slates and train_rows >= request.min_training_rows:
                x_train = np.vstack(history_x)
                y_train = np.concatenate(history_y)
                weights, bias, mean, std = self._fit_logistic(x_train, y_train)
                discovered_weights = weights
                x_norm = (x_slate - mean) / std
                probs = _sigmoid(x_norm @ weights + bias)
                selected_idx = np.argsort(-probs)[:selected_n]

                random_runs = 7
                random_means: list[float] = []
                random_top_rates: list[float] = []
                top1_threshold = float(np.percentile(points_slate, 99.0))
                for _ in range(random_runs):
                    random_idx = rng.choice(len(points_slate), size=selected_n, replace=False)
                    random_points = points_slate[random_idx]
                    random_means.append(float(np.mean(random_points)))
                    random_top_rates.append(float(np.mean(random_points >= top1_threshold)))

                selected_points = points_slate[selected_idx]
                selected_mean = float(np.mean(selected_points))
                selected_top_rate = float(np.mean(selected_points >= top1_threshold))
                random_mean = float(np.mean(random_means))
                random_top_rate = float(np.mean(random_top_rates))

                selected_points_total += selected_mean
                random_points_total += random_mean
                selected_top_rate_total += selected_top_rate
                random_top_rate_total += random_top_rate
                evaluated_slates += 1

                slate_rows.append(
                    LineupLearningSlateResultRowResponse(
                        season=season,
                        week=week,
                        slate=slate,
                        generated_lineups=len(points_slate),
                        selected_lineups=selected_n,
                        mean_selected_points=selected_mean,
                        mean_random_points=random_mean,
                        selected_top1pct_rate=selected_top_rate,
                        random_top1pct_rate=random_top_rate,
                        uplift_points=selected_mean - random_mean,
                        uplift_top1pct_rate=selected_top_rate - random_top_rate,
                        error_message=None,
                    )
                )
            else:
                slate_rows.append(
                    LineupLearningSlateResultRowResponse(
                        season=season,
                        week=week,
                        slate=slate,
                        generated_lineups=len(points_slate),
                        selected_lineups=0,
                        mean_selected_points=None,
                        mean_random_points=None,
                        selected_top1pct_rate=None,
                        random_top1pct_rate=None,
                        uplift_points=None,
                        uplift_top1pct_rate=None,
                        error_message="Warm-up slate used for training only.",
                    )
                )

            history_x.append(x_slate)
            history_y.append(y_slate)
            while len(history_x) > request.training_window_slates:
                history_x.pop(0)
                history_y.pop(0)

        mean_selected_points = (
            (selected_points_total / evaluated_slates) if evaluated_slates > 0 else None
        )
        mean_random_points = (random_points_total / evaluated_slates) if evaluated_slates > 0 else None
        mean_selected_top = (selected_top_rate_total / evaluated_slates) if evaluated_slates > 0 else None
        mean_random_top = (random_top_rate_total / evaluated_slates) if evaluated_slates > 0 else None

        feature_insights: list[LineupLearningFeatureInsightRowResponse] = []
        if discovered_weights is not None:
            ranked = sorted(
                enumerate(discovered_weights),
                key=lambda pair: abs(float(pair[1])),
                reverse=True,
            )
            for index, weight in ranked[:8]:
                direction = "positive" if weight > 0 else "negative"
                feature_insights.append(
                    LineupLearningFeatureInsightRowResponse(
                        feature_name=FEATURE_NAMES[index],
                        weight=float(weight),
                        direction=direction,
                    )
                )

        discovered_patterns: list[str] = []
        global_success_rate = (global_success_total / global_row_total) if global_row_total > 0 else 0.0
        if feature_insights:
            discovered_patterns.append(
                "Top learned features ranked by predictive weight are included below."
            )
            best_positive = next((row for row in feature_insights if row.weight > 0), None)
            best_negative = next((row for row in feature_insights if row.weight < 0), None)
            if best_positive:
                discovered_patterns.append(
                    f"Most positive signal: {best_positive.feature_name} (weight {best_positive.weight:.3f})."
                )
            if best_negative:
                discovered_patterns.append(
                    f"Most negative signal: {best_negative.feature_name} (weight {best_negative.weight:.3f})."
                )
        if mean_selected_points is not None and mean_random_points is not None:
            discovered_patterns.append(
                f"Walk-forward average lineup points uplift: {(mean_selected_points - mean_random_points):.2f}."
            )
        if mean_selected_top is not None and mean_random_top is not None:
            discovered_patterns.append(
                "Walk-forward top-1% lineup hit-rate uplift: "
                f"{(mean_selected_top - mean_random_top) * 100:.2f} percentage points."
            )
        if global_success_rate > 0:
            lifts: list[tuple[str, float, int, float]] = []
            for name, count in pattern_counts.items():
                if count < 5000:
                    continue
                success_rate = pattern_success_counts[name] / count
                lift = (success_rate - global_success_rate) / global_success_rate
                lifts.append((name, lift, count, success_rate))
            lifts.sort(key=lambda row: row[1], reverse=True)
            for name, lift, count, success_rate in lifts[:3]:
                discovered_patterns.append(
                    f"Pattern lift: {name} success_rate={success_rate:.2%} over baseline {global_success_rate:.2%} "
                    f"(lift {lift * 100:.1f}%, n={count})."
                )

        return LineupLearningResponse(
            source_system=request.source_system,
            season_start=season_start,
            season_end=season_end,
            slate=request.slate,
            lineups_per_slate=request.lineups_per_slate,
            slates_total=len(slices),
            slates_evaluated=evaluated_slates,
            slates_warmup_or_failed=len(slices) - evaluated_slates,
            mean_selected_points=mean_selected_points,
            mean_random_points=mean_random_points,
            points_uplift=(mean_selected_points - mean_random_points)
            if mean_selected_points is not None and mean_random_points is not None
            else None,
            mean_selected_top1pct_rate=mean_selected_top,
            mean_random_top1pct_rate=mean_random_top,
            top1pct_rate_uplift=(mean_selected_top - mean_random_top)
            if mean_selected_top is not None and mean_random_top is not None
            else None,
            discovered_patterns=discovered_patterns,
            feature_insights=feature_insights,
            rows=slate_rows,
        )

    def build_ultimate_lineups(self, request: UltimateLineupRequest) -> UltimateLineupResponse:
        rng = np.random.default_rng(request.random_seed)
        x_history_chunks, points_history_chunks, training_slates_used, training_rows_used = self._collect_training_lineup_chunks(
            source_system=request.source_system,
            season=request.season,
            week=request.week,
            training_start_season=request.training_start_season,
            training_window_slates=request.training_window_slates,
            training_lineups_per_slate=request.training_lineups_per_slate,
            rng=rng,
        )
        history_ready = (
            training_slates_used >= request.min_training_slates
            and training_rows_used >= request.min_training_rows
        )
        dim = len(FEATURE_NAMES)
        zero_model = LogisticTargetModel(
            weights=np.zeros(dim, dtype=float),
            bias=0.0,
            mean=np.zeros(dim, dtype=float),
            std=np.ones(dim, dtype=float),
            positive_rate=0.0,
            training_rows=0,
            has_signal=False,
        )
        policy_model = zero_model
        ceiling_model = zero_model
        bust_model = zero_model
        blend_weights = np.asarray([1.0, 0.0, 0.0], dtype=float)
        blend_intercept = 0.0

        if history_ready:
            policy_model = self._fit_percentile_model(
                x_chunks=x_history_chunks,
                points_chunks=points_history_chunks,
                percentile=TOP_TARGET_PERCENTILE,
                tail="upper",
            )
            ceiling_model = self._fit_percentile_model(
                x_chunks=x_history_chunks,
                points_chunks=points_history_chunks,
                percentile=CEILING_TARGET_PERCENTILE,
                tail="upper",
            )
            bust_model = self._fit_percentile_model(
                x_chunks=x_history_chunks,
                points_chunks=points_history_chunks,
                percentile=BUST_TARGET_PERCENTILE,
                tail="lower",
            )

            x_history = np.vstack(x_history_chunks)
            points_history = np.concatenate(points_history_chunks)
            policy_history_scores = self._predict_target_model(policy_model, x_history)
            ceiling_history_scores = self._predict_target_model(ceiling_model, x_history)
            bust_history_scores = self._predict_target_model(bust_model, x_history)
            quality_history_scores = 1.0 - bust_history_scores
            blend_weights, blend_intercept = self._fit_blend_weights(
                points_train=points_history,
                policy_scores=policy_history_scores,
                ceiling_scores=ceiling_history_scores,
                quality_scores=quality_history_scores,
            )

        training_positive_rate = float(policy_model.positive_rate)

        player_projection_lookup, dst_projection_lookup = self._compute_player_projection_lookup(
            source_system=request.source_system,
            season=request.season,
            week=request.week,
            slate=request.slate,
        )
        target_pool = self._fetch_slate_player_pool(
            source_system=request.source_system,
            season=request.season,
            week=request.week,
            slate=request.slate,
            projection_lookup=player_projection_lookup,
            dst_projection_lookup=dst_projection_lookup,
        )
        if not target_pool:
            raise ValueError(
                f"No salary player pool available for {request.source_system} {request.season} week {request.week} slate={request.slate}."
            )

        projected_by_position: dict[str, list[tuple[float, float]]] = defaultdict(list)
        for player in target_pool:
            if player.projected_mean_points > 0 and player.projected_p90_points > 0:
                projected_by_position[player.position].append(
                    (player.projected_mean_points, player.projected_p90_points)
                )
        global_mean = float(
            np.mean([pair[0] for values in projected_by_position.values() for pair in values] or [8.0])
        )
        global_p90 = float(
            np.mean([pair[1] for values in projected_by_position.values() for pair in values] or [14.0])
        )
        for player in target_pool:
            if player.projected_mean_points > 0 and player.projected_p90_points > 0:
                continue
            pos_values = projected_by_position.get(player.position, [])
            if pos_values:
                player.projected_mean_points = float(np.mean([pair[0] for pair in pos_values]))
                player.projected_p90_points = float(np.mean([pair[1] for pair in pos_values]))
            else:
                player.projected_mean_points = global_mean
                player.projected_p90_points = global_p90

        candidate_lineups = self._generate_candidate_lineups_adaptive(
            players=target_pool,
            requested_lineups=request.candidate_lineups,
            min_salary_floor=request.min_salary_floor,
            rng=rng,
        )
        x_candidates = np.vstack([self._lineup_features(lineup) for lineup in candidate_lineups])
        mean_points = np.asarray(
            [sum(player.projected_mean_points for player in lineup) for lineup in candidate_lineups],
            dtype=float,
        )
        p90_points = np.asarray(
            [sum(player.projected_p90_points for player in lineup) for lineup in candidate_lineups],
            dtype=float,
        )

        has_learned_signal = history_ready and (policy_model.has_signal or ceiling_model.has_signal or bust_model.has_signal)
        learned_only = bool(getattr(request, "learned_only", True))
        if not has_learned_signal and learned_only:
            raise ValueError(
                "No learnable signal found for this target slate. "
                "Widen training window or lower minimum training thresholds."
            )

        if has_learned_signal:
            policy_scores = self._predict_target_model(policy_model, x_candidates)
            ceiling_scores = self._predict_target_model(ceiling_model, x_candidates)
            bust_scores = self._predict_target_model(bust_model, x_candidates)
            quality_scores = 1.0 - bust_scores
            composite = (
                blend_intercept
                + (blend_weights[0] * policy_scores)
                + (blend_weights[1] * ceiling_scores)
                + (blend_weights[2] * quality_scores)
            )
        else:
            # Optional heuristic fallback is only used when learned_only=False.
            policy_scores = np.full(len(candidate_lineups), 0.5, dtype=float)
            ceiling_scores = np.full(len(candidate_lineups), 0.5, dtype=float)
            bust_scores = np.full(len(candidate_lineups), 0.5, dtype=float)
            mean_std = float(np.std(mean_points))
            p90_std = float(np.std(p90_points))
            mean_norm = (
                (mean_points - float(np.mean(mean_points))) / (mean_std if mean_std > 1e-9 else 1.0)
            )
            p90_norm = (
                (p90_points - float(np.mean(p90_points))) / (p90_std if p90_std > 1e-9 else 1.0)
            )
            composite = (0.6 * mean_norm) + (0.4 * p90_norm)

        matchup_stack_rules = self._summarize_matchup_stack_rules(
            candidate_lineups=candidate_lineups,
            ranking_scores=composite,
        )

        ranked_idx = np.argsort(-composite)
        keep = min(request.output_lineups, len(ranked_idx))

        base_player_cap = min(keep, max(1, int(math.floor(keep * request.max_player_exposure))))
        base_qb_cap = min(keep, max(1, int(math.floor(keep * request.max_qb_exposure))))
        base_dst_cap = min(keep, max(1, int(math.floor(keep * request.max_dst_exposure))))

        def select_with_caps(multiplier: float) -> tuple[list[int], int, int, int]:
            player_cap = min(keep, max(1, int(math.floor(base_player_cap * multiplier))))
            qb_cap = min(keep, max(1, int(math.floor(base_qb_cap * multiplier))))
            dst_cap = min(keep, max(1, int(math.floor(base_dst_cap * multiplier))))

            selected: list[int] = []
            player_counts: dict[str, int] = defaultdict(int)
            qb_counts: dict[str, int] = defaultdict(int)
            dst_counts: dict[str, int] = defaultdict(int)

            for raw_idx in ranked_idx:
                idx = int(raw_idx)
                lineup = candidate_lineups[idx]
                if not _lineup_satisfies_roster_rules(lineup):
                    continue

                blocked = False
                qb_uid: str | None = None
                dst_uid: str | None = None
                for player in lineup:
                    if player_counts[player.uid] >= player_cap:
                        blocked = True
                        break
                    if player.position == "QB":
                        qb_uid = player.uid
                    elif player.position == "DST":
                        dst_uid = player.uid
                if blocked:
                    continue
                if qb_uid is not None and qb_counts[qb_uid] >= qb_cap:
                    continue
                if dst_uid is not None and dst_counts[dst_uid] >= dst_cap:
                    continue

                selected.append(idx)
                for player in lineup:
                    player_counts[player.uid] += 1
                if qb_uid is not None:
                    qb_counts[qb_uid] += 1
                if dst_uid is not None:
                    dst_counts[dst_uid] += 1
                if len(selected) >= keep:
                    break

            return selected, player_cap, qb_cap, dst_cap

        selected_idx: list[int] = []
        effective_player_cap = base_player_cap
        effective_qb_cap = base_qb_cap
        effective_dst_cap = base_dst_cap
        cap_multiplier_used = 1.0
        for multiplier in (1.0, 1.25, 1.5, 2.0, 3.0, 6.0):
            chosen, player_cap, qb_cap, dst_cap = select_with_caps(multiplier)
            selected_idx = chosen
            effective_player_cap = player_cap
            effective_qb_cap = qb_cap
            effective_dst_cap = dst_cap
            cap_multiplier_used = multiplier
            if len(selected_idx) >= keep:
                break

        # Guaranteed fill for output volume if caps are still too strict for this slate.
        if len(selected_idx) < keep:
            selected_set = set(selected_idx)
            for raw_idx in ranked_idx:
                idx = int(raw_idx)
                if idx in selected_set:
                    continue
                if not _lineup_satisfies_roster_rules(candidate_lineups[idx]):
                    continue
                selected_idx.append(idx)
                selected_set.add(idx)
                if len(selected_idx) >= keep:
                    break

        top_idx = np.asarray(selected_idx[:keep], dtype=int)
        keep = int(len(top_idx))

        rows: list[UltimateLineupRowResponse] = []
        exposure_counts: dict[str, tuple[PlayerPoolRow, int]] = {}
        for rank, idx in enumerate(top_idx.tolist(), start=1):
            lineup = candidate_lineups[idx]
            salary_used = int(sum(player.salary for player in lineup))
            salary_left = int(DK_SALARY_CAP - salary_used)
            lineup_players: list[UltimateLineupPlayerRowResponse] = []
            for player in lineup:
                lineup_players.append(
                    UltimateLineupPlayerRowResponse(
                        player_name=player.name,
                        team=player.team,
                        position=player.position,
                        salary=int(player.salary),
                        projected_mean_points=float(player.projected_mean_points),
                        projected_p90_points=float(player.projected_p90_points),
                    )
                )
                existing = exposure_counts.get(player.uid)
                if existing is None:
                    exposure_counts[player.uid] = (player, 1)
                else:
                    exposure_counts[player.uid] = (existing[0], existing[1] + 1)
            rows.append(
                UltimateLineupRowResponse(
                    rank=rank,
                    salary_used=salary_used,
                    salary_left=salary_left,
                    projected_mean_points=float(mean_points[idx]),
                    projected_p90_points=float(p90_points[idx]),
                    policy_score=float(policy_scores[idx]),
                    composite_score=float(composite[idx]),
                    players=lineup_players,
                )
            )

        exposures: list[UltimateLineupExposureRowResponse] = []
        for player, count in sorted(
            [value for value in exposure_counts.values()],
            key=lambda item: item[1],
            reverse=True,
        ):
            exposures.append(
                UltimateLineupExposureRowResponse(
                    player_name=player.name,
                    team=player.team,
                    position=player.position,
                    salary=int(player.salary),
                    exposure_count=int(count),
                    exposure_rate=(count / keep) if keep > 0 else 0.0,
                )
            )

        top_feature_weights = sorted(
            enumerate(policy_model.weights),
            key=lambda item: abs(float(item[1])),
            reverse=True,
        )[:5]
        selected_policy_mean = float(np.mean(policy_scores[top_idx])) if keep > 0 else 0.0
        selected_ceiling_mean = float(np.mean(ceiling_scores[top_idx])) if keep > 0 else 0.0
        selected_bust_mean = float(np.mean(bust_scores[top_idx])) if keep > 0 else 0.0
        discovered_patterns = [
            f"Models trained on {training_slates_used} slates and {training_rows_used} historical lineups.",
            (
                "Historical label rates: "
                f"top-{100 - TOP_TARGET_PERCENTILE:.0f}%={policy_model.positive_rate:.2%}, "
                f"ceiling(top-{100 - CEILING_TARGET_PERCENTILE:.0f}%)={ceiling_model.positive_rate:.2%}, "
                f"bust(bottom-{BUST_TARGET_PERCENTILE:.0f}%)={bust_model.positive_rate:.2%}."
            ),
            (
                "Ranking mode: "
                + (
                    "learned blended score (policy + ceiling + quality)."
                    if has_learned_signal
                    else "heuristic fallback (no learned signal)."
                )
            ),
            (
                "Diversification targets: "
                f"player<={request.max_player_exposure:.0%}, "
                f"QB<={request.max_qb_exposure:.0%}, DST<={request.max_dst_exposure:.0%}."
            ),
            (
                "Effective exposure caps (count): "
                f"player<={effective_player_cap}, QB<={effective_qb_cap}, DST<={effective_dst_cap}."
            ),
        ]
        if cap_multiplier_used > 1.0:
            discovered_patterns.append(
                f"Exposure caps auto-relaxed by x{cap_multiplier_used:.2f} to fill {keep} lineups."
            )
        if has_learned_signal:
            discovered_patterns.append(
                "Learned blend weights: "
                f"policy={blend_weights[0]:.3f}, "
                f"ceiling={blend_weights[1]:.3f}, "
                f"quality(1-bust)={blend_weights[2]:.3f}, "
                f"intercept={blend_intercept:.3f}."
            )
            discovered_patterns.append(
                "Selected lineup average risk profile: "
                f"policy={selected_policy_mean:.3f}, "
                f"ceiling={selected_ceiling_mean:.3f}, "
                f"bust={selected_bust_mean:.3f}."
            )
            for idx, weight in top_feature_weights:
                direction = "positive" if weight > 0 else "negative"
                discovered_patterns.append(
                    f"Policy signal: {FEATURE_NAMES[idx]} has {direction} weight {float(weight):.3f}."
                )
        discovered_patterns.extend(matchup_stack_rules)
        if rows:
            discovered_patterns.append(
                f"Top lineup projection mean/p90 = {rows[0].projected_mean_points:.2f}/{rows[0].projected_p90_points:.2f}."
            )

        return UltimateLineupResponse(
            source_system=request.source_system,
            season=request.season,
            week=request.week,
            slate=request.slate,
            candidate_lineups_requested=request.candidate_lineups,
            generated_candidate_lineups=len(candidate_lineups),
            output_lineups=keep,
            training_slates_used=training_slates_used,
            training_rows_used=training_rows_used,
            training_positive_rate=training_positive_rate,
            discovered_patterns=discovered_patterns,
            rows=rows,
            exposures=exposures,
        )
