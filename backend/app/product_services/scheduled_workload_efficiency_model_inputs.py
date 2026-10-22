"""Prior-only workload/efficiency batch, source labels and explicit residuals."""
from copy import deepcopy
from .model_weekly_workload_components import VERSION as SOURCE_VERSION,CHANNEL_FIELDS
from .scheduled_pressure_model_inputs import build_contexts
from .scheduled_coverage_model_inputs import TEAM_COLUMNS as BASE_TEAM,PLAYER_COLUMNS as BASE_PLAYER,TEAM_VERSION as BASE_TEAM_VERSION,PLAYER_VERSION as BASE_PLAYER_VERSION
from .market_snapshots import canonical_team
from .evaluation_record import digest

VERSION='scheduled_workload_efficiency_model_inputs_v1'
TEAM_VERSION='team_opportunity_matrix_workload_efficiency_v1'
PLAYER_VERSION='player_opportunity_matrix_workload_efficiency_v1'
METRICS=(('completion_fraction','completions','attempts',True),('passing_yards_per_attempt','passing_yards','attempts',True),('passing_yards_per_completion','passing_yards','completions',True),('interceptions_per_attempt','interceptions','attempts',True),('passing_td_per_attempt','passing_tds','attempts',True),('rushing_yards_per_carry','rushing_yards','carries',False),('receptions_per_target','receptions','targets',False),('receiving_yards_per_target','receiving_yards','targets',False),('receiving_yards_per_reception','receiving_yards','receptions',False))
EXPOSURES=('attempts','completions','carries','targets','receptions')
TEAM_SUFFIXES=(*(m[0]for m in METRICS),*(f'{f}_exposure'for f in EXPOSURES),*(f'{c}_mean'for c in CHANNEL_FIELDS),'known_source_games','unknown_source_games')
TEAM_ADDED=tuple('weekly3_'+axis+'_'+s for axis in('own','opponent')for s in TEAM_SUFFIXES)
PLAYER_ADDED=(*(f'scheduled3_{m[0]}'for m in METRICS),*(f'scheduled3_{f}_exposure'for f in EXPOSURES),*(f'scheduled3_{c}_mean'for c in CHANNEL_FIELDS),*(f'scheduled3_{c}_pooled_share'for c in CHANNEL_FIELDS),'scheduled3_known_actor_rows','scheduled3_unknown_actor_rows',*(f'latest_prior_role_{r}'for r in('QB','RB','WR','TE','FB','other')),'scheduled3_role_consistent')
TEAM_COLUMNS=(*BASE_TEAM,*TEAM_ADDED)
PLAYER_COLUMNS=(*BASE_PLAYER,*(f'team_{k}'for k in TEAM_ADDED),*PLAYER_ADDED)


def _pool(rows,*,actor=False):
    complete=len(rows)==3 and all(r is not None for r in rows)
    def total(field):
        values=[r['values'][field]for r in rows if r is not None]
        return sum(values)if complete and all(v is not None for v in values)else None
    values={}
    for name,num,den,qb in METRICS:
        n,d=total(num),total(den);role=not actor or not qb or all(r is not None and r['source_QB_proven']for r in rows)
        values[name]=n/d if role and n is not None and d is not None and d>0 else None
    values.update({f'{field}_exposure':total(field)for field in EXPOSURES})
    values.update({c+'_mean':total(field)/3 if total(field)is not None else None for c,field in CHANNEL_FIELDS.items()})
    values.update(known_source_games=sum(r is not None and r.get('source_rows',1)>0 for r in rows),unknown_source_games=3-sum(r is not None and r.get('source_rows',1)>0 for r in rows))
    return values


def build_workload_efficiency_contexts(source,schedule):
    if source.get('version')!=SOURCE_VERSION:raise ValueError('Exact raw-native weekly component required')
    calendar=build_contexts(dict(version='pfr_pressure_catalog_v1',pregame_serving_eligible=False,game_rows=[]),schedule)
    teams={(r['game_id'],r['team']):r for r in source['team_game_rows']};actors={}
    if len(teams)!=len(source['team_game_rows']):raise ValueError('Unique source team game required')
    for r in source['actor_rows']:
        if r['player_master_id']is None:continue
        key=(r['game_id'],r['team'],r['player_master_id'])
        if key in actors:raise ValueError('Canonical actor game collision must be withheld upstream')
        actors[key]=r
    output=[]
    for target in calendar['rows']:
        fields={};windows={}
        for axis,team,history_key in(('own',target['team'],'own_allowed'),('opponent',target['opponent'],'opponent_generated')):
            ids=target['axes'][history_key]['contributing_game_ids'];prior=[teams.get((g,team))for g in ids];pooled=_pool(prior)
            fields.update({'weekly3_'+axis+'_'+k:v for k,v in pooled.items()});windows[axis]=dict(team=team,game_ids=ids,periods=target['axes'][history_key]['contributing_periods'])
        output.append(dict(game_id=target['game_id'],period=target['period'],team=target['team'],opponent=target['opponent'],features=fields,windows=windows))
    return dict(version=VERSION,team_contexts=output,actor_index=actors,team_index=teams)


