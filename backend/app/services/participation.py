from __future__ import annotations

from collections import defaultdict, deque
from itertools import groupby
from statistics import fmean
from typing import Any, Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import (
    CuratedPlayerGameParticipation,
    PlayerAlias,
    PlayerMaster,
    RawNflSchedule,
    RawNflSnapCount,
    RawNflWeeklyRoster,
    RawNflWeeklyStat,
    TeamGameAvailabilityFeature,
)
from .matching import normalize_name, normalize_position, normalize_team


INACTIVE_ROSTER_STATUSES = {
    "DEV",
    "EXE",
    "INA",
    "RES",
    "SUS",
}

BOX_SCORE_ACTIVITY_FIELDS = {
    "attempts",
    "carries",
    "completions",
    "fantasy_points",
    "fantasy_points_ppr",
    "field_goal_attempts",
    "field_goals_made",
    "interceptions",
    "passing_attempts",
    "passing_tds",
    "passing_yards",
    "receptions",
    "receiving_tds",
    "receiving_yards",
    "rushing_tds",
    "rushing_yards",
    "targets",
    "xp_attempts",
    "xp_made",
}
BOX_SCORE_ACTIVITY_PREFIXES = ("def_", "fg_", "kick_", "punt_", "special_")


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    text_value = str(value).strip()
    if not text_value:
        return None
    is_percent = text_value.endswith("%")
    if is_percent:
        text_value = text_value[:-1]
    try:
        result = float(text_value)
    except (TypeError, ValueError):
        return None
    if is_percent or result > 1.5:
        result /= 100.0
    return max(0.0, result)


