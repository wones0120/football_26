"""Historical scheduled-window official workload count and allocation contrasts."""
from collections import defaultdict
from copy import deepcopy
from datetime import datetime,UTC
from .workload_venue_splits import build_workload_venue_splits,CHANNELS
from .weekly_effectiveness_catalog_features import _values,SOURCE_FIELDS
from .factual_designation import clock
from .market_snapshots import canonical_team
from .defense_context_evidence import _hash
from .evaluation_record import digest

VERSION='historical_scheduled_workload_trends_v1'
RAW_COUNT={'pass_attempts':'attempts','rush_attempts':'carries','targets':'targets'}


def _window(games,logs,budgets,channel,*,required):
    values=[logs.get(g['week'],{}).get('counts',{}).get(channel)for g in games]
    denoms=[budgets.get((g['season'],g['week'],g['team']),{}).get(channel)for g in games]
    complete=len(games)>=required and bool(games)and all(v is not None for v in values)
    n=sum(values)if complete else None;d=sum(denoms)if complete and all(v is not None for v in denoms)else None
    return dict(native_game_ids=[g['game_id']for g in games],periods=[g['season']*100+g['week']for g in games],required_games=required,achieved_scheduled_games=len(games),
        known_count_games=sum(v is not None for v in values),known_count_sum=sum(v for v in values if v is not None),
        unknown_count_game_ids=[g['game_id']for g,v in zip(games,values)if v is None],
        exact_count_sum=n,exact_count_per_scheduled_game=n/len(games)if n is not None else None,
        full_native_team_count_sum=d,exact_pooled_share=n/d if d is not None and d>0 else None,
        known_zero_team_budget=d==0,unknown_team_budget_game_ids=[g['game_id']for g,v in zip(games,denoms)if v is None])


