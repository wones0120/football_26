"""Auditable post-slate learning reports from normalized contest evidence."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
import hashlib
import json
import math
import re
import uuid
from typing import Any, Iterable, Mapping

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from Database.config import get_connection_string

from .target_schema import validate_target_schema


LEARNING_REPORT_CONTRACT = "slate_learning_report_v1"
LEARNING_REPORT_BUILDER_VERSION = "2026-09-14.4"
LEARNING_EFFECT_TOLERANCE = 0.25
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
    encoded = json.dumps(
        _json_value(payload), sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


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
) -> dict[str, Any]:
    """Build one report without inventing missing identity or lineage evidence."""
    generated = generated_at or datetime.now(UTC)
    contests = [dict(row) for row in evidence.get("contests", [])]
    entries = [dict(row) for row in evidence.get("entries", [])]
    observations = [dict(row) for row in evidence.get("observations", [])]
    lineup_players = [dict(row) for row in evidence.get("lineup_players", [])]
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
        assignment = assigned.get((contest_id, str(entry["entry_id"])))
        if assignment:
            candidate_id = str(assignment["lineup_id"])
            candidate = saved_by_lineup.get(candidate_id, [])
            if identity_complete and candidate and _signature(candidate) == _signature(resolved_players):
                matched_lineup_id = candidate_id
                match_basis = "contest_entry_assignment"
            else:
                missing.add(f"entry:{contest_id}:{entry['entry_id']}:assignment_signature_conflict")
        elif identity_complete:
            missing.add(f"entry:{contest_id}:{entry['entry_id']}:contest_entry_assignment")
            candidates = signature_matches.get(_signature(resolved_players), [])
            if candidates:
                candidates.sort(
                    key=lambda lineup_id: str(saved_by_lineup[lineup_id][0].get("optimizer_created_at") or ""),
                    reverse=True,
                )
                matched_lineup_id = candidates[0]
                match_basis = "canonical_lineup_signature"

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
                    "rule_evaluations": rule_results,
                }
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
        financial = {
            "entry_fee": fee,
            "payout": payout,
            "profit": payout - fee if payout is not None and fee is not None else None,
            "roi": (payout - fee) / fee if payout is not None and fee not in {None, 0} else None,
            "status": "complete" if payout is not None and fee is not None else "missing_fee_or_payout_evidence",
        }
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
                "opt_007_control": control,
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

    belief_reports = []
    residuals_by_player = defaultdict(list)
    for entry in entry_reports:
        for player in entry["players"]:
            actual_base = _number(player.get("actual_base_points"))
            projected_base = _number(player.get("projected_base_points"))
            if actual_base is not None and projected_base is not None:
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
        if impact_timing != "predecision":
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
                "is_retrospective": bool(belief.get("is_retrospective")),
                "timing_status": timing_status,
                "evaluation": score,
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
        if timing_status != "predecision" or answer == "no_change":
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
    report = {
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
            "matched_optimizer_entries": sum(entry["lineup_id"] is not None for entry in entry_reports),
            "entries_with_opt_007": sum(entry["opt_007_control"] is not None for entry in entry_reports),
            "duplicate_entries": duplicate_entries,
            "projection_player_observations": len(projection_errors),
            "projection_mae": _mean(projection_errors),
            "projection_rmse": (
                math.sqrt(_mean(squared_errors)) if squared_errors else None
            ),
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
    }
    report["evidence_hash"] = _canonical_hash(
        {
            "builder_version": LEARNING_REPORT_BUILDER_VERSION,
            "scope": [season, week, slate.upper(), entry_user.casefold()],
            "contests": contests,
            "entries": entries,
            "observations": observations,
            "lineup_players": lineup_players,
            "assignments": assignments,
            "portfolios": portfolios,
            "exports": exports,
            "rule_applications": rule_applications,
            "beliefs": beliefs,
            "belief_impacts": belief_impacts,
            "agent_questions": agent_questions,
            "payout_tiers": evidence.get("payout_tiers", []),
        }
    )
    report["report_id"] = "learning-report-" + str(
        uuid.uuid5(uuid.NAMESPACE_URL, report["evidence_hash"])
    )
    return report


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
                "agent_question", "agent_question_answer",
            ),
        )

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
            "lineup_players": self._rows(connection, """
                SELECT player.*, lineup.lineup_number, lineup.projected_mean,
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
        }
        return evidence

    def generate(self, *, season: int, week: int, slate: str, entry_user: str) -> dict[str, Any]:
        slate = str(slate or "").strip().upper()
        entry_user = str(entry_user or "").strip()
        if not slate:
            raise ValueError("slate is required")
        if not entry_user:
            raise ValueError("entry_user is required")
        self._ensure_schema()
        with self.engine.begin() as connection:
            evidence = self._load_evidence(
                connection, season=season, week=week, slate=slate, entry_user=entry_user
            )
            report = build_slate_learning_report(
                season=season, week=week, slate=slate, entry_user=entry_user, evidence=evidence
            )
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
