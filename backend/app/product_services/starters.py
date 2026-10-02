"""Resolve and persist auditable starting-QB evidence for a slate."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from Database.config import get_connection_string
from Database.dst import canonical_team_sql, normalize_team
from .optimizer import restrict_showdown_pool_to_starting_qbs
from .replay import parse_slate_lock


@dataclass
class StarterLoadResult:
    season: int
    week: int
    slate: str
    rows_written: int
    message: str
    completed_at: datetime
    candidates: list[dict[str, Any]] = field(default_factory=list)


class StartingQBService:
    """Build one canonical QB selection per slate team.

    Operator selections, including sourced provisional inferences, are validated
    against the canonical DraftKings slate pool. Without them, the service
    prefers explicit QB1 depth-chart evidence. The nflreadpy weekly roster
    currently exposes only a generic QB label,
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
        candidate_summaries = self._candidate_summaries(candidates)
        if candidates.empty:
            return StarterLoadResult(
                season=season,
                week=week,
                slate=slate,
                rows_written=0,
                message="No canonical DraftKings QB candidates found for this slate.",
                completed_at=completed_at,
                candidates=candidate_summaries,
            )

        try:
            depth_selections, depth_conflicts, depth_note = self._depth_chart_selections(
                candidates=candidates, season=season, week=week, slate=slate,
            )
            operator_teams = {str(row.get("team") or "").upper() for row in (confirmed_starters or [])}
            stored_teams = {
                str(row.get("player_team") or "").upper()
                for row in candidates.to_dict(orient="records")
                if row.get("is_starting_qb")
                and (
                    str(row.get("starting_qb_evidence_tier") or "").lower() == "confirmed"
                    or (
                        str(row.get("starting_qb_evidence_tier") or "").lower() == "inferred"
                        and str(row.get("starting_qb_source") or "").startswith("provisional_")
                        and not str(row.get("starting_qb_source") or "").startswith("provisional_nflverse_depth_chart")
                        and bool(row.get("starting_qb_source_uri"))
                    )
                )
            }
            protected_teams = operator_teams | stored_teams
            unresolved_depth = sorted(set(depth_conflicts) - protected_teams)
            if unresolved_depth:
                return StarterLoadResult(
                    season=season, week=week, slate=slate, rows_written=0,
                    message=("Nflverse QB depth-chart evidence conflicts with the salary pool for: "
                             + ", ".join(unresolved_depth) + ". Review the listed QBs."),
                    completed_at=completed_at,
                    candidates=[row for row in candidate_summaries if row["team"] in unresolved_depth],
                )
            prepared = self._apply_confirmed_starters(
                candidates=candidates,
                confirmed_starters=[
                    *(row for row in depth_selections if row["team"] not in protected_teams),
                    *(confirmed_starters or []),
                ],
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
                candidates=self._unresolved_candidate_summaries(candidates),
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
        inferred = sum(row.get("evidence_tier") == "inferred" for row in evidence.get("selected", []))
        provisional = sum(
            row.get("evidence_tier") == "inferred"
            and str(row.get("source") or "").startswith("provisional_")
            for row in evidence.get("selected", [])
        )
        qualifier = (
            f" ({inferred - provisional} inferred from unique top DraftKings salary"
            + (f", {provisional} provisional choices" if provisional else "")
            + ")"
            if inferred
            else " (confirmed by QB1 evidence)"
        )
        return StarterLoadResult(
            season=season,
            week=week,
            slate=slate,
            rows_written=len(starters),
            message=f"Stored {len(starters)} starting QBs{qualifier}." + (f" {depth_note}" if depth_note else ""),
            completed_at=completed_at,
        )

    def _depth_chart_selections(
        self, *, candidates: pd.DataFrame, season: int, week: int, slate: str,
    ) -> tuple[list[dict[str, Any]], list[str], str]:
        """Capture current nflverse QB ranks and match QB1 by GSIS ID before lock."""
        if "gsis_id" not in candidates.columns or "game_info" not in candidates.columns:
            return [], [], ""
        lock_at = parse_slate_lock(candidates["game_info"])
        now = datetime.now(timezone.utc)
        if lock_at is None or lock_at <= now:
            return [], [], ""

        from ..services.source_capture import (
            DEFAULT_NFLREADPY_LICENSE,
            SourceCaptureService,
            fetch_nflreadpy_dataset,
        )

        try:
            depth, version = fetch_nflreadpy_dataset(
                "depth_charts", season=season, week=None,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            return [], [], f"Nflverse depth charts unavailable; existing evidence/salary fallback used ({exc})."
        required = {"dt", "team", "gsis_id", "pos_abb", "pos_rank"}
        if not required.issubset(depth.columns):
            return [], [], "Nflverse depth charts lack required QB identity/rank fields; existing evidence/salary fallback used."
        qbs = depth.loc[depth["pos_abb"].fillna("").astype(str).str.upper().eq("QB")].copy()
        qbs["observed_at"] = pd.to_datetime(qbs["dt"], utc=True, errors="coerce")
        qbs = qbs.loc[qbs["observed_at"].notna() & qbs["observed_at"].le(now) & qbs["observed_at"].le(lock_at)].copy()
        qbs["team_key"] = qbs["team"].map(normalize_team)
        qbs["pos_rank"] = pd.to_numeric(qbs["pos_rank"], errors="coerce")
        if qbs.empty:
            return [], [], "Nflverse depth charts have no current QB rows; existing evidence/salary fallback used."
        latest = qbs.groupby("team_key")["observed_at"].transform("max")
        qbs = qbs.loc[qbs["observed_at"].eq(latest)].copy()
        with Session(self.engine) as session:
            capture = SourceCaptureService(session).capture_dataframe(
                qbs[["dt", "team", "gsis_id", "pos_abb", "pos_rank"]].sort_values(
                    ["team", "pos_rank", "gsis_id"]
                ),
                artifact_name=f"nflverse_qb_depth_{season}_{week}_{slate}.csv",
                source_system="nflreadpy", dataset="qb_depth_charts",
                season=season, week=week, slate=slate,
                source_license=DEFAULT_NFLREADPY_LICENSE,
                source_uri=f"nflreadpy://depth_charts/{season}",
                slate_lock_at=lock_at,
                metadata={"nflreadpy_version": version, "provider_latest_dt": str(qbs["dt"].max())},
            )
        candidate_teams = set(candidates["player_team"].fillna("").astype(str).str.upper())
        out_salary_qbs = self._load_out_salary_qbs(season=season, week=week, slate=slate)
        selections: list[dict[str, Any]] = []
        conflicts: list[str] = []
        for team in sorted(candidate_teams - {""}):
            team_rows = qbs.loc[qbs["team_key"].eq(team) & qbs["pos_rank"].eq(1)]
            if len(team_rows) != 1:
                conflicts.append(team)
                continue
            depth_row = team_rows.iloc[0]
            match = candidates.loc[
                candidates["player_team"].fillna("").astype(str).str.upper().eq(team)
                & candidates["gsis_id"].fillna("").astype(str).eq(str(depth_row["gsis_id"]))
            ]
            source = "provisional_nflverse_depth_chart_qb1"
            note = f"GSIS {depth_row['gsis_id']}; rank 1; snapshot {capture.snapshot.snapshot_id}"
            if len(match) != 1:
                out_qb = out_salary_qbs.get(str(depth_row["gsis_id"]))
                if not out_qb or out_qb["team"] != team:
                    conflicts.append(team)
                    continue
                # An OUT QB1 is stale starter evidence. Advance only when the
                # unique next depth rank agrees with the unique top eligible salary.
                backups = qbs.loc[qbs["team_key"].eq(team) & qbs["pos_rank"].gt(1)]
                next_rank = backups["pos_rank"].min() if not backups.empty else None
                next_rows = backups.loc[backups["pos_rank"].eq(next_rank)] if next_rank is not None else backups
                team_candidates = candidates.loc[
                    candidates["player_team"].fillna("").astype(str).str.upper().eq(team)
                ]
                top_salary = pd.to_numeric(team_candidates["salary"], errors="coerce").max()
                top_rows = team_candidates.loc[pd.to_numeric(
                    team_candidates["salary"], errors="coerce").eq(top_salary)]
                if len(next_rows) != 1 or len(top_rows) != 1 or str(top_rows.iloc[0]["gsis_id"]) != str(next_rows.iloc[0]["gsis_id"]):
                    conflicts.append(team)
                    continue
                depth_row = next_rows.iloc[0]
                match = top_rows
                source = "provisional_nflverse_depth_chart_next_active_qb"
                note = (f"QB1 GSIS {out_qb['gsis_id']} salary status {out_qb['status']}; "
                        f"next rank {int(next_rank)} GSIS {depth_row['gsis_id']} agrees with unique top "
                        f"eligible salary; snapshot {capture.snapshot.snapshot_id}")
            selections.append({
                "team": team,
                "player_master_id": str(match.iloc[0]["player_id"]),
                "source": source,
                "source_uri": f"nflreadpy://depth_charts/{season}",
                "observed_at": str(depth_row["dt"]),
                "evidence_tier": "inferred",
                "note": note,
            })
        return selections, conflicts, f"QB depth-chart snapshot: {capture.snapshot.snapshot_id}."

    def _load_out_salary_qbs(self, *, season: int, week: int, slate: str) -> dict[str, dict[str, str]]:
        """Match latest OUT salary rows to GSIS IDs through canonical aliases."""
        with self.engine.connect() as connection:
            rows = connection.execute(text(f"""
                WITH latest_salary AS (
                    SELECT DISTINCT ON (salary.player_master_id)
                        salary.player_master_id, salary.team, salary.player_status
                    FROM public.curated_salary salary
                    WHERE salary.season = :season AND salary.week = :week
                      AND UPPER(salary.slate) = UPPER(:slate)
                      AND UPPER(salary.position) = 'QB'
                      AND salary.player_master_id IS NOT NULL
                    ORDER BY salary.player_master_id,
                             CASE WHEN UPPER(salary.roster_position) = 'FLEX' THEN 0 ELSE 1 END,
                             salary.created_at DESC,
                             salary.curated_salary_id DESC
                )
                SELECT alias.source_key AS gsis_id,
                       {canonical_team_sql('salary.team')} AS team,
                       UPPER(salary.player_status) AS status
                FROM latest_salary salary
                JOIN public.player_alias alias
                  ON alias.player_master_id = salary.player_master_id
                 AND alias.source_system = 'nflreadpy'
                 AND alias.source_key IS NOT NULL
                 AND UPPER(alias.position) = 'QB'
                 AND {canonical_team_sql('alias.team')} = {canonical_team_sql('salary.team')}
                WHERE UPPER(salary.player_status) IN
                      ('OUT', 'O', 'IR', 'PUP', 'NFI', 'INACTIVE', 'SUSPENDED')
            """), {"season": season, "week": week, "slate": slate}).mappings()
            return {str(row["gsis_id"]): dict(row) for row in rows}

    @staticmethod
    def _candidate_summaries(candidates: pd.DataFrame) -> list[dict[str, Any]]:
        """Return the exact canonical choices needed to resolve an ambiguous team."""
        if candidates.empty:
            return []
        rows: list[dict[str, Any]] = []
        for row in candidates.to_dict(orient="records"):
            salary = pd.to_numeric(row.get("salary"), errors="coerce")
            salary = 0.0 if pd.isna(salary) else float(salary)
            value = row.get("is_starting_qb")
            is_stored_starter = (
                bool(value)
                if isinstance(value, bool)
                else str(value).strip().lower() in {"1", "true", "yes"}
            )
            rows.append(
                {
                    "player_master_id": str(row.get("player_id") or ""),
                    "player_name": str(row.get("name") or row.get("player_id") or ""),
                    "team": str(row.get("player_team") or "").upper(),
                    "salary": salary,
                    "depth_chart_position": (
                        str(row.get("depth_chart_position"))
                        if pd.notna(row.get("depth_chart_position"))
                        else None
                    ),
                    "roster_status": (
                        str(row.get("roster_status"))
                        if pd.notna(row.get("roster_status"))
                        else None
                    ),
                    "is_stored_starter": is_stored_starter,
                    "stored_source": (
                        str(row.get("starting_qb_source"))
                        if pd.notna(row.get("starting_qb_source"))
                        else None
                    ),
                    "stored_evidence_tier": (
                        str(row.get("starting_qb_evidence_tier"))
                        if pd.notna(row.get("starting_qb_evidence_tier"))
                        else None
                    ),
                }
            )
        return sorted(rows, key=lambda row: (row["team"], -row["salary"], row["player_name"]))

    @classmethod
    def _unresolved_candidate_summaries(cls, candidates: pd.DataFrame) -> list[dict[str, Any]]:
        """Limit operator review to teams that cannot be deterministically selected."""
        if candidates.empty:
            return []
        unresolved_teams: set[str] = set()
        frame = candidates.copy()
        frame["player_team"] = frame["player_team"].fillna("").astype(str).str.upper()
        for team, team_qbs in frame.groupby("player_team"):
            stored = team_qbs.get("is_starting_qb", pd.Series(False, index=team_qbs.index)).map(
                lambda value: bool(value) if isinstance(value, bool) else str(value).strip().lower() in {"1", "true", "yes"}
            )
            inferred = team_qbs.get(
                "starting_qb_evidence_tier", pd.Series("", index=team_qbs.index)
            ).fillna("").astype(str).str.lower().eq("inferred")
            provisional = team_qbs.get(
                "starting_qb_source", pd.Series("", index=team_qbs.index)
            ).fillna("").astype(str).str.startswith("provisional_")
            stored &= ~inferred | provisional
            depth = team_qbs.get("depth_chart_position", pd.Series("", index=team_qbs.index)).fillna("").astype(str).str.upper().isin({"QB1", "STARTER", "STARTING"})
            if int((stored | depth).sum()) == 1:
                continue
            salaries = pd.to_numeric(team_qbs.get("salary", 0), errors="coerce").fillna(0.0)
            if salaries.max() <= 0 or int(salaries.eq(salaries.max()).sum()) != 1:
                unresolved_teams.add(str(team))
        return [
            row for row in cls._candidate_summaries(frame)
            if row["team"] in unresolved_teams
        ]

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
            evidence_tier = str(selection.get("evidence_tier") or "confirmed").lower()
            if evidence_tier not in {"confirmed", "inferred"}:
                raise ValueError(f"Invalid starting-QB evidence tier for {team}: {evidence_tier}")
            if (str(selection.get("source") or "").startswith("provisional_")
                    and evidence_tier != "inferred"):
                raise ValueError(f"Provisional starting-QB evidence for {team} must be inferred")
            if (evidence_tier == "inferred"
                    and str(selection.get("source") or "").startswith("provisional_")
                    and not str(selection.get("source_uri") or "").strip()):
                raise ValueError(f"Provisional starting-QB evidence for {team} requires a source URI")
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
            if evidence_tier == "inferred" and not str(selection.get("source") or "").startswith("provisional_"):
                team_qbs = frame[frame["player_team"] == team]
                top = team_qbs[team_qbs["salary"] == team_qbs["salary"].max()]
                if len(top) != 1 or str(top.iloc[0]["player_id"]) != player_id:
                    raise ValueError(
                        f"Inferred starting-QB evidence for {team} differs from the unique top salary; "
                        "use a sourced provisional_ selection for an override."
                    )
            selections_by_team[team] = selection
            selected_ids.add(player_id)

        supplied_teams = set(selections_by_team)
        extra = sorted(supplied_teams - slate_teams)
        if extra:
            raise ValueError(
                "Confirmed starter-QB evidence includes teams outside the selected slate: "
                + ", ".join(extra)
                + "."
            )

        for team, selection in selections_by_team.items():
            team_mask = frame["player_team"] == team
            frame.loc[team_mask, "is_starting_qb"] = False
            frame.loc[team_mask, "starting_qb_source"] = None
            frame.loc[team_mask, "starting_qb_evidence_tier"] = None
            frame.loc[team_mask, "starting_qb_source_uri"] = None
            frame.loc[team_mask, "starting_qb_observed_at"] = None
            player_id = str(selection["player_master_id"])
            selected_mask = (
                (frame["player_team"] == team)
                & (frame["player_id"].astype(str) == player_id)
            )
            frame.loc[selected_mask, "is_starting_qb"] = True
            frame.loc[selected_mask, "starting_qb_source"] = str(selection["source"])
            frame.loc[selected_mask, "starting_qb_evidence_tier"] = str(selection.get("evidence_tier") or "confirmed").lower()
            frame.loc[selected_mask, "starting_qb_source_uri"] = (
                str(selection.get("source_uri") or "").strip() or None
            )
            frame.loc[selected_mask, "starting_qb_observed_at"] = str(
                selection["observed_at"]
            )
            frame.loc[selected_mask, "starting_qb_note"] = str(selection.get("note") or "")
        return frame

    def _load_candidates(self, *, season: int, week: int, slate: str) -> pd.DataFrame:
        roster_team = canonical_team_sql("raw.team")
        participation_team = canonical_team_sql("participation_row.team")
        query = text(
            f"""
            WITH latest_salary AS (
                SELECT DISTINCT ON (salary.player_master_id)
                    salary.player_master_id AS player_id,
                    salary.player_master_id,
                    salary.player_name AS name,
                    UPPER(salary.position) AS position,
                    UPPER(salary.team) AS player_team,
                    salary.salary,
                    salary.game_info,
                    salary.player_status
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
                nflverse_id.gsis_id,
                roster.depth_chart_position,
                participation.roster_status,
                (starter.player_master_id IS NOT NULL) AS is_starting_qb,
                starter.source AS starting_qb_source,
                starter.evidence_tier AS starting_qb_evidence_tier,
                starter.evidence_json ->> 'source_uri' AS starting_qb_source_uri,
                starter.evidence_json ->> 'observed_at' AS starting_qb_observed_at,
                starter.evidence_json ->> 'note' AS starting_qb_note
            FROM latest_salary salary
            LEFT JOIN LATERAL (
                SELECT alias.source_key AS gsis_id
                FROM public.player_alias alias
                WHERE alias.player_master_id = salary.player_master_id
                  AND alias.source_system = 'nflreadpy'
                  AND {canonical_team_sql('alias.team')} = salary.player_team
                  AND UPPER(alias.position) = 'QB'
                ORDER BY alias.created_at DESC
                LIMIT 1
            ) nflverse_id ON TRUE
            LEFT JOIN LATERAL (
                SELECT raw.depth_chart_position
                FROM public.raw_nfl_weekly_roster raw
                WHERE raw.season = :season
                  AND raw.week = :week
                  AND {roster_team} = salary.player_team
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
                  AND {participation_team} = salary.player_team
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
            WHERE UPPER(COALESCE(salary.player_status, '')) NOT IN
                  ('OUT', 'O', 'IR', 'PUP', 'NFI', 'INACTIVE', 'SUSPENDED')
              AND (NOT EXISTS (
                SELECT 1
                FROM public.curated_player_game_participation roster_evidence
                WHERE roster_evidence.season = :season
                  AND roster_evidence.week = :week
            )
              OR UPPER(COALESCE(participation.roster_status, '')) = 'ACT')
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
