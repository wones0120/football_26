"""Deterministic reassessment and repair for participation-source identities."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pandas as pd
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from ..models import PlayerAlias, PlayerMaster, UnresolvedPlayerQueue
from .matching import normalize_name, normalize_position, normalize_team, upsert_alias
from .participation import ParticipationService


PARTICIPATION_IDENTITY_CONTRACT_ID = "participation_identity_reassessment_v1"
PARTICIPATION_SOURCE_TABLES = ("weekly_rosters", "snap_counts")
REPAIR_ACTOR = "participation_identity_reassessment_v1"


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


@dataclass(frozen=True)
class ParticipationIdentityDecision:
    source_table: str
    source_system: str
    source_key: str | None
    unresolved_ids: tuple[str, ...]
    player_master_id: str
    reason: str
    gsis_id: str | None
    alias_name: str
    team: str | None
    position: str | None
    first_seen_season: int | None
    first_seen_week: int | None

    @property
    def queue_rows(self) -> int:
        return len(self.unresolved_ids)


@dataclass(frozen=True)
class ParticipationIdentityAssessment:
    generated_at: str
    registry_rows: int
    relevant_registry_rows: pd.DataFrame
    registry_evidence_sha256: str
    open_rows_before: int
    open_rows_by_table: dict[str, int]
    decisions: tuple[ParticipationIdentityDecision, ...]
    conflicts: tuple[dict[str, Any], ...]
    remaining_rows: int
    remaining_by_table: dict[str, int]

    def report(self) -> dict[str, Any]:
        decision_rows_by_reason: dict[str, int] = defaultdict(int)
        decision_keys_by_reason: dict[str, int] = defaultdict(int)
        for decision in self.decisions:
            decision_rows_by_reason[decision.reason] += decision.queue_rows
            decision_keys_by_reason[decision.reason] += 1
        return {
            "contract_id": PARTICIPATION_IDENTITY_CONTRACT_ID,
            "generated_at": self.generated_at,
            "registry_rows": self.registry_rows,
            "relevant_registry_rows": len(self.relevant_registry_rows),
            "registry_evidence_sha256": self.registry_evidence_sha256,
            "open_rows_before": self.open_rows_before,
            "open_rows_by_table": dict(sorted(self.open_rows_by_table.items())),
            "deterministic_queue_rows": sum(row.queue_rows for row in self.decisions),
            "deterministic_keys": len(self.decisions),
            "decision_rows_by_reason": dict(sorted(decision_rows_by_reason.items())),
            "decision_keys_by_reason": dict(sorted(decision_keys_by_reason.items())),
            "conflict_count": len(self.conflicts),
            "conflict_sample": list(self.conflicts[:25]),
            "remaining_rows": self.remaining_rows,
            "remaining_by_table": dict(sorted(self.remaining_by_table.items())),
            "decision_sample": [
                {
                    "source_table": row.source_table,
                    "source_system": row.source_system,
                    "source_key": row.source_key,
                    "queue_rows": row.queue_rows,
                    "player_master_id": row.player_master_id,
                    "reason": row.reason,
                    "gsis_id": row.gsis_id,
                    "alias_name": row.alias_name,
                    "team": row.team,
                    "position": row.position,
                }
                for row in self.decisions[:25]
            ],
        }


def _registry_crosswalk(
    registry_frame: pd.DataFrame,
    relevant_pfr_ids: set[str],
) -> tuple[dict[str, tuple[str, ...]], pd.DataFrame, str]:
    required = {"pfr_id", "gsis_id"}
    missing = sorted(required - set(registry_frame.columns))
    if missing:
        raise ValueError(f"Player registry is missing required columns: {', '.join(missing)}")

    evidence_columns = [
        column
        for column in (
            "pfr_id",
            "gsis_id",
            "display_name",
            "football_name",
            "position",
            "latest_team",
            "last_season",
        )
        if column in registry_frame.columns
    ]
    relevant = registry_frame[
        registry_frame["pfr_id"].map(_safe_text).isin(relevant_pfr_ids)
    ][evidence_columns].copy()
    for column in relevant.columns:
        relevant[column] = relevant[column].map(_safe_text)
    relevant = relevant.sort_values(evidence_columns, kind="stable").reset_index(drop=True)

    gsis_by_pfr: dict[str, set[str]] = defaultdict(set)
    for row in relevant.to_dict("records"):
        pfr_id = _safe_text(row.get("pfr_id"))
        gsis_id = _safe_text(row.get("gsis_id"))
        if pfr_id and gsis_id:
            gsis_by_pfr[pfr_id].add(gsis_id)
    crosswalk = {
        pfr_id: tuple(sorted(gsis_ids))
        for pfr_id, gsis_ids in sorted(gsis_by_pfr.items())
    }
    stable_evidence = relevant.to_dict("records")
    evidence_sha256 = hashlib.sha256(
        json.dumps(stable_evidence, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return crosswalk, relevant, evidence_sha256


def assess_participation_identities(
    session: Session,
    registry_frame: pd.DataFrame,
) -> ParticipationIdentityAssessment:
    queue_rows = list(
        session.scalars(
            select(UnresolvedPlayerQueue)
            .where(
                and_(
                    UnresolvedPlayerQueue.source_table.in_(PARTICIPATION_SOURCE_TABLES),
                    UnresolvedPlayerQueue.resolution_status == "open",
                )
            )
            .order_by(
                UnresolvedPlayerQueue.source_table,
                UnresolvedPlayerQueue.season,
                UnresolvedPlayerQueue.week,
                UnresolvedPlayerQueue.unresolved_id,
            )
        )
    )
    by_table: dict[str, int] = defaultdict(int)
    for row in queue_rows:
        by_table[row.source_table] += 1

    snap_groups: dict[str, list[UnresolvedPlayerQueue]] = defaultdict(list)
    roster_rows: list[UnresolvedPlayerQueue] = []
    for row in queue_rows:
        if row.source_table == "snap_counts" and row.source_player_key:
            snap_groups[row.source_player_key].append(row)
        elif row.source_table == "weekly_rosters":
            roster_rows.append(row)

    crosswalk, relevant_registry, evidence_sha256 = _registry_crosswalk(
        registry_frame,
        set(snap_groups),
    )
    aliases = list(
        session.scalars(
            select(PlayerAlias).where(PlayerAlias.source_system.in_(("nflreadpy", "pfr")))
        )
    )
    pfr_aliases = {
        row.source_key: row.player_master_id
        for row in aliases
        if row.source_system == "pfr"
    }
    gsis_aliases = {
        row.source_key: row.player_master_id
        for row in aliases
        if row.source_system == "nflreadpy"
    }

    decisions: list[ParticipationIdentityDecision] = []
    conflicts: list[dict[str, Any]] = []
    resolved_ids: set[str] = set()
    for pfr_id, rows in sorted(snap_groups.items()):
        gsis_ids = crosswalk.get(pfr_id, ())
        existing_master_id = pfr_aliases.get(pfr_id)
        crosswalk_master_id = gsis_aliases.get(gsis_ids[0]) if len(gsis_ids) == 1 else None
        if (
            existing_master_id
            and crosswalk_master_id
            and existing_master_id != crosswalk_master_id
        ):
            conflicts.append(
                {
                    "source_table": "snap_counts",
                    "pfr_id": pfr_id,
                    "existing_player_master_id": existing_master_id,
                    "crosswalk_player_master_id": crosswalk_master_id,
                    "gsis_id": gsis_ids[0],
                    "queue_rows": len(rows),
                }
            )
            continue
        if existing_master_id:
            player_master_id = existing_master_id
            reason = "existing_pfr_alias"
            gsis_id = gsis_ids[0] if len(gsis_ids) == 1 else None
        elif len(gsis_ids) == 1 and crosswalk_master_id:
            player_master_id = crosswalk_master_id
            reason = "unique_pfr_gsis_crosswalk"
            gsis_id = gsis_ids[0]
        else:
            continue

        representative = max(
            rows,
            key=lambda row: (row.season or 0, row.week or 0, row.created_at),
        )
        raw = representative.raw_row_json or {}
        alias_name = _safe_text(raw.get("player") or raw.get("player_name"))
        alias_name = alias_name or representative.normalized_name or pfr_id
        decisions.append(
            ParticipationIdentityDecision(
                source_table="snap_counts",
                source_system="pfr",
                source_key=pfr_id,
                unresolved_ids=tuple(sorted(row.unresolved_id for row in rows)),
                player_master_id=player_master_id,
                reason=reason,
                gsis_id=gsis_id,
                alias_name=alias_name,
                team=normalize_team(representative.team),
                position=normalize_position(representative.position),
                first_seen_season=min(
                    (row.season for row in rows if row.season is not None),
                    default=None,
                ),
                first_seen_week=min(
                    (row.week for row in rows if row.week is not None),
                    default=None,
                ),
            )
        )
        resolved_ids.update(row.unresolved_id for row in rows)

    semantic_candidates: dict[tuple[str, str | None, str | None], set[str]] = defaultdict(set)
    for master in session.scalars(select(PlayerMaster)):
        key = (
            master.normalized_name or normalize_name(master.full_name),
            normalize_team(master.primary_team),
            normalize_position(master.position),
        )
        if all(key):
            semantic_candidates[key].add(master.player_master_id)
    semantic_to_master = {
        key: next(iter(player_ids))
        for key, player_ids in semantic_candidates.items()
        if len(player_ids) == 1
    }
    for row in roster_rows:
        if row.source_player_key:
            continue
        key = (
            row.normalized_name,
            normalize_team(row.team),
            normalize_position(row.position),
        )
        player_master_id = semantic_to_master.get(key)
        if not player_master_id:
            continue
        raw = row.raw_row_json or {}
        alias_name = _safe_text(
            raw.get("full_name") or raw.get("player_name") or row.normalized_name
        )
        decisions.append(
            ParticipationIdentityDecision(
                source_table="weekly_rosters",
                source_system="nflreadpy",
                source_key=None,
                unresolved_ids=(row.unresolved_id,),
                player_master_id=player_master_id,
                reason="unique_name_team_position",
                gsis_id=None,
                alias_name=alias_name,
                team=normalize_team(row.team),
                position=normalize_position(row.position),
                first_seen_season=row.season,
                first_seen_week=row.week,
            )
        )
        resolved_ids.add(row.unresolved_id)

    remaining_by_table: dict[str, int] = defaultdict(int)
    for row in queue_rows:
        if row.unresolved_id not in resolved_ids:
            remaining_by_table[row.source_table] += 1
    return ParticipationIdentityAssessment(
        generated_at=datetime.now(UTC).isoformat(),
        registry_rows=len(registry_frame),
        relevant_registry_rows=relevant_registry,
        registry_evidence_sha256=evidence_sha256,
        open_rows_before=len(queue_rows),
        open_rows_by_table=dict(by_table),
        decisions=tuple(decisions),
        conflicts=tuple(conflicts),
        remaining_rows=sum(remaining_by_table.values()),
        remaining_by_table=dict(remaining_by_table),
    )


def apply_participation_identity_repairs(
    session: Session,
    assessment: ParticipationIdentityAssessment,
    *,
    registry_snapshot_id: str,
) -> dict[str, Any]:
    if assessment.conflicts:
        raise RuntimeError("Participation identity conflicts must be resolved before apply")

    resolved_at = datetime.now(UTC).replace(tzinfo=None)
    affected_seasons: set[int] = set()
    aliases_written = 0
    queue_rows_resolved = 0
    for decision in assessment.decisions:
        unresolved_rows = [
            session.get(UnresolvedPlayerQueue, unresolved_id)
            for unresolved_id in decision.unresolved_ids
        ]
        open_rows = [
            row
            for row in unresolved_rows
            if row is not None and row.resolution_status == "open"
        ]
        if len(open_rows) != len(decision.unresolved_ids):
            raise RuntimeError(
                "Participation queue changed after assessment; rerun dry-run before apply"
            )
        if decision.source_key:
            upsert_alias(
                session=session,
                player_master_id=decision.player_master_id,
                source_system=decision.source_system,
                source_key=decision.source_key,
                alias_name=decision.alias_name,
                team=decision.team,
                position=decision.position,
                season=decision.first_seen_season,
                week=decision.first_seen_week,
            )
            aliases_written += 1
        notes = (
            f"{PARTICIPATION_IDENTITY_CONTRACT_ID}; reason={decision.reason}; "
            f"gsis_id={decision.gsis_id or ''}; registry_snapshot_id={registry_snapshot_id}"
        )
        for row in open_rows:
            row.resolution_status = "resolved"
            row.resolved_player_master_id = decision.player_master_id
            row.resolved_by = REPAIR_ACTOR
            row.resolved_at = resolved_at
            row.notes = notes
            session.add(row)
            if row.season is not None:
                affected_seasons.add(row.season)
            queue_rows_resolved += 1

    rebuilds: dict[str, dict[str, int]] = {}
    for season in sorted(affected_seasons):
        rebuilds[str(season)] = ParticipationService(session).rebuild(season=season)
    session.commit()
    open_after = session.scalar(
        select(func.count())
        .select_from(UnresolvedPlayerQueue)
        .where(
            and_(
                UnresolvedPlayerQueue.source_table.in_(PARTICIPATION_SOURCE_TABLES),
                UnresolvedPlayerQueue.resolution_status == "open",
            )
        )
    )
    return {
        "contract_id": PARTICIPATION_IDENTITY_CONTRACT_ID,
        "registry_snapshot_id": registry_snapshot_id,
        "aliases_written": aliases_written,
        "queue_rows_resolved": queue_rows_resolved,
        "open_rows_after": int(open_after or 0),
        "affected_seasons": sorted(affected_seasons),
        "rebuilds": rebuilds,
    }
