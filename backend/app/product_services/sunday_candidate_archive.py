"""Persistent, versioned candidate archive for a single Classic slate."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


CONTRACT_ID = "classic_slate_candidate_archive_v1"
INACTIVE_STATUSES = {
    "OUT", "O", "IR", "INA", "INACTIVE", "PUP", "SUS", "RES",
    "PS", "PRACTICE_SQUAD",
}


def lineup_key(player_ids: Iterable[str]) -> str:
    ids = sorted(str(player_id).strip() for player_id in player_ids if str(player_id).strip())
    return "|".join(ids)


def _candidate_ids(row: Mapping[str, Any]) -> list[str]:
    for field in ("player_ids", "lineup_key"):
        value = row.get(field)
        if isinstance(value, list) and len(value) == 9:
            return [str(player_id) for player_id in value]
    roster = row.get("roster")
    if isinstance(roster, list) and len(roster) == 9 and all(isinstance(item, Mapping) for item in roster):
        ids = [str(item.get("player_id") or "") for item in roster]
        if all(ids):
            return ids
    return []


def extract_candidates(payload: Any, *, source: str, source_sha256: str) -> list[dict[str, Any]]:
    """Find serialized nine-player lineups without joining on display names."""
    output: list[dict[str, Any]] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            ids = _candidate_ids(value)
            if len(ids) == 9 and len(set(ids)) == 9:
                output.append({
                    "lineup_key": lineup_key(ids),
                    "player_ids": sorted(ids),
                    "source": source,
                    "source_path": path,
                    "source_sha256": source_sha256,
                    "source_rank": value.get("rank") or value.get("shadow_rank") or value.get("previous_rank"),
                })
            for key, child in value.items():
                visit(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")

    visit(payload, "$")
    return output


def artifact_candidates(path: Path, *, source: str | None = None) -> list[dict[str, Any]]:
    raw = path.read_bytes()
    payload = json.loads(raw)
    return extract_candidates(
        payload,
        source=source or str(path),
        source_sha256=hashlib.sha256(raw).hexdigest(),
    )


def new_archive(*, season: int, week: int, slate: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "contract_id": CONTRACT_ID,
        "season": int(season),
        "week": int(week),
        "slate": str(slate).upper(),
        "created_at": now,
        "updated_at": now,
        "candidates": {},
        "refresh_history": [],
    }


def load_archive(path: Path, *, season: int, week: int, slate: str) -> dict[str, Any]:
    if not path.exists():
        return new_archive(season=season, week=week, slate=slate)
    archive = json.loads(path.read_text())
    expected = (int(season), int(week), str(slate).upper())
    actual = (int(archive["season"]), int(archive["week"]), str(archive["slate"]).upper())
    if archive.get("contract_id") != CONTRACT_ID or actual != expected:
        raise ValueError(f"Candidate archive scope mismatch: expected {expected}, got {actual}")
    return archive


def merge_discoveries(
    archive: dict[str, Any], discoveries: Iterable[Mapping[str, Any]], *, observed_at: str,
) -> dict[str, int]:
    candidates = archive.setdefault("candidates", {})
    discovered_rows = list(discoveries)
    unique_input = {str(row["lineup_key"]) for row in discovered_rows}
    existing_keys = set(candidates)
    for row in discovered_rows:
        key = str(row["lineup_key"])
        candidate = candidates.setdefault(key, {
            "lineup_key": key,
            "player_ids": list(row["player_ids"]),
            "first_seen_at": observed_at,
            "last_seen_at": observed_at,
            "discoveries": [],
            "current_validation": None,
        })
        candidate["last_seen_at"] = observed_at
        discovery = {
            "source": row["source"],
            "source_path": row["source_path"],
            "source_sha256": row["source_sha256"],
            "source_rank": row.get("source_rank"),
            "observed_at": observed_at,
        }
        signature = (discovery["source"], discovery["source_path"], discovery["source_sha256"])
        known = {
            (item["source"], item["source_path"], item["source_sha256"])
            for item in candidate["discoveries"]
        }
        if signature not in known:
            candidate["discoveries"].append(discovery)
    archive["updated_at"] = observed_at
    return {
        "input_candidate_rows": len(discovered_rows),
        "unique_input_candidates": len(unique_input),
        "duplicates_removed": len(discovered_rows) - len(unique_input),
        "new_archive_candidates": len(unique_input - existing_keys),
        "previous_archive_candidates": len(existing_keys),
    }


def _status_values(row: Mapping[str, Any]) -> list[str]:
    return [
        str(row.get(field) or "").strip().upper()
        for field in ("roster_status", "player_status", "pregame_injury_status", "injury_status")
    ]


def validate_candidate(
    player_ids: Iterable[str], *, players_by_id: Mapping[str, Any],
    pool_by_id: Mapping[str, Mapping[str, Any]], single_te: bool = True,
    excluded_opponents: set[str] | None = None, max_from_team: int = 4,
    max_from_game: int = 5, avoid_dst_opponents: bool = True,
    require_bring_back: bool = False,
) -> dict[str, Any]:
    ids = [str(player_id) for player_id in player_ids]
    reasons: list[str] = []
    if len(ids) != 9:
        reasons.append(f"roster_size:{len(ids)}")
    if len(set(ids)) != len(ids):
        reasons.append("duplicate_player_id")
    missing = sorted(set(ids) - set(players_by_id))
    if missing:
        reasons.append("missing_from_current_eligible_pool:" + ",".join(missing))
    if reasons:
        return {"legal": False, "reasons": reasons, "checks": {
            "roster_size": len(ids) == 9,
            "unique_players": len(set(ids)) == len(ids),
            "current_eligible_pool": not missing,
        }}

    players = [players_by_id[player_id] for player_id in ids]
    positions = [str(player.position).upper() for player in players]
    if positions.count("QB") != 1:
        reasons.append("requires_exactly_one_qb")
    if sum(position in {"DST", "D", "DEF"} for position in positions) != 1:
        reasons.append("requires_exactly_one_dst")
    if positions.count("RB") < 2 or positions.count("WR") < 3 or positions.count("TE") < 1:
        reasons.append("classic_position_minimums")
    if single_te and positions.count("TE") > 1:
        reasons.append("single_te")
    salary = sum(int(player.salary) for player in players)
    if salary > 50_000:
        reasons.append(f"salary_cap:{salary}")

    team_counts: dict[str, int] = {}
    game_counts: dict[str, int] = {}
    excluded = {team.upper() for team in (excluded_opponents or set())}
    for player in players:
        team_counts[player.team] = team_counts.get(player.team, 0) + 1
        if player.game_id:
            game_counts[player.game_id] = game_counts.get(player.game_id, 0) + 1
        if str(player.opponent).upper() in excluded:
            reasons.append(f"excluded_opponent:{player.name}:{player.opponent}")
        source = pool_by_id.get(str(player.player_id), {})
        if any(status in INACTIVE_STATUSES or "PRACTICE" in status for status in _status_values(source)):
            reasons.append(f"inactive:{player.name}")
        if player.projection is None or player.ceiling is None:
            reasons.append(f"projection_unavailable:{player.name}")
    if max(team_counts.values(), default=0) > max_from_team:
        reasons.append("max_from_team")
    if max(game_counts.values(), default=0) > max_from_game:
        reasons.append("max_from_game")

    qb = next((player for player in players if player.position == "QB"), None)
    dst = next((player for player in players if player.position in {"DST", "D", "DEF"}), None)
    if qb:
        partners = [player for player in players if player.team == qb.team and player.position in {"RB", "WR", "TE"}]
        bring_backs = [player for player in players if player.team == qb.opponent and player.position in {"RB", "WR", "TE"}]
        if not partners:
            reasons.append("qb_stack_missing")
        if require_bring_back and not bring_backs:
            reasons.append("bring_back_missing")
    if avoid_dst_opponents and dst:
        conflicting = [player.name for player in players if player.position not in {"DST", "D", "DEF"} and player.team == dst.opponent]
        if conflicting:
            reasons.append("dst_opponent_conflict:" + ",".join(sorted(conflicting)))
    return {
        "legal": not reasons,
        "reasons": reasons,
        "salary": salary,
        "checks": {
            "dk_roster_legal": (
                len(ids) == 9 and len(set(ids)) == 9 and positions.count("QB") == 1
                and sum(position in {"DST", "D", "DEF"} for position in positions) == 1
                and positions.count("RB") >= 2 and positions.count("WR") >= 3
                and positions.count("TE") >= 1
            ),
            "salary_legal": salary <= 50_000,
            "qb_stack_present": bool(qb and partners),
            "bring_back_present": bool(qb and bring_backs),
            "bring_back_required": bool(require_bring_back),
            "single_te_legal": not single_te or positions.count("TE") <= 1,
            "active_eligible": not any(reason.startswith("inactive:") for reason in reasons),
            "excluded_opponents_clear": not any(reason.startswith("excluded_opponent:") for reason in reasons),
            "dst_conflict_clear": not any(reason.startswith("dst_opponent_conflict:") for reason in reasons),
            "projection_available": not any(reason.startswith("projection_unavailable:") for reason in reasons),
        },
    }


def persist_archive(path: Path, archive: Mapping[str, Any], *, refresh_id: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    snapshots = path.parent / "snapshots"
    snapshots.mkdir(parents=True, exist_ok=True)
    snapshot = snapshots / f"{refresh_id}.json"
    body = json.dumps(archive, indent=2, sort_keys=True, default=str) + "\n"
    if snapshot.exists():
        if snapshot.read_text() != body:
            raise ValueError(f"Immutable archive snapshot already exists with different content: {snapshot}")
    else:
        snapshot.write_text(body)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(body)
    os.replace(temporary, path)
    return snapshot
