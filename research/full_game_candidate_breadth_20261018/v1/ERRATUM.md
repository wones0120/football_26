# Research scoring correction

The original public research replay941f74f4c02d56b76dc73133613b89d00eda832949168ea94ca470f1ddd59a75 and draft413eeeb1 used a research-only typed scoring helper with −2 per lost fumble. DraftKings NFL DFS deducts **−1**. Production `calculate_dk_points` already uses the correct−1; saved point projections and entered/saved operational lineups were not changed by this helper.

Verified against the [DraftKings primary DFS scoring guide](https://dknetwork.draftkings.com/2025/08/27/nfl-dfs-beginners-guide-draftkings/) and observed canonical contest actuals. The incorrect helper produced27mismatches among323component-covered regular-role player-games in2026Weeks2,3,5. Those mismatches prompted the correction; no W6 winner or player-specific adjustment was used.

Original artifacts/reports remain immutable historical experiment evidence. Their joint scores and generation-derived comparison must be treated as superseded until the public corrected baseline is built and separately reported. Conditional outcome probabilities were never validated, and no live promotion occurred. A new source-code/scoring contract and artifact identity preserve correction lineage. This is not a change to user settings, production scoring or player forecasts.
