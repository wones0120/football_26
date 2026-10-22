"""Auditable post-slate learning reports from normalized contest evidence."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
import hashlib
import json
import math
import re
import uuid
import logging
import resource
import sys
from time import monotonic
from typing import Any, Callable, Iterable, Mapping

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from Database.config import get_connection_string
from ..schemas import NflReadPySeasonRequest
from ..services.ingest import IngestService
from ..services.source_capture import (
    DEFAULT_NFLREADPY_LICENSE, SourceCaptureService, _ingest_run_id,
    capture_nflreadpy_datasets,
)

from .target_schema import validate_target_schema
from .optimizer_effectiveness import build_optimizer_effectiveness, correlation_samples, metric_correlations
from .entry_submission_evidence import submission_evidence


LEARNING_REPORT_CONTRACT = "slate_learning_report_v1"
LEARNING_REPORT_BUILDER_VERSION = "2026-10-18.analyst-candidates.1"
WEEKLY_LEARNING_REPORT_CONTRACT = "weekly_learning_report_v1"
LEARNING_EFFECT_TOLERANCE = 0.25
OUTCOME_TAGS = frozenset({
    "NORMAL_VARIANCE", "IN_GAME_INJURY", "EJECTION", "BENCHED",
    "WEATHER_EVENT", "ROLE_CHANGED_IN_GAME", "OVERTIME",
    "OTHER_DISRUPTION", "UNKNOWN",
})
_LINEUP_PATTERN = re.compile(
    r"\b(CPT|DST|FLEX|QB|RB|WR|TE)\s+(.+?)(?=\s+(?:CPT|DST|FLEX|QB|RB|WR|TE)\s+|$)"
)


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _canonical_hash(payload: Any) -> str:
    digest = hashlib.sha256()
    for chunk in json.JSONEncoder(sort_keys=True, separators=(",", ":"), default=str).iterencode(_json_value(payload)):
        digest.update(chunk.encode())
    return digest.hexdigest()


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _normalized_name(value: Any) -> str:
    return " ".join(
        re.sub(r"[^a-z0-9 ]", " ", str(value or "").casefold()).split()
    )


def _parse_lineup(value: Any) -> list[dict[str, str]]:
    return [
        {"roster_position": slot, "player_display_name": name.strip()}
        for slot, name in _LINEUP_PATTERN.findall(str(value or "").strip())
    ]


def _signature(players: Iterable[Mapping[str, Any]]) -> tuple[tuple[str, bool], ...]:
    return tuple(
        sorted(
            (
                str(player["player_id"]),
                str(player.get("roster_position") or "").upper() == "CPT",
            )
            for player in players
        )
    )


def _mean(values: Iterable[float | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return sum(present) / len(present) if present else None


def _json_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _lineup_structure_family(script: Mapping[str, Any], environment: Mapping[str, Any]) -> dict[str, Any]:
    """Translate legacy construction labels without inferring the game environment."""
    kind = str(script.get("kind") or "").lower()
    team = str(script.get("team") or "").upper()
    if kind == "shootout":
        family_id, label = "two_sided_pass_stack", "Two-sided pass stack"
    elif kind == "pass_led":
        spread = _number(_json_mapping(environment.get("team_spreads")).get(team))
        side = "favorite" if spread is not None and spread < 0 else "underdog" if spread is not None and spread > 0 else "team"
        family_id, label = f"{side}_onslaught", f"{team} {side} onslaught"
    elif kind == "run_control":
        family_id, label = "run_control", f"{team} run-control"
    elif kind == "contrarian":
        family_id, label = "contrarian_construction", f"{team} contrarian construction"
    else:
        family_id, label = "unknown", "Unknown structure"
    return {
        "family_id": family_id, "label": label, "team": team or None,
        "basis": "selected_lineup_construction", "legacy_script_id": script.get("script_id"),
        "reason_codes": script.get("reason_codes") or [],
    }


def _game_environment(rows: list[Mapping[str, Any]], cutoff: Any) -> dict[str, Any]:
    """Report only market facts carried in saved, point-in-time-safe player rows."""
    totals: set[float] = set()
    spreads: dict[str, float] = {}
    implied: dict[str, float] = {}
    for saved in rows:
        player = _json_mapping(saved.get("player_json"))
        if player.get("market_context_point_in_time_safe") is not True:
            continue
        team = str(player.get("player_team") or "").upper()
        if (total := _number(player.get("game_total_line"))) is not None:
            totals.add(total)
        if team and (spread := _number(player.get("team_spread_line"))) is not None:
            spreads[team] = spread
        if team and (team_total := _number(player.get("team_implied_total"))) is not None:
            implied[team] = team_total
    return {
        "status": "available" if totals or spreads or implied else "unavailable",
        "basis": "saved_point_in_time_market_inputs",
        "data_cutoff_at": cutoff,
        "game_totals": sorted(totals),
        "team_spreads": dict(sorted(spreads.items())),
        "team_implied_totals": dict(sorted(implied.items())),
        "pace_expectations": None,
        "pass_expectations": None,
    }


def _projection_metrics(players: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    errors = [
        _number(row.get("projection_residual"))
        for row in players
    ]
    present = [value for value in errors if value is not None]
    return {
        "observations": len(present),
        "mae": _mean(abs(value) for value in present),
        "rmse": math.sqrt(_mean(value * value for value in present)) if present else None,
    }


def _outcome_counts(players: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    projected = [row for row in players if _number(row.get("projection_residual")) is not None]
    tags = Counter(str(row.get("outcome_tag") or "UNKNOWN") for row in projected)
    eligible = sum(row.get("training_eligible_residual") is True for row in projected)
    return {
        "by_tag": {tag: tags[tag] for tag in sorted(OUTCOME_TAGS)},
        "training_eligible": eligible,
        "training_ineligible": len(projected) - eligible,
    }


def _score_control(
    control: Mapping[str, Any], selected: list[Mapping[str, Any]],
    actuals: Mapping[tuple[str, str], Mapping[str, Any]],
) -> dict[str, Any]:
    rows = control.get("control_lineup") or []
    if not isinstance(rows, list) or not rows:
        return {"status": "missing_control_lineup", "actual_selected_minus_control": None}
    def score(players: Iterable[Mapping[str, Any]]) -> tuple[float | None, list[str], list[dict[str, Any]]]:
        values, absent, details = [], [], []
        for player in players:
            player_id = str(player.get("player_id") or "")
            slot = "CPT" if str(player.get("roster_position") or "").upper() == "CPT" else "FLEX"
            evidence = actuals.get((player_id, slot), {})
            value = _number(evidence.get("actual_points"))
            details.append({"player_id": player_id, "roster_position": slot,
                            "actual_points": value, "observation_id": evidence.get("observation_id")})
            if value is None:
                absent.append(player_id)
            else:
                values.append(value)
        return (sum(values) if not absent else None), absent, details
    selected_actual, selected_missing, selected_players = score(selected)
    control_actual, control_missing, control_players = score(rows)
    scored = _json_mapping(control.get("scored_metrics"))
    alternative = _json_mapping(control.get("control_metrics"))
    return {
        "status": "complete" if not selected_missing and not control_missing else "missing_player_actuals",
        "selected_projected_mean": _number(scored.get("mean")),
        "control_projected_mean": _number(alternative.get("mean")),
        "selected_projected_ceiling_proxy": _number(scored.get("individual_ceiling_sum")),
        "control_projected_ceiling_proxy": _number(alternative.get("individual_ceiling_sum")),
        "selected_projected_ownership": _number(scored.get("ownership_sum")),
        "control_projected_ownership": _number(alternative.get("ownership_sum")),
        "selected_actual_score": selected_actual,
        "control_actual_score": control_actual,
        "selected_players": selected_players,
        "control_players": control_players,
        "actual_selected_minus_control": (
            selected_actual - control_actual
            if selected_actual is not None and control_actual is not None else None
        ),
        "selected_only": control.get("selected_only") or [],
        "control_only": control.get("control_only") or [],
        "missing_selected_player_ids": selected_missing,
        "missing_control_player_ids": control_missing,
    }


def _compare_choice(
    *, actual: float | None, selected: float | None, comparator: float | None
) -> dict[str, Any]:
    if actual is None or selected is None or comparator is None:
        return {
            "outcome_effect": "unscored",
            "selected_abs_error": None,
            "comparator_abs_error": None,
            "error_delta": None,
        }
    selected_error = abs(actual - selected)
    comparator_error = abs(actual - comparator)
    delta = selected_error - comparator_error
    effect = (
        "helped"
        if delta < -LEARNING_EFFECT_TOLERANCE
        else "hurt"
        if delta > LEARNING_EFFECT_TOLERANCE
        else "no_measurable_effect"
    )
    return {
        "outcome_effect": effect,
        "selected_abs_error": round(selected_error, 4),
        "comparator_abs_error": round(comparator_error, 4),
        "error_delta": round(delta, 4),
    }


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _relevant_belief(
    belief: Mapping[str, Any], *, season: int, week: int, slate: str
) -> bool:
    if belief.get("season") not in {None, season}:
        return False
    if belief.get("week") not in {None, week}:
        return False
    belief_slate = str(belief.get("slate") or "").upper()
    return not belief_slate or belief_slate == slate.upper()


def build_slate_learning_report(
    *,
    season: int,
    week: int,
    slate: str,
    entry_user: str,
    evidence: Mapping[str, list[Mapping[str, Any]]],
    generated_at: datetime | None = None,
    run_loader: Callable[[str], Mapping[str, Any]] | None = None,
    detail_sink: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    diagnostic_run_ids: Iterable[str] = (),
) -> dict[str, Any]:
    """Build one report without inventing missing identity or lineage evidence."""
    generated = generated_at or datetime.now(UTC)
    contests = [dict(row) for row in evidence.get("contests", [])]
    entries = [dict(row) for row in evidence.get("entries", [])]
    observations = [dict(row) for row in evidence.get("observations", [])]
    lineup_players = [dict(row) for row in evidence.get("lineup_players", [])]
    optimizer_runs_by_id = {
        str(row["optimizer_run_id"]): row for row in evidence.get("optimizer_runs", [])
    }
    assignments = [dict(row) for row in evidence.get("assignments", [])]
    portfolios = [dict(row) for row in evidence.get("portfolios", [])]
    exports = [dict(row) for row in evidence.get("exports", [])]
    rule_applications = [dict(row) for row in evidence.get("rule_applications", [])]
    beliefs = [
        dict(row)
        for row in evidence.get("beliefs", [])
        if _relevant_belief(row, season=season, week=week, slate=slate)
    ]
    belief_impacts = [dict(row) for row in evidence.get("belief_impacts", [])]
    agent_questions = [dict(row) for row in evidence.get("agent_questions", [])]
    outcome_events = {
        str(row.get("player_id")): dict(row)
        for row in evidence.get("outcome_events", []) if row.get("player_id")
    }

    contests_by_id = {str(row["contest_id"]): row for row in contests}
    observations_by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in observations:
        observations_by_key[
            (
                str(row.get("contest_id") or ""),
                _normalized_name(row.get("player_display_name")),
                str(row.get("roster_position") or "").upper(),
            )
        ].append(row)

    saved_by_lineup: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in lineup_players:
        saved_by_lineup[str(row["lineup_id"])].append(row)
    for rows in saved_by_lineup.values():
        rows.sort(key=lambda row: int(row.get("slot_index") or 0))

    assigned = {
        (str(row["contest_id"]), str(row["entry_id"])): row for row in assignments
    }
    portfolio_by_id = {str(row["portfolio_id"]): row for row in portfolios}
    exports_by_portfolio: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in exports:
        exports_by_portfolio[str(row["portfolio_id"])].append(row)

    signature_matches: dict[tuple[tuple[str, bool], ...], list[str]] = defaultdict(list)
    for lineup_id, rows in saved_by_lineup.items():
        signature_matches[_signature(rows)].append(lineup_id)

    applications_by_run_player: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rule_applications:
        applications_by_run_player[
            (str(row.get("rule_run_id") or ""), str(row.get("player_id") or ""))
        ].append(row)

    missing: set[str] = set()
    entry_reports: list[dict[str, Any]] = []
    actual_lineup_counts: Counter[tuple[tuple[str, bool], ...]] = Counter()
    captain_counts: Counter[str] = Counter()
    projection_errors: list[float] = []
    squared_errors: list[float] = []
    unique_projection_players: dict[tuple[str, str, float], dict[str, Any]] = {}
    run_ids: dict[str, set[str]] = defaultdict(set)

    for entry in entries:
        contest_id = str(entry["contest_id"])
        contest = contests_by_id.get(contest_id, {})
        resolved_players: list[dict[str, Any]] = []
        unresolved_players: list[dict[str, Any]] = []
        for parsed in _parse_lineup(entry.get("lineup_text")):
            slot = parsed["roster_position"]
            candidate_slots = (
                {slot}
                if str(contest.get("contest_format") or "").lower() == "showdown"
                else ({"RB", "WR", "TE"} if slot == "FLEX" else {slot})
            )
            candidates = []
            for candidate_slot in candidate_slots:
                candidates.extend(
                    observations_by_key.get(
                        (
                            contest_id,
                            _normalized_name(parsed["player_display_name"]),
                            candidate_slot,
                        ),
                        [],
                    )
                )
            resolved_ids = {
                str(row["player_id"])
                for row in candidates
                if row.get("resolution_status") == "resolved" and row.get("player_id")
            }
            points = {
                _number(row.get("actual_points"))
                for row in candidates
                if row.get("resolution_status") == "resolved"
                and row.get("actual_points") is not None
            }
            points.discard(None)
            if len(resolved_ids) != 1 or len(points) != 1:
                unresolved_players.append(
                    {
                        **parsed,
                        "reason": "identity_or_actual_points_not_uniquely_resolved",
                    }
                )
                continue
            identity = next(iter(resolved_ids))
            actual = next(iter(points))
            source_row = next(
                row
                for row in candidates
                if str(row.get("player_id") or "") == identity
                and _number(row.get("actual_points")) == actual
            )
            resolved_players.append(
                {
                    **parsed,
                    "player_id": identity,
                    "actual_points": actual,
                    "actual_ownership": _number(source_row.get("actual_ownership")),
                }
            )

        parsed_count = len(_parse_lineup(entry.get("lineup_text")))
        identity_complete = parsed_count > 0 and len(resolved_players) == parsed_count
        if not identity_complete:
            missing.add(f"entry:{contest_id}:{entry['entry_id']}:canonical_lineup")

        match_basis = "unavailable"
        matched_lineup_id: str | None = None
        candidates = sorted(signature_matches.get(_signature(resolved_players), [])) if identity_complete else []
        saved_matches = [{
            "lineup_id": lineup_id,
            "optimizer_run_id": saved_by_lineup[lineup_id][0].get("optimizer_run_id"),
            "created_at": saved_by_lineup[lineup_id][0].get("optimizer_created_at"),
            "roster_equal": True,
            "exact_slot_equal": [(p["player_id"], p["roster_position"]) for p in resolved_players]
                == [(p["player_id"], p["roster_position"]) for p in saved_by_lineup[lineup_id]],
        } for lineup_id in candidates]
        assignment = assigned.get((contest_id, str(entry["entry_id"])))
        if not assignment:
            missing.add(f"entry:{contest_id}:{entry['entry_id']}:contest_entry_assignment")
        if assignment:
            candidate_id = str(assignment["lineup_id"])
            candidate = saved_by_lineup.get(candidate_id, [])
            if identity_complete and candidate and _signature(candidate) == _signature(resolved_players):
                matched_lineup_id = candidate_id
                match_basis = "contest_entry_assignment"
            else:
                missing.add(f"entry:{contest_id}:{entry['entry_id']}:assignment_signature_conflict")
        elif identity_complete:
            if len(candidates) == 1:
                matched_lineup_id = candidates[0]
                match_basis = "canonical_lineup_signature"
            elif candidates:
                match_basis = "ambiguous_canonical_lineup_signature"
                missing.add(f"entry:{contest_id}:{entry['entry_id']}:ambiguous_saved_lineup_matches")

        saved_rows = saved_by_lineup.get(matched_lineup_id or "", [])
        saved_by_identity = {
            (
                str(row["player_id"]),
                str(row.get("roster_position") or "").upper() == "CPT",
            ): row
            for row in saved_rows
        }
        optimizer_run_id = (
            str(saved_rows[0].get("optimizer_run_id")) if saved_rows else None
        )
        projection_run_id = (
            str(saved_rows[0].get("projection_run_id"))
            if saved_rows and saved_rows[0].get("projection_run_id")
            else None
        )
        rule_run_id = (
            str(saved_rows[0].get("rule_run_id"))
            if saved_rows and saved_rows[0].get("rule_run_id")
            else None
        )
        if optimizer_run_id:
            run_ids["optimizer_run_ids"].add(optimizer_run_id)
        if projection_run_id:
            run_ids["projection_run_ids"].add(projection_run_id)
        if rule_run_id:
            run_ids["rule_run_ids"].add(rule_run_id)
        elif matched_lineup_id:
            missing.add(f"lineup:{matched_lineup_id}:symbolic_rule_run")
        if identity_complete and not matched_lineup_id:
            missing.add(f"entry:{contest_id}:{entry['entry_id']}:saved_lineup_lineage")

        player_reports = []
        for player in resolved_players:
            saved = saved_by_identity.get(
                (
                    player["player_id"],
                    player["roster_position"] == "CPT",
                )
            )
            projected = _number(saved.get("projection")) if saved else None
            residual = player["actual_points"] - projected if projected is not None else None
            if residual is not None:
                projection_errors.append(abs(residual))
                squared_errors.append(residual * residual)
            event = outcome_events.get(player["player_id"], {})
            tag = str(event.get("tag") or "UNKNOWN").upper()
            if (tag not in OUTCOME_TAGS
                    or (tag != "UNKNOWN" and not event.get("evidence"))
                    or (tag == "NORMAL_VARIANCE" and not event.get("source_url"))):
                tag = "UNKNOWN"
            rule_results = []
            if rule_run_id:
                actual_base = player["actual_points"] / (1.5 if player["roster_position"] == "CPT" else 1.0)
                for application in applications_by_run_player.get(
                    (rule_run_id, player["player_id"]), []
                ):
                    before = _number(application.get("mean_before"))
                    after = _number(application.get("mean_after"))
                    rule_results.append(
                        {
                            "rule_id": application.get("rule_id"),
                            "rule_version": application.get("rule_version"),
                            "mean_before": before,
                            "mean_after": after,
                            "actual_points": actual_base,
                            "mae_before": abs(actual_base - before) if before is not None else None,
                            "mae_after": abs(actual_base - after) if after is not None else None,
                            "improved": (
                                abs(actual_base - after) < abs(actual_base - before)
                                if before is not None and after is not None
                                else None
                            ),
                        }
                    )
            player_reports.append(
                {
                    **player,
                    "projected_points": projected,
                    "actual_base_points": (
                        player["actual_points"] / 1.5
                        if player["roster_position"] == "CPT"
                        else player["actual_points"]
                    ),
                    "projected_base_points": (
                        projected / 1.5
                        if projected is not None and player["roster_position"] == "CPT"
                        else projected
                    ),
                    "projection_residual": residual,
                    "outcome_tag": tag,
                    "outcome_tag_evidence": event.get("evidence") if tag != "UNKNOWN" else None,
                    "outcome_tag_source_url": event.get("source_url") if tag != "UNKNOWN" else None,
                    "training_eligible_residual": tag == "NORMAL_VARIANCE" and residual is not None,
                    "rule_evaluations": rule_results,
                }
            )
            if projected is not None:
                base_projection = projected / (1.5 if player["roster_position"] == "CPT" else 1.0)
                unique_projection_players.setdefault(
                    (projection_run_id or optimizer_run_id or "", player["player_id"], round(base_projection, 6)),
                    {**player_reports[-1],
                     "projection_residual": player_reports[-1]["actual_base_points"] - base_projection},
                )

        if identity_complete:
            actual_signature = _signature(resolved_players)
            actual_lineup_counts[actual_signature] += 1
            captain = next(
                (
                    player["player_display_name"]
                    for player in resolved_players
                    if player["roster_position"] == "CPT"
                ),
                None,
            )
            if captain:
                captain_counts[captain] += 1

        rank = int(entry["rank"]) if entry.get("rank") is not None else None
        field_size = int(contest.get("field_size") or 0)
        payout = None
        contest_tiers = [
            tier
            for tier in evidence.get("payout_tiers", [])
            if str(tier.get("contest_id")) == contest_id
        ]
        if rank is not None:
            for tier in contest_tiers:
                if int(tier["min_rank"]) <= rank <= int(tier["max_rank"]):
                    payout = _number(tier.get("payout"))
                    break
            if payout is None and contest_tiers:
                payout = 0.0
        fee = _number(contest.get("entry_fee"))
        personal = next((row for row in evidence.get('entry_history', [])
                         if row['contest_id'] == contest_id and str(row['entry_id']) == str(entry['entry_id'])), None)
        if personal:
            fee = personal['entry_fee']
            payout = personal['cash_winnings']
        financial = {
            "contest": contest.get("contest_name"),
            "contest_type": contest.get("contest_type"),
            "field_size": field_size,
            "entry_fee": fee,
            "payout": payout,
            "profit": payout - fee if payout is not None and fee is not None else None,
            "roi": (payout - fee) / fee if payout is not None and fee not in {None, 0} else None,
            "status": "complete" if payout is not None and fee is not None else "missing_fee_or_payout_evidence",
        }
        financial['payout_source'] = 'entry_history' if personal else 'payout_tiers'
        financial['ticket_winnings'] = personal['ticket_winnings'] if personal else None
        financial['paid_finish'] = (payout > 0 or personal['ticket_winnings'] > 0) if personal else (payout > 0 if payout is not None else None)
        cash_line = _number(next((row.get("cash_line") for row in evidence.get("cash_lines", [])
                                  if str(row.get("contest_id")) == contest_id), None))
        financial["cash_line"] = cash_line
        financial["points_from_cash_line"] = (
            _number(entry.get("entry_points")) - cash_line
            if cash_line is not None and _number(entry.get("entry_points")) is not None else None
        )
        financial["rank"] = rank
        financial["percentile"] = (100.0 * (field_size - rank + 1) / field_size) if rank and field_size else None
        if financial["status"] != "complete":
            missing.add(f"contest:{contest_id}:financial_evidence")

        portfolio_id = str(assignment["portfolio_id"]) if assignment else None
        portfolio = portfolio_by_id.get(portfolio_id or "")
        related_exports = exports_by_portfolio.get(portfolio_id or "", [])
        if portfolio_id:
            run_ids["portfolio_ids"].add(portfolio_id)
        for export in related_exports:
            run_ids["export_ids"].add(str(export["export_id"]))
        if assignment and not related_exports:
            missing.add(f"portfolio:{portfolio_id}:export")

        control = None
        if saved_rows:
            for saved in saved_rows:
                player_json = saved.get("player_json") or {}
                if isinstance(player_json, str):
                    player_json = json.loads(player_json)
                if player_json.get("lineup_control_comparison"):
                    control = player_json["lineup_control_comparison"]
                    break
        if matched_lineup_id and control is None:
            missing.add(f"lineup:{matched_lineup_id}:opt_007_control")
        actuals_for_contest: dict[tuple[str, str], dict[str, Any]] = {}
        conflicting_actuals: set[tuple[str, str]] = set()
        for observation in observations:
            if str(observation.get("contest_id")) != contest_id or observation.get("resolution_status") != "resolved":
                continue
            actual_value = _number(observation.get("actual_points"))
            if actual_value is not None and observation.get("player_id"):
                slot = "CPT" if str(observation.get("roster_position") or "").upper() == "CPT" else "FLEX"
                key = (str(observation["player_id"]), slot)
                if key in actuals_for_contest and actuals_for_contest[key]["actual_points"] != actual_value:
                    conflicting_actuals.add(key)
                actuals_for_contest[key] = {"actual_points": actual_value,
                                            "observation_id": observation.get("observation_id")}
        for key in conflicting_actuals:
            actuals_for_contest.pop(key, None)
        control_outcome = _score_control(control, saved_rows, actuals_for_contest) if isinstance(control, Mapping) else None
        if control_outcome and control_outcome["status"] != "complete":
            missing.add(f"lineup:{matched_lineup_id}:opt_007_control_actuals")
        lineup_metadata = _json_mapping(saved_rows[0].get("player_json")) if saved_rows else {}
        game_script = _json_mapping(lineup_metadata.get("portfolio_game_script"))
        environment = _game_environment(saved_rows, saved_rows[0].get("data_cutoff_at") if saved_rows else None)
        structure = _lineup_structure_family(game_script, environment) if saved_rows else None
        run_config = _json_mapping(
            optimizer_runs_by_id.get(optimizer_run_id, {}).get("constraint_config_json")
            or (saved_rows[0].get("constraint_config_json") if saved_rows else None)
        )

        entry_reports.append(
            {
                "contest_id": contest_id,
                "entry_id": str(entry["entry_id"]),
                "rank": rank,
                "field_size": field_size,
                "top_percent": (100.0 * rank / field_size) if rank and field_size else None,
                "entry_points": _number(entry.get("entry_points")),
                "identity_complete": identity_complete,
                "unresolved_players": unresolved_players,
                "lineup_match_basis": match_basis,
                "lineup_id": matched_lineup_id,
                "saved_lineup_number": saved_rows[0].get("lineup_number") if saved_rows else None,
                "optimizer_run_id": optimizer_run_id,
                "projection_run_id": projection_run_id,
                "rule_run_id": rule_run_id,
                "data_cutoff_at": saved_rows[0].get("data_cutoff_at") if saved_rows else None,
                "strategy": saved_rows[0].get("strategy") if saved_rows else None,
                "objective": saved_rows[0].get("objective") if saved_rows else None,
                "projected_points": (
                    sum(_number(row.get("projection")) or 0 for row in saved_rows)
                    if saved_rows and all(_number(row.get("projection")) is not None for row in saved_rows)
                    else None
                ),
                "players": player_reports,
                "financial": financial,
                "portfolio": dict(portfolio) if portfolio else None,
                "exports": related_exports,
                "submission_evidence": submission_evidence(
                    entry, resolved_players, identity_complete, assignment, saved_by_lineup,
                    saved_matches, related_exports, evidence.get("export_records", []), []),
                "opt_007_control": control,
                "opt_007_outcome": control_outcome,
                "decision_snapshot": optimizer_runs_by_id.get(optimizer_run_id, {}).get(
                    "decision_snapshot", run_config.get("decision_snapshot")),
                "lineup_structure_family": structure,
                "game_environment": environment,
            }
        )

    if entries and not projection_errors:
        missing.add("slate:projection_evaluation")
    if not beliefs:
        missing.add("slate:beliefs")

    actuals_by_player: dict[str, list[float]] = defaultdict(list)
    for observation in observations:
        if observation.get("resolution_status") != "resolved" or not observation.get("player_id"):
            continue
        actual = _number(observation.get("actual_points"))
        if actual is None:
            continue
        if str(observation.get("roster_position") or "").upper() == "CPT":
            actual /= 1.5
        actuals_by_player[str(observation["player_id"])].append(actual)
    actual_outcomes = {
        player_id: _mean(sorted(set(round(value, 6) for value in values)))
        for player_id, values in actuals_by_player.items()
    }
    disrupted_players = {
        player_id for player_id, event in outcome_events.items()
        if str(event.get("tag") or "").upper() in OUTCOME_TAGS - {"NORMAL_VARIANCE", "UNKNOWN"}
        and event.get("evidence")
    }

    belief_reports = []
    residuals_by_player = defaultdict(list)
    for entry in entry_reports:
        for player in entry["players"]:
            actual_base = _number(player.get("actual_base_points"))
            projected_base = _number(player.get("projected_base_points"))
            if actual_base is not None and projected_base is not None and player["player_id"] not in disrupted_players:
                residuals_by_player[player["player_id"]].append(actual_base - projected_base)
    decision_cutoffs = [
        cutoff
        for entry in entry_reports
        if (cutoff := _as_datetime(entry.get("data_cutoff_at"))) is not None
    ]
    decision_cutoff = min(decision_cutoffs) if decision_cutoffs else None
    impacts_by_belief = {
        str(row.get("belief_version_id")): row
        for row in belief_impacts
        if row.get("belief_version_id")
    }
    for belief in beliefs:
        direction = str(belief.get("direction") or "").lower()
        residual = _mean(residuals_by_player.get(str(belief.get("subject_id") or ""), []))
        belief_created_at = _as_datetime(belief.get("created_at"))
        if belief.get("is_retrospective"):
            timing_status = "retrospective"
        elif decision_cutoff is None:
            timing_status = "missing_decision_cutoff"
        elif belief_created_at is None:
            timing_status = "missing_belief_created_at"
        elif belief_created_at <= decision_cutoff:
            timing_status = "predecision"
        else:
            timing_status = "created_after_decision"
        score = "unscored"
        if (
            timing_status == "predecision"
            and residual is not None
            and direction in {"boost", "prefer", "fade", "avoid"}
        ):
            expected_positive = direction in {"boost", "prefer"}
            if abs(residual) <= LEARNING_EFFECT_TOLERANCE:
                score = "no_measurable_effect"
            else:
                score = "supported" if (residual >= 0) == expected_positive else "contradicted"
        impact = impacts_by_belief.get(str(belief.get("belief_version_id") or ""), {})
        impact_decided_at = _as_datetime(impact.get("decided_at"))
        impact_timing = (
            "not_decided"
            if not impact.get("decision")
            else "missing_decision_cutoff"
            if decision_cutoff is None
            else "missing_decision_created_at"
            if impact_decided_at is None
            else "predecision"
            if impact_decided_at <= decision_cutoff
            else "created_after_decision"
        )
        baseline = _json_mapping(impact.get("baseline_json"))
        proposed = _json_mapping(impact.get("proposed_json"))
        actual = actual_outcomes.get(str(belief.get("subject_id") or ""))
        baseline_mean = _number(baseline.get("projection_mean"))
        proposed_mean = _number(proposed.get("projection_mean"))
        if impact_timing != "predecision" or str(belief.get("subject_id") or "") in disrupted_players:
            impact_result = _compare_choice(actual=None, selected=None, comparator=None)
        elif impact.get("decision") == "approved":
            impact_result = _compare_choice(
                actual=actual, selected=proposed_mean, comparator=baseline_mean
            )
        else:
            impact_result = _compare_choice(
                actual=actual, selected=baseline_mean, comparator=proposed_mean
            )
        belief_reports.append(
            {
                "belief_id": belief.get("belief_id"),
                "belief_version_id": belief.get("belief_version_id"),
                "scope_type": belief.get("scope_type"),
                "subject_id": belief.get("subject_id"),
                "direction": direction,
                "strength": belief.get("strength"),
                "confidence": belief.get("confidence"),
                "thought_text": belief.get("thought_text"),
                "pregame_evidence": belief.get("evidence_text"),
                "pregame_metadata": _json_mapping(belief.get("metadata_json")),
                "postgame_evidence": {
                    "actual_points": actual,
                    "mean_projection_residual": residual,
                },
                "conclusion_scope": "hypothesis_only" if score != "unscored" else "unscorable",
                "is_retrospective": bool(belief.get("is_retrospective")),
                "timing_status": timing_status,
                "evaluation": score,
                "evidence_classification": score.upper() if score != "unscored" else "UNSCORABLE",
                "chronological_validation_candidate": timing_status == "predecision" and score != "unscored",
                "mean_projection_residual": residual,
                "actual_points": actual,
                "impact_decision": impact.get("decision"),
                "impact_timing_status": impact_timing,
                "baseline_projection_mean": baseline_mean,
                "selected_projection_mean": (
                    proposed_mean if impact.get("decision") == "approved" else baseline_mean
                ),
                **impact_result,
            }
        )
        if belief.get("belief_version_id"):
            run_ids["belief_version_ids"].add(str(belief["belief_version_id"]))

    question_reports = []
    for question in agent_questions:
        answer = str(question.get("answer") or "") or None
        answer_at = _as_datetime(question.get("answered_at"))
        if answer is None:
            timing_status = "unanswered"
        elif decision_cutoff is None:
            timing_status = "missing_decision_cutoff"
        elif answer_at is None:
            timing_status = "missing_answer_created_at"
        elif answer_at <= decision_cutoff:
            timing_status = "predecision"
        else:
            timing_status = "created_after_decision"
        context = _json_mapping(question.get("context_json", question.get("context")))
        modifier = _json_mapping(
            question.get("resulting_modifier_json", question.get("resulting_modifier"))
        )
        actual = actual_outcomes.get(str(question.get("subject_player_id") or ""))
        baseline_mean = _number(context.get("model_projection_mean"))
        selected_mean = baseline_mean
        comparator_mean = None
        if answer == "support_human":
            selected_mean = _number(context.get("human_projection_mean"))
            comparator_mean = baseline_mean
        elif answer == "support_model":
            comparator_mean = _number(context.get("human_projection_mean"))
        elif answer in {"lean_upside", "lean_downside"}:
            multiplier = _number(modifier.get("projection_multiplier"))
            selected_mean = baseline_mean * multiplier if baseline_mean is not None and multiplier is not None else None
            comparator_mean = baseline_mean
        if timing_status != "predecision" or answer == "no_change" or str(question.get("subject_player_id") or "") in disrupted_players:
            result = _compare_choice(actual=None, selected=None, comparator=None)
            if timing_status == "predecision" and answer == "no_change":
                result["outcome_effect"] = "no_measurable_effect"
                result["selected_abs_error"] = (
                    round(abs(actual - baseline_mean), 4)
                    if actual is not None and baseline_mean is not None
                    else None
                )
        else:
            result = _compare_choice(
                actual=actual, selected=selected_mean, comparator=comparator_mean
            )
        question_reports.append({
            "question_id": question.get("question_id"),
            "answer_id": question.get("answer_id"),
            "policy_id": question.get("policy_id"),
            "trigger_type": question.get("trigger_type"),
            "subject_player_id": question.get("subject_player_id"),
            "subject_label": question.get("subject_label"),
            "question_text": question.get("question_text"),
            "answer": answer,
                "answer_text": question.get("answer_text"),
                "pregame_evidence": context,
                "postgame_evidence": {"actual_points": actual},
                "conclusion_scope": "hypothesis_only" if result["outcome_effect"] != "unscored" else "unscorable",
            "timing_status": timing_status,
            "actual_points": actual,
            "baseline_projection_mean": baseline_mean,
            "selected_projection_mean": selected_mean,
            "comparator_projection_mean": comparator_mean,
            "resulting_modifier": modifier,
            **result,
        })
        if question.get("question_id"):
            run_ids["agent_question_ids"].add(str(question["question_id"]))
        if question.get("answer_id"):
            run_ids["agent_answer_ids"].add(str(question["answer_id"]))

    belief_effects = Counter(row["outcome_effect"] for row in belief_reports)
    question_effects = Counter(row["outcome_effect"] for row in question_reports)
    def belief_group(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
        grouped = list(rows)
        return {
            "total": len(grouped),
            "theses_scored": sum(row.get("evaluation") != "unscored" for row in grouped),
            "supported": sum(row.get("evaluation") == "supported" for row in grouped),
            "contradicted": sum(row.get("evaluation") == "contradicted" for row in grouped),
            "helped": sum(row.get("outcome_effect") == "helped" for row in grouped),
            "hurt": sum(row.get("outcome_effect") == "hurt" for row in grouped),
            "no_measurable_effect": sum(
                row.get("outcome_effect") == "no_measurable_effect" for row in grouped
            ),
            "unscored": sum(row.get("outcome_effect") == "unscored" for row in grouped),
        }

    belief_scopes = {
        scope: belief_group(row for row in belief_reports if row.get("scope_type") == scope)
        for scope in sorted({str(row.get("scope_type") or "unknown") for row in belief_reports})
    }
    confidence_bands = {
        label: belief_group(
            row for row in belief_reports
            if lower <= int(row.get("confidence") or 0) <= upper
        )
        for label, lower, upper in (("low_0_49", 0, 49), ("medium_50_74", 50, 74), ("high_75_100", 75, 100))
        if any(lower <= int(row.get("confidence") or 0) <= upper for row in belief_reports)
    }
    source_file_ids = sorted(
        {str(row["source_file_id"]) for row in contests if row.get("source_file_id")}
    )
    contest_summaries = [
        {
            key: row.get(key)
            for key in (
                "contest_id", "contest_name", "contest_format", "contest_type",
                "field_size", "observed_entries", "field_complete", "winning_points",
                "median_points", "source_file_id", "content_sha256",
            )
        }
        for row in contests
    ]
    duplicate_entries = sum(count - 1 for count in actual_lineup_counts.values() if count > 1)
    unique_metrics = _projection_metrics(unique_projection_players.values())
    entry_outcome_counts = _outcome_counts(
        player for entry in entry_reports for player in entry["players"]
    )
    unique_outcome_counts = _outcome_counts(unique_projection_players.values())
    financials = [row["financial"] for row in entry_reports]
    fees_complete = bool(financials) and all(row["entry_fee"] is not None for row in financials)
    payouts_complete = bool(financials) and all(row["payout"] is not None for row in financials)
    financial_complete = fees_complete and payouts_complete
    amount_entered = sum(row["entry_fee"] for row in financials) if fees_complete else None
    amount_returned = sum(row["payout"] for row in financials) if payouts_complete else None
    net_profit = amount_returned - amount_entered if financial_complete else None
    player_exposure = Counter(
        player["player_id"] for entry in entry_reports for player in entry["players"]
    )
    bankroll_by_lineup = defaultdict(float)
    structure_families: dict[str, dict[str, Any]] = {}
    for entry in entry_reports:
        if entry["lineup_id"] and entry["financial"]["entry_fee"] is not None:
            bankroll_by_lineup[entry["lineup_id"]] += entry["financial"]["entry_fee"]
        structure = entry.get("lineup_structure_family") or {}
        family_id = str(structure.get("family_id") or "unknown")
        family = structure_families.setdefault(family_id, {"family_id": family_id, "entries": 0, "bankroll": 0.0,
                                                      "lineup_ids": set(), "net_profit": 0.0,
                                                      "fee_complete": True, "profit_complete": True})
        family["entries"] += 1
        if entry["lineup_id"]:
            family["lineup_ids"].add(entry["lineup_id"])
        fee = entry["financial"]["entry_fee"]
        profit = entry["financial"]["profit"]
        if fee is not None:
            family["bankroll"] += fee
        else:
            family["fee_complete"] = False
            family["profit_complete"] = False
        if profit is not None:
            family["net_profit"] += profit
        else:
            family["profit_complete"] = False
    for entry in entry_reports:
        links = [r for r in evidence.get("entry_candidate_lineage", [])
                 if str(r["contest_id"]) == str(entry["contest_id"]) and str(r["entry_id"]) == str(entry["entry_id"])]
        matches = [m for r in links for m in r.get("matches", [])]
        entry["candidate_lineage"] = matches
        matching_runs = {m["optimizer_run_id"] for m in matches}
        saved_match_runs = {m["optimizer_run_id"] for m in entry["submission_evidence"]["saved_lineup_matches"]}
        if not entry["optimizer_run_id"] and len(matching_runs) == 1 and len(saved_match_runs) <= 1:
            entry["optimizer_run_id"] = next(iter(matching_runs))
            entry["projection_run_id"] = matches[0].get("projection_run_id")
            entry["lineup_match_basis"] = "original_candidate_signature_only"
            run_ids["optimizer_run_ids"].add(entry["optimizer_run_id"])
            if entry["projection_run_id"]:
                run_ids["projection_run_ids"].add(entry["projection_run_id"])
        entry["submission_evidence"] = submission_evidence(
            entry["submission_evidence"]["observed"], entry["players"], entry["identity_complete"],
            assigned.get((str(entry["contest_id"]), str(entry["entry_id"]))), saved_by_lineup,
            entry["submission_evidence"]["saved_lineup_matches"], entry["exports"],
            evidence.get("export_records", []), matches)
    report = {
        "evaluation_records": evidence.get("evaluation_records", []),
        "contract_id": LEARNING_REPORT_CONTRACT,
        "builder_version": LEARNING_REPORT_BUILDER_VERSION,
        "season": season,
        "week": week,
        "slate": slate.upper(),
        "entry_user": entry_user,
        "generated_at": generated.isoformat(),
        "status": "partial" if missing else "completed",
        "summary": {
            "contests": len(contests),
            "entries": len(entries),
            "identity_complete_entries": sum(entry["identity_complete"] for entry in entry_reports),
            "matched_optimizer_entries": sum(entry["optimizer_run_id"] is not None for entry in entry_reports),
            "entries_with_opt_007": sum(entry["opt_007_control"] is not None for entry in entry_reports),
            "duplicate_entries": duplicate_entries,
            "projection_player_observations": len(projection_errors),
            "projection_mae": _mean(projection_errors),
            "projection_rmse": (
                math.sqrt(_mean(squared_errors)) if squared_errors else None
            ),
            "unique_projection_observations": unique_metrics["observations"],
            "unique_projection_mae": unique_metrics["mae"],
            "unique_projection_rmse": unique_metrics["rmse"],
            "entry_weighted_outcome_counts": entry_outcome_counts,
            "unique_outcome_counts": unique_outcome_counts,
            "total_amount_entered": amount_entered,
            "total_returned": amount_returned,
            "net_profit": net_profit,
            "roi": net_profit / amount_entered if net_profit is not None and amount_entered else None,
            "number_cashed": sum(bool(row["paid_finish"]) for row in financials) if payouts_complete else None,
            "net_positive": net_profit > 0 if net_profit is not None else None,
        },
        "portfolio_analysis": {
            "captain_exposure": [
                {
                    "player_display_name": name,
                    "entries": count,
                    "pct": 100.0 * count / len(entries) if entries else 0.0,
                }
                for name, count in captain_counts.most_common()
            ],
            "duplicate_entries": duplicate_entries,
            "player_exposure": [
                {"player_id": player_id, "entries": count, "pct": 100.0 * count / len(entries)}
                for player_id, count in player_exposure.most_common()
            ] if entries else [],
            "bankroll_by_lineup": [
                {"lineup_id": lineup_id, "amount": amount,
                 "pct": 100.0 * amount / amount_entered if amount_entered else None}
                for lineup_id, amount in sorted(bankroll_by_lineup.items())
            ],
            "lineup_structure_families": [
                {"family_id": family_id, "entries": family["entries"],
                 "distinct_lineups": len(family["lineup_ids"]),
                 "bankroll": family["bankroll"] if family["fee_complete"] else None,
                 "bankroll_pct": 100.0 * family["bankroll"] / amount_entered
                 if amount_entered else None,
                 "net_profit": family["net_profit"] if family["profit_complete"] else None}
                for family_id, family in sorted(structure_families.items())
            ],
            "distinct_recorded_lineup_structures": len([key for key in structure_families if key != "unknown"]),
            "profitable_lineup_structure_families": (
                sum(family["net_profit"] > 0 for family in structure_families.values())
                if financial_complete else None
            ),
            "best_entry": next(({"contest_id": row["contest_id"], "entry_id": row["entry_id"],
                                  "profit": row["financial"]["profit"]}
                                 for row in sorted(entry_reports, key=lambda row: row["financial"]["profit"]
                                                   if row["financial"]["profit"] is not None else float("-inf"), reverse=True)
                                 if row["financial"]["profit"] is not None), None),
            "worst_entry": next(({"contest_id": row["contest_id"], "entry_id": row["entry_id"],
                                   "profit": row["financial"]["profit"]}
                                  for row in sorted(entry_reports, key=lambda row: row["financial"]["profit"]
                                                    if row["financial"]["profit"] is not None else float("inf"))
                                  if row["financial"]["profit"] is not None), None),
            "net_profit": net_profit,
            "diversification_assessment": "Requires contest payouts and script-family outcomes; lineup differences alone earn no credit.",
        },
        "contests": contest_summaries,
        "entries": entry_reports,
        "beliefs": belief_reports,
        "agent_questions": question_reports,
        "learning_outcomes": {
            "beliefs": {
                "total": len(belief_reports),
                "theses_scored": sum(row["evaluation"] != "unscored" for row in belief_reports),
                "supported": sum(row["evaluation"] == "supported" for row in belief_reports),
                "contradicted": sum(row["evaluation"] == "contradicted" for row in belief_reports),
                "helped": belief_effects["helped"],
                "hurt": belief_effects["hurt"],
                "no_measurable_effect": belief_effects["no_measurable_effect"],
                "unscored": belief_effects["unscored"],
                "by_scope": belief_scopes,
                "by_confidence_band": confidence_bands,
            },
            "agent_answers": {
                "total": len(question_reports),
                "answered": sum(row["answer"] is not None for row in question_reports),
                "helped": question_effects["helped"],
                "hurt": question_effects["hurt"],
                "no_measurable_effect": question_effects["no_measurable_effect"],
                "unscored": question_effects["unscored"],
            },
            "effect_tolerance_points": LEARNING_EFFECT_TOLERANCE,
        },
        "source_file_ids": source_file_ids,
        "run_ids": {key: sorted(values) for key, values in sorted(run_ids.items())},
        "missing_evidence": sorted(missing),
        "interpretation": (
            "Observed outcomes diagnose completed entries. They do not by themselves "
            "justify changing a production model or rule."
        ),
        "validation_gate": {
            "production_change_allowed": False,
            "requirement": "Separate chronological multi-slate validation using only prelock information",
        },
    }
    if run_loader:
        report["contract_id"] = "slate_learning_report_v2"
    report["optimizer_effectiveness"] = build_optimizer_effectiveness(
        report, evidence, run_loader=run_loader, detail_sink=detail_sink,
        diagnostic_run_ids=diagnostic_run_ids,
    )
    for run in report["optimizer_effectiveness"]["runs"]:
        if run.get("run_scope") == "entry_linked" and run.get("status") != "complete":
            missing.add(f"optimizer_run:{run['optimizer_run_id']}:{run.get('status')}")
    for contest_id, field in report["optimizer_effectiveness"]["field_benchmarks"].items():
        if field.get("status") != "available":
            missing.add(f"contest:{contest_id}:complete_scored_field")
    report["missing_evidence"] = sorted(missing)
    report["status"] = "partial" if missing else "completed"
    report["evidence_hash"] = _canonical_hash(
        {
            "builder_version": LEARNING_REPORT_BUILDER_VERSION,
            "scope": [season, week, slate.upper(), entry_user.casefold()],
            "contests": contests,
            "entries": entries,
            "observations": observations,
            "lineup_players": lineup_players,
            "optimizer_runs": [
                {"optimizer_run_id": str(row["optimizer_run_id"]), "evidence_hash": _canonical_hash(row)}
                for row in evidence.get("optimizer_runs", [])
            ],
            "assignments": assignments,
            "portfolios": portfolios,
            "exports": exports,
            "export_records": evidence.get("export_records", []),
            "rule_applications": rule_applications,
            "beliefs": beliefs,
            "belief_impacts": belief_impacts,
            "agent_questions": agent_questions,
            "payout_tiers": evidence.get("payout_tiers", []),
            "entry_history": evidence.get("entry_history", []),
            "entry_candidate_lineage": evidence.get("entry_candidate_lineage", []),
            "evaluation_records": evidence.get("evaluation_records", []),
            "recommendation_assignments": evidence.get("recommendation_assignments", []),
            "entry_history_sources": evidence.get("entry_history_sources", []),
            "entry_history_conflicts": evidence.get("entry_history_conflicts", []),
            "cash_lines": evidence.get("cash_lines", []),
            "outcome_events": evidence.get("outcome_events", []),
            "optimizer_effectiveness": report["optimizer_effectiveness"],
        }
    )
    report["report_id"] = "learning-report-" + str(
        uuid.uuid5(uuid.NAMESPACE_URL, report["evidence_hash"])
    )
    return report


def build_weekly_learning_report(
    *, season: int, week: int, entry_user: str,
    slate_reports: Iterable[Mapping[str, Any]],
    historical_slate_reports: Iterable[Mapping[str, Any]] = (),
    weekly_stats: Mapping[str, Any] | None = None,
    generated_at: datetime | None = None,
    correlation_loader: Callable[[Mapping[str, Any], Mapping[str, Any]], Iterable[Mapping[str, Any]]] | None = None,
    format_results: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Combine exact slate reports without treating repeated entries as new model labels."""
    reports = sorted((dict(report) for report in slate_reports), key=lambda row: row["slate"])
    typed_results = [dict(row) for row in format_results]
    if not reports and not typed_results:
        raise ValueError("No imported contest results exist for this user and week")
    entries = [
        {"slate": report["slate"], **entry}
        for report in reports for entry in report["entries"]
    ]
    observed_contests = {(entry["slate"], entry["contest_id"]) for entry in entries}
    observation_count = sum(report["summary"]["projection_player_observations"] for report in reports)
    weighted_absolute_error = sum(
        report["summary"]["projection_mae"] * report["summary"]["projection_player_observations"]
        for report in reports if report["summary"]["projection_mae"] is not None
    )
    weighted_squared_error = sum(
        report["summary"]["projection_rmse"] ** 2 * report["summary"]["projection_player_observations"]
        for report in reports if report["summary"]["projection_rmse"] is not None
    )
    unique_week_players: dict[tuple[str, str, str, float], Mapping[str, Any]] = {}
    for entry in entries:
        for player in entry["players"]:
            projected = _number(player.get("projected_base_points"))
            if projected is not None:
                unique_week_players.setdefault(
                    (entry["slate"], str(entry.get("projection_run_id") or entry.get("optimizer_run_id") or ""),
                     str(player["player_id"]), round(projected, 6)),
                    {**player, "projection_residual": _number(player.get("actual_base_points")) - projected},
                )
    unique_week_metrics = _projection_metrics(unique_week_players.values())
    weekly_outcome_counts = _outcome_counts(unique_week_players.values())
    slate_financials = [report["summary"] for report in reports]
    entered_complete = bool(slate_financials) and all(row.get("total_amount_entered") is not None for row in slate_financials)
    returned_complete = bool(slate_financials) and all(row.get("total_returned") is not None for row in slate_financials)
    financial_complete = entered_complete and returned_complete
    entered = sum(row["total_amount_entered"] for row in slate_financials) if entered_complete else None
    returned = sum(row["total_returned"] for row in slate_financials) if returned_complete else None
    source_file_ids = sorted({source_id for report in reports for source_id in report["source_file_ids"]} | {row["source_file_id"] for row in typed_results if row.get("source_file_id")})
    run_ids: dict[str, set[str]] = defaultdict(set)
    for report in reports:
        for kind, identifiers in report["run_ids"].items():
            run_ids[kind].update(identifiers)
    if weekly_stats is not None:
        run_ids["weekly_stats_ingest"].add(weekly_stats["ingest_run_id"])
        run_ids["source_snapshot"].add(weekly_stats["snapshot_id"])
    optimizer_history = []
    all_reports = sorted([*historical_slate_reports, *reports],
                         key=lambda row: (row.get("season", 0), row.get("week", 0), row.get("slate", "")))
    correlation_groups: dict[str, dict[str, Any]] = defaultdict(lambda: {"slates": set(), "candidates": []})
    for past in all_reports:
        for run in (past.get("optimizer_effectiveness") or {}).get("runs", []):
            if (run.get("run_scope", "entry_linked") == "entry_linked"
                    and run.get("status") == "complete"
                    and (run.get("chronological_validation") or {}).get("status") == "predecision"):
                fmt = str(run.get("contest_format") or "")
                correlation_groups[fmt]["slates"].add((past.get("season"), past.get("week"), past.get("slate")))
                correlation_groups[fmt]["candidates"].extend(
                    correlation_loader(past, run) if correlation_loader else run.get("candidates") or []
                )
    aggregate_correlations = {
        fmt: {"status": "available" if len(group["slates"]) >= 2 else "insufficient_chronologically_valid_slates",
              "slates": len(group["slates"]), "candidate_count": len(group["candidates"]),
              "correlations": metric_correlations(group["candidates"]) if len(group["slates"]) >= 2 else None}
        for fmt, group in correlation_groups.items()
    }
    for fmt in ("classic", "showdown"):
        aggregate_correlations.setdefault(fmt, {"status": "insufficient_chronologically_valid_slates",
                                                "slates": 0, "candidate_count": 0, "correlations": None})
    for past in all_reports:
        effectiveness = past.get("optimizer_effectiveness") or {}
        for run in effectiveness.get("runs", []):
            if run.get("run_scope", "entry_linked") != "entry_linked":
                continue
            for contest_id, field in (run.get("field") or {}).items():
                attainment = field.get("attainment") or {}
                generated = (run.get("unique_roster_count") or run.get("generated_count") or 0) if run.get("status") == "complete" else 0
                selected = (run.get("selected_count") or 0) if run.get("selected_scored_count") == run.get("selected_count") else 0
                optimizer_history.append({
                    "season": past.get("season"), "week": past.get("week"), "slate": past.get("slate"),
                    "contest_id": contest_id, "contest_format": run.get("contest_format"),
                    "strategy": run.get("strategy"), "optimizer_run_id": run.get("optimizer_run_id"),
                    "status": run.get("status"),
                    "best_generated_top_percent": (field.get("best_generated_field_rank") or {}).get("top_percent_conservative"),
                    "best_selected_top_percent": (field.get("best_selected_field_rank") or {}).get("top_percent_conservative"),
                    "best_entered_top_percent": (field.get("best_entered_field_rank") or {}).get("top_percent_conservative"),
                    "selection_regret_observed": run.get("selection_regret_observed"),
                    "selector_spearman": ((run.get("correlations") or {}).get("objective_score") or {}).get("spearman"),
                    "candidate_cash_rate_scored": ((attainment.get("cash") or {}).get("generated_scored") / generated
                                                    if generated and (attainment.get("cash") or {}).get("generated_scored") is not None else None),
                    "candidate_top_10_rate_scored": ((attainment.get("top_10_percent") or {}).get("generated_scored") / generated
                                                      if generated and (attainment.get("top_10_percent") or {}).get("generated_scored") is not None else None),
                    "candidate_top_1_rate_scored": ((attainment.get("top_1_percent") or {}).get("generated_scored") / generated
                                                     if generated and (attainment.get("top_1_percent") or {}).get("generated_scored") is not None else None),
                    "selected_top_10_rate_scored": ((attainment.get("top_10_percent") or {}).get("selected_scored") / selected
                                                     if selected and (attainment.get("top_10_percent") or {}).get("selected_scored") is not None else None),
                    "selected_top_1_rate_scored": ((attainment.get("top_1_percent") or {}).get("selected_scored") / selected
                                                    if selected and (attainment.get("top_1_percent") or {}).get("selected_scored") is not None else None),
                })
    evidence_hash = _canonical_hash({
        **({"typed_results": typed_results} if typed_results else {}),
        "contract_id": "weekly_learning_report_v2" if correlation_loader else WEEKLY_LEARNING_REPORT_CONTRACT,
        "scope": [season, week, entry_user.casefold()],
        "slate_report_ids": [report["report_id"] for report in reports],
        **({"historical_report_ids": [past["report_id"] for past in all_reports
                                      if past["report_id"] not in {report["report_id"] for report in reports}],
            "optimizer_correlation_aggregate": aggregate_correlations} if correlation_loader else {}),
        **({"weekly_stats": dict(weekly_stats)} if weekly_stats is not None else {}),
    })
    return {
        "format_results": typed_results,
        "report_id": "weekly-learning-report-" + str(uuid.uuid5(uuid.NAMESPACE_URL, evidence_hash)),
        "contract_id": "weekly_learning_report_v2" if correlation_loader else WEEKLY_LEARNING_REPORT_CONTRACT,
        "builder_version": LEARNING_REPORT_BUILDER_VERSION,
        "season": season,
        "week": week,
        "entry_user": entry_user,
        "generated_at": (generated_at or datetime.now(UTC)).isoformat(),
        "evidence_hash": evidence_hash,
        "status": "partial" if typed_results or any(report["status"] == "partial" for report in reports) else "completed",
        "summary": {
            "typed_contest_entries": sum(len(row['entries']) for row in typed_results),
            "typed_contest_groups": len(typed_results),
            "financial_scope": "Classic/Showdown only; typed standings carry no inferred fees/payouts",
            **({"weekly_stats": dict(weekly_stats)} if weekly_stats is not None else {}),
            "slates": len(reports),
            "contests_entered": len(observed_contests),
            "entries": len(entries),
            "identity_complete_entries": sum(report["summary"]["identity_complete_entries"] for report in reports),
            "matched_optimizer_entries": sum(report["summary"]["matched_optimizer_entries"] for report in reports),
            "entries_with_opt_007": sum(report["summary"]["entries_with_opt_007"] for report in reports),
            "duplicate_entries": sum(report["summary"]["duplicate_entries"] for report in reports),
            "entry_weighted_projection_observations": observation_count,
            "entry_weighted_projection_mae": (
                weighted_absolute_error / observation_count if observation_count else None
            ),
            "entry_weighted_projection_rmse": (
                math.sqrt(weighted_squared_error / observation_count) if observation_count else None
            ),
            "unique_projection_observations": unique_week_metrics["observations"],
            "unique_projection_mae": unique_week_metrics["mae"],
            "unique_projection_rmse": unique_week_metrics["rmse"],
            "unique_outcome_counts": weekly_outcome_counts,
            "total_amount_entered": entered,
            "total_returned": returned,
            "net_profit": returned - entered if financial_complete else None,
            "roi": (returned - entered) / entered if financial_complete and entered else None,
            "number_cashed": (sum(row["number_cashed"] for row in slate_financials)
                              if slate_financials and all(row.get("number_cashed") is not None for row in slate_financials) else None),
            "net_positive_slates": (
                sum(row["net_positive"] for row in slate_financials)
                if slate_financials and all(row["net_positive"] is not None for row in slate_financials) else None
            ),
            "net_positive_slate_frequency": (
                sum(row["net_positive"] for row in slate_financials) / len(slate_financials)
                if slate_financials and all(row["net_positive"] is not None for row in slate_financials) else None
            ),
        },
        "slate_reports": reports,
        "optimizer_effectiveness_history": optimizer_history,
        "optimizer_correlation_aggregate": aggregate_correlations,
        "source_file_ids": source_file_ids,
        "run_ids": {kind: sorted(values) for kind, values in sorted(run_ids.items())},
        "missing_evidence": sorted([
            f"{report['slate']}:{item}"
            for report in reports for item in report["missing_evidence"]
        ] + [f"{row['contest_format']}:{row['variant']}:{row['contest_id']}:component_reconstruction_and_forecast_origin_unverified" for row in typed_results]),
        "interpretation": (
            "The aggregate projection metrics weight each entered lineup player; repeated "
            "players are not independent model training observations. Import files and resolve "
            "identity gaps before evaluation. Model changes require separate chronological "
            "validation and promotion."
        ),
    }


