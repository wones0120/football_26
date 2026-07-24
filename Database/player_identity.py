"""Deterministic salary-to-player identity repair with explicit quarantine."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy import inspect, text

from .dst import normalize_team


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SUFFIXES = frozenset({"jr", "sr", "ii", "iii", "iv", "v"})
_UNKNOWN_POSITIONS = frozenset({"", "CPT", "FLEX", "UTIL"})
_POSITION_ALIASES = {
    "HB": "RB",
    "FB": "RB",
    "FL": "WR",
    "SE": "WR",
}


@dataclass(frozen=True)
class MasterIdentity:
    player_id: str
    full_name: str
    normalized_name: str = ""
    name_norm: str = ""
    team: str = ""
    position: str = ""
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class IdentityDecision:
    player_id: str | None
    reason: str
    candidate_player_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SalaryIdentityRepairResult:
    salary_rows_seen: int = 0
    salary_rows_resolved: int = 0
    salary_rows_quarantined: int = 0
    no_match_rows: int = 0
    ambiguous_rows: int = 0
    masters_updated: int = 0


def normalize_player_name(name: object) -> str:
    """Normalize punctuation and accents while preserving token boundaries."""
    value = unicodedata.normalize("NFKD", str(name or ""))
    value = "".join(character for character in value if not unicodedata.combining(character))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def strip_name_suffix(name: object) -> str:
    parts = normalize_player_name(name).split()
    if parts and parts[-1] in _SUFFIXES:
        parts.pop()
    return " ".join(parts)


def normalize_position(position: object) -> str:
    value = str(position or "").strip().upper()
    if value in {"D", "DEF"}:
        return "DST"
    return _POSITION_ALIASES.get(value, value)


def _name_keys(values: Iterable[object]) -> set[str]:
    keys: set[str] = set()
    for value in values:
        normalized = strip_name_suffix(value)
        if normalized:
            keys.add(normalized)
            keys.add(normalized.replace(" ", ""))
    return keys


def _identity_name_keys(identity: MasterIdentity) -> set[str]:
    return _name_keys(
        (
            identity.full_name,
            identity.normalized_name,
            identity.name_norm,
            *identity.aliases,
        )
    )


def choose_identity(
    *,
    player_name: object,
    team: object,
    position: object,
    masters: Iterable[MasterIdentity],
) -> IdentityDecision:
    """Resolve only unique, explainable matches; return ambiguity otherwise."""
    salary_keys = _name_keys((player_name,))
    if not salary_keys:
        return IdentityDecision(None, "missing_name")

    candidates = [identity for identity in masters if salary_keys & _identity_name_keys(identity)]
    candidates_by_id = {identity.player_id: identity for identity in candidates}
    candidates = list(candidates_by_id.values())
    candidate_ids = tuple(sorted(candidates_by_id))
    if not candidates:
        return IdentityDecision(None, "no_match")
    if len(candidates) == 1:
        return IdentityDecision(candidates[0].player_id, "unique_name", candidate_ids)

    salary_team = normalize_team(str(team or ""))
    salary_position = normalize_position(position)
    team_matches = [
        identity
        for identity in candidates
        if salary_team and normalize_team(identity.team) == salary_team
    ]
    position_matches = [
        identity
        for identity in candidates
        if salary_position
        and normalize_position(identity.position) not in _UNKNOWN_POSITIONS
        and normalize_position(identity.position) == salary_position
    ]
    position_ids = {identity.player_id for identity in position_matches}
    team_position_matches = [identity for identity in team_matches if identity.player_id in position_ids]

    if len(team_position_matches) == 1:
        return IdentityDecision(team_position_matches[0].player_id, "unique_team_position", candidate_ids)
    if len(position_matches) == 1:
        return IdentityDecision(position_matches[0].player_id, "unique_position", candidate_ids)
    if len(team_matches) == 1:
        return IdentityDecision(team_matches[0].player_id, "unique_team", candidate_ids)
    return IdentityDecision(None, "ambiguous", candidate_ids)


def _aliases(value: Any) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item) for item in value if item)
    if not value:
        return ()
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return ()
    return tuple(str(item) for item in parsed if item) if isinstance(parsed, list) else ()


def _quarantine_id(source_schema: str, source_record_key: str) -> str:
    payload = f"{source_schema}.curated_salary:{source_record_key}".encode()
    return f"salary-identity:{hashlib.sha256(payload).hexdigest()[:32]}"


def repair_salary_identities(
    engine,
    *,
    source_schema: str = "public",
    target_schema: str = "target",
) -> SalaryIdentityRepairResult:
    """Repair unresolved non-DST salaries and persist every non-match for audit."""
    for identifier in (source_schema, target_schema):
        if not _IDENTIFIER_RE.match(identifier):
            raise ValueError(f"Unsafe schema identifier: {identifier!r}")
    source = f'"{source_schema}"'
    target = f'"{target_schema}"'

    with engine.begin() as conn:
        inspector = inspect(conn)
        required = (
            inspector.has_table("curated_salary", schema=source_schema)
            and inspector.has_table("player_master", schema=source_schema)
        )
        if not required:
            return SalaryIdentityRepairResult()
        if not inspector.has_table("identity_quarantine", schema=target_schema):
            raise RuntimeError(f"{target_schema}.identity_quarantine must exist before identity repair")

        master_rows = conn.execute(
            text(
                f"""
                SELECT player_master_id::text AS player_id, full_name,
                       COALESCE(normalized_name, '') AS normalized_name,
                       COALESCE(name_norm, '') AS name_norm,
                       COALESCE(primary_team, '') AS team,
                       COALESCE(position, '') AS position,
                       COALESCE(aliases, '[]'::jsonb) AS aliases
                FROM {source}.player_master
                """
            )
        ).mappings().all()
        masters = [
            MasterIdentity(
                player_id=str(row["player_id"]),
                full_name=str(row["full_name"] or ""),
                normalized_name=str(row["normalized_name"] or ""),
                name_norm=str(row["name_norm"] or ""),
                team=str(row["team"] or ""),
                position=str(row["position"] or ""),
                aliases=_aliases(row["aliases"]),
            )
            for row in master_rows
        ]
        salary_rows = conn.execute(
            text(
                f"""
                SELECT curated_salary_id::text AS source_record_key,
                       source_system, source_player_key, season, week, slate,
                       player_name, team, position, created_at
                FROM {source}.curated_salary
                WHERE player_master_id IS NULL
                  AND upper(trim(COALESCE(NULLIF(position, ''), roster_position, '')))
                      NOT IN ('D', 'DEF', 'DST')
                ORDER BY season, week, curated_salary_id
                """
            )
        ).mappings().all()

        decisions: dict[tuple[str, str, str], IdentityDecision] = {}
        resolved_player_ids: set[str] = set()
        resolved = 0
        quarantined = 0
        no_match = 0
        ambiguous = 0

        for row in salary_rows:
            name = str(row["player_name"] or "")
            team = normalize_team(str(row["team"] or ""))
            position = normalize_position(row["position"])
            key = (strip_name_suffix(name), team, position)
            decision = decisions.get(key)
            if decision is None:
                decision = choose_identity(
                    player_name=name,
                    team=team,
                    position=position,
                    masters=masters,
                )
                decisions[key] = decision

            source_record_key = str(row["source_record_key"])
            if decision.player_id:
                update = conn.execute(
                    text(
                        f"""
                        UPDATE {source}.curated_salary
                        SET player_master_id = :player_id,
                            normalized_name = COALESCE(NULLIF(normalized_name, ''), :normalized_name)
                        WHERE curated_salary_id::text = :source_record_key
                          AND player_master_id IS NULL
                        """
                    ),
                    {
                        "player_id": decision.player_id,
                        "normalized_name": strip_name_suffix(name),
                        "source_record_key": source_record_key,
                    },
                )
                resolved += int(update.rowcount or 0)
                conn.execute(
                    text(
                        f"""
                        UPDATE {target}.identity_quarantine
                        SET status = 'resolved', resolved_player_id = :player_id,
                            resolution_reason = :reason, resolved_at = now(), updated_at = now()
                        WHERE source_schema = :source_schema
                          AND source_table = 'curated_salary'
                          AND source_record_key = :source_record_key
                          AND status = 'open'
                        """
                    ),
                    {
                        "player_id": decision.player_id,
                        "reason": decision.reason,
                        "source_schema": source_schema,
                        "source_record_key": source_record_key,
                    },
                )
                resolved_player_ids.add(decision.player_id)
                continue

            reason = decision.reason if decision.reason in {"ambiguous", "missing_name"} else "no_match"
            ambiguous += int(reason == "ambiguous")
            no_match += int(reason != "ambiguous")
            conn.execute(
                text(
                    f"""
                    INSERT INTO {target}.identity_quarantine
                    (identity_quarantine_id, entity_type, source_schema, source_table,
                     source_record_key, source_system, season, week, slate, source_player_key,
                     display_name, team_id, position, reason_code, candidate_player_ids,
                     status, first_seen_at, updated_at)
                    VALUES
                    (:quarantine_id, 'player', :source_schema, 'curated_salary',
                     :source_record_key, :source_system, :season, :week, :slate, :source_player_key,
                     :display_name, :team_id, :position, :reason_code,
                     CAST(:candidate_player_ids AS jsonb), 'open', now(), now())
                    ON CONFLICT (source_schema, source_table, source_record_key) DO UPDATE SET
                        source_system = EXCLUDED.source_system,
                        season = EXCLUDED.season,
                        week = EXCLUDED.week,
                        slate = EXCLUDED.slate,
                        source_player_key = EXCLUDED.source_player_key,
                        display_name = EXCLUDED.display_name,
                        team_id = EXCLUDED.team_id,
                        position = EXCLUDED.position,
                        reason_code = EXCLUDED.reason_code,
                        candidate_player_ids = EXCLUDED.candidate_player_ids,
                        status = 'open',
                        resolved_player_id = NULL,
                        resolution_reason = NULL,
                        resolved_at = NULL,
                        updated_at = now()
                    """
                ),
                {
                    "quarantine_id": _quarantine_id(source_schema, source_record_key),
                    "source_schema": source_schema,
                    "source_record_key": source_record_key,
                    "source_system": row["source_system"],
                    "season": row["season"],
                    "week": row["week"],
                    "slate": row["slate"],
                    "source_player_key": row["source_player_key"],
                    "display_name": name,
                    "team_id": team,
                    "position": position,
                    "reason_code": reason,
                    "candidate_player_ids": json.dumps(decision.candidate_player_ids),
                },
            )
            quarantined += 1

        latest_context_rows = conn.execute(
            text(
                f"""
                SELECT DISTINCT ON (player_master_id)
                       player_master_id::text AS player_id,
                       upper(trim(COALESCE(team, ''))) AS team,
                       upper(trim(COALESCE(NULLIF(position, ''), roster_position, ''))) AS position
                FROM {source}.curated_salary
                WHERE player_master_id = ANY(:player_ids)
                ORDER BY player_master_id, season DESC, week DESC, created_at DESC,
                         curated_salary_id DESC
                """
            ),
            {"player_ids": sorted(resolved_player_ids)},
        ).mappings().all() if resolved_player_ids else []

        masters_updated = 0
        for context in latest_context_rows:
            player_id = str(context["player_id"])
            team = normalize_team(str(context["team"] or ""))
            position = normalize_position(context["position"])
            if position in _UNKNOWN_POSITIONS:
                position = ""
            if not team and not position:
                continue
            update = conn.execute(
                text(
                    f"""
                    UPDATE {source}.player_master
                    SET primary_team = CASE WHEN :team <> '' THEN :team ELSE primary_team END,
                        position = CASE WHEN :position <> '' THEN :position ELSE position END,
                        updated_at = now()
                    WHERE player_master_id::text = :player_id
                      AND (
                        (:team <> '' AND COALESCE(primary_team, '') IS DISTINCT FROM :team)
                        OR (:position <> '' AND COALESCE(position, '') IS DISTINCT FROM :position)
                      )
                    """
                ),
                {"player_id": player_id, "team": team, "position": position},
            )
            masters_updated += int(update.rowcount or 0)

    return SalaryIdentityRepairResult(
        salary_rows_seen=len(salary_rows),
        salary_rows_resolved=resolved,
        salary_rows_quarantined=quarantined,
        no_match_rows=no_match,
        ambiguous_rows=ambiguous,
        masters_updated=masters_updated,
    )
