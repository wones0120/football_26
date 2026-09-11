"""Projection input contract for the canonical salary and player-game matrix."""

from __future__ import annotations

from bisect import bisect_left
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sqlalchemy import inspect, select, text

from ..models import CuratedPlayerGameParticipation, CuratedSalary, PlayerGameFeatureMatrix
from .salary_eligibility import (
    INELIGIBLE_SALARY_STATUSES,
    is_salary_status_eligible,
    normalize_salary_status,
)


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
    *POSITION_FEATURE_COLUMNS,
]

PREGAME_LINEAGE_COLUMNS = [
    "pregame_availability_probability",
    "pregame_start_probability",
    "pregame_carry_share",
    "pregame_target_share",
    "pregame_role_label",
    "pregame_injury_status",
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
    "starting_qb_source",
    "starting_qb_evidence_tier",
    *OPPORTUNITY_FEATURE_COLUMNS,
    "pregame_base_carries_mean_3",
    "pregame_base_targets_mean_3",
    "pregame_workload_multiplier",
    "pregame_workload_adjustment_source",
    "pregame_opportunity_context_applied",
    "pregame_point_mean_before_opportunity",
    "pregame_opportunity_point_anchor",
    "pregame_opportunity_point_weight",
    "pregame_point_mean_after_opportunity",
]


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
    for season, week, player_id in zip(
        rows["season"], rows["week"], rows["player_master_id"], strict=True
    ):
        history = snap_history.get(str(player_id))
        if history is None:
            lagged_values.append(0.0)
            continue
        periods, shares = history
        stop = bisect_left(periods, _period_ordinal(season, week))
        recent = shares[max(0, stop - 3):stop]
        lagged_values.append(float(np.mean(recent)) if recent else 0.0)
    rows["snap_share_mean_3"] = lagged_values
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
) -> tuple[pd.DataFrame, dict]:
    """Attach prior-only carries, targets, and team-share features."""
    rows = matrix.copy()
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
    metrics = {
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
        if column not in evidence:
            evidence[column] = 0.0
        evidence[column] = pd.to_numeric(evidence[column], errors="coerce").fillna(0.0)
    evidence["team"] = evidence["team"].fillna("").astype(str).str.upper()
    evidence["position"] = evidence["position"].fillna("").astype(str).str.upper()
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
        for season, week, player_id in zip(
            rows["season"], rows["week"], rows["player_master_id"], strict=True
        ):
            history = histories.get(str(player_id), {}).get(source)
            if history is None:
                lagged_values.append(0.0)
                continue
            periods, values = history
            stop = bisect_left(periods, _period_ordinal(season, week))
            recent = values[max(0, stop - 3):stop]
            lagged_values.append(float(np.mean(recent)) if recent else 0.0)
        rows[feature] = lagged_values

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
        for season, week, team in zip(
            rows["season"], rows["week"], matrix_teams, strict=True
        ):
            history = team_histories.get(str(team), {}).get(source)
            if history is None:
                lagged_values.append(0.0)
                continue
            periods, values = history
            stop = bisect_left(periods, _period_ordinal(season, week))
            recent = values[max(0, stop - 3):stop]
            lagged_values.append(float(np.mean(recent)) if recent else 0.0)
        rows[feature] = lagged_values

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

    Carry and target work is redistributed as team opportunity before the point
    model runs. Salary is used only as a disclosed fallback weight for active
    players without prior NFL opportunity; it is never treated as evidence that
    a player starts.
    """
    rows = target.copy().reset_index(drop=True)
    rows["pregame_availability_probability"] = 1.0
    rows["pregame_start_probability"] = np.nan
    rows["pregame_carry_share"] = np.nan
    rows["pregame_target_share"] = np.nan
    rows["pregame_role_label"] = None
    rows["pregame_injury_status"] = None
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
    rows["pregame_base_carries_mean_3"] = pd.to_numeric(
        rows["carries_mean_3"], errors="coerce"
    ).fillna(0.0)
    rows["pregame_base_targets_mean_3"] = pd.to_numeric(
        rows["targets_mean_3"], errors="coerce"
    ).fillna(0.0)
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
            salary = pd.to_numeric(group["salary"], errors="coerce").fillna(0.0).clip(lower=0.0)
            salary_weights = salary / salary.sum() if salary.sum() > 0 else pd.Series(
                1.0 / len(group), index=group.index
            )
            history = pd.to_numeric(group["player_games_history"], errors="coerce").fillna(0.0)
            history_confidence = (history / 3.0).clip(lower=0.0, upper=1.0)
            fallback_weight = (
                prior_share * history_confidence
                + salary_weights * (1.0 - history_confidence)
            )
            if fallback_weight.sum() <= 0:
                fallback_weight = salary_weights

            explicit_share = pd.to_numeric(group[explicit_column], errors="coerce")
            explicit_mask = explicit_share.notna()
            assigned = pd.Series(0.0, index=group.index)
            if explicit_mask.any():
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
                        weights = pd.Series(1.0, index=weights.index)
                    assigned.loc[unassigned] = remainder * weights / weights.sum()
                source = "explicit_context_with_prior_salary_fallback"
            else:
                assigned = fallback_weight / fallback_weight.sum()
                source = "lagged_opportunity_with_salary_fallback"

            availability = pd.to_numeric(
                group["pregame_availability_probability"], errors="coerce"
            ).fillna(1.0).clip(lower=0.0, upper=1.0)
            available_share = assigned * availability
            if available_share.sum() > 0:
                available_share = available_share / available_share.sum()
            else:
                raise ValueError(
                    f"No available {opportunity} players remain for {team}; "
                    "correct the pregame availability evidence."
                )

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
                explicit_mask.any() or not np.allclose(availability, 1.0)
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
                    "explicit_player_count": int(explicit_mask.sum()),
                    "player_count": len(index_list),
                    "allocated_share": float(available_share.sum()),
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
    rows["snap_share_mean_3"] = pd.to_numeric(
        rows["snap_share_mean_3"], errors="coerce"
    ).fillna(0.0).clip(lower=0.0, upper=1.0)
    return rows, {
        "source": "public.starting_qb_evidence + public.pregame_player_context",
        "context_player_count": len(context_by_player),
        "context_run_ids": sorted(
            str(value)
            for value in rows["pregame_context_run_id"].dropna().unique().tolist()
        ),
        "starting_qb_teams": sorted(selected_by_team),
        "allocation_policy": (
            "team carry/target shares before point scoring; explicit context first; "
            "lagged opportunity plus disclosed DraftKings salary fallback for players "
            "without prior NFL games"
        ),
        "allocations": allocation_metrics,
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
    *,
    season: int,
    week: int,
    slate: str,
    cutoff: datetime,
    positions: list[str] | None = None,
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
    salaries["normalized_player_status"] = salaries["player_status"].map(
        normalize_salary_status
    )
    unavailable = salaries.loc[
        ~salaries["player_status"].map(is_salary_status_eligible)
    ].copy()
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
    salaries = salaries.loc[
        salaries["player_status"].map(is_salary_status_eligible)
    ].copy()
    if salaries.empty:
        raise ValueError(
            f"No eligible canonical salaries available for {season} week {week} slate {slate}; "
            "all salary players have unavailable statuses."
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
    if participation is not None and roster_columns.issubset(participation.columns):
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
            roster["team_key"] = roster["team"].fillna("").astype(str).str.upper()
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
            salaries["current_roster_status"] = [
                roster_lookup.get(
                    (
                        str(player_id),
                        str(team).strip().upper() if pd.notna(team) else "",
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
    unresolved = salaries.loc[salaries["player_master_id"].isna(), "source_player_key"].tolist()
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
        matrix[column] = pd.to_numeric(matrix[column], errors="coerce").fillna(0.0)
    matrix, participation_metrics = attach_lagged_participation_features(
        matrix,
        participation,
        cutoff=cutoff,
    )
    matrix, opportunity_metrics = attach_lagged_opportunity_features(
        matrix,
        weekly_stats,
        cutoff=cutoff,
    )
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
    salary_by_id = salaries.set_index("player_master_id")
    for output, source in [("salary", "salary"), ("recent_team", "team"),
                           ("opponent_team", "opponent"), ("position", "position"),
                           ("player_display_name", "player_name")]:
        target[output] = target["player_id"].map(salary_by_id[source])
    target = add_position_features(target)
    target, pregame_metrics = apply_pregame_projection_context(
        target,
        starting_qbs=starting_qbs,
        pregame_context=pregame_context,
    )
    # Future matrix rows currently store zero actuals. They are never labels.
    target[TARGET_COL] = float("nan")
    metadata = {
        "source": "public.player_game_feature_matrix",
        "salary_source": "public.curated_salary",
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
        "opportunity_features": opportunity_metrics,
        "pregame_context": pregame_metrics,
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


def load_inputs(engine, *, season, week, slate, cutoff, positions=None):
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
        pregame_context = pd.DataFrame()
        db_inspector = inspect(engine)
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
                            NULLIF(raw.raw_row_json ->> 'rushing_attempts', '')::DOUBLE PRECISION,
                            0.0
                        ) AS carries,
                        COALESCE(
                            NULLIF(raw.raw_row_json ->> 'targets', '')::DOUBLE PRECISION,
                            0.0
                        ) AS targets,
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
    return prepare_inputs(
        matrix,
        salaries,
        participation,
        weekly_stats,
        starting_qbs,
        pregame_context,
        season=season,
        week=week,
        slate=slate,
        cutoff=cutoff,
        positions=positions,
    )
