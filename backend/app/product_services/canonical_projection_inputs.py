"""Projection input contract for the canonical salary and player-game matrix."""

from __future__ import annotations

from ..injury_scope import injury_slate_sql

from bisect import bisect_left
from datetime import datetime, timezone
import re

import numpy as np
import pandas as pd
from sqlalchemy import inspect, select, text

from Database.dst import normalize_team
from ..models import CuratedPlayerGameParticipation, CuratedSalary, PlayerGameFeatureMatrix, RawNflSchedule
from .salary_eligibility import (
    INELIGIBLE_SALARY_STATUSES,
    is_salary_status_eligible,
    normalize_salary_status,
)
from .showdown_player_context import CONTEXT_FIELDS, CONTEXT_CONTRACT, PlayerContextUnresolved, assess_availability, is_excluded_specialist


SUPPORTED_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DST"}
PLAYED_PARTICIPATION_STATUSES = {"played_confirmed", "played_inferred"}
POSITION_FEATURE_COLUMNS = [
    "position_qb", "position_rb", "position_wr", "position_te", "position_k",
    "position_dst",
]
# Explicit pregame inputs: never infer features from all numeric matrix columns
# (which also include outcomes, database row IDs, and ingestion metadata).
BASE_FEATURE_COLUMNS = [
    "salary", "is_home", "game_total_line", "team_spread_line",
    "team_implied_total", "opponent_implied_total", "player_games_history",
    "player_roll3_mean", "player_roll8_mean", "player_roll8_std",
    "player_vs_opp_roll4", "defense_pos_allowed_roll3",
    "defense_pos_allowed_roll8", "defense_pos_allowed_p90_roll8",
    "team_offense_missing_share_lag1", "team_defense_missing_share_lag1",
    "opponent_offense_missing_share_lag1", "opponent_defense_missing_share_lag1",
]
MARKET_FEATURE_COLUMNS = {
    "game_total_line", "team_spread_line", "team_implied_total",
    "opponent_implied_total",
}
OPPORTUNITY_FEATURE_COLUMNS = [
    "carry_share_mean_3",
    "target_share_mean_3",
    "carries_mean_3",
    "targets_mean_3",
    "team_carries_mean_3",
    "team_targets_mean_3",
]
FEATURE_COLUMNS = [
    *BASE_FEATURE_COLUMNS,
    "snap_share_mean_3",
    "offensive_role_importance", "offensive_role_completeness",
    *POSITION_FEATURE_COLUMNS,
]

PREGAME_LINEAGE_COLUMNS = [
    "opportunity_allocation_policy", "opportunity_history_team",
    "opportunity_history_status", "opportunity_history_observed_games",
    "opportunity_history_window",
    *CONTEXT_FIELDS,
    "role_availability", "expected_depth_role", "role_starter_evidence",
    "role_change", "role_optimizer_eligible", "role_confidence",
    "role_resolution_warning", "role_rostered", "role_active",
    "kicker_role", "kicker_role_eligible", "kicker_role_reason",
    "kicker_role_evidence", "kicker_role_warning",
    "pregame_availability_probability",
    "pregame_start_probability",
    "pregame_carry_share",
    "pregame_target_share",
    "pregame_effective_carry_share", "pregame_effective_target_share",
    "pregame_effective_carry_share_source", "pregame_effective_target_share_source",
    "pregame_role_label",
    "pregame_injury_status",
    "practice_participation", "practice_trend", "practice_observed_at",
    "expected_workload_status", "expected_workload_observed_at", "expected_workload_source_ids",
    "pregame_expected_snaps",
    "pregame_expected_routes",
    "pregame_expected_carries",
    "pregame_expected_targets",
    "pregame_red_zone_share",
    "pregame_goal_line_share",
    "pregame_role_uncertain",
    "pregame_newly_assigned_role",
    "pregame_depth_chart_conflict",
    "pregame_context_run_id",
    "pregame_context_row_id",
    "pregame_context_source",
    "pregame_context_observed_at",
    "official_availability_status", "availability_override",
    "model_availability_used", "opportunity_redistributed",
    "projection_before_scenario", "projection_after_scenario",
    "starting_qb_source",
    "starting_qb_evidence_tier",
    "team_starting_qb_player_id", "team_starting_qb_name",
    "team_starting_qb_evidence_tier", "team_starting_qb_observed_at",
    "market_source_system", "market_snapshot_row_id", "market_observed_at",
    "market_context_updated_from_matrix",
    "market_team_point_adjustment",
    *OPPORTUNITY_FEATURE_COLUMNS,
    "offensive_role_importance", "offensive_role_completeness",
    "offensive_role_evidence", "offensive_role_class", "offensive_role_reason",
    "offensive_role_confidence", "offensive_role_source",
    "role_counterfactual_grid",
    "offensive_role_rank", "team_mean_rank", "team_p90_rank",
    "role_projection_disagreement", "team_cumulative_target_share",
    "team_cumulative_rb_carry_share",
    "projected_carries", "projected_targets", "projected_opportunity_source",
    "carry_share_mean_3_available", "target_share_mean_3_available",
    "carries_mean_3_available", "targets_mean_3_available",
    "team_carries_mean_3_available", "team_targets_mean_3_available",
    "snap_share_mean_3_available",
    "snap_share_last", "snap_share_prior3", "snap_share_trend",
    "target_share_last", "target_share_prior3", "target_share_trend",
    "rush_share_last", "rush_share_prior3", "rush_share_trend",
    "pregame_base_carries_mean_3",
    "pregame_base_targets_mean_3",
    "pregame_base_carry_share_mean_3", "pregame_base_target_share_mean_3",
    "pregame_workload_multiplier",
    "pregame_workload_adjustment_source",
    "pregame_opportunity_context_applied",
    "pregame_point_mean_before_opportunity",
    "pregame_opportunity_point_anchor",
    "pregame_opportunity_point_weight",
    "pregame_point_mean_after_opportunity",
    "pregame_opportunity_point_reason",
    "pregame_opportunity_evidence_status",
    "pregame_opportunity_review_required",
]


class StaleTrainingOutcomeError(ValueError):
    """Completed results exist, but their persisted training labels are stale."""

    def __init__(self, periods: list[tuple[int, int]]):
        self.periods = tuple(sorted(set(periods)))
        labels = [f"{season}-W{week:02d}" for season, week in self.periods]
        super().__init__(
            "Completed weekly stats contain opportunities but the projection feature "
            "matrix has only zero outcomes for "
            f"{', '.join(labels)}. Rebuild the player-game feature matrix after "
            "ingesting results before running projections."
        )


