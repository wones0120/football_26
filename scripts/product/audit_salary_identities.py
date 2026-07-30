#!/usr/bin/env python3
"""Reassess unresolved salary identities without changing canonical mappings."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Database.config import get_connection_string
from Database.dst import normalize_team
from Database.player_identity import (
    MasterIdentity,
    _aliases,
    choose_identity,
    normalize_position,
    strip_name_suffix,
)
from backend.app.product_services.readiness import ACCEPTED_IDENTITY_QUARANTINE_REASONS


AUDIT_CONTRACT_ID = "salary_identity_audit_v1"


def evaluate_unresolved_rows(
    masters: Iterable[MasterIdentity],
    salary_rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Re-run deterministic matching and classify retained quarantine rows."""
    master_rows = list(masters)
    unresolved_rows = list(salary_rows)
    decision_cache = {}
    decision_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    stored_reason_counts: Counter[str] = Counter()
    accepted_reason_counts: Counter[str] = Counter()
    deterministic_matches: list[dict[str, Any]] = []
    reason_mismatches: list[dict[str, Any]] = []
    untracked: list[str] = []
    unaccepted: list[dict[str, Any]] = []
    row_evidence: list[dict[str, Any]] = []

    for row in unresolved_rows:
        name = str(row.get("player_name") or "")
        team = normalize_team(str(row.get("team") or ""))
        position = normalize_position(row.get("position"))
        key = (strip_name_suffix(name), team, position)
        decision = decision_cache.get(key)
        if decision is None:
            decision = choose_identity(
                player_name=name,
                team=team,
                position=position,
                masters=master_rows,
            )
            decision_cache[key] = decision

        source_record_key = str(row.get("source_record_key") or "")
        stored_status = str(row.get("status") or "missing")
        stored_reason = str(row.get("reason_code") or "missing")
        decision_counts[decision.reason] += 1
        status_counts[stored_status] += 1
        stored_reason_counts[stored_reason] += 1

        if decision.player_id:
            row_evidence.append(
                {
                    "source_record_key": source_record_key,
                    "stored_status": stored_status,
                    "stored_reason": stored_reason,
                    "current_player_id": decision.player_id,
                    "current_reason": decision.reason,
                    "accepted": False,
                }
            )
            deterministic_matches.append(
                {
                    "source_record_key": source_record_key,
                    "season": row.get("season"),
                    "week": row.get("week"),
                    "slate": row.get("slate"),
                    "player_name": name,
                    "team": team,
                    "position": position,
                    "player_id": decision.player_id,
                    "reason": decision.reason,
                }
            )
            continue

        expected_reason = (
            decision.reason
            if decision.reason in {"ambiguous", "missing_name"}
            else "no_match"
        )
        if stored_status == "missing":
            untracked.append(source_record_key)
        if stored_reason != expected_reason:
            reason_mismatches.append(
                {
                    "source_record_key": source_record_key,
                    "stored": stored_reason,
                    "current": expected_reason,
                }
            )

        accepted = (
            stored_status == "open"
            and stored_reason == expected_reason
            and stored_reason in ACCEPTED_IDENTITY_QUARANTINE_REASONS
        )
        if accepted:
            accepted_reason_counts[stored_reason] += 1
        else:
            unaccepted.append(
                {
                    "source_record_key": source_record_key,
                    "status": stored_status,
                    "stored_reason": stored_reason,
                    "current_reason": expected_reason,
                }
            )
        row_evidence.append(
            {
                "source_record_key": source_record_key,
                "stored_status": stored_status,
                "stored_reason": stored_reason,
                "current_player_id": None,
                "current_reason": expected_reason,
                "accepted": accepted,
            }
        )

    return {
        "master_rows": len(master_rows),
        "unresolved_salary_rows": len(unresolved_rows),
        "current_decision_counts": dict(sorted(decision_counts.items())),
        "stored_status_counts": dict(sorted(status_counts.items())),
        "stored_reason_counts": dict(sorted(stored_reason_counts.items())),
        "accepted_quarantine_rows": sum(accepted_reason_counts.values()),
        "accepted_quarantine_reasons": dict(sorted(accepted_reason_counts.items())),
        "deterministic_match_count": len(deterministic_matches),
        "deterministic_match_sample": deterministic_matches[:25],
        "reason_mismatch_count": len(reason_mismatches),
        "reason_mismatch_sample": reason_mismatches[:25],
        "untracked_count": len(untracked),
        "untracked_sample": untracked[:25],
        "unaccepted_quarantine_count": len(unaccepted),
        "unaccepted_quarantine_sample": unaccepted[:25],
        "row_evidence_sha256": hashlib.sha256(
            json.dumps(row_evidence, sort_keys=True).encode()
        ).hexdigest(),
    }


