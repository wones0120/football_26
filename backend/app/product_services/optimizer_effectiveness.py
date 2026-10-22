"""Post-slate optimizer diagnostics from saved pregame pools and canonical actuals.

This module never writes to an optimizer run. Pregame records are copied into a
separate namespace before postgame scores are attached.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
import math
import re
from statistics import median
from typing import Any, Callable, Iterable, Mapping
from zoneinfo import ZoneInfo

from .workload_evidence import SUPPORTED_CONTRACT_IDS


POOL_PATHS = (
    ("strategy_runtime", "single_lineup", "all_candidates"),
    ("strategy_runtime", "strategy_contract_audit", "candidate_rosters"),
    ("strategy_runtime", "classic_small_field", "all_candidates"),
    ("strategy_runtime", "showdown_portfolio_policy", "candidate_selection", "ranked_metrics"),
    ("strategy_runtime", "single_entry", "all_candidates"),
    ("strategy_runtime", "three_max", "all_candidates"),
    ("strategy_runtime", "small_max", "all_candidates"),
)
THRESHOLD_PCTS = (0.1, 1, 5, 10, 20)
_LINEUP_PATTERN = re.compile(r"\b(CPT|DST|FLEX|QB|RB|WR|TE)\s+(.+?)(?=\s+(?:CPT|DST|FLEX|QB|RB|WR|TE)\s+|$)")


def _frequency(counter: Counter, limit: int | None = None) -> list:
    # Counter insertion order must not make tied counts depend on Python hash seeds.
    return sorted(counter.items(), key=lambda item: (-item[1], str(item[0])))[:limit]


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (ValueError, TypeError):
        return None
    return result if math.isfinite(result) else None


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            result = json.loads(value)
        except ValueError:
            return {}
        return dict(result) if isinstance(result, Mapping) else {}
    return {}


def _digest(value: Any) -> str:
    digest = hashlib.sha256()
    for chunk in json.JSONEncoder(sort_keys=True, separators=(",", ":"), default=str).iterencode(value):
        digest.update(chunk.encode())
    return digest.hexdigest()


def _name(value: Any) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", str(value or "").casefold()).split())


def candidate_signature(candidate: Mapping[str, Any], contest_format: str) -> tuple[tuple[str, bool], ...] | None:
    """Use canonical IDs and CPT identity; FLEX is a roster slot, not a player."""
    roster = candidate.get("players") or candidate.get("roster")
    if isinstance(roster, list) and roster and all(isinstance(item, Mapping) for item in roster):
        pairs = [(str(item.get("player_id") or ""), str(item.get("slot") or item.get("roster_position") or "").upper() == "CPT") for item in roster]
    elif isinstance(candidate.get("signature"), (list, tuple)):
        pairs = [(str(item[0]), bool(item[1])) for item in candidate["signature"]]
    elif isinstance(candidate.get("player_ids"), list) and contest_format == "classic":
        pairs = [(str(item), False) for item in candidate["player_ids"]]
    else:
        return None
    required = 6 if contest_format == "showdown" else 9
    if len(pairs) != required or any(not player_id for player_id, _ in pairs):
        return None
    if len({player_id for player_id, _ in pairs}) != required:
        return None
    if contest_format == "showdown" and sum(captain for _, captain in pairs) != 1:
        return None
    return tuple(sorted(pairs))


def _analyst_saved_pool(config, contest_format):
    """Adapt persisted canonical Analyst variants, never today's projections."""
    analyst = _mapping(_mapping(config.get("strategy_runtime")).get("football_analyst"))
    original = analyst.get("candidates")
    if not isinstance(original, list) or not original:
        return None
    snapshot = _mapping(analyst.get("input_snapshot"))
    players = {}
    for row in snapshot.get("players") or []:
        if not isinstance(row, Mapping):
            return {"status":"unavailable","reason":"analyst_snapshot_identity_missing_or_duplicate"}
        pid = str(row.get("player_id") or "")
        if not pid or pid in players:
            return {"status":"unavailable","reason":"analyst_snapshot_identity_missing_or_duplicate"}
        players[pid] = row
    manifest=_mapping(_mapping(config.get("strategy_runtime")).get("candidate_pool_manifest"))
    if manifest.get("source_path")=="strategy_runtime.football_analyst.candidates" and manifest.get("sha256") and manifest["sha256"]!=_digest(original):
        return {"status":"unavailable","reason":"candidate_pool_hash_mismatch"}
    converted = []
    for index, raw in enumerate(original, 1):
        roster = raw.get("roster") if isinstance(raw, Mapping) else None
        if not isinstance(roster, list) or any(not isinstance(r, Mapping) or not r.get("player_master_id") for r in roster):
            return {"status":"unavailable","reason":"saved_candidate_rows_lack_canonical_rosters"}
        forbidden = {"postgame", "actual_points", "actual_score", "actual_rank"}
        if forbidden.intersection(raw) or any(forbidden.intersection(r) for r in roster):
            return {"status":"unavailable","reason":"postgame_data_in_saved_candidate_pool"}
        if contest_format == "showdown" and any(r.get("role") not in {"CPT","FLEX"} for r in roster):
            return {"status":"unavailable","reason":"analyst_showdown_role_missing"}
        if contest_format=="classic" and any(r.get("role")=="CPT" for r in roster):
            return {"status":"unavailable","reason":"analyst_classic_captain_invalid"}
        normalized = [{"player_id":str(r["player_master_id"]),"slot":r.get("role")} for r in roster]
        candidate = {"roster":normalized,"candidate_id":raw.get("candidate_id"),
            "source_candidate_ordinal":index,"source_candidate_sha256":_digest(raw),
            "source_scenario_ids":raw.get("scenario_ids"),"source_scenario_scores":raw.get("scores"),
            "analyst_adapter":True,"games_represented":[],"mean":None,"p90":None,"salary":None}
        if candidate_signature(candidate, contest_format) is None:
            return {"status":"unavailable","reason":"saved_candidate_rows_lack_canonical_rosters"}
        terms=[]
        for r in normalized:
            row=players.get(r["player_id"])
            if row is None:break
            terms.append((row,1.5 if contest_format=="showdown" and r["slot"]=="CPT" else 1))
        if len(terms)==len(roster):
            for target,source in (("mean","projection"),("p90","p90"),("salary","salary")):
                values=[_number(row.get(source)) for row,mult in terms]
                if all(v is not None for v in values):candidate[target]=sum(v*mult for v,(row,mult) in zip(values,terms))
            candidate["games_represented"] = sorted({str(row["game_id"]) for row,mult in terms if row.get("game_id")})
        converted.append(candidate)
    signatures=[candidate_signature(c,contest_format) for c in converted]
    return {"status":"original_candidate_pool","source_path":"strategy_runtime.football_analyst.candidates",
        "adapter_contract":"saved_analyst_candidate_adapter_v1","sha256":_digest(original),
        "source_input_snapshot_sha256":analyst.get("input_snapshot_sha256"),
        "source_candidate_identity":"original candidate_id where recorded; source array ordinal/hash are adapter lineage, not selector rank",
        "source_chronology_verified":False,"count":len(original),"candidates":converted,
        "unique_roster_count":len(set(signatures)),"scenario_variant_duplicates":len(original)-len(set(signatures)),
        "metric_basis":"mean/P90 sum from frozen baseline player moments with Captain multiplier once; scenario scores retained separately, no objective inferred"}


