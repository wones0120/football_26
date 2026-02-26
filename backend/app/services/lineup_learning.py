from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import numpy as np
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from ..models import CuratedSalary, PlayerAlias, RawNflSchedule, RawNflWeeklyStat
from ..schemas import (
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
        policy_scores: np.ndarray,
    ) -> list[str]:
        by_matchup: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for idx, lineup in enumerate(candidate_lineups):
            archetype, matchup_key = self._qb_game_stack_archetype(lineup)
            if matchup_key is None:
                continue
            by_matchup[matchup_key][archetype].append(float(policy_scores[idx]))

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

    def _generate_lineups_for_slate(
        self,
        *,
        players: list[PlayerPoolRow],
        lineups_target: int,
        rng: np.random.Generator,
    ) -> tuple[np.ndarray, np.ndarray, list[float]]:
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

        if len(feature_rows) < 120:
            raise ValueError("No valid lineups generated for this slate.")

        return np.vstack(feature_rows), np.asarray(point_rows, dtype=float), point_rows

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
            threshold = float(np.percentile(points_slate, 98.0))
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
        max_attempts = max(candidate_lineups * 6, 12000)
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

        min_required = min(candidate_lineups, max(200, candidate_lineups // 30))
        if len(lineups) < min_required:
            raise ValueError(
                f"Could not generate enough valid candidate lineups ({len(lineups)}). "
                "Try lower min_salary_floor or a larger player pool."
            )
        return lineups

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
        (
            policy_weights,
            policy_bias,
            policy_mean,
            policy_std,
            training_slates_used,
            training_rows_used,
            training_positive_rate,
        ) = self._fit_policy_for_target(
            source_system=request.source_system,
            season=request.season,
            week=request.week,
            training_start_season=request.training_start_season,
            training_window_slates=request.training_window_slates,
            training_lineups_per_slate=request.training_lineups_per_slate,
            min_training_slates=request.min_training_slates,
            min_training_rows=request.min_training_rows,
            rng=rng,
        )

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

        candidate_lineups = self._generate_candidate_lineups(
            players=target_pool,
            candidate_lineups=request.candidate_lineups,
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

        has_learned_signal = training_rows_used > 0 and float(np.max(np.abs(policy_weights))) > 1e-8
        learned_only = bool(getattr(request, "learned_only", True))
        if not has_learned_signal and learned_only:
            raise ValueError(
                "No learnable signal found for this target slate. "
                "Widen training window or lower minimum training thresholds."
            )

        if has_learned_signal:
            x_norm = (x_candidates - policy_mean) / policy_std
            policy_scores = _sigmoid(x_norm @ policy_weights + policy_bias)
        else:
            # Optional heuristic fallback is only used when learned_only=False.
            policy_scores = np.full(len(candidate_lineups), 0.5, dtype=float)

        composite = np.asarray(policy_scores, dtype=float)
        matchup_stack_rules = self._summarize_matchup_stack_rules(
            candidate_lineups=candidate_lineups,
            policy_scores=policy_scores,
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

        insights = sorted(
            enumerate(policy_weights),
            key=lambda item: abs(float(item[1])),
            reverse=True,
        )[:5]
        discovered_patterns = [
            f"Policy trained on {training_slates_used} slates and {training_rows_used} historical lineups.",
            f"Historical positive lineup rate (top 2% target) = {training_positive_rate:.2%}.",
            (
                "Ranking mode: "
                + ("learned-only policy score." if has_learned_signal else "heuristic fallback (no learned signal).")
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
            for idx, weight in insights:
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
