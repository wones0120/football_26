"""Shared eligibility policy for salary-feed player availability statuses."""

from __future__ import annotations


INELIGIBLE_SALARY_STATUSES = frozenset(
    {
        "INACTIVE",
        "IR",
        "NFI",
        "O",
        "OUT",
        "PUP",
        "RES",
        "RESERVE",
        "SUSP",
        "SUSPENDED",
    }
)
INELIGIBLE_SALARY_STATUSES_SQL = ", ".join(
    f"'{status}'" for status in sorted(INELIGIBLE_SALARY_STATUSES)
)


def normalize_salary_status(value: object) -> str:
    """Return the canonical uppercase status token used by eligibility gates."""
    if value is None:
        return ""
    normalized = str(value).strip().upper()
    if normalized in {"<NA>", "NAN", "NONE", "NULL"}:
        return ""
    return normalized


def is_salary_status_eligible(value: object) -> bool:
    """Keep blank/questionable/doubtful rows; exclude confirmed unavailability."""
    return normalize_salary_status(value) not in INELIGIBLE_SALARY_STATUSES
