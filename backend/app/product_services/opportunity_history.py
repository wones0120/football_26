"""Same-team, common-window opportunity evidence; never translates old-team roles."""
from bisect import bisect_left

import numpy as np
import pandas as pd
from Database.dst import normalize_team

POLICY = "team_window_v2"


def attach_team_window_opportunity(rows, evidence, weekly_team_volume):
    rows = rows.copy()
    teams = rows.get("recent_team", rows.get("team", pd.Series("", index=rows.index)))
    teams = teams.fillna("").map(normalize_team)
    team_games = {
        team: group.sort_values("period_ordinal")
        for team, group in weekly_team_volume.groupby("team")
    }
    player_games = {
        (str(pid), team): group.set_index("period_ordinal")
        for (pid, team), group in evidence.dropna(subset=["player_master_id"]).groupby(["player_master_id", "team"])
    }
    rows["opportunity_allocation_policy"] = POLICY
    rows["opportunity_history_team"] = teams
    rows["opportunity_history_status"] = "no_same_team_window_history"
    rows["opportunity_history_observed_games"] = 0
    rows["opportunity_history_window"] = pd.Series([[] for _ in range(len(rows))], index=rows.index, dtype=object)
    cache = {}
    for index, row in rows.iterrows():
        team = teams.loc[index]
        season, week = int(row["season"]), int(row["week"])
        key = (team, season, week)
        if key not in cache:
            games = team_games.get(team)
            if games is None:
                cache[key] = pd.DataFrame()
            else:
                stop = bisect_left(games["period_ordinal"].tolist(), season * 100 + week)
                # Last three TEAM games, shared by every current-team member.
                # Prior-season fallback is useful at season start; no player can
                # reach farther back than this team's window to import a role.
                cache[key] = games.iloc[max(0, stop - 3):stop]
        window = cache[key]
        if window.empty:
            continue
        periods = window["period_ordinal"].astype(int).tolist()
        rows.at[index, "opportunity_history_window"] = [
            {"season": int(g.season), "week": int(g.week)} for g in window.itertuples()
        ]
        player = player_games.get((str(row["player_master_id"]), team))
        observed = pd.DataFrame() if player is None else player.loc[player.index.intersection(periods)]
        supported = not observed.empty
        rows.at[index, "opportunity_history_observed_games"] = len(observed)
        rows.at[index, "opportunity_history_status"] = "same_team_common_window" if supported else "no_same_team_window_history"
        for count, volume, share, prefix in (
            ("carries", "team_carries", "carry_share", "rush_share"),
            ("targets", "team_targets", "target_share", "target_share"),
        ):
            mean_volume = float(window[volume].mean())
            rows.at[index, f"{volume}_mean_3"] = mean_volume
            rows.at[index, f"{volume}_mean_3_available"] = True
            # A missing player row in a known team game contributes no observed
            # volume. No same-team rows at all remains missing evidence, not a
            # measured forward zero. Explicit current role inputs may supply it.
            counts = pd.Series(0.0, index=periods)
            if supported:
                current_position = str(row.get("position", "")).upper()
                eligible = observed["position"].isin(({"RB"} if current_position == "RB" else {current_position}) if count == "carries" else {"RB", "WR", "TE"})
                counts.loc[observed.index] = observed[count].where(eligible, 0.0).astype(float)
            mean_count = float(counts.mean())
            rows.at[index, f"{count}_mean_3"] = mean_count
            rows.at[index, f"{count}_mean_3_available"] = supported
            rows.at[index, f"{share}_mean_3"] = mean_count / mean_volume if mean_volume > 0 and (count != "carries" or str(row.get("position", "")).upper() == "RB") else 0.0
            rows.at[index, f"{share}_mean_3_available"] = supported and mean_volume > 0
            game_shares = counts.to_numpy() / window[volume].replace(0, np.nan).to_numpy()
            rows.at[index, f"{prefix}_last"] = float(game_shares[-1]) if supported else np.nan
            prior = game_shares[:-1]
            rows.at[index, f"{prefix}_prior3"] = float(np.nanmean(prior)) if supported and np.isfinite(prior).any() else np.nan
            rows.at[index, f"{prefix}_trend"] = rows.at[index, f"{prefix}_last"] - rows.at[index, f"{prefix}_prior3"]
        if "position" in rows and str(row["position"]).upper() != "RB":
            for suffix in ("last", "prior3", "trend"):
                rows.at[index, f"rush_share_{suffix}"] = np.nan
    return rows
