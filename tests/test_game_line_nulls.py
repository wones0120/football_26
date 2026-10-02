import pandas as pd
from sqlalchemy import create_engine, text

from Database.features import _load_game_lines


def test_game_lines_keep_missing_null_and_use_home_margin_sign():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE nfl_schedules (
                season INTEGER, week INTEGER, home_team TEXT, away_team TEXT,
                spread_line REAL, total_line REAL)
        """))
        connection.execute(text("""
            INSERT INTO nfl_schedules VALUES
                (2026, 4, 'TB', 'GB', -3.5, 39.5),
                (2026, 4, 'NYG', 'ARI', NULL, NULL)
        """))
    lines = _load_game_lines(engine, 2026).set_index("team")
    assert lines.loc["TB", "team_spread"] == 3.5
    assert lines.loc["TB", "team_implied_total"] == 18
    assert lines.loc["GB", "team_spread"] == -3.5
    assert lines.loc["GB", "team_implied_total"] == 21.5
    for team in ("NYG", "ARI"):
        assert pd.isna(lines.loc[team, "team_spread"])
        assert pd.isna(lines.loc[team, "team_implied_total"])
        assert pd.isna(lines.loc[team, "game_total"])
