"""Daily allowlisted NFL news and injury monitoring service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from hashlib import sha256
from html.parser import HTMLParser
from io import StringIO
import json
import re
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen
import uuid
import xml.etree.ElementTree as ET

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from Database.config import get_connection_string

TEAM_NAME_TO_ABBR = {
    "arizona cardinals": "ARI",
    "atlanta falcons": "ATL",
    "baltimore ravens": "BAL",
    "buffalo bills": "BUF",
    "carolina panthers": "CAR",
    "chicago bears": "CHI",
    "cincinnati bengals": "CIN",
    "cleveland browns": "CLE",
    "dallas cowboys": "DAL",
    "denver broncos": "DEN",
    "detroit lions": "DET",
    "green bay packers": "GB",
    "houston texans": "HOU",
    "indianapolis colts": "IND",
    "jacksonville jaguars": "JAX",
    "kansas city chiefs": "KC",
    "las vegas raiders": "LV",
    "los angeles chargers": "LAC",
    "los angeles rams": "LAR",
    "miami dolphins": "MIA",
    "minnesota vikings": "MIN",
    "new england patriots": "NE",
    "new orleans saints": "NO",
    "new york giants": "NYG",
    "new york jets": "NYJ",
    "philadelphia eagles": "PHI",
    "pittsburgh steelers": "PIT",
    "san francisco 49ers": "SF",
    "seattle seahawks": "SEA",
    "tampa bay buccaneers": "TB",
    "tennessee titans": "TEN",
    "washington commanders": "WAS",
}
TEAM_ABBRS = set(TEAM_NAME_TO_ABBR.values())
PERSON_STOP_WORDS = {
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Coach",
    "NFL",
    "QB",
    "RB",
    "WR",
    "TE",
    "OL",
    "DL",
    "CB",
    "S",
    "LB",
    "Bills",
    "Chiefs",
    "Packers",
    "Bears",
    "Jets",
    "Giants",
    "Patriots",
    "Cowboys",
    "Eagles",
    "Rams",
    "Chargers",
    "Raiders",
    "Broncos",
    "Titans",
    "Texans",
    "Colts",
    "Jaguars",
    "Steelers",
    "Browns",
    "Bengals",
    "Ravens",
    "Falcons",
    "Panthers",
    "Saints",
    "Buccaneers",
    "Seahawks",
    "Cardinals",
    "Vikings",
    "Lions",
    "Dolphins",
    "Commanders",
    "Inactive",
    "Watch",
    "Report",
    "Update",
    "Source",
    "Fantasy",
    "Football",
    "Draft",
    "Guide",
    "Buzz",
    "Practice",
    "Squads",
    "Will",
    "Look",
    "How",
    "What",
    "Why",
    "Which",
    "From",
    "Can",
    "The",
}
NFL_HINT_TOKENS = [
    "nfl",
    "quarterback",
    "qb",
    "rb",
    "wr",
    "te",
    "minicamp",
    "training camp",
    "practice",
    "depth chart",
    "snap",
]
OFF_FIELD_TOKENS = [
    "arrest",
    "armed robbery",
    "kidnapping",
    "murder",
    "body found",
    "gambling scandal",
    "social media video",
    "date of birth",
    "world cup",
    "nba draft",
    "golf",
    "scotland",
    "greatest team",
]
EVERGREEN_TOKENS = [
    "greatest",
    "ranking the",
    "rankings",
    "quarterback rankings",
    "quarterback tiers",
    "tiers ahead of the",
    "top 10",
    "top dynamic duos",
    "winners",
    "losers",
    "best-and worst-case",
    "best and worst-case",
    "over/unders",
    "offseason",
    "report dates",
    "storyline for all 32 teams",
    "training camp report dates",
    "roundtable",
    "takeaways",
    "overreactions",
    "dark horse",
    "backup qb rankings",
    "surprise players",
    "biggest surprise players",
    "legitimacy of",
    "what we're hearing",
    "one from every team",
    "inside the",
    "all 32 teams",
    "every team",
    "agent's take",
    "free agency",
    "landing spots",
    "retirement rumors",
    "retirement hint",
    "contract decision",
    "future deal",
    "walk year",
    "shares longevity advice",
]
ROUNDUP_TOKENS = [
    "what we're hearing",
    "one from every team",
    "all 32 teams",
    "every team",
    "plus",
    "roundup",
    "takeaways",
    "overreactions",
]
INJURY_STATUS_PATTERNS = [
    r"\bquestionable\b",
    r"\bdoubtful\b",
    r"\b(?:ruled\s+)?out\b",
    r"\bdnp\b",
    r"\bdid not practice\b",
    r"\blimited(?:\s+participant|\s+in\s+practice)?\b",
    r"\bfull participant\b",
    r"\binjured reserve\b",
    r"\bplaced on ir\b",
    r"\bactivated from ir\b",
    r"\bhold-?in\b",
    r"\bhamstring\b",
    r"\bankle\b",
    r"\bknee\b",
    r"\bconcussion\b",
    r"\bshoulder\b",
    r"\bgroin\b",
    r"\bback spasms\b",
]
TRANSACTION_TOKENS = ["signed", "waived", "released", "elevated", "activated", "traded", "extension"]
DEPTH_CHART_TOKENS = ["starter", "first-team reps", "target share", "snaps", "backup", "depth chart", "competing for", "could start"]
QUOTE_TOKENS = ["said", "told reporters", "press conference", "confirmed"]
WEATHER_TOKENS = ["weather", "wind", "rain", "snow"]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _date_text(value: date) -> str:
    return value.isoformat()


def _hash_text(*parts: Any) -> str:
    normalized = "||".join(_clean_text(part).lower() for part in parts if _clean_text(part))
    return sha256(normalized.encode("utf-8")).hexdigest()


def _parse_timestamp(value: str | None) -> datetime | None:
    text_value = _clean_text(value)
    if not text_value:
        return None
    try:
        parsed = parsedate_to_datetime(text_value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except (TypeError, ValueError, IndexError):
        pass
    try:
        parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except ValueError:
        return None


def _normalize_team(value: str | None) -> str | None:
    team = _clean_text(value).upper()
    return team or None


def _normalize_team_mention(text: str | None) -> str | None:
    cleaned = _clean_text(text)
    if not cleaned:
        return None
    upper = cleaned.upper()
    if upper in TEAM_ABBRS:
        return upper
    lowered = cleaned.lower()
    for team_name, abbr in TEAM_NAME_TO_ABBR.items():
        if team_name in lowered:
            return abbr
    return None


def _matches_any_pattern(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


@dataclass
class NewsMonitorRunResult:
    run_id: str
    run_date: date
    status: str
    forced: bool
    skipped: bool
    message: str
    sources_checked: int
    items_ingested: int
    signals_extracted: int
    completed_at: datetime
    report: dict[str, Any]


class NewsMonitorService:
    """Ingest allowlisted NFL sources and generate a daily DFS research report."""

    RUN_TABLE = "news_monitor_run"
    SOURCE_TABLE = "news_monitor_source"
    ITEM_TABLE = "news_monitor_item"
    SIGNAL_TABLE = "news_monitor_signal"
    MANUAL_NOTE_TABLE = "news_monitor_manual_note"
    FEEDBACK_TABLE = "news_monitor_feedback"

    def __init__(
        self,
        connection_string: str | None = None,
        engine: Engine | None = None,
        config_path: str | Path | None = None,
        fetcher: Callable[[str], bytes] | None = None,
    ) -> None:
        self.connection_string = connection_string or get_connection_string()
        self.engine = engine or create_engine(self.connection_string)
        self.config_path = Path(config_path) if config_path else Path(__file__).resolve().parent.parent / "news_sources.json"
        self.fetcher = fetcher or self._default_fetcher
        self._ensure_tables()

    def run_daily(
        self,
        run_date: date | None = None,
        force: bool = False,
        source_ids: list[str] | None = None,
    ) -> NewsMonitorRunResult:
        target_date = run_date or _utcnow().date()
        existing = self._load_completed_run(target_date)
        if existing and not force:
            return NewsMonitorRunResult(
                run_id=existing["run_id"],
                run_date=target_date,
                status="skipped",
                forced=False,
                skipped=True,
                message=f"Run already completed for {target_date.isoformat()}",
                sources_checked=int(existing.get("sources_checked") or 0),
                items_ingested=int(existing.get("items_ingested") or 0),
                signals_extracted=int(existing.get("signals_extracted") or 0),
                completed_at=existing["completed_at"],
                report=existing["report"],
            )

        run_id = str(uuid.uuid4())
        started_at = _utcnow()
        sources = self._load_sources(source_ids=source_ids)
        self._sync_sources(sources)

        items_ingested = 0
        signals_extracted = 0
        source_results: list[dict[str, Any]] = []
        source_errors: list[dict[str, str]] = []

        self._persist_run(
            run_id=run_id,
            run_date=target_date,
            status="running",
            force_run=force,
            started_at=started_at,
            completed_at=started_at,
            sources_checked=len(sources),
            items_ingested=0,
            signals_extracted=0,
            report={},
        )

        for source in sources:
            try:
                records = self._ingest_source(source=source, run_date=target_date)
                inserted = 0
                source_signal_count = 0
                for item in records:
                    saved_item = self._upsert_item(item, run_date=target_date)
                    if saved_item["inserted"]:
                        inserted += 1
                    signals = self._extract_signals(saved_item["item"])
                    for signal in signals:
                        saved_signal = self._upsert_signal(signal)
                        if saved_signal:
                            source_signal_count += 1
                items_ingested += inserted
                signals_extracted += source_signal_count
                source_results.append(
                    {
                        "source_id": source["source_id"],
                        "source_name": source["name"],
                        "status": "ok",
                        "items_seen": len(records),
                        "items_inserted": inserted,
                        "signals_inserted": source_signal_count,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                source_errors.append({"source_id": source["source_id"], "error": str(exc)})
                source_results.append(
                    {
                        "source_id": source["source_id"],
                        "source_name": source["name"],
                        "status": "error",
                        "items_seen": 0,
                        "items_inserted": 0,
                        "signals_inserted": 0,
                    }
                )

        report = self._build_report(target_date, source_results=source_results, source_errors=source_errors)
        completed_at = _utcnow()
        self._persist_run(
            run_id=run_id,
            run_date=target_date,
            status="completed",
            force_run=force,
            started_at=started_at,
            completed_at=completed_at,
            sources_checked=len(sources),
            items_ingested=items_ingested,
            signals_extracted=signals_extracted,
            report=report,
        )
        return NewsMonitorRunResult(
            run_id=run_id,
            run_date=target_date,
            status="completed",
            forced=force,
            skipped=False,
            message=f"Processed {len(sources)} sources for {target_date.isoformat()}",
            sources_checked=len(sources),
            items_ingested=items_ingested,
            signals_extracted=signals_extracted,
            completed_at=completed_at,
            report=report,
        )

    def add_manual_note(
        self,
        run_date: date | None,
        title: str,
        note_text: str,
        source_link: str | None = None,
    ) -> dict[str, Any]:
        target_date = run_date or _utcnow().date()
        note_id = str(uuid.uuid4())
        created_at = _utcnow()
        payload = {
            "note_id": note_id,
            "run_date": _date_text(target_date),
            "title": _clean_text(title),
            "note_text": _clean_text(note_text),
            "source_link": _clean_text(source_link) or None,
            "created_at": created_at.isoformat(),
        }
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    f"""
                    INSERT INTO {self.MANUAL_NOTE_TABLE}
                    (note_id, run_date, title, note_text, source_link, created_at)
                    VALUES (:note_id, :run_date, :title, :note_text, :source_link, :created_at)
                    """
                ),
                payload,
            )
        return {
            "note_id": note_id,
            "run_date": target_date,
            "title": payload["title"],
            "source_link": payload["source_link"],
            "created_at": created_at,
            "message": "Manual note stored for next news-monitor run",
        }

    def import_history(
        self,
        path: str,
        run_date: date | None = None,
        source_id: str = "historical_import",
        source_name: str = "Historical Import",
    ) -> NewsMonitorRunResult:
        target_date = run_date or _utcnow().date()
        source = {
            "source_id": source_id,
            "name": source_name,
            "source_type": "historical_import",
            "url": str(Path(path).expanduser()),
            "enabled": True,
            "content_mode": "metadata_only",
            "notes": "Imported from local historical file",
        }
        self._sync_sources([source])
        rows = self._load_history_rows(path)
        run_id = str(uuid.uuid4())
        started_at = _utcnow()
        items_ingested = 0
        signals_extracted = 0
        self._persist_run(
            run_id=run_id,
            run_date=target_date,
            status="running",
            force_run=True,
            started_at=started_at,
            completed_at=started_at,
            sources_checked=1,
            items_ingested=0,
            signals_extracted=0,
            report={},
        )
        for row in rows:
            item = self._build_import_item_record(source=source, run_date=target_date, row=row)
            saved_item = self._upsert_item(item, run_date=target_date)
            if saved_item["inserted"]:
                items_ingested += 1
            signals = self._extract_signals(saved_item["item"])
            for signal in signals:
                if self._upsert_signal(signal):
                    signals_extracted += 1
        source_results = [
            {
                "source_id": source_id,
                "source_name": source_name,
                "status": "ok",
                "items_seen": len(rows),
                "items_inserted": items_ingested,
                "signals_inserted": signals_extracted,
            }
        ]
        report = self._build_report(target_date, source_results=source_results, source_errors=[])
        completed_at = _utcnow()
        self._persist_run(
            run_id=run_id,
            run_date=target_date,
            status="completed",
            force_run=True,
            started_at=started_at,
            completed_at=completed_at,
            sources_checked=1,
            items_ingested=items_ingested,
            signals_extracted=signals_extracted,
            report=report,
        )
        return NewsMonitorRunResult(
            run_id=run_id,
            run_date=target_date,
            status="completed",
            forced=True,
            skipped=False,
            message=f"Imported {len(rows)} historical rows from {Path(path).expanduser().name}",
            sources_checked=1,
            items_ingested=items_ingested,
            signals_extracted=signals_extracted,
            completed_at=completed_at,
            report=report,
        )

    def get_report(self, run_date: date) -> dict[str, Any] | None:
        run = self._load_completed_run(run_date)
        if not run:
            return None
        return {
            "run_id": run["run_id"],
            "run_date": run_date,
            "status": "completed",
            "forced": bool(run.get("force_run")),
            "skipped": False,
            "message": f"Loaded completed news-monitor report for {run_date.isoformat()}",
            "sources_checked": int(run.get("sources_checked") or 0),
            "items_ingested": int(run.get("items_ingested") or 0),
            "signals_extracted": int(run.get("signals_extracted") or 0),
            "completed_at": run["completed_at"],
            "report": run["report"],
        }

    def list_feedback(self, run_date: date) -> list[dict[str, Any]]:
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT
                        feedback_id,
                        run_date,
                        signal_key,
                        signal_type,
                        signal_text,
                        player_name,
                        team,
                        source_link,
                        feedback_choice,
                        note_text,
                        created_at,
                        updated_at
                    FROM {self.FEEDBACK_TABLE}
                    WHERE run_date = :run_date
                    ORDER BY updated_at DESC, feedback_id ASC
                    """
                ),
                {"run_date": _date_text(run_date)},
            ).mappings().all()
        payload: list[dict[str, Any]] = []
        for row in rows:
            payload.append(
                {
                    "feedback_id": row["feedback_id"],
                    "run_date": run_date,
                    "signal_key": row["signal_key"],
                    "signal_type": row["signal_type"],
                    "signal_text": row["signal_text"],
                    "player_name": row["player_name"],
                    "team": row["team"],
                    "source_link": row["source_link"],
                    "feedback_choice": row["feedback_choice"],
                    "note_text": row["note_text"] or "",
                    "created_at": _parse_timestamp(row["created_at"]) or _utcnow(),
                    "updated_at": _parse_timestamp(row["updated_at"]) or _utcnow(),
                }
            )
        return payload

    def upsert_feedback(
        self,
        run_date: date,
        signal_key: str,
        signal_type: str,
        signal_text: str,
        feedback_choice: str | None = None,
        note_text: str = "",
        player_name: str | None = None,
        team: str | None = None,
        source_link: str | None = None,
    ) -> dict[str, Any]:
        cleaned_choice = _clean_text(feedback_choice) or None
        cleaned_note = _clean_text(note_text)
        if not cleaned_choice and not cleaned_note:
            with self.engine.begin() as conn:
                conn.execute(
                    text(
                        f"""
                        DELETE FROM {self.FEEDBACK_TABLE}
                        WHERE run_date = :run_date AND signal_key = :signal_key
                        """
                    ),
                    {
                        "run_date": _date_text(run_date),
                        "signal_key": _clean_text(signal_key),
                    },
                )
            return {
                "feedback_id": "",
                "run_date": run_date,
                "signal_key": _clean_text(signal_key),
                "signal_type": _clean_text(signal_type),
                "signal_text": _clean_text(signal_text),
                "player_name": _clean_text(player_name) or None,
                "team": _normalize_team(team),
                "source_link": _clean_text(source_link) or None,
                "feedback_choice": None,
                "note_text": "",
                "created_at": _utcnow(),
                "updated_at": _utcnow(),
            }

        feedback_id = str(uuid.uuid4())
        timestamp = _utcnow()
        payload = {
            "feedback_id": feedback_id,
            "run_date": _date_text(run_date),
            "signal_key": _clean_text(signal_key),
            "signal_type": _clean_text(signal_type),
            "signal_text": _clean_text(signal_text),
            "player_name": _clean_text(player_name) or None,
            "team": _normalize_team(team),
            "source_link": _clean_text(source_link) or None,
            "feedback_choice": cleaned_choice,
            "note_text": cleaned_note,
            "created_at": timestamp.isoformat(),
            "updated_at": timestamp.isoformat(),
        }
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    f"""
                    INSERT INTO {self.FEEDBACK_TABLE}
                    (
                        feedback_id,
                        run_date,
                        signal_key,
                        signal_type,
                        signal_text,
                        player_name,
                        team,
                        source_link,
                        feedback_choice,
                        note_text,
                        created_at,
                        updated_at
                    )
                    VALUES
                    (
                        :feedback_id,
                        :run_date,
                        :signal_key,
                        :signal_type,
                        :signal_text,
                        :player_name,
                        :team,
                        :source_link,
                        :feedback_choice,
                        :note_text,
                        :created_at,
                        :updated_at
                    )
                    ON CONFLICT(run_date, signal_key) DO UPDATE SET
                        signal_type = excluded.signal_type,
                        signal_text = excluded.signal_text,
                        player_name = excluded.player_name,
                        team = excluded.team,
                        source_link = excluded.source_link,
                        feedback_choice = excluded.feedback_choice,
                        note_text = excluded.note_text,
                        updated_at = excluded.updated_at
                    RETURNING
                        feedback_id,
                        run_date,
                        signal_key,
                        signal_type,
                        signal_text,
                        player_name,
                        team,
                        source_link,
                        feedback_choice,
                        note_text,
                        created_at,
                        updated_at
                    """
                ),
                payload,
            ).mappings().one()
        return {
            "feedback_id": row["feedback_id"],
            "run_date": run_date,
            "signal_key": row["signal_key"],
            "signal_type": row["signal_type"],
            "signal_text": row["signal_text"],
            "player_name": row["player_name"],
            "team": row["team"],
            "source_link": row["source_link"],
            "feedback_choice": row["feedback_choice"],
            "note_text": row["note_text"] or "",
            "created_at": _parse_timestamp(row["created_at"]) or timestamp,
            "updated_at": _parse_timestamp(row["updated_at"]) or timestamp,
        }

    def _default_fetcher(self, url: str) -> bytes:
        request = Request(url, headers={"User-Agent": "NFL-Control-Center-NewsMonitor/1.0"})
        with urlopen(request, timeout=20) as response:  # noqa: S310
            return response.read()

    def _ensure_tables(self) -> None:
        statements = [
            f"""
            CREATE TABLE IF NOT EXISTS {self.RUN_TABLE} (
                run_id TEXT PRIMARY KEY,
                run_date TEXT NOT NULL,
                status TEXT NOT NULL,
                force_run BOOLEAN NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                sources_checked INTEGER NOT NULL,
                items_ingested INTEGER NOT NULL,
                signals_extracted INTEGER NOT NULL,
                report_json TEXT NOT NULL
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.SOURCE_TABLE} (
                source_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                url TEXT,
                enabled BOOLEAN NOT NULL,
                content_mode TEXT NOT NULL,
                notes TEXT,
                config_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.ITEM_TABLE} (
                item_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                run_date TEXT NOT NULL,
                item_type TEXT NOT NULL,
                title TEXT,
                link TEXT,
                published_at TEXT,
                fetched_at TEXT NOT NULL,
                summary TEXT,
                external_id TEXT,
                content_hash TEXT NOT NULL,
                dedupe_key TEXT NOT NULL UNIQUE,
                metadata_json TEXT NOT NULL
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.SIGNAL_TABLE} (
                signal_id TEXT PRIMARY KEY,
                item_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                run_date TEXT NOT NULL,
                player_name TEXT,
                team TEXT,
                signal_type TEXT NOT NULL,
                signal_text TEXT NOT NULL,
                dfs_relevance TEXT NOT NULL,
                confidence TEXT NOT NULL,
                source_link TEXT,
                created_at TEXT NOT NULL,
                dedupe_key TEXT NOT NULL UNIQUE
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.MANUAL_NOTE_TABLE} (
                note_id TEXT PRIMARY KEY,
                run_date TEXT NOT NULL,
                title TEXT NOT NULL,
                note_text TEXT NOT NULL,
                source_link TEXT,
                created_at TEXT NOT NULL
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.FEEDBACK_TABLE} (
                feedback_id TEXT PRIMARY KEY,
                run_date TEXT NOT NULL,
                signal_key TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                signal_text TEXT NOT NULL,
                player_name TEXT,
                team TEXT,
                source_link TEXT,
                feedback_choice TEXT,
                note_text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(run_date, signal_key)
            )
            """,
        ]
        with self.engine.begin() as conn:
            for statement in statements:
                conn.execute(text(statement))

    def _load_sources(self, source_ids: list[str] | None = None) -> list[dict[str, Any]]:
        payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("news_sources.json must contain a list of source definitions")
        sources = []
        allowed = set(source_ids or [])
        for source in payload:
            if not source.get("enabled"):
                continue
            if allowed and source.get("source_id") not in allowed:
                continue
            sources.append(source)
        return sources

    def _load_history_rows(self, path: str) -> list[dict[str, Any]]:
        source_path = Path(path).expanduser()
        if not source_path.exists():
            raise FileNotFoundError(f"Historical import file not found: {source_path}")
        if source_path.suffix.lower() == ".json":
            payload = json.loads(source_path.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                raise ValueError("Historical import JSON must be a list of objects")
            rows = [dict(row) for row in payload]
        elif source_path.suffix.lower() in {".csv", ".tsv"}:
            sep = "\t" if source_path.suffix.lower() == ".tsv" else ","
            rows = pd.read_csv(source_path, sep=sep).to_dict(orient="records")
        else:
            raise ValueError("Historical import file must be .json, .csv, or .tsv")
        if not rows:
            raise ValueError("Historical import file is empty")
        required = {"title"}
        missing = required - set(str(key) for key in rows[0].keys())
        if missing:
            raise ValueError(f"Historical import rows missing required columns: {', '.join(sorted(missing))}")
        return rows

    def _sync_sources(self, sources: list[dict[str, Any]]) -> None:
        updated_at = _utcnow().isoformat()
        with self.engine.begin() as conn:
            for source in sources:
                conn.execute(
                    text(
                        f"""
                        INSERT INTO {self.SOURCE_TABLE}
                        (source_id, name, source_type, url, enabled, content_mode, notes, config_json, updated_at)
                        VALUES
                        (:source_id, :name, :source_type, :url, :enabled, :content_mode, :notes, :config_json, :updated_at)
                        ON CONFLICT(source_id) DO UPDATE SET
                            name = excluded.name,
                            source_type = excluded.source_type,
                            url = excluded.url,
                            enabled = excluded.enabled,
                            content_mode = excluded.content_mode,
                            notes = excluded.notes,
                            config_json = excluded.config_json,
                            updated_at = excluded.updated_at
                        """
                    ),
                    {
                        "source_id": source["source_id"],
                        "name": source["name"],
                        "source_type": source["source_type"],
                        "url": source.get("url"),
                        "enabled": bool(source.get("enabled", False)),
                        "content_mode": source.get("content_mode", "metadata_only"),
                        "notes": source.get("notes"),
                        "config_json": _json_dumps(source),
                        "updated_at": updated_at,
                    },
                )

    def _load_completed_run(self, run_date: date) -> dict[str, Any] | None:
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    f"""
                    SELECT run_id, force_run, sources_checked, items_ingested, signals_extracted, completed_at, report_json
                    FROM {self.RUN_TABLE}
                    WHERE run_date = :run_date AND status = 'completed'
                    ORDER BY completed_at DESC
                    LIMIT 1
                    """
                ),
                {"run_date": _date_text(run_date)},
            ).mappings().first()
        if not row:
            return None
        completed_at = _parse_timestamp(row["completed_at"]) or _utcnow()
        return {
            "run_id": row["run_id"],
            "force_run": row["force_run"],
            "sources_checked": row["sources_checked"],
            "items_ingested": row["items_ingested"],
            "signals_extracted": row["signals_extracted"],
            "completed_at": completed_at,
            "report": json.loads(row["report_json"]),
        }

    def _persist_run(
        self,
        run_id: str,
        run_date: date,
        status: str,
        force_run: bool,
        started_at: datetime,
        completed_at: datetime,
        sources_checked: int,
        items_ingested: int,
        signals_extracted: int,
        report: dict[str, Any],
    ) -> None:
        payload = {
            "run_id": run_id,
            "run_date": _date_text(run_date),
            "status": status,
            "force_run": force_run,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "sources_checked": sources_checked,
            "items_ingested": items_ingested,
            "signals_extracted": signals_extracted,
            "report_json": _json_dumps(report),
        }
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    f"""
                    INSERT INTO {self.RUN_TABLE}
                    (run_id, run_date, status, force_run, started_at, completed_at, sources_checked, items_ingested, signals_extracted, report_json)
                    VALUES
                    (:run_id, :run_date, :status, :force_run, :started_at, :completed_at, :sources_checked, :items_ingested, :signals_extracted, :report_json)
                    ON CONFLICT(run_id) DO UPDATE SET
                        status = excluded.status,
                        force_run = excluded.force_run,
                        started_at = excluded.started_at,
                        completed_at = excluded.completed_at,
                        sources_checked = excluded.sources_checked,
                        items_ingested = excluded.items_ingested,
                        signals_extracted = excluded.signals_extracted,
                        report_json = excluded.report_json
                    """
                ),
                payload,
            )

    def _ingest_source(self, source: dict[str, Any], run_date: date) -> list[dict[str, Any]]:
        source_type = source["source_type"]
        if source_type == "rss":
            return self._ingest_rss(source=source, run_date=run_date)
        if source_type == "injury_table":
            return self._ingest_injury_table(source=source, run_date=run_date)
        if source_type == "manual":
            return self._ingest_manual_notes(source=source, run_date=run_date)
        if source_type == "historical_import":
            raise ValueError("historical_import must be loaded through import_history")
        raise ValueError(f"Unsupported source_type: {source_type}")

    def _ingest_rss(self, source: dict[str, Any], run_date: date) -> list[dict[str, Any]]:
        body = self.fetcher(source["url"])
        root = ET.fromstring(body)
        channel_items = root.findall(".//item")
        if not channel_items:
            channel_items = root.findall(".//{http://www.w3.org/2005/Atom}entry")
        fetched_at = _utcnow()
        items = []
        for entry in channel_items:
            title = _clean_text(self._xml_text(entry, "title"))
            link = _clean_text(self._xml_text(entry, "link"))
            if not link:
                link = entry.findtext("{http://www.w3.org/2005/Atom}link") or ""
                if not link:
                    link_element = entry.find("{http://www.w3.org/2005/Atom}link")
                    if link_element is not None:
                        link = link_element.attrib.get("href", "")
            summary = _clean_text(self._xml_text(entry, "description") or self._xml_text(entry, "summary"))
            published = (
                _parse_timestamp(self._xml_text(entry, "pubDate"))
                or _parse_timestamp(self._xml_text(entry, "updated"))
                or _parse_timestamp(self._xml_text(entry, "published"))
            )
            external_id = _clean_text(self._xml_text(entry, "guid") or self._xml_text(entry, "id")) or None
            metadata = {"source_type": "rss"}
            if not self._should_keep_rss_item(source=source, title=title, summary=summary, link=link):
                continue
            items.append(
                self._build_item_record(
                    source=source,
                    run_date=run_date,
                    item_type="news",
                    title=title,
                    link=link or None,
                    published_at=published,
                    fetched_at=fetched_at,
                    summary=summary,
                    external_id=external_id,
                    metadata=metadata,
                )
            )
        return items

    def _should_keep_rss_item(self, source: dict[str, Any], title: str, summary: str, link: str) -> bool:
        combined = _clean_text(f"{title} {summary}").lower()
        lowered_link = _clean_text(link).lower()
        blocked_link_tokens = [
            "/college-football/",
            "/fantasy/football/",
        ]
        blocked_text_tokens = [
            "draft guide",
            "mock draft",
            "cheat sheets",
            "sleepers",
            "investigation",
            "body found",
            "murder",
            "lawsuit",
            "eligibility",
            "officials",
            "referees",
            "salary cap trend",
        ]
        if any(token in lowered_link for token in blocked_link_tokens):
            return False
        if any(token in combined for token in blocked_text_tokens):
            return False
        return True

    def _ingest_injury_table(self, source: dict[str, Any], run_date: date) -> list[dict[str, Any]]:
        html = self.fetcher(source["url"]).decode("utf-8", errors="replace")
        options = source.get("options", {})
        try:
            tables = pd.read_html(StringIO(html))
        except ImportError:
            tables = self._read_simple_html_tables(html)
        table_index = int(options.get("table_index", 0))
        if table_index >= len(tables):
            raise ValueError(f"injury_table source {source['source_id']} missing table index {table_index}")
        df = tables[table_index].copy()
        rename_map = {str(key): str(value) for key, value in options.get("column_map", {}).items()}
        if rename_map:
            df = df.rename(columns=rename_map)
        fetched_at = _utcnow()
        report_date = _clean_text(options.get("report_date")) or run_date.isoformat()
        items = []
        for row in df.to_dict(orient="records"):
            player_name = _clean_text(row.get("player_name"))
            if not player_name:
                continue
            team = _normalize_team(row.get("team"))
            position = _clean_text(row.get("position")) or None
            injury = _clean_text(row.get("injury")) or None
            practice_status = _clean_text(row.get("practice_status")) or None
            game_status = _clean_text(row.get("game_status")) or None
            title_bits = [player_name]
            if team:
                title_bits.append(team)
            if practice_status:
                title_bits.append(practice_status)
            elif game_status:
                title_bits.append(game_status)
            title = " - ".join(title_bits)
            summary = "; ".join(
                bit
                for bit in [
                    f"Position: {position}" if position else "",
                    f"Injury: {injury}" if injury else "",
                    f"Practice: {practice_status}" if practice_status else "",
                    f"Game status: {game_status}" if game_status else "",
                ]
                if bit
            )
            metadata = {
                "source_type": "injury_table",
                "season": options.get("season"),
                "week": options.get("week"),
                "report_date": report_date,
                "team": team,
                "player_name": player_name,
                "position": position,
                "injury": injury,
                "practice_status": practice_status,
                "game_status": game_status,
            }
            items.append(
                self._build_item_record(
                    source=source,
                    run_date=run_date,
                    item_type="injury",
                    title=title,
                    link=source.get("url"),
                    published_at=_parse_timestamp(report_date) or datetime.combine(run_date, datetime.min.time(), tzinfo=UTC),
                    fetched_at=fetched_at,
                    summary=summary,
                    external_id=_hash_text(source["source_id"], player_name, team, report_date),
                    metadata=metadata,
                )
            )
        return items

    def _ingest_manual_notes(self, source: dict[str, Any], run_date: date) -> list[dict[str, Any]]:
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT note_id, title, note_text, source_link, created_at
                    FROM {self.MANUAL_NOTE_TABLE}
                    WHERE run_date = :run_date
                    ORDER BY created_at ASC
                    """
                ),
                {"run_date": _date_text(run_date)},
            ).mappings().all()
        items = []
        for row in rows:
            created_at = _parse_timestamp(row["created_at"]) or _utcnow()
            items.append(
                self._build_item_record(
                    source=source,
                    run_date=run_date,
                    item_type="manual_note",
                    title=row["title"],
                    link=row["source_link"],
                    published_at=created_at,
                    fetched_at=created_at,
                    summary=row["note_text"],
                    external_id=row["note_id"],
                    metadata={"source_type": "manual_note", "manual_note_id": row["note_id"]},
                )
            )
        return items

    def _build_item_record(
        self,
        source: dict[str, Any],
        run_date: date,
        item_type: str,
        title: str,
        link: str | None,
        published_at: datetime | None,
        fetched_at: datetime,
        summary: str,
        external_id: str | None,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        title_text = _clean_text(title)
        summary_text = _clean_text(summary)
        metadata = dict(metadata)
        metadata["classification"] = self._classify_item(
            item_type=item_type,
            title=title_text,
            summary=summary_text,
            link=link,
            metadata=metadata,
        )
        content_hash = _hash_text(title, summary, link, external_id)
        dedupe_key = _hash_text(source["source_id"], link, external_id, title, published_at.isoformat() if published_at else "", content_hash)
        return {
            "item_id": str(uuid.uuid4()),
            "source_id": source["source_id"],
            "run_date": _date_text(run_date),
            "item_type": item_type,
            "title": title_text,
            "link": _clean_text(link) or None,
            "published_at": published_at.isoformat() if published_at else None,
            "fetched_at": fetched_at.isoformat(),
            "summary": summary_text,
            "external_id": external_id,
            "content_hash": content_hash,
            "dedupe_key": dedupe_key,
            "metadata_json": _json_dumps(metadata),
        }

    def _build_import_item_record(self, source: dict[str, Any], run_date: date, row: dict[str, Any]) -> dict[str, Any]:
        title = _clean_text(row.get("title"))
        summary = _clean_text(row.get("summary") or row.get("description"))
        link = _clean_text(row.get("link") or row.get("source_link")) or None
        published_at = _parse_timestamp(str(row.get("published_at") or row.get("published") or row.get("pubDate") or "")) or None
        fetched_at = _utcnow()
        metadata = {
            "source_type": "historical_import",
            "player_name": _clean_text(row.get("player_name")) or None,
            "team": _normalize_team_mention(str(row.get("team") or "")),
            "position": _clean_text(row.get("position")) or None,
            "season": row.get("season"),
            "week": row.get("week"),
        }
        item_type = _clean_text(row.get("item_type") or "news")
        external_id = _clean_text(row.get("external_id")) or None
        return self._build_item_record(
            source=source,
            run_date=run_date,
            item_type=item_type,
            title=title,
            link=link,
            published_at=published_at,
            fetched_at=fetched_at,
            summary=summary,
            external_id=external_id,
            metadata=metadata,
        )

    def _upsert_item(self, item: dict[str, Any], run_date: date) -> dict[str, Any]:
        with self.engine.begin() as conn:
            existing = conn.execute(
                text(
                    f"""
                    SELECT item_id, source_id, run_date, item_type, title, link, published_at, fetched_at, summary, external_id, content_hash, dedupe_key, metadata_json
                    FROM {self.ITEM_TABLE}
                    WHERE dedupe_key = :dedupe_key
                    """
                ),
                {"dedupe_key": item["dedupe_key"]},
            ).mappings().first()
            if existing:
                materialized = dict(existing)
                materialized["metadata"] = json.loads(materialized.pop("metadata_json"))
                materialized["run_date"] = _date_text(run_date)
                return {"inserted": False, "item": materialized}
            conn.execute(
                text(
                    f"""
                    INSERT INTO {self.ITEM_TABLE}
                    (item_id, source_id, run_date, item_type, title, link, published_at, fetched_at, summary, external_id, content_hash, dedupe_key, metadata_json)
                    VALUES
                    (:item_id, :source_id, :run_date, :item_type, :title, :link, :published_at, :fetched_at, :summary, :external_id, :content_hash, :dedupe_key, :metadata_json)
                    """
                ),
                item,
            )
        materialized = dict(item)
        materialized["metadata"] = json.loads(materialized.pop("metadata_json"))
        return {"inserted": True, "item": materialized}

    def _extract_signals(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        if item["item_type"] == "injury":
            return self._signals_from_injury_item(item)
        return self._signals_from_text_item(item)

    def _classify_item(
        self,
        item_type: str,
        title: str,
        summary: str,
        link: str | None,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        combined = _clean_text(f"{title} {summary}").lower()
        link_text = _clean_text(link).lower()
        explicit_injury = _matches_any_pattern(combined, INJURY_STATUS_PATTERNS)
        transaction = any(token in combined for token in TRANSACTION_TOKENS)
        depth_chart = any(token in combined for token in DEPTH_CHART_TOKENS)
        weather = any(token in combined for token in WEATHER_TOKENS)
        quote = any(token in combined for token in QUOTE_TOKENS)
        off_field = any(token in combined or token in link_text for token in OFF_FIELD_TOKENS)
        evergreen = any(token in combined for token in EVERGREEN_TOKENS)
        roundup = any(token in combined for token in ROUNDUP_TOKENS)
        source_type = _clean_text(metadata.get("source_type")).lower()
        is_nfl = (
            item_type == "injury"
            or source_type in {"injury_table", "manual_note", "historical_import"}
            or "/nfl/" in link_text
            or any(token in combined for token in NFL_HINT_TOKENS)
        )
        actionable_injury = explicit_injury and not evergreen and not roundup
        actionable_transaction = transaction and not roundup and not evergreen and not any(token in combined for token in ["could force", "landing spots", "negotiations", "future deal", "hearing"])
        actionable_depth_chart = depth_chart and not roundup and not evergreen
        topics = [
            topic
            for topic, present in [
                ("injury", actionable_injury),
                ("roster_move", actionable_transaction),
                ("depth_chart_change", actionable_depth_chart),
                ("weather_note", weather),
                ("coach_quote", quote),
            ]
            if present
        ]
        is_dfs_relevant = bool(is_nfl and not off_field and (actionable_injury or actionable_transaction or actionable_depth_chart or weather or item_type == "injury"))
        return {
            "is_nfl": is_nfl,
            "is_dfs_relevant": is_dfs_relevant,
            "off_field": off_field,
            "evergreen": evergreen,
            "roundup": roundup,
            "explicit_injury": explicit_injury,
            "topics": topics,
        }

    def _signals_from_injury_item(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        metadata = item.get("metadata", {})
        player_name = metadata.get("player_name")
        team = metadata.get("team")
        practice_status = _clean_text(metadata.get("practice_status"))
        game_status = _clean_text(metadata.get("game_status"))
        injury = _clean_text(metadata.get("injury"))
        fragments = [fragment for fragment in [injury, practice_status, game_status] if fragment]
        if not fragments:
            fragments.append(item.get("summary") or item.get("title"))
        text_value = " | ".join(fragments)
        relevance = "high" if any(token in text_value.lower() for token in ["out", "doubtful", "questionable", "dnp"]) else "medium"
        signal_text = f"{player_name} ({team or 'N/A'}): {text_value}".strip()
        return [
            self._build_signal_record(
                item=item,
                signal_type="injury",
                signal_text=signal_text,
                dfs_relevance=relevance,
                confidence="high",
                player_name=player_name,
                team=team,
            )
        ]

    def _signals_from_text_item(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        title = _clean_text(item.get("title", ""))
        summary = _clean_text(item.get("summary", ""))
        combined = _clean_text(f"{title} {summary}")
        lower = combined.lower()
        player_name, team = self._extract_entities(item=item, title=title, summary=summary)
        matches: list[tuple[str, str, str, str]] = []
        injury_status_tokens = [
            "questionable",
            "doubtful",
            "out ",
            " out",
            "dnp",
            "did not practice",
            "limited",
            "full participant",
            "injured reserve",
            "placed on ir",
            "activated from ir",
            "hold-in",
            "hamstring",
            "ankle",
            "knee",
            "concussion",
            "shoulder",
            "groin",
            "back spasms",
        ]
        if _matches_any_pattern(lower, INJURY_STATUS_PATTERNS):
            matches.append(("injury", combined, "high", "medium"))
        if any(token in lower for token in TRANSACTION_TOKENS):
            matches.append(("roster_move", combined, "medium", "medium"))
        if any(token in lower for token in DEPTH_CHART_TOKENS):
            matches.append(("depth_chart_change", combined, "high", "low"))
        if any(token in lower for token in QUOTE_TOKENS):
            matches.append(("coach_quote", combined, "low", "low"))
        if any(token in lower for token in WEATHER_TOKENS):
            matches.append(("weather_note", combined, "medium", "low"))
        if not matches:
            matches.append(("other", item.get("title") or combined, "low", "low"))
        signals = []
        for signal_type, signal_text, relevance, confidence in matches:
            enriched_text = self._format_signal_text(
                player_name=player_name,
                team=team,
                signal_text=signal_text,
            )
            signals.append(
                self._build_signal_record(
                    item=item,
                    signal_type=signal_type,
                    signal_text=enriched_text,
                    dfs_relevance=relevance,
                    confidence=confidence,
                    player_name=player_name,
                    team=team,
                )
            )
        return signals

    def _extract_entities(self, item: dict[str, Any], title: str, summary: str) -> tuple[str | None, str | None]:
        metadata = item.get("metadata", {})
        seeded_player = _clean_text(metadata.get("player_name")) or None
        seeded_team = _normalize_team_mention(str(metadata.get("team") or ""))
        if seeded_player or seeded_team:
            return seeded_player, seeded_team
        combined = _clean_text(f"{title} {summary}")
        team = _normalize_team_mention(title) or _normalize_team_mention(summary)
        player_name = self._extract_player_name(summary) or self._extract_player_name(title) or self._extract_player_name(combined)
        return player_name, team

    def _extract_player_name(self, text: str) -> str | None:
        if not text:
            return None
        candidates = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b", text)
        for candidate in candidates:
            parts = candidate.split()
            if any(part in PERSON_STOP_WORDS for part in parts):
                continue
            if candidate in {"New York", "Las Vegas", "San Francisco", "Los Angeles", "Tampa Bay", "Green Bay", "New England", "Kansas City"}:
                continue
            if len(parts) < 2:
                continue
            if any(len(part) <= 2 for part in parts):
                continue
            return candidate
        return None

    @staticmethod
    def _format_signal_text(player_name: str | None, team: str | None, signal_text: str) -> str:
        text_value = _clean_text(signal_text)
        if player_name and team:
            return f"{player_name} ({team}): {text_value}"
        if player_name:
            return f"{player_name}: {text_value}"
        if team:
            return f"{team}: {text_value}"
        return text_value

    def _build_signal_record(
        self,
        item: dict[str, Any],
        signal_type: str,
        signal_text: str,
        dfs_relevance: str,
        confidence: str,
        player_name: str | None,
        team: str | None,
    ) -> dict[str, Any]:
        dedupe_key = _hash_text(item["run_date"], item["item_id"], signal_type, signal_text, player_name, team)
        return {
            "signal_id": str(uuid.uuid4()),
            "item_id": item["item_id"],
            "source_id": item["source_id"],
            "run_date": item["run_date"],
            "player_name": _clean_text(player_name) or None,
            "team": _normalize_team(team),
            "signal_type": signal_type,
            "signal_text": _clean_text(signal_text),
            "dfs_relevance": dfs_relevance,
            "confidence": confidence,
            "source_link": item.get("link"),
            "created_at": _utcnow().isoformat(),
            "dedupe_key": dedupe_key,
        }

    def _upsert_signal(self, signal: dict[str, Any]) -> bool:
        with self.engine.begin() as conn:
            existing = conn.execute(
                text(f"SELECT signal_id FROM {self.SIGNAL_TABLE} WHERE dedupe_key = :dedupe_key"),
                {"dedupe_key": signal["dedupe_key"]},
            ).scalar()
            if existing:
                return False
            conn.execute(
                text(
                    f"""
                    INSERT INTO {self.SIGNAL_TABLE}
                    (signal_id, item_id, source_id, run_date, player_name, team, signal_type, signal_text, dfs_relevance, confidence, source_link, created_at, dedupe_key)
                    VALUES
                    (:signal_id, :item_id, :source_id, :run_date, :player_name, :team, :signal_type, :signal_text, :dfs_relevance, :confidence, :source_link, :created_at, :dedupe_key)
                    """
                ),
                signal,
            )
        return True

    def _build_report(
        self,
        run_date: date,
        source_results: list[dict[str, Any]],
        source_errors: list[dict[str, str]],
    ) -> dict[str, Any]:
        date_key = _date_text(run_date)
        with self.engine.begin() as conn:
            signal_rows = conn.execute(
                text(
                    f"""
                    SELECT signal_type, signal_text, dfs_relevance, confidence, player_name, team, source_link, item_id
                    FROM {self.SIGNAL_TABLE}
                    WHERE run_date = :run_date
                    ORDER BY
                        CASE dfs_relevance
                            WHEN 'high' THEN 1
                            WHEN 'medium' THEN 2
                            ELSE 3
                        END,
                        created_at ASC
                    """
                ),
                {"run_date": date_key},
            ).mappings().all()
            item_rows = conn.execute(
                text(
                    f"""
                    SELECT item_id, source_id, title, link, published_at, summary, item_type, metadata_json
                    FROM {self.ITEM_TABLE}
                    WHERE run_date = :run_date OR item_id IN (
                        SELECT item_id FROM {self.SIGNAL_TABLE} WHERE run_date = :run_date
                    )
                    ORDER BY fetched_at ASC
                    """
                ),
                {"run_date": date_key},
            ).mappings().all()
        items_by_id: dict[str, dict[str, Any]] = {}
        for row in item_rows:
            item = dict(row)
            metadata = json.loads(item.pop("metadata_json"))
            if "classification" not in metadata:
                metadata["classification"] = self._classify_item(
                    item_type=item["item_type"],
                    title=_clean_text(item["title"]),
                    summary=_clean_text(item["summary"]),
                    link=item["link"],
                    metadata=metadata,
                )
            item["metadata"] = metadata
            items_by_id[item["item_id"]] = item
        filtered_signals = []
        for row in signal_rows:
            signal = dict(row)
            item = items_by_id.get(signal["item_id"])
            if not item:
                continue
            classification = item["metadata"].get("classification", {})
            if not classification.get("is_dfs_relevant"):
                continue
            signal.pop("item_id", None)
            filtered_signals.append(signal)
        headlines = [
            {
                "source_id": row["source_id"],
                "title": row["title"],
                "link": row["link"],
                "published_at": row["published_at"],
            }
            for row in items_by_id.values()
            if any(
                topic in {"injury", "roster_move", "depth_chart_change", "weather_note"}
                for topic in row["metadata"].get("classification", {}).get("topics", [])
            )
        ]
        return {
            "date": date_key,
            "summary": {
                "high_priority_count": sum(1 for signal in filtered_signals if signal["dfs_relevance"] == "high"),
                "items_needing_manual_review": sum(1 for signal in filtered_signals if signal["signal_type"] in {"coach_quote", "other"}),
            },
            "high_priority_signals": [signal for signal in filtered_signals if signal["dfs_relevance"] == "high"][:25],
            "injury_updates": [signal for signal in filtered_signals if signal["signal_type"] == "injury"][:50],
            "roster_moves": [signal for signal in filtered_signals if signal["signal_type"] == "roster_move"][:50],
            "depth_chart_notes": [signal for signal in filtered_signals if signal["signal_type"] == "depth_chart_change"][:50],
            "manual_review": [signal for signal in filtered_signals if signal["signal_type"] in {"coach_quote", "other"}][:50],
            "team_headlines": headlines[:50],
            "sources_checked": source_results,
            "source_errors": source_errors,
        }

    @staticmethod
    def _xml_text(element: ET.Element, tag: str) -> str | None:
        direct = element.findtext(tag)
        if direct:
            return direct
        for child in list(element):
            if child.tag.endswith(tag):
                return child.text
        return None

    @staticmethod
    def _read_simple_html_tables(html: str) -> list[pd.DataFrame]:
        parser = _SimpleHtmlTableParser()
        parser.feed(html)
        tables = []
        for table in parser.tables:
            if not table:
                continue
            header = table[0]
            rows = table[1:] if len(table) > 1 else []
            tables.append(pd.DataFrame(rows, columns=header))
        return tables


class _SimpleHtmlTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._current_table: list[list[str]] | None = None
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._current_table = []
        elif tag == "tr" and self._current_table is not None:
            self._current_row = []
        elif tag in {"th", "td"} and self._current_row is not None:
            self._current_cell = []

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"th", "td"} and self._current_row is not None and self._current_cell is not None:
            self._current_row.append(_clean_text("".join(self._current_cell)))
            self._current_cell = None
        elif tag == "tr" and self._current_table is not None and self._current_row is not None:
            if any(cell for cell in self._current_row):
                self._current_table.append(self._current_row)
            self._current_row = None
        elif tag == "table" and self._current_table is not None:
            self.tables.append(self._current_table)
            self._current_table = None