def _safe_int(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _has_box_score_activity(payload: dict[str, Any] | None) -> bool:
    for key, value in (payload or {}).items():
        normalized_key = str(key).strip().lower()
        if normalized_key not in BOX_SCORE_ACTIVITY_FIELDS and not normalized_key.startswith(
            BOX_SCORE_ACTIVITY_PREFIXES
        ):
            continue
        try:
            if abs(float(value or 0)) > 1e-12:
                return True
        except (TypeError, ValueError):
            continue
    return False


def infer_participation_status(
    *,
    total_snaps: int,
    box_score_activity: bool,
    roster_status: str | None,
    team_has_snap_coverage: bool,
) -> tuple[str, str]:
    """Classify player-game participation without treating missing source data as a DNP."""
    if total_snaps > 0:
        return "played_confirmed", "snap_count"
    if box_score_activity:
        return "played_inferred", "box_score_activity"
    if (roster_status or "").strip().upper() in INACTIVE_ROSTER_STATUSES:
        return "did_not_play", "inactive_roster_status"
    if team_has_snap_coverage:
        return "did_not_play", "roster_without_snap"
    return "unknown", "no_participation_evidence"


def build_lagged_availability_rows(
    participation_rows: Iterable[dict[str, Any]],
    schedule_rows: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build target-game features using only participation from earlier games."""
    participation = sorted(
        participation_rows,
        key=lambda row: (
            int(row["season"]),
            int(row["week"]),
            str(row["game_id"]),
            str(row["player_master_id"]),
        ),
    )
    history: dict[tuple[str, str, str], deque[float]] = defaultdict(lambda: deque(maxlen=4))
    game_impacts: dict[tuple[int, int, str, str], dict[str, Any]] = {}

    for row in participation:
        status = str(row.get("participation_status") or "unknown")
        if status == "unknown":
            continue
        season = int(row["season"])
        week = int(row["week"])
        game_id = str(row["game_id"])
        team = str(row["team"])
        player_id = str(row["player_master_id"])
        impact = game_impacts.setdefault(
            (season, week, game_id, team),
            {
                "offense_missing_share": 0.0,
                "defense_missing_share": 0.0,
                "offense_missing_count": 0,
                "defense_missing_count": 0,
            },
        )
        for side, share_field in (
            ("offense", "offense_snap_share"),
            ("defense", "defense_snap_share"),
        ):
            history_key = (player_id, team, side)
            actual = _safe_float(row.get(share_field)) or 0.0
            prior_shares = history[history_key]
            if prior_shares:
                expected = fmean(prior_shares)
                missing = max(0.0, expected - actual)
                impact[f"{side}_missing_share"] += missing
                if expected >= 0.25 and actual <= 0.01:
                    impact[f"{side}_missing_count"] += 1
            prior_shares.append(actual)

    schedule = sorted(
        schedule_rows,
        key=lambda row: (int(row["season"]), int(row["week"]), str(row["game_id"]), str(row["team"])),
    )
    previous_by_team: dict[tuple[int, str], dict[str, Any]] = {}
    output: list[dict[str, Any]] = []
    for _game_key, game_rows_iter in groupby(
        schedule,
        key=lambda row: (int(row["season"]), int(row["week"]), str(row["game_id"])),
    ):
        game_rows = list(game_rows_iter)
        # Read both teams' prior state before either team is advanced to this game.
        for row in game_rows:
            season = int(row["season"])
            week = int(row["week"])
            game_id = str(row["game_id"])
            team = str(row["team"])
            opponent = str(row["opponent"])
            team_prior = previous_by_team.get((season, team))
            opponent_prior = previous_by_team.get((season, opponent))
            output.append(
                {
                    "season": season,
                    "week": week,
                    "game_id": game_id,
                    "team": team,
                    "opponent": opponent,
                    "team_offense_missing_share_lag1": float(
                        (team_prior or {}).get("offense_missing_share", 0.0)
                    ),
                    "team_defense_missing_share_lag1": float(
                        (team_prior or {}).get("defense_missing_share", 0.0)
                    ),
                    "team_offense_missing_count_lag1": int(
                        (team_prior or {}).get("offense_missing_count", 0)
                    ),
                    "team_defense_missing_count_lag1": int(
                        (team_prior or {}).get("defense_missing_count", 0)
                    ),
                    "opponent_offense_missing_share_lag1": float(
                        (opponent_prior or {}).get("offense_missing_share", 0.0)
                    ),
                    "opponent_defense_missing_share_lag1": float(
                        (opponent_prior or {}).get("defense_missing_share", 0.0)
                    ),
                    "opponent_offense_missing_count_lag1": int(
                        (opponent_prior or {}).get("offense_missing_count", 0)
                    ),
                    "opponent_defense_missing_count_lag1": int(
                        (opponent_prior or {}).get("defense_missing_count", 0)
                    ),
                    "team_source_game_id": (team_prior or {}).get("game_id"),
                    "team_source_week": (team_prior or {}).get("week"),
                    "opponent_source_game_id": (opponent_prior or {}).get("game_id"),
                    "opponent_source_week": (opponent_prior or {}).get("week"),
                }
            )

        for row in game_rows:
            season = int(row["season"])
            week = int(row["week"])
            game_id = str(row["game_id"])
            team = str(row["team"])
            current_key = (season, week, game_id, team)
            current_impact = dict(game_impacts.get(current_key, {}))
            current_impact.update({"game_id": game_id, "week": week})
            previous_by_team[(season, team)] = current_impact
    return output


class ParticipationService:
    def __init__(self, session: Session):
        self.session = session

    def rebuild(self, *, season: int) -> dict[str, int]:
        roster_rows = self.session.execute(
            select(RawNflWeeklyRoster)
            .where(RawNflWeeklyRoster.season == season)
            .order_by(RawNflWeeklyRoster.created_at, RawNflWeeklyRoster.raw_nfl_weekly_roster_id)
        ).scalars().all()
        snap_rows = self.session.execute(
            select(RawNflSnapCount)
            .where(RawNflSnapCount.season == season)
            .order_by(RawNflSnapCount.created_at, RawNflSnapCount.raw_nfl_snap_count_id)
        ).scalars().all()

        # Latest row per natural key wins in Silver while Bronze snapshots remain immutable.
        latest_roster: dict[tuple[Any, ...], RawNflWeeklyRoster] = {}
        for row in roster_rows:
            if (row.game_type or "REG").upper() not in {"REG", "POST"}:
                continue
            identity = row.gsis_id or row.pfr_id or f"{row.player_name}|{row.position}"
            latest_roster[(row.week, row.team, row.game_type, identity)] = row
        latest_snaps: dict[tuple[Any, ...], RawNflSnapCount] = {}
        for row in snap_rows:
            if (row.game_type or "REG").upper() not in {"REG", "POST"}:
                continue
            latest_snaps[(row.week, row.team, row.game_id, row.pfr_player_id)] = row

        alias_rows = self.session.execute(
            select(PlayerAlias).where(PlayerAlias.source_system.in_(["nflreadpy", "pfr"]))
        ).scalars().all()
        gsis_to_master = {
            row.source_key: row.player_master_id for row in alias_rows if row.source_system == "nflreadpy"
        }
        pfr_to_master = {
            row.source_key: row.player_master_id for row in alias_rows if row.source_system == "pfr"
        }
        semantic_candidates: dict[tuple[str, str | None, str | None], set[str]] = defaultdict(set)
        for master in self.session.execute(select(PlayerMaster)).scalars():
            semantic_key = (
                master.normalized_name or normalize_name(master.full_name),
                normalize_team(master.primary_team),
                normalize_position(master.position),
            )
            if all(semantic_key):
                semantic_candidates[semantic_key].add(master.player_master_id)
        semantic_to_master = {
            key: next(iter(player_ids))
            for key, player_ids in semantic_candidates.items()
            if len(player_ids) == 1
        }

        weekly_stats = self.session.execute(
            select(RawNflWeeklyStat).where(RawNflWeeklyStat.season == season)
        ).scalars().all()
        box_activity = {
            (row.week, row.team, row.player_id): _has_box_score_activity(row.raw_row_json)
            for row in weekly_stats
            if row.player_id
        }

        schedule_models = self.session.execute(
            select(RawNflSchedule).where(RawNflSchedule.season == season)
        ).scalars().all()
        team_schedule: dict[tuple[int, str], dict[str, Any]] = {}
        schedule_rows: list[dict[str, Any]] = []
        seen_schedule: set[tuple[int, str, str]] = set()
        for row in schedule_models:
            if row.week is None or not row.game_id:
                continue
            game_type = str(row.game_type or (row.raw_row_json or {}).get("game_type") or "REG").upper()
            if game_type not in {"REG", "POST"}:
                continue
            home = normalize_team(row.home_team)
            away = normalize_team(row.away_team)
            if not home or not away:
                continue
            for team, opponent in ((home, away), (away, home)):
                key = (int(row.week), team)
                payload = {
                    "season": season,
                    "week": int(row.week),
                    "game_id": row.game_id,
                    "game_type": game_type,
                    "team": team,
                    "opponent": opponent,
                }
                team_schedule[key] = payload
                schedule_key = (int(row.week), row.game_id, team)
                if schedule_key not in seen_schedule:
                    seen_schedule.add(schedule_key)
                    schedule_rows.append(payload)

        snap_by_player: dict[tuple[int, str, str], RawNflSnapCount] = {}
        snap_game_by_team: dict[tuple[int, str], RawNflSnapCount] = {}
        for row in latest_snaps.values():
            if not row.team or not row.pfr_player_id:
                continue
            snap_by_player[(row.week, row.team, row.pfr_player_id)] = row
            snap_game_by_team[(row.week, row.team)] = row

        participation_by_key: dict[tuple[int, str, str, str], dict[str, Any]] = {}
        for roster in latest_roster.values():
            if not roster.team:
                continue
            player_master_id = (
                gsis_to_master.get(roster.gsis_id or "")
                or pfr_to_master.get(roster.pfr_id or "")
            )
            if not player_master_id:
                player_master_id = semantic_to_master.get(
                    (
                        normalize_name(roster.player_name),
                        normalize_team(roster.team),
                        normalize_position(roster.position),
                    )
                )
            if not player_master_id:
                continue
            snap = snap_by_player.get((roster.week, roster.team, roster.pfr_id or ""))
            schedule = team_schedule.get((roster.week, roster.team))
            game_id = (snap.game_id if snap else None) or (schedule or {}).get("game_id")
            if not game_id:
                continue
            opponent = (snap.opponent if snap else None) or (schedule or {}).get("opponent")
            total_snaps = sum(
                value or 0
                for value in (
                    snap.offense_snaps if snap else None,
                    snap.defense_snaps if snap else None,
                    snap.st_snaps if snap else None,
                )
            )
            has_box_activity = bool(
                box_activity.get((roster.week, roster.team, roster.gsis_id))
            )
            status, reason = infer_participation_status(
                total_snaps=total_snaps,
                box_score_activity=has_box_activity,
                roster_status=roster.roster_status,
                team_has_snap_coverage=(roster.week, roster.team) in snap_game_by_team,
            )
            payload = {
                "season": season,
                "week": roster.week,
                "game_id": game_id,
                "game_type": (snap.game_type if snap else None) or roster.game_type,
                "player_master_id": player_master_id,
                "player_name": roster.player_name or (snap.player_name if snap else None),
                "team": roster.team,
                "opponent": opponent,
                "position": normalize_position(roster.position or (snap.position if snap else None)),
                "roster_status": roster.roster_status,
                "participation_status": status,
                "participation_reason": reason,
                "offense_snaps": snap.offense_snaps if snap else None,
                "offense_snap_share": snap.offense_pct if snap else None,
                "defense_snaps": snap.defense_snaps if snap else None,
                "defense_snap_share": snap.defense_pct if snap else None,
                "st_snaps": snap.st_snaps if snap else None,
                "st_snap_share": snap.st_pct if snap else None,
                "box_score_activity": has_box_activity,
                "roster_ingest_run_id": roster.ingest_run_id,
                "snap_ingest_run_id": snap.ingest_run_id if snap else None,
            }
            participation_by_key[(roster.week, str(game_id), player_master_id, roster.team)] = payload

        # Preserve participants omitted from the weekly roster snapshot when their PFR ID resolves.
        for snap in latest_snaps.values():
            if not snap.team or not snap.pfr_player_id or not snap.game_id:
                continue
            player_master_id = pfr_to_master.get(snap.pfr_player_id)
            if not player_master_id:
                continue
            key = (snap.week, snap.game_id, player_master_id, snap.team)
            if key in participation_by_key:
                continue
            total_snaps = sum(value or 0 for value in (snap.offense_snaps, snap.defense_snaps, snap.st_snaps))
            status, reason = infer_participation_status(
                total_snaps=total_snaps,
                box_score_activity=False,
                roster_status=None,
                team_has_snap_coverage=True,
            )
            participation_by_key[key] = {
                "season": season,
                "week": snap.week,
                "game_id": snap.game_id,
                "game_type": snap.game_type,
                "player_master_id": player_master_id,
                "player_name": snap.player_name,
                "team": snap.team,
                "opponent": snap.opponent,
                "position": normalize_position(snap.position),
                "roster_status": None,
                "participation_status": status,
                "participation_reason": reason,
                "offense_snaps": snap.offense_snaps,
                "offense_snap_share": snap.offense_pct,
                "defense_snaps": snap.defense_snaps,
                "defense_snap_share": snap.defense_pct,
                "st_snaps": snap.st_snaps,
                "st_snap_share": snap.st_pct,
                "box_score_activity": False,
                "roster_ingest_run_id": None,
                "snap_ingest_run_id": snap.ingest_run_id,
            }

        participation_payloads = list(participation_by_key.values())
        availability_payloads = build_lagged_availability_rows(
            participation_payloads,
            schedule_rows,
        )
        self.session.execute(
            delete(CuratedPlayerGameParticipation).where(
                CuratedPlayerGameParticipation.season == season
            )
        )
        self.session.execute(
            delete(TeamGameAvailabilityFeature).where(
                TeamGameAvailabilityFeature.season == season
            )
        )
        if participation_payloads:
            self.session.bulk_insert_mappings(
                CuratedPlayerGameParticipation,
                participation_payloads,
            )
        if availability_payloads:
            self.session.bulk_insert_mappings(
                TeamGameAvailabilityFeature,
                availability_payloads,
            )
        self.session.flush()
        return {
            "participation_rows": len(participation_payloads),
            "availability_rows": len(availability_payloads),
        }
