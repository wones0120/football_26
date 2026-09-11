"""Resolve and persist auditable starting-QB evidence for a slate."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd
from sqlalchemy import create_engine, text

from Database.config import get_connection_string
from .optimizer import restrict_showdown_pool_to_starting_qbs


@dataclass
class StarterLoadResult:
    season: int
    week: int
    slate: str
    rows_written: int
    message: str
    completed_at: datetime


class StartingQBService:
    """Build one canonical QB selection per slate team.

    Confirmed selections supplied by an operator are validated against the canonical
    DraftKings slate pool. Without them, the service prefers explicit QB1 depth-chart
    evidence. The nflreadpy weekly roster currently exposes only a generic QB label,
    so the documented fallback is the unique highest DraftKings FLEX salary among
    active QBs on each team.
    """

    def __init__(self, connection_string: Optional[str] = None) -> None:
        self.connection_string = connection_string or get_connection_string()
        self.engine = create_engine(self.connection_string)

    def derive_starters(
        self,
        season: int,
        week: int,
        slate: str,
        confirmed_starters: Optional[list[dict[str, Any]]] = None,
    ) -> StarterLoadResult:
        completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        candidates = self._load_candidates(season=season, week=week, slate=slate)
        if candidates.empty:
            return StarterLoadResult(
                season=season,
                week=week,
                slate=slate,
                rows_written=0,
                message="No canonical DraftKings QB candidates found for this slate.",
                completed_at=completed_at,
            )

        try:
            prepared = self._apply_confirmed_starters(
                candidates=candidates,
                confirmed_starters=confirmed_starters,
            )
            filtered, evidence = restrict_showdown_pool_to_starting_qbs(
                prepared,
                require_exactly_two_teams=False,
            )
        except ValueError as exc:
            return StarterLoadResult(
                season=season,
                week=week,
                slate=slate,
                rows_written=0,
                message=f"Starting QB validation failed: {exc}",
                completed_at=completed_at,
            )

        starters = filtered[filtered["position"] == "QB"].copy()
        self._persist(
            starters=starters,
            evidence=evidence,
            season=season,
            week=week,
            slate=slate,
            completed_at=completed_at,
        )
        inferred = sum(
            row.get("evidence_tier") == "inferred"
            for row in evidence.get("selected", [])
        )
        qualifier = (
            f" ({inferred} inferred from unique top DraftKings salary)"
            if inferred
            else " (confirmed by QB1 evidence)"
        )
        return StarterLoadResult(
            season=season,
            week=week,
            slate=slate,
            rows_written=len(starters),
            message=f"Stored {len(starters)} starting QBs{qualifier}.",
            completed_at=completed_at,
        )

    @staticmethod
    def _apply_confirmed_starters(
        *,
        candidates: pd.DataFrame,
        confirmed_starters: Optional[list[dict[str, Any]]],
    ) -> pd.DataFrame:
        if not confirmed_starters:
            return candidates

        frame = candidates.copy()
        frame["player_team"] = (
            frame["player_team"].fillna("").astype(str).str.strip().str.upper()
        )
        slate_teams = {team for team in frame["player_team"].unique() if team}
        selections_by_team: dict[str, dict[str, Any]] = {}
        selected_ids: set[str] = set()
        for raw_selection in confirmed_starters:
            selection = dict(raw_selection)
            team = str(selection.get("team") or "").strip().upper()
            player_id = str(selection.get("player_master_id") or "").strip()
            if team in selections_by_team:
                raise ValueError(
                    f"Confirmed starter-QB evidence is ambiguous for {team}: "
                    "more than one selection was supplied."
                )
            if player_id in selected_ids:
                raise ValueError(
                    f"Confirmed starter-QB evidence reuses canonical player ID {player_id}."
                )
            match = frame[
                (frame["player_team"] == team)
                & (frame["player_id"].astype(str) == player_id)
            ]
            if len(match) != 1:
                raise ValueError(
                    f"Confirmed starter-QB evidence for {team} does not match exactly "
                    "one canonical QB in the selected salary slate."
                )
            selections_by_team[team] = selection
            selected_ids.add(player_id)

        supplied_teams = set(selections_by_team)
        if supplied_teams != slate_teams:
            missing = sorted(slate_teams - supplied_teams)
            extra = sorted(supplied_teams - slate_teams)
            details = []
            if missing:
                details.append(f"missing {', '.join(missing)}")
            if extra:
                details.append(f"unexpected {', '.join(extra)}")
            raise ValueError(
                "Confirmed starter-QB evidence must cover every slate team: "
                + "; ".join(details)
                + "."
            )

        frame["is_starting_qb"] = False
        frame["starting_qb_source"] = None
        frame["starting_qb_evidence_tier"] = None
        frame["starting_qb_source_uri"] = None
        frame["starting_qb_observed_at"] = None
        for team, selection in selections_by_team.items():
            player_id = str(selection["player_master_id"])
            selected_mask = (
                (frame["player_team"] == team)
                & (frame["player_id"].astype(str) == player_id)
            )
            frame.loc[selected_mask, "is_starting_qb"] = True
            frame.loc[selected_mask, "starting_qb_source"] = str(selection["source"])
            frame.loc[selected_mask, "starting_qb_evidence_tier"] = "confirmed"
            frame.loc[selected_mask, "starting_qb_source_uri"] = (
                str(selection.get("source_uri") or "").strip() or None
            )
            frame.loc[selected_mask, "starting_qb_observed_at"] = str(
                selection["observed_at"]
            )
        return frame

    def _load_candidates(self, *, season: int, week: int, slate: str) -> pd.DataFrame:
        query = text(
            """
            WITH latest_salary AS (
                SELECT DISTINCT ON (salary.player_master_id)
                    salary.player_master_id AS player_id,
                    salary.player_master_id,
                    salary.player_name AS name,
                    UPPER(salary.position) AS position,
                    UPPER(salary.team) AS player_team,
                    salary.salary
                FROM public.curated_salary salary
                WHERE salary.season = :season
                  AND salary.week = :week
                  AND UPPER(salary.slate) = UPPER(:slate)
                  AND UPPER(salary.position) = 'QB'
                  AND salary.player_master_id IS NOT NULL
                ORDER BY salary.player_master_id,
                    CASE WHEN UPPER(salary.roster_position) = 'FLEX' THEN 0 ELSE 1 END,
                    salary.created_at DESC,
                    salary.curated_salary_id DESC
            )
            SELECT
                salary.*,
                roster.depth_chart_position,
                participation.roster_status,
                (starter.player_master_id IS NOT NULL) AS is_starting_qb,
                starter.source AS starting_qb_source,
                starter.evidence_tier AS starting_qb_evidence_tier,
                starter.evidence_json ->> 'source_uri' AS starting_qb_source_uri,
                starter.evidence_json ->> 'observed_at' AS starting_qb_observed_at
            FROM latest_salary salary
            LEFT JOIN LATERAL (
                SELECT raw.depth_chart_position
                FROM public.raw_nfl_weekly_roster raw
                WHERE raw.season = :season
                  AND raw.week = :week
                  AND UPPER(raw.team) = salary.player_team
                  AND EXISTS (
                      SELECT 1
                      FROM public.player_alias alias
                      WHERE alias.player_master_id = salary.player_master_id
                        AND (
                            (
                                alias.source_system = 'nflreadpy'
                                AND alias.source_key = raw.gsis_id
                            )
                            OR (
                                alias.source_system = 'pfr'
                                AND alias.source_key = raw.pfr_id
                            )
                        )
                  )
                ORDER BY raw.created_at DESC,
                    raw.raw_nfl_weekly_roster_id DESC
                LIMIT 1
            ) roster ON TRUE
            LEFT JOIN LATERAL (
                SELECT participation_row.roster_status
                FROM public.curated_player_game_participation participation_row
                WHERE participation_row.season = :season
                  AND participation_row.week = :week
                  AND participation_row.player_master_id = salary.player_master_id
                  AND UPPER(participation_row.team) = salary.player_team
                ORDER BY participation_row.created_at DESC,
                    participation_row.curated_player_game_participation_id DESC
                LIMIT 1
            ) participation ON TRUE
            LEFT JOIN public.starting_qb_evidence starter
              ON starter.season = :season
             AND starter.week = :week
             AND UPPER(starter.slate) = UPPER(:slate)
             AND UPPER(starter.team) = salary.player_team
             AND starter.player_master_id = salary.player_master_id
            WHERE NOT EXISTS (
                SELECT 1
                FROM public.curated_player_game_participation roster_evidence
                WHERE roster_evidence.season = :season
                  AND roster_evidence.week = :week
            )
            OR UPPER(COALESCE(participation.roster_status, '')) = 'ACT'
            ORDER BY salary.player_team, salary.salary DESC, salary.player_id
            """
        )
        with self.engine.begin() as connection:
            return pd.read_sql(
                query,
                connection,
                params={
                    "season": season,
                    "week": week,
                    "slate": slate,
                },
            )

    def _persist(
        self,
        *,
        starters: pd.DataFrame,
        evidence: dict,
        season: int,
        week: int,
        slate: str,
        completed_at: datetime,
    ) -> None:
        selection_by_id = {
            str(row.get("player_id")): row for row in evidence.get("selected", [])
        }
        rows = []
        for row in starters.to_dict(orient="records"):
            player_id = str(row["player_id"])
            selection = selection_by_id[player_id]
            rows.append(
                {
                    "season": season,
                    "week": week,
                    "slate": slate,
                    "team": str(row["player_team"]),
                    "player_id": player_id,
                    "player_master_id": player_id,
                    "player_name": str(row.get("name") or player_id),
                    "status": "active",
                    "source": str(selection["source"]),
                    "evidence_tier": str(selection["evidence_tier"]),
                    "evidence_json": json.dumps(selection, sort_keys=True),
                    "created_at": completed_at,
                    "updated_at": completed_at,
                }
            )

        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM public.starting_qb_evidence "
                    "WHERE season = :season AND week = :week "
                    "AND UPPER(slate) = UPPER(:slate)"
                ),
                {"season": season, "week": week, "slate": slate},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO public.starting_qb_evidence
                        (season, week, slate, team, player_id, player_master_id,
                         player_name, status, source, evidence_tier,
                         evidence_json, created_at, updated_at)
                    VALUES
                        (:season, :week, :slate, :team, :player_id, :player_master_id,
                         :player_name, :status, :source, :evidence_tier,
                         CAST(:evidence_json AS JSONB), :created_at, :updated_at)
                    """
                ),
                rows,
            )
