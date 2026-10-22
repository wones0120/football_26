"""Read-only workload evidence contract shared by Classic and Showdown.

Consumes the already selected, cutoff-filtered projection/context inputs. Never
queries history, creates forecasts, or participates in eligibility/scoring.
"""
from __future__ import annotations

from datetime import datetime
import math
from collections.abc import Mapping

import pandas as pd

CONTRACT_ID = "workload_evidence_v2"
SUPPORTED_CONTRACT_IDS = frozenset({"workload_evidence_v1", CONTRACT_ID})
ORIGINAL_HISTORY_FIELDS = {key: "pregame_base_" + key for key in (
    "targets_mean_3", "carries_mean_3", "target_share_mean_3", "carry_share_mean_3")}
HISTORICAL_FIELDS = (
    "snap_share_mean_3", "snap_share_last", "snap_share_prior3", "snap_share_trend",
    "targets_mean_3", "carries_mean_3", "target_share_mean_3", "carry_share_mean_3",
    "target_share_last", "target_share_prior3", "target_share_trend",
    "rush_share_last", "rush_share_prior3", "rush_share_trend",
)
PROXY_FIELDS = ("projected_targets", "projected_carries")
FORECAST_FIELDS = (
    "pregame_expected_snaps", "pregame_expected_routes", "pregame_expected_targets",
    "pregame_expected_carries", "pregame_target_share", "pregame_carry_share",
    "pregame_red_zone_share", "pregame_goal_line_share",
)
COVERAGE_FIELDS = (
    "opportunity_allocation_policy", "opportunity_history_team", "opportunity_history_status",
    "opportunity_history_observed_games", "opportunity_history_window",
)
LINEAGE_FIELDS = (
    "workload_feature_run_id", "workload_feature_cutoff_at", "pregame_context_run_id",
    "pregame_context_row_id", "pregame_context_source", "pregame_context_observed_at", "expected_workload_status",
    "expected_workload_observed_at", "projected_opportunity_source",
    "availability_source", "availability_observed_at", "availability_source_ids",
    "role_source", "role_observed_at", "role_source_ids",
)
# Only these small feature values are carried through optimizer SQL. No new
# sources and no full feature grids duplicated across candidates.
FEATURE_FIELDS = tuple(dict.fromkeys((
    'pregame_base_targets_mean_3', 'pregame_base_carries_mean_3',
    'pregame_base_target_share_mean_3', 'pregame_base_carry_share_mean_3',
    'expected_workload_source_ids',
    *HISTORICAL_FIELDS, *(f"{key}_available" for key in HISTORICAL_FIELDS if key.endswith("mean_3")),
    *PROXY_FIELDS, *FORECAST_FIELDS, *COVERAGE_FIELDS, *LINEAGE_FIELDS,
    "team_targets_mean_3", "team_targets_mean_3_available",
    "team_carries_mean_3", "team_carries_mean_3_available",
    "offensive_role_confidence", "offensive_role_source", "pregame_role_uncertain",
)))


def _safe(value):
    if isinstance(value, Mapping):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    if value is None or pd.isna(value):
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value if isinstance(value, (str, int, float, bool)) else str(value)


def _after_cutoff(clock, cutoff):
    if clock is None or cutoff is None:
        return False
    try:
        return pd.to_datetime(clock, utc=True) > pd.to_datetime(cutoff, utc=True)
    except (ValueError, TypeError):
        return False