class SlateLearningService:
    """Generate and retrieve immutable LEARN-001 reports."""

    def __init__(self, connection_string: str | None = None, engine: Engine | None = None) -> None:
        self.connection_string = connection_string or (
            str(engine.url) if engine is not None else get_connection_string()
        )
        self.engine = engine or create_engine(self.connection_string)

    def _ensure_schema(self) -> None:
        validate_target_schema(
            self.engine,
            consumer=type(self).__name__,
            required_tables=(
                "slate_learning_report", "dfs_contest", "dfs_contest_entry_result",
                "contest_ownership_observation", "optimizer_run", "lineup", "lineup_player",
                "human_belief", "lineup_portfolio", "contest_entry_assignment",
                "dk_upload_export", "dk_export_validation", "symbolic_rule_application",
                "belief_impact_preview", "belief_impact_decision",
                "agent_question", "agent_question_answer", "player_outcome_event",
                "slate_learning_run_detail", "dk_entry_history_snapshot", "evaluation_record",
            ),
        )

    def record_outcome_event(
        self, *, season: int, week: int, slate: str, player_id: str,
        tag: str, evidence: str, source_url: str, observed_at: datetime,
    ) -> str:
        """Append source-backed outcome attribution without modifying a projection."""
        tag = tag.upper().strip()
        if tag not in OUTCOME_TAGS:
            raise ValueError("Unsupported outcome tag")
        if not player_id.strip() or not evidence.strip() or not source_url.strip():
            raise ValueError("Player ID, evidence, and source URL are required")
        if _as_datetime(observed_at) is None:
            raise ValueError("observed_at must be a timestamp")
        self._ensure_schema()
        payload = [season, week, slate.upper(), player_id, tag, evidence, source_url,
                   _as_datetime(observed_at).isoformat()]
        event_id = "outcome-event-" + _canonical_hash(payload)[:32]
        with self.engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO target.player_outcome_event
                    (event_id, season, week, slate, player_id, tag, evidence, source_url, observed_at)
                VALUES (:event_id, :season, :week, :slate, :player_id, :tag, :evidence, :source_url, :observed_at)
                ON CONFLICT (event_id) DO NOTHING
            """), {"event_id": event_id, "season": season, "week": week, "slate": slate.upper(),
                    "player_id": player_id, "tag": tag, "evidence": evidence,
                    "source_url": source_url, "observed_at": _as_datetime(observed_at)})
        return event_id

    @staticmethod
    def _rows(connection, sql: str, params: Mapping[str, Any]) -> list[dict[str, Any]]:
        return [dict(row) for row in connection.execute(text(sql), dict(params)).mappings().all()]

    def _load_evidence(
        self, connection, *, season: int, week: int, slate: str, entry_user: str
    ) -> dict[str, list[dict[str, Any]]]:
        params = {"season": season, "week": week, "slate": slate.upper(), "entry_user": entry_user.casefold()}
        contests = self._rows(connection, """
            SELECT c.contest_id, c.contest_name, c.contest_format, c.contest_type,
                   c.entry_fee, c.field_size, c.max_entries_per_user, c.prize_pool,
                   c.source_file_id, source.content_sha256,
                   COUNT(entry.entry_id)::INT AS observed_entries,
                   (COUNT(entry.entry_id) = c.field_size) AS field_complete,
                   MAX(entry.entry_points) AS winning_points,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY entry.entry_points) AS median_points
            FROM target.dfs_contest c
            LEFT JOIN target.source_file_import source USING (source_file_id)
            LEFT JOIN target.dfs_contest_entry_result entry USING (contest_id)
            WHERE c.season=:season AND c.week=:week AND upper(c.slate_id)=:slate
            GROUP BY c.contest_id, source.content_sha256
            ORDER BY c.contest_id
        """, params)
        if not contests:
            raise ValueError("No normalized contest results exist for this slate")
        evidence = {
            "contests": contests,
            "entries": self._rows(connection, """
                SELECT entry.contest_id, entry.entry_id, entry.entry_name, entry.rank,
                       entry.entry_points, entry.lineup_text, entry.source_file_id, entry.ingested_at
                FROM target.dfs_contest_entry_result entry
                JOIN target.dfs_contest contest USING (contest_id)
                WHERE contest.season=:season AND contest.week=:week
                  AND upper(contest.slate_id)=:slate
                  AND lower(regexp_replace(coalesce(entry.entry_name,''), '\\s+\\([0-9]+/[0-9]+\\)$', ''))=:entry_user
                ORDER BY entry.contest_id, entry.rank, entry.entry_id
            """, params),
            "field_entries": self._rows(connection, """
                SELECT entry.contest_id, entry.entry_id, entry.rank,
                       entry.entry_points, entry.lineup_text
                FROM target.dfs_contest_entry_result entry
                JOIN target.dfs_contest contest USING (contest_id)
                WHERE contest.season=:season AND contest.week=:week
                  AND upper(contest.slate_id)=:slate
                ORDER BY entry.contest_id, entry.rank, entry.entry_id
            """, params),
            "salary_context": self._rows(connection, """
                SELECT player_id, roster_position, salary, team_id,
                       opponent_team_id, game_id, as_of
                FROM target.snapshot_salary
                WHERE season=:season AND week=:week AND upper(slate)=:slate
                  AND lower(site)='draftkings'
                ORDER BY player_id, roster_position, as_of
            """, params),
            "optimizer_runs": self._rows(connection, """
                SELECT optimizer_run_id, contest_format, strategy,
                       encode(sha256(convert_to(constraint_config_json::text, 'UTF8')), 'hex') AS configuration_hash,
                       pg_column_size(constraint_config_json) AS configuration_bytes, data_cutoff_at,
                       projection_run_id, created_at AS optimizer_created_at,
                       (SELECT jsonb_agg(DISTINCT p.player_json->>'game_id')
                        FROM target.lineup l JOIN target.lineup_player p USING(lineup_id)
                        WHERE l.optimizer_run_id=run.optimizer_run_id AND p.player_json ? 'game_id') AS saved_lineup_games
                FROM target.optimizer_run run
                WHERE season=:season AND week=:week AND upper(slate_id)=:slate
                  AND status='completed'
                ORDER BY created_at, optimizer_run_id
            """, params),
            "observations": self._rows(connection, """
                SELECT observation.*
                FROM target.contest_ownership_observation observation
                JOIN target.dfs_contest contest USING (contest_id)
                WHERE contest.season=:season AND contest.week=:week
                  AND upper(contest.slate_id)=:slate
                ORDER BY observation.recorded_at DESC, observation.observation_id
            """, params),
            "payout_tiers": self._rows(connection, """
                SELECT tier.* FROM target.dfs_contest_payout_tier tier
                JOIN target.dfs_contest contest USING (contest_id)
                WHERE contest.season=:season AND contest.week=:week
                  AND upper(contest.slate_id)=:slate
                ORDER BY tier.contest_id, tier.min_rank
            """, params),
            "cash_lines": self._rows(connection, """
                WITH paid_cutoff AS (
                    SELECT contest_id, MAX(max_rank) AS cash_rank
                    FROM target.dfs_contest_payout_tier
                    WHERE payout > 0
                    GROUP BY contest_id
                )
                SELECT contest.contest_id, MIN(result.entry_points) AS cash_line
                FROM target.dfs_contest contest
                JOIN paid_cutoff ON paid_cutoff.contest_id=contest.contest_id
                JOIN target.dfs_contest_entry_result result ON result.contest_id=contest.contest_id
                  AND result.rank=paid_cutoff.cash_rank
                WHERE contest.season=:season AND contest.week=:week
                  AND upper(contest.slate_id)=:slate
                GROUP BY contest.contest_id
            """, params),
            "lineup_players": self._rows(connection, """
                SELECT player.lineup_id, player.slot_index, player.roster_position, player.player_id,
                       player.projection,
                       encode(sha256(convert_to(player.player_json::text, 'UTF8')), 'hex') AS saved_player_hash,
                       coalesce((SELECT jsonb_object_agg(key, value) FROM jsonb_each(player.player_json)
                        WHERE key IN ('portfolio_game_script',
                                      'market_context_point_in_time_safe', 'player_team',
                                      'game_total_line', 'team_spread_line', 'team_implied_total')), '{}'::jsonb)
                       || CASE WHEN player.player_json ? 'lineup_control_comparison' THEN jsonb_build_object(
                            'lineup_control_comparison', (player.player_json->'lineup_control_comparison') - 'replay')
                          ELSE '{}'::jsonb END AS player_json,
                       lineup.lineup_number, lineup.projected_mean,
                       run.optimizer_run_id, run.projection_run_id, run.rule_run_id,
                       run.strategy, run.objective, run.contest_format,
                       run.data_cutoff_at, run.created_at AS optimizer_created_at
                FROM target.optimizer_run run
                JOIN target.lineup lineup USING (optimizer_run_id)
                JOIN target.lineup_player player USING (lineup_id)
                WHERE run.season=:season AND run.week=:week AND upper(run.slate_id)=:slate
                  AND run.status='completed'
                ORDER BY run.created_at, lineup.lineup_number, player.slot_index
            """, params),
            "assignments": self._rows(connection, """
                SELECT assignment.*, portfolio.optimizer_run_id
                FROM target.contest_entry_assignment assignment
                JOIN target.lineup_portfolio portfolio USING (portfolio_id)
                WHERE portfolio.season=:season AND portfolio.week=:week
                  AND upper(portfolio.slate_id)=:slate
            """, params),
            "portfolios": self._rows(connection, """
                SELECT portfolio.* FROM target.lineup_portfolio portfolio
                WHERE portfolio.season=:season AND portfolio.week=:week
                  AND upper(portfolio.slate_id)=:slate
            """, params),
            "exports": self._rows(connection, """
                SELECT export.export_id, export.portfolio_id, export.validation_id,
                       export.file_name, export.row_count, export.content_sha256,
                       export.created_at, validation.status AS validation_status,
                       validation.errors_json, validation.warnings_json
                FROM target.dk_upload_export export
                JOIN target.lineup_portfolio portfolio USING (portfolio_id)
                LEFT JOIN target.dk_export_validation validation USING (validation_id)
                WHERE portfolio.season=:season AND portfolio.week=:week
                  AND upper(portfolio.slate_id)=:slate
            """, params),
            "rule_applications": self._rows(connection, """
                SELECT DISTINCT application.*
                FROM target.symbolic_rule_application application
                JOIN target.optimizer_run run ON run.rule_run_id=application.rule_run_id
                WHERE run.season=:season AND run.week=:week AND upper(run.slate_id)=:slate
            """, params),
            "beliefs": self._rows(connection, """
                SELECT DISTINCT ON (belief_id) *
                FROM target.human_belief
                WHERE (season IS NULL OR season=:season)
                  AND (week IS NULL OR week=:week)
                  AND (slate IS NULL OR upper(slate)=:slate)
                ORDER BY belief_id, belief_version DESC
            """, params),
            "belief_impacts": self._rows(connection, """
                SELECT DISTINCT ON (preview.belief_version_id)
                       preview.preview_id, preview.belief_id, preview.belief_version_id,
                       preview.policy_id, preview.target_player_id,
                       preview.baseline_json, preview.proposed_json, preview.modifier_json,
                       decision.decision_id, decision.decision,
                       decision.approved_modifier_json,
                       decision.created_at AS decided_at,
                       preview.created_at
                FROM target.belief_impact_preview preview
                LEFT JOIN target.belief_impact_decision decision USING (preview_id)
                WHERE preview.season=:season AND preview.week=:week
                  AND (preview.slate IS NULL OR upper(preview.slate)=:slate)
                ORDER BY preview.belief_version_id, preview.created_at DESC
            """, params),
            "agent_questions": self._rows(connection, """
                SELECT question.question_id, question.policy_id, question.variant_set_id,
                       question.trigger_type, question.subject_player_id,
                       question.subject_label, question.question_text,
                       question.context_json, question.evidence_hash,
                       question.created_at, answer.answer_id, answer.answer,
                       answer.answer_text, answer.resulting_modifier_json,
                       answer.created_at AS answered_at
                FROM target.agent_question question
                LEFT JOIN target.agent_question_answer answer USING (question_id)
                WHERE question.season=:season AND question.week=:week
                  AND upper(question.slate)=:slate
                ORDER BY question.created_at, question.question_id
            """, params),
            "outcome_events": self._rows(connection, """
                SELECT DISTINCT ON (event.player_id)
                       event.player_id, event.tag, event.evidence, event.source_url,
                       event.observed_at, event.event_id
                FROM target.player_outcome_event event
                WHERE event.season=:season AND event.week=:week
                  AND upper(event.slate)=:slate
                ORDER BY event.player_id, event.observed_at DESC, event.event_id DESC
            """, params),
        }
        from .entry_history import load_history, enrich_contests
        history, conflicts, snapshots = load_history(connection)
        contest_ids = {str(c['contest_id']) for c in contests}
        evidence['entry_history'] = [row for row in history if row['contest_id'] in contest_ids]
        evidence['entry_history_conflicts'] = [key for key in conflicts if key[0] in contest_ids]
        evidence['entry_history_sources'] = [row['content_sha256'] for row in snapshots]
        evidence['contests'] = enrich_contests(contests, evidence['entry_history'])
        evidence['entry_candidate_lineage'] = self._rows(connection, """
            SELECT DISTINCT ON (record_json#>>'{payload,contest_id}',record_json#>>'{payload,entry_id}')
                (record_json->'payload')->>'contest_id' AS contest_id,
                (record_json->'payload')->>'entry_id' AS entry_id,
                record_json#>'{payload,matches}' AS matches
            FROM target.evaluation_record WHERE kind='entry_candidate_lineage'
                AND record_json#>>'{payload,season}'=CAST(:season AS TEXT)
                AND record_json#>>'{payload,week}'=CAST(:week AS TEXT)
                AND upper(record_json#>>'{payload,slate}')=:slate
            ORDER BY record_json#>>'{payload,contest_id}',record_json#>>'{payload,entry_id}',recorded_at DESC
        """, params)
        evidence['evaluation_records'] = self._rows(connection, """
            SELECT record.record_id,record.kind,record.optimizer_run_id,record.evidence_sha256,
                   record.recorded_at FROM target.evaluation_record record
            LEFT JOIN target.optimizer_run run USING(optimizer_run_id)
            WHERE (run.season=:season AND run.week=:week AND upper(run.slate_id)=:slate)
               OR (record.kind IN ('contest_evidence','scope_correction','contest_submission_snapshot')
                   AND record.record_json#>>'{payload,contest_id}' IN (
                       SELECT contest_id FROM target.dfs_contest WHERE season=:season AND week=:week
                       AND upper(slate_id)=:slate))
            ORDER BY record.recorded_at,record.record_id
        """, params)
        evidence['export_records'] = self._rows(connection, """
            SELECT record.record_id, record.kind, record.optimizer_run_id, record.recorded_at,
                   jsonb_build_object(
                       'filename', coalesce(record.record_json#>'{payload,filename}', to_jsonb(artifact.file_name)),
                       'export_id', record.record_json#>'{payload,export_id}',
                       'content_sha256', record.record_json#>'{payload,content_sha256}',
                       'rows', record.record_json#>'{payload,rows}',
                       'assignments', record.record_json#>'{payload,assignments}') AS payload
            FROM target.evaluation_record record JOIN target.optimizer_run run USING (optimizer_run_id)
            LEFT JOIN target.dk_upload_export artifact
              ON artifact.export_id=record.record_json#>>'{payload,export_id}'
            WHERE record.kind IN ('export', 'portfolio_export')
              AND run.season=:season AND run.week=:week AND upper(run.slate_id)=:slate
            ORDER BY record.recorded_at, record.record_id
        """, params)
        recommendations = self._rows(connection, """
            SELECT record.optimizer_run_id,record.recorded_at,record.record_json->'payload' AS payload
            FROM target.evaluation_record record JOIN target.optimizer_run run USING(optimizer_run_id)
            WHERE record.kind='recommendation' AND run.season=:season AND run.week=:week
              AND upper(run.slate_id)=:slate
        """, params)
        from .evaluation_record import prelock_recommendation_assignments
        evidence['recommendation_assignments'] = prelock_recommendation_assignments(recommendations)
        return evidence

    def _load_optimizer_config(self, connection, run_id: str, expected_hash: str) -> dict[str, Any]:
        row = connection.execute(text("""
            SELECT encode(sha256(convert_to(constraint_config_json::text, 'UTF8')), 'hex') AS configuration_hash,
                jsonb_build_object(
                    'ownership_run_id', constraint_config_json->'ownership_run_id',
                    'effective_strategy_contract', constraint_config_json->'effective_strategy_contract',
                    'showdown_evidence_snapshot', jsonb_build_object('frozen_at', constraint_config_json#>'{showdown_evidence_snapshot,frozen_at}', 'player_pool', (
                        SELECT coalesce(jsonb_agg(jsonb_build_object('game_id', p->'game_id')), '[]'::jsonb)
                        FROM jsonb_array_elements(coalesce(constraint_config_json#>'{showdown_evidence_snapshot,player_pool}', '[]'::jsonb)) p)),
                    'correlation_profile', constraint_config_json->'correlation_profile',
                    'strategy_runtime', jsonb_build_object(
                        'candidate_pool_manifest', constraint_config_json#>'{strategy_runtime,candidate_pool_manifest}',
                        'football_analyst', jsonb_build_object(
                            'candidates', constraint_config_json#>'{strategy_runtime,football_analyst,candidates}',
                            'input_snapshot_sha256', constraint_config_json#>'{strategy_runtime,football_analyst,input_snapshot_sha256}',
                            'input_snapshot', jsonb_build_object('players', (
                                SELECT coalesce(jsonb_agg(jsonb_build_object('player_id', p->'player_id', 'projection', p->'projection',
                                    'p90', p->'p90', 'salary', p->'salary', 'game_id', p->'game_id')), '[]'::jsonb)
                                FROM jsonb_array_elements(coalesce(constraint_config_json#>'{strategy_runtime,football_analyst,input_snapshot,players}', '[]'::jsonb)) p))
                        ),
                        'classic_run_input_snapshot', jsonb_build_object('payload', jsonb_build_object('metadata', constraint_config_json#>'{strategy_runtime,classic_run_input_snapshot,payload,metadata}')),
                        'single_lineup', jsonb_build_object('all_candidates', constraint_config_json#>'{strategy_runtime,single_lineup,all_candidates}'),
                        'strategy_contract_audit', jsonb_build_object('candidate_rosters', constraint_config_json#>'{strategy_runtime,strategy_contract_audit,candidate_rosters}'),
                        'classic_small_field', jsonb_build_object('all_candidates', constraint_config_json#>'{strategy_runtime,classic_small_field,all_candidates}'),
                        'single_entry', jsonb_build_object('all_candidates', constraint_config_json#>'{strategy_runtime,single_entry,all_candidates}'),
                        'three_max', jsonb_build_object('all_candidates', constraint_config_json#>'{strategy_runtime,three_max,all_candidates}'),
                        'small_max', jsonb_build_object('all_candidates', constraint_config_json#>'{strategy_runtime,small_max,all_candidates}'),
                        'showdown_portfolio_policy', jsonb_build_object('candidate_selection', jsonb_build_object(
                            'ranked_metrics', constraint_config_json#>'{strategy_runtime,showdown_portfolio_policy,candidate_selection,ranked_metrics}',
                            'selected_ranks', constraint_config_json#>'{strategy_runtime,showdown_portfolio_policy,candidate_selection,selected_ranks}',
                            'omission_reasons', constraint_config_json#>'{strategy_runtime,showdown_portfolio_policy,candidate_selection,omission_reasons}'
                        ))
                    )
                )::text AS config
            FROM target.optimizer_run WHERE optimizer_run_id=:run_id AND status='completed'
        """), {"run_id": run_id}).mappings().one()
        raw = row["config"]
        if row["configuration_hash"] != expected_hash:
            raise ValueError("Saved optimizer evidence changed during learning generation; retry the report")
        return {"constraint_config_json": json.loads(raw)}

    def _store_run_detail(self, connection, evaluated: Mapping[str, Any]) -> dict[str, Any]:
        payload = _json_value(dict(evaluated))
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        detail_id = "learning-detail-" + digest
        samples = correlation_samples(evaluated.get("candidates", []))
        connection.execute(text("""
            INSERT INTO target.slate_learning_run_detail
                (detail_id, optimizer_run_id, evidence_hash, candidate_count, detail_json, correlation_samples_json)
            VALUES (:detail_id, :run_id, :hash, :count, CAST(:detail AS JSONB), CAST(:samples AS JSONB))
            ON CONFLICT (detail_id) DO NOTHING
        """), {"detail_id": detail_id, "run_id": evaluated["optimizer_run_id"], "hash": digest,
                "count": len(samples), "detail": encoded, "samples": json.dumps(samples, default=str)})
        return {"detail_id": detail_id, "evidence_hash": digest, "candidate_count": len(samples),
                "representation": "immutable_paginated_candidates_v1"}

    def generate(self, *, season: int, week: int, slate: str, entry_user: str,
                 diagnostic_run_ids: Iterable[str] = ()) -> dict[str, Any]:
        slate = str(slate or "").strip().upper()
        entry_user = str(entry_user or "").strip()
        if not slate:
            raise ValueError("slate is required")
        if not entry_user:
            raise ValueError("entry_user is required")
        self._ensure_schema()
        started = monotonic()
        with self.engine.begin() as connection:
            evidence = self._load_evidence(
                connection, season=season, week=week, slate=slate, entry_user=entry_user
            )
            loaded_at = monotonic()
            run_metadata = {str(row["optimizer_run_id"]): row for row in evidence["optimizer_runs"]}
            loaded_run_ids = []
            def load_run(run_id):
                loaded_run_ids.append(run_id)
                return self._load_optimizer_config(connection, run_id, run_metadata[run_id]["configuration_hash"])
            report = build_slate_learning_report(
                season=season, week=week, slate=slate, entry_user=entry_user, evidence=evidence,
                run_loader=load_run, detail_sink=lambda run: self._store_run_detail(connection, run),
                diagnostic_run_ids=diagnostic_run_ids,
            )
            del evidence
            for entry in report["entries"]:
                if not entry.get("optimizer_run_id") or not entry.get("lineup_id"):
                    continue
                payload = connection.execute(text("""
                    SELECT jsonb_build_object('decision_snapshot', run.constraint_config_json->'decision_snapshot',
                                              'opt_007_control', (
                        SELECT player_json->'lineup_control_comparison' FROM target.lineup_player
                        WHERE lineup_id=:lineup_id AND player_json ? 'lineup_control_comparison'
                        ORDER BY slot_index LIMIT 1)) AS evidence
                    FROM target.optimizer_run run WHERE optimizer_run_id=:run_id
                """), {"lineup_id": entry["lineup_id"], "run_id": entry["optimizer_run_id"]}).scalar_one()
                payload["submission_evidence"] = entry["submission_evidence"]
                entry["entry_evidence"] = self._store_run_detail(connection, {
                    "optimizer_run_id": entry["optimizer_run_id"], "entry_evidence": payload,
                })
                entry["entry_evidence"].update({"representation": "immutable_entry_evidence_v1",
                    "url": f"/api/learning/reports/{report['report_id']}/entries/{entry['entry_id']}/evidence?contest_id={entry['contest_id']}"})
                entry["decision_snapshot"] = None
                del payload
            for run in report["optimizer_effectiveness"]["runs"]:
                if "candidate_detail" in run:
                    run["candidate_detail"]["url"] = (
                        f"/api/learning/reports/{report['report_id']}/optimizer-runs/{run['optimizer_run_id']}/candidates"
                    )
            peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            report["telemetry"] = {
                "contract_id": "learning_memory_telemetry_v1", "metadata_load_seconds": loaded_at - started,
                "build_seconds": monotonic() - loaded_at, "loaded_configuration_count": len(loaded_run_ids),
                "completed_configuration_bytes": sum(row["configuration_bytes"] for row in run_metadata.values()),
                "loaded_configuration_bytes": sum(run_metadata[run_id]["configuration_bytes"] for run_id in loaded_run_ids),
                "candidate_count": sum(run.get("generated_count", 0) for run in report["optimizer_effectiveness"]["runs"]),
                "process_lifetime_peak_rss_bytes": peak if sys.platform == "darwin" else peak * 1024,
                "peak_rss_budget_bytes": 1_000_000_000, "response_budget_bytes": 2_000_000,
            }
            report["telemetry"]["serialized_report_bytes"] = len(json.dumps(report, default=str).encode())
            logging.getLogger(__name__).info("Learning report memory: %s", json.dumps(report["telemetry"]))
            if report["telemetry"]["serialized_report_bytes"] > report["telemetry"]["response_budget_bytes"]:
                logging.getLogger(__name__).warning("Learning report %s exceeds compact response budget", report["report_id"])
            if report["telemetry"]["process_lifetime_peak_rss_bytes"] > report["telemetry"]["peak_rss_budget_bytes"]:
                logging.getLogger(__name__).warning("Learning process lifetime peak exceeds RSS budget; confirm in a fresh benchmark")
            connection.execute(text("""
                INSERT INTO target.slate_learning_report
                    (report_id, contract_id, season, week, slate, entry_user,
                     evidence_hash, status, source_file_ids_json, run_ids_json, report_json)
                VALUES
                    (:report_id, :contract_id, :season, :week, :slate, :entry_user,
                     :evidence_hash, :status, CAST(:source_file_ids AS JSONB),
                     CAST(:run_ids AS JSONB), CAST(:report AS JSONB))
                ON CONFLICT (report_id) DO NOTHING
            """), {
                "report_id": report["report_id"], "contract_id": report["contract_id"],
                "season": season, "week": week, "slate": slate, "entry_user": entry_user,
                "evidence_hash": report["evidence_hash"], "status": report["status"],
                "source_file_ids": json.dumps(report["source_file_ids"], sort_keys=True),
                "run_ids": json.dumps(report["run_ids"], sort_keys=True),
                "report": json.dumps(report, sort_keys=True, default=str),
            })
            stored = connection.execute(text("""
                SELECT report_json FROM target.slate_learning_report
                WHERE report_id=:report_id
            """), {"report_id": report["report_id"]}).mappings().one()
        return dict(stored["report_json"])

    def candidate_detail(self, report_id: str, run_id: str, *, offset: int = 0, limit: int = 100) -> dict[str, Any] | None:
        """Read frozen postgame evidence, including legacy v1 reports; never rescore current data."""
        if offset < 0 or not 1 <= limit <= 200:
            raise ValueError("Candidate pages require offset >= 0 and limit between 1 and 200")
        with self.engine.connect() as connection:
            rows = self._rows(connection, """
                WITH source AS (
                    SELECT run.value - 'candidates' - 'candidate_preview' AS summary,
                           coalesce(detail.detail_json->'candidates', run.value->'candidates', '[]'::jsonb) AS candidates,
                           run.value->'candidate_detail'->>'detail_id' IS NOT NULL AND detail.detail_id IS NULL AS detail_missing
                    FROM target.slate_learning_report report
                    CROSS JOIN LATERAL jsonb_array_elements(report.report_json->'optimizer_effectiveness'->'runs') run(value)
                    LEFT JOIN target.slate_learning_run_detail detail
                      ON detail.detail_id=run.value->'candidate_detail'->>'detail_id'
                    WHERE report.report_id=:report_id AND run.value->>'optimizer_run_id'=:run_id
                )
                SELECT summary, detail_missing, jsonb_array_length(candidates) AS total,
                       coalesce((SELECT jsonb_agg(page.value ORDER BY page.ordinality)
                           FROM jsonb_array_elements(candidates) WITH ORDINALITY page(value, ordinality)
                           WHERE page.ordinality > :offset AND page.ordinality <= :offset + :limit), '[]'::jsonb) AS rows
                FROM source
            """, {"report_id": report_id, "run_id": run_id, "offset": offset, "limit": limit})
            if not rows:
                return None
        row = rows[0]
        if row["detail_missing"]:
            raise ValueError("Frozen learning candidate evidence is missing")
        return {"contract_id": "learning_candidate_page_v1", "report_id": report_id,
                "optimizer_run_id": run_id, "evidence_hash": row["summary"].get("candidate_detail", {}).get("evidence_hash"),
                "offset": offset, "limit": limit, "total": row["total"], "rows": row["rows"],
                "next_offset": offset + limit if offset + limit < row["total"] else None}

    def entry_detail(self, report_id: str, entry_id: str, contest_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            rows = self._rows(connection, """
                SELECT coalesce(detail.detail_json->'entry_evidence', jsonb_build_object(
                    'decision_snapshot', entry.value->'decision_snapshot',
                    'opt_007_control', entry.value->'opt_007_control',
                    'submission_evidence', entry.value->'submission_evidence')) AS evidence,
                    entry.value->'entry_evidence'->>'evidence_hash' AS evidence_hash,
                    entry.value->'entry_evidence'->>'detail_id' IS NOT NULL AND detail.detail_id IS NULL AS detail_missing
                FROM target.slate_learning_report report
                CROSS JOIN LATERAL jsonb_array_elements(report.report_json->'entries') entry(value)
                LEFT JOIN target.slate_learning_run_detail detail
                  ON detail.detail_id=entry.value->'entry_evidence'->>'detail_id'
                WHERE report.report_id=:report_id AND entry.value->>'entry_id'=:entry_id
                  AND entry.value->>'contest_id'=:contest_id
            """, {"report_id": report_id, "entry_id": entry_id, "contest_id": contest_id})
        if not rows:
            return None
        if rows[0].pop("detail_missing"):
            raise ValueError("Frozen learning entry evidence is missing")
        return {"report_id": report_id, "entry_id": entry_id, "contest_id": contest_id, **rows[0]}

    def _correlation_samples(self, report: Mapping[str, Any], run: Mapping[str, Any]) -> list[dict[str, Any]]:
        if "candidates" in run:
            return correlation_samples(run["candidates"])
        with self.engine.connect() as connection:
            detail_id = (run.get("candidate_detail") or {}).get("detail_id")
            if detail_id:
                rows = self._rows(connection, """
                    SELECT correlation_samples_json AS samples FROM target.slate_learning_run_detail
                    WHERE detail_id=:detail_id
                """, {"detail_id": detail_id})
                if not rows:
                    raise ValueError("Frozen learning correlation evidence is missing")
                return rows[0]["samples"]
            rows = self._rows(connection, """
                SELECT jsonb_build_object('pregame', jsonb_build_object(
                    'mean', candidate.value->'pregame'->'mean', 'p90', candidate.value->'pregame'->'p90',
                    'objective_score', candidate.value->'pregame'->'objective_score',
                    'ownership_sum', candidate.value->'pregame'->'ownership_sum',
                    'leverage_sum', candidate.value->'pregame'->'leverage_sum',
                    'correlation_adjustment', candidate.value->'pregame'->'correlation_adjustment',
                    'context_adjustment', candidate.value->'pregame'->'context_adjustment'),
                    'postgame', jsonb_build_object('actual_points', candidate.value->'postgame'->'actual_points')) AS sample
                FROM target.slate_learning_report report
                CROSS JOIN LATERAL jsonb_array_elements(report.report_json->'optimizer_effectiveness'->'runs') run(value)
                CROSS JOIN LATERAL jsonb_array_elements(run.value->'candidates') WITH ORDINALITY candidate(value, ordinality)
                WHERE report.report_id=:report_id AND run.value->>'optimizer_run_id'=:run_id
                ORDER BY candidate.ordinality
            """, {"report_id": report["report_id"], "run_id": run["optimizer_run_id"]})
            return [row["sample"] for row in rows]

    def _refresh_weekly_stats(self, *, season: int, week: int) -> dict[str, Any]:
        """Archive and ingest the report week's published stats before evaluation."""
        try:
            with Session(self.engine) as session:
                capture_service = SourceCaptureService(session)
                capture = capture_nflreadpy_datasets(
                    capture_service, ["weekly_stats"], season=season, week=week,
                    slate=None, slate_lock_at=None, source_license=DEFAULT_NFLREADPY_LICENSE,
                )[0]
                if not capture.snapshot.row_count:
                    raise ValueError("No weekly stats are published for this week yet")
                result = IngestService(session).ingest_nflreadpy_weekly_stats(
                    NflReadPySeasonRequest(season=season, weeks=[week]),
                    source_frame=pd.read_csv(capture.snapshot.artifact_path),
                    source_path=capture.snapshot.artifact_path,
                    ingest_run_id=_ingest_run_id(capture.snapshot.snapshot_id),
                )
                capture_service.link_ingest_run(capture.snapshot.snapshot_id, result.ingest_run_id)
                if result.status != "completed":
                    raise ValueError(result.error_message or "Weekly stats ingest failed")
                return {
                    "status": result.status, "season": season, "week": week,
                    "rows_raw": result.rows_raw, "rows_curated": result.rows_curated,
                    "rows_unresolved": result.rows_unresolved,
                    "snapshot_id": capture.snapshot.snapshot_id,
                    "content_sha256": capture.snapshot.content_sha256,
                    "observed_at": capture.snapshot.observed_at.isoformat(),
                    "ingest_run_id": result.ingest_run_id,
                }
        except Exception as exc:
            raise ValueError(
                f"Weekly stats refresh failed for season {season}, week {week}: {exc}"
            ) from exc

    def generate_week(self, *, season: int, week: int, entry_user: str) -> dict[str, Any]:
        started = monotonic()
        entry_user = str(entry_user or "").strip()
        if not entry_user:
            raise ValueError("entry_user is required")
        self._ensure_schema()
        with self.engine.connect() as connection:
            slates = self._rows(connection, """
                SELECT DISTINCT upper(contest.slate_id) AS slate
                FROM target.dfs_contest contest
                JOIN target.dfs_contest_entry_result entry USING (contest_id)
                WHERE contest.season=:season AND contest.week=:week
                  AND lower(regexp_replace(coalesce(entry.entry_name,''),
                      '\\s+\\([0-9]+/[0-9]+\\)$', ''))=:entry_user
                ORDER BY slate
            """, {"season": season, "week": week, "entry_user": entry_user.casefold()})
        from .special_contest_results import learning_groups
        typed_results = learning_groups(season=season,week=week,entry_user=entry_user)
        if not slates and not typed_results:
            raise ValueError("No imported contest results exist for this user and week")
        weekly_stats = self._refresh_weekly_stats(season=season, week=week) if slates else None
        reports = [
            self.generate(season=season, week=week, slate=row["slate"], entry_user=entry_user)
            for row in slates
        ]
        with self.engine.connect() as connection:
            history = self._rows(connection, """
                SELECT DISTINCT ON (season, week, upper(slate)) jsonb_build_object(
                    'report_id', report_id, 'season', season, 'week', week, 'slate', slate,
                    'optimizer_effectiveness', jsonb_build_object('runs', (
                        SELECT coalesce(jsonb_agg(run.value - 'candidates' - 'candidate_preview'), '[]'::jsonb)
                        FROM jsonb_array_elements(report_json->'optimizer_effectiveness'->'runs') run(value)
                        WHERE coalesce(run.value->>'run_scope', 'entry_linked')='entry_linked'
                    ))) AS report_json
                FROM target.slate_learning_report
                WHERE lower(entry_user)=:entry_user
                  AND (season < :season OR (season=:season AND week < :week))
                  AND report_json ? 'optimizer_effectiveness'
                ORDER BY season, week, upper(slate), created_at DESC, report_id DESC
            """, {"entry_user": entry_user.casefold(), "season": season, "week": week})
        report = build_weekly_learning_report(
            season=season, week=week, entry_user=entry_user, slate_reports=reports,
            historical_slate_reports=[row["report_json"] for row in history],
            weekly_stats=weekly_stats,
            correlation_loader=self._correlation_samples,
            format_results=typed_results,
        )
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        report["telemetry"] = {
            "contract_id": "learning_memory_telemetry_v1", "elapsed_seconds": monotonic() - started,
            "process_lifetime_peak_rss_bytes": peak if sys.platform == "darwin" else peak * 1024,
            "loaded_configuration_count": sum(row["telemetry"]["loaded_configuration_count"] for row in reports),
            "candidate_count": sum(row["telemetry"]["candidate_count"] for row in reports),
            "peak_rss_budget_bytes": 1_000_000_000, "response_budget_bytes": 2_000_000,
            "request_duration_budget_seconds": 60,
        }
        report["telemetry"]["serialized_report_bytes"] = len(json.dumps(report, default=str).encode())
        logging.getLogger(__name__).info("Weekly learning report memory: %s", json.dumps(report["telemetry"]))
        if (report["telemetry"]["serialized_report_bytes"] > 2_000_000
                or report["telemetry"]["elapsed_seconds"] > 60):
            logging.getLogger(__name__).warning("Weekly learning report %s exceeds response or duration budget", report["report_id"])
        from .weekly_learning_library import save_report
        save_report(report)
        return report

    def latest(self, *, season: int, week: int, slate: str, entry_user: str) -> dict[str, Any] | None:
        self._ensure_schema()
        with self.engine.connect() as connection:
            row = connection.execute(text("""
                SELECT report_json FROM target.slate_learning_report
                WHERE season=:season AND week=:week AND upper(slate)=:slate
                  AND lower(entry_user)=:entry_user
                ORDER BY created_at DESC, report_id DESC LIMIT 1
            """), {
                "season": season, "week": week, "slate": slate.upper(),
                "entry_user": entry_user.casefold(),
            }).mappings().first()
        return dict(row["report_json"]) if row else None
