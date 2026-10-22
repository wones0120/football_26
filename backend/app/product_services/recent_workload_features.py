"""Observed workload contrasts, not future workload or participation forecasts."""
from uuid import UUID
import pandas as pd

from .evaluation_record import digest
from .factual_designation import clock
from .market_snapshots import canonical_team
from .opportunity_history_evidence import CHANNELS, source_history

VERSION = 'recent_observed_workload_v1'


def build_recent_workload_features(weekly, actors, *, before_period, cutoff):
    """Keep one/three/eight-game and season windows in the same season/team.

    Windows are actual source team-game periods, not the player's last positive
    outcomes. Missing actor rows remain unknown, including possible inactive
    games. No participant/healthy inference is made from a stat row.
    """
    if type(before_period) is not int or not 2000 <= before_period // 100 <= 2200 or not 1 <= before_period % 100 <= 18:
        raise ValueError('REG target season/week required')
    if clock(cutoff) is None:
        raise ValueError('Actual feature cutoff required')
    scoped = weekly.loc[weekly.period < before_period]
    if 'imported_at' not in scoped or scoped.imported_at.isna().any():
        raise ValueError('Source receipt/import clock required; original availability remains separate')
    rows = source_history(weekly, before_period=before_period, cutoff=cutoff)
    rows['team'] = rows.team.map(canonical_team)
    rows = rows.loc[rows.period.ge(before_period // 100 * 100)]
    if any(not 1 <= int(p) % 100 <= 18 for p in rows.period):
        raise ValueError('REG source period required')
    rows = rows.copy()
    rows['canonical_id'] = rows.player_master_id.map(lambda x: str(UUID(str(x))) if pd.notna(x) else None)
    if rows.loc[rows.canonical_id.notna()].duplicated(['canonical_id', 'period']).any():
        raise ValueError('Duplicate canonical player period')
    results = []; seen = set()
    for actor in actors:
        pid = str(UUID(str(actor['player_master_id']))); team = canonical_team(actor['team'])
        if pid in seen:
            raise ValueError('Duplicate requested canonical player')
        seen.add(pid)
        team_rows = rows.loc[rows.team.eq(team)]
        periods = sorted(int(p) for p in team_rows.period.unique())
        player = team_rows.loc[team_rows.canonical_id.eq(pid)].set_index('period')
        metrics = {}
        for mid, short, long in (('G22-M01', 1, 8), ('G22-M02', 3, None)):
            windows = {'recent': periods[-short:], 'reference': periods if long is None else periods[-long:]}
            channels = {}
            for channel in CHANNELS:
                summary = {}
                for label, selected in windows.items():
                    values = [float(player.loc[p, channel]) if p in player.index and pd.notna(player.loc[p, channel]) else None for p in selected]
                    required = short if label == 'recent' else (long if long else 1)
                    complete = len(selected) >= required and all(v is not None for v in values)
                    summary[label] = dict(mean=sum(values)/len(values) if complete else None,
                        periods=selected, known_games=sum(v is not None for v in values),
                        unknown_periods=[p for p, v in zip(selected, values) if v is None],
                        required_games=required)
                a, b = summary['recent']['mean'], summary['reference']['mean']
                channels[channel] = dict(**summary, difference=a-b if a is not None and b is not None else None,
                    ratio=a/b if a is not None and b is not None and b > 0 else None,
                    ratio_reason='zero_reference' if b == 0 else None)
            metrics[mid] = dict(channels=channels, kind='observed_workload_contrast', forecast=False,
                variant='one_vs_eight_observed_team_games' if long else 'three_vs_same_season_observed_team_games',
                overlapping_windows=True, unit='official_count_per_observed_team_game')
        results.append(dict(player_master_id=pid, team=team, metrics=metrics))
    results.sort(key=lambda a: (a['team'], a['player_master_id']))
    semantic = dict(version=VERSION, before_period=before_period, actors=results)
    return {**semantic, 'semantic_sha256': digest(semantic), 'forecast': None,
        'provenance': dict(decision_cutoff_at=str(cutoff),
            original_historical_availability='not_established_by_revised_weekly_rows',
            source_rows=rows[['source_id', 'imported_at']].to_dict('records') if {'source_id', 'imported_at'} <= set(rows) else None),
        'source_universe': 'full supplied source team periods before actor selection/preferences',
        'missingness': 'absent actor rows are unknown, not DNP or measured zero'}