def extract_saved_pool(config: Any, contest_format: str) -> dict[str, Any]:
    """Only saved runtime candidates qualify as original; never synthesize a pool."""
    source = _mapping(config)
    for path in POOL_PATHS:
        value: Any = source
        for key in path:
            value = value.get(key) if isinstance(value, Mapping) else None
        if not isinstance(value, list) or not value:
            continue
        if path[1] == "strategy_contract_audit":
            effective = _mapping(_mapping(source.get("effective_strategy_contract")).get("effective"))
            if effective.get("generation") != "sequential exposure-aware ILP; accepted candidates are the selected portfolio":
                continue
            if len(value) != effective.get("entry_count"):
                return {"status": "unavailable", "reason": "incomplete_sequential_candidate_pool"}
        forbidden = {"postgame", "actual_points", "actual_score", "actual_rank"}
        if any(forbidden.intersection(row) or any(
                forbidden.intersection(player) for player in (row.get("roster") or row.get("players") or [])
                if isinstance(player, Mapping)) for row in value if isinstance(row, Mapping)):
            return {"status": "unavailable", "reason": "postgame_data_in_saved_candidate_pool",
                    "source_path": ".".join(path), "saved_rows": len(value)}
        signatures = [candidate_signature(row, contest_format) for row in value]
        if any(signature is None for signature in signatures):
            return {"status": "unavailable", "reason": "saved_candidate_rows_lack_canonical_rosters",
                    "source_path": ".".join(path), "saved_rows": len(value)}
        saved_manifest = _mapping(_mapping(source.get("strategy_runtime")).get("candidate_pool_manifest"))
        if saved_manifest.get("sha256") and saved_manifest["sha256"] != _digest(value):
            return {"status": "unavailable", "reason": "candidate_pool_hash_mismatch",
                    "source_path": ".".join(path), "saved_rows": len(value)}
        return {"status": "original_candidate_pool", "source_path": ".".join(path),
                "sha256": _digest(value), "candidates": value, "count": len(value),
                "unique_roster_count": len(set(signatures)),
                "scenario_variant_duplicates": len(value) - len(set(signatures))}
    return _analyst_saved_pool(source, contest_format) or {"status": "unavailable", "reason": "no_complete_saved_candidate_pool"}


def candidate_snapshot(config: Any, contest_format: str) -> dict[str, Any]:
    """Small deterministic lineage manifest for the already persisted pregame pool."""
    pool = extract_saved_pool(config, contest_format)
    manifest = {"contract_id": "candidate_pool_manifest_v1",
            **{key: pool[key] for key in ("status", "source_path", "sha256", "count",
                                         "unique_roster_count", "scenario_variant_duplicates", "reason") if key in pool}}
    evidence = saved_workload_evidence(config)
    if evidence:
        manifest["workload_evidence"] = {
            "contract_id": saved_workload_contract(evidence), "sha256": _digest(evidence),
            "player_count": len(evidence),
            "source_path": "strategy_runtime.player_pool.rows[player_id].workload_evidence",
            "linkage": "canonical player_id; shared by all saved candidate variants and CPT/FLEX roles",
        }
    return manifest


def saved_workload_evidence(config: Any) -> dict[str, dict]:
    """Only read saved packets; never reconstruct missing historical evidence."""
    runtime = _mapping(_mapping(config).get("strategy_runtime"))
    return {str(row["player_id"]): row["workload_evidence"]
            for row in _mapping(runtime.get("player_pool")).get("rows", [])
            if isinstance(row, Mapping) and row.get("player_id")
            and isinstance(row.get("workload_evidence"), Mapping)
            and row["workload_evidence"].get("contract_id") in SUPPORTED_CONTRACT_IDS}


def saved_workload_contract(evidence):
    """Report original saved versions, without stamping legacy packets as v2."""
    versions = {row["contract_id"] for row in evidence.values()}
    return next(iter(versions)) if len(versions) == 1 else "mixed_saved_workload_versions" if versions else None


def chronological_validation(run: Mapping[str, Any], pool: Mapping[str, Any]) -> dict[str, Any]:
    """Accept aggregation only with a saved kickoff strictly after the run decision."""
    if pool.get("status") not in {"original_candidate_pool", "slate_source_pool"}:
        return {"status": "unavailable", "reason": "original_candidate_pool_unavailable"}
    kicks = []
    game_rows = list(pool["candidates"]) + [{"games_represented": run.get("saved_lineup_games", [])}]
    for candidate in game_rows:
        for game in candidate.get("games_represented") or []:
            match = re.search(r"\b(\d{2}/\d{2}/\d{4} \d{2}:\d{2}[AP]M) ET\b", str(game))
            if match:
                kicks.append(datetime.strptime(match.group(1), "%m/%d/%Y %I:%M%p")
                             .replace(tzinfo=ZoneInfo("America/New_York")))
    # The frozen input frame contains all slate games, including games absent
    # from selected candidates. Never substitute today's schedule or salaries.
    config = _mapping(run.get("constraint_config_json"))
    runtime = _mapping(config.get("strategy_runtime"))
    frozen = _mapping(config.get("showdown_evidence_snapshot"))
    classic = _mapping(_mapping(runtime.get("classic_run_input_snapshot")).get("payload"))
    frames = [frozen.get("player_pool") or [], classic.get("players") or [],
              _mapping(_mapping(config.get("effective_strategy_contract")).get("effective")).get("players") or []]
    for rows in frames:
        for row in rows:
            game = str(row.get("game_id") or "")
            match = re.search(r"\b(\d{2}/\d{2}/\d{4} \d{2}:\d{2}[AP]M) ET\b", game)
            if match:
                kicks.append(datetime.strptime(match.group(1), "%m/%d/%Y %I:%M%p")
                             .replace(tzinfo=ZoneInfo("America/New_York")))
    if not kicks:
        return {"status": "unavailable", "reason": "saved_kickoff_evidence_unavailable"}
    cutoff = run.get("data_cutoff_at")
    created = run.get("optimizer_created_at")
    created_basis = "optimizer_database_timestamp"
    # Older writers inserted naive UTC into a session-local TIMESTAMPTZ column.
    # Recover only from an explicitly zoned timestamp in the ORIGINAL snapshot.
    frozen_created = frozen.get("frozen_at") or _mapping(classic.get("metadata")).get("created_at")
    if isinstance(frozen_created, str):
        try:
            observed = datetime.fromisoformat(frozen_created)
            if observed.tzinfo is not None:
                created, created_basis = observed, "original_frozen_input_timestamp"
        except ValueError:
            pass
    try:
        cutoff = datetime.fromisoformat(cutoff) if isinstance(cutoff, str) else cutoff
        created = datetime.fromisoformat(created) if isinstance(created, str) else created
        valid = bool(cutoff and created and cutoff.tzinfo and created.tzinfo
                     and cutoff < min(kicks) and created < min(kicks))
    except ValueError:
        valid = False
    if pool.get("adapter_contract"):
        return {"status":"unavailable", "reason":"original_code_and_source_availability_proof_not_verified",
            "stored_timing_status":"predecision" if valid else "unavailable",
            "first_saved_kickoff_at":min(kicks).isoformat(),"input_cutoff_at":cutoff.isoformat() if isinstance(cutoff,datetime) else cutoff,
            "decision_at":created.isoformat() if isinstance(created,datetime) else created,
            "decision_time_basis":created_basis,"retrospective_scoring_only":True,
            "limitation":"Saved timestamps establish timing correspondence, not original source availability or code reproducibility."}
    return {"status": "predecision" if valid else "unavailable",
            "reason": None if valid else "cutoff_or_run_creation_not_before_saved_kickoff",
            "first_saved_kickoff_at": min(kicks).isoformat(),
            "decision_at": created.isoformat() if isinstance(created, datetime) else created,
            "decision_time_basis": created_basis,
            "input_cutoff_at": cutoff.isoformat() if isinstance(cutoff, datetime) else cutoff}