def append_workload_efficiency(matrix,contexts,source,*,grain,parent_refs):
    expected=list(BASE_TEAM if grain=='team'else BASE_PLAYER)
    if grain not in{'team','player'}or matrix.get('version')!=(BASE_TEAM_VERSION if grain=='team'else BASE_PLAYER_VERSION)or matrix['feature_columns']!=expected or contexts.get('version')!=VERSION:raise ValueError('Exact approved coverage matrix/context required')
    if digest({k:v for k,v in matrix.items()if k not in{'matrix_sha256','provenance'}})!=matrix['matrix_sha256']:raise ValueError('Parent matrix semantic differs')
    lookup={(r['game_id'],r['team']):r for r in contexts['team_contexts']};out=deepcopy(matrix);out['version']=TEAM_VERSION if grain=='team'else PLAYER_VERSION;out['feature_columns']=list(TEAM_COLUMNS if grain=='team'else PLAYER_COLUMNS)
    for row in out['rows']:
        team=canonical_team(row['team']);ctx=lookup.get((row['game_id'],team))
        if ctx is None or ctx['period']!=row['period']:raise ValueError('Native target missing/mismatched schedule')
        periods=sorted({p for w in ctx['windows'].values()for p in w['periods']})
        if any(p>=row['period']or p//100!=row['period']//100 for p in periods):raise ValueError('Prior weekly context leaks target/year')
        row['features'].update({(''if grain=='team'else'team_')+k:v for k,v in ctx['features'].items()});row['context_periods']=sorted(set(row.get('context_periods',[]))|set(periods));row['weekly_context_windows']=deepcopy(ctx['windows']);oldlabels=deepcopy(row['labels'])
        if grain=='team':
            current=contexts['team_index'].get((row['game_id'],team));row['labels']={c:current['values'][CHANNEL_FIELDS[c]]if current is not None and row['period']<matrix['before_period']else None for c in row['labels']};row['previous_role_filtered_labels']=oldlabels
        else:
            pid=row['player_master_id'];ids=ctx['windows']['own']['game_ids'];rs=[contexts['actor_index'].get((g,team,pid))for g in ids];pooled=_pool(rs,actor=True)
            own=[contexts['team_index'].get((g,team))for g in ids]
            fields={'scheduled3_'+k:v for k,v in pooled.items()if k not in('known_source_games','unknown_source_games')};fields['scheduled3_known_actor_rows']=sum(r is not None for r in rs);fields['scheduled3_unknown_actor_rows']=3-fields['scheduled3_known_actor_rows']
            for c,field in CHANNEL_FIELDS.items():
                nums=[r['counts'][c]if r else None for r in rs];dens=[r['values'][field]if r else None for r in own];valid=len(ids)==3 and all(v is not None for v in nums+dens);n=sum(nums)if valid else None;d=sum(dens)if valid else None
                fields[f'scheduled3_{c}_pooled_share']=n/d if valid and d>0 else None
                if valid and n>d:raise ValueError('Actor raw source count exceeds matched all-native budget')
            latest=rs[-1]['source_position']if rs and rs[-1]is not None else None
            fields.update({'latest_prior_role_'+r:(None if latest is None else int(latest==r if r!='other'else latest not in{'QB','RB','WR','TE','FB'}))for r in('QB','RB','WR','TE','FB','other')})
            roles=[r['source_position']if r else None for r in rs];fields['scheduled3_role_consistent']=int(len(set(roles))==1)if len(roles)==3 and all(r is not None for r in roles)else None
            if set(fields)!=set(PLAYER_ADDED):raise ValueError('Exact declared actor input columns required')
            row['features'].update(fields);current=contexts['actor_index'].get((row['game_id'],team,pid));row['previous_player_labels']=oldlabels
            # Same canonical recorded cohort; changed/unbound raw revision is
            # unknown per head rather than silently substituting actor labels.
            row['labels']={c:oldlabels[c]if current is not None and current['counts'][c]==oldlabels[c]else None for c in oldlabels}
        row['label_revision_difference']={c:dict(previous=oldlabels[c],current=row['labels'][c])for c in oldlabels if oldlabels[c]!=row['labels'][c]}
    out['weekly_workload_adapter']=dict(version=VERSION,parent_refs=deepcopy(parent_refs),added_team_columns=list(TEAM_ADDED),added_player_columns=list(PLAYER_ADDED)if grain=='player'else[],clock_policy='Revised source observations/aliases; not original pregame backtest proof',team_passing_context='All raw native source passers, including nonQB; separate extension from sourceQB actor efficiency',player_cohort='Existing canonical warmup/scoring cohort preserved; no coldstart insertion or target-role eligibility change')
    out['label_contract']=dict(version='all_native_source_observed_weekly_counts_v1',team='All retained raw native actors before role/UUID filtering; unknown contributions mask observed source total. NOT certified full NFL census',player='Original canonical labels only with matching raw source count; unknown per-head revisions excluded',historical_participant_census='UNKNOWN',target_ledger_is_predictor=False)
    out['matrix_sha256']=digest({k:v for k,v in out.items()if k not in{'matrix_sha256','provenance'}})
    return out