def build_workload_evidence(row: Mapping, *, projection_run_id=None, cutoff=None) -> dict:
    """Preserve observations, zero-fill, proxies and explicit inputs separately.

    Availability flags are authoritative. Missing flags never prove measurement,
    even when a historical feature has a numeric value. Caller-supplied rows must
    come from the existing point-in-time loader, not reconstructed current data.
    """
    features = row.get("workload_feature_evidence")
    facts = dict(features) if isinstance(features, Mapping) else {}
    facts.update({k: v for k, v in row.items() if k != "workload_feature_evidence"})
    facts = _safe(facts)
    # Availability refresh can replace the containing context clock while
    # leaving projection-time expected workload intact. Keep its original
    # feature-snapshot attribution separate instead of renewing the forecast.
    forecast_lineage = _safe({key: features.get(key) if isinstance(features, Mapping) else facts.get(key)
                             for key in ("pregame_context_run_id", "pregame_context_row_id",
                                         "pregame_context_source", "pregame_context_observed_at",
                                         "expected_workload_observed_at")})
    position = str(facts.get("position") or "").upper()
    applicable = position in {"QB", "RB", "WR", "TE"}
    applicability = "applicable" if applicable else "not_applicable" if position in {"DST", "DEF", "K", "PK"} else "unknown_position"
    historical_future = _after_cutoff(facts.get("workload_feature_cutoff_at"), cutoff)
    forecast_future = any(_after_cutoff(forecast_lineage.get(k) or facts.get(k), cutoff) for k in (
        "pregame_context_observed_at", "expected_workload_observed_at"))

    def metric(key, *, observed=False, future=False, source_key=None, values=None):
        raw = (facts if values is None else values).get(source_key or key)
        flag_key = key + "_available"
        # Trends inherit their corresponding historical mean's measurement flag.
        if key.startswith("snap_share_"):
            flag_key = "snap_share_mean_3_available"
        elif key.startswith("target_share_"):
            flag_key = "target_share_mean_3_available"
        elif key.startswith("rush_share_"):
            flag_key = "carry_share_mean_3_available"
        flag = facts.get(flag_key)
        available = flag if isinstance(flag, bool) else None
        status = (applicability if not applicable else "after_cutoff" if future else
                  "unavailable" if raw is None or (observed and available is False) else
                  "coverage_unknown" if observed and available is None else
                  "observed" if observed else "present")
        return {"value": raw if applicable and not future and not (observed and available is False) else None,
                "status": status, "available": available if observed else None,
                "stored_value": raw if applicable and not future else None}

    historical = {}
    for key in HISTORICAL_FIELDS:
        source_key = ORIGINAL_HISTORY_FIELDS.get(key, key)
        item = metric(key, observed=True, future=historical_future, source_key=source_key)
        if key in ORIGINAL_HISTORY_FIELDS and facts.get(source_key) is None and applicable and not historical_future:
            item.update(value=None, status="original_history_unavailable")
        historical[key] = {**item, "evidence_kind": "observed_history", "source_field": source_key}
    forecasts = {key: {**metric(key, future=forecast_future,
        values=features if isinstance(features, Mapping) and key in features else None),
        "evidence_kind": "explicit_pregame_input", "source_field": key,
        "producer_source": forecast_lineage.get("pregame_context_source"),
        "producer_observed_at": forecast_lineage.get("expected_workload_observed_at")
            or forecast_lineage.get("pregame_context_observed_at")}
        for key in FORECAST_FIELDS}
    proxies = {key: {**metric(key, future=historical_future),
        "evidence_kind": "allocated_proxy", "source_field": key} for key in PROXY_FIELDS}
    for key in ORIGINAL_HISTORY_FIELDS:
        proxies["allocated_" + key.removesuffix("_mean_3")] = {
            **metric(key, future=historical_future), "evidence_kind": "allocated_proxy", "source_field": key}
    supported = any(value["status"] == "observed" for value in historical.values())
    present = any(value["value"] is not None for group in (historical, forecasts, proxies) for value in group.values())
    return {
        "contract_id": CONTRACT_ID,
        "measurement_semantics": {"historical": "original pre-allocation observations; missing original values remain unknown",
            "derived_proxies": "allocated counts/shares, not independently calibrated workload forecasts",
            "explicit_pregame": "producer-attributed inputs, never filled from history or allocation"},
        "player_id": str(facts.get("player_id") or facts.get("player_master_id") or ""),
        "applicability": applicability,
        "status": applicability if not applicable else "supported_history" if supported else "partial_evidence" if present else "unavailable",
        "historical": historical,
        "historical_coverage": {key: facts.get(key) for key in COVERAGE_FIELDS},
        "existing_assessment": {key: facts.get(key) for key in (
            "offensive_role_confidence", "offensive_role_source", "pregame_role_uncertain")},
        "derived_proxies": proxies,
        "explicit_pregame": forecasts,
        "explicit_pregame_lineage": forecast_lineage,
        "availability_depth": {key: facts.get(key) for key in (
            "roster_status", "player_status", "official_availability_status", "depth_chart_position",
            "pregame_role_label", "pregame_availability_probability", "pregame_start_probability")},
        "team_volume_proxies": {key: metric(key, observed=True, future=historical_future) for key in (
            "team_targets_mean_3", "team_carries_mean_3")},
        "lineage": {"projection_run_id": _safe(projection_run_id), "evidence_cutoff_at": _safe(cutoff),
                    **{key: facts.get(key) for key in LINEAGE_FIELDS}},
        "limitations": [
            "Historical and allocated counts are not independent pregame forecasts.",
            "Skill-player targets and RB carries are incomplete team-volume proxies; pass/rush attempts and red-zone totals are unavailable here.",
            "Missing availability flags leave measurement coverage unknown; stored zero may be a fill value.",
            "Historical source row IDs and observation clocks are unavailable unless retained in the saved inputs; a cutoff alone does not prove chronology.",
            "Optimizer role scoring still consumes explicit pregame inputs only; this packet is diagnostic evidence.",
        ],
    }


