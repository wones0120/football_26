"""Shared point-in-time visibility rules for replay-safe snapshots."""

from __future__ import annotations

from datetime import datetime, timezone


POINT_IN_TIME_CUTOFF_CONTRACT_ID = "point_in_time_cutoff_v1"


def snapshot_visible_at_cutoff(
    observed_at: datetime | None,
    cutoff_at: datetime | None,
) -> bool:
    """Return true only when both timestamps exist and observation preceded cutoff."""
    if observed_at is None or cutoff_at is None:
        return False
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    if cutoff_at.tzinfo is None:
        cutoff_at = cutoff_at.replace(tzinfo=timezone.utc)
    return observed_at <= cutoff_at


def injury_snapshot_cutoff_sql(
    *,
    injury_alias: str = "injury",
    projection_alias: str = "p",
) -> str:
    """SQL predicate mirroring ``snapshot_visible_at_cutoff`` for injury rows."""
    return (
        f"{injury_alias}.as_of IS NOT NULL "
        f"AND {projection_alias}.data_cutoff_at IS NOT NULL "
        f"AND {injury_alias}.as_of <= {projection_alias}.data_cutoff_at"
    )
