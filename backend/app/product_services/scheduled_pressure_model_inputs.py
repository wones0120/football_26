"""Exact prior-three scheduled HHS pressure contexts for reconstructed research.

Source receipts are retrospective. Lagged football measurements do not establish
original historical pregame availability or individual protection assignments.
"""
from collections import defaultdict
from copy import deepcopy
from datetime import date
import math
from .market_snapshots import canonical_team
from .evaluation_record import digest
from .team_opportunity_matrix import FEATURES as TEAM_BASE
from .offensive_volume_features import FEATURES as PLAYER_BASE

VERSION='scheduled_pressure_model_inputs_v1'
TEAM_VERSION='team_opportunity_matrix_pressure3_v1'
PLAYER_VERSION='player_opportunity_matrix_pressure3_v1'
SUFFIXES=('rate','pressures','dropbacks','known_games','unknown_games')
PRESSURE_COLUMNS=tuple('pressure3_'+axis+'_'+s for axis in ('own_allowed','opponent_generated')for s in SUFFIXES)
TEAM_COLUMNS=(*TEAM_BASE,*PRESSURE_COLUMNS)
PLAYER_COLUMNS=(*PLAYER_BASE,*(f'team_{k}'for k in TEAM_BASE),*(f'team_{k}'for k in PRESSURE_COLUMNS))


def build_contexts(pressure,schedule):
    if pressure.get('version')!='pfr_pressure_catalog_v1' or pressure.get('pregame_serving_eligible')is not False:
        raise ValueError('Approved nonserving per-game pressure contract required')
    games={};calendar=defaultdict(list)
    for g in schedule:
        if g['game_type']!='REG':continue
        gid=g['game_id'];season=g['season'];week=g['week'];parts=gid.split('_')
        home,away=canonical_team(g['home_team']),canonical_team(g['away_team'])
        if type(season)is not int or type(week)is not int or not 1<=week<=18 or len(parts)!=4 or parts[:2]!=[str(season),f'{week:02d}'] or {home,away}!={canonical_team(t)for t in parts[2:]} or home==away:
            raise ValueError('Unique native schedule period/sides required')
        day=date.fromisoformat(g['game_date'])
        if gid in games:raise ValueError('Duplicate native scheduled game')
        games[gid]=dict(game_id=gid,season=season,week=week,day=day,home=home,away=away)
        for team in(home,away):calendar[(season,team)].append(games[gid])
    observations={}
    for r in pressure['game_rows']:
        g=games.get(r['game_id']);off,defense=canonical_team(r['offense']),canonical_team(r['defense'])
        if g is None or (r['season'],r['week'])!=(g['season'],g['week'])or {off,defense}!={g['home'],g['away']}or off==defense:raise ValueError('Pressure/schedule binding differs')
        key=(r['game_id'],off)
        if key in observations:raise ValueError('Duplicate pressure side')
        if r['full_observed_cohort_proven'] is True:
            n,d=r['known_source_pressure_sum'],r['known_dropbacks']
            if any(type(v)is not int or v<0 for v in(n,d))or n>d or r['unknown_or_incompatible_reasons']:
                raise ValueError('Exact compatible integer exposure required')
            rate=n/d if d else None
            if r['pressure_rate']!=rate:raise ValueError('Pressure numerator/denominator differs')
        observations[key]=r
    own={}
    for (season,team),gs in calendar.items():
        gs.sort(key=lambda g:g['day'])
        if len({g['day']for g in gs})!=len(gs)or len({g['week']for g in gs})!=len(gs):raise ValueError('Unique scheduled team dates/weeks required')
        for i,g in enumerate(gs):
            prior=gs[max(0,i-3):i]
            if any(o['day']>=g['day']or o['week']>=g['week']for o in prior):raise ValueError('Strict prior scheduled date/period required')
            for axis in('own_allowed','opponent_generated'):
                rows=[observations.get((o['game_id'],team if axis=='own_allowed'else(o['away']if team==o['home']else o['home'])))for o in prior]
                known=[r for r in rows if r is not None and r['full_observed_cohort_proven']is True]
                complete=len(prior)==3 and len(known)==3
                n=sum(r['known_source_pressure_sum']for r in known)if complete else None
                d=sum(r['known_dropbacks']for r in known)if complete else None
                own[(g['game_id'],team,axis)]=dict(rate=n/d if complete and d else None,pressures=n,dropbacks=d,known_games=len(known),unknown_games=3-len(known),contributing_game_ids=[o['game_id']for o in prior],contributing_periods=[o['season']*100+o['week']for o in prior],complete=complete)
    result=[]
    for gid,g in sorted(games.items()):
        for team,opp in((g['home'],g['away']),(g['away'],g['home'])):
            axes={'own_allowed':own[(gid,team,'own_allowed')],'opponent_generated':own[(gid,opp,'opponent_generated')]}
            features={'pressure3_'+axis+'_'+s:a[s]for axis,a in axes.items()for s in SUFFIXES}
            result.append(dict(game_id=gid,team=team,opponent=opp,period=g['season']*100+g['week'],features=features,axes=axes))
    return dict(version=VERSION,rows=result,source_scope='Revised historical pressure cohorts; source-unavailable years unknown',original_pregame_backtest_eligible=False)


def append_pressure_context(matrix,contexts,*,grain,parent_refs):
    if grain not in{'team','player'}or contexts.get('version')!=VERSION:raise ValueError('Exact context/grain required')
    expected=list(TEAM_BASE)if grain=='team'else[*PLAYER_BASE,*(f'team_{k}'for k in TEAM_BASE)]
    if matrix['feature_columns']!=expected or matrix.get('admission_policy',{}).get('version')!='reconstructed_count_input_admission_v1':raise ValueError('Exact admitted baseline required')
    if digest({k:v for k,v in matrix.items()if k not in{'matrix_sha256','provenance'}})!=matrix['matrix_sha256']:raise ValueError('Baseline semantic checksum differs')
    lookup={(r['game_id'],r['team']):r for r in contexts['rows']}
    if len(lookup)!=len(contexts['rows']):raise ValueError('Duplicate model context')
    out=deepcopy(matrix);out['version']=TEAM_VERSION if grain=='team'else PLAYER_VERSION;out['feature_columns']=list(TEAM_COLUMNS if grain=='team'else PLAYER_COLUMNS)
    for r in out['rows']:
        ctx=lookup.get((r['game_id'],canonical_team(r['team'])))
        if ctx is None:raise ValueError('Model target absent native schedule')
        if ctx['period']!=r['period']:raise ValueError('Target context period mismatch')
        periods=sorted({p for a in ctx['axes'].values()for p in a['contributing_periods']})
        if any(p>=r['period']or p//100!=r['period']//100 for p in periods):raise ValueError('Pressure context target/future/cross-season leak')
        r['features'].update({(''if grain=='team'else'team_')+k:v for k,v in ctx['features'].items()})
        r['pressure_context']=deepcopy(ctx['axes']);r['context_periods']=sorted(set(r.get('context_periods',[]))|set(periods))
    out['pressure_adapter']=dict(version=VERSION,parent_refs=deepcopy(parent_refs),columns=list(PRESSURE_COLUMNS),window='Exactly three immediate prior SCHEDULED same-season games; no skip/padding',availability='Reconstructed history only; retrospective acquisition/alias clocks not original pregame proof',catalog_ids=['G13-M03','G14-M01'],consumer_scope='Team-level pressure context shared with canonical player rows; not individual blocking/pressure skill')
    out['matrix_sha256']=digest({k:v for k,v in out.items()if k not in{'matrix_sha256','provenance'}})
    return out
