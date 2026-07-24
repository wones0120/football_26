from __future__ import annotations

import logging
from typing import List

import polars as pl
from sqlalchemy import text

from .manager import NFLDatabaseManager


def calculate_and_insert_player_season_averages(
    weekly_stats_with_scores: pl.DataFrame,
    db_manager: NFLDatabaseManager,
    season: int,
) -> None:
    """Aggregate weekly stats with DK scores into per-player season averages."""
    logging.info("Calculating and inserting player season averages for season %s", season)
    logging.info("Type of weekly_stats_with_scores: %s", type(weekly_stats_with_scores))

    if not isinstance(weekly_stats_with_scores, pl.DataFrame):
        raise TypeError(
            f"Unexpected type for weekly_stats_with_scores: {type(weekly_stats_with_scores)}"
        )

    season_averages = (
        weekly_stats_with_scores.filter(pl.col("season") == season)
        .group_by(
            [
                "player_id",
                "player_display_name",
                "season",
                "position",
                "recent_team",
            ]
        )
        .agg(
            [
                pl.mean("completions").alias("completions"),
                pl.mean("attempts").alias("attempts"),
                pl.mean("passing_yards").alias("passing_yards"),
                pl.mean("passing_tds").alias("passing_tds"),
                pl.mean("interceptions").alias("interceptions"),
                pl.mean("passing_air_yards").alias("passing_air_yards"),
                pl.mean("passing_yards_after_catch").alias(
                    "passing_yards_after_catch"
                ),
                pl.mean("passing_first_downs").alias("passing_first_downs"),
                pl.mean("passing_epa").alias("passing_epa"),
                pl.mean("passing_2pt_conversions").alias("passing_2pt_conversions"),
                pl.mean("pacr").alias("pacr"),
                pl.mean("carries").alias("carries"),
                pl.mean("rushing_yards").alias("rushing_yards"),
                pl.mean("rushing_tds").alias("rushing_tds"),
                pl.mean("rushing_fumbles").alias("rushing_fumbles"),
                pl.mean("rushing_fumbles_lost").alias("rushing_fumbles_lost"),
                pl.mean("rushing_first_downs").alias("rushing_first_downs"),
                pl.mean("rushing_epa").alias("rushing_epa"),
                pl.mean("rushing_2pt_conversions").alias("rushing_2pt_conversions"),
                pl.mean("receptions").alias("receptions"),
                pl.mean("targets").alias("targets"),
                pl.mean("receiving_yards").alias("receiving_yards"),
                pl.mean("receiving_tds").alias("receiving_tds"),
                pl.mean("receiving_fumbles").alias("receiving_fumbles"),
                pl.mean("receiving_fumbles_lost").alias("receiving_fumbles_lost"),
                pl.mean("receiving_air_yards").alias("receiving_air_yards"),
                pl.mean("receiving_yards_after_catch").alias(
                    "receiving_yards_after_catch"
                ),
                pl.mean("receiving_first_downs").alias("receiving_first_downs"),
                pl.mean("receiving_epa").alias("receiving_epa"),
                pl.mean("receiving_2pt_conversions").alias(
                    "receiving_2pt_conversions"
                ),
                pl.mean("racr").alias("racr"),
                pl.mean("target_share").alias("target_share"),
                pl.mean("air_yards_share").alias("air_yards_share"),
                pl.mean("wopr").alias("wopr"),
                pl.mean("special_teams_tds").alias("special_teams_tds"),
                pl.mean("fantasy_points").alias("fantasy_points"),
                pl.mean("fantasy_points_ppr").alias("fantasy_points_ppr"),
                pl.mean("dk_pass_yds_points").alias("dk_pass_yds_points"),
                pl.mean("dk_pass_td_points").alias("dk_pass_td_points"),
                pl.mean("dk_int_points").alias("dk_int_points"),
                pl.mean("dk_rush_yds_points").alias("dk_rush_yds_points"),
                pl.mean("dk_rush_td_points").alias("dk_rush_td_points"),
                pl.mean("dk_rec_points").alias("dk_rec_points"),
                pl.mean("dk_rec_yds_points").alias("dk_rec_yds_points"),
                pl.mean("dk_rec_td_points").alias("dk_rec_td_points"),
                pl.mean("dk_fum_lost_points").alias("dk_fum_lost_points"),
                pl.mean("dk_pass_300_bonus").alias("dk_pass_300_bonus"),
                pl.mean("dk_rush_100_bonus").alias("dk_rush_100_bonus"),
                pl.mean("dk_rec_100_bonus").alias("dk_rec_100_bonus"),
                pl.mean("dk_rush_2pt_points").alias("dk_rush_2pt_points"),
                pl.mean("dk_rec_2pt_points").alias("dk_rec_2pt_points"),
                pl.mean("dk_pass_2pt_points").alias("dk_pass_2pt_points"),
                pl.mean("dk_total_points").alias("dk_total_points"),
            ]
        )
    )

    # Filter out rows with null player_id before converting
    season_averages = season_averages.filter(pl.col("player_id").is_not_null())

    # Convert Polars DataFrame to Pandas DataFrame
    season_averages_pd = season_averages.to_pandas()

    # Delete existing data for the specific season
    with db_manager.engine.connect() as connection:
        connection.execute(
            text("DELETE FROM player_season_averages WHERE season = :season"),
            {"season": season},
        )
        connection.commit()

    # Insert new data
    season_averages_pd.to_sql(
        "player_season_averages",
        db_manager.engine,
        if_exists="append",
        index=False,
    )

    logging.info(
        "Inserted %s player season averages for season %s",
        len(season_averages_pd),
        season,
    )


