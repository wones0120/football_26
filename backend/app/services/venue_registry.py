"""Versioned venue registry and deterministic nflverse game mapping."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import (
    CuratedGameVenue,
    RawNflSchedule,
    VenueGameOverride,
    VenueRegistryRecord,
)


VENUE_REGISTRY_CONTRACT_ID = "nfl_venue_registry_v1"
DEFAULT_VENUE_REGISTRY_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "venue_registry_v1.json"
)
ROOF_CLASSIFICATIONS = {"outdoor", "fixed_indoor", "retractable"}
MAPPING_STATUSES = {"resolved", "unresolved", "ambiguous"}


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _canonical_sha256(payload: dict[str, Any]) -> str:
    rendered = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(rendered).hexdigest()


def _require_text(payload: dict[str, Any], field: str, *, context: str) -> str:
    value = _safe_text(payload.get(field))
    if not value:
        raise ValueError(f"{context}.{field} is required")
    return value


def _optional_text(payload: dict[str, Any], field: str) -> str | None:
    return _safe_text(payload.get(field)) or None


def _record_db_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "registry_record_id": payload["registry_record_id"],
        "venue_id": payload["venue_id"],
        "registry_version": int(payload["registry_version"]),
        "canonical_name": payload["canonical_name"],
        "effective_from_season": int(payload["effective_from_season"]),
        "effective_to_season": payload.get("effective_to_season"),
        "latitude": float(payload["latitude"]),
        "longitude": float(payload["longitude"]),
        "timezone": payload["timezone"],
        "default_roof": payload["default_roof"],
        "country_code": payload["country_code"],
        "source_system": payload.get("source_system"),
        "source_venue_id": payload.get("source_venue_id"),
        "source_evidence_uri": payload.get("source_evidence_uri"),
        "coordinate_source_uri": payload["coordinate_source_uri"],
        "review_notes": payload["review_notes"],
        "review_classifications_json": list(
            payload.get("review_classifications_json") or []
        ),
        "definition_sha256": _canonical_sha256(payload),
    }


def _override_db_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "override_id": payload["override_id"],
        "game_id": payload["game_id"],
        "decision_version": int(payload["decision_version"]),
        "registry_record_id": payload["registry_record_id"],
        "reason": payload["reason"],
        "evidence_uri": payload["evidence_uri"],
        "definition_sha256": _canonical_sha256(payload),
    }


@dataclass(frozen=True)
class VenueRegistrySeed:
    contract_id: str
    registry_version: int
    reviewed_at: str
    records: tuple[dict[str, Any], ...]
    overrides: tuple[dict[str, Any], ...]


def load_venue_registry_seed(
    path: Path | str = DEFAULT_VENUE_REGISTRY_PATH,
) -> VenueRegistrySeed:
    seed_path = Path(path)
    payload = json.loads(seed_path.read_text(encoding="utf-8"))
    contract_id = _require_text(payload, "contract_id", context="registry")
    if contract_id != VENUE_REGISTRY_CONTRACT_ID:
        raise ValueError(
            f"unsupported venue registry contract {contract_id!r}; "
            f"expected {VENUE_REGISTRY_CONTRACT_ID!r}"
        )
    registry_version = int(payload.get("registry_version") or 0)
    if registry_version < 1:
        raise ValueError("registry.registry_version must be positive")
    reviewed_at = _require_text(payload, "reviewed_at", context="registry")

    raw_records = payload.get("venues")
    if not isinstance(raw_records, list) or not raw_records:
        raise ValueError("registry.venues must be a non-empty list")
    records: list[dict[str, Any]] = []
    record_ids: set[str] = set()
    identity_versions: set[tuple[str, int]] = set()
    for index, raw_record in enumerate(raw_records):
        if not isinstance(raw_record, dict):
            raise ValueError(f"registry.venues[{index}] must be an object")
        context = f"registry.venues[{index}]"
        record = dict(raw_record)
        record_id = _require_text(record, "registry_record_id", context=context)
        venue_id = _require_text(record, "venue_id", context=context)
        version = int(record.get("registry_version") or 0)
        expected_record_id = f"{venue_id}:v{version}"
        if version < 1:
            raise ValueError(f"{context}.registry_version must be positive")
        if record_id != expected_record_id:
            raise ValueError(
                f"{context}.registry_record_id must be {expected_record_id!r}"
            )
        if record_id in record_ids:
            raise ValueError(f"duplicate registry_record_id {record_id!r}")
        identity_key = (venue_id, version)
        if identity_key in identity_versions:
            raise ValueError(f"duplicate venue/version {identity_key!r}")
        record_ids.add(record_id)
        identity_versions.add(identity_key)

        record["canonical_name"] = _require_text(
            record, "canonical_name", context=context
        )
        from_season = int(record.get("effective_from_season") or 0)
        to_season_raw = record.get("effective_to_season")
        to_season = int(to_season_raw) if to_season_raw is not None else None
        if from_season < 1920:
            raise ValueError(f"{context}.effective_from_season is invalid")
        if to_season is not None and to_season < from_season:
            raise ValueError(f"{context} has an inverted effective season range")
        record["effective_from_season"] = from_season
        record["effective_to_season"] = to_season

        latitude = float(record.get("latitude"))
        longitude = float(record.get("longitude"))
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError(f"{context} has invalid coordinates")
        record["latitude"] = latitude
        record["longitude"] = longitude
        timezone_name = _require_text(record, "timezone", context=context)
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"{context}.timezone is not an IANA timezone") from exc
        record["timezone"] = timezone_name
        roof = _require_text(record, "default_roof", context=context)
        if roof not in ROOF_CLASSIFICATIONS:
            raise ValueError(f"{context}.default_roof is invalid")
        record["default_roof"] = roof
        country_code = _require_text(record, "country_code", context=context).upper()
        if len(country_code) != 2:
            raise ValueError(f"{context}.country_code must have two letters")
        record["country_code"] = country_code

        source_system = _optional_text(record, "source_system")
        source_venue_id = _optional_text(record, "source_venue_id")
        if bool(source_system) != bool(source_venue_id):
            raise ValueError(
                f"{context}.source_system and source_venue_id must be set together"
            )
        record["source_system"] = source_system
        record["source_venue_id"] = source_venue_id
        record["source_evidence_uri"] = _optional_text(record, "source_evidence_uri")
        record["coordinate_source_uri"] = _require_text(
            record, "coordinate_source_uri", context=context
        )
        record["review_notes"] = _require_text(record, "review_notes", context=context)
        classifications = record.get("review_classifications_json") or []
        if not isinstance(classifications, list) or not all(
            isinstance(item, str) and item.strip() for item in classifications
        ):
            raise ValueError(f"{context}.review_classifications_json must be strings")
        record["review_classifications_json"] = sorted(set(classifications))
        records.append(record)

    raw_overrides = payload.get("game_overrides") or []
    if not isinstance(raw_overrides, list):
        raise ValueError("registry.game_overrides must be a list")
    overrides: list[dict[str, Any]] = []
    override_ids: set[str] = set()
    override_versions: set[tuple[str, int]] = set()
    for index, raw_override in enumerate(raw_overrides):
        if not isinstance(raw_override, dict):
            raise ValueError(f"registry.game_overrides[{index}] must be an object")
        context = f"registry.game_overrides[{index}]"
        override = dict(raw_override)
        game_id = _require_text(override, "game_id", context=context)
        decision_version = int(override.get("decision_version") or 0)
        if decision_version < 1:
            raise ValueError(f"{context}.decision_version must be positive")
        expected_override_id = f"{game_id}:v{decision_version}"
        override_id = _require_text(override, "override_id", context=context)
        if override_id != expected_override_id:
            raise ValueError(f"{context}.override_id must be {expected_override_id!r}")
        if override_id in override_ids:
            raise ValueError(f"duplicate override_id {override_id!r}")
        decision_key = (game_id, decision_version)
        if decision_key in override_versions:
            raise ValueError(f"duplicate override version {decision_key!r}")
        override_ids.add(override_id)
        override_versions.add(decision_key)
        registry_record_id = _require_text(
            override, "registry_record_id", context=context
        )
        if registry_record_id not in record_ids:
            raise ValueError(
                f"{context}.registry_record_id does not reference a registry venue"
            )
        override.update(
            {
                "game_id": game_id,
                "decision_version": decision_version,
                "registry_record_id": registry_record_id,
                "reason": _require_text(override, "reason", context=context),
                "evidence_uri": _require_text(
                    override, "evidence_uri", context=context
                ),
            }
        )
        overrides.append(override)

    return VenueRegistrySeed(
        contract_id=contract_id,
        registry_version=registry_version,
        reviewed_at=reviewed_at,
        records=tuple(sorted(records, key=lambda item: item["registry_record_id"])),
        overrides=tuple(
            sorted(
                overrides,
                key=lambda item: (item["game_id"], item["decision_version"]),
            )
        ),
    )


def _effective_for_season(record: dict[str, Any], season: int) -> bool:
    return int(record["effective_from_season"]) <= season and (
        record.get("effective_to_season") is None
        or season <= int(record["effective_to_season"])
    )


@dataclass(frozen=True)
class VenueRegistryAssessment:
    generated_at: str
    season_start: int
    season_end: int
    source_rows: int
    latest_games: int
    skipped_without_game_key: int
    seed: VenueRegistrySeed
    rows: tuple[dict[str, Any], ...]

    def report(self) -> dict[str, Any]:
        status_counts: dict[str, int] = defaultdict(int)
        method_counts: dict[str, int] = defaultdict(int)
        unresolved_games: list[str] = []
        ambiguous_games: list[str] = []
        neutral_games = 0
        neutral_games_without_override: list[str] = []
        for row in self.rows:
            status_counts[row["mapping_status"]] += 1
            method_counts[row["mapping_method"]] += 1
            if row["mapping_status"] == "unresolved":
                unresolved_games.append(row["game_id"])
            elif row["mapping_status"] == "ambiguous":
                ambiguous_games.append(row["game_id"])
            evidence = row["evidence_json"]
            if evidence.get("location") == "Neutral":
                neutral_games += 1
                if row["mapping_method"] != "reviewed_game_override":
                    neutral_games_without_override.append(row["game_id"])

        source_alias_conflicts: list[dict[str, Any]] = []
        for source_key, records in _source_alias_conflicts(
            self.seed.records,
            season_start=self.season_start,
            season_end=self.season_end,
        ):
            source_alias_conflicts.append(
                {
                    "source_system": source_key[0],
                    "source_venue_id": source_key[1],
                    "registry_record_ids": sorted(
                        record["registry_record_id"] for record in records
                    ),
                }
            )
        return {
            "contract_id": self.seed.contract_id,
            "registry_version": self.seed.registry_version,
            "registry_reviewed_at": self.seed.reviewed_at,
            "generated_at": self.generated_at,
            "season_start": self.season_start,
            "season_end": self.season_end,
            "source_rows": self.source_rows,
            "latest_games": self.latest_games,
            "skipped_without_game_key": self.skipped_without_game_key,
            "registry_records": len(self.seed.records),
            "reviewed_game_overrides": len(self.seed.overrides),
            "rows_ready": len(self.rows),
            "mapping_status_counts": dict(sorted(status_counts.items())),
            "mapping_method_counts": dict(sorted(method_counts.items())),
            "unresolved_games": sorted(unresolved_games),
            "ambiguous_games": sorted(ambiguous_games),
            "neutral_games": neutral_games,
            "neutral_games_without_override": sorted(neutral_games_without_override),
            "source_alias_conflicts": source_alias_conflicts,
            "acceptance_ready": (
                len(self.rows) == self.latest_games
                and not unresolved_games
                and not ambiguous_games
                and not neutral_games_without_override
                and not source_alias_conflicts
            ),
        }


def _source_alias_conflicts(
    records: tuple[dict[str, Any], ...],
    *,
    season_start: int,
    season_end: int,
) -> list[tuple[tuple[str, str], list[dict[str, Any]]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        source_system = record.get("source_system")
        source_venue_id = record.get("source_venue_id")
        if not source_system or not source_venue_id:
            continue
        if int(record["effective_from_season"]) > season_end:
            continue
        effective_to = record.get("effective_to_season")
        if effective_to is not None and int(effective_to) < season_start:
            continue
        grouped[(source_system, source_venue_id)].append(record)

    conflicts: list[tuple[tuple[str, str], list[dict[str, Any]]]] = []
    for source_key, candidates in grouped.items():
        overlapping: set[str] = set()
        for season in range(season_start, season_end + 1):
            effective = [
                record for record in candidates if _effective_for_season(record, season)
            ]
            if len(effective) > 1:
                overlapping.update(record["registry_record_id"] for record in effective)
        if overlapping:
            conflicts.append(
                (
                    source_key,
                    [
                        record
                        for record in candidates
                        if record["registry_record_id"] in overlapping
                    ],
                )
            )
    return sorted(conflicts, key=lambda item: item[0])


def assess_venue_registry(
    session: Session,
    *,
    season_start: int,
    season_end: int,
    seed_path: Path | str = DEFAULT_VENUE_REGISTRY_PATH,
) -> VenueRegistryAssessment:
    if season_start > season_end:
        raise ValueError("season_start must be less than or equal to season_end")
    seed = load_venue_registry_seed(seed_path)
    source_rows = list(
        session.scalars(
            select(RawNflSchedule)
            .where(
                RawNflSchedule.season >= season_start,
                RawNflSchedule.season <= season_end,
            )
            .order_by(
                RawNflSchedule.created_at,
                RawNflSchedule.raw_nfl_schedule_id,
            )
        )
    )
    latest_by_game: dict[str, RawNflSchedule] = {}
    skipped_without_game_key = 0
    for schedule in source_rows:
        if not schedule.game_id or schedule.week is None:
            skipped_without_game_key += 1
            continue
        latest_by_game[schedule.game_id] = schedule

    records_by_id = {
        record["registry_record_id"]: record for record in seed.records
    }
    overrides_by_game: dict[str, dict[str, Any]] = {}
    for override in seed.overrides:
        overrides_by_game[override["game_id"]] = override
    records_by_source: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in seed.records:
        if record.get("source_system") and record.get("source_venue_id"):
            records_by_source[
                (record["source_system"], record["source_venue_id"])
            ].append(record)

    rows: list[dict[str, Any]] = []
    for game_id, schedule in sorted(latest_by_game.items()):
        raw = schedule.raw_row_json or {}
        source_venue_id = _safe_text(raw.get("stadium_id")) or None
        location = _safe_text(raw.get("location")) or None
        source_stadium_name = _safe_text(schedule.stadium) or None
        override = overrides_by_game.get(game_id)
        candidates: list[dict[str, Any]]
        if override:
            override_record = records_by_id[override["registry_record_id"]]
            candidates = (
                [override_record]
                if _effective_for_season(override_record, schedule.season)
                else []
            )
            mapping_method = (
                "reviewed_game_override"
                if candidates
                else "override_outside_effective_range"
            )
        elif source_venue_id:
            candidates = [
                record
                for record in records_by_source.get(("pfr", source_venue_id), [])
                if _effective_for_season(record, schedule.season)
            ]
            mapping_method = "source_venue_id"
        else:
            candidates = []
            mapping_method = "missing_source_venue_id"

        if len(candidates) == 1:
            mapping_status = "resolved"
            registry_record_id = candidates[0]["registry_record_id"]
        elif len(candidates) > 1:
            mapping_status = "ambiguous"
            registry_record_id = None
            mapping_method = "conflicting_registry_records"
        else:
            mapping_status = "unresolved"
            registry_record_id = None
            if source_venue_id and not override:
                mapping_method = "no_effective_registry_record"

        evidence_json: dict[str, Any] = {
            "source_schedule_system": schedule.source_system,
            "source_venue_id_system": "pfr",
            "source_venue_id": source_venue_id,
            "source_stadium_name_diagnostic_only": source_stadium_name,
            "location": location,
            "home_team": _safe_text(schedule.home_team) or None,
            "away_team": _safe_text(schedule.away_team) or None,
        }
        if override:
            evidence_json.update(
                {
                    "override_id": override["override_id"],
                    "override_reason": override["reason"],
                    "override_evidence_uri": override["evidence_uri"],
                }
            )
        if mapping_status != "resolved":
            evidence_json["quarantine_reason"] = mapping_method
        rows.append(
            {
                "game_id": game_id,
                "season": schedule.season,
                "week": int(schedule.week),
                "mapping_status": mapping_status,
                "mapping_method": mapping_method,
                "source_venue_id": source_venue_id,
                "registry_record_id": registry_record_id,
                "evidence_json": evidence_json,
                "candidate_registry_record_ids_json": sorted(
                    record["registry_record_id"] for record in candidates
                ),
                "source_ingest_run_id": schedule.ingest_run_id,
                "raw_nfl_schedule_id": schedule.raw_nfl_schedule_id,
            }
        )

    return VenueRegistryAssessment(
        generated_at=datetime.now(UTC).isoformat(),
        season_start=season_start,
        season_end=season_end,
        source_rows=len(source_rows),
        latest_games=len(latest_by_game),
        skipped_without_game_key=skipped_without_game_key,
        seed=seed,
        rows=tuple(rows),
    )


def apply_venue_registry(
    session: Session,
    assessment: VenueRegistryAssessment,
) -> dict[str, Any]:
    registry_created = 0
    registry_existing = 0
    for record in assessment.seed.records:
        values = _record_db_payload(record)
        existing = session.get(VenueRegistryRecord, values["registry_record_id"])
        if existing:
            if existing.definition_sha256 != values["definition_sha256"]:
                raise ValueError(
                    f"registry record {existing.registry_record_id!r} changed in place; "
                    "add a new registry_version instead"
                )
            registry_existing += 1
            continue
        session.add(VenueRegistryRecord(**values))
        registry_created += 1
    session.flush()

    overrides_created = 0
    overrides_existing = 0
    for override in assessment.seed.overrides:
        values = _override_db_payload(override)
        existing = session.get(VenueGameOverride, values["override_id"])
        if existing:
            if existing.definition_sha256 != values["definition_sha256"]:
                raise ValueError(
                    f"venue override {existing.override_id!r} changed in place; "
                    "add a new decision_version instead"
                )
            overrides_existing += 1
            continue
        session.add(VenueGameOverride(**values))
        overrides_created += 1
    session.flush()

    session.execute(
        delete(CuratedGameVenue).where(
            CuratedGameVenue.season >= assessment.season_start,
            CuratedGameVenue.season <= assessment.season_end,
        )
    )
    session.add_all(CuratedGameVenue(**row) for row in assessment.rows)
    session.flush()
    report = assessment.report()
    return {
        "contract_id": assessment.seed.contract_id,
        "registry_created": registry_created,
        "registry_existing": registry_existing,
        "overrides_created": overrides_created,
        "overrides_existing": overrides_existing,
        "mapping_rows_written": len(assessment.rows),
        "mapping_status_counts": report["mapping_status_counts"],
        "acceptance_ready": report["acceptance_ready"],
    }