def audit_salary_identities(engine) -> dict[str, Any]:
    """Collect and evaluate canonical salary-identity coverage."""
    with engine.begin() as connection:
        totals = dict(
            connection.execute(
                text(
                    """
                    SELECT COUNT(*)::int AS salary_rows,
                           COUNT(*) FILTER (WHERE player_master_id IS NOT NULL)::int
                               AS resolved_salary_rows,
                           COUNT(*) FILTER (
                               WHERE player_master_id IS NULL
                                 AND upper(trim(COALESCE(NULLIF(position, ''), roster_position, '')))
                                     IN ('D', 'DEF', 'DST')
                           )::int AS unresolved_dst_rows
                    FROM public.curated_salary
                    """
                )
            ).mappings().one()
        )
        master_db_rows = connection.execute(
            text(
                """
                SELECT player_master_id::text AS player_id, full_name,
                       COALESCE(normalized_name, '') AS normalized_name,
                       COALESCE(name_norm, '') AS name_norm,
                       COALESCE(primary_team, '') AS team,
                       COALESCE(position, '') AS position,
                       COALESCE(aliases, '[]'::jsonb) AS aliases
                FROM public.player_master
                """
            )
        ).mappings().all()
        salary_rows = connection.execute(
            text(
                """
                SELECT salary.curated_salary_id::text AS source_record_key,
                       salary.season, salary.week, salary.slate,
                       salary.player_name, salary.team, salary.position,
                       quarantine.reason_code, quarantine.status
                FROM public.curated_salary salary
                LEFT JOIN target.identity_quarantine quarantine
                  ON quarantine.source_schema = 'public'
                 AND quarantine.source_table = 'curated_salary'
                 AND quarantine.source_record_key = salary.curated_salary_id::text
                WHERE salary.player_master_id IS NULL
                  AND upper(trim(COALESCE(NULLIF(salary.position, ''), salary.roster_position, '')))
                      NOT IN ('D', 'DEF', 'DST')
                ORDER BY salary.season, salary.week, salary.curated_salary_id
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
        for row in master_db_rows
    ]
    decision_report = evaluate_unresolved_rows(masters, salary_rows)
    blockers = {
        "deterministic_matches": decision_report["deterministic_match_count"],
        "reason_mismatches": decision_report["reason_mismatch_count"],
        "untracked": decision_report["untracked_count"],
        "unaccepted_quarantine": decision_report["unaccepted_quarantine_count"],
        "unresolved_dst": totals["unresolved_dst_rows"],
    }
    status = "pass" if not any(blockers.values()) else "fail"
    stable_payload = {"contract_id": AUDIT_CONTRACT_ID, **totals, **decision_report, "blockers": blockers}
    audit_sha256 = hashlib.sha256(
        json.dumps(stable_payload, sort_keys=True, default=str).encode()
    ).hexdigest()
    return {
        "contract_id": AUDIT_CONTRACT_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "audit_sha256": audit_sha256,
        **totals,
        **decision_report,
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reassess unresolved salary identities without changing mappings."
    )
    parser.add_argument(
        "--database",
        help="Optional database override; defaults to the canonical repo-local configuration.",
    )
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    connection_url = make_url(get_connection_string())
    if args.database:
        connection_url = connection_url.set(database=args.database)
    report = audit_salary_identities(create_engine(connection_url))
    print(json.dumps(report, indent=2 if args.pretty else None, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