def workload_evidence_reference(player_id) -> dict:
    return {"contract_id": CONTRACT_ID, "player_id": str(player_id),
            "source_path": "strategy_runtime.player_pool.rows[player_id].workload_evidence"}


def select_measurement(player, channel, *, allow_proxy=True):
    """Read saved versions as written; v2 includes typed original/proxy provenance."""
    evidence = player.get("workload_evidence") or {}
    version = evidence.get("contract_id")
    if version not in (None, *SUPPORTED_CONTRACT_IDS):
        return None, "unsupported_workload_contract"
    choices = [("explicit_pregame", "pregame_expected_" + channel),
               ("historical", channel + "_mean_3")]
    if allow_proxy:
        choices.append(("derived_proxies", "projected_" + channel))
        if version == CONTRACT_ID:
            choices.append(("derived_proxies", "allocated_" + channel))
    for group, key in choices:
        item = evidence.get(group, {}).get(key) or {}
        value = item.get("value")
        valid = item.get("status") not in {"after_cutoff", "unavailable", "coverage_unknown", "original_history_unavailable"}
        if version == CONTRACT_ID:
            kind = {"historical": "observed_history", "derived_proxies": "allocated_proxy",
                    "explicit_pregame": "explicit_pregame_input"}[group]
            valid = valid and item.get("evidence_kind") == kind
            if group == "historical":
                valid = valid and item.get("status") == "observed" and item.get("available") is True
                valid = valid and item.get("source_field") == ORIGINAL_HISTORY_FIELDS.get(key, key)
            elif group == "explicit_pregame":
                valid = valid and bool(item.get("producer_source") and item.get("producer_observed_at"))
                try:
                    observed = datetime.fromisoformat(str(item.get("producer_observed_at")).replace("Z", "+00:00"))
                    valid = valid and observed.tzinfo is not None
                except (TypeError, ValueError):
                    valid = False
        if valid and type(value) in (int, float) and math.isfinite(value) and value >= 0:
            basis = group + "." + key
            if version == CONTRACT_ID:
                basis += " [" + item["evidence_kind"] + ":" + item.get("source_field", key) + "]"
            return float(value), basis
    return None, "unavailable"
