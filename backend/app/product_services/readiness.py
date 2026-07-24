"""Authoritative slate-readiness checks for prediction, optimization, and replay."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import create_engine, inspect, text

from Database.config import get_connection_string
from .replay import parse_slate_lock


READINESS_CONTRACT_ID = "slate_readiness_v1"
GATES = (
    "prediction",
    "classic_cash",
    "classic_gpp",
    "showdown_cash",
    "showdown_gpp",
    "replay",
)
OPTIMIZER_GATES = ("classic_cash", "classic_gpp", "showdown_cash", "showdown_gpp")
CLASSIC_GATES = ("classic_cash", "classic_gpp")
SHOWDOWN_GATES = ("showdown_cash", "showdown_gpp")
GPP_GATES = ("classic_gpp", "showdown_gpp")
REQUIRED_CLASSIC_POSITIONS = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "DST": 1}
ELIGIBLE_POSITIONS = frozenset(REQUIRED_CLASSIC_POSITIONS)


def _normalized_position(value: object) -> str:
    position = str(value or "").strip().upper()
    return "DST" if position in {"D", "DEF"} else position


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _at_or_before(value: datetime | None, cutoff: datetime | None) -> bool:
    if value is None or cutoff is None:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=timezone.utc)
    return value <= cutoff


def _status_score(statuses: Iterable[str]) -> int:
    values = [{"pass": 100, "warn": 60, "fail": 0}[status] for status in statuses]
    return round(sum(values) / len(values)) if values else 0


@dataclass
class SlateReadinessMetrics:
    season: int
    week: int
    slate: str
    salary_table_available: bool = False
    eligible_salary_rows: int = 0
    position_counts: dict[str, int] = field(default_factory=dict)
    roster_position_counts: dict[str, int] = field(default_factory=dict)
    team_count: int = 0
    resolved_identity_rows: int = 0
    quarantined_identity_rows: int = 0
    quarantine_reason_counts: dict[str, int] = field(default_factory=dict)
    complete_game_rows: int = 0
    valid_salary_rows: int = 0
    salary_timestamp_rows: int = 0
    salary_latest_created_at: datetime | None = None
    slate_lock_at: datetime | None = None
    injury_rows: int = 0
    injury_identity_rows: int = 0
    projection_run_count: int = 0
    projection_run_id: str | None = None
    projection_run_is_explicit: bool = False
    projected_salary_rows: int = 0
    positive_projection_rows: int = 0
    positive_projection_positions: dict[str, int] = field(default_factory=dict)
    projection_cutoff_rows: int = 0
    projection_data_cutoff_at: datetime | None = None
    ownership_rows: int = 0
    actual_salary_rows: int = 0
    actual_position_counts: dict[str, int] = field(default_factory=dict)
    normalized_contest_rows: int = 0
    legacy_contest_entry_rows: int = 0
    source_errors: list[str] = field(default_factory=list)


def _check(
    check_id: str,
    category: str,
    status: str,
    message: str,
    *,
    applies_to: Iterable[str],
    blocks: Iterable[str] = (),
    value: Any = None,
    threshold: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "category": category,
        "status": status,
        "message": message,
        "value": value,
        "threshold": threshold,
        "applies_to": list(applies_to),
        "blocks": list(blocks) if status == "fail" else [],
        "details": details or {},
    }


def evaluate_slate_readiness(metrics: SlateReadinessMetrics) -> dict[str, Any]:
    """Evaluate collected metrics without database access."""
    checks: list[dict[str, Any]] = []
    all_gates = GATES
    eligible = metrics.eligible_salary_rows

    salary_status = "pass" if metrics.salary_table_available and eligible > 0 else "fail"
    checks.append(
        _check(
            "salary_pool",
            "salaries",
            salary_status,
            f"{eligible} eligible salary rows are available." if salary_status == "pass" else "No eligible salary pool is available.",
            applies_to=all_gates,
            blocks=all_gates,
            value=eligible,
            threshold="> 0 eligible rows",
            details={"positions": metrics.position_counts},
        )
    )

    missing_classic = {
        position: minimum
        for position, minimum in REQUIRED_CLASSIC_POSITIONS.items()
        if metrics.position_counts.get(position, 0) < minimum
    }
    classic_markers = set(REQUIRED_CLASSIC_POSITIONS)
    classic_salary_format = classic_markers.issubset(metrics.roster_position_counts)
    classic_status = "pass" if not missing_classic and classic_salary_format else "fail"
    if classic_status == "pass":
        classic_message = "Every classic roster position has enough salary candidates."
    elif not classic_salary_format:
        classic_message = "The loaded salary file is not a Classic export; classic roster markers are missing."
    else:
        classic_message = "The salary pool cannot form a legal classic roster."
    checks.append(
        _check(
            "classic_roster_coverage",
            "salaries",
            classic_status,
            classic_message,
            applies_to=(*CLASSIC_GATES, "replay"),
            blocks=(*CLASSIC_GATES, "replay"),
            value=metrics.position_counts,
            threshold="classic salary markers plus QB>=1, RB>=2, WR>=3, TE>=1, DST>=1",
            details={
                "missing": missing_classic,
                "salary_format": "classic" if classic_salary_format else "not_classic",
                "roster_positions": metrics.roster_position_counts,
            },
        )
    )

    showdown_salary_format = {"CPT", "FLEX"}.issubset(metrics.roster_position_counts)
    showdown_ready = eligible >= 6 and metrics.team_count >= 2 and showdown_salary_format
    checks.append(
        _check(
            "showdown_roster_coverage",
            "salaries",
            "pass" if showdown_ready else "fail",
            "The pool has at least six players across two teams."
            if showdown_ready
            else "The pool cannot form a valid showdown lineup.",
            applies_to=SHOWDOWN_GATES,
            blocks=SHOWDOWN_GATES,
            value={
                "players": eligible,
                "teams": metrics.team_count,
                "roster_positions": metrics.roster_position_counts,
            },
            threshold="players>=6, teams>=2, and CPT/FLEX salary markers",
            details={"salary_format": "showdown" if showdown_salary_format else "not_showdown"},
        )
    )

    identity_rate = metrics.resolved_identity_rows / eligible if eligible else 0.0
    untracked_identity_rows = max(
        eligible - metrics.resolved_identity_rows - metrics.quarantined_identity_rows,
        0,
    )
    if untracked_identity_rows:
        identity_status = "fail"
    else:
        identity_status = "pass" if identity_rate >= 0.98 else "warn" if identity_rate >= 0.50 else "fail"
    identity_message = (
        f"{metrics.resolved_identity_rows} of {eligible} eligible salaries have canonical player identities."
    )
    if metrics.quarantined_identity_rows:
        identity_message += (
            f" {metrics.quarantined_identity_rows} unresolved salaries are quarantined and excluded."
        )
    if untracked_identity_rows:
        identity_message += f" {untracked_identity_rows} unresolved salaries are not quarantined."
    checks.append(
        _check(
            "player_identity_coverage",
            "identities",
            identity_status,
            identity_message,
            applies_to=all_gates,
            blocks=all_gates,
            value=round(identity_rate, 4),
            threshold=">= 98% pass; >= 50% warn; every unresolved row quarantined",
            details={
                "resolved": metrics.resolved_identity_rows,
                "eligible": eligible,
                "quarantined": metrics.quarantined_identity_rows,
                "untracked": untracked_identity_rows,
                "quarantine_reasons": metrics.quarantine_reason_counts,
                "quarantine_enforcement": "excluded_from_optimizer_projection_and_replay_inputs",
            },
        )
    )

    game_rate = metrics.complete_game_rows / eligible if eligible else 0.0
    game_status = "pass" if game_rate >= 1.0 else "warn" if game_rate >= 0.90 else "fail"
    checks.append(
        _check(
            "game_context_coverage",
            "games",
            game_status,
            f"{metrics.complete_game_rows} of {eligible} salaries have team, opponent, and game context.",
            applies_to=all_gates,
            blocks=all_gates,
            value=round(game_rate, 4),
            threshold="100% pass; >= 90% warn",
        )
    )

    salary_value_status = "pass" if eligible > 0 and metrics.valid_salary_rows == eligible else "fail"
    checks.append(
        _check(
            "salary_value_integrity",
            "salaries",
            salary_value_status,
            "All eligible salaries are positive and within the site cap."
            if salary_value_status == "pass"
            else "One or more eligible salary values are invalid.",
            applies_to=(*OPTIMIZER_GATES, "replay"),
            blocks=(*OPTIMIZER_GATES, "replay"),
            value={"valid": metrics.valid_salary_rows, "eligible": eligible},
            threshold="all salaries > 0 and <= 50000",
        )
    )

    injury_status = "pass" if metrics.injury_rows > 0 and metrics.injury_identity_rows == metrics.injury_rows else "warn"
    injury_message = (
        f"{metrics.injury_rows} injury rows are linked to canonical players."
        if injury_status == "pass"
        else "No complete, identity-linked injury snapshot is available for this slate."
    )
    checks.append(
        _check(
            "injury_snapshot",
            "injuries",
            injury_status,
            injury_message,
            applies_to=all_gates,
            value={"rows": metrics.injury_rows, "identified": metrics.injury_identity_rows},
            threshold="at least one snapshot row; 100% identity-linked",
        )
    )

    if metrics.projection_run_is_explicit:
        projection_run_status = "pass"
        projection_run_message = "An explicit active projection run is selected."
        projection_blocks = ()
    elif metrics.projection_run_count == 1:
        projection_run_status = "pass"
        projection_run_message = "One exact projection run is available."
        projection_blocks: tuple[str, ...] = ()
    elif metrics.projection_run_count == 0:
        projection_run_status = "fail"
        projection_run_message = "No projection run is available for this slate."
        projection_blocks = (*OPTIMIZER_GATES, "replay")
    else:
        projection_run_status = "fail"
        projection_run_message = "Multiple projection runs are compatible; select an exact run for replay."
        projection_blocks = ("replay",)
    checks.append(
        _check(
            "projection_run_lineage",
            "projections",
            projection_run_status,
            projection_run_message,
            applies_to=(*OPTIMIZER_GATES, "replay"),
            blocks=projection_blocks,
            value=metrics.projection_run_count,
            threshold="one explicit active run, or one compatible legacy run",
            details={
                "selected_projection_run_id": metrics.projection_run_id,
                "selection_is_explicit": metrics.projection_run_is_explicit,
            },
        )
    )

    projection_rate = metrics.positive_projection_rows / eligible if eligible else 0.0
    if projection_rate >= 0.85:
        projection_status = "pass"
    elif projection_rate >= 0.50:
        projection_status = "warn"
    else:
        projection_status = "fail"
    checks.append(
        _check(
            "projection_coverage",
            "projections",
            projection_status,
            f"{metrics.positive_projection_rows} of {eligible} salary candidates have positive projections.",
            applies_to=(*OPTIMIZER_GATES, "replay"),
            blocks=(*OPTIMIZER_GATES, "replay"),
            value=round(projection_rate, 4),
            threshold=">= 85% pass; >= 50% warn",
            details={
                "matched_salary_rows": metrics.projected_salary_rows,
                "positive_by_position": metrics.positive_projection_positions,
            },
        )
    )

    missing_offense = [
        position for position in ("QB", "RB", "WR", "TE")
        if metrics.positive_projection_positions.get(position, 0) == 0
    ]
    offense_status = "pass" if not missing_offense else "fail"
    checks.append(
        _check(
            "offensive_position_projections",
            "projections",
            offense_status,
            "Every offensive roster position has a positive projection."
            if offense_status == "pass"
            else "One or more offensive positions have no positive projection.",
            applies_to=(*OPTIMIZER_GATES, "replay"),
            blocks=(*OPTIMIZER_GATES, "replay"),
            value=metrics.positive_projection_positions,
            threshold="QB, RB, WR, and TE each >= 1",
            details={"missing": missing_offense},
        )
    )

    dst_rows = metrics.positive_projection_positions.get("DST", 0)
    checks.append(
        _check(
            "dst_projection",
            "projections",
            "pass" if dst_rows > 0 else "fail",
            f"{dst_rows} DST candidates have positive projections."
            if dst_rows > 0
            else "No DST candidate has a positive canonical projection.",
            applies_to=(*CLASSIC_GATES, "replay"),
            blocks=(*CLASSIC_GATES, "replay"),
            value=dst_rows,
            threshold=">= 1 positive DST projection",
        )
    )

    ownership_status = "pass" if metrics.ownership_rows > 0 else "warn"
    checks.append(
        _check(
            "ownership_projection",
            "ownership",
            ownership_status,
            f"{metrics.ownership_rows} ownership projections are available."
            if ownership_status == "pass"
            else "Ownership is unavailable; GPP leverage cannot be evaluated.",
            applies_to=GPP_GATES,
            value=metrics.ownership_rows,
            threshold="> 0 rows",
        )
    )

    cutoff = metrics.projection_data_cutoff_at
    cutoff_complete = (
        metrics.projected_salary_rows > 0
        and metrics.projection_cutoff_rows == metrics.projected_salary_rows
    )
    cutoff_safe = cutoff_complete and _at_or_before(cutoff, metrics.slate_lock_at)
    checks.append(
        _check(
            "projection_cutoff",
            "timestamps",
            "pass" if cutoff_safe else "fail",
            "Projection data cutoff is proven at or before slate lock."
            if cutoff_safe
            else "Projection data cutoff is missing or later than slate lock.",
            applies_to=("replay",),
            blocks=("replay",),
            value=_iso(cutoff),
            threshold=f"<= {_iso(metrics.slate_lock_at) or 'known slate lock'}",
            details={
                "timestamped_projection_rows": metrics.projection_cutoff_rows,
                "projected_salary_rows": metrics.projected_salary_rows,
            },
        )
    )

    salary_time = metrics.salary_latest_created_at
    salary_timestamps_complete = eligible > 0 and metrics.salary_timestamp_rows == eligible
    salary_prelock = salary_timestamps_complete and _at_or_before(salary_time, metrics.slate_lock_at)
    checks.append(
        _check(
            "salary_snapshot_cutoff",
            "timestamps",
            "pass" if salary_prelock else "fail",
            "Salary availability is proven at or before slate lock."
            if salary_prelock
            else "Salary content exists, but pre-lock availability is not proven.",
            applies_to=("replay",),
            blocks=("replay",),
            value=_iso(salary_time),
            threshold=f"<= {_iso(metrics.slate_lock_at) or 'known slate lock'}",
            details={
                "timestamped_salary_rows": metrics.salary_timestamp_rows,
                "eligible_salary_rows": eligible,
            },
        )
    )

    actual_rate = metrics.actual_salary_rows / eligible if eligible else 0.0
    actual_positions_complete = all(metrics.actual_position_counts.get(position, 0) > 0 for position in REQUIRED_CLASSIC_POSITIONS)
    actual_status = "pass" if actual_rate >= 0.95 and actual_positions_complete else "fail"
    checks.append(
        _check(
            "replay_actual_coverage",
            "replay",
            actual_status,
            f"{metrics.actual_salary_rows} of {eligible} salary players have canonical actuals."
            if actual_status == "pass"
            else "Canonical actuals are incomplete for full-lineup replay.",
            applies_to=("replay",),
            blocks=("replay",),
            value=round(actual_rate, 4),
            threshold=">= 95% and every classic position represented",
            details={"actuals_by_position": metrics.actual_position_counts},
        )
    )

    contest_status = "pass" if metrics.normalized_contest_rows > 0 else "fail"
    if metrics.normalized_contest_rows > 0:
        contest_message = f"{metrics.normalized_contest_rows} normalized contest records are linked."
    elif metrics.legacy_contest_entry_rows > 0:
        contest_message = "Legacy standings exist but are not linked to normalized contest metadata."
    else:
        contest_message = "No normalized contest result is linked to this slate."
    checks.append(
        _check(
            "contest_result_linkage",
            "contests",
            contest_status,
            contest_message,
            applies_to=("replay",),
            blocks=("replay",),
            value={
                "normalized_contests": metrics.normalized_contest_rows,
                "legacy_entries": metrics.legacy_contest_entry_rows,
            },
            threshold=">= 1 normalized contest",
        )
    )

    if metrics.source_errors:
        checks.append(
            _check(
                "source_query_health",
                "sources",
                "warn",
                "One or more optional readiness sources could not be queried.",
                applies_to=all_gates,
                value=len(metrics.source_errors),
                threshold="0 query errors",
                details={"errors": metrics.source_errors},
            )
        )

    gates: dict[str, dict[str, Any]] = {}
    for gate in GATES:
        relevant = [check for check in checks if gate in check["applies_to"]]
        blocking = [
            check["check_id"]
            for check in relevant
            if check["status"] == "fail" and gate in check["blocks"]
        ]
        attention = [check["check_id"] for check in relevant if check["status"] != "pass"]
        gate_counts = Counter(check["status"] for check in relevant)
        status = "fail" if blocking else "warn" if attention else "pass"
        gates[gate] = {
            "status": status,
            "score": _status_score(check["status"] for check in relevant),
            "summary": {
                "pass": gate_counts["pass"],
                "warn": gate_counts["warn"],
                "fail": gate_counts["fail"],
            },
            "blocking_checks": blocking,
            "attention_checks": attention,
            "message": (
                f"Blocked by {len(blocking)} readiness check{'s' if len(blocking) != 1 else ''}."
                if blocking
                else f"Ready with {len(attention)} warning{'s' if len(attention) != 1 else ''}."
                if attention
                else "Ready."
            ),
        }

    counts = Counter(check["status"] for check in checks)
    gate_statuses = [gate["status"] for gate in gates.values()]
    overall_status = "fail" if "fail" in gate_statuses else "warn" if "warn" in gate_statuses else "pass"
    stable_payload = {
        "contract_id": READINESS_CONTRACT_ID,
        "season": metrics.season,
        "week": metrics.week,
        "slate": metrics.slate.upper(),
        "checks": checks,
        "gates": gates,
    }
    report_id = f"slate-readiness:{hashlib.sha256(json.dumps(stable_payload, sort_keys=True, default=str).encode()).hexdigest()[:24]}"
    return {
        "report_id": report_id,
        "contract_id": READINESS_CONTRACT_ID,
        "season": metrics.season,
        "week": metrics.week,
        "slate": metrics.slate.upper(),
        "generated_at": datetime.now(timezone.utc),
        "status": overall_status,
        "score": _status_score(check["status"] for check in checks),
        "summary": {"pass": counts["pass"], "warn": counts["warn"], "fail": counts["fail"]},
        "gates": gates,
        "checks": checks,
    }


class SlateReadinessService:
    """Collect the latest slate inputs and evaluate the readiness contract."""

    def __init__(self, connection_string: str | None = None) -> None:
        self.connection_string = connection_string or get_connection_string()
        self.engine = create_engine(self.connection_string)

    def collect_metrics(self, *, season: int, week: int, slate: str) -> SlateReadinessMetrics:
        metrics = SlateReadinessMetrics(season=season, week=week, slate=slate.upper())
        inspector = inspect(self.engine)
        metrics.salary_table_available = inspector.has_table("curated_salary", schema="public")
        salary_rows: list[dict[str, Any]] = []

        with self.engine.begin() as connection:
            if metrics.salary_table_available:
                salary_rows = [
                    dict(row)
                    for row in connection.execute(
                        text(
                            """
                            SELECT DISTINCT ON (COALESCE(player_master_id, 'site:' || source_player_key))
                                COALESCE(player_master_id, 'site:' || source_player_key) AS player_id,
                                curated_salary_id::text AS source_record_key,
                                player_master_id,
                                COALESCE(NULLIF(position, ''), roster_position) AS position,
                                team, opponent, game_info, salary, created_at
                            FROM public.curated_salary
                            WHERE season = :season AND week = :week
                              AND UPPER(slate) = UPPER(:slate)
                            ORDER BY COALESCE(player_master_id, 'site:' || source_player_key), created_at DESC
                            """
                        ),
                        {"season": season, "week": week, "slate": slate},
                    ).mappings()
                ]
                roster_position_rows = connection.execute(
                    text(
                        """
                        SELECT UPPER(roster_position) AS roster_position, COUNT(*) AS rows
                        FROM public.curated_salary
                        WHERE season = :season AND week = :week
                          AND UPPER(slate) = UPPER(:slate)
                        GROUP BY UPPER(roster_position)
                        """
                    ),
                    {"season": season, "week": week, "slate": slate},
                ).mappings().all()
                metrics.roster_position_counts = {
                    str(row["roster_position"]): int(row["rows"])
                    for row in roster_position_rows
                    if row["roster_position"]
                }

            eligible_rows = [row for row in salary_rows if _normalized_position(row["position"]) in ELIGIBLE_POSITIONS]
            metrics.eligible_salary_rows = len(eligible_rows)
            metrics.position_counts = dict(Counter(_normalized_position(row["position"]) for row in eligible_rows))
            metrics.team_count = len({str(row["team"]).strip().upper() for row in eligible_rows if row.get("team")})
            metrics.resolved_identity_rows = sum(bool(row.get("player_master_id")) for row in eligible_rows)
            unresolved_record_keys = [
                str(row["source_record_key"])
                for row in eligible_rows
                if not row.get("player_master_id") and row.get("source_record_key")
            ]
            if (
                unresolved_record_keys
                and inspector.has_table("identity_quarantine", schema="target")
            ):
                quarantine_rows = connection.execute(
                    text(
                        """
                        SELECT source_record_key, reason_code
                        FROM target.identity_quarantine
                        WHERE source_schema = 'public'
                          AND source_table = 'curated_salary'
                          AND status = 'open'
                          AND source_record_key = ANY(:source_record_keys)
                        """
                    ),
                    {"source_record_keys": unresolved_record_keys},
                ).mappings().all()
                metrics.quarantined_identity_rows = len(quarantine_rows)
                metrics.quarantine_reason_counts = dict(
                    Counter(str(row["reason_code"]) for row in quarantine_rows)
                )
            metrics.complete_game_rows = sum(
                bool(row.get("team") and row.get("opponent") and row.get("game_info")) for row in eligible_rows
            )
            metrics.valid_salary_rows = sum(0 < int(row.get("salary") or 0) <= 50000 for row in eligible_rows)
            salary_times = [row["created_at"] for row in eligible_rows if row.get("created_at") is not None]
            metrics.salary_timestamp_rows = len(salary_times)
            metrics.salary_latest_created_at = max(salary_times) if salary_times else None
            metrics.slate_lock_at = parse_slate_lock(row.get("game_info") for row in eligible_rows)

            salary_positions = {str(row["player_id"]): _normalized_position(row["position"]) for row in eligible_rows}
            salary_player_ids = sorted(salary_positions)
            resolved_player_ids = sorted(
                str(row["player_id"]) for row in eligible_rows if row.get("player_master_id")
            )

            if inspector.has_table("snapshot_injury_status", schema="target"):
                injury = connection.execute(
                    text(
                        """
                        SELECT COUNT(*) AS rows, COUNT(*) FILTER (WHERE player_id IS NOT NULL) AS identified
                        FROM target.snapshot_injury_status
                        WHERE season = :season AND week = :week
                          AND (slate IS NULL OR UPPER(slate) = UPPER(:slate))
                        """
                    ),
                    {"season": season, "week": week, "slate": slate},
                ).mappings().one()
                metrics.injury_rows = int(injury["rows"] or 0)
                metrics.injury_identity_rows = int(injury["identified"] or 0)

            if inspector.has_table("player_projection", schema="target"):
                projection_runs = connection.execute(
                    text(
                        """
                        SELECT projection_run_id, MAX(created_at) AS latest_created_at
                        FROM target.player_projection
                        WHERE season = :season AND week = :week
                          AND (slate_id IS NULL OR UPPER(slate_id) = UPPER(:slate))
                        GROUP BY projection_run_id
                        ORDER BY latest_created_at DESC, projection_run_id
                        """
                    ),
                    {"season": season, "week": week, "slate": slate},
                ).mappings().all()
                metrics.projection_run_count = len(projection_runs)
                if projection_runs:
                    metrics.projection_run_id = str(projection_runs[0]["projection_run_id"])
                    if inspector.has_table("active_projection_run", schema="target"):
                        active_projection = connection.execute(
                            text(
                                """
                                SELECT projection_run_id
                                FROM target.active_projection_run
                                WHERE season = :season AND week = :week
                                  AND (UPPER(slate_id) = UPPER(:slate) OR slate_id = 'DEFAULT')
                                ORDER BY CASE WHEN UPPER(slate_id) = UPPER(:slate)
                                    THEN 0 ELSE 1 END, selected_at DESC
                                LIMIT 1
                                """
                            ),
                            {"season": season, "week": week, "slate": slate},
                        ).mappings().first()
                        if active_projection:
                            active_run_id = str(active_projection["projection_run_id"])
                            if any(
                                str(row["projection_run_id"]) == active_run_id
                                for row in projection_runs
                            ):
                                metrics.projection_run_id = active_run_id
                                metrics.projection_run_is_explicit = True
                    projection_rows = connection.execute(
                        text(
                            """
                            SELECT DISTINCT ON (player_id) player_id, mean, data_cutoff_at
                            FROM target.player_projection
                            WHERE season = :season AND week = :week
                              AND projection_run_id = :projection_run_id
                              AND (slate_id IS NULL OR UPPER(slate_id) = UPPER(:slate))
                              AND player_id = ANY(:player_ids)
                            ORDER BY player_id, created_at DESC, game_id
                            """
                        ),
                        {
                            "season": season,
                            "week": week,
                            "slate": slate,
                            "projection_run_id": metrics.projection_run_id,
                            "player_ids": salary_player_ids,
                        },
                    ).mappings().all() if salary_player_ids else []
                    metrics.projected_salary_rows = len(projection_rows)
                    positive_rows = [row for row in projection_rows if float(row["mean"] or 0) > 0]
                    metrics.positive_projection_rows = len(positive_rows)
                    metrics.positive_projection_positions = dict(
                        Counter(salary_positions[str(row["player_id"])] for row in positive_rows)
                    )
                    cutoff_values = [row["data_cutoff_at"] for row in projection_rows if row["data_cutoff_at"]]
                    metrics.projection_cutoff_rows = len(cutoff_values)
                    metrics.projection_data_cutoff_at = max(cutoff_values) if cutoff_values else None

            if inspector.has_table("ownership_projection", schema="target"):
                ownership = connection.execute(
                    text(
                        """
                        SELECT COUNT(*) AS rows
                        FROM target.ownership_projection
                        WHERE season = :season AND week = :week
                          AND UPPER(slate_id) = UPPER(:slate)
                          AND ownership_run_id = (
                              SELECT ownership_run_id
                              FROM target.ownership_projection
                              WHERE season = :season AND week = :week
                                AND UPPER(slate_id) = UPPER(:slate)
                              GROUP BY ownership_run_id
                              ORDER BY MAX(created_at) DESC, ownership_run_id
                              LIMIT 1
                          )
                        """
                    ),
                    {"season": season, "week": week, "slate": slate},
                ).scalar_one()
                metrics.ownership_rows = int(ownership or 0)

            if inspector.has_table("fact_player_game_actual", schema="target") and resolved_player_ids:
                actual_rows = connection.execute(
                    text(
                        """
                        SELECT DISTINCT player_id
                        FROM target.fact_player_game_actual
                        WHERE season = :season AND week = :week
                          AND dk_points IS NOT NULL AND player_id = ANY(:player_ids)
                        """
                    ),
                    {"season": season, "week": week, "player_ids": resolved_player_ids},
                ).mappings().all()
                metrics.actual_salary_rows = len(actual_rows)
                metrics.actual_position_counts = dict(
                    Counter(salary_positions[str(row["player_id"])] for row in actual_rows)
                )

            if inspector.has_table("dfs_contest", schema="target"):
                metrics.normalized_contest_rows = int(
                    connection.execute(
                        text(
                            """
                            SELECT COUNT(*) FROM target.dfs_contest
                            WHERE season = :season AND week = :week
                              AND UPPER(slate_id) = UPPER(:slate)
                            """
                        ),
                        {"season": season, "week": week, "slate": slate},
                    ).scalar_one()
                    or 0
                )
            if inspector.has_table("dk_contest_entries", schema="public"):
                metrics.legacy_contest_entry_rows = int(
                    connection.execute(
                        text(
                            """
                            SELECT COUNT(*) FROM public.dk_contest_entries
                            WHERE season = :season AND week = :week
                              AND UPPER(slate) = UPPER(:slate)
                            """
                        ),
                        {"season": season, "week": week, "slate": slate},
                    ).scalar_one()
                    or 0
                )
        return metrics

    def report(self, *, season: int, week: int, slate: str) -> dict[str, Any]:
        return evaluate_slate_readiness(self.collect_metrics(season=season, week=week, slate=slate))
