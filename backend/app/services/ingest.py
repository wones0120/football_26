from __future__ import annotations

import hashlib
import inspect
import math
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import and_, case, desc, func, select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from ..models import (
    CuratedInjury,
    CuratedSalary,
    IngestRun,
    PlayerMaster,
    RawNflSchedule,
    RawNflWeeklyStat,
    RawInjuryRow,
    RawSalaryRow,
    UnresolvedPlayerQueue,
)
from ..schemas import (
    AutoDiscoveredFileResponse,
    AutoDiscoverIngestRequest,
    AutoDiscoverIngestResponse,
    CuratedSalarySliceRowResponse,
    DataFreshnessResponse,
    DataFreshnessRowResponse,
    IngestResultResponse,
    InjuryIngestRequest,
    NflReadPyBootstrapRequest,
    NflReadPySeasonRequest,
    PlayerMasterResponse,
    PlayerMasterUpsertRequest,
    ResolveUnresolvedRequest,
    SalaryIngestRequest,
    SeasonCoverageRowResponse,
    UnresolvedRowResponse,
    UnresolvedTriageResponse,
    UnresolvedTriageRowResponse,
)
from .matching import (
    create_player_master,
    find_player_master_id,
    normalize_name,
    normalize_position,
    normalize_team,
    parse_opponent_from_game_info,
    upsert_alias,
)


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