TEAM_WEEKLY_SUM_COLUMNS: List[str] = [
    "completions",
    "attempts",
    "passing_yards",
    "passing_tds",
    "interceptions",
    "sacks",
    "sack_yards",
    "sack_fumbles",
    "sack_fumbles_lost",
    "passing_air_yards",
    "passing_yards_after_catch",
    "passing_first_downs",
    "passing_2pt_conversions",
    "carries",
    "rushing_yards",
    "rushing_tds",
    "rushing_fumbles",
    "rushing_fumbles_lost",
    "rushing_first_downs",
    "rushing_2pt_conversions",
    "receptions",
    "targets",
    "receiving_yards",
    "receiving_tds",
    "receiving_fumbles",
    "receiving_fumbles_lost",
    "receiving_air_yards",
    "receiving_yards_after_catch",
    "receiving_first_downs",
    "receiving_2pt_conversions",
    "special_teams_tds",
    "dk_pass_yds_points",
    "dk_pass_td_points",
    "dk_int_points",
    "dk_rush_yds_points",
    "dk_rush_td_points",
    "dk_rec_points",
    "dk_rec_yds_points",
    "dk_rec_td_points",
    "dk_fum_lost_points",
    "dk_pass_300_bonus",
    "dk_rush_100_bonus",
    "dk_rec_100_bonus",
    "dk_rush_2pt_points",
    "dk_rec_2pt_points",
    "dk_pass_2pt_points",
    "dk_total_points",
]

TEAM_WEEKLY_MEAN_COLUMNS: List[str] = [
    "passing_epa",
    "rushing_epa",
    "receiving_epa",
    "fantasy_points",
    "fantasy_points_ppr",
]


def calculate_and_insert_team_weekly_offense(
    weekly_stats_with_scores: pl.DataFrame,
    db_manager: NFLDatabaseManager,
    season: int,
    week: int,
) -> None:
    logging.info(
        "Starting to calculate and insert team weekly offense for season %s, week %s",
        season,
        week,
    )

    unique_columns = list(dict.fromkeys(weekly_stats_with_scores.columns))
    weekly_stats_with_scores = weekly_stats_with_scores.select(unique_columns)
    # Ensure recent_team is populated, falling back to team where needed
    if "team" in weekly_stats_with_scores.columns:
        weekly_stats_with_scores = weekly_stats_with_scores.with_columns(
            pl.coalesce([pl.col("recent_team"), pl.col("team")]).alias("recent_team")
        )

    weekly_stats_with_scores = weekly_stats_with_scores.filter(
        (pl.col("season") == season)
        & (pl.col("week") == week)
        & (pl.col("recent_team").is_not_null())
        & (pl.col("opponent_team").is_not_null())
    )
    logging.info(
        "Filtered offense data for season %s, week %s. Shape: %s",
        season,
        week,
        weekly_stats_with_scores.shape,
    )

    sum_cols = [col for col in TEAM_WEEKLY_SUM_COLUMNS if col in weekly_stats_with_scores.columns]
    mean_cols = [col for col in TEAM_WEEKLY_MEAN_COLUMNS if col in weekly_stats_with_scores.columns]

    team_weekly_offense = weekly_stats_with_scores.group_by(
        ["recent_team", "season", "week", "opponent_team"]
    ).agg(
        [pl.sum(col).alias(col) for col in sum_cols]
        + [pl.mean(col).alias(col) for col in mean_cols]
    )

    logging.info(
        "Team weekly offense shape after aggregation: %s",
        team_weekly_offense.shape,
    )

    team_weekly_offense_pd = team_weekly_offense.to_pandas()

    with db_manager.engine.connect() as connection:
        delete_query = text(
            "DELETE FROM team_weekly_offense WHERE season = :season AND week = :week"
        )
        connection.execute(delete_query, {"season": season, "week": week})
        connection.commit()

    team_weekly_offense_pd.to_sql(
        "team_weekly_offense",
        db_manager.engine,
        if_exists="append",
        index=False,
    )

    logging.info(
        "Inserted %s team weekly offense rows for season %s, week %s",
        len(team_weekly_offense_pd),
        season,
        week,
    )


