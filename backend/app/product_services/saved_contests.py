"""Persistent DraftKings contest catalog and immutable observation history."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Engine, text

from .showdown_contests import contest_id_from_url, _ladder_is_complete, _unavailable_fields
from .target_schema import validate_target_schema


CONTEST_TYPES = frozenset({"gpp", "cash", "h2h", "double_up", "fifty_fifty", "other"})
CONTEST_FORMATS = frozenset({"classic", "showdown"})
REQUIRED_TABLES = ("saved_dk_contest", "saved_dk_contest_observation")


def _json(value: object) -> str:
    return json.dumps(value, default=str, sort_keys=True)


def _decoded(value: object) -> object:
    return json.loads(value) if isinstance(value, str) else value


def save_contests(
    engine: Engine, rows: list[dict], *, season: int, week: int, slate: str,
    contest_format: str, contest_type: str,
) -> list[dict]:
    """Save IDs and scope, then append the fetched facts as observations."""
    if contest_format not in CONTEST_FORMATS or contest_type not in CONTEST_TYPES:
        raise ValueError("Unsupported contest format or type")
    if season < 2000 or not 1 <= week <= 25 or not slate.strip():
        raise ValueError("Season, week, and slate are required")
    validate_target_schema(engine, consumer="SavedContestService", required_tables=REQUIRED_TABLES)
    seen: set[str] = set()
    with engine.begin() as connection:
        for row in rows:
            contest_id = contest_id_from_url(str(row.get("url") or ""))
            if str(row.get("contest_id")) != contest_id or contest_id in seen:
                raise ValueError("Contest URL and ID must match and be unique")
            seen.add(contest_id)
            previous = connection.execute(text(
                "SELECT season, week, slate, contest_format FROM target.saved_dk_contest "
                "WHERE contest_id = :contest_id"
            ), {"contest_id": contest_id}).mappings().first()
            if previous and (int(previous["season"]), int(previous["week"]),
                             str(previous["slate"]).upper(), previous["contest_format"]) != (
                                 season, week, slate.upper(), contest_format):
                raise ValueError(f"Contest {contest_id} is already saved under another slate or format")
            now = datetime.now(UTC)
            connection.execute(text("""
                INSERT INTO target.saved_dk_contest
                    (contest_id, url, season, week, slate, contest_format, contest_type,
                     name, draft_group_id, active, created_at, updated_at)
                VALUES (:contest_id, :url, :season, :week, :slate, :contest_format,
                        :contest_type, :name, :draft_group_id, TRUE, :now, :now)
                ON CONFLICT (contest_id) DO UPDATE SET
                    url = excluded.url, contest_type = excluded.contest_type,
                    name = COALESCE(excluded.name, saved_dk_contest.name),
                    draft_group_id = COALESCE(excluded.draft_group_id, saved_dk_contest.draft_group_id),
                    active = TRUE, updated_at = excluded.updated_at
            """), {
                "contest_id": contest_id, "url": row["url"], "season": season,
                "week": week, "slate": slate.upper(), "contest_format": contest_format,
                "contest_type": contest_type, "name": row.get("name"),
                "draft_group_id": str(row["draft_group_id"]) if row.get("draft_group_id") is not None else None,
                "now": now,
            })
            _append_observation(connection, row, reason="save")
    return list_saved_contests(engine, season=season, week=week, slate=slate,
                               contest_format=contest_format, contest_type=contest_type)


def _append_observation(connection, row: dict, *, reason: str) -> None:
    catalog = connection.execute(text("""
        SELECT season, week, slate, contest_format, contest_type
        FROM target.saved_dk_contest WHERE contest_id = :contest_id
    """), {"contest_id": str(row["contest_id"])}).mappings().one()
    observed_row = {**row, "catalog_scope": dict(catalog)}
    observed = row.get("observed_at") or datetime.now(UTC).isoformat()
    observed_at = datetime.fromisoformat(str(observed).replace("Z", "+00:00"))
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=UTC)
    connection.execute(text("""
        INSERT INTO target.saved_dk_contest_observation
            (observation_id, contest_id, observed_at, observation_reason, source,
             source_sha256, source_payload_json, contest_json, error)
        VALUES (:observation_id, :contest_id, :observed_at, :reason, :source,
                :source_sha256, :source_payload, :contest_json, :error)
    """), {
        "observation_id": str(uuid4()), "contest_id": str(row["contest_id"]),
        "observed_at": observed_at, "reason": reason,
        "source": str(row.get("source") or "unavailable"),
        "source_sha256": row.get("source_sha256"),
        "source_payload": _json(row.get("source_payload")) if row.get("source_payload") is not None else None,
        "contest_json": _json(observed_row), "error": row.get("error"),
    })


def record_saved_observations(engine: Engine, rows: list[dict], *, reason: str) -> int:
    """Append preview/optimizer observations only for contests already cataloged."""
    if reason not in {"preview", "optimizer"}:
        raise ValueError("Unsupported observation reason")
    if not rows:
        return 0
    validate_target_schema(engine, consumer="SavedContestService", required_tables=REQUIRED_TABLES)
    count = 0
    with engine.begin() as connection:
        for row in rows:
            contest_id = contest_id_from_url(str(row.get("url") or ""))
            if contest_id != str(row.get("contest_id")):
                raise ValueError("Contest URL and ID must match")
            existing = connection.execute(text(
                "SELECT contest_id FROM target.saved_dk_contest WHERE contest_id = :contest_id AND active = TRUE"
            ), {"contest_id": contest_id}).first()
            if not existing:
                continue
            _append_observation(connection, row, reason=reason)
            connection.execute(text("""
                UPDATE target.saved_dk_contest
                SET name = COALESCE(:name, name),
                    draft_group_id = COALESCE(:draft_group_id, draft_group_id),
                    updated_at = :now
                WHERE contest_id = :contest_id
            """), {"contest_id": contest_id, "name": row.get("name"),
                   "draft_group_id": str(row["draft_group_id"]) if row.get("draft_group_id") is not None else None,
                   "now": datetime.now(UTC)})
            count += 1
    return count


def list_saved_contests(
    engine: Engine, *, season: int, week: int, slate: str,
    contest_format: str | None = None, contest_type: str | None = None,
) -> list[dict]:
    validate_target_schema(engine, consumer="SavedContestService", required_tables=REQUIRED_TABLES)
    filters = ["c.season = :season", "c.week = :week", "UPPER(c.slate) = UPPER(:slate)", "c.active = TRUE"]
    params: dict = {"season": season, "week": week, "slate": slate}
    if contest_format:
        filters.append("c.contest_format = :contest_format")
        params["contest_format"] = contest_format
    if contest_type:
        filters.append("c.contest_type = :contest_type")
        params["contest_type"] = contest_type
    query = """
        WITH ranked AS (
            SELECT o.*, ROW_NUMBER() OVER (
                PARTITION BY o.contest_id ORDER BY o.observed_at DESC, o.created_at DESC, o.observation_id DESC
            ) AS observation_rank,
            COUNT(*) OVER (PARTITION BY o.contest_id) AS observation_count
            FROM target.saved_dk_contest_observation o
        ), successful AS (
            SELECT o.contest_id, o.contest_json, ROW_NUMBER() OVER (
                PARTITION BY o.contest_id ORDER BY o.observed_at DESC, o.created_at DESC, o.observation_id DESC
            ) AS successful_rank
            FROM target.saved_dk_contest_observation o
            WHERE o.source <> 'unavailable' AND o.error IS NULL
        )
        SELECT c.*, o.observed_at AS latest_observed_at, o.observation_reason AS latest_reason,
               o.contest_json AS latest_contest_json, o.error AS latest_error,
               successful.contest_json AS latest_successful_contest_json,
               COALESCE(o.observation_count, 0) AS observation_count
        FROM target.saved_dk_contest c
        LEFT JOIN ranked o ON o.contest_id = c.contest_id AND o.observation_rank = 1
        LEFT JOIN successful ON successful.contest_id = c.contest_id AND successful.successful_rank = 1
        WHERE """ + " AND ".join(filters) + " ORDER BY c.created_at, c.contest_id"
    with engine.connect() as connection:
        rows = connection.execute(text(query), params).mappings().all()
    result = []
    for row in rows:
        item = dict(row)
        item["latest_contest"] = _decoded(item.pop("latest_contest_json"))
        item["latest_successful_contest"] = _decoded(item.pop("latest_successful_contest_json"))
        result.append(item)
    return result


def list_saved_contest_scopes(engine: Engine) -> list[dict]:
    """List every active saved slate/type group for browsing."""
    validate_target_schema(engine, consumer="SavedContestService", required_tables=REQUIRED_TABLES)
    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT season, week, slate, contest_format, contest_type,
                   COUNT(*) AS contest_count, MAX(updated_at) AS last_updated_at
            FROM target.saved_dk_contest
            WHERE active = TRUE
            GROUP BY season, week, slate, contest_format, contest_type
            ORDER BY season DESC, week DESC, slate, contest_format, contest_type
        """)).mappings().all()
    return [dict(row) for row in rows]


