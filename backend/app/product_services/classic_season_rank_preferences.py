"""Frozen, prior-week season-average user preferences; never projection inputs."""
from collections import defaultdict
import hashlib
import json
import math

from sqlalchemy import text
from Database.dst import normalize_team
from backend.app.services.simulation import calculate_dk_points

POSITIONS = ("QB", "RB", "WR", "TE")


def limits(params):
    return {pos: params[f"season_ppg_top_pct_{pos.lower()}"] for pos in POSITIONS
            if params.get(f"season_ppg_top_pct_{pos.lower()}") is not None}


def validate(params, *, showdown):
    for pos, value in limits(params).items():
        if showdown:
            raise ValueError("Season-average rank limits require Classic format")
        if type(value) is not int or value not in (25, 50, 75, 100):
            raise ValueError(f"season_ppg_top_pct_{pos.lower()} must be 25, 50, 75, 100 or null")


def build_rankings(stats, snaps, aliases, *, season, week, include_kickers=False):
    """Deduplicate canonical player-week scores; conflicting evidence stays unranked."""
    allowed_positions = (*POSITIONS, "K") if include_kickers else POSITIONS
    alias_ids = defaultdict(set)
    for row in aliases:
        alias_ids[(row['source_system'], row['source_key'])].add(str(row['player_master_id']))
    scores, positions, sources = defaultdict(set), defaultdict(set), defaultdict(set)
    participating = set()
    warnings = defaultdict(int)
    for row in stats:
        if row['season'] != season or not 1 <= row['week'] < week or row['position'] not in allowed_positions:
            continue
        raw = row['raw_row_json']
        if raw.get('season_type', 'REG') != 'REG':
            continue
        ids = alias_ids[(row['source_system'], row['player_id'])]
        if len(ids) != 1:
            warnings['unresolved_stat_rows'] += 1
            continue
        pid = next(iter(ids)); key = (pid, row['week'])
        data = dict(raw)
        if 'kickoff_return_tds' not in data and 'punt_return_tds' not in data:
            data['kickoff_return_tds'] = data.get('special_teams_tds', 0)
        points = round(calculate_dk_points(data, floor_at_zero=False) + 6 * float(data.get('fumble_recovery_tds') or 0), 2)
        if row['position'] == 'K':
            num = lambda key: float(raw.get(key) or 0)
            points += (3 * sum(num(k) for k in ('fg_made_0_19', 'fg_made_20_29', 'fg_made_30_39'))
                       + 4 * num('fg_made_40_49') + 5 * (num('fg_made_50_59') + num('fg_made_60_')) + num('pat_made'))
            points = round(points, 2)
        if not math.isfinite(points):
            raise ValueError('Non-finite season scoring evidence; refresh historical stats')
        scores[key].add(points)
        positions[pid].add(row['position'])
        sources[key].add(str(row['ingest_run_id']))
        if points != 0 or any(float(raw.get(k) or 0) > 0 for k in ('attempts', 'carries', 'targets', 'sacks_suffered', 'kickoff_returns', 'punt_returns', 'fg_att', 'pat_att')):
            participating.add(key)
    for row in snaps:
        if row['season'] != season or not 1 <= row['week'] < week or row['position'] not in allowed_positions or (row.get('st_snaps' if row['position'] == 'K' else 'offense_snaps') or 0) <= 0:
            continue
        if row.get('game_type', 'REG') not in ('REG', None):
            continue
        ids = alias_ids[('pfr', row['pfr_player_id'])]
        if len(ids) != 1:
            warnings['unresolved_snap_rows'] += 1
            continue
        pid = next(iter(ids)); key = (pid, row['week'])
        participating.add(key); positions[pid].add(row['position'])
        sources[key].add(str(row['ingest_run_id']))
        if not scores[key]:
            scores[key].add(0.0)
    by_player = defaultdict(list)
    for pid, w in sorted(participating):
        by_player[pid].append(w)
    rows = []
    for pid, weeks in sorted(by_player.items()):
        if len(positions[pid]) != 1 or any(len(scores[(pid, w)]) != 1 for w in weeks):
            warnings['conflicting_players'] += 1
            continue
        games = [dict(week=w, points=next(iter(scores[(pid, w)])), ingest_run_ids=sorted(sources[(pid, w)])) for w in weeks]
        rows.append(dict(player_id=pid, position=next(iter(positions[pid])), games=games,
                         games_played=len(games), ppg=sum(g['points'] for g in games)/len(games)))
    return rows, dict(warnings)


