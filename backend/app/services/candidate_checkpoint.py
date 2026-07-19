from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


CANDIDATE_CHECKPOINT_SCHEMA_VERSION = 1
CANDIDATE_GENERATOR_VERSION = "classic-weighted-v1"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _json_default(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"Value of type {type(value).__name__} is not JSON serializable.")


def _json_dumps(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


def candidate_checkpoint_fingerprint(config: dict[str, Any]) -> str:
    return hashlib.sha256(_json_dumps(config).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CandidateCheckpointSnapshot:
    path: str
    run_fingerprint: str
    run_config: dict[str, Any]
    status: str
    stage_index: int
    stage_config: dict[str, Any]
    attempts: int
    max_attempts: int
    rng_state: dict[str, Any]
    candidate_uids: list[list[str]]
    write_count: int
    created_at: str
    updated_at: str


class CandidateCheckpointStore:
    """Transactional SQLite checkpoint for long-running candidate generation."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.execute("PRAGMA synchronous = FULL")
        connection.execute("PRAGMA journal_mode = DELETE")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize_schema(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoint_metadata (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoint_candidates (
                    sequence INTEGER PRIMARY KEY,
                    lineup_key TEXT NOT NULL UNIQUE,
                    player_uids_json TEXT NOT NULL
                )
                """
            )

    def load(self) -> CandidateCheckpointSnapshot | None:
        with self._connection() as connection:
            metadata_row = connection.execute(
                "SELECT payload_json FROM checkpoint_metadata WHERE id = 1"
            ).fetchone()
            if metadata_row is None:
                return None
            payload = json.loads(str(metadata_row[0]))
            schema_version = int(payload.get("schema_version", -1))
            if schema_version != CANDIDATE_CHECKPOINT_SCHEMA_VERSION:
                raise ValueError(
                    "Unsupported candidate checkpoint schema version "
                    f"{schema_version}; expected "
                    f"{CANDIDATE_CHECKPOINT_SCHEMA_VERSION}."
                )
            candidate_cursor = connection.execute(
                """
                SELECT sequence, player_uids_json
                FROM checkpoint_candidates
                ORDER BY sequence
                """
            )
            candidate_uids: list[list[str]] = []
            for expected_sequence, row in enumerate(candidate_cursor):
                if int(row[0]) != expected_sequence:
                    raise ValueError(
                        "Candidate checkpoint contains a non-contiguous lineup sequence."
                    )
                player_uids = json.loads(str(row[1]))
                if (
                    not isinstance(player_uids, list)
                    or not all(
                        isinstance(uid, str) and uid
                        for uid in player_uids
                    )
                ):
                    raise ValueError(
                        "Candidate checkpoint contains invalid player UID data."
                    )
                candidate_uids.append(player_uids)

        if int(payload.get("candidate_count", -1)) != len(candidate_uids):
            raise ValueError(
                "Candidate checkpoint metadata count does not match persisted lineups."
            )

        return CandidateCheckpointSnapshot(
            path=str(self.path),
            run_fingerprint=str(payload["run_fingerprint"]),
            run_config=dict(payload["run_config"]),
            status=str(payload["status"]),
            stage_index=int(payload["stage_index"]),
            stage_config=dict(payload["stage_config"]),
            attempts=int(payload["attempts"]),
            max_attempts=int(payload["max_attempts"]),
            rng_state=dict(payload["rng_state"]),
            candidate_uids=candidate_uids,
            write_count=int(payload["write_count"]),
            created_at=str(payload["created_at"]),
            updated_at=str(payload["updated_at"]),
        )

    def start_run(
        self,
        *,
        run_config: dict[str, Any],
        stage_index: int,
        stage_config: dict[str, Any],
        max_attempts: int,
        rng_state: dict[str, Any],
    ) -> None:
        timestamp = _utc_now_iso()
        payload = {
            "schema_version": CANDIDATE_CHECKPOINT_SCHEMA_VERSION,
            "run_fingerprint": candidate_checkpoint_fingerprint(run_config),
            "run_config": run_config,
            "status": "in_progress",
            "stage_index": int(stage_index),
            "stage_config": stage_config,
            "attempts": 0,
            "max_attempts": int(max_attempts),
            "rng_state": rng_state,
            "candidate_count": 0,
            "write_count": 1,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM checkpoint_candidates")
            connection.execute("DELETE FROM checkpoint_metadata")
            connection.execute(
                "INSERT INTO checkpoint_metadata (id, payload_json) VALUES (1, ?)",
                (_json_dumps(payload),),
            )

    def advance_stage(
        self,
        *,
        expected_run_fingerprint: str,
        stage_index: int,
        stage_config: dict[str, Any],
        max_attempts: int,
        rng_state: dict[str, Any],
    ) -> None:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            payload = self._load_payload_for_update(
                connection,
                expected_run_fingerprint=expected_run_fingerprint,
            )
            connection.execute("DELETE FROM checkpoint_candidates")
            payload.update(
                {
                    "status": "in_progress",
                    "stage_index": int(stage_index),
                    "stage_config": stage_config,
                    "attempts": 0,
                    "max_attempts": int(max_attempts),
                    "rng_state": rng_state,
                    "candidate_count": 0,
                    "write_count": int(payload["write_count"]) + 1,
                    "updated_at": _utc_now_iso(),
                }
            )
            connection.execute(
                "UPDATE checkpoint_metadata SET payload_json = ? WHERE id = 1",
                (_json_dumps(payload),),
            )

    def save_progress(
        self,
        *,
        expected_run_fingerprint: str,
        stage_index: int,
        attempts: int,
        max_attempts: int,
        rng_state: dict[str, Any],
        lineups: list[list[Any]],
        persisted_count: int,
        status: str,
    ) -> None:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            payload = self._load_payload_for_update(
                connection,
                expected_run_fingerprint=expected_run_fingerprint,
            )
            if int(payload["stage_index"]) != int(stage_index):
                raise ValueError(
                    "Candidate checkpoint stage changed while generation was running."
                )
            stored_count = int(payload["candidate_count"])
            if stored_count != int(persisted_count):
                raise ValueError(
                    "Candidate checkpoint persisted count changed while generation was running."
                )
            new_rows: list[tuple[int, str, str]] = []
            for sequence, lineup in enumerate(
                lineups[persisted_count:],
                start=persisted_count,
            ):
                player_uids = [str(player.uid) for player in lineup]
                lineup_key = _json_dumps(sorted(player_uids))
                new_rows.append((sequence, lineup_key, _json_dumps(player_uids)))
            if new_rows:
                connection.executemany(
                    """
                    INSERT INTO checkpoint_candidates (
                        sequence,
                        lineup_key,
                        player_uids_json
                    )
                    VALUES (?, ?, ?)
                    """,
                    new_rows,
                )
            payload.update(
                {
                    "status": str(status),
                    "attempts": int(attempts),
                    "max_attempts": int(max_attempts),
                    "rng_state": rng_state,
                    "candidate_count": len(lineups),
                    "write_count": int(payload["write_count"]) + 1,
                    "updated_at": _utc_now_iso(),
                }
            )
            connection.execute(
                "UPDATE checkpoint_metadata SET payload_json = ? WHERE id = 1",
                (_json_dumps(payload),),
            )

    @staticmethod
    def _load_payload_for_update(
        connection: sqlite3.Connection,
        *,
        expected_run_fingerprint: str,
    ) -> dict[str, Any]:
        row = connection.execute(
            "SELECT payload_json FROM checkpoint_metadata WHERE id = 1"
        ).fetchone()
        if row is None:
            raise ValueError("Candidate checkpoint metadata is missing.")
        payload = json.loads(str(row[0]))
        actual_fingerprint = str(payload.get("run_fingerprint", ""))
        if actual_fingerprint != expected_run_fingerprint:
            raise ValueError(
                "Candidate checkpoint does not match the current generation request."
            )
        return payload