def archive_saved_contest(engine: Engine, contest_id: str) -> bool:
    validate_target_schema(engine, consumer="SavedContestService", required_tables=REQUIRED_TABLES)
    with engine.begin() as connection:
        result = connection.execute(text(
            "UPDATE target.saved_dk_contest SET active = FALSE, updated_at = :now "
            "WHERE contest_id = :contest_id AND active = TRUE"
        ), {"contest_id": contest_id, "now": datetime.now(UTC)})
    return bool(result.rowcount)


def list_contest_observations(engine: Engine, contest_id: str, *, limit: int = 50) -> list[dict]:
    """Return dated parsed snapshots; raw source remains in the immutable table."""
    validate_target_schema(engine, consumer="SavedContestService", required_tables=REQUIRED_TABLES)
    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT observation_id, observed_at, observation_reason, source,
                   source_sha256, contest_json, error
            FROM target.saved_dk_contest_observation
            WHERE contest_id = :contest_id
            ORDER BY observed_at DESC, created_at DESC, observation_id DESC
            LIMIT :limit
        """), {"contest_id": contest_id, "limit": max(1, min(limit, 500))}).mappings().all()
    return [{**dict(row), "contest": _decoded(row["contest_json"])} for row in rows]


def recover_saved_contest_snapshots(
    engine: Engine, rows: list[dict], *, season: int, week: int, slate: str,
) -> list[dict]:
    """Reuse dated, verified facts when a live DraftKings lookup is incomplete."""
    if not any(row.get("unavailable_fields") for row in rows):
        return rows
    validate_target_schema(engine, consumer="SavedContestService", required_tables=REQUIRED_TABLES)
    recovered = []
    with engine.connect() as connection:
        for row in rows:
            if not row.get("unavailable_fields") or row.get("manual_fields"):
                recovered.append(row)
                continue
            contest_id = contest_id_from_url(str(row.get("url") or ""))
            snapshots = connection.execute(text("""
                SELECT o.observation_id, o.observed_at, o.contest_json
                FROM target.saved_dk_contest c
                JOIN target.saved_dk_contest_observation o ON o.contest_id = c.contest_id
                WHERE c.contest_id = :contest_id AND c.active = TRUE
                  AND c.season = :season AND c.week = :week
                  AND UPPER(c.slate) = UPPER(:slate)
                  AND c.contest_format = 'showdown' AND c.contest_type = 'gpp'
                ORDER BY o.observed_at DESC, o.created_at DESC, o.observation_id DESC
            """), {"contest_id": contest_id, "season": season, "week": week, "slate": slate}).mappings()
            fallback = None
            for saved in snapshots:
                candidate = _decoded(saved["contest_json"])
                if not isinstance(candidate, dict):
                    continue
                try:
                    lock = datetime.fromisoformat(str(candidate["lock_time"]).replace("Z", "+00:00"))
                    valid = (
                        str(candidate.get("contest_id")) == contest_id
                        and contest_id_from_url(str(candidate.get("url") or "")) == contest_id
                        and candidate.get("single_entry") is True
                        and candidate.get("state") in {None, "Upcoming"}
                        and lock.tzinfo is not None
                        and lock.astimezone(UTC) > datetime.now(UTC)
                        and not _unavailable_fields(candidate)
                        and _ladder_is_complete(candidate)
                    )
                except (KeyError, TypeError, ValueError):
                    valid = False
                if valid:
                    fallback = {
                        **candidate,
                        "source": "saved_snapshot",
                        "snapshot_observed_at": str(saved["observed_at"]),
                        "snapshot_observation_id": str(saved["observation_id"]),
                        "live_fetch_error": row.get("error"),
                        "unavailable_fields": [],
                    }
                    break
            recovered.append(fallback if fallback is not None else row)
    return recovered