def load_rankings(engine, *, season, week, include_kickers=False):
    if week <= 1:
        raise ValueError('Season-average preferences have no prior games in Week 1; disable the team-leader requirement or select No restriction for Classic positions')
    args = dict(season=season, week=week)
    with engine.connect() as c:
        if c.dialect.name == 'postgresql':
            c.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
            c.execute(text('SET TRANSACTION READ ONLY'))
        stats = [dict(r) for r in c.execute(text('SELECT * FROM raw_nfl_weekly_stat WHERE season=:season AND week>=1 AND week<:week'), args).mappings()]
        snaps = [dict(r) for r in c.execute(text('SELECT * FROM raw_nfl_snap_count WHERE season=:season AND week>=1 AND week<:week'), args).mappings()]
        aliases = [dict(r) for r in c.execute(text("SELECT source_system,source_key,player_master_id FROM player_alias WHERE source_system IN ('nflreadpy','pfr')")).mappings()]
        schedule = [dict(r) for r in c.execute(text('SELECT week,home_team,away_team,raw_row_json FROM raw_nfl_schedule WHERE season=:season AND week>=1 AND week<:week'), args).mappings()]
    for w in range(1, week):
        expected = {normalize_team(r[k]) for r in schedule if r['week'] == w for k in ('home_team','away_team') if r[k]}
        stat_teams = {normalize_team(r['team']) for r in stats if r['week'] == w and r['raw_row_json'].get('season_type','REG') == 'REG'}
        snap_teams = {normalize_team(r['team']) for r in snaps if r['week'] == w and r.get('game_type','REG') in ('REG',None)}
        if not expected or not expected <= stat_teams or not expected <= snap_teams:
            raise ValueError(f'Season-average rank limits need complete stats and snap coverage for Week {w}; refresh historical inputs or select No restriction')
    rows, warnings = build_rankings(stats, snaps, aliases, season=season, week=week, include_kickers=include_kickers)
    # Hash the exact source inputs including mappings, not just the resulting ranks.
    source_hash = hashlib.sha256(json.dumps([stats, snaps, aliases, schedule], sort_keys=True, default=str).encode()).hexdigest()
    return dict(rows=rows, warnings=warnings, source_sha256=source_hash)


def preference(engine, params, *, season, week):
    requested = limits(params)
    if not requested:
        return dict(enabled=False, eligible_ids={})
    evidence = load_rankings(engine, season=season, week=week)
    eligible, cutoffs = {}, {}
    for pos, pct in requested.items():
        players = [r for r in evidence['rows'] if r['position'] == pos]
        if not players:
            raise ValueError(f'Season-average rank limit has no usable {pos} history; refresh inputs or select No restriction')
        cutoff = sorted((r['ppg'] for r in players), reverse=True)[math.ceil(len(players)*pct/100)-1]
        eligible[pos] = sorted(r['player_id'] for r in players if r['ppg'] >= cutoff)
        cutoffs[pos] = dict(top_percent=pct, ranked_players=len(players), minimum_ppg=cutoff)
    return dict(enabled=True, season=season, through_week=week-1, eligible_ids=eligible, cutoffs=cutoffs,
                category='user_preference', reason='user_season_ppg_rank', basis='league-wide DK points per participating game, prior weeks only; ties included; no usable history excluded',
                model_assessments_preserved=True, **evidence)