def build_historical_workload_trends(weekly,schedule,raw_source,*,before_period,cutoff,positive_participants_missing_weekly=()):
    actual=clock(cutoff)
    if actual is None or actual>datetime.now(UTC):raise ValueError('Actual nonfuture source cutoff required')
    base=build_workload_venue_splits(weekly,schedule,before_period=before_period)
    if clock(weekly['provenance'].get('actual_derived_at'))is None or clock(weekly['provenance']['actual_derived_at'])>actual:raise ValueError('Reviewed weekly unavailable at actual cutoff')
    teams=defaultdict(list);scope={}
    for g in schedule['game_rows']:
        if g['game_type']!='REG'or g['season']*100+g['week']>=before_period:continue
        pair={canonical_team(g['home_team']),canonical_team(g['away_team'])}
        if len(pair)!=2 or g['game_id'].split('_')[:2]!=[str(g['season']),f"{g['week']:02d}"]or{canonical_team(t)for t in g['game_id'].split('_')[2:]}!=pair:raise ValueError('Native schedule game/period/pair differs')
        for team in pair:
            key=(g['season'],g['week'],team)
            if key in scope:raise ValueError('Unique native scheduled team-week required')
            row=dict(game_id=g['game_id'],season=g['season'],week=g['week'],team=team);scope[key]=row;teams[(g['season'],team)].append(row)
    for games in teams.values():games.sort(key=lambda g:g['week'])
    raw_index={};budget_parts=defaultdict(lambda:defaultdict(list));unknown_team_periods=set()
    for r in raw_source['rows']:
        sid=r['source_id'];raw=r['raw_row_json'];season=r['season'];week=r['week']
        if sid in raw_index or raw.get('season_type')!='REG'or type(season)is not int or type(week)is not int or season*100+week>=before_period or clock(r.get('imported_at'))is None or clock(r['imported_at'])>actual:raise ValueError('Frozen raw identity/phase/period/clock differs')
        raw_index[sid]=r;variants=set()
        for t in(r.get('team'),raw.get('team'),raw.get('recent_team')):
            if t not in(None,''):
                try:variants.add(canonical_team(t))
                except ValueError:variants.add(None)
        team=next(iter(variants))if len(variants)==1 and None not in variants else None
        if team is None:unknown_team_periods.add((season,week));continue
        key=(season,week,team)
        if key not in scope:raise ValueError('Raw native team lacks scheduled game')
        values=_values(raw)[0]
        for channel,field in RAW_COUNT.items():budget_parts[key][channel].append(values[field])
    budgets={key:{c:sum(v)if v and all(x is not None for x in v)and key[:2]not in unknown_team_periods else None for c,v in channels.items()}for key,channels in budget_parts.items()}
    groups={};unknown_actor_scope=set();identities={};role_rows=[]
    for row in weekly['rows']:
        source=raw_index.get(row['source_ref']['source_id'])
        if source is None:raise ValueError('Every reviewed row requires frozen raw counterpart')
        raw=source['raw_row_json'];key=(row['season'],row['week'],row['team']);actor=(row['season'],row['team'],row['source_player_id'])
        if _hash({k:v for k,v in raw.items()if k in SOURCE_FIELDS})!=row['source_ref']['projected_source_row_sha256']:raise ValueError('Projected frozen raw row differs')
        if(source['source_player_id'],source['season'],source['week'],source.get('ingest_run_id'),source.get('imported_at'))!=(row['source_player_id'],row['season'],row['week'],row['source_ref']['ingest_run_id'],row['source_ref']['imported_at']):raise ValueError('Native weekly source revision differs')
        if key not in scope:
            unknown_actor_scope.add((row['season'],row['source_player_id']));continue
        if row['native_game_id']not in(None,'',scope[key]['game_id']):raise ValueError('Weekly native game differs')
        roles={p for p in(source.get('position'),raw.get('position'),raw.get('pos'))if p not in(None,'')};role=next(iter(roles))if len(roles)==1 else None
        if role!=row['source_position']:role=None
        if role is None:role_rows.append(dict(season=row['season'],week=row['week'],team=row['team'],source_player_id=row['source_player_id']))
        counts={c:row['metrics'].get(mid,{}).get('denominator')for c,mid in CHANNELS.items()};v=_values(raw)[0]
        for c,field in RAW_COUNT.items():
            if c=='pass_attempts'and(role!='QB'or row.get('QB_scope_source_proven')is not True):counts[c]=None
            elif counts[c]!=v[field]:raise ValueError('Raw count differs from reviewed official channel')
            if counts[c]is not None and budgets.get(key,{}).get(c)is not None and counts[c]>budgets[key][c]:raise ValueError('Actor exceeds full native source channel budget')
        if row['week']in groups.setdefault(actor,{}):raise ValueError('Unique actor/team/season/week required')
        groups[actor][row['week']]=dict(counts=counts,source_role=role,source_ref=deepcopy(row['source_ref']))
        if actor in identities and identities[actor]!=row['player_master_id']:raise ValueError('Native canonical attachment changes')
        identities[actor]=row['player_master_id']
    missing=[]
    for p in positive_participants_missing_weekly:
        key=(p['season'],p['week'],p['team']);g=scope.get(key)
        if g is None or p.get('native_game_id')!=g['game_id']or type(p.get('offense_snaps'))not in(int,float)or not p['offense_snaps']>0:raise ValueError('Dated positive source participant proof required')
        missing.append(deepcopy(p));budgets[key]={c:None for c in CHANNELS}
        # Even unassigned native/role participant can own channel mass: budget unknown.
        for actor,logs in groups.items():
            season,team,native=actor
            if p.get('player_master_id')is not None and (season,team,p['player_master_id'])==(p['season'],p['team'],identities[actor]):
                if p['week']in logs:raise ValueError('Missing-positive evidence duplicates observed weekly actor')
                logs[p['week']]=dict(counts={c:None for c in CHANNELS},source_role=p.get('source_position'),positive_missing=True)
    rows=[]
    for actor,logs in sorted(groups.items(),key=lambda x:str(x[0])):
        year,team,native=actor;games=teams[(year,team)];latest=games[-1:];prior8=games[-9:-1];recent3=games[-3:];metrics={}
        for mid,a,b,required_a,required_b in(('G22-M01',latest,prior8,1,8),('G22-M02',recent3,games,3,1)):
            channels={}
            for channel in CHANNELS:
                short=_window(a,logs,budgets,channel,required=required_a);long=_window(b,logs,budgets,channel,required=required_b)
                unknown_scope=(year,native)in unknown_actor_scope
                def diff(field):
                    x,y=short[field],long[field]
                    return x-y if x is not None and y is not None and not unknown_scope else None
                channels[channel]=dict(recent=short,reference=long,count_mean_difference=diff('exact_count_per_scheduled_game'),pooled_share_difference=diff('exact_pooled_share'))
            metrics[mid]=dict(channels=channels,recent_reference_overlap=mid=='G22-M02',unit='official_count_per_scheduled_game; fraction_of_full_native_source_channel_budget')
        rows.append(dict(season=year,team=team,source_player_id=native,player_master_id=identities[actor],target_boundary_period=year*100+19 if year<before_period//100 else before_period,
            latest_measured_game_id=games[-1]['game_id'],source_roles_by_week={str(w):log['source_role']for w,log in sorted(logs.items())},native_team_scope_unknown=(year,native)in unknown_actor_scope,metrics=metrics))
    core=dict(version=VERSION,candidate_ids=['G22-M01','G22-M02'],before_period=before_period,rows=rows,
        native_team_budgets=[dict(season=s,week=w,team=t,counts=c)for(s,w,t),c in sorted(budgets.items())],unknown_team_periods=sorted(unknown_team_periods),unknown_role_rows=role_rows,positive_participants_missing_weekly=missing,
        definition='Latest measured scheduled same-team-season game minus exactly8 preceding scheduled slots; recent3 scheduled slots minus all season games before declared target boundary. Count means and pooled full-native budget shares separate; M02 overlap explicit')
    return dict(**core,semantic_sha256=digest(core),provenance=deepcopy(base['provenance']),pregame_serving_eligible=False,forecast=None,models_or_optimizer_consumed=False,identity_review_requests=deepcopy(weekly['identity_review_requests']),
        limitations=['Missing weekly row is unknown, never DNP or measured zero; no scheduled slot skipped','Source observed counts and all-raw native budgets, not independent complete NFL game charting','Pass actor channel sourceQB only; nonQB pass budget remains residual','Historical/revised/actual postlock evidence, no original pregame/health/causal/future role claim'])
