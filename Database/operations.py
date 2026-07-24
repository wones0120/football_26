import logging
from sqlalchemy import create_engine, MetaData, Table, delete, text, select, and_, or_, Integer, inspect
import pandas as pd
from pandas.api import types as pd_types
from sqlalchemy.exc import SQLAlchemyError

import polars as pl
import numpy as np

from sqlalchemy import create_engine, text
import logging

REQUIRED_NOT_NULL = {
    "nfl_weekly_data": ["player_id", "player_name"],
    "nfl_weekly_data_with_scores": ["player_id", "player_name"],
    "nfl_weekly_rosters": ["player_id"],
}

def delete_from_postgres(connection_string, table_name, season=None, week=None, slate=None):
    engine = create_engine(connection_string)
    with engine.begin() as connection:  # Using engine.begin() to ensure commit
        if table_name == 'dk_salaries':
            connection.execute(
                text(f"DELETE FROM {table_name} WHERE season = :season AND week = :week AND slate = :slate"),
                {"season": season, "week": week, "slate": slate}
            )
        elif table_name == 'weekly_injuries':
            connection.execute(
                text(f"DELETE FROM {table_name} WHERE season = :season AND week = :week" + (" AND slate = :slate" if slate else "")),
                {"season": season, "week": week, "slate": slate} if slate else {"season": season, "week": week},
            )
        elif (table_name == 'dk_optimizer'
              or table_name == 'predictive_features_DOUBLE'
              or table_name == 'predictive_features_TOURNAMENT'
              or table_name == 'predictive_features_score_DOUBLE'
              or table_name == 'predictive_features_score_TOURNAMENT'):
            connection.execute(
                text(f"DELETE FROM {table_name}")
            )
        elif table_name == 'player_expected_points':
            connection.execute(
                text(f"DELETE FROM {table_name}")
            )
        else:
            base_query = f"DELETE FROM {table_name} WHERE season = :season"
            params = {"season": season}
            if week is not None:
                base_query += " AND week = :week"
                params["week"] = week
            connection.execute(text(base_query), params)
    logging.info(f"Deleted data from {table_name} for season {season}" + (f" and week {week}" if week else ""))


def insert_into_postgres(df, connection_string, table_name, season, week=None, slate=None):
    engine = create_engine(connection_string)
    try:
        if isinstance(df, pl.DataFrame):
            df = df.to_pandas()

        # Ensure season and week are integers
        if 'season' in df.columns:
            df['season'] = df['season'].astype(int)
        if 'week' in df.columns:
            df['week'] = df['week'].astype(int)

        # Convert 'overtime' to boolean if it exists in the dataframe
        if 'overtime' in df.columns:
            df['overtime'] = df['overtime'].astype(bool)

        # Convert div_game to boolean if it exists
        if 'div_game' in df.columns:
            df['div_game'] = df['div_game'].astype(bool)

        # Handle NaN and inf values in salary_points_ratio
        if 'salary_points_ratio' in df.columns:
            df['salary_points_ratio'] = df['salary_points_ratio'].replace([np.inf, -np.inf], np.nan)

        # Align columns with destination table to avoid unexpected fields from nfl_data_py
        valid_columns = ensure_table_columns(engine, table_name, df)
        df = df[[col for col in df.columns if col in valid_columns]]

        required_cols = REQUIRED_NOT_NULL.get(table_name, [])
        if required_cols:
            before = len(df)
            df = df.dropna(subset=[col for col in required_cols if col in df.columns])
            dropped = before - len(df)
            if dropped:
                logging.warning(
                    "Dropped %s rows from %s due to missing required columns %s",
                    dropped,
                    table_name,
                    required_cols,
                )

        df.to_sql(table_name, engine, if_exists='append', index=False)
        return True
    except Exception as e:
        logging.error(f"Error inserting data into {table_name}: {e}")
        return False


def ensure_table_columns(engine, table_name, df):
    inspector = inspect(engine)
    try:
        existing_columns = {col['name'] for col in inspector.get_columns(table_name)}
    except Exception:
        # Table does not exist; create it with current dataframe schema
        df.head(0).to_sql(table_name, engine, if_exists="append", index=False)
        existing_columns = set(df.columns)
    missing_columns = [col for col in df.columns if col not in existing_columns]

    if missing_columns:
        logging.info("Adding missing columns %s to %s", missing_columns, table_name)
        with engine.begin() as connection:
            for column in missing_columns:
                sql_type = infer_sql_type(df[column])
                quoted_table = f"\"{table_name}\""
                quoted_column = f"\"{column}\""
                connection.execute(text(f"ALTER TABLE {quoted_table} ADD COLUMN {quoted_column} {sql_type}"))
        inspector = inspect(engine)
        existing_columns = {col['name'] for col in inspector.get_columns(table_name)}

    return existing_columns


def infer_sql_type(series):
    if pd_types.is_bool_dtype(series):
        return "BOOLEAN"
    if pd_types.is_integer_dtype(series):
        return "BIGINT"
    if pd_types.is_float_dtype(series):
        return "DOUBLE PRECISION"
    if pd_types.is_datetime64_any_dtype(series):
        return "TIMESTAMP"
    return "TEXT"