def calculate_and_insert_team_weekly_defense(
    weekly_stats_with_scores: pl.DataFrame,
    db_manager: NFLDatabaseManager,
    season: int,
    week: int,
) -> None:
    logging.info(
        "Starting to calculate and insert team weekly defense for season %s, week %s",
        season,
        week,
    )

    unique_columns = list(dict.fromkeys(weekly_stats_with_scores.columns))
    weekly_stats_with_scores = weekly_stats_with_scores.select(unique_columns)
    if "team" in weekly_stats_with_scores.columns:
        weekly_stats_with_scores = weekly_stats_with_scores.with_columns(
            pl.coalesce([pl.col("recent_team"), pl.col("team")]).alias("recent_team")
        )

    weekly_stats_with_scores = weekly_stats_with_scores.filter(
        (pl.col("season") == season)
        & (pl.col("week") == week)
        & (pl.col("recent_team").is_not_null())
        & (pl.col("opponent_team").is_not_null())
    )
    logging.info(
        "Filtered defense data for season %s, week %s. Shape: %s",
        season,
        week,
        weekly_stats_with_scores.shape,
    )

    sum_cols = [col for col in TEAM_WEEKLY_SUM_COLUMNS if col in weekly_stats_with_scores.columns]
    mean_cols = [col for col in TEAM_WEEKLY_MEAN_COLUMNS if col in weekly_stats_with_scores.columns]

    team_weekly_defense = weekly_stats_with_scores.group_by(
        ["opponent_team", "season", "week", "recent_team"]
    ).agg(
        [pl.sum(col).alias(col) for col in sum_cols]
        + [pl.mean(col).alias(col) for col in mean_cols]
    )

    logging.info(
        "Team weekly defense shape after aggregation: %s",
        team_weekly_defense.shape,
    )

    team_weekly_defense_pd = team_weekly_defense.to_pandas()
    team_weekly_defense_pd = team_weekly_defense_pd.rename(
        columns={"opponent_team": "recent_team", "recent_team": "opponent_team"}
    )

    with db_manager.engine.connect() as connection:
        delete_query = text(
            "DELETE FROM team_weekly_defense WHERE season = :season AND week = :week"
        )
        connection.execute(delete_query, {"season": season, "week": week})
        connection.commit()

    team_weekly_defense_pd.to_sql(
        "team_weekly_defense",
        db_manager.engine,
        if_exists="append",
        index=False,
    )
    logging.info(
        "Inserted %s team weekly defense rows for season %s, week %s",
        len(team_weekly_defense_pd),
        season,
        week,
    )


