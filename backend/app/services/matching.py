from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from Database.dst import normalize_team as normalize_nfl_team
from ..models import PlayerAlias, PlayerMaster


WHITESPACE_RE = re.compile(r"\s+")
NON_ALNUM_RE = re.compile(r"[^a-z0-9\s]")
TEAM_TOKEN_RE = re.compile(r"[A-Z]{2,4}")
TEAM_DEFENSE_POSITIONS = {"D", "DEF", "DEFENSE", "DST", "D/ST"}


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def normalize_name(value: str | None) -> str:
    if not value:
        return ""
    cleaned = NON_ALNUM_RE.sub(" ", value.strip().lower())
    return WHITESPACE_RE.sub(" ", cleaned).strip()


def normalize_team(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = normalize_nfl_team(value)
    return cleaned or None


def normalize_position(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().upper()
    if cleaned in TEAM_DEFENSE_POSITIONS:
        return "DST"
    if "/" in cleaned:
        cleaned = cleaned.split("/", 1)[0]
    return cleaned or None


def parse_opponent_from_game_info(game_info: str | None, team: str | None) -> str | None:
    if not game_info:
        return None
    cleaned = game_info.upper()
    if "@" not in cleaned:
        return None
    left, right = cleaned.split("@", 1)
    left_tokens = TEAM_TOKEN_RE.findall(left)
    right_tokens = TEAM_TOKEN_RE.findall(right)
    left_team = left_tokens[-1] if left_tokens else None
    right_team = right_tokens[0] if right_tokens else None
    if not right_team:
        return None
    if team:
        team_upper = team.upper()
        if left_team and team_upper == left_team:
            return right_team
        if team_upper == right_team:
            return left_team
    return right_team


def create_player_master(
    session: Session,
    full_name: str,
    team: str | None = None,
    position: str | None = None,
    player_master_id: str | None = None,
) -> PlayerMaster:
    now = utcnow_naive()
    record = PlayerMaster(
        player_master_id=player_master_id or str(uuid.uuid4()),
        full_name=full_name.strip(),
        normalized_name=normalize_name(full_name),
        first_name=(full_name.strip().split(" ", 1)[0] if full_name.strip() else None),
        last_name=(full_name.strip().split(" ", 1)[1] if " " in full_name.strip() else None),
        primary_team=normalize_team(team),
        position=normalize_position(position),
        created_at=now,
        updated_at=now,
    )
    session.add(record)
    # Force INSERT so downstream alias writes in the same transaction satisfy FK constraints.
    session.flush([record])
    return record


def upsert_alias(
    session: Session,
    player_master_id: str,
    source_system: str,
    source_key: str,
    alias_name: str,
    team: str | None,
    position: str | None,
    season: int | None,
    week: int | None,
) -> PlayerAlias:
    existing = session.execute(
        select(PlayerAlias).where(
            and_(
                PlayerAlias.source_system == source_system,
                PlayerAlias.source_key == source_key,
            )
        )
    ).scalar_one_or_none()
    now = utcnow_naive()
    if existing:
        existing.player_master_id = player_master_id
        existing.alias_name = alias_name
        existing.normalized_alias = normalize_name(alias_name)
        existing.team = normalize_team(team)
        existing.position = normalize_position(position)
        existing.last_seen_at = now
        return existing
    record = PlayerAlias(
        player_master_id=player_master_id,
        source_system=source_system,
        source_key=source_key,
        alias_name=alias_name,
        normalized_alias=normalize_name(alias_name),
        team=normalize_team(team),
        position=normalize_position(position),
        first_seen_season=season,
        first_seen_week=week,
        last_seen_at=now,
        created_at=now,
    )
    session.add(record)
    # Flush immediately so subsequent lookups in the same transaction can see this key
    # even when Session is configured with autoflush=False.
    session.flush([record])
    return record


def find_player_master_id(
    session: Session,
    source_system: str,
    source_key: str | None,
    name: str | None,
    team: str | None,
    position: str | None,
) -> tuple[str | None, str]:
    norm_name = normalize_name(name)
    norm_team = normalize_team(team)
    norm_position = normalize_position(position)

    def authoritative_alias(ids):
        # Contradictory historical vendor aliases may reference duplicate masters.
        # Require a unique current team/position/name match from roster identity
        # sources; never choose by row order or display name alone.
        from Database.player_identity import _name_keys
        rows = session.scalars(select(PlayerAlias).where(
            PlayerAlias.player_master_id.in_(ids), PlayerAlias.team == norm_team,
            PlayerAlias.position == norm_position,
            PlayerAlias.source_system.in_(("nflreadpy", "pfr", "nfl_official", "official_club")),
        )).all()
        supported = [a for a in rows if _name_keys((name,)) & _name_keys((a.alias_name, a.normalized_alias))]
        matches = {a.player_master_id for a in supported}
        sources = {a.source_system for a in supported}
        return next(iter(matches)) if len(matches) == 1 and len(sources) >= 2 else None

    if source_key:
        alias_by_key = session.execute(
            select(PlayerAlias).where(
                and_(
                    PlayerAlias.source_system == source_system,
                    PlayerAlias.source_key == source_key,
                )
            )
        ).scalar_one_or_none()
        if alias_by_key:
            return alias_by_key.player_master_id, "alias_source_key"

    if norm_position == "DST":
        if not norm_team:
            return None, "dst_team_required"

        team_aliases = session.execute(
            select(PlayerAlias).where(
                and_(
                    PlayerAlias.source_system == source_system,
                    PlayerAlias.team == norm_team,
                )
            )
        ).scalars().all()
        canonical_team_alias_master_ids = {
            alias.player_master_id
            for alias in team_aliases
            if alias.position == "DST"
        }
        if len(canonical_team_alias_master_ids) == 1:
            return canonical_team_alias_master_ids.pop(), "alias_dst_team"
        if len(canonical_team_alias_master_ids) > 1:
            return None, "ambiguous_dst_team_alias"

        legacy_team_alias_master_ids = {
            alias.player_master_id
            for alias in team_aliases
            if normalize_position(alias.position) == "DST"
        }
        if len(legacy_team_alias_master_ids) == 1:
            return legacy_team_alias_master_ids.pop(), "alias_dst_team"
        if len(legacy_team_alias_master_ids) > 1:
            return None, "ambiguous_dst_team_alias"

        team_masters = session.execute(
            select(PlayerMaster).where(PlayerMaster.primary_team == norm_team)
        ).scalars().all()
        canonical_team_master_ids = {
            master.player_master_id
            for master in team_masters
            if master.position == "DST"
        }
        if len(canonical_team_master_ids) == 1:
            return canonical_team_master_ids.pop(), "master_dst_team"
        if len(canonical_team_master_ids) > 1:
            return None, "ambiguous_dst_team_master"

        legacy_team_master_ids = {
            master.player_master_id
            for master in team_masters
            if normalize_position(master.position) == "DST"
        }
        if len(legacy_team_master_ids) == 1:
            return legacy_team_master_ids.pop(), "master_dst_team"
        if len(legacy_team_master_ids) > 1:
            return None, "ambiguous_dst_team_master"

        return None, "unresolved_dst_team"

    if norm_name and norm_team and norm_position:
        alias_exact = session.execute(
            select(PlayerAlias).where(
                and_(
                    PlayerAlias.source_system == source_system,
                    PlayerAlias.normalized_alias == norm_name,
                    PlayerAlias.team == norm_team,
                    PlayerAlias.position == norm_position,
                )
            )
        ).scalars().all()
        alias_master_ids = {alias.player_master_id for alias in alias_exact}
        if len(alias_master_ids) == 1:
            return alias_master_ids.pop(), "alias_name_team_position"
        if len(alias_master_ids) > 1:
            supported = authoritative_alias(alias_master_ids)
            return (supported, "source_backed_alias_conflict_resolved") if supported else (None, "ambiguous_alias_name_team_position")

    if norm_name and norm_team and norm_position:
        cross_source_aliases = session.execute(
            select(PlayerAlias).where(
                and_(
                    PlayerAlias.normalized_alias == norm_name,
                    PlayerAlias.team == norm_team,
                    PlayerAlias.position == norm_position,
                )
            )
        ).scalars().all()
        cross_source_master_ids = {
            alias.player_master_id for alias in cross_source_aliases
        }
        if len(cross_source_master_ids) == 1:
            return (
                cross_source_master_ids.pop(),
                "alias_cross_source_name_team_position",
            )
        if len(cross_source_master_ids) > 1:
            supported = authoritative_alias(cross_source_master_ids)
            return (supported, "source_backed_alias_conflict_resolved") if supported else (None, "ambiguous_cross_source_name_team_position")

    # Salary feeds vary accents, punctuation and suffixes. Reuse sourced
    # aliases before considering master records, including duplicate masters.
    from Database.player_identity import MasterIdentity, choose_identity, _name_keys
    if norm_name and norm_team and norm_position:
        wanted = _name_keys((name,))
        scoped_aliases = session.scalars(select(PlayerAlias).where(
            PlayerAlias.team == norm_team, PlayerAlias.position == norm_position,
        )).all()
        matches = {a.player_master_id for a in scoped_aliases
                   if wanted & _name_keys((a.alias_name, a.normalized_alias))}
        if len(matches) == 1:
            return matches.pop(), "alias_normalized_name_team_position"
        if len(matches) > 1:
            supported = authoritative_alias(matches)
            return (supported, "source_backed_alias_conflict_resolved") if supported else (None, "ambiguous_alias_name_team_position")

    if norm_name and norm_team and norm_position:
        master_exact = session.execute(
            select(PlayerMaster).where(
                and_(
                    PlayerMaster.normalized_name == norm_name,
                    PlayerMaster.primary_team == norm_team,
                    PlayerMaster.position == norm_position,
                )
            )
        ).scalars().all()
        if len(master_exact) == 1:
            return master_exact[0].player_master_id, "master_name_team_position"

    # One fallback policy is shared by ingest and preparation. It requires
    # corroborating position/team evidence and leaves ambiguity unresolved.
    masters = session.scalars(select(PlayerMaster)).all()
    decision = choose_identity(player_name=name, team=team, position=position,
        masters=[MasterIdentity(player_id=m.player_master_id, full_name=m.full_name,
            normalized_name=m.normalized_name, team=m.primary_team or "", position=m.position or "") for m in masters if normalize_team(m.primary_team) == norm_team])
    return (decision.player_id, decision.reason) if decision.player_id else (None, "unresolved")