FRESHNESS_THRESHOLDS_HOURS = {
    "salaries": 24,
    "injuries": 12,
    "schedules": 168,
    "weekly_stats": 168,
}


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _file_checksum(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _synthetic_source_key(name: str, team: str, position: str) -> str:
    semantic_identity = "|".join(
        (
            normalize_name(name),
            normalize_team(team) or "",
            normalize_position(position) or "",
        )
    )
    digest = hashlib.sha256(semantic_identity.encode("utf-8")).hexdigest()
    return f"synthetic-{digest[:24]}"


def _column_map(row: pd.Series, choices: list[str]) -> Any:
    for col in choices:
        if col in row.index:
            value = row[col]
            if not (isinstance(value, float) and pd.isna(value)):
                return value
    return None


def _call_with_supported_kwargs(func: Any, **kwargs: Any) -> Any:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        signature = None

    if signature is None:
        return func(**kwargs)

    accepts_var_kwargs = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    if accepts_var_kwargs:
        return func(**kwargs)

    supported = {key: value for key, value in kwargs.items() if key in signature.parameters}
    return func(**supported)


def _coerce_dataframe(value: Any) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value
    if hasattr(value, "to_pandas"):
        return value.to_pandas()  # type: ignore[no-any-return]
    if isinstance(value, list):
        return pd.DataFrame(value)
    raise RuntimeError(f"Expected tabular data but received {type(value).__name__}.")


def _safe_int(value: Any) -> int | None:
    text = _safe_str(value)
    if not text:
        return None
    try:
        return int(float(text))
    except (ValueError, TypeError):
        return None


def _json_safe_value(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:  # noqa: BLE001
            pass
    try:
        if pd.isna(value):  # type: ignore[arg-type]
            return None
    except Exception:  # noqa: BLE001
        pass
    if isinstance(value, float) and not math.isfinite(value):
        # JSONB rejects Infinity/-Infinity/NaN tokens.
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime().isoformat()
    if isinstance(value, pd.Timedelta):
        return str(value)
    return value


def _row_json(row: pd.Series) -> dict[str, Any]:
    return {str(k): _json_safe_value(v) for k, v in row.to_dict().items()}


NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
DISCOVERY_PATTERNS: dict[tuple[str, str], list[re.Pattern[str]]] = {
    ("draftkings", "salary"): [
        re.compile(r"^DKSalaries_(?P<season>\d{4})_(?P<week>\d{1,2})(?P<suffix>[^.]*)\.csv$", re.IGNORECASE),
    ],
    ("draftkings", "injury"): [
        re.compile(r"^DKInjuries_(?P<season>\d{4})_(?P<week>\d{1,2})(?P<suffix>[^.]*)\.csv$", re.IGNORECASE),
        re.compile(r"^DKInjury_(?P<season>\d{4})_(?P<week>\d{1,2})(?P<suffix>[^.]*)\.csv$", re.IGNORECASE),
    ],
    ("fanduel", "salary"): [
        re.compile(r"^FanDuelSalaries_(?P<season>\d{4})_(?P<week>\d{1,2})(?P<suffix>[^.]*)\.csv$", re.IGNORECASE),
        re.compile(r"^FanduelSalaries_(?P<season>\d{4})_(?P<week>\d{1,2})(?P<suffix>[^.]*)\.csv$", re.IGNORECASE),
        re.compile(r"^FanDuel_salaries_(?P<season>\d{4})_(?P<week>\d{1,2})(?P<suffix>[^.]*)\.csv$", re.IGNORECASE),
    ],
    ("fanduel", "injury"): [
        re.compile(r"^FanDuel_injuries_(?P<season>\d{4})_(?P<week>\d{1,2})(?P<suffix>[^.]*)\.csv$", re.IGNORECASE),
        re.compile(r"^Fanduel_injuries_(?P<season>\d{4})_(?P<week>\d{1,2})(?P<suffix>[^.]*)\.csv$", re.IGNORECASE),
        re.compile(r"^FanDuelInjuries_(?P<season>\d{4})_(?P<week>\d{1,2})(?P<suffix>[^.]*)\.csv$", re.IGNORECASE),
    ],
}

INGEST_COLUMN_ALIASES: dict[tuple[str, str], dict[str, tuple[str, ...]]] = {
    ("draftkings", "salary"): {
        "source_player_key": ("ID", "Id", "id"),
        "player_name": ("Name", "name"),
        "team": ("TeamAbbrev", "Team", "team"),
        "position": ("Position", "position"),
        "salary": ("Salary", "salary"),
    },
    ("fanduel", "salary"): {
        "source_player_key": ("Id", "ID", "id"),
        "player_name": ("Nickname", "Name", "name"),
        "team": ("Team", "TeamAbbrev", "team"),
        "position": ("Position", "position"),
        "salary": ("Salary", "salary"),
    },
    ("draftkings", "injury"): {
        "source_player_key": ("ID", "Id", "id"),
        "player_name": ("Name", "name"),
        "team": ("Team", "TeamAbbrev", "team"),
        "position": ("Position", "position"),
        "injury_status": ("Injury Indicator", "Status", "injury_indicator"),
    },
    ("fanduel", "injury"): {
        "source_player_key": ("Id", "ID", "id"),
        "player_name": ("Nickname", "Name", "name"),
        "team": ("Team", "team"),
        "position": ("Position", "position"),
        "injury_status": (
            "Injury Indicator",
            "Status",
            "Injury Status",
            "injury_status",
        ),
    },
}
INGEST_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "salary": ("source_player_key", "player_name", "team", "position", "salary"),
    "injury": ("player_name", "team", "position", "injury_status"),
}
INGEST_NONEMPTY_FIELDS: dict[str, tuple[str, ...]] = {
    "salary": ("source_player_key", "player_name", "team", "position", "salary"),
    "injury": ("player_name", "team", "position"),
}


class IngestValidationError(ValueError):
    pass


def _resolved_ingest_columns(
    source_system: str,
    source_table: str,
    raw_df: pd.DataFrame,
) -> tuple[dict[str, str], list[str]]:
    aliases = INGEST_COLUMN_ALIASES[(source_system, source_table)]
    resolved: dict[str, str] = {}
    missing: list[str] = []
    for field in INGEST_REQUIRED_FIELDS[source_table]:
        column = next((candidate for candidate in aliases[field] if candidate in raw_df.columns), None)
        if column is None:
            expected = ", ".join(aliases[field])
            missing.append(f"{field} (expected one of: {expected})")
        else:
            resolved[field] = column

    source_key_column = next(
        (
            candidate
            for candidate in aliases["source_player_key"]
            if candidate in raw_df.columns
        ),
        None,
    )
    if source_key_column is not None:
        resolved["source_player_key"] = source_key_column
    return resolved, missing


def _csv_row_numbers(positions: list[int], limit: int = 10) -> str:
    displayed = ", ".join(str(position + 2) for position in positions[:limit])
    if len(positions) > limit:
        displayed += f", ... (+{len(positions) - limit} more)"
    return displayed


def _duplicate_identity_positions(
    raw_df: pd.DataFrame,
    resolved_columns: dict[str, str],
) -> list[int]:
    identities: list[str | None] = []
    for _, row in raw_df.iterrows():
        source_key = _safe_str(
            row[resolved_columns["source_player_key"]]
            if "source_player_key" in resolved_columns
            else None
        )
        if source_key:
            identities.append(f"source:{source_key}")
            continue

        if not all(field in resolved_columns for field in ("player_name", "team", "position")):
            identities.append(None)
            continue
        name = normalize_name(_safe_str(row[resolved_columns["player_name"]]))
        team = normalize_team(_safe_str(row[resolved_columns["team"]]))
        position = normalize_position(_safe_str(row[resolved_columns["position"]]))
        identities.append(
            f"semantic:{name}:{team}:{position}" if name and team and position else None
        )

    positions_by_identity: dict[str, list[int]] = {}
    for position, identity in enumerate(identities):
        if identity is not None:
            positions_by_identity.setdefault(identity, []).append(position)
    return sorted(
        position
        for positions in positions_by_identity.values()
        if len(positions) > 1
        for position in positions
    )


def _validate_ingest_dataframe(
    source_system: str,
    source_table: str,
    raw_df: pd.DataFrame,
) -> None:
    if source_table not in INGEST_REQUIRED_FIELDS:
        raise ValueError(f"Unsupported validation source_table: {source_table}")
    if (source_system, source_table) not in INGEST_COLUMN_ALIASES:
        raise ValueError(
            f"Unsupported validation source: source_system={source_system} "
            f"source_table={source_table}"
        )

    errors: list[str] = []
    if raw_df.empty:
        errors.append("file contains no data rows")

    resolved_columns, missing_columns = _resolved_ingest_columns(
        source_system,
        source_table,
        raw_df,
    )
    if missing_columns:
        errors.append("missing required columns: " + "; ".join(missing_columns))

    for field in INGEST_NONEMPTY_FIELDS[source_table]:
        column = resolved_columns.get(field)
        if column is None:
            continue
        blank_positions = [
            position
            for position, value in enumerate(raw_df[column].tolist())
            if not _safe_str(value)
        ]
        if blank_positions:
            errors.append(
                f"blank {field} values at CSV rows {_csv_row_numbers(blank_positions)}"
            )

    salary_column = resolved_columns.get("salary")
    if salary_column is not None:
        invalid_salary_positions: list[int] = []
        for position, value in enumerate(raw_df[salary_column].tolist()):
            text_value = _safe_str(value)
            if not text_value:
                continue
            try:
                salary = float(text_value)
            except (TypeError, ValueError):
                invalid_salary_positions.append(position)
                continue
            if not math.isfinite(salary) or salary <= 0 or not salary.is_integer():
                invalid_salary_positions.append(position)
        if invalid_salary_positions:
            errors.append(
                "invalid salary values (expected positive integers) at CSV rows "
                + _csv_row_numbers(invalid_salary_positions)
            )

    duplicate_positions = _duplicate_identity_positions(raw_df, resolved_columns)
    if duplicate_positions:
        errors.append(
            "duplicate player identities at CSV rows "
            + _csv_row_numbers(duplicate_positions)
        )

    if errors:
        raise IngestValidationError(
            f"{source_system} {source_table} validation failed: " + "; ".join(errors)
        )


def _parse_discovered_slate(suffix: str) -> str:
    cleaned = suffix.strip().lower()
    if cleaned.startswith("_") or cleaned.startswith("-"):
        cleaned = cleaned[1:]
    if not cleaned:
        return "main"
    return NON_ALNUM_RE.sub("_", cleaned).strip("_") or "main"


def _parse_discovered_file_name(
    file_name: str,
    source_system: str,
    source_table: str,
) -> tuple[int, int, str] | None:
    patterns = DISCOVERY_PATTERNS.get((source_system, source_table), [])
    for pattern in patterns:
        match = pattern.match(file_name)
        if not match:
            continue
        season = int(match.group("season"))
        week = int(match.group("week"))
        if week < 1 or week > 25:
            return None
        slate = _parse_discovered_slate(match.group("suffix") or "")
        return season, week, slate
    return None


class IngestService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _new_run(
        self,
        source_system: str,
        source_table: str,
        source_path: str | None,
        season: int | None,
        week: int | None,
        slate: str | None,
    ) -> IngestRun:
        run = IngestRun(
            ingest_run_id=str(uuid.uuid4()),
            source_system=source_system,
            source_table=source_table,
            source_path=source_path,
            source_checksum=_file_checksum(source_path) if source_path else None,
            season=season,
            week=week,
            slate=slate,
            status="running",
            started_at=utcnow_naive(),
        )
        self.session.add(run)
        self.session.commit()
        return run

    def _complete_run(
        self,
        run_id: str,
        status: str,
        rows_raw: int,
        rows_curated: int,
        rows_unresolved: int,
        error_message: str | None = None,
    ) -> IngestRun:
        run = self.session.get(IngestRun, run_id)
        if run is None:
            raise RuntimeError(f"Run not found: {run_id}")
        run.status = status
        run.rows_raw = rows_raw
        run.rows_curated = rows_curated
        run.rows_unresolved = rows_unresolved
        run.error_message = error_message
        run.completed_at = utcnow_naive()
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run

    def _clear_existing_slice(
        self,
        source_system: str,
        source_table: str,
        season: int,
        week: int,
        slate: str,
    ) -> None:
        self.session.query(UnresolvedPlayerQueue).filter(
            and_(
                UnresolvedPlayerQueue.source_system == source_system,
                UnresolvedPlayerQueue.source_table == source_table,
                UnresolvedPlayerQueue.season == season,
                UnresolvedPlayerQueue.week == week,
                UnresolvedPlayerQueue.slate == slate,
            )
        ).delete(synchronize_session=False)

        if source_table == "salary":
            self.session.query(CuratedSalary).filter(
                and_(
                    CuratedSalary.source_system == source_system,
                    CuratedSalary.season == season,
                    CuratedSalary.week == week,
                    CuratedSalary.slate == slate,
                )
            ).delete(synchronize_session=False)
        elif source_table == "injury":
            self.session.query(CuratedInjury).filter(
                and_(
                    CuratedInjury.source_system == source_system,
                    CuratedInjury.season == season,
                    CuratedInjury.week == week,
                    CuratedInjury.slate == slate,
                )
            ).delete(synchronize_session=False)

    def _normalize_salary_rows(self, source_system: str, raw_df: pd.DataFrame) -> list[dict]:
        normalized: list[dict] = []
        for _, row in raw_df.iterrows():
            if source_system == "draftkings":
                source_player_key = _safe_str(_column_map(row, ["ID", "Id", "id"]))
                name = _safe_str(_column_map(row, ["Name", "name"]))
                team = _safe_str(_column_map(row, ["TeamAbbrev", "Team", "team"]))
                position = _safe_str(_column_map(row, ["Position", "position"]))
                roster_position = _safe_str(_column_map(row, ["Roster Position", "RosterPosition"]))
                salary_val = _column_map(row, ["Salary", "salary"])
                game_info = _safe_str(_column_map(row, ["Game Info", "GameInfo", "game_info"]))
            else:
                source_player_key = _safe_str(_column_map(row, ["Id", "ID", "id"]))
                name = _safe_str(_column_map(row, ["Nickname", "Name", "name"]))
                team = _safe_str(_column_map(row, ["Team", "TeamAbbrev", "team"]))
                position = _safe_str(_column_map(row, ["Position", "position"]))
                roster_position = position
                salary_val = _column_map(row, ["Salary", "salary"])
                game_info = _safe_str(_column_map(row, ["Game", "Game Info", "game_info"]))

            if not source_player_key:
                source_player_key = _synthetic_source_key(name, team, position)
            salary = int(float(salary_val)) if salary_val not in (None, "", "nan") else None
            norm_team = normalize_team(team)

            normalized.append(
                {
                    "source_player_key": source_player_key,
                    "player_name": name,
                    "normalized_name": normalize_name(name),
                    "team": norm_team,
                    "opponent": parse_opponent_from_game_info(game_info, norm_team),
                    "position": normalize_position(position),
                    "roster_position": normalize_position(roster_position) or normalize_position(position),
                    "salary": salary,
                    "game_info": game_info or None,
                    "raw_row_json": _row_json(row),
                }
            )
        return normalized

    def _normalize_injury_rows(self, source_system: str, raw_df: pd.DataFrame) -> list[dict]:
        normalized: list[dict] = []
        for _, row in raw_df.iterrows():
            if source_system == "draftkings":
                source_player_key = _safe_str(_column_map(row, ["ID", "Id", "id"]))
                name = _safe_str(_column_map(row, ["Name", "name"]))
                team = _safe_str(_column_map(row, ["Team", "TeamAbbrev", "team"]))
                position = _safe_str(_column_map(row, ["Position", "position"]))
                injury_status = _safe_str(
                    _column_map(row, ["Injury Indicator", "Status", "injury_indicator"])
                )
                injury_details = _safe_str(
                    _column_map(row, ["Injury Details", "Injury", "Notes", "injury_details"])
                )
            else:
                source_player_key = _safe_str(_column_map(row, ["Id", "ID", "id"]))
                name = _safe_str(_column_map(row, ["Nickname", "Name", "name"]))
                team = _safe_str(_column_map(row, ["Team", "team"]))
                position = _safe_str(_column_map(row, ["Position", "position"]))
                injury_status = _safe_str(
                    _column_map(
                        row,
                        [
                            "Injury Indicator",
                            "Status",
                            "Injury Status",
                            "injury_status",
                        ],
                    )
                )
                injury_details = _safe_str(_column_map(row, ["Injury", "Notes", "injury_details"]))

            if not source_player_key:
                source_player_key = _synthetic_source_key(name, team, position)

            normalized.append(
                {
                    "source_player_key": source_player_key,
                    "player_name": name,
                    "normalized_name": normalize_name(name),
                    "team": normalize_team(team),
                    "position": normalize_position(position),
                    "injury_status": injury_status or None,
                    "injury_details": injury_details or None,
                    "raw_row_json": _row_json(row),
                }
            )
        return normalized

    def _load_nflreadpy_weekly_data(
        self,
        nfl_module: Any,
        season: int,
        weeks: list[int] | None,
    ) -> pd.DataFrame:
        seasons = [season]

        if hasattr(nfl_module, "import_weekly_data"):
            data = nfl_module.import_weekly_data(seasons)  # type: ignore[attr-defined]
            df = _coerce_dataframe(data)
            if weeks and "week" in df.columns:
                df = df[df["week"].isin(weeks)]
            return df

        if hasattr(nfl_module, "load_weekly_data"):
            data = _call_with_supported_kwargs(
                nfl_module.load_weekly_data,  # type: ignore[attr-defined]
                season=season,
                seasons=seasons,
                weeks=weeks,
            )
            df = _coerce_dataframe(data)
            if weeks and "week" in df.columns:
                df = df[df["week"].isin(weeks)]
            return df

        if hasattr(nfl_module, "load_player_stats"):
            data = _call_with_supported_kwargs(
                nfl_module.load_player_stats,  # type: ignore[attr-defined]
                season=season,
                seasons=seasons,
                weeks=weeks,
                summary_level="week",
            )
            df = _coerce_dataframe(data)
            if weeks and "week" in df.columns:
                df = df[df["week"].isin(weeks)]
            return df

        raise RuntimeError(
            "Unsupported nflreadpy API surface. Expected one of "
            "import_weekly_data, load_weekly_data, or load_player_stats."
        )

    def _load_nflreadpy_schedules(
        self,
        nfl_module: Any,
        season: int,
        weeks: list[int] | None,
    ) -> pd.DataFrame:
        seasons = [season]

        if hasattr(nfl_module, "load_schedules"):
            data = _call_with_supported_kwargs(
                nfl_module.load_schedules,  # type: ignore[attr-defined]
                season=season,
                seasons=seasons,
            )
            df = _coerce_dataframe(data)
        elif hasattr(nfl_module, "import_schedules"):
            data = nfl_module.import_schedules(seasons)  # type: ignore[attr-defined]
            df = _coerce_dataframe(data)
        else:
            raise RuntimeError(
                "Unsupported nflreadpy schedule API surface. Expected load_schedules or import_schedules."
            )

        if weeks and "week" in df.columns:
            df = df[df["week"].isin(weeks)]
        return df

    def _clear_existing_nflreadpy_schedules(
        self,
        season: int,
        weeks: list[int] | None,
    ) -> None:
        query = self.session.query(RawNflSchedule).filter(
            and_(
                RawNflSchedule.source_system == "nflreadpy",
                RawNflSchedule.season == season,
            )
        )
        if weeks:
            query = query.filter(RawNflSchedule.week.in_(weeks))
        query.delete(synchronize_session=False)

    def _clear_existing_nflreadpy_weekly_stats(
        self,
        season: int,
        weeks: list[int] | None,
    ) -> None:
        query = self.session.query(RawNflWeeklyStat).filter(
            and_(
                RawNflWeeklyStat.source_system == "nflreadpy",
                RawNflWeeklyStat.season == season,
            )
        )
        if weeks:
            query = query.filter(RawNflWeeklyStat.week.in_(weeks))
        query.delete(synchronize_session=False)

    def ingest_salaries(self, request: SalaryIngestRequest) -> IngestResultResponse:
        path = Path(request.path).expanduser().resolve()
        if not path.exists():
            raise ValueError(f"File not found: {path}")

        run = self._new_run(
            source_system=request.source_system,
            source_table="salary",
            source_path=str(path),
            season=request.season,
            week=request.week,
            slate=request.slate,
        )
        rows_raw = 0
        rows_curated = 0
        rows_unresolved = 0
        try:
            raw_df = pd.read_csv(path)
            rows_raw = len(raw_df)
            _validate_ingest_dataframe(request.source_system, "salary", raw_df)
            normalized_rows = self._normalize_salary_rows(request.source_system, raw_df)
            self._clear_existing_slice(
                source_system=request.source_system,
                source_table="salary",
                season=request.season,
                week=request.week,
                slate=request.slate,
            )

            for row in normalized_rows:
                self.session.add(
                    RawSalaryRow(
                        ingest_run_id=run.ingest_run_id,
                        source_system=request.source_system,
                        season=request.season,
                        week=request.week,
                        slate=request.slate,
                        source_player_key=row["source_player_key"],
                        raw_row_json=row["raw_row_json"],
                    )
                )
                player_master_id, _reason = find_player_master_id(
                    self.session,
                    source_system=request.source_system,
                    source_key=row["source_player_key"],
                    name=row["player_name"],
                    team=row["team"],
                    position=row["position"],
                )
                self.session.add(
                    CuratedSalary(
                        ingest_run_id=run.ingest_run_id,
                        source_system=request.source_system,
                        season=request.season,
                        week=request.week,
                        slate=request.slate,
                        source_player_key=row["source_player_key"],
                        player_master_id=player_master_id,
                        player_name=row["player_name"],
                        normalized_name=row["normalized_name"],
                        team=row["team"],
                        opponent=row["opponent"],
                        position=row["position"],
                        roster_position=row["roster_position"],
                        salary=row["salary"],
                        game_info=row["game_info"],
                    )
                )
                rows_curated += 1
                if player_master_id:
                    upsert_alias(
                        session=self.session,
                        player_master_id=player_master_id,
                        source_system=request.source_system,
                        source_key=row["source_player_key"],
                        alias_name=row["player_name"],
                        team=row["team"],
                        position=row["position"],
                        season=request.season,
                        week=request.week,
                    )
                else:
                    rows_unresolved += 1
                    self.session.add(
                        UnresolvedPlayerQueue(
                            unresolved_id=str(uuid.uuid4()),
                            ingest_run_id=run.ingest_run_id,
                            source_system=request.source_system,
                            source_table="salary",
                            source_player_key=row["source_player_key"],
                            season=request.season,
                            week=request.week,
                            slate=request.slate,
                            raw_row_json=row["raw_row_json"],
                            normalized_name=row["normalized_name"],
                            team=row["team"],
                            position=row["position"],
                            resolution_status="open",
                        )
                    )

            self.session.commit()
            run = self._complete_run(
                run_id=run.ingest_run_id,
                status="completed",
                rows_raw=rows_raw,
                rows_curated=rows_curated,
                rows_unresolved=rows_unresolved,
            )
            return IngestResultResponse.model_validate(run, from_attributes=True)
        except Exception as exc:  # noqa: BLE001
            self.session.rollback()
            run = self._complete_run(
                run_id=run.ingest_run_id,
                status="failed",
                rows_raw=rows_raw,
                rows_curated=rows_curated,
                rows_unresolved=rows_unresolved,
                error_message=str(exc),
            )
            return IngestResultResponse.model_validate(run, from_attributes=True)

    def ingest_injuries(self, request: InjuryIngestRequest) -> IngestResultResponse:
        path = Path(request.path).expanduser().resolve()
        if not path.exists():
            raise ValueError(f"File not found: {path}")

        run = self._new_run(
            source_system=request.source_system,
            source_table="injury",
            source_path=str(path),
            season=request.season,
            week=request.week,
            slate=request.slate,
        )
        rows_raw = 0
        rows_curated = 0
        rows_unresolved = 0
        try:
            raw_df = pd.read_csv(path)
            rows_raw = len(raw_df)
            _validate_ingest_dataframe(request.source_system, "injury", raw_df)
            normalized_rows = self._normalize_injury_rows(request.source_system, raw_df)
            self._clear_existing_slice(
                source_system=request.source_system,
                source_table="injury",
                season=request.season,
                week=request.week,
                slate=request.slate,
            )

            for row in normalized_rows:
                self.session.add(
                    RawInjuryRow(
                        ingest_run_id=run.ingest_run_id,
                        source_system=request.source_system,
                        season=request.season,
                        week=request.week,
                        slate=request.slate,
                        source_player_key=row["source_player_key"],
                        raw_row_json=row["raw_row_json"],
                    )
                )
                player_master_id, _reason = find_player_master_id(
                    self.session,
                    source_system=request.source_system,
                    source_key=row["source_player_key"],
                    name=row["player_name"],
                    team=row["team"],
                    position=row["position"],
                )
                self.session.add(
                    CuratedInjury(
                        ingest_run_id=run.ingest_run_id,
                        source_system=request.source_system,
                        season=request.season,
                        week=request.week,
                        slate=request.slate,
                        source_player_key=row["source_player_key"],
                        player_master_id=player_master_id,
                        player_name=row["player_name"],
                        normalized_name=row["normalized_name"],
                        team=row["team"],
                        position=row["position"],
                        injury_status=row["injury_status"],
                        injury_details=row["injury_details"],
                    )
                )
                rows_curated += 1
                if player_master_id:
                    upsert_alias(
                        session=self.session,
                        player_master_id=player_master_id,
                        source_system=request.source_system,
                        source_key=row["source_player_key"],
                        alias_name=row["player_name"],
                        team=row["team"],
                        position=row["position"],
                        season=request.season,
                        week=request.week,
                    )
                else:
                    rows_unresolved += 1
                    self.session.add(
                        UnresolvedPlayerQueue(
                            unresolved_id=str(uuid.uuid4()),
                            ingest_run_id=run.ingest_run_id,
                            source_system=request.source_system,
                            source_table="injury",
                            source_player_key=row["source_player_key"],
                            season=request.season,
                            week=request.week,
                            slate=request.slate,
                            raw_row_json=row["raw_row_json"],
                            normalized_name=row["normalized_name"],
                            team=row["team"],
                            position=row["position"],
                            resolution_status="open",
                        )
                    )
            self.session.commit()
            run = self._complete_run(
                run_id=run.ingest_run_id,
                status="completed",
                rows_raw=rows_raw,
                rows_curated=rows_curated,
                rows_unresolved=rows_unresolved,
            )
            return IngestResultResponse.model_validate(run, from_attributes=True)
        except Exception as exc:  # noqa: BLE001
            self.session.rollback()
            run = self._complete_run(
                run_id=run.ingest_run_id,
                status="failed",
                rows_raw=rows_raw,
                rows_curated=rows_curated,
                rows_unresolved=rows_unresolved,
                error_message=str(exc),
            )
            return IngestResultResponse.model_validate(run, from_attributes=True)

    def _discover_files(
        self,
        source_system: str,
        source_table: str,
        directory: str,
    ) -> tuple[Path, list[tuple[Path, int, int, str]]]:
        root = Path(directory).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise ValueError(f"Directory not found: {root}")
        discovered: list[tuple[Path, int, int, str]] = []
        for path in sorted(root.glob("*.csv")):
            parsed = _parse_discovered_file_name(path.name, source_system=source_system, source_table=source_table)
            if parsed is None:
                continue
            season, week, slate = parsed
            discovered.append((path, season, week, slate))
        return root, discovered

    def ingest_discovered_files(
        self,
        request: AutoDiscoverIngestRequest,
        source_table: str,
    ) -> AutoDiscoverIngestResponse:
        if source_table not in {"salary", "injury"}:
            raise ValueError(f"Unsupported source_table: {source_table}")

        root, files = self._discover_files(
            source_system=request.source_system,
            source_table=source_table,
            directory=request.directory,
        )

        rows: list[AutoDiscoveredFileResponse] = []
        files_completed = 0
        files_failed = 0
        rows_curated = 0
        rows_unresolved = 0

        for path, season, week, slate in files:
            if source_table == "salary":
                result = self.ingest_salaries(
                    SalaryIngestRequest(
                        source_system=request.source_system,
                        season=season,
                        week=week,
                        slate=slate,
                        path=str(path),
                    )
                )
            else:
                result = self.ingest_injuries(
                    InjuryIngestRequest(
                        source_system=request.source_system,
                        season=season,
                        week=week,
                        slate=slate,
                        path=str(path),
                    )
                )

            rows_curated += result.rows_curated
            rows_unresolved += result.rows_unresolved
            if result.status == "completed":
                files_completed += 1
            else:
                files_failed += 1

            rows.append(
                AutoDiscoveredFileResponse(
                    file_name=path.name,
                    path=str(path),
                    season=season,
                    week=week,
                    slate=slate,
                    status=result.status,
                    rows_curated=result.rows_curated,
                    rows_unresolved=result.rows_unresolved,
                    error_message=result.error_message,
                )
            )

        return AutoDiscoverIngestResponse(
            source_system=request.source_system,
            source_table=source_table,
            directory=str(root),
            files_attempted=len(files),
            files_completed=files_completed,
            files_failed=files_failed,
            rows_curated=rows_curated,
            rows_unresolved=rows_unresolved,
            rows=rows,
        )

    def ingest_nflreadpy_schedules(self, request: NflReadPySeasonRequest) -> IngestResultResponse:
        run = self._new_run(
            source_system="nflreadpy",
            source_table="nfl_schedule",
            source_path=None,
            season=request.season,
            week=None,
            slate=None,
        )
        rows_raw = 0
        rows_curated = 0
        rows_unresolved = 0
        try:
            try:
                import nflreadpy as nfl  # type: ignore
            except ModuleNotFoundError as exc:
                raise RuntimeError(
                    "nflreadpy is not installed. Activate your virtualenv and run "
                    "`pip install -r requirements.txt`, then restart the API."
                ) from exc

            df = self._load_nflreadpy_schedules(
                nfl_module=nfl,
                season=request.season,
                weeks=request.weeks,
            )
            if df is None or getattr(df, "empty", True):
                raise RuntimeError("nflreadpy schedules returned no records.")

            season_col = next((c for c in ["season", "game_season"] if c in df.columns), None)
            week_col = next((c for c in ["week", "game_week"] if c in df.columns), None)
            game_id_col = next((c for c in ["game_id", "gameid", "old_game_id"] if c in df.columns), None)
            home_col = next((c for c in ["home_team", "home", "home_abbr"] if c in df.columns), None)
            away_col = next((c for c in ["away_team", "away", "away_abbr"] if c in df.columns), None)
            type_col = next((c for c in ["game_type", "season_type", "type"] if c in df.columns), None)
            status_col = next((c for c in ["status", "game_status"] if c in df.columns), None)
            stadium_col = next((c for c in ["stadium", "location", "venue"] if c in df.columns), None)
            kickoff_col = next((c for c in ["kickoff", "gametime", "gameday", "game_date"] if c in df.columns), None)

            self._clear_existing_nflreadpy_schedules(
                season=request.season,
                weeks=request.weeks,
            )

            for _, row in df.iterrows():
                row_season = _safe_int(row[season_col]) if season_col else request.season
                row_week = _safe_int(row[week_col]) if week_col else None
                rows_raw += 1
                self.session.add(
                    RawNflSchedule(
                        ingest_run_id=run.ingest_run_id,
                        source_system="nflreadpy",
                        season=row_season or request.season,
                        week=row_week,
                        game_id=(_safe_str(row[game_id_col]) or None) if game_id_col else None,
                        home_team=normalize_team(_safe_str(row[home_col]) if home_col else None),
                        away_team=normalize_team(_safe_str(row[away_col]) if away_col else None),
                        game_type=(_safe_str(row[type_col]) or None) if type_col else None,
                        kickoff=(_safe_str(row[kickoff_col]) or None) if kickoff_col else None,
                        status=(_safe_str(row[status_col]) or None) if status_col else None,
                        stadium=(_safe_str(row[stadium_col]) or None) if stadium_col else None,
                        raw_row_json=_row_json(row),
                    )
                )
                rows_curated += 1

            self.session.commit()
            run = self._complete_run(
                run_id=run.ingest_run_id,
                status="completed",
                rows_raw=rows_raw,
                rows_curated=rows_curated,
                rows_unresolved=rows_unresolved,
            )
            return IngestResultResponse.model_validate(run, from_attributes=True)
        except Exception as exc:  # noqa: BLE001
            self.session.rollback()
            run = self._complete_run(
                run_id=run.ingest_run_id,
                status="failed",
                rows_raw=rows_raw,
                rows_curated=rows_curated,
                rows_unresolved=rows_unresolved,
                error_message=str(exc),
            )
            return IngestResultResponse.model_validate(run, from_attributes=True)

    def ingest_nflreadpy_weekly_stats(self, request: NflReadPySeasonRequest) -> IngestResultResponse:
        run = self._new_run(
            source_system="nflreadpy",
            source_table="weekly_stats",
            source_path=None,
            season=request.season,
            week=None,
            slate=None,
        )
        rows_raw = 0
        rows_curated = 0
        rows_unresolved = 0
        try:
            try:
                import nflreadpy as nfl  # type: ignore
            except ModuleNotFoundError as exc:
                raise RuntimeError(
                    "nflreadpy is not installed. Activate your virtualenv and run "
                    "`pip install -r requirements.txt`, then restart the API."
                ) from exc

            df = self._load_nflreadpy_weekly_data(
                nfl_module=nfl,
                season=request.season,
                weeks=request.weeks,
            )
            if df is None or getattr(df, "empty", True):
                raise RuntimeError("nflreadpy weekly stats returned no records.")

            season_col = next((c for c in ["season", "game_season"] if c in df.columns), None)
            week_col = next((c for c in ["week", "game_week"] if c in df.columns), None)
            player_id_col = next((c for c in ["player_id", "gsis_id", "id"] if c in df.columns), None)
            name_col = next(
                (c for c in ["player_display_name", "player_name", "full_name", "name"] if c in df.columns),
                None,
            )
            team_col = next((c for c in ["recent_team", "team", "posteam"] if c in df.columns), None)
            opp_col = next((c for c in ["opponent_team", "defteam", "opponent"] if c in df.columns), None)
            position_col = next((c for c in ["position", "pos"] if c in df.columns), None)
            game_id_col = next((c for c in ["game_id", "gameid", "old_game_id"] if c in df.columns), None)

            if week_col is None:
                raise RuntimeError("Could not find a usable week column in nflreadpy weekly stats output.")

            self._clear_existing_nflreadpy_weekly_stats(
                season=request.season,
                weeks=request.weeks,
            )

            for _, row in df.iterrows():
                row_week = _safe_int(row[week_col])
                if row_week is None:
                    rows_unresolved += 1
                    continue
                row_season = _safe_int(row[season_col]) if season_col else request.season
                rows_raw += 1
                self.session.add(
                    RawNflWeeklyStat(
                        ingest_run_id=run.ingest_run_id,
                        source_system="nflreadpy",
                        season=row_season or request.season,
                        week=row_week,
                        player_id=(_safe_str(row[player_id_col]) or None) if player_id_col else None,
                        player_name=(_safe_str(row[name_col]) or None) if name_col else None,
                        team=normalize_team(_safe_str(row[team_col]) if team_col else None),
                        opponent=normalize_team(_safe_str(row[opp_col]) if opp_col else None),
                        position=normalize_position(_safe_str(row[position_col]) if position_col else None),
                        game_id=(_safe_str(row[game_id_col]) or None) if game_id_col else None,
                        raw_row_json=_row_json(row),
                    )
                )
                rows_curated += 1

            self.session.commit()
            run = self._complete_run(
                run_id=run.ingest_run_id,
                status="completed",
                rows_raw=rows_raw,
                rows_curated=rows_curated,
                rows_unresolved=rows_unresolved,
            )
            return IngestResultResponse.model_validate(run, from_attributes=True)
        except Exception as exc:  # noqa: BLE001
            self.session.rollback()
            run = self._complete_run(
                run_id=run.ingest_run_id,
                status="failed",
                rows_raw=rows_raw,
                rows_curated=rows_curated,
                rows_unresolved=rows_unresolved,
                error_message=str(exc),
            )
            return IngestResultResponse.model_validate(run, from_attributes=True)

    def bootstrap_nflreadpy(self, request: NflReadPyBootstrapRequest) -> IngestResultResponse:
        run = self._new_run(
            source_system="nflreadpy",
            source_table="player_bootstrap",
            source_path=None,
            season=request.season,
            week=None,
            slate=None,
        )
        rows_raw = 0
        rows_curated = 0
        rows_unresolved = 0
        try:
            try:
                import nflreadpy as nfl  # type: ignore
            except ModuleNotFoundError as exc:
                raise RuntimeError(
                    "nflreadpy is not installed. Activate your virtualenv and run "
                    "`pip install -r requirements.txt`, then restart the API."
                ) from exc

            df = self._load_nflreadpy_weekly_data(
                nfl_module=nfl,
                season=request.season,
                weeks=request.weeks,
            )

            if df is None or getattr(df, "empty", True):
                raise RuntimeError("nflreadpy returned no records.")

            id_col = next((c for c in ["player_id", "gsis_id", "id"] if c in df.columns), None)
            name_col = next(
                (c for c in ["player_display_name", "player_name", "full_name", "name"] if c in df.columns),
                None,
            )
            team_col = next((c for c in ["recent_team", "team", "posteam"] if c in df.columns), None)
            pos_col = next((c for c in ["position", "pos"] if c in df.columns), None)

            if not name_col:
                raise RuntimeError("Could not find a usable name column from nflreadpy output.")

            distinct = (
                df[[c for c in [id_col, name_col, team_col, pos_col] if c is not None]]
                .drop_duplicates()
                .fillna("")
            )
            rows_raw = int(len(distinct))
            for _, row in distinct.iterrows():
                source_key = _safe_str(row[id_col]) if id_col else ""
                full_name = _safe_str(row[name_col])
                team = _safe_str(row[team_col]) if team_col else None
                position = _safe_str(row[pos_col]) if pos_col else None
                if not full_name:
                    rows_unresolved += 1
                    continue

                player_master_id, _reason = find_player_master_id(
                    self.session,
                    source_system="nflreadpy",
                    source_key=source_key or None,
                    name=full_name,
                    team=team,
                    position=position,
                )
                if player_master_id is None:
                    created = create_player_master(
                        session=self.session,
                        full_name=full_name,
                        team=team,
                        position=position,
                    )
                    player_master_id = created.player_master_id
                if source_key:
                    upsert_alias(
                        session=self.session,
                        player_master_id=player_master_id,
                        source_system="nflreadpy",
                        source_key=source_key,
                        alias_name=full_name,
                        team=team,
                        position=position,
                        season=request.season,
                        week=None,
                    )
                rows_curated += 1

            self.session.commit()
            run = self._complete_run(
                run_id=run.ingest_run_id,
                status="completed",
                rows_raw=rows_raw,
                rows_curated=rows_curated,
                rows_unresolved=rows_unresolved,
            )
            return IngestResultResponse.model_validate(run, from_attributes=True)
        except Exception as exc:  # noqa: BLE001
            self.session.rollback()
            run = self._complete_run(
                run_id=run.ingest_run_id,
                status="failed",
                rows_raw=rows_raw,
                rows_curated=rows_curated,
                rows_unresolved=rows_unresolved,
                error_message=str(exc),
            )
            return IngestResultResponse.model_validate(run, from_attributes=True)

    def list_runs(self, limit: int = 50) -> list[IngestResultResponse]:
        try:
            rows = self.session.execute(
                select(IngestRun).order_by(desc(IngestRun.started_at)).limit(limit)
            ).scalars()
            return [IngestResultResponse.model_validate(r, from_attributes=True) for r in rows]
        except ProgrammingError:
            # Table/schema not initialized yet.
            self.session.rollback()
            return []

    def list_season_coverage(self) -> list[SeasonCoverageRowResponse]:
        try:
            result = self.session.execute(
                text(
                    """
                    SELECT dataset, season, rows
                    FROM (
                        SELECT 'raw_nfl_schedule' AS dataset, season, COUNT(*)::INT AS rows
                        FROM raw_nfl_schedule
                        GROUP BY season
                        UNION ALL
                        SELECT 'raw_nfl_weekly_stat' AS dataset, season, COUNT(*)::INT AS rows
                        FROM raw_nfl_weekly_stat
                        GROUP BY season
                        UNION ALL
                        SELECT 'raw_salary_row' AS dataset, season, COUNT(*)::INT AS rows
                        FROM raw_salary_row
                        GROUP BY season
                        UNION ALL
                        SELECT 'raw_injury_row' AS dataset, season, COUNT(*)::INT AS rows
                        FROM raw_injury_row
                        GROUP BY season
                        UNION ALL
                        SELECT 'curated_salary' AS dataset, season, COUNT(*)::INT AS rows
                        FROM curated_salary
                        GROUP BY season
                        UNION ALL
                        SELECT 'curated_injury' AS dataset, season, COUNT(*)::INT AS rows
                        FROM curated_injury
                        GROUP BY season
                        UNION ALL
                        SELECT 'player_alias' AS dataset, first_seen_season AS season, COUNT(*)::INT AS rows
                        FROM player_alias
                        GROUP BY first_seen_season
                    ) coverage
                    ORDER BY season DESC NULLS LAST, dataset ASC
                    """
                )
            ).mappings()
            return [SeasonCoverageRowResponse(**dict(row)) for row in result]
        except ProgrammingError:
            self.session.rollback()
            return []

    def list_curated_salary_slices(
        self,
        season: int | None = None,
        source_system: str | None = None,
        limit: int = 2000,
    ) -> list[CuratedSalarySliceRowResponse]:
        try:
            query = self.session.query(
                CuratedSalary.source_system.label("source_system"),
                CuratedSalary.season.label("season"),
                CuratedSalary.week.label("week"),
                CuratedSalary.slate.label("slate"),
                func.count(CuratedSalary.curated_salary_id).label("rows"),
            )
            if season is not None:
                query = query.filter(CuratedSalary.season == season)
            if source_system:
                query = query.filter(CuratedSalary.source_system == source_system)
            rows = (
                query.group_by(
                    CuratedSalary.source_system,
                    CuratedSalary.season,
                    CuratedSalary.week,
                    CuratedSalary.slate,
                )
                .order_by(
                    desc(CuratedSalary.season),
                    desc(CuratedSalary.week),
                    CuratedSalary.source_system.asc(),
                    CuratedSalary.slate.asc(),
                )
                .limit(limit)
                .all()
            )
            return [
                CuratedSalarySliceRowResponse(
                    source_system=row.source_system,
                    season=row.season,
                    week=row.week,
                    slate=row.slate,
                    rows=int(row.rows),
                )
                for row in rows
            ]
        except ProgrammingError:
            self.session.rollback()
            return []

    def get_data_freshness(
        self,
        *,
        source_system: str,
        season: int,
        week: int,
        slate: str,
        checked_at: datetime | None = None,
    ) -> DataFreshnessResponse:
        checked_at = checked_at or utcnow_naive()
        specs = (
            (
                "salaries",
                source_system,
                slate,
                CuratedSalary.curated_salary_id,
                CuratedSalary.created_at,
                (
                    CuratedSalary.source_system == source_system,
                    CuratedSalary.season == season,
                    CuratedSalary.week == week,
                    CuratedSalary.slate == slate,
                ),
            ),
            (
                "injuries",
                source_system,
                slate,
                CuratedInjury.curated_injury_id,
                CuratedInjury.created_at,
                (
                    CuratedInjury.source_system == source_system,
                    CuratedInjury.season == season,
                    CuratedInjury.week == week,
                    CuratedInjury.slate == slate,
                ),
            ),
            (
                "schedules",
                "nflreadpy",
                None,
                RawNflSchedule.raw_nfl_schedule_id,
                RawNflSchedule.created_at,
                (
                    RawNflSchedule.source_system == "nflreadpy",
                    RawNflSchedule.season == season,
                    RawNflSchedule.week == week,
                ),
            ),
            (
                "weekly_stats",
                "nflreadpy",
                None,
                RawNflWeeklyStat.raw_nfl_weekly_stat_id,
                RawNflWeeklyStat.created_at,
                (
                    RawNflWeeklyStat.source_system == "nflreadpy",
                    RawNflWeeklyStat.season == season,
                    RawNflWeeklyStat.week == week,
                ),
            ),
        )

        rows: list[DataFreshnessRowResponse] = []
        try:
            for dataset, dataset_source, dataset_slate, id_column, created_at_column, filters in specs:
                row_count, latest_loaded_at = (
                    self.session.query(
                        func.count(id_column),
                        func.max(created_at_column),
                    )
                    .filter(*filters)
                    .one()
                )
                count = int(row_count or 0)
                age_hours = (
                    max(0.0, (checked_at - latest_loaded_at).total_seconds() / 3600)
                    if latest_loaded_at is not None
                    else None
                )
                threshold = FRESHNESS_THRESHOLDS_HOURS[dataset]
                status = (
                    "missing"
                    if count == 0 or latest_loaded_at is None
                    else "fresh"
                    if age_hours is not None and age_hours <= threshold
                    else "stale"
                )
                rows.append(
                    DataFreshnessRowResponse(
                        dataset=dataset,
                        source_system=dataset_source,
                        season=season,
                        week=week,
                        slate=dataset_slate,
                        rows=count,
                        latest_loaded_at=latest_loaded_at,
                        age_hours=round(age_hours, 2) if age_hours is not None else None,
                        stale_after_hours=threshold,
                        status=status,
                    )
                )
        except ProgrammingError:
            self.session.rollback()
            rows = [
                DataFreshnessRowResponse(
                    dataset=dataset,
                    source_system=dataset_source,
                    season=season,
                    week=week,
                    slate=dataset_slate,
                    rows=0,
                    stale_after_hours=FRESHNESS_THRESHOLDS_HOURS[dataset],
                    status="missing",
                )
                for dataset, dataset_source, dataset_slate, *_ in specs
            ]

        return DataFreshnessResponse(
            checked_at=checked_at,
            source_system=source_system,
            season=season,
            week=week,
            slate=slate,
            rows=rows,
        )

    def list_unresolved(
        self,
        status: str = "open",
        source_system: str | None = None,
        season: int | None = None,
        week: int | None = None,
        slate: str | None = None,
        limit: int = 200,
    ) -> list[UnresolvedRowResponse]:
        query = select(UnresolvedPlayerQueue).where(
            UnresolvedPlayerQueue.resolution_status == status
        )
        if source_system:
            query = query.where(UnresolvedPlayerQueue.source_system == source_system)
        if season is not None:
            query = query.where(UnresolvedPlayerQueue.season == season)
        if week is not None:
            query = query.where(UnresolvedPlayerQueue.week == week)
        if slate:
            query = query.where(UnresolvedPlayerQueue.slate == slate)
        try:
            rows = self.session.execute(
                query.order_by(desc(UnresolvedPlayerQueue.created_at)).limit(limit)
            ).scalars()
            return [UnresolvedRowResponse.model_validate(r, from_attributes=True) for r in rows]
        except ProgrammingError:
            # Table/schema not initialized yet.
            self.session.rollback()
            return []

    def unresolved_triage(
        self,
        lookback_hours: int = 24,
        source_system: str | None = None,
        limit: int = 200,
    ) -> UnresolvedTriageResponse:
        generated_at = utcnow_naive()
        cutoff = generated_at - timedelta(hours=lookback_hours)
        filters = [UnresolvedPlayerQueue.resolution_status == "open"]
        if source_system:
            filters.append(UnresolvedPlayerQueue.source_system == source_system)

        new_case = case(
            (UnresolvedPlayerQueue.created_at >= cutoff, 1),
            else_=0,
        )
        try:
            open_total, new_total = self.session.execute(
                select(
                    func.count(UnresolvedPlayerQueue.unresolved_id),
                    func.coalesce(func.sum(new_case), 0),
                ).where(*filters)
            ).one()

            open_count = func.count(UnresolvedPlayerQueue.unresolved_id).label("open_count")
            new_count = func.coalesce(func.sum(new_case), 0).label("new_count")
            oldest_created_at = func.min(UnresolvedPlayerQueue.created_at).label(
                "oldest_created_at"
            )
            newest_created_at = func.max(UnresolvedPlayerQueue.created_at).label(
                "newest_created_at"
            )
            grouped_rows = self.session.execute(
                select(
                    UnresolvedPlayerQueue.source_system,
                    UnresolvedPlayerQueue.source_table,
                    UnresolvedPlayerQueue.season,
                    UnresolvedPlayerQueue.week,
                    UnresolvedPlayerQueue.slate,
                    open_count,
                    new_count,
                    oldest_created_at,
                    newest_created_at,
                )
                .where(*filters)
                .group_by(
                    UnresolvedPlayerQueue.source_system,
                    UnresolvedPlayerQueue.source_table,
                    UnresolvedPlayerQueue.season,
                    UnresolvedPlayerQueue.week,
                    UnresolvedPlayerQueue.slate,
                )
                .order_by(
                    desc(new_count),
                    desc(open_count),
                    desc(newest_created_at),
                    UnresolvedPlayerQueue.source_system.asc(),
                    UnresolvedPlayerQueue.source_table.asc(),
                )
                .limit(limit)
            ).all()
            rows = [
                UnresolvedTriageRowResponse(
                    source_system=row.source_system,
                    source_table=row.source_table,
                    season=row.season,
                    week=row.week,
                    slate=row.slate,
                    open_count=int(row.open_count),
                    new_count=int(row.new_count),
                    oldest_created_at=row.oldest_created_at,
                    newest_created_at=row.newest_created_at,
                )
                for row in grouped_rows
            ]
            return UnresolvedTriageResponse(
                generated_at=generated_at,
                lookback_hours=lookback_hours,
                open_total=int(open_total),
                new_total=int(new_total),
                groups_returned=len(rows),
                rows=rows,
            )
        except ProgrammingError:
            self.session.rollback()
            return UnresolvedTriageResponse(
                generated_at=generated_at,
                lookback_hours=lookback_hours,
                open_total=0,
                new_total=0,
                groups_returned=0,
                rows=[],
            )

    def resolve_unresolved(
        self,
        unresolved_id: str,
        request: ResolveUnresolvedRequest,
    ) -> UnresolvedRowResponse:
        unresolved = self.session.get(UnresolvedPlayerQueue, unresolved_id)
        if unresolved is None:
            raise ValueError(f"Unresolved row not found: {unresolved_id}")
        player_master = self.session.get(PlayerMaster, request.player_master_id)
        if player_master is None:
            raise ValueError(f"player_master_id not found: {request.player_master_id}")

        unresolved.resolution_status = "resolved"
        unresolved.resolved_player_master_id = request.player_master_id
        unresolved.resolved_by = request.resolved_by
        unresolved.resolved_at = utcnow_naive()
        unresolved.notes = request.notes
        self.session.add(unresolved)

        if request.create_alias and unresolved.source_player_key:
            alias_name = (
                str(unresolved.raw_row_json.get("Name") or unresolved.raw_row_json.get("Nickname") or "")
                or player_master.full_name
            )
            upsert_alias(
                session=self.session,
                player_master_id=request.player_master_id,
                source_system=unresolved.source_system,
                source_key=unresolved.source_player_key,
                alias_name=alias_name,
                team=unresolved.team,
                position=unresolved.position,
                season=unresolved.season,
                week=unresolved.week,
            )

        if unresolved.source_player_key:
            self.session.query(CuratedSalary).filter(
                and_(
                    CuratedSalary.source_system == unresolved.source_system,
                    CuratedSalary.source_player_key == unresolved.source_player_key,
                    CuratedSalary.season == unresolved.season,
                    CuratedSalary.week == unresolved.week,
                    CuratedSalary.slate == unresolved.slate,
                )
            ).update({CuratedSalary.player_master_id: request.player_master_id}, synchronize_session=False)
            self.session.query(CuratedInjury).filter(
                and_(
                    CuratedInjury.source_system == unresolved.source_system,
                    CuratedInjury.source_player_key == unresolved.source_player_key,
                    CuratedInjury.season == unresolved.season,
                    CuratedInjury.week == unresolved.week,
                    CuratedInjury.slate == unresolved.slate,
                )
            ).update({CuratedInjury.player_master_id: request.player_master_id}, synchronize_session=False)

        self.session.commit()
        self.session.refresh(unresolved)
        return UnresolvedRowResponse.model_validate(unresolved, from_attributes=True)

    def upsert_player_master(
        self,
        request: PlayerMasterUpsertRequest,
    ) -> PlayerMasterResponse:
        target: PlayerMaster | None = None
        if request.player_master_id:
            target = self.session.get(PlayerMaster, request.player_master_id)
        if target is None:
            target = create_player_master(
                session=self.session,
                full_name=request.full_name,
                team=request.team,
                position=request.position,
                player_master_id=request.player_master_id,
            )
        else:
            target.full_name = request.full_name
            target.normalized_name = normalize_name(request.full_name)
            target.primary_team = normalize_team(request.team)
            target.position = normalize_position(request.position)
            target.updated_at = utcnow_naive()
            self.session.add(target)
        self.session.commit()
        self.session.refresh(target)
        return PlayerMasterResponse.model_validate(target, from_attributes=True)