def _control_name(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _questionable_snapshot_overrides(target, pregame_context, injury_statuses) -> list[dict]:
    """Automatic assumptions apply only after scoring-pool eligibility filters."""
    if injury_statuses is None or injury_statuses.empty:
        return []
    from .factual_designation import effective_designation, QUESTIONABLE
    context_rows = {
        str(row["player_master_id"]): row
        for row in (pregame_context.to_dict("records") if pregame_context is not None else [])
    }
    scoring_ids = set(target["player_id"].astype(str))
    return [
        {"player_id": str(row.player_id), "availability": "assume_out",
         "official_availability_status": normalize_salary_status(row.injury_status)}
        for row in injury_statuses.itertuples(index=False)
        if str(row.player_id) in scoring_ids
        and effective_designation({**row._asdict(), **{k:v for k,v in context_rows.get(str(row.player_id), {}).items()
            if v is not None}}) in QUESTIONABLE
    ]


def apply_player_availability_overrides(
    target: pd.DataFrame,
    pregame_context: pd.DataFrame | None,
    overrides: list[dict] | None,
    *,
    allow_confirmed_inactive_override: bool = False,
    assume_questionable_out: bool = False,
) -> tuple[pd.DataFrame, list[dict]]:
    """Overlay user scenario evidence before generic opportunity allocation."""
    context = pregame_context.copy() if pregame_context is not None else pd.DataFrame()
    requested = [row for row in (overrides or []) if row.get("availability") != "default"]
    if assume_questionable_out:
        from .factual_designation import effective_designation, QUESTIONABLE
        context_rows = {}
        if not context.empty:
            context_id = "player_master_id" if "player_master_id" in context else "player_id"
            context_rows = {
                str(row[context_id]): row
                for row in context.to_dict("records")
            }
        requested = [*requested, *[
            {"player_id": str(row.player_id), "availability": "assume_out"}
            for row in target.itertuples(index=False)
            if effective_designation({**row._asdict(), **context_rows.get(str(row.player_id), {})}) in QUESTIONABLE
        ]]
    if not requested:
        return context, []

    by_id = {str(row.player_id): row for row in target.itertuples(index=False)}
    by_name: dict[str, list] = {}
    for row in target.itertuples(index=False):
        by_name.setdefault(_control_name(row.player_display_name), []).append(row)

    if context.empty:
        context = pd.DataFrame(columns=["player_master_id"])
    id_column = "player_master_id" if "player_master_id" in context.columns else "player_id"
    if id_column not in context.columns:
        context[id_column] = None
    audit: list[dict] = []
    seen: dict[str, str] = {}
    zero_fields = (
        "start_probability", "expected_snaps",
        "expected_routes", "red_zone_share", "goal_line_share",
    )
    for override in requested:
        player = None
        player_id = str(override.get("player_id") or "").strip()
        if player_id:
            player = by_id.get(player_id)
            if player is None:
                raise ValueError(
                    f"Availability override player_id was not found in the selected slate: {player_id}"
                )
        else:
            supplied_name = str(override.get("player_name") or "").strip()
            matches = by_name.get(_control_name(supplied_name), [])
            if len(matches) != 1:
                reason = "was not found" if not matches else "is ambiguous"
                raise ValueError(
                    f"Availability override player {reason} in the selected slate: {supplied_name}"
                )
            player = matches[0]
            player_id = str(player.player_id)
        if player_id in seen:
            if seen[player_id] == override["availability"]:
                continue
            raise ValueError(f"Conflicting availability overrides for {player.player_display_name}")
        seen[player_id] = override["availability"]

        matches = context.index[context[id_column].astype(str).eq(player_id)].tolist()
        context_index = matches[0] if matches else len(context)
        if not matches:
            context.loc[context_index, id_column] = player_id
        official_status = (
            normalize_salary_status(context.loc[context_index].get("injury_status"))
            or normalize_salary_status(override.get("official_availability_status"))
            or normalize_salary_status(getattr(player, "player_status", None))
        )
        availability = str(override["availability"])
        if (
            availability == "assume_active"
            and official_status
            and not is_salary_status_eligible(official_status)
            and not allow_confirmed_inactive_override
        ):
            raise ValueError(
                f"Assume Active cannot override confirmed inactive status for "
                f"{player.player_display_name} ({official_status})"
            )
        context.loc[context_index, "availability_probability"] = (
            1.0 if availability == "assume_active" else 0.0
        )
        context.loc[context_index, "source"] = "user_availability_scenario"
        if availability == "assume_out":
            for field in zero_fields:
                context.loc[context_index, field] = 0.0
            # Preserve pre-injury shares and counts until allocation measures
            # the removed work. Availability zeroes the final allocation.
        audit.append(
            {
                "player_id": player_id,
                "player_name": str(player.player_display_name),
                "team": str(player.recent_team),
                "official_availability_status": official_status or None,
                "availability_override": availability,
                "model_availability_used": 1.0 if availability == "assume_active" else 0.0,
                "opportunity_redistributed": availability == "assume_out",
            }
        )
    return context, audit


def apply_latest_market_context(
    target: pd.DataFrame, market_rows: pd.DataFrame, *, cutoff: datetime | None = None,
) -> tuple[pd.DataFrame, list[dict]]:
    """Overlay only captured, pre-cutoff game lines on future projection rows."""
    updated = target.copy()
    matrix_market = target.copy()
    # A feature-matrix zero is a model imputation, not a captured betting line.
    # Only a timestamped, matched raw schedule row may populate decision data.
    for column in MARKET_FEATURE_COLUMNS:
        updated[column] = np.nan
    for column in ("market_source_system", "market_snapshot_row_id", "market_observed_at"):
        updated[column] = None
    updated["market_context_updated_from_matrix"] = False
    audit: list[dict] = []
    if market_rows.empty:
        return updated, audit
    from backend.app.services.schedule_context import nflverse_team_market_context

    def market_payload(row: dict) -> dict:
        payload = row.get("raw_row_json")
        return payload if isinstance(payload, dict) else {}

    def observation_order(row: dict) -> int:
        observed_value = row.get("observed_at") if pd.notna(row.get("observed_at")) else \
            market_payload(row).get("observed_at")
        observed = pd.to_datetime(observed_value,
                                  utc=True, errors="coerce")
        return -1 if pd.isna(observed) else observed.value

    ordered_markets = sorted(market_rows.to_dict(orient="records"), key=observation_order)
    for market in ordered_markets:
        payload = market_payload(market)
        normalized = pd.notna(market.get("game_total")) and pd.notna(market.get("home_spread"))
        snapshot_row_id = market.get("market_snapshot_id") if normalized else market.get("raw_nfl_schedule_id")
        source_system = market.get("source") if normalized else market.get("source_system")
        try:
            total = float(market["game_total"] if normalized else payload["total_line"])
            home_margin = float(-market["home_spread"] if normalized else payload["spread_line"])
        except (KeyError, TypeError, ValueError):
            continue
        if (not np.isfinite(total) or not np.isfinite(home_margin)
                or not 20 <= total <= 80 or abs(home_margin) > 30
                or (total - abs(home_margin)) / 2 <= 0):
            audit.append({"status": "invalid_market_values",
                          "snapshot_row_id": snapshot_row_id})
            continue
        home = normalize_team(str(market.get("home_team") or ""))
        away = normalize_team(str(market.get("away_team") or ""))
        observed_at = str(market.get("observed_at") if normalized else payload.get("observed_at") or "")
        observed = pd.to_datetime(observed_at, utc=True, errors="coerce")
        kickoff = pd.to_datetime(market.get("kickoff_at") if normalized else market.get("kickoff"),
                                 utc=True, errors="coerce")
        ingested = pd.to_datetime(market.get("ingested_at") if normalized else market.get("created_at"),
                                  utc=True, errors="coerce")
        if (pd.isna(observed) or
                cutoff is not None and observed > pd.Timestamp(cutoff).tz_convert("UTC") or
                pd.isna(kickoff) or observed >= kickoff or
                cutoff is not None and (pd.isna(ingested) or
                                        ingested > pd.Timestamp(cutoff).tz_convert("UTC"))):
            audit.append({"status": "market_timestamp_not_predecision",
                          "snapshot_row_id": snapshot_row_id,
                          "observed_at": observed_at})
            continue
        home_context, away_context = nflverse_team_market_context(
            total_line=total, home_margin=home_margin,
        )
        for team, opponent, context in ((home, away, home_context),
                                        (away, home, away_context)):
            mask = (
                updated["recent_team"].astype(str).str.upper().eq(team)
                & updated["opponent_team"].astype(str).str.upper().eq(opponent)
            )
            if market.get("season") is not None and "season" in updated:
                mask &= pd.to_numeric(updated["season"], errors="coerce").eq(int(market["season"]))
            if market.get("week") is not None and "week" in updated:
                mask &= pd.to_numeric(updated["week"], errors="coerce").eq(int(market["week"]))
            if market.get("game_id") and "game_id" in updated:
                mask &= (updated["game_id"].isna() |
                         updated["game_id"].astype(str).eq(str(market["game_id"])))
            if not mask.any():
                continue
            if market.get("game_id") and "game_id" in updated:
                missing_game_id = mask & updated["game_id"].isna()
                updated.loc[missing_game_id, "game_id"] = str(market["game_id"])
            previous = {
                key: float(pd.to_numeric(matrix_market.loc[mask, key], errors="coerce").iloc[0])
                for key in context
                if pd.notna(pd.to_numeric(matrix_market.loc[mask, key], errors="coerce").iloc[0])
            }
            changed = any(
                pd.to_numeric(matrix_market.loc[mask, key], errors="coerce")
                .sub(value).abs().gt(0.001).any()
                for key, value in context.items()
            )
            for key, value in context.items():
                updated.loc[mask, key] = value
            updated.loc[mask, "market_source_system"] = source_system
            updated.loc[mask, "market_snapshot_row_id"] = snapshot_row_id
            updated.loc[mask, "market_observed_at"] = observed_at
            updated.loc[mask, "market_context_updated_from_matrix"] = bool(changed)
            audit.append({
                "team": team, "opponent": opponent, "source_system": source_system,
                "snapshot_row_id": snapshot_row_id,
                "observed_at": observed_at,
                "game_total": total, "team_spread": context["team_spread_line"],
                "team_implied_total": context["team_implied_total"],
                "previous_matrix": previous,
                "implied_total_delta": (
                    context["team_implied_total"] - previous["team_implied_total"]
                    if "team_implied_total" in previous else None
                ),
                "changed_from_matrix": bool(changed),
            })
    return updated, audit


def reconcile_training_market_context(
    train: pd.DataFrame, market_rows: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    """Correct legacy historical spread signs from source-native pregame lines."""
    if train.empty or market_rows.empty:
        return train.copy(), {"status": "unavailable", "corrected_players": 0}
    from backend.app.services.schedule_context import nflverse_team_market_context

    observations: list[dict] = []
    for market in market_rows.to_dict(orient="records"):
        payload = market.get("raw_row_json") or {}
        if not isinstance(payload, dict):
            continue
        try:
            total = float(payload["total_line"])
            home_margin = float(payload["spread_line"])
        except (KeyError, TypeError, ValueError):
            continue
        if not np.isfinite(total) or not np.isfinite(home_margin) or total <= 0:
            continue
        home = normalize_team(str(market.get("home_team") or ""))
        away = normalize_team(str(market.get("away_team") or ""))
        home_context, away_context = nflverse_team_market_context(
            total_line=total, home_margin=home_margin,
        )
        for team, opponent, context in ((home, away, home_context),
                                        (away, home, away_context)):
            observations.append({
                "season": int(market["season"]), "week": int(market["week"]),
                "market_team": team, "market_opponent": opponent,
                **{f"correct_{key}": value for key, value in context.items()},
            })
    if not observations:
        return train.copy(), {"status": "unavailable", "corrected_players": 0}
    rows = train.copy()
    rows["market_team"] = rows["team"].map(normalize_team)
    rows["market_opponent"] = rows["opponent"].map(normalize_team)
    corrected = rows.merge(
        pd.DataFrame(observations).drop_duplicates(
            ["season", "week", "market_team", "market_opponent"], keep="last"
        ),
        on=["season", "week", "market_team", "market_opponent"], how="left",
        sort=False, validate="many_to_one",
    ).drop(columns=["market_team", "market_opponent"])
    source_matched = corrected["correct_game_total_line"].notna()
    mismatch = pd.Series(False, index=corrected.index)
    for column in ("game_total_line", "team_spread_line", "team_implied_total",
                   "opponent_implied_total"):
        source = corrected[f"correct_{column}"]
        existing = pd.to_numeric(corrected[column], errors="coerce")
        mismatch |= source.notna() & (existing.isna() | (existing - source).abs().gt(0.001))
        corrected[column] = source.where(source.notna(), existing)
        corrected = corrected.drop(columns=[f"correct_{column}"])
    audit = {
        "status": "reconciled",
        "policy": "source-native pregame spread_line is expected home-team margin",
        "matched_players": int(source_matched.sum()),
        "corrected_players": int(mismatch.sum()),
        "corrected_games": int(corrected.loc[mismatch, ["season", "week", "game_id"]]
                               .drop_duplicates().shape[0]),
    }
    return corrected, audit


def validate_completed_training_outcomes(
    train: pd.DataFrame,
    weekly_stats: pd.DataFrame | None,
) -> dict[str, object]:
    """Reject a completed period whose feature matrix still has pregame zero labels."""
    audit: dict[str, object] = {
        "status": "unavailable",
        "periods_checked": 0,
        "zero_label_periods": [],
    }
    target_column = "label_dk_total_points"
    required_train = {"season", "week", "player_id", target_column}
    required_stats = {"season", "week", "player_master_id", "carries", "targets"}
    if train.empty or weekly_stats is None or weekly_stats.empty:
        return audit
    if not required_train.issubset(train.columns) or not required_stats.issubset(
        weekly_stats.columns
    ):
        return audit

    stats = weekly_stats.copy()
    stats["player_master_id"] = stats["player_master_id"].astype(str)
    stats["actual_opportunities"] = (
        pd.to_numeric(stats["carries"], errors="coerce").fillna(0.0)
        + pd.to_numeric(stats["targets"], errors="coerce").fillna(0.0)
    )
    labels = train.copy()
    labels["player_id"] = labels["player_id"].astype(str)
    labels[target_column] = pd.to_numeric(labels[target_column], errors="coerce")
    zero_periods: list[tuple[int, int]] = []
    periods_checked = 0
    for (period_season, period_week), period in labels.groupby(["season", "week"]):
        source = stats.loc[
            (stats["season"] == period_season)
            & (stats["week"] == period_week)
            & stats["player_master_id"].isin(period["player_id"])
        ]
        if source.empty or not source["actual_opportunities"].gt(0).any():
            continue
        periods_checked += 1
        if period[target_column].fillna(0.0).abs().max() == 0.0:
            zero_periods.append((int(period_season), int(period_week)))

    audit.update(
        {
            "status": "valid" if not zero_periods else "invalid",
            "periods_checked": periods_checked,
            "zero_label_periods": [
                f"{period_season}-W{period_week:02d}"
                for period_season, period_week in zero_periods
            ],
        }
    )
    if zero_periods:
        raise StaleTrainingOutcomeError(zero_periods)
    return audit


def _period_ordinal(season: object, week: object) -> int:
    return (int(season) * 100) + int(week)


def attach_lagged_participation_features(
    matrix: pd.DataFrame,
    participation: pd.DataFrame | None,
    *,
    cutoff: pd.Timestamp,
) -> tuple[pd.DataFrame, dict]:
    """Attach exact historical participation and prior-only snap-share history."""
    rows = matrix.copy()
    rows["training_participation_status"] = "unavailable"
    rows["snap_share_mean_3"] = 0.0
    rows["snap_share_mean_3_available"] = False
    for column in ("snap_share_last", "snap_share_prior3", "snap_share_trend"):
        rows[column] = np.nan
    metrics = {
        "source": "public.curated_player_game_participation",
        "available": False,
        "rows_loaded": 0,
        "rows_with_lagged_snap_share": 0,
    }
    if participation is None or participation.empty:
        return rows, metrics

    evidence = participation.copy()
    required = {"season", "week", "player_master_id", "participation_status"}
    missing = sorted(required.difference(evidence.columns))
    if missing:
        raise ValueError(
            "Participation data is missing required columns: " + ", ".join(missing)
        )
    if "created_at" in evidence.columns:
        evidence = evidence.loc[
            pd.to_datetime(evidence["created_at"], utc=True) <= cutoff
        ].copy()
    evidence = evidence.loc[evidence["player_master_id"].notna()].copy()
    if evidence.empty:
        return rows, metrics

    evidence["player_master_id"] = evidence["player_master_id"].astype(str)
    evidence["season"] = pd.to_numeric(evidence["season"], errors="coerce")
    evidence["week"] = pd.to_numeric(evidence["week"], errors="coerce")
    evidence = evidence.dropna(subset=["season", "week"])
    evidence["period_ordinal"] = [
        _period_ordinal(season, week)
        for season, week in zip(evidence["season"], evidence["week"], strict=True)
    ]
    sort_columns = ["period_ordinal"]
    for column in ("created_at", "curated_player_game_participation_id"):
        if column in evidence.columns:
            sort_columns.append(column)
    evidence = evidence.sort_values(sort_columns).drop_duplicates(
        ["season", "week", "player_master_id"], keep="last"
    )

    status_lookup = {
        (int(row.season), int(row.week), str(row.player_master_id)): str(
            row.participation_status
        ).lower()
        for row in evidence.itertuples(index=False)
    }
    rows["training_participation_status"] = [
        status_lookup.get(
            (int(season), int(week), str(player_id)),
            "no_record",
        )
        for season, week, player_id in zip(
            rows["season"], rows["week"], rows["player_master_id"], strict=True
        )
    ]

    evidence["offense_snap_share"] = pd.to_numeric(
        evidence.get("offense_snap_share"), errors="coerce"
    )
    snap_history: dict[str, tuple[list[int], list[float]]] = {}
    for player_id, player_rows in evidence.dropna(subset=["offense_snap_share"]).groupby(
        "player_master_id"
    ):
        ordered = player_rows.sort_values("period_ordinal")
        snap_history[str(player_id)] = (
            ordered["period_ordinal"].astype(int).tolist(),
            ordered["offense_snap_share"].astype(float).tolist(),
        )

    lagged_values: list[float] = []
    last_values: list[float] = []
    prior_values: list[float] = []
    for season, week, player_id in zip(
        rows["season"], rows["week"], rows["player_master_id"], strict=True
    ):
        history = snap_history.get(str(player_id))
        if history is None:
            lagged_values.append(0.0)
            last_values.append(np.nan)
            prior_values.append(np.nan)
            continue
        periods, shares = history
        stop = bisect_left(periods, _period_ordinal(season, week))
        recent = shares[max(0, stop - 3):stop]
        lagged_values.append(float(np.mean(recent)) if recent else 0.0)
        last_values.append(float(shares[stop - 1]) if stop else np.nan)
        prior = shares[max(0, stop - 4):stop - 1] if stop else []
        prior_values.append(float(np.mean(prior)) if prior else np.nan)
    rows["snap_share_mean_3"] = lagged_values
    rows["snap_share_last"] = last_values
    rows["snap_share_prior3"] = prior_values
    rows["snap_share_trend"] = rows["snap_share_last"] - rows["snap_share_prior3"]
    rows["snap_share_mean_3_available"] = [
        bool((history := snap_history.get(str(player_id))) and
             bisect_left(history[0], _period_ordinal(season, week)) > 0)
        for season, week, player_id in zip(
            rows["season"], rows["week"], rows["player_master_id"], strict=True
        )
    ]
    metrics.update(
        {
            "available": True,
            "rows_loaded": int(len(evidence)),
            "rows_with_lagged_snap_share": int((rows["snap_share_mean_3"] > 0).sum()),
        }
    )
    return rows, metrics


def attach_lagged_opportunity_features(
    matrix: pd.DataFrame,
    weekly_stats: pd.DataFrame | None,
    *,
    cutoff: pd.Timestamp,
    policy: str = "legacy_v1",
) -> tuple[pd.DataFrame, dict]:
    """Attach prior-only carries, targets, and team-share features."""
    rows = matrix.copy()
    if policy not in {"legacy_v1", "team_window_v2"}:
        raise ValueError("Unsupported player opportunity allocation policy")
    player_feature_sources = {
        "carries_mean_3": "carries",
        "targets_mean_3": "targets",
        "carry_share_mean_3": "carry_share",
        "target_share_mean_3": "target_share",
    }
    team_feature_sources = {
        "team_carries_mean_3": "team_carries",
        "team_targets_mean_3": "team_targets",
    }
    for feature in (*player_feature_sources, *team_feature_sources):
        rows[feature] = 0.0
        rows[f"{feature}_available"] = False
    for prefix in ("target_share", "rush_share"):
        for suffix in ("last", "prior3", "trend"):
            rows[f"{prefix}_{suffix}"] = np.nan
    if policy == "team_window_v2":
        rows["opportunity_allocation_policy"] = policy
        rows["opportunity_history_team"] = rows.get("recent_team", rows.get("team", pd.Series("", index=rows.index))).fillna("").map(normalize_team)
        rows["opportunity_history_status"] = "no_same_team_window_history"
        rows["opportunity_history_observed_games"] = 0
        rows["opportunity_history_window"] = pd.Series([[] for _ in range(len(rows))], index=rows.index, dtype=object)
    metrics = {
        "policy": policy,
        "source": "public.raw_nfl_weekly_stat + public.player_alias",
        "available": False,
        "rows_loaded": 0,
        "rows_with_lagged_carries": 0,
        "rows_with_lagged_targets": 0,
        "rows_with_lagged_carry_share": 0,
        "rows_with_lagged_target_share": 0,
        "rows_with_lagged_team_carries": 0,
        "rows_with_lagged_team_targets": 0,
        "unresolved_rows_in_team_volume": 0,
    }
    if weekly_stats is None or weekly_stats.empty:
        return rows, metrics

    evidence = weekly_stats.copy()
    required = {
        "season",
        "week",
        "player_master_id",
        "team",
        "position",
        "carries",
        "targets",
    }
    missing = sorted(required.difference(evidence.columns))
    if missing:
        raise ValueError(
            "Weekly opportunity data is missing required columns: "
            + ", ".join(missing)
        )
    if "created_at" in evidence.columns:
        evidence = evidence.loc[
            pd.to_datetime(evidence["created_at"], utc=True) <= cutoff
        ].copy()
    evidence["player_master_id"] = evidence["player_master_id"].astype("string")
    evidence["season"] = pd.to_numeric(evidence["season"], errors="coerce")
    evidence["week"] = pd.to_numeric(evidence["week"], errors="coerce")
    evidence = evidence.dropna(subset=["season", "week"])
    for column in ("carries", "targets"):
        evidence[column] = pd.to_numeric(evidence[column], errors="coerce")
        if evidence[column].isna().any():
            raise ValueError(
                f"Weekly opportunity source has unavailable {column}; "
                "do not convert missing role data to measured zero."
            )
    evidence["team"] = evidence["team"].fillna("").astype(str).str.upper()
    if policy == "team_window_v2":
        evidence["team"] = evidence["team"].map(normalize_team)
    evidence["position"] = evidence["position"].fillna("").astype(str).str.upper()
    if policy == "team_window_v2":
        # DraftKings fullbacks belong to the RB opportunity pool.
        evidence["position"] = evidence["position"].replace({"FB": "RB"})
    evidence["period_ordinal"] = [
        _period_ordinal(season, week)
        for season, week in zip(evidence["season"], evidence["week"], strict=True)
    ]
    sort_columns = ["period_ordinal"]
    for column in ("created_at", "raw_nfl_weekly_stat_id"):
        if column in evidence.columns:
            sort_columns.append(column)
    source_identity = evidence.get(
        "source_player_id", pd.Series(pd.NA, index=evidence.index, dtype="string")
    ).astype("string")
    fallback_identity = evidence.get(
        "raw_nfl_weekly_stat_id", pd.Series(evidence.index, index=evidence.index)
    ).astype("string")
    evidence["opportunity_identity"] = evidence["player_master_id"].fillna(
        source_identity
    ).fillna(fallback_identity)
    evidence = evidence.sort_values(sort_columns).drop_duplicates(
        ["season", "week", "opportunity_identity"], keep="last"
    )
    evidence["carry_share"] = 0.0
    running_backs = evidence["position"].eq("RB")
    rb_carries = evidence.loc[running_backs].groupby(
        ["season", "week", "team"], dropna=False
    )["carries"].transform("sum")
    evidence.loc[running_backs, "carry_share"] = np.where(
        rb_carries > 0,
        evidence.loc[running_backs, "carries"] / rb_carries,
        0.0,
    )
    evidence["target_share"] = 0.0
    target_eligible = evidence["position"].isin({"RB", "WR", "TE"})
    skill_targets = evidence.loc[target_eligible].groupby(
        ["season", "week", "team"], dropna=False
    )["targets"].transform("sum")
    evidence.loc[target_eligible, "target_share"] = np.where(
        skill_targets > 0,
        evidence.loc[target_eligible, "targets"] / skill_targets,
        0.0,
    )

    weekly_team_volume = (
        evidence.assign(
            team_carries=np.where(running_backs, evidence["carries"], 0.0),
            team_targets=np.where(target_eligible, evidence["targets"], 0.0),
        )
        .groupby(["season", "week", "team", "period_ordinal"], as_index=False)[
            ["team_carries", "team_targets"]
        ]
        .sum()
    )

    if policy == "team_window_v2":
        from .opportunity_history import attach_team_window_opportunity
        rows = attach_team_window_opportunity(rows, evidence, weekly_team_volume)
        for feature in (*player_feature_sources, *team_feature_sources):
            metrics[f"rows_with_lagged_{feature.removesuffix('_mean_3')}"] = int(rows[f"{feature}_available"].sum())
        metrics.update(available=True, rows_loaded=len(evidence),
            unresolved_rows_in_team_volume=int(evidence["player_master_id"].isna().sum()),
            history_status_counts=rows["opportunity_history_status"].value_counts().to_dict())
        return rows, metrics

    histories: dict[str, dict[str, tuple[list[int], list[float]]]] = {}
    resolved_evidence = evidence.loc[evidence["player_master_id"].notna()].copy()
    for player_id, player_rows in resolved_evidence.groupby("player_master_id"):
        ordered = player_rows.sort_values("period_ordinal")
        periods = ordered["period_ordinal"].astype(int).tolist()
        histories[str(player_id)] = {
            source: (periods, ordered[source].astype(float).tolist())
            for source in player_feature_sources.values()
        }

    for feature, source in player_feature_sources.items():
        lagged_values: list[float] = []
        available_values: list[bool] = []
        last_values: list[float] = []
        prior_values: list[float] = []
        for season, week, player_id in zip(
            rows["season"], rows["week"], rows["player_master_id"], strict=True
        ):
            history = histories.get(str(player_id), {}).get(source)
            if history is None:
                lagged_values.append(0.0)
                available_values.append(False)
                last_values.append(np.nan)
                prior_values.append(np.nan)
                continue
            periods, values = history
            stop = bisect_left(periods, _period_ordinal(season, week))
            recent = values[max(0, stop - 3):stop]
            lagged_values.append(float(np.mean(recent)) if recent else 0.0)
            available_values.append(bool(recent))
            last_values.append(float(values[stop - 1]) if stop else np.nan)
            prior = values[max(0, stop - 4):stop - 1] if stop else []
            prior_values.append(float(np.mean(prior)) if prior else np.nan)
        rows[feature] = lagged_values
        rows[f"{feature}_available"] = available_values
        prefix = {"target_share_mean_3": "target_share", "carry_share_mean_3": "rush_share"}.get(feature)
        if prefix:
            relevant = (
                rows.get("position", pd.Series("", index=rows.index)).astype(str).str.upper().eq("RB")
                if prefix == "rush_share" else pd.Series(True, index=rows.index)
            )
            rows[f"{prefix}_last"] = np.where(relevant, last_values, np.nan)
            rows[f"{prefix}_prior3"] = np.where(relevant, prior_values, np.nan)
            rows[f"{prefix}_trend"] = rows[f"{prefix}_last"] - rows[f"{prefix}_prior3"]

    team_histories: dict[str, dict[str, tuple[list[int], list[float]]]] = {}
    for team, team_rows in weekly_team_volume.groupby("team"):
        ordered = team_rows.sort_values("period_ordinal")
        periods = ordered["period_ordinal"].astype(int).tolist()
        team_histories[str(team)] = {
            source: (periods, ordered[source].astype(float).tolist())
            for source in team_feature_sources.values()
        }
    matrix_teams = rows.get(
        "team", pd.Series("", index=rows.index, dtype="object")
    ).fillna("").astype(str).str.upper()
    for feature, source in team_feature_sources.items():
        lagged_values = []
        available_values = []
        for season, week, team in zip(
            rows["season"], rows["week"], matrix_teams, strict=True
        ):
            history = team_histories.get(str(team), {}).get(source)
            if history is None:
                lagged_values.append(0.0)
                available_values.append(False)
                continue
            periods, values = history
            stop = bisect_left(periods, _period_ordinal(season, week))
            recent = values[max(0, stop - 3):stop]
            lagged_values.append(float(np.mean(recent)) if recent else 0.0)
            available_values.append(bool(recent))
        rows[feature] = lagged_values
        rows[f"{feature}_available"] = available_values

    metrics.update(
        {
            "available": True,
            "rows_loaded": int(len(evidence)),
            "rows_with_lagged_carries": int((rows["carries_mean_3"] > 0).sum()),
            "rows_with_lagged_targets": int((rows["targets_mean_3"] > 0).sum()),
            "rows_with_lagged_carry_share": int(
                (rows["carry_share_mean_3"] > 0).sum()
            ),
            "rows_with_lagged_target_share": int(
                (rows["target_share_mean_3"] > 0).sum()
            ),
            "rows_with_lagged_team_carries": int(
                (rows["team_carries_mean_3"] > 0).sum()
            ),
            "rows_with_lagged_team_targets": int(
                (rows["team_targets_mean_3"] > 0).sum()
            ),
            "unresolved_rows_in_team_volume": int(
                evidence["player_master_id"].isna().sum()
            ),
        }
    )
    return rows, metrics


def apply_pregame_projection_context(
    target: pd.DataFrame,
    *,
    starting_qbs: pd.DataFrame | None = None,
    pregame_context: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Apply cutoff-safe starter, availability, and opportunity evidence.

    Removed work stays unallocated without evidence-backed recipients. Salary
    never supplies opportunity weights. Allocation is auditable per recipient,
    before the point model runs; it does not transfer fantasy points.
    """
    rows = target.copy().reset_index(drop=True)
    rows["pregame_availability_probability"] = 1.0
    rows["pregame_start_probability"] = np.nan
    rows["pregame_carry_share"] = np.nan
    rows["pregame_target_share"] = np.nan
    rows["pregame_effective_carry_share"] = np.nan
    rows["pregame_effective_target_share"] = np.nan
    rows["pregame_effective_carry_share_source"] = None
    rows["pregame_effective_target_share_source"] = None
    rows["pregame_role_label"] = None
    rows["pregame_injury_status"] = None
    for field in ("practice_participation", "practice_trend", "practice_observed_at",
                  "expected_workload_status", "expected_workload_observed_at"):
        rows[field] = None
    rows["pregame_expected_snaps"] = np.nan
    rows["pregame_expected_routes"] = np.nan
    rows["pregame_expected_carries"] = np.nan
    rows["pregame_expected_targets"] = np.nan
    rows["pregame_red_zone_share"] = np.nan
    rows["pregame_goal_line_share"] = np.nan
    rows["pregame_role_uncertain"] = False
    rows["pregame_newly_assigned_role"] = False
    rows["pregame_depth_chart_conflict"] = False
    rows["pregame_context_run_id"] = None
    rows["pregame_context_row_id"] = None
    rows["pregame_context_source"] = None
    rows["pregame_context_observed_at"] = None
    rows["starting_qb_source"] = None
    rows["starting_qb_evidence_tier"] = None
    rows["team_starting_qb_player_id"] = None
    rows["team_starting_qb_name"] = None
    rows["team_starting_qb_evidence_tier"] = None
    rows["team_starting_qb_observed_at"] = None
    rows["pregame_base_carries_mean_3"] = pd.to_numeric(
        rows["carries_mean_3"], errors="coerce"
    ).fillna(0.0)
    rows["pregame_base_targets_mean_3"] = pd.to_numeric(
        rows["targets_mean_3"], errors="coerce"
    ).fillna(0.0)
    rows["pregame_base_carry_share_mean_3"] = rows["carry_share_mean_3"]
    rows["pregame_base_target_share_mean_3"] = rows["target_share_mean_3"]
    rows["pregame_opportunity_context_applied"] = False

    context_rows = pregame_context.copy() if pregame_context is not None else pd.DataFrame()
    context_by_player: dict[str, dict] = {}
    explicit_start_player_ids: set[str] = set()
    if not context_rows.empty:
        id_column = (
            "player_master_id"
            if "player_master_id" in context_rows.columns
            else "player_id"
        )
        context_rows = context_rows.loc[context_rows[id_column].notna()].copy()
        context_by_player = {
            str(row[id_column]): row
            for row in context_rows.to_dict(orient="records")
        }
        explicit_start_player_ids = {
            str(row[id_column])
            for row in context_rows.to_dict(orient="records")
            if row.get("start_probability") is not None
            and not (
                isinstance(row.get("start_probability"), float)
                and np.isnan(row["start_probability"])
            )
        }
    for index, row in rows.iterrows():
        context = context_by_player.get(str(row["player_id"]))
        if context is None:
            continue
        for source, output in (
            ("availability_probability", "pregame_availability_probability"),
            ("start_probability", "pregame_start_probability"),
            ("carry_share", "pregame_carry_share"),
            ("target_share", "pregame_target_share"),
            ("role_label", "pregame_role_label"),
            ("injury_status", "pregame_injury_status"),
            ("expected_snaps", "pregame_expected_snaps"),
            ("expected_routes", "pregame_expected_routes"),
            ("expected_carries", "pregame_expected_carries"),
            ("expected_targets", "pregame_expected_targets"),
            ("red_zone_share", "pregame_red_zone_share"),
            ("goal_line_share", "pregame_goal_line_share"),
            ("context_run_id", "pregame_context_run_id"),
            ("pregame_player_context_id", "pregame_context_row_id"),
            ("source", "pregame_context_source"),
            ("observed_at", "pregame_context_observed_at"),
        ):
            value = context.get(source)
            if value is not None and not (isinstance(value, float) and np.isnan(value)):
                rows.at[index, output] = value
        evidence = context.get("evidence_json") or context.get("evidence") or {}
        if isinstance(evidence, dict):
            for field in CONTEXT_FIELDS:
                if field not in rows:
                    rows[field] = None
                rows.at[index, field] = evidence.get(field)
            from .pregame_context import risk_evidence_fields
            for field, value in risk_evidence_fields(evidence, context.get("observed_at")).items():
                rows.at[index, field] = value
            for source, output in (
                ("role_uncertain", "pregame_role_uncertain"),
                ("newly_assigned_role", "pregame_newly_assigned_role"),
                ("depth_chart_conflict", "pregame_depth_chart_conflict"),
            ):
                if source in evidence:
                    rows.at[index, output] = bool(evidence[source])

    qb_evidence = (
        starting_qbs.copy() if starting_qbs is not None else pd.DataFrame()
    )
    selected_by_team: dict[str, dict] = {}
    if not qb_evidence.empty:
        qb_evidence["team"] = qb_evidence["team"].fillna("").astype(str).str.upper()
        for evidence in qb_evidence.to_dict(orient="records"):
            selected_by_team[str(evidence["team"])] = evidence

    missing_qb_teams: list[str] = []
    positions = rows["position"].fillna("").astype(str).str.upper()
    teams = rows["recent_team"].fillna("").astype(str).str.upper()
    for team, indexes in rows.loc[positions.eq("QB")].groupby(teams).groups.items():
        evidence = selected_by_team.get(str(team))
        explicit = rows.loc[indexes, "player_id"].astype(str).isin(
            explicit_start_player_ids
        )
        if evidence is None and len(indexes) > 1 and not explicit.all():
            missing_qb_teams.append(str(team))
            continue
        if evidence is None:
            continue
        starter_id = str(
            evidence.get("player_master_id") or evidence.get("player_id") or ""
        )
        evidence_details = evidence.get("evidence_json") or {}
        observed_at = (
            evidence_details.get("observed_at")
            if isinstance(evidence_details, dict) else None
        ) or evidence.get("created_at")
        team_mask = teams.eq(str(team))
        rows.loc[team_mask, "team_starting_qb_player_id"] = starter_id
        rows.loc[team_mask, "team_starting_qb_name"] = evidence.get("player_name")
        rows.loc[team_mask, "team_starting_qb_evidence_tier"] = evidence.get("evidence_tier")
        rows.loc[team_mask, "team_starting_qb_observed_at"] = str(observed_at)
        for index in indexes:
            if not explicit.loc[index]:
                rows.at[index, "pregame_start_probability"] = float(
                    str(rows.at[index, "player_id"]) == starter_id
                )
            rows.at[index, "starting_qb_source"] = evidence.get("source")
            rows.at[index, "starting_qb_evidence_tier"] = evidence.get(
                "evidence_tier"
            )
    if missing_qb_teams:
        raise ValueError(
            "Starting-QB evidence is required before projections because multiple "
            "active QBs are present for: " + ", ".join(sorted(missing_qb_teams))
        )

    from .player_roles import resolve_player_roles
    rows, role_audit = resolve_player_roles(rows, context_rows)
    unavailable_roles = rows["role_availability"].eq("unavailable")
    rows.loc[unavailable_roles, "pregame_availability_probability"] = 0.0

    allocation_metrics: list[dict] = []
    allocation_specs = (
        (
            "carry",
            {"RB"},
            "carry_share_mean_3",
            "carries_mean_3",
            "pregame_carry_share",
            "team_carries_mean_3",
        ),
        (
            "target",
            {"RB", "WR", "TE"},
            "target_share_mean_3",
            "targets_mean_3",
            "pregame_target_share",
            "team_targets_mean_3",
        ),
    )
    for (
        opportunity,
        allowed_positions,
        share_column,
        count_column,
        explicit_column,
        team_volume_column,
    ) in allocation_specs:
        eligible = positions.isin(allowed_positions)
        for team, indexes in rows.loc[eligible].groupby(teams).groups.items():
            index_list = list(indexes)
            group = rows.loc[index_list]
            prior_share = pd.to_numeric(group[share_column], errors="coerce").fillna(0.0).clip(lower=0.0)
            fallback_weight = prior_share.copy()
            coherent = group.get("opportunity_allocation_policy", pd.Series("legacy_v1", index=group.index)).eq("team_window_v2").all()
            policies = group.get("opportunity_allocation_policy", pd.Series("legacy_v1", index=group.index))
            if policies.eq("team_window_v2").any() and not coherent:
                raise ValueError("Mixed opportunity history policies in one team allocation")
            if coherent and not group["opportunity_history_team"].eq(str(team)).all():
                raise ValueError("Opportunity history team differs from current membership; rebuild same-team features")
            if coherent and prior_share.sum() > 1.000001:
                raise ValueError("Same-team opportunity shares exceed team volume; reconcile identities/windows")

            explicit_share = pd.to_numeric(group[explicit_column], errors="coerce")
            expected_column = (
                "pregame_expected_carries" if opportunity == "carry"
                else "pregame_expected_targets"
            )
            expected_counts = pd.to_numeric(group[expected_column], errors="coerce")
            known_team_volume = pd.to_numeric(
                group.get(team_volume_column, pd.Series(np.nan, index=group.index)),
                errors="coerce",
            ).dropna().clip(lower=0.0)
            known_team_volume = known_team_volume.loc[known_team_volume > 0]
            if not known_team_volume.empty:
                from_counts = expected_counts / float(known_team_volume.iloc[0])
                conflicting = (
                    explicit_share.notna() & from_counts.notna()
                    & (explicit_share - from_counts).abs().gt(0.02)
                )
                if conflicting.any():
                    raise ValueError(
                        f"Current {opportunity} share and expected count conflict "
                        f"for {team}; correct the pregame context evidence."
                    )
                explicit_share = explicit_share.where(explicit_share.notna(), from_counts)
            elif expected_counts.notna().any():
                raise ValueError(
                    f"Expected {opportunity} counts for {team} require a measured "
                    "team-volume estimate."
                )
            effective_column = f"pregame_effective_{opportunity}_share"
            source_column = f"{effective_column}_source"
            rows.loc[index_list, effective_column] = explicit_share
            rows.loc[index_list, source_column] = np.where(
                group[explicit_column].notna(), "explicit_share",
                np.where(expected_counts.notna(), "expected_count_divided_by_lagged_team_volume", None),
            )
            explicit_mask = explicit_share.notna()
            assigned = pd.Series(0.0, index=group.index)
            if coherent:
                # Keep measured shares rather than allocating a full remainder
                # to the subset of players present in this salary pool.
                assigned = prior_share.copy()
                assigned.loc[explicit_mask] = explicit_share.loc[explicit_mask]
                if float(explicit_share.loc[explicit_mask].sum()) > 1.000001:
                    raise ValueError(f"Effective {opportunity} share exceeds 1.0 for {team}")
                source = "same_team_common_window_with_explicit_context" if explicit_mask.any() else "same_team_common_window"
            elif explicit_mask.any():
                explicit_total = float(explicit_share.loc[explicit_mask].sum())
                if explicit_total > 1.000001:
                    raise ValueError(
                        f"Effective {opportunity} share exceeds 1.0 for {team}; "
                        "correct the current pregame context evidence."
                    )
                assigned.loc[explicit_mask] = explicit_share.loc[explicit_mask]
                remainder = max(0.0, 1.0 - float(assigned.sum()))
                unassigned = ~explicit_mask
                weights = fallback_weight.loc[unassigned]
                if unassigned.any() and remainder > 0:
                    if weights.sum() <= 0:
                        weights = pd.Series(0.0, index=weights.index)
                    if weights.sum() > 0:
                        assigned.loc[unassigned] = remainder * weights / weights.sum()
                source = "explicit_context_with_prior_opportunity"
            else:
                # Preserve missing opportunity, including QB carries and work
                # belonging to players omitted from the native salary pool.
                assigned = fallback_weight / max(1.0, float(fallback_weight.sum()))
                source = "lagged_opportunity_without_salary_inference"

            availability = pd.to_numeric(
                group["pregame_availability_probability"], errors="coerce"
            ).fillna(1.0).clip(lower=0.0, upper=1.0)
            available_share = assigned * availability
            # Genuine vacated work is prior same-team work, not an expanded
            # forward role or a former team's workload.
            removed_share = (prior_share if coherent else assigned) * (1.0 - availability)
            if coherent and available_share.sum() > 1.000001:
                fixed = float(available_share.loc[explicit_mask].sum())
                if fixed > 1.000001:
                    raise ValueError(f"Explicit expected {opportunity} volume exceeds team volume for {team}")
                other = ~explicit_mask
                total = float(available_share.loc[other].sum())
                if total > 0:
                    available_share.loc[other] *= max(0.0, 1.0 - fixed) / total
            redistribution_fractions = []
            recipient_mask = pd.Series(False, index=group.index)
            for context in group["player_id"].astype(str).map(context_by_player).tolist():
                context = context if isinstance(context, dict) else {}
                evidence = context.get("evidence_json") or context.get("evidence") or {}
                # Existing user scenarios explicitly model full generic team
                # redistribution. Real injury evidence never implies that.
                default_fraction = 1.0 if context.get("source") == "user_availability_scenario" else 0.0
                fraction = evidence.get(f"{opportunity}_redistribution_fraction", default_fraction) if isinstance(evidence, dict) else default_fraction
                fraction = float(fraction)
                if not 0.0 <= fraction <= 1.0:
                    raise ValueError(f"{opportunity} redistribution fraction must be between 0 and 1")
                redistribution_fractions.append(fraction)
            redistributed_share = float((removed_share * redistribution_fractions).sum())
            requested_redistribution = redistributed_share
            if coherent:
                # Explicit recipient counts may already consume vacated work.
                redistributed_share = min(redistributed_share, max(0.0, 1.0 - float(available_share.sum())))
            before_redistribution = available_share.copy()
            for i in index_list:
                context = context_by_player.get(str(rows.at[i, "player_id"]), {})
                facts = context.get("evidence_json") or context.get("evidence") or {}
                recipient_mask.at[i] = bool(
                    availability.at[i] > 0 and
                    (opportunity in facts.get("redistribution_opportunities", []) or
                     context.get("source") == "user_availability_scenario"))
            # Explicit fractions preserve the existing modeled scenario API;
            # otherwise use only sourced, named recipients of a promotion.
            has_fraction = any(f"{opportunity}_redistribution_fraction" in
                ((context_by_player.get(str(pid), {}).get("evidence_json") or
                  context_by_player.get(str(pid), {}).get("evidence") or {}))
                for pid in group["player_id"])
            user_scenario = any(c.get("source") == "user_availability_scenario" for c in context_by_player.values())
            if (has_fraction and not recipient_mask.any()) or user_scenario:
                recipient_mask = availability.gt(0)
            recipient_weights = available_share.where(recipient_mask, 0.0)
            if recipient_weights.sum() > 0:
                available_share += redistributed_share * recipient_weights / recipient_weights.sum()
            else:
                redistributed_share = 0.0

            team_volumes = pd.to_numeric(
                group.get(
                    team_volume_column,
                    pd.Series(0.0, index=group.index),
                ),
                errors="coerce",
            ).dropna().clip(lower=0.0)
            positive_team_volumes = team_volumes.loc[team_volumes > 0]
            if not positive_team_volumes.empty:
                if not np.allclose(
                    positive_team_volumes,
                    float(positive_team_volumes.iloc[0]),
                    rtol=1e-6,
                    atol=1e-6,
                ):
                    raise ValueError(
                        f"Inconsistent prior team {opportunity} volume for {team}; "
                        "rebuild the canonical feature slice."
                    )
                team_volume = float(positive_team_volumes.iloc[0])
                team_volume_source = "lagged_full_team_volume"
            else:
                prior_counts = pd.to_numeric(
                    group[count_column], errors="coerce"
                ).fillna(0.0).clip(lower=0.0)
                team_volume = float(prior_counts.sum())
                team_volume_source = "active_player_history_fallback"
            rows.loc[index_list, share_column] = available_share
            rows.loc[index_list, count_column] = available_share * team_volume
            context_applied = bool(
                explicit_mask.any() or (removed_share.sum() > 1e-12 if coherent else not np.allclose(availability, 1.0))
            )
            if context_applied:
                rows.loc[index_list, "pregame_opportunity_context_applied"] = True
            allocation_metrics.append(
                {
                    "team": str(team),
                    "opportunity": opportunity,
                    "source": source,
                    "team_volume": team_volume,
                    "team_volume_source": team_volume_source,
                    "player_projected_volume_sum": float((available_share * team_volume).sum()),
                    "unallocated_volume": max(
                        0.0, team_volume - float((available_share * team_volume).sum())
                    ),
                    "explicit_player_count": int(explicit_mask.sum()),
                    "player_count": len(index_list),
                    "allocated_share": float(available_share.sum()),
                    "removed_share": float(removed_share.sum()),
                    "redistributed_share": redistributed_share,
                    "requested_redistribution_share": requested_redistribution,
                    "history_policy": "team_window_v2" if coherent else "legacy_v1",
                    "historical_share_sum": float(prior_share.sum()),
                    "historical_unrepresented_volume": max(0.0, 1.0 - float(prior_share.sum())) * team_volume if coherent else None,
                    "players": [dict(player_id=str(rows.at[i, "player_id"]),
                        prior_volume=float(assigned.at[i] * team_volume),
                        historical_volume=float(prior_share.at[i] * team_volume),
                        history_status=rows.at[i, "opportunity_history_status"] if coherent else None,
                        vacated_volume=float(removed_share.at[i] * team_volume),
                        received_volume=float((available_share.at[i] - before_redistribution.at[i]) * team_volume),
                        expected_volume=float(available_share.at[i] * team_volume),
                        recipient_supported=bool(recipient_mask.at[i])) for i in index_list],
                }
            )

    base_workload = (
        rows["pregame_base_carries_mean_3"]
        + rows["pregame_base_targets_mean_3"]
    )
    adjusted_workload = (
        pd.to_numeric(rows["carries_mean_3"], errors="coerce").fillna(0.0)
        + pd.to_numeric(rows["targets_mean_3"], errors="coerce").fillna(0.0)
    )
    rows["pregame_workload_multiplier"] = np.where(
        base_workload > 0,
        adjusted_workload / base_workload,
        np.nan,
    )
    rows["pregame_workload_adjustment_source"] = np.where(
        rows["pregame_opportunity_context_applied"],
        "current_pregame_context",
        np.where(
            positions.isin({"RB", "WR", "TE"}),
            "team_opportunity_reallocation",
            "not_applicable",
        ),
    )

    # Historical production and snap share remain immutable historical inputs.
    # Current workload is applied to the point estimate explicitly after the
    # base model runs, with its own persisted lineage.
    rows["pregame_availability_probability"] = pd.to_numeric(
        rows["pregame_availability_probability"], errors="coerce"
    ).fillna(1.0).clip(lower=0.0, upper=1.0)
    rows["pregame_start_probability"] = pd.to_numeric(
        rows["pregame_start_probability"], errors="coerce"
    ).fillna(1.0).clip(lower=0.0, upper=1.0)
    unavailable = (
        rows["pregame_availability_probability"].le(0.0)
        & rows["pregame_context_source"].eq("user_availability_scenario")
    )
    rows.loc[
        unavailable,
        [
            "pregame_expected_snaps", "pregame_expected_routes",
            "pregame_expected_carries", "pregame_expected_targets",
            "pregame_red_zone_share", "pregame_goal_line_share",
        ],
    ] = 0.0
    rows["snap_share_mean_3"] = pd.to_numeric(
        rows["snap_share_mean_3"], errors="coerce"
    ).fillna(0.0).clip(lower=0.0, upper=1.0)
    return rows, {
        "source": "public.starting_qb_evidence + public.pregame_player_context",
        "role_availability_audit": role_audit,
        "context_player_count": len(context_by_player),
        "context_run_ids": sorted(
            str(value)
            for value in rows["pregame_context_run_id"].dropna().unique().tolist()
        ),
        "starting_qb_teams": sorted(selected_by_team),
        "allocation_policy": (
            "team carry/target shares before point scoring; explicit context first; "
            "lagged opportunity without salary inference; removed work unallocated "
            "unless an explicit redistribution assumption/evidence supplies recipients"
        ),
        "allocations": allocation_metrics,
        "team_pass_attempts": None,
        "team_rush_attempts": None,
        "team_red_zone_opportunities": None,
        "unavailable_volume_note": (
            "Full team pass attempts, all-position rush attempts, and red-zone "
            "opportunities are not independently forecast; target and RB carry "
            "volumes are lagged team proxies, not complete play-volume models."
        ),
    }


def add_position_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Add stable one-hot position inputs shared by training and scoring."""
    rows = frame.copy()
    positions = rows["position"].fillna("").astype(str).str.upper()
    for position in sorted(SUPPORTED_POSITIONS):
        rows[f"position_{position.lower()}"] = positions.eq(position).astype(float)
    return rows


def prepare_inputs(
    matrix: pd.DataFrame,
    salaries: pd.DataFrame,
    participation: pd.DataFrame | None = None,
    weekly_stats: pd.DataFrame | None = None,
    starting_qbs: pd.DataFrame | None = None,
    pregame_context: pd.DataFrame | None = None,
    market_rows: pd.DataFrame | None = None,
    *,
    season: int,
    week: int,
    slate: str,
    cutoff: datetime,
    positions: list[str] | None = None,
    availability_overrides: list[dict] | None = None,
    allow_confirmed_inactive_override: bool = False,
    assume_questionable_out: bool = False,
    preliminary_exclude_unknown: bool = False,
    injury_statuses: pd.DataFrame | None = None,
    opportunity_allocation_policy: str = "legacy_v1",
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Return training and scoring rows using canonical UUIDs only."""
    from .predictions import TARGET_COL, select_training_rows_before_cutoff

    cutoff = pd.Timestamp(cutoff)
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("UTC")
    requested = {p.upper() for p in positions} if positions else SUPPORTED_POSITIONS
    unsupported = requested - SUPPORTED_POSITIONS
    if unsupported:
        raise ValueError(f"Projection features do not support positions: {', '.join(sorted(unsupported))}.")
    salaries = salaries.loc[
        (salaries["season"] == season) & (salaries["week"] == week)
        & (salaries["slate"].str.upper() == slate.upper())
        & (salaries["source_system"] == "draftkings")
        & (pd.to_datetime(salaries["created_at"], utc=True) <= cutoff)
    ].copy()
    if salaries.empty:
        raise ValueError(f"No canonical salaries available by cutoff for {season} week {week} slate {slate}.")
    source_salary_ingest_run_ids = sorted(
        salaries["ingest_run_id"].dropna().astype(str).unique().tolist()
    )
    if "player_status" not in salaries.columns:
        salaries["player_status"] = None
    all_slate_salaries = salaries.copy()
    canonical_context = {str(r.get("player_master_id") or r.get("player_id")): r
                         for r in (pregame_context.to_dict("records") if pregame_context is not None else [])
                         if (r.get("evidence_json") or {}).get("canonical_context_contract") == CONTEXT_CONTRACT}
    specialist_ids = set()
    classic_scope = None
    role_excluded_ids = set()
    quarantine_ids = set()
    preliminary_excluded_ids = set()
    if canonical_context:
        from ..config import get_settings
        classic = not salaries['roster_position'].fillna('').str.upper().eq('CPT').any()
        max_age = (get_settings().classic_player_status_max_age_hours if classic
                   else get_settings().showdown_player_status_max_age_hours)
        if classic:
            from .classic_player_pool import assess_pool_player
            classic_scope = {pid: assess_pool_player({**r['evidence_json'], 'position': r.get('position')},
                cutoff=cutoff, evaluated_at=cutoff, max_age_hours=max_age) for pid, r in canonical_context.items()}
            role_excluded_ids = {pid for pid, assessment in classic_scope.items() if assessment['role_exclusion_policy']}
            quarantine_ids = {pid for pid, assessment in classic_scope.items() if assessment['quarantine']}
        assessed = {pid: assess_availability({**r["evidence_json"], "position": r.get("position")},
                    cutoff=cutoff, evaluated_at=cutoff, max_age_hours=max_age)[0]
                    for pid,r in canonical_context.items()}
        missing_status = sorted({str(pid) for pid in salaries["player_master_id"].dropna() if
            assessed.get(str(pid), "UNKNOWN") == "UNKNOWN" and str(pid) not in quarantine_ids})
        if classic_scope:
            missing_status = sorted(set(missing_status) | {str(pid) for pid in salaries['player_master_id'].dropna()
                if assessed.get(str(pid)) != 'UNAVAILABLE' and str(pid) not in role_excluded_ids
                and canonical_context.get(str(pid), {}).get('position') != 'DST'
                and not classic_scope.get(str(pid), {}).get('role_current')})
        if missing_status and preliminary_exclude_unknown:
            if not classic:
                raise ValueError("Preliminary unknown exclusions require Classic format")
            preliminary_excluded_ids = set(missing_status)
        if missing_status and not preliminary_exclude_unknown:
            names = {str(r.player_master_id): str(r.player_name) for r in salaries.itertuples(index=False)}
            raise PlayerContextUnresolved(
                "Current player availability or depth-chart role needs verification for "
                + ", ".join(names.get(pid, pid) for pid in missing_status)
                + ". Prepare the slate again to refresh roster, injury and depth-chart evidence."
            )
        specialist_ids = {pid for pid,r in canonical_context.items() if assessed[pid] == "AVAILABLE"
            and is_excluded_specialist(r["evidence_json"], cutoff=cutoff, evaluated_at=cutoff,
                                      max_age_hours=max_age)}
        # Current canonical facts supersede the original salary status only
        # where their source clocks established a deterministic disposition.
        salaries["player_status"] = [canonical_context[str(pid)]["evidence_json"].get("availability_status")
                                     if str(pid) in canonical_context else value
                                     for pid,value in zip(salaries["player_master_id"],salaries["player_status"],strict=True)]
    salaries["normalized_player_status"] = salaries["player_status"].map(
        normalize_salary_status
    )
    eligibility_mask = salaries["player_status"].map(is_salary_status_eligible)
    if canonical_context:
        eligibility_mask = salaries["player_master_id"].map(lambda pid:
            canonical_context.get(str(pid), {}).get("evidence_json", {}).get("availability_state") == "AVAILABLE")
    # Unknown quarantines and unresolved identities are not injury facts.
    unavailable = salaries.loc[~eligibility_mask & salaries["player_master_id"].astype(str).isin(
        {pid for pid, state in assessed.items() if state == 'UNAVAILABLE'})].copy() if canonical_context else salaries.loc[~eligibility_mask].copy()
    normalized_names = unavailable.get(
        "normalized_name",
        unavailable["player_name"].fillna("").astype(str).str.strip().str.lower(),
    )
    unavailable["eligibility_player_key"] = unavailable["player_master_id"].fillna(
        normalized_names.fillna("").astype(str)
        + "|"
        + unavailable["team"].fillna("").astype(str)
        + "|"
        + unavailable["position"].fillna("").astype(str)
    )
    excluded_status_players = (
        unavailable.sort_values(["created_at", "curated_salary_id"])
        .drop_duplicates("eligibility_player_key", keep="last")
    )
    excluded_salary_status_rows = [
        {
            "player_master_id": (
                str(row.player_master_id)
                if pd.notna(row.player_master_id)
                else None
            ),
            "player_name": str(row.player_name) if pd.notna(row.player_name) else "",
            "team": str(row.team) if pd.notna(row.team) else "",
            "position": str(row.position) if pd.notna(row.position) else "",
            "status": str(row.normalized_player_status),
            "ingest_run_id": (
                str(row.ingest_run_id) if pd.notna(row.ingest_run_id) else ""
            ),
        }
        for row in excluded_status_players.itertuples(index=False)
    ]
    excluded_salary_row_ids = unavailable["curated_salary_id"].astype(int).tolist()
    # Role exclusions are independent of unavailable salary/status exclusions.
    specialist_mask = salaries["player_master_id"].astype(str).isin(specialist_ids | role_excluded_ids)
    excluded_specialist_salary_row_ids = salaries.loc[specialist_mask, "curated_salary_id"].astype(int).tolist()
    salaries = salaries.loc[eligibility_mask & ~specialist_mask & ~salaries["player_master_id"].astype(str).isin(preliminary_excluded_ids)].copy()
    if salaries.empty:
        raise ValueError(
            f"No eligible canonical salaries available for {season} week {week} slate {slate}; "
            "all salary players are unavailable or sourced unsupported specialists."
        )
    roster_eligibility_policy = {
        "source": "public.curated_player_game_participation",
        "available": False,
        "eligible_statuses": ["ACT"],
        "dst_policy": "retained_without_player_roster_evidence",
        "excluded_player_count": 0,
        "excluded_row_count": 0,
        "excluded_salary_row_ids": [],
        "excluded_players": [],
    }
    roster_columns = {
        "season",
        "week",
        "player_master_id",
        "team",
        "roster_status",
    }
    if not canonical_context and participation is not None and roster_columns.issubset(participation.columns):
        roster = participation.loc[
            (participation["season"] == season)
            & (participation["week"] == week)
        ].copy()
        if "created_at" in roster.columns:
            roster = roster.loc[
                pd.to_datetime(roster["created_at"], utc=True) <= cutoff
            ].copy()
        roster = roster.loc[roster["player_master_id"].notna()].copy()
        if roster["roster_status"].notna().any():
            roster["player_master_id"] = roster["player_master_id"].astype(str)
            roster["team_key"] = roster["team"].map(normalize_team)
            sort_columns = [
                column
                for column in (
                    "created_at",
                    "curated_player_game_participation_id",
                )
                if column in roster.columns
            ]
            if sort_columns:
                roster = roster.sort_values(sort_columns)
            roster = roster.drop_duplicates(
                ["player_master_id", "team_key"], keep="last"
            )
            roster_lookup = {
                (str(row.player_master_id), str(row.team_key)): (
                    str(row.roster_status).strip().upper()
                    if pd.notna(row.roster_status)
                    else "MISSING"
                )
                for row in roster.itertuples(index=False)
            }
            # Weekly ingestion can cover only one slate. Other teams have no
            # roster evidence yet; that absence must not become an inactive
            # designation just because another team has loaded records.
            covered_teams = set(roster["team_key"].dropna())
            salary_team_keys = salaries["team"].map(normalize_team)
            roster_eligibility_policy["covered_teams"] = sorted(covered_teams)
            roster_eligibility_policy["missing_teams"] = sorted(
                set(salary_team_keys.dropna()) - covered_teams
            )
            salaries["current_roster_status"] = [
                roster_lookup.get(
                    (
                        str(player_id),
                        normalize_team(team) if pd.notna(team) else "",
                    ),
                    "MISSING",
                )
                for player_id, team in zip(
                    salaries["player_master_id"], salaries["team"], strict=True
                )
            ]
            position_keys = salaries["position"].fillna("").astype(str).str.upper()
            unavailable_roster_mask = (
                position_keys.isin(requested)
                & ~position_keys.isin({"D", "DEF", "DST"})
                & salary_team_keys.isin(covered_teams)
                & salaries["current_roster_status"].ne("ACT")
            )
            unavailable_roster = salaries.loc[unavailable_roster_mask].copy()
            unavailable_roster["eligibility_player_key"] = (
                unavailable_roster["player_master_id"].fillna("").astype(str)
                + "|"
                + unavailable_roster["team"].fillna("").astype(str)
                + "|"
                + unavailable_roster["position"].fillna("").astype(str)
            )
            excluded_roster_players = (
                unavailable_roster.sort_values(["created_at", "curated_salary_id"])
                .drop_duplicates("eligibility_player_key", keep="last")
            )
            roster_eligibility_policy.update(
                {
                    "available": True,
                    "excluded_player_count": int(len(excluded_roster_players)),
                    "excluded_row_count": int(len(unavailable_roster)),
                    "excluded_salary_row_ids": unavailable_roster[
                        "curated_salary_id"
                    ].astype(int).tolist(),
                    "excluded_players": [
                        {
                            "player_master_id": (
                                str(row.player_master_id)
                                if pd.notna(row.player_master_id)
                                else None
                            ),
                            "player_name": (
                                str(row.player_name)
                                if pd.notna(row.player_name)
                                else ""
                            ),
                            "team": str(row.team) if pd.notna(row.team) else "",
                            "position": (
                                str(row.position) if pd.notna(row.position) else ""
                            ),
                            "roster_status": str(row.current_roster_status),
                            "ingest_run_id": (
                                str(row.ingest_run_id)
                                if pd.notna(row.ingest_run_id)
                                else ""
                            ),
                        }
                        for row in excluded_roster_players.itertuples(index=False)
                    ],
                }
            )
            salaries = salaries.loc[~unavailable_roster_mask].copy()
            if salaries.empty:
                raise ValueError(
                    f"No roster-eligible canonical salaries available for {season} "
                    f"week {week} slate {slate}."
                )
    unresolved = all_slate_salaries.loc[all_slate_salaries["player_master_id"].isna(), "source_player_key"].tolist()
    if unresolved:
        raise ValueError(f"Resolve {len(unresolved)} salary identities before projections: "
                         + ", ".join(map(str, unresolved[:20])))
    excluded_positions = sorted(set(salaries["position"].dropna()) - requested)
    salaries = salaries.loc[
        salaries["player_master_id"].notna() & salaries["position"].isin(requested)
    ].copy()
    salaries["role_order"] = salaries["roster_position"].str.upper().eq("CPT").astype(int)
    salaries = salaries.sort_values(
        ["role_order", "created_at", "curated_salary_id"], ascending=[True, False, False]
    ).drop_duplicates("player_master_id")
    if salaries.empty:
        raise ValueError("No resolved canonical salary players in the requested positions.")
    if matrix.empty:
        raise ValueError("No player-game feature matrix exists. Build features before running projections.")
    matrix = matrix.loc[
        (matrix["source_system"] == "draftkings")
        & matrix["player_master_id"].notna()
        & (pd.to_datetime(matrix["created_at"], utc=True) <= cutoff)
    ].copy()
    matrix["player_id"] = matrix["player_master_id"].astype(str)
    matrix[TARGET_COL] = pd.to_numeric(matrix["dk_points"], errors="coerce")
    matrix["player_display_name"] = matrix["player_name"]
    matrix["recent_team"] = matrix["team"]
    matrix["opponent_team"] = matrix["opponent"]
    for column in BASE_FEATURE_COLUMNS:
        numeric = pd.to_numeric(matrix[column], errors="coerce")
        matrix[column] = numeric if column in MARKET_FEATURE_COLUMNS else numeric.fillna(0.0)
    matrix, participation_metrics = attach_lagged_participation_features(
        matrix,
        participation,
        cutoff=cutoff,
    )
    matrix, opportunity_metrics = attach_lagged_opportunity_features(
        matrix,
        weekly_stats,
        cutoff=cutoff,
        policy=opportunity_allocation_policy,
    )
    from .offensive_role import attach_offensive_role
    matrix = attach_offensive_role(matrix)
    matrix = add_position_features(matrix)
    # A player can appear in several slate builds; a game is one training sample.
    matrix = matrix.sort_values(["created_at", "player_game_feature_matrix_id"])
    train = select_training_rows_before_cutoff(matrix, target_season=season, target_week=week)
    train = train.loc[train["position"].isin(requested)].drop_duplicates(
        ["season", "week", "player_id", "position"], keep="last"
    )
    training_rows_before_participation_filter = len(train)
    if participation_metrics["available"]:
        train = train.loc[
            train["position"].eq("DST")
            | train["training_participation_status"].isin(
                PLAYED_PARTICIPATION_STATUSES
            )
        ].copy()
    outcome_audit = validate_completed_training_outcomes(train, weekly_stats)
    participation_metrics.update(
        {
            "training_rows_before_filter": int(
                training_rows_before_participation_filter
            ),
            "training_rows_after_filter": int(len(train)),
            "excluded_training_rows": int(
                training_rows_before_participation_filter - len(train)
            ),
            "accepted_statuses": sorted(PLAYED_PARTICIPATION_STATUSES),
            "dst_policy": "retained_without_player_participation",
        }
    )
    if train.empty:
        raise ValueError(f"No labeled canonical feature rows before {season} week {week}. Build historical features first.")
    train, historical_market_audit = reconcile_training_market_context(
        train, market_rows if market_rows is not None else pd.DataFrame(),
    )
    target = matrix.loc[
        (matrix["season"] == season) & (matrix["week"] == week)
        & matrix["slate"].fillna("").str.upper().eq(slate.upper())
    ].drop_duplicates("player_id", keep="last").set_index("player_id", drop=False)
    ids = salaries["player_master_id"].astype(str).tolist()
    missing = sorted(set(ids) - set(target.index))
    if missing:
        raise ValueError(
            f"Missing canonical features for {len(missing)} resolved salary players in {slate}; "
            f"build features for this slate before retrying. Player IDs: {', '.join(missing)}"
        )
    target = target.loc[ids].copy().reset_index(drop=True)
    # Keep excluded starter history in the allocation audit. Removing IR salary
    # rows before measuring vacated work used to silently normalize it away.
    removed_salaries = all_slate_salaries.loc[
        all_slate_salaries["player_master_id"].notna()
        & ~all_slate_salaries["player_master_id"].astype(str).isin(ids)
        & all_slate_salaries["position"].isin(requested)
    ].sort_values(["created_at", "curated_salary_id"]).drop_duplicates("player_master_id", keep="last")
    removed_ids = set(removed_salaries["player_master_id"].astype(str))
    removed_features = matrix.loc[
        matrix["season"].eq(season) & matrix["week"].eq(week)
        & matrix["slate"].fillna("").str.upper().eq(slate.upper())
        & matrix["player_id"].astype(str).isin(removed_ids)
    ].drop_duplicates("player_id", keep="last").copy()
    removed_salary_lookup = removed_salaries.assign(
        player_master_id=removed_salaries["player_master_id"].astype(str)).set_index("player_master_id")
    for output, source in [("salary", "salary"), ("recent_team", "team"),
                           ("opponent_team", "opponent"), ("position", "position"),
                           ("player_display_name", "player_name")]:
        removed_features[output] = removed_features["player_id"].map(removed_salary_lookup[source])
    removed_features["player_status"] = "OUT"
    salary_by_id = salaries.set_index("player_master_id")
    for output, source in [("salary", "salary"), ("player_status", "player_status"),
                           ("recent_team", "team"),
                           ("opponent_team", "opponent"), ("position", "position"),
                           ("player_display_name", "player_name")]:
        target[output] = target["player_id"].map(salary_by_id[source])
    target = add_position_features(target)
    target, market_audit = apply_latest_market_context(
        target,
        (market_rows.loc[
            market_rows["season"].eq(season) & market_rows["week"].eq(week)
        ] if market_rows is not None and not market_rows.empty
         else pd.DataFrame()), cutoff=cutoff,
    )
    if assume_questionable_out:
        availability_overrides = [*(availability_overrides or []),
            *_questionable_snapshot_overrides(target, pregame_context, injury_statuses)]
    pregame_context, availability_override_audit = apply_player_availability_overrides(
        target,
        pregame_context,
        availability_overrides,
        allow_confirmed_inactive_override=allow_confirmed_inactive_override,
        assume_questionable_out=assume_questionable_out,
    )
    allocation_input = pd.concat([target, removed_features], ignore_index=True)
    if opportunity_allocation_policy == "team_window_v2":
        # Salary/role membership can supersede matrix team; rebuild after that
        # mapping so old matrix-team evidence cannot enter a current team.
        allocation_input, _ = attach_lagged_opportunity_features(
            allocation_input, weekly_stats, cutoff=cutoff, policy=opportunity_allocation_policy)
    allocation_rows, pregame_metrics = apply_pregame_projection_context(
        allocation_input,
        starting_qbs=starting_qbs,
        pregame_context=pregame_context,
    )
    target = allocation_rows.loc[allocation_rows["player_id"].astype(str).isin(ids)].copy().reset_index(drop=True)
    pregame_metrics["excluded_opportunity_players_without_features"] = sorted(removed_ids - set(removed_features["player_id"].astype(str)))
    market_starter_sanity: list[dict] = []
    for team, team_rows in target.groupby("recent_team"):
        first = team_rows.iloc[0]
        starter_at = pd.to_datetime(
            first.get("team_starting_qb_observed_at"), utc=True, errors="coerce"
        )
        market_at = pd.to_datetime(
            first.get("market_observed_at"), utc=True, errors="coerce"
        )
        if pd.isna(starter_at):
            continue
        status = (
            "market_missing_after_starter_evidence" if pd.isna(market_at)
            else "market_older_than_starter_evidence" if market_at < starter_at
            else "market_observed_after_starter_evidence"
        )
        market_starter_sanity.append({
            "team": str(team), "starter": first.get("team_starting_qb_name"),
            "starter_evidence_at": starter_at.isoformat(),
            "market_observed_at": market_at.isoformat() if pd.notna(market_at) else None,
            "status": status,
        })
    target["official_availability_status"] = None
    target["availability_override"] = "default"
    target["model_availability_used"] = target["pregame_availability_probability"]
    target["opportunity_redistributed"] = False
    for override in availability_override_audit:
        mask = target["player_id"].astype(str).eq(str(override["player_id"]))
        for column in (
            "official_availability_status", "availability_override",
            "model_availability_used", "opportunity_redistributed",
        ):
            target.loc[mask, column] = override[column]
    role_inputs = target.copy()
    for opportunity in ("carry", "target"):
        share = f"{opportunity}_share_mean_3"
        explicit = f"pregame_effective_{opportunity}_share"
        role_inputs[share] = target[explicit].where(
            target[explicit].notna(), target[f"pregame_base_{share}"]
        )
        role_inputs[f"{share}_available"] = (
            target[f"{share}_available"] | target[explicit].notna()
        )
    refreshed_roles = attach_offensive_role(role_inputs)
    for column in (
        "offensive_role_importance", "offensive_role_completeness",
        "offensive_role_evidence", "offensive_role_class", "offensive_role_reason",
        "offensive_role_confidence", "offensive_role_source",
    ):
        target[column] = refreshed_roles[column]
    # Importance is calculated from prior observed shares, not from the salary
    # fallback used to allocate this week's incomplete opportunity pool.
    target["projected_carries"] = target["carries_mean_3"].where(
        target["team_carries_mean_3_available"]
        & target["position"].fillna("").astype(str).str.upper().eq("RB"),
        np.nan,
    )
    target["projected_targets"] = target["targets_mean_3"].where(
        target["team_targets_mean_3_available"]
        & target["position"].fillna("").astype(str).str.upper().isin({"RB", "WR", "TE"}),
        np.nan,
    )
    if opportunity_allocation_policy == "team_window_v2":
        for kind, count in (("carry", "carries"), ("target", "targets")):
            supported = target[f"{count}_mean_3_available"] | target[f"pregame_effective_{kind}_share"].notna()
            target[f"projected_{count}"] = target[f"projected_{count}"].where(supported, np.nan)
    target["projected_opportunity_source"] = np.where(
        target["team_targets_mean_3_available"] | target["team_carries_mean_3_available"],
        "lagged_team_volume_with_evidence_supported_redistribution", "unavailable",
    )
    if opportunity_allocation_policy == "team_window_v2":
        supported = target["projected_carries"].notna() | target["projected_targets"].notna()
        applicable = target["position"].isin({"RB", "WR", "TE"})
        target["projected_opportunity_source"] = np.where(
            applicable, np.where(supported, "same_team_common_window_with_evidence_supported_context",
                                 "unavailable_same_team_history"), "not_applicable")
    # Future matrix rows currently store zero actuals. They are never labels.
    target[TARGET_COL] = float("nan")
    metadata = {
        "source": "public.player_game_feature_matrix",
        "salary_source": "public.curated_salary",
        "preliminary_research": {"enabled": preliminary_exclude_unknown, "policy": "exclude_unknown_availability_or_role",
            "exclude_player_ids": sorted(preliminary_excluded_ids), "entry_ready": False},
        "canonical_player_pool": {
            "contract_id": CONTEXT_CONTRACT if canonical_context else None,
            "generation_eligible_player_ids": sorted(salaries["player_master_id"].dropna().astype(str).unique()),
            "scoring_player_ids": sorted(target["player_id"].dropna().astype(str).unique()),
            "explicitly_unavailable_player_ids": sorted(excluded_status_players["player_master_id"].dropna().astype(str).unique()),
            "explicitly_excluded_specialist_player_ids": sorted(specialist_ids),
            "specialist_exclusion_reason": "unsupported_non_scoring_specialist_role",
            "excluded_specialist_salary_row_ids": excluded_specialist_salary_row_ids,
            "quarantined_unresolved_player_ids": sorted(quarantine_ids),
            "role_ineligible_player_ids": sorted(role_excluded_ids - quarantine_ids),
            "materiality_assessments": classic_scope,
        },
        "salary_ingest_run_ids": source_salary_ingest_run_ids,
        "salary_row_ids": salaries["curated_salary_id"].astype(int).tolist(),
        "salary_status_policy": {
            "source_column": "public.curated_salary.player_status",
            "ineligible_statuses": sorted(INELIGIBLE_SALARY_STATUSES),
            "excluded_player_count": len(excluded_salary_status_rows),
            "excluded_row_count": len(excluded_salary_row_ids),
            "excluded_salary_row_ids": excluded_salary_row_ids,
            "excluded_players": excluded_salary_status_rows,
        },
        "roster_eligibility_policy": roster_eligibility_policy,
        "training_matrix_row_ids": train["player_game_feature_matrix_id"].astype(int).tolist(),
        "scoring_matrix_row_ids": target["player_game_feature_matrix_id"].astype(int).tolist(),
        "unresolved_salary_source_keys": unresolved,
        "excluded_positions": excluded_positions,
        "participation_filter": participation_metrics,
        "training_outcome_audit": outcome_audit,
        "opportunity_features": opportunity_metrics,
        "pregame_context": pregame_metrics,
        "market_context": {
            "source": "cutoff-safe market observations; team_rows retain consumed source and snapshot ID",
            "team_rows": market_audit,
            "starter_sanity": market_starter_sanity,
            "historical_training_reconciliation": historical_market_audit,
        },
        "availability_scenario": {
            "overrides": availability_override_audit,
            "assume_questionable_out": assume_questionable_out,
            "allow_confirmed_inactive_override": allow_confirmed_inactive_override,
            "policy": "user scenario before generic team opportunity allocation",
        },
        "target_season": season, "target_week": week, "target_slate": slate,
        "leakage_policy": (
            "pregame feature allowlist; labeled rows strictly before target season/week; "
            "historical participation filters labels only; snap share uses prior games only; "
            "opportunity features use prior games only; pregame evidence must be observed "
            "and received by cutoff; "
            "inputs created by cutoff"
        ),
    }
    return train, target, metadata


def load_inputs(
    engine, *, season, week, slate, cutoff, positions=None,
    availability_overrides=None, allow_confirmed_inactive_override=False,
    assume_questionable_out=False,
    opportunity_allocation_policy=None,
    preliminary_exclude_unknown=False,
):
    if opportunity_allocation_policy is None:
        from ..config import get_settings
        opportunity_allocation_policy = get_settings().player_opportunity_allocation_policy
    if not slate or not slate.strip():
        raise ValueError("A selected slate is required for canonical projections.")
    naive_cutoff = cutoff.astimezone(timezone.utc).replace(tzinfo=None)
    with engine.connect() as connection:
        salaries = pd.read_sql(select(CuratedSalary).where(
            CuratedSalary.season == season, CuratedSalary.week == week,
            CuratedSalary.created_at <= naive_cutoff,
        ), connection)
        matrix = pd.read_sql(select(PlayerGameFeatureMatrix).where(
            PlayerGameFeatureMatrix.season <= season,
            PlayerGameFeatureMatrix.created_at <= naive_cutoff,
        ), connection)
        participation = pd.DataFrame()
        if inspect(engine).has_table("curated_player_game_participation"):
            participation = pd.read_sql(
                select(CuratedPlayerGameParticipation).where(
                    CuratedPlayerGameParticipation.season <= season,
                    CuratedPlayerGameParticipation.position.in_(
                        sorted(SUPPORTED_POSITIONS - {"DST"})
                    ),
                    CuratedPlayerGameParticipation.created_at <= naive_cutoff,
                ),
                connection,
            )
        weekly_stats = pd.DataFrame()
        starting_qbs = pd.DataFrame()
        market_rows = pd.DataFrame()
        pregame_context = pd.DataFrame()
        injury_statuses = pd.DataFrame()
        db_inspector = inspect(engine)
        if assume_questionable_out and engine.dialect.name == "postgresql" and db_inspector.has_table(
            "snapshot_injury_status", schema="target"
        ):
            injury_statuses = pd.read_sql(
                text(f"""
                    SELECT DISTINCT ON (player_id) snapshot_injury_id, player_id,
                           injury_status, as_of, source
                    FROM target.snapshot_injury_status
                    WHERE season = :season AND week = :week
                      AND (slate IS NULL OR {injury_slate_sql('slate')})
                      AND as_of IS NOT NULL AND as_of <= :cutoff
                    ORDER BY player_id, as_of DESC, snapshot_injury_id DESC
                """), connection,
                params={"season": season, "week": week, "slate": slate, "cutoff": naive_cutoff},
            )
        if engine.dialect.name == "postgresql" and db_inspector.has_table(
            "raw_nfl_weekly_stat", schema="public"
        ) and db_inspector.has_table("player_alias", schema="public"):
            weekly_stats = pd.read_sql(
                text(
                    """
                    WITH latest_weekly_stat AS (
                        SELECT DISTINCT ON (season, week, player_id)
                            raw_nfl_weekly_stat_id, season, week, player_id,
                            team, position, raw_row_json, created_at
                        FROM public.raw_nfl_weekly_stat
                        WHERE season <= :season
                          AND created_at <= :cutoff
                        ORDER BY season, week, player_id,
                                 created_at DESC, raw_nfl_weekly_stat_id DESC
                    )
                    SELECT
                        raw.raw_nfl_weekly_stat_id,
                        raw.season,
                        raw.week,
                        raw.player_id AS source_player_id,
                        alias.player_master_id,
                        raw.team,
                        raw.position,
                        COALESCE(
                            NULLIF(raw.raw_row_json ->> 'carries', '')::DOUBLE PRECISION,
                            NULLIF(raw.raw_row_json ->> 'rushing_attempts', '')::DOUBLE PRECISION
                        ) AS carries,
                        NULLIF(raw.raw_row_json ->> 'targets', '')::DOUBLE PRECISION AS targets,
                        raw.created_at
                    FROM latest_weekly_stat raw
                    LEFT JOIN public.player_alias alias
                      ON alias.source_system = 'nflreadpy'
                     AND alias.source_key = raw.player_id
                    ORDER BY raw.season, raw.week, raw.player_id
                    """
                ),
                connection,
                params={"season": season, "cutoff": naive_cutoff},
            )
        if engine.dialect.name == "postgresql" and db_inspector.has_table(
            "starting_qb_evidence", schema="public"
        ):
            starting_qbs = pd.read_sql(
                text(
                    """
                    SELECT starting_qb_id, team, player_id, player_master_id,
                           player_name, source, evidence_tier, evidence_json,
                           created_at, updated_at
                    FROM public.starting_qb_evidence
                    WHERE season = :season
                      AND week = :week
                      AND UPPER(slate) = UPPER(:slate)
                      AND created_at <= :cutoff
                    ORDER BY team, created_at DESC, starting_qb_id DESC
                    """
                ),
                connection,
                params={
                    "season": season,
                    "week": week,
                    "slate": slate,
                    "cutoff": naive_cutoff,
                },
            ).drop_duplicates("team", keep="first")
        if engine.dialect.name == "postgresql" and db_inspector.has_table(
            "raw_nfl_schedule", schema="public"
        ):
            market_rows = pd.read_sql(
                text("""
                    SELECT DISTINCT ON (season, week, home_team, away_team)
                           raw_nfl_schedule_id, source_system, season, week, game_id,
                           home_team, away_team, kickoff, raw_row_json, created_at
                    FROM public.raw_nfl_schedule
                    WHERE (season < :season OR (season = :season AND week < :week))
                      AND created_at <= :cutoff
                      AND raw_row_json ->> 'total_line' IS NOT NULL
                      AND raw_row_json ->> 'spread_line' IS NOT NULL
                    ORDER BY season, week, home_team, away_team, created_at DESC,
                             raw_nfl_schedule_id DESC
                """),
                connection,
                params={"season": season, "week": week, "cutoff": naive_cutoff},
            )
        if engine.dialect.name == "postgresql" and db_inspector.has_table(
            "market_snapshot", schema="target"
        ):
            from .market_snapshots import load_current_markets
            current_markets = pd.DataFrame(load_current_markets(connection,season=season,week=week,cutoff=cutoff))
            market_rows = pd.concat([market_rows, current_markets], ignore_index=True)
        if engine.dialect.name == "postgresql" and db_inspector.has_table(
            "pregame_player_context", schema="public"
        ):
            from .pregame_context import load_current_pregame_context

            pregame_context = pd.DataFrame(
                load_current_pregame_context(
                    connection,
                    season=season,
                    week=week,
                    slate=slate,
                    cutoff=cutoff,
                )
            )
    train, target, metadata = prepare_inputs(
        matrix,
        salaries,
        participation,
        weekly_stats,
        starting_qbs,
        pregame_context,
        market_rows,
        season=season,
        week=week,
        slate=slate,
        cutoff=cutoff,
        positions=positions,
        availability_overrides=availability_overrides,
        allow_confirmed_inactive_override=allow_confirmed_inactive_override,
        assume_questionable_out=assume_questionable_out,
        preliminary_exclude_unknown=preliminary_exclude_unknown,
        injury_statuses=injury_statuses,
        opportunity_allocation_policy=opportunity_allocation_policy,
    )
    from .kicker_roles import assign_kicker_roles, load_kicker_evidence
    if "position" in target and target["position"].astype(str).str.upper().eq("K").any():
        target, metadata["kicker_role_gate"] = assign_kicker_roles(
            target, load_kicker_evidence(engine, season=season, week=week,
                                       slate=slate, cutoff=cutoff)
        )
    if not injury_statuses.empty:
        used_ids = {
            str(row["player_id"])
            for row in metadata["availability_scenario"]["overrides"]
        }
        metadata["availability_scenario"]["injury_snapshot_rows"] = [
            {"snapshot_injury_id": int(row.snapshot_injury_id),
             "player_id": str(row.player_id),
             "injury_status": normalize_salary_status(row.injury_status),
             "observed_at": pd.Timestamp(row.as_of).isoformat(), "source": row.source}
            for row in injury_statuses.itertuples(index=False)
            if str(row.player_id) in used_ids
        ]
    from .dst_feature_support import operational_support
    metadata["dst_feature_support"] = operational_support(train, target, cutoff=cutoff)
    return train, target, metadata


def load_dst_candidate_inputs(engine, *, dst_candidate_context, dst_label_dataset, **kwargs):
    """Explicit inactive adapter; live load_inputs and serving defaults are unchanged."""
    from .dst_feature_pipeline import prepare_candidate_frames
    from .dst_training_labels import select_corrected_dst_labels
    train, target, metadata = load_inputs(engine, **kwargs)
    train, label_audit = select_corrected_dst_labels(
        train, dst_label_dataset, target_season=kwargs["season"], target_week=kwargs["week"])
    train, target, audit = prepare_candidate_frames(train, target, dst_candidate_context)
    metadata = {**metadata, "dst_candidate_features": audit,
                "dst_candidate_labels": label_audit, "live_enabled": False}
    return train, target, metadata