def actual_points_by_player(observations: Iterable[Mapping[str, Any]], contest_format: str) -> dict[str, float]:
    """Resolve base DK points; CPT observations already contain the 1.5 multiplier."""
    values: dict[str, set[float]] = defaultdict(set)
    for row in observations:
        if row.get("resolution_status") != "resolved" or not row.get("player_id"):
            continue
        points = _number(row.get("actual_points"))
        if points is None:
            continue
        slot = str(row.get("roster_position") or "").upper()
        base = points / 1.5 if contest_format == "showdown" and slot == "CPT" else points
        values[str(row["player_id"])].add(round(base, 2))
    return {player_id: next(iter(scores)) for player_id, scores in values.items() if len(scores) == 1}


def score_signature(signature: tuple[tuple[str, bool], ...], actuals: Mapping[str, float]) -> tuple[float | None, list[str]]:
    missing = sorted({player_id for player_id, _ in signature if player_id not in actuals})
    if missing:
        return None, missing
    return round(sum(actuals[player_id] * (1.5 if captain else 1.0)
                     for player_id, captain in signature), 2), []


def _quantile(scores: list[float], fraction: float) -> float | None:
    if not scores:
        return None
    ordered = sorted(scores)
    index = fraction * (len(ordered) - 1)
    low = math.floor(index)
    high = math.ceil(index)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def field_benchmarks(
    contest: Mapping[str, Any], entries: Iterable[Mapping[str, Any]],
    payout_tiers: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    rows = list(entries)
    scores = [_number(row.get("entry_points")) for row in rows]
    size = int(contest.get("field_size") or 0)
    if not size or len(rows) != size or any(score is None for score in scores):
        return {"status": "unavailable", "reason": "complete_scored_field_not_imported",
                "field_size": size, "observed_entries": len(rows)}
    ordered = sorted((float(score) for score in scores if score is not None), reverse=True)
    thresholds = {f"top_{pct:g}_percent": ordered[max(0, math.ceil(size * pct / 100) - 1)]
                  for pct in THRESHOLD_PCTS}
    paid = [int(tier["max_rank"]) for tier in payout_tiers
            if _number(tier.get("payout")) is not None and float(tier["payout"]) > 0]
    cash_rank = max(paid, default=None)
    if cash_rank is None and contest.get('paid_places_source') == 'draftkings_entry_history':
        exported_paid = contest.get('places_paid')
        if isinstance(exported_paid, int) and 0 < exported_paid <= size:
            cash_rank = exported_paid
    cash = ordered[cash_rank - 1] if cash_rank and cash_rank <= size else None
    return {"status": "available", "field_size": size, "winner": ordered[0],
            "median": median(ordered), "thresholds": thresholds, "cash_line": cash,
            "cash_line_reason": None if cash is not None else "paid_rank_or_payout_unavailable",
            "cash_rank": cash_rank, "field_scores_desc": ordered}


def field_rank(points: float, scores_desc: list[float]) -> dict[str, Any]:
    # Benchmarks already sort the field descending; avoid scanning it per candidate.
    above = bisect_left(scores_desc, -(points + 0.005), key=lambda score: -score)
    tied_or_above = bisect_right(scores_desc, -(points - 0.005), key=lambda score: -score)
    return {"best_rank": above + 1, "worst_rank": max(above + 1, tied_or_above),
            "top_percent_conservative": 100 * tied_or_above / len(scores_desc)}


def top_field_constructions(
    contest_id: str, entries: Iterable[Mapping[str, Any]],
    observations: Iterable[Mapping[str, Any]], salary_context: Iterable[Mapping[str, Any]],
    benchmark: Mapping[str, Any], contest_format: str,
) -> dict[str, Any]:
    """Describe fully resolved top field lineups; report identity coverage explicitly."""
    if benchmark.get("status") != "available":
        return {"status": "unavailable", "reason": "complete_field_unavailable"}
    identities: dict[tuple[str, str], set[str]] = defaultdict(set)
    ownership: dict[tuple[str, str], float] = {}
    for row in observations:
        if str(row.get("contest_id")) != contest_id or row.get("resolution_status") != "resolved":
            continue
        player_id = str(row.get("player_id") or "")
        slot = str(row.get("roster_position") or "").upper()
        key = (_name(row.get("player_display_name")), slot)
        if player_id:
            identities[key].add(player_id)
            value = _number(row.get("actual_ownership"))
            if value is not None:
                ownership[(player_id, slot)] = value
    context: dict[tuple[str, str], dict[str, Any]] = {}
    for row in salary_context:
        player_id = str(row.get("player_id") or "")
        slot = str(row.get("roster_position") or "").upper()
        if player_id and slot:
            context[(player_id, slot)] = dict(row)
    result = {}
    for pct in (0.1, 1, 5):
        threshold = benchmark["thresholds"][f"top_{pct:g}_percent"]
        top_entries = [row for row in entries if _number(row.get("entry_points")) is not None
                       and float(row["entry_points"]) >= threshold - .005]
        player_counts: Counter[str] = Counter()
        qb_counts: Counter[str] = Counter()
        captain_counts: Counter[str] = Counter()
        stack_counts: Counter[str] = Counter()
        split_counts: Counter[str] = Counter()
        game_counts: Counter[str] = Counter()
        salary_left = []
        ownership_sums = []
        low_owned_counts = []
        resolved_count = 0
        for entry in top_entries:
            parsed = _LINEUP_PATTERN.findall(str(entry.get("lineup_text") or ""))
            if len(parsed) != (6 if contest_format == "showdown" else 9):
                continue
            lineup = []
            for slot, display_name in parsed:
                allowed = ("RB", "WR", "TE") if slot == "FLEX" and contest_format == "classic" else (slot,)
                ids = set().union(*(identities.get((_name(display_name), candidate_slot), set())
                                    for candidate_slot in allowed))
                if len(ids) != 1:
                    break
                player_id = next(iter(ids))
                metadata = context.get((player_id, slot)) or next(
                    (value for (pid, _), value in context.items() if pid == player_id), {})
                actual_ownership = ownership.get((player_id, slot))
                if actual_ownership is None:
                    actual_ownership = next((value for (pid, _), value in ownership.items() if pid == player_id), None)
                lineup.append({"player_id": player_id, "slot": slot, "context": metadata,
                               "ownership": actual_ownership})
            if len(lineup) != len(parsed) or len({row["player_id"] for row in lineup}) != len(parsed):
                continue
            resolved_count += 1
            player_counts.update(row["player_id"] for row in lineup)
            game_counts.update({str(row["context"]["game_id"]) for row in lineup
                                if row["context"].get("game_id")})
            qb = next((row for row in lineup if row["slot"] == "QB"), None)
            captain = next((row for row in lineup if row["slot"] == "CPT"), None)
            if captain:
                captain_counts[captain["player_id"]] += 1
            if contest_format == "showdown" and all(row["context"].get("team_id") for row in lineup):
                team_counts = Counter(row["context"]["team_id"] for row in lineup)
                split_counts["-".join(str(count) for count in sorted(team_counts.values(), reverse=True))] += 1
            if qb:
                qb_counts[qb["player_id"]] += 1
                team = qb["context"].get("team_id")
                opponent = qb["context"].get("opponent_team_id")
                if team:
                    partners = sum(row["context"].get("team_id") == team and row["slot"] in {"RB", "WR", "TE", "FLEX"}
                                   for row in lineup if row is not qb)
                    bringbacks = sum(row["context"].get("team_id") == opponent and row["slot"] in {"RB", "WR", "TE", "FLEX"}
                                     for row in lineup if row is not qb)
                    stack_counts[f"QB+{partners};bringback={bringbacks}"] += 1
            salaries = [_number(row["context"].get("salary")) for row in lineup]
            if all(value is not None for value in salaries):
                salary_left.append((50000 if contest_format == "classic" else 50000) - sum(salaries))
            owns = [row["ownership"] for row in lineup]
            if all(value is not None for value in owns):
                ownership_sums.append(sum(owns))
                low_owned_counts.append(sum(value < 10 for value in owns))
        result[f"top_{pct:g}_percent"] = {
            "threshold": threshold, "field_lineups_including_ties": len(top_entries),
            "canonical_lineups_summarized": resolved_count,
            "qb_frequency": _frequency(qb_counts, 15),
            "captain_frequency": _frequency(captain_counts, 15),
            "qb_stack_family_frequency": _frequency(stack_counts),
            "showdown_team_split_frequency": _frequency(split_counts),
            "qb_stack_status": "not_applicable_showdown" if contest_format == "showdown" else "available_if_team_context_complete",
            "player_exposure": _frequency(player_counts, 25),
            "game_exposure": _frequency(game_counts, 15),
            "average_salary_left": sum(salary_left) / len(salary_left) if salary_left else None,
            "average_total_actual_ownership": sum(ownership_sums) / len(ownership_sums) if ownership_sums else None,
            "average_low_owned_players_under_10pct": sum(low_owned_counts) / len(low_owned_counts) if low_owned_counts else None,
            "context_complete_lineups": len(salary_left), "ownership_complete_lineups": len(ownership_sums),
        }
    return {"status": "available", "groups": result,
            "identity_basis": "contest-specific resolved ownership observation plus roster slot"}


def summarize_construction_signatures(
    signatures: Iterable[tuple[tuple[str, bool], ...]],
    salary_context: Iterable[Mapping[str, Any]], observations: Iterable[Mapping[str, Any]],
    contest_id: str, contest_format: str,
) -> dict[str, Any]:
    """Use the same canonical roster basis for generated, selected, and entered groups."""
    lineups = list(signatures)
    context: dict[tuple[str, str], dict[str, Any]] = {}
    for row in salary_context:
        context[(str(row.get("player_id")), str(row.get("roster_position") or "").upper())] = dict(row)
    ownership = {(str(row.get("player_id")), str(row.get("roster_position") or "").upper()): _number(row.get("actual_ownership"))
                 for row in observations if str(row.get("contest_id")) == contest_id
                 and row.get("resolution_status") == "resolved"}
    players: Counter[str] = Counter()
    games: Counter[str] = Counter()
    qbs: Counter[str] = Counter()
    captains: Counter[str] = Counter()
    stacks: Counter[str] = Counter()
    splits: Counter[str] = Counter()
    salaries = []
    owns = []
    lows = []
    for signature in lineups:
        roster = []
        for player_id, captain in signature:
            slot = "CPT" if captain else "FLEX" if contest_format == "showdown" else ""
            meta = context.get((player_id, slot)) or next(
                (row for (pid, _), row in context.items() if pid == player_id), {})
            actual_ownership = ownership.get((player_id, slot))
            if actual_ownership is None:
                actual_ownership = next((value for (pid, _), value in ownership.items() if pid == player_id), None)
            roster.append((player_id, captain, meta, actual_ownership))
            players[player_id] += 1
        games.update({str(meta["game_id"]) for _, _, meta, _ in roster if meta.get("game_id")})
        captains.update(player_id for player_id, captain, _, _ in roster if captain)
        if contest_format == "showdown" and all(meta.get("team_id") for _, _, meta, _ in roster):
            team_counts = Counter(meta["team_id"] for _, _, meta, _ in roster)
            splits["-".join(str(count) for count in sorted(team_counts.values(), reverse=True))] += 1
        qb = next(((player_id, meta) for player_id, _, meta, _ in roster
                   if str(meta.get("roster_position") or "").upper() == "QB"), None)
        if qb:
            qbs[qb[0]] += 1
            team = qb[1].get("team_id")
            opponent = qb[1].get("opponent_team_id")
            if team:
                partner_count = sum(meta.get("team_id") == team and player_id != qb[0]
                                    and str(meta.get("roster_position") or "").upper() in {"RB", "WR", "TE"}
                                    for player_id, _, meta, _ in roster)
                bringback_count = sum(meta.get("team_id") == opponent and player_id != qb[0]
                                      and str(meta.get("roster_position") or "").upper() in {"RB", "WR", "TE"}
                                      for player_id, _, meta, _ in roster)
                stacks[f"QB+{partner_count};bringback={bringback_count}"] += 1
        salary_values = [_number(meta.get("salary")) for _, _, meta, _ in roster]
        if all(value is not None for value in salary_values):
            salaries.append(50000 - sum(salary_values))
        own_values = [value for _, _, _, value in roster]
        if all(value is not None for value in own_values):
            owns.append(sum(own_values))
            lows.append(sum(value < 10 for value in own_values))
    return {"lineups": len(lineups), "qb_frequency": _frequency(qbs, 15),
            "captain_frequency": _frequency(captains, 15),
            "qb_stack_family_frequency": _frequency(stacks),
            "showdown_team_split_frequency": _frequency(splits),
            "player_exposure": _frequency(players, 25), "game_exposure": _frequency(games, 15),
            "average_salary_left": sum(salaries) / len(salaries) if salaries else None,
            "average_total_actual_ownership": sum(owns) / len(owns) if owns else None,
            "average_low_owned_players_under_10pct": sum(lows) / len(lows) if lows else None,
            "context_complete_lineups": len(salaries), "ownership_complete_lineups": len(owns)}


def _ranks(values: list[float]) -> list[float]:
    ordered = sorted(range(len(values)), key=lambda index: values[index])
    result = [0.0] * len(values)
    start = 0
    while start < len(values):
        stop = start + 1
        while stop < len(values) and values[ordered[stop]] == values[ordered[start]]:
            stop += 1
        rank = (start + 1 + stop) / 2
        for index in ordered[start:stop]:
            result[index] = rank
        start = stop
    return result


def _pearson(x: list[float], y: list[float]) -> float | None:
    if len(x) < 3:
        return None
    mx, my = sum(x) / len(x), sum(y) / len(y)
    xx = sum((v - mx) ** 2 for v in x)
    yy = sum((v - my) ** 2 for v in y)
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / math.sqrt(xx * yy) if xx and yy else None


def metric_correlations(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    fields = ("mean", "p90", "objective_score", "ownership_sum", "leverage_sum",
              "correlation_adjustment", "context_adjustment")
    records = list(rows)
    output = {}
    for field in fields:
        pairs = [(_number(row["pregame"].get(field)), _number(row["postgame"].get("actual_points")))
                 for row in records]
        valid = [(x, y) for x, y in pairs if x is not None and y is not None]
        x = [a for a, _ in valid]
        y = [b for _, b in valid]
        output[field] = {"n": len(valid), "pearson": _pearson(x, y),
                         "spearman": _pearson(_ranks(x), _ranks(y)) if len(valid) >= 3 else None}
    return output


def correlation_samples(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Retain only numeric observations needed for exact cross-slate correlations."""
    fields = ("mean", "p90", "objective_score", "ownership_sum", "leverage_sum",
              "correlation_adjustment", "context_adjustment")
    return [{"pregame": {key: row["pregame"].get(key) for key in fields},
             "postgame": {"actual_points": row["postgame"].get("actual_points")}} for row in rows]


def _pregame(candidate: Mapping[str, Any], rank: int, run: Mapping[str, Any]) -> dict[str, Any]:
    components = _mapping(candidate.get("components"))
    return {
        "candidate_id": f"{run['optimizer_run_id']}:candidate:{rank}",
        "source_candidate_id": candidate.get("candidate_id"),
        "source_candidate_ordinal":candidate.get("source_candidate_ordinal"),
        "source_candidate_sha256":candidate.get("source_candidate_sha256"),
        "source_scenario_ids":candidate.get("source_scenario_ids"),
        "conditional_scenario_scores":candidate.get("source_scenario_scores"),
        "metric_basis": "frozen_baseline_player_moments; P90 is marginal sum, not joint upside" if candidate.get("analyst_adapter") else None,
        "candidate_ordinal": rank,
        "optimizer_run_id": str(run["optimizer_run_id"]), "generation_rank": candidate.get("generation_rank"),
        "selector_rank": candidate.get("selector_rank", candidate.get("rank")),
        "order_basis": "recorded_selector_rank" if candidate.get("rank") is not None or candidate.get("selector_rank") is not None else "saved_candidate_array_order_not_proven_generation_rank" if candidate.get("analyst_adapter") else "saved_generation_order",
        "mean": _number(candidate.get("mean")), "p90": _number(candidate.get("p90")),
        "objective_score": _number(candidate.get("objective_score") or candidate.get("single_entry_score") or candidate.get("selector")),
        "ownership_sum": _number(candidate.get("ownership_sum")),
        "leverage_sum": _number(candidate.get("leverage_sum") if candidate.get("leverage_sum") is not None
                                else _mapping(candidate.get("ownership_derived_terms")).get("leverage")),
        "context_adjustment": _number(candidate.get("context_score") or components.get("context")),
        "correlation_adjustment": _number(candidate.get("correlation_score") or components.get("correlation")),
        "objective_components": components or _mapping(candidate.get("objective_contributions")),
        "construction_family": candidate.get("game_script") or candidate.get("generation_template"),
        "qb_stack_family": _mapping(candidate.get("stack")).get("type"),
        "salary": _number(candidate.get("salary")),
        "data_cutoff_at": run.get("data_cutoff_at"),
        "projection_run_id": run.get("projection_run_id"),
        "ownership_run_id": _mapping(run.get("constraint_config_json")).get("ownership_run_id"),
        "correlation_profile": _mapping(run.get("constraint_config_json")).get("correlation_profile"),
        "strategy": run.get("strategy"),
    }


def evaluate_run(
    run: Mapping[str, Any], selected_lineups: Iterable[Mapping[str, Any]],
    entered_lineups: Iterable[Mapping[str, Any]], actuals: Mapping[str, float],
    benchmarks: Mapping[str, Mapping[str, Any]],
    contest_submissions: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    selected_lineups, entered_lineups = list(selected_lineups), list(entered_lineups)
    contest_submissions = list(contest_submissions) if contest_submissions is not None else entered_lineups
    fmt = str(run.get("contest_format") or "").lower()
    pool = extract_saved_pool(run.get("constraint_config_json"), fmt)
    output: dict[str, Any] = {"optimizer_run_id": str(run["optimizer_run_id"]),
                              "contest_format": fmt, "strategy": run.get("strategy"),
                              "candidate_pool": {k: v for k, v in pool.items() if k != "candidates"},
                              "chronological_validation": chronological_validation(run, pool)}
    workload = saved_workload_evidence(run.get("constraint_config_json"))
    output["workload_evidence"] = {"contract_id": saved_workload_contract(workload),
                                   "status": "saved" if workload else "unavailable_in_saved_run",
                                   "players": workload}
    if pool["status"] != "original_candidate_pool":
        output["status"] = "candidate_pool_unavailable"
        output["replay_status"] = "not_attempted_without_verified_point_in_time_reproducibility"
        return output
    selected = {tuple(row["signature"]): row for row in selected_lineups if row.get("signature")}
    entered = {tuple(row["signature"]): row for row in entered_lineups if row.get("signature")}
    runtime = _mapping(_mapping(run.get("constraint_config_json")).get("strategy_runtime"))
    policy = _mapping(runtime.get("showdown_portfolio_policy"))
    selection_report = _mapping(policy.get("candidate_selection"))
    omissions = _mapping(selection_report.get("omission_reasons"))
    selected_ranks = {int(value) for value in selection_report.get("selected_ranks") or []
                      if value is not None}
    first_rank_by_signature = {}
    selected_variant_signatures = set()
    for index, candidate in enumerate(pool["candidates"], 1):
        signature = candidate_signature(candidate, fmt)
        first_rank_by_signature.setdefault(signature, index)
        if index in selected_ranks:
            selected_variant_signatures.add(signature)
    candidates = []
    for index, candidate in enumerate(pool["candidates"], 1):
        signature = candidate_signature(candidate, fmt)
        assert signature is not None
        points, missing = score_signature(signature, actuals)
        pregame = _pregame(candidate, index, run)
        if workload:
            pregame["workload_evidence_player_ids"] = sorted({pid for pid, _ in signature if pid in workload})
            pregame["workload_evidence_missing_player_ids"] = sorted({pid for pid, _ in signature if pid not in workload})
        is_selected = (int(pregame["selector_rank"] or index) in selected_ranks
                       if selected_ranks else signature in selected)
        is_entered = signature in entered and (
            is_selected if signature in selected_variant_signatures
            else first_rank_by_signature[signature] == index
        )
        pregame["saved_lineups"] = [
            {"lineup_id": row.get("lineup_id"), "saved_lineup_number": row.get("lineup_number")}
            for row in selected_lineups if tuple(row.get("signature") or ()) == signature]
        pregame["portfolio_selected"] = is_selected
        pregame["selection_reason"] = (candidate.get("selection_reason") or
                                       omissions.get(str(pregame["selector_rank"])) or
                                       omissions.get(pregame["selector_rank"]))
        candidates.append({"signature": signature, "pregame": pregame,
                           "postgame": {"actual_points": points, "missing_player_ids": missing,
                                        "selected": is_selected, "entered": is_entered}})
    scored = [row for row in candidates if row["postgame"]["actual_points"] is not None]
    unique_scored_by_signature = {row["signature"]: row for row in scored}
    unique_scored = list(unique_scored_by_signature.values())
    unscored_count = pool["unique_roster_count"] - len(unique_scored)
    for row in scored:
        score = row["postgame"]["actual_points"]
        scored_rank = 1 + sum(other["postgame"]["actual_points"] > score + 0.005 for other in unique_scored)
        row["postgame"]["actual_rank"] = scored_rank if unscored_count == 0 else None
        row["postgame"]["actual_rank_among_scored"] = scored_rank
        row["postgame"]["actual_rank_bounds"] = [scored_rank, scored_rank + unscored_count]
        scored_percentile = 100 * sum(other["postgame"]["actual_points"] <= score + 0.005 for other in unique_scored) / len(unique_scored)
        row["postgame"]["actual_percentile"] = scored_percentile if unscored_count == 0 else None
        row["postgame"]["actual_percentile_among_scored"] = scored_percentile
        row["postgame"]["difference_from_mean"] = (round(score - row["pregame"]["mean"], 2)
                                                       if row["pregame"]["mean"] is not None else None)
    scores = [row["postgame"]["actual_points"] for row in unique_scored]
    selected_scored = [row for row in scored if row["postgame"]["selected"]]
    entered_scored = [row for row in scored if row["postgame"]["entered"]]
    best = max(scores, default=None)
    best_selected = max((row["postgame"]["actual_points"] for row in selected_scored), default=None)
    best_entered = max((row["postgame"]["actual_points"] for row in entered_scored), default=None)
    best_observed = max(scored, key=lambda row: row["postgame"]["actual_points"], default=None)
    top_selected = min((row for row in candidates if row["postgame"]["selected"]),
                       key=lambda row: row["pregame"]["selector_rank"] or row["pregame"]["candidate_ordinal"], default=None)
    rank_comparison = None
    if best_observed and top_selected:
        contender = best_observed["pregame"]
        reference = top_selected["pregame"]
        contender_parts = contender["objective_components"]
        reference_parts = reference["objective_components"]
        rank_comparison = {
            "best_scoreable_candidate_rank": contender["selector_rank"],
            "reference_selected_rank": reference["selector_rank"],
            "objective_score_delta": round(contender["objective_score"] - reference["objective_score"], 6)
            if contender["objective_score"] is not None and reference["objective_score"] is not None else None,
            "mean_delta": round(contender["mean"] - reference["mean"], 4)
            if contender["mean"] is not None and reference["mean"] is not None else None,
            "p90_sum_delta": round(contender["p90"] - reference["p90"], 4)
            if contender["p90"] is not None and reference["p90"] is not None else None,
            "objective_component_deltas": {
                key: round(float(contender_parts.get(key) or 0) - float(reference_parts.get(key) or 0), 6)
                for key in sorted(set(contender_parts) | set(reference_parts))
            },
        }
    selected_count = len(selected)
    entered_count = len(entered)
    complete = len(unique_scored) == pool["unique_roster_count"]
    ordered = sorted(candidates, key=lambda row: (row["pregame"]["selector_rank"] or row["pregame"]["candidate_ordinal"], row["pregame"]["candidate_id"]))
    top_k = {str(k): {"best_scored_actual": max((row["postgame"]["actual_points"] for row in ordered[:k]
                                                   if row["postgame"]["actual_points"] is not None), default=None),
                       "scored": sum(row["postgame"]["actual_points"] is not None for row in ordered[:k]),
                       "size": min(k, len(ordered))} for k in (1, 3, 5, 10, 20)}
    field = {}
    for contest_id, benchmark in benchmarks.items():
        if benchmark.get("status") != "available":
            field[contest_id] = {"status": "unavailable", "reason": benchmark.get("reason")}
            continue
        contest_entered = [row for row in contest_submissions if str(row.get("contest_id")) == str(contest_id)]
        contest_entered_scores = [_number(row.get("entry_points")) for row in contest_entered]
        contest_best_entered = max((v for v in contest_entered_scores if v is not None), default=None)
        contest_entered_signatures = {tuple(row["signature"]) for row in contest_entered if row.get("signature")}
        contest_entered_scored = [row for row in unique_scored if row["signature"] in contest_entered_signatures]
        thresholds = {**benchmark["thresholds"], "cash": benchmark["cash_line"], "winner": benchmark["winner"]}
        for row in scored:
            points = row["postgame"]["actual_points"]
            row["postgame"].setdefault("field_benchmarks", {})[contest_id] = {
                "field_rank": field_rank(points, benchmark["field_scores_desc"]),
                "reached": {key: points >= threshold - .005 if threshold is not None else None
                            for key, threshold in thresholds.items()},
            }
        attainment = {}
        for key, threshold in thresholds.items():
            attainment[key] = {"generated_scored": sum(row["postgame"]["actual_points"] >= threshold - 0.005 for row in unique_scored) if threshold is not None else None,
                                "generated_variant_scored": sum(row["postgame"]["actual_points"] >= threshold - 0.005 for row in scored) if threshold is not None else None,
                                "selected_scored": sum(row["postgame"]["actual_points"] >= threshold - 0.005 for row in selected_scored) if threshold is not None else None,
                                "entered_scored": sum(row["postgame"]["actual_points"] >= threshold - 0.005 for row in contest_entered_scored) if threshold is not None else None}
        field[contest_id] = {"status": "available", "winner": benchmark["winner"],
                             "median": benchmark["median"], "thresholds": benchmark["thresholds"],
                             "cash_line": benchmark["cash_line"], "attainment": attainment,
                             "generation_ceiling_gap": round(benchmark["winner"] - best, 2) if best is not None else None,
                             "top_1_gap": round(benchmark["thresholds"]["top_1_percent"] - best, 2) if best is not None else None,
                             "best_generated_field_rank": field_rank(best, benchmark["field_scores_desc"]) if best is not None else None,
                             "best_selected_field_rank": field_rank(best_selected, benchmark["field_scores_desc"]) if best_selected is not None else None,
                             "best_entered_field_rank": field_rank(contest_best_entered, benchmark["field_scores_desc"]) if contest_best_entered is not None else None,
                             "best_entered_actual": contest_best_entered,
                             "entered_count": len(contest_entered),
                             "selected_vs_entered_hindsight_gap": round(best_selected - contest_best_entered, 2) if best_selected is not None and contest_best_entered is not None else None}
    output.update({"status": "complete" if complete else "incomplete_player_actuals",
                   "generated_count": len(candidates), "unique_roster_count": pool["unique_roster_count"],
                   "scored_count": len(scored), "unique_scored_roster_count": len(unique_scored),
                   "selected_count": selected_count, "selected_matched_count": sum(row["postgame"]["selected"] for row in candidates),
                   "selected_scored_count": len(selected_scored),
                   "entered_count": entered_count, "entered_matched_count": sum(row["postgame"]["entered"] for row in candidates),
                   "entered_scored_count": len(entered_scored),
                   "best_generated_actual": best, "median_generated_actual": median(scores) if scores else None,
                   "p90_generated_actual": _quantile(scores, .9), "p95_generated_actual": _quantile(scores, .95),
                   "p99_generated_actual": _quantile(scores, .99) if len(scores) >= 100 else None,
                   "best_selected_actual": best_selected, "best_entered_actual": best_entered,
                   "selection_regret_observed": round(best - best_selected, 2) if best is not None and best_selected is not None else None,
                   "entry_regret_observed": round(best - best_entered, 2) if best is not None and best_entered is not None else None,
                   "selection_efficiency": {"best_ratio": best_selected / best if best and best_selected is not None else None,
                                            "average_selected": sum(row["postgame"]["actual_points"] for row in selected_scored) / len(selected_scored) if selected_scored else None,
                                            "average_generated": sum(scores) / len(scores) if scores else None,
                                            "median_selected": median(row["postgame"]["actual_points"] for row in selected_scored) if selected_scored else None,
                                            "median_generated": median(scores) if scores else None},
                   "top_k_capture": top_k, "correlations": metric_correlations(candidates),
                   "best_candidate_pregame_rank_comparison": rank_comparison,
                   "correlations_scope": "all_saved_variants" if complete else "scoreable_saved_variants_only",
                   "field": field, "candidates": candidates,
                   "missing_actual_player_ids": sorted({pid for row in candidates for pid in row["postgame"]["missing_player_ids"]}),
                   "diagnostic": _diagnose(best, best_selected, best_entered, complete, field, selected_count, entered_count)})
    return output


def _diagnose(best: float | None, selected: float | None, entered: float | None,
              complete: bool, field: Mapping[str, Any], selected_count: int, entered_count: int) -> list[dict[str, Any]]:
    findings = []
    for contest_id, row in field.items():
        if row.get("status") != "available" or best is None:
            continue
        top1 = row["thresholds"]["top_1_percent"]
        if complete and best < top1:
            findings.append({"stage": "CANDIDATE_GENERATION", "contest_id": contest_id,
                             "evidence": f"Best generated {best:.2f}; top 1% requires {top1:.2f}."})
        if selected_count and selected is not None and best > selected + .005:
            findings.append({"stage": "CANDIDATE_SELECTION", "contest_id": contest_id,
                             "evidence": f"Best scoreable generated {best:.2f}; best selected {selected:.2f}; observed regret {best-selected:.2f}."})
        contest_entered = row.get("best_entered_actual")
        if contest_entered is not None and selected is not None and selected > contest_entered + .005:
            findings.append({"stage": "HINDSIGHT_GAP", "contest_id": contest_id,
                             "evidence": f"Best saved selection {selected:.2f}; this contest's best submission {contest_entered:.2f}. No execution error is implied."})
    if not complete:
        findings.append({"stage": "EVIDENCE_GAP", "evidence": "Unscored candidates prevent an exact generation ceiling and final actual ranks."})
    return findings


def build_optimizer_effectiveness(
    slate_report: Mapping[str, Any], evidence: Mapping[str, Any],
    *, run_loader: Callable[[str], Mapping[str, Any]] | None = None,
    detail_sink: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    diagnostic_run_ids: Iterable[str] = (),
) -> dict[str, Any]:
    """Evaluate runs attached through canonical saved-lineup matching."""
    contests = {str(row["contest_id"]): row for row in evidence.get("contests", [])}
    by_contest: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in evidence.get("field_entries", []):
        by_contest[str(row["contest_id"])].append(row)
    tiers: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in evidence.get("payout_tiers", []):
        tiers[str(row["contest_id"])].append(row)
    benchmarks = {cid: field_benchmarks(contest, by_contest[cid], tiers[cid])
                  for cid, contest in contests.items()}
    saved: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    runs: dict[str, dict[str, Any]] = {
        str(row["optimizer_run_id"]): dict(row) for row in evidence.get("optimizer_runs", [])
    }
    for row in evidence.get("lineup_players", []):
        run_id = str(row.get("optimizer_run_id") or "")
        if not run_id:
            continue
        saved[str(row["lineup_id"])].append(row)
        runs.setdefault(run_id, {key: row.get(key) for key in (
            "optimizer_run_id", "contest_format", "strategy", "constraint_config_json",
            "data_cutoff_at", "projection_run_id", "optimizer_created_at",
        )})
    attached = set(slate_report.get("run_ids", {}).get("optimizer_run_ids", []))
    corresponding = {str(match["optimizer_run_id"]) for entry in slate_report.get("entries", [])
        for match in _mapping(entry.get("submission_evidence")).get("saved_lineup_matches", [])
        if match.get("optimizer_run_id") and str(match["optimizer_run_id"]) in runs}
    requested = set(diagnostic_run_ids)
    if requested - set(runs):
        raise ValueError("Diagnostic optimizer runs must be completed runs in the requested slate")
    saved_pool_runs = set() if run_loader else {run_id for run_id, run in runs.items()
                       if extract_saved_pool(run.get("constraint_config_json"),
                                             str(run.get("contest_format") or "").lower())["status"]
                       == "original_candidate_pool"}
    evaluated_run_ids = attached | corresponding | saved_pool_runs | requested
    selected: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for lineup_id, players in saved.items():
        run_id = str(players[0]["optimizer_run_id"])
        if run_id not in evaluated_run_ids:
            continue
        signature = tuple(sorted((str(row["player_id"]),
                                  str(row.get("roster_position") or "").upper() == "CPT")
                                 for row in players))
        selected[run_id].append({"lineup_id": lineup_id, "signature": signature,
                                 "lineup_number": players[0].get("lineup_number")})
    entered: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in slate_report.get("entries", []):
        run_id = str(entry.get("optimizer_run_id") or "")
        possible = {str(m["optimizer_run_id"]) for m in _mapping(entry.get("submission_evidence")).get("saved_lineup_matches", []) if m.get("optimizer_run_id")}
        if not entry.get("identity_complete"):
            continue
        matched = ({run_id} if run_id in attached else possible) & evaluated_run_ids
        if not matched:continue
        signature = tuple(sorted((str(row["player_id"]),
                                  str(row.get("roster_position") or "").upper() == "CPT")
                                 for row in entry["players"]))
        for matched_run_id in matched:
            entered[matched_run_id].append({"entry_id":entry["entry_id"],"contest_id":entry["contest_id"],
                "entry_points":entry.get("entry_points"),"signature":signature,
                "match_basis":"unique_roster_correspondence" if run_id in attached else "ambiguous_roster_correspondence",
                "origin_proven":False})
    execution = execution_diagnostics(slate_report.get("entries", []), [*evidence.get("assignments", []), *evidence.get("recommendation_assignments", [])], saved)
    output = []
    for run_id in sorted(evaluated_run_ids, key=lambda value: (value not in attached, value)):
        run = runs.get(run_id)
        if run is None:
            output.append({"optimizer_run_id": run_id, "status": "saved_run_unavailable"})
            continue
        if run_loader:
            run = {**run, **run_loader(run_id)}
        fmt = str(run.get("contest_format") or "").lower()
        actuals = actual_points_by_player(evidence.get("observations", []), fmt)
        evaluated = evaluate_run(run, selected[run_id], entered[run_id], actuals, benchmarks,
            contest_submissions=[{**entry, "signature": tuple(sorted((str(p["player_id"]), p.get("roster_position")=="CPT")
                for p in entry.get("players", []))) if entry.get("identity_complete") else None}
                for entry in slate_report.get("entries", [])])
        evaluated["execution_diagnostics"] = [row for row in execution if row.get("optimizer_run_id") == run_id]
        evaluated.setdefault("diagnostic", []).extend(row for row in evaluated["execution_diagnostics"] if row["status"] == "mismatch")
        evaluated["entry_correspondence"] = [{k:row[k] for k in ("entry_id","contest_id","match_basis","origin_proven") if k in row} for row in entered[run_id]]
        evaluated["run_scope"] = ("entry_linked" if run_id in attached else
                                  "entry_correspondence" if run_id in corresponding else
                                  "explicit_diagnostic" if run_id in requested else "other_completed_saved_pool")
        if run_loader:
            evaluated["inclusion_reason"] = ("canonical_entered_lineup_match" if run_id in attached
                                              else "ambiguous_canonical_roster_correspondence" if run_id in corresponding else "explicit_diagnostic_request")
            evaluated["configuration_hash"] = run.get("configuration_hash")
        cutoff = run.get("data_cutoff_at")
        if isinstance(cutoff, str):
            try:
                cutoff = datetime.fromisoformat(cutoff)
            except ValueError:
                cutoff = None
        safe_salary = [row for row in evidence.get("salary_context", [])
                       if cutoff is not None and row.get("as_of") is not None
                       and row["as_of"] <= cutoff]
        evaluated["top_field_constructions"] = {
            contest_id: top_field_constructions(
                contest_id, by_contest[contest_id], evidence.get("observations", []),
                safe_salary, benchmark, fmt,
            ) for contest_id, benchmark in benchmarks.items()
        }
        candidate_signatures = sorted({tuple(row["signature"]) for row in evaluated.get("candidates", [])})
        evaluated["construction_comparison"] = {
            contest_id: {
                "generated": summarize_construction_signatures(
                    candidate_signatures, safe_salary, evidence.get("observations", []), contest_id, fmt
                ) if candidate_signatures else {"status": "candidate_pool_unavailable"},
                "selected": summarize_construction_signatures(
                    [row["signature"] for row in selected[run_id]], safe_salary,
                    evidence.get("observations", []), contest_id, fmt,
                ),
                "entered": summarize_construction_signatures(
                    [row["signature"] for row in entered[run_id] if row["contest_id"] == contest_id],
                    safe_salary, evidence.get("observations", []), contest_id, fmt,
                ),
            } for contest_id in benchmarks
        }
        if evaluated["status"] == "candidate_pool_unavailable":
            selected_scores = []
            for row in selected[run_id]:
                score, missing = score_signature(row["signature"], actuals)
                selected_scores.append({"lineup_id": row["lineup_id"], "actual_points": score,
                                        "missing_player_ids": missing})
            evaluated["selected_lineups"] = selected_scores
            evaluated["best_selected_actual"] = max((row["actual_points"] for row in selected_scores
                                                       if row["actual_points"] is not None), default=None)
            evaluated["best_entered_actual"] = max((_number(row["entry_points"]) for row in entered[run_id]
                                                      if _number(row["entry_points"]) is not None), default=None)
        if detail_sink:
            detail = detail_sink(evaluated)
            candidates = evaluated.pop("candidates", [])
            preview = [row for row in candidates
                       if row["postgame"].get("selected") or row["postgame"].get("entered")][:17]
            for group in (None, "selected", "entered"):
                best = max((row for row in candidates if row["postgame"].get("actual_points") is not None
                            and (group is None or row["postgame"].get(group))),
                           key=lambda row: row["postgame"]["actual_points"], default=None)
                if best is not None and best not in preview:
                    preview.append(best)
            evaluated["candidate_preview"] = preview
            evaluated["candidate_detail"] = dict(detail)
            del candidates
            del preview, best
        output.append(evaluated)
        # Never carry a decoded full configuration into the next run load.
        del run
    # Exclude the full field score arrays from the compact persisted report.
    public_benchmarks = {cid: {key: value for key, value in row.items() if key != "field_scores_desc"}
                         for cid, row in benchmarks.items()}
    entered_points = [_number(row.get("entry_points")) for row in slate_report.get("entries", [])]
    entered_field = []
    for entry in slate_report.get("entries", []):
        contest_id = str(entry["contest_id"])
        benchmark = benchmarks.get(contest_id, {})
        points = _number(entry.get("entry_points"))
        if benchmark.get("status") != "available" or points is None:
            entered_field.append({"contest_id": contest_id, "entry_id": entry["entry_id"],
                                  "status": "unavailable", "reason": benchmark.get("reason") or "entry_points_unavailable"})
            continue
        entered_field.append({"contest_id": contest_id, "entry_id": entry["entry_id"],
                              "status": "available", "entry_points": points,
                              "field_rank": field_rank(points, benchmark["field_scores_desc"]),
                              "points_from_winner": round(points - benchmark["winner"], 2),
                              "points_from_top_1_percent": round(points - benchmark["thresholds"]["top_1_percent"], 2),
                              "points_from_top_5_percent": round(points - benchmark["thresholds"]["top_5_percent"], 2),
                              "points_from_top_10_percent": round(points - benchmark["thresholds"]["top_10_percent"], 2),
                              "points_from_cash": round(points - benchmark["cash_line"], 2)
                              if benchmark["cash_line"] is not None else None})
    return {"contract_id": "optimizer_effectiveness_v2" if run_loader else "optimizer_effectiveness_v1", "runs": output,
            **({"inclusion_policy": {
                "policy_id": "entry_correspondence_and_explicit_diagnostics_v2",
                "completed_run_count": len(runs), "included_run_count": len(evaluated_run_ids),
                "excluded_run_count": len(set(runs) - evaluated_run_ids),
                "excluded_runs": [{"optimizer_run_id": run_id, "reason": "unrelated_completed_run",
                                   "configuration_hash": runs[run_id].get("configuration_hash")}
                                  for run_id in sorted(set(runs) - evaluated_run_ids)],
                "historical_policy": "entry_linked_complete_predecision_correlation_samples_only",
            }} if run_loader else {}),
            "unavailable_completed_run_ids": sorted(set(runs) - evaluated_run_ids),
            "field_benchmarks": public_benchmarks,
            "entered_field_comparisons": entered_field,
            "execution_diagnostics": execution,
            "best_entered_slate_actual": max((x for x in entered_points if x is not None), default=None),
            "unmatched_entered_entries": [row["entry_id"] for row in slate_report.get("entries", [])
                                           if not row.get("optimizer_run_id")],
            "scope_note": "Run metrics use canonical matched entries. Slate entry totals include unmatched submissions."
        }


def execution_diagnostics(entries, assignments, saved):
    """A score difference is never an execution error; require entry-specific intent."""
    by_entry = defaultdict(list)
    for assignment in assignments:
        by_entry[(str(assignment["contest_id"]), str(assignment["entry_id"]))].append(assignment)
    output = []
    for entry in entries:
        key = (str(entry["contest_id"]), str(entry["entry_id"]))
        intent = by_entry.get(key, [])
        row = {"contest_id": key[0], "entry_id": key[1], "status": "intended_entry_unavailable"}
        if len(intent) == 1:
            assignment = intent[0]
            players = assignment.get("intended_players") or saved.get(str(assignment.get("lineup_id")), [])
            expected = tuple(sorted((str(p["player_id"]), p.get("roster_position") == "CPT") for p in players))
            actual = tuple(sorted((str(p["player_id"]), p.get("roster_position") == "CPT") for p in entry.get("players", [])))
            row.update(optimizer_run_id=assignment.get("optimizer_run_id"), intended_lineup_id=assignment.get("lineup_id"))
            if players and entry.get("identity_complete"):
                row["status"] = "matched" if expected == actual else "mismatch"
                if expected != actual:
                    row.update(stage="EXECUTION", evidence="Recorded intended entry roster differs from the submitted roster.")
            else:
                row["status"] = "identity_or_intended_roster_unavailable"
        elif intent:
            row["status"] = "conflicting_intended_entries"
        output.append(row)
    return output