def calculate_and_insert_team_weekly_position_offense(
    weekly_stats_with_scores: pl.DataFrame,
    db_manager: NFLDatabaseManager,
    season: int,
    week: int,
) -> None:
    logging.info(
        "Starting positional offensive aggregation for season %s, week %s",
        season,
        week,
    )

    unique_columns = list(dict.fromkeys(weekly_stats_with_scores.columns))
    weekly_stats_with_scores = weekly_stats_with_scores.select(unique_columns)
    if "team" in weekly_stats_with_scores.columns:
        weekly_stats_with_scores = weekly_stats_with_scores.with_columns(
            pl.coalesce([pl.col("recent_team"), pl.col("team")]).alias("recent_team")
        )

    weekly_stats_with_scores = weekly_stats_with_scores.filter(
        (pl.col("season") == season)
        & (pl.col("week") == week)
        & (pl.col("position").is_not_null())
        & (pl.col("recent_team").is_not_null())
        & (pl.col("opponent_team").is_not_null())
    )
    logging.info(
        "Positional offense filtered shape: %s",
        weekly_stats_with_scores.shape,
    )

    sum_cols = [col for col in TEAM_WEEKLY_SUM_COLUMNS if col in weekly_stats_with_scores.columns]
    mean_cols = [col for col in TEAM_WEEKLY_MEAN_COLUMNS if col in weekly_stats_with_scores.columns]

    grouped = weekly_stats_with_scores.group_by(
        ["recent_team", "season", "week", "position", "opponent_team"]
    ).agg(
        [pl.sum(col).alias(col) for col in sum_cols]
        + [pl.mean(col).alias(col) for col in mean_cols]
    )

    logging.info("Positional offense aggregation shape: %s", grouped.shape)

    grouped_pd = grouped.to_pandas()

    with db_manager.engine.connect() as connection:
        delete_query = text(
            "DELETE FROM team_weekly_position_offense "
            "WHERE season = :season AND week = :week"
        )
        connection.execute(delete_query, {"season": season, "week": week})
        connection.commit()

    grouped_pd.to_sql(
        "team_weekly_position_offense",
        db_manager.engine,
        if_exists="append",
        index=False,
    )
    logging.info(
        "Inserted %s positional offensive rows for season %s, week %s",
        len(grouped_pd),
        season,
        week,
    )


def calculate_and_insert_team_weekly_position_defense(
    weekly_stats_with_scores: pl.DataFrame,
    db_manager: NFLDatabaseManager,
    season: int,
    week: int,
) -> None:
    logging.info(
        "Starting positional defensive aggregation for season %s, week %s",
        season,
        week,
    )

    unique_columns = list(dict.fromkeys(weekly_stats_with_scores.columns))
    weekly_stats_with_scores = weekly_stats_with_scores.select(unique_columns)
    if "team" in weekly_stats_with_scores.columns:
        weekly_stats_with_scores = weekly_stats_with_scores.with_columns(
            pl.coalesce([pl.col("recent_team"), pl.col("team")]).alias("recent_team")
        )

    weekly_stats_with_scores = weekly_stats_with_scores.filter(
        (pl.col("season") == season)
        & (pl.col("week") == week)
        & (pl.col("position").is_not_null())
        & (pl.col("recent_team").is_not_null())
        & (pl.col("opponent_team").is_not_null())
    )
    logging.info(
        "Positional defense filtered shape: %s",
        weekly_stats_with_scores.shape,
    )

    sum_cols = [col for col in TEAM_WEEKLY_SUM_COLUMNS if col in weekly_stats_with_scores.columns]
    mean_cols = [col for col in TEAM_WEEKLY_MEAN_COLUMNS if col in weekly_stats_with_scores.columns]

    grouped = weekly_stats_with_scores.group_by(
        ["opponent_team", "season", "week", "position", "recent_team"]
    ).agg(
        [pl.sum(col).alias(col) for col in sum_cols]
        + [pl.mean(col).alias(col) for col in mean_cols]
    )

    logging.info("Positional defense aggregation shape: %s", grouped.shape)

    grouped_pd = grouped.to_pandas()
    grouped_pd = grouped_pd.rename(
        columns={"opponent_team": "recent_team", "recent_team": "opponent_team"}
    )

    with db_manager.engine.connect() as connection:
        delete_query = text(
            "DELETE FROM team_weekly_position_defense "
            "WHERE season = :season AND week = :week"
        )
        connection.execute(delete_query, {"season": season, "week": week})
        connection.commit()

    grouped_pd.to_sql(
        "team_weekly_position_defense",
        db_manager.engine,
        if_exists="append",
        index=False,
    )
    logging.info(
        "Inserted %s positional defensive rows for season %s, week %s",
        len(grouped_pd),
        season,
        week,
    )


def build_team_weekly_aggregations(
    weekly_stats_with_scores: pl.DataFrame,
    db_manager: NFLDatabaseManager,
    season: int,
    weeks: List[int],
) -> None:
    for wk in sorted(set(weeks)):
        logging.info(
            "Creating team weekly aggregates for season %s, week %s", season, wk
        )
        calculate_and_insert_team_weekly_offense(
            weekly_stats_with_scores, db_manager, season, wk
        )
        calculate_and_insert_team_weekly_defense(
            weekly_stats_with_scores, db_manager, season, wk
        )
        calculate_and_insert_team_weekly_position_offense(
            weekly_stats_with_scores, db_manager, season, wk
        )
        calculate_and_insert_team_weekly_position_defense(
            weekly_stats_with_scores, db_manager, season, wk
        )
