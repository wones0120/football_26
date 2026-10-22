"""Observed screen offense versus strictly prior opposing screen defense.

Direct FTN screen label, fixed historical reference, no fitted response or proxy.
"""
from collections import defaultdict
from copy import deepcopy
import re
from .evaluation_record import digest
from .coverage_receiver_performance import VERSION as PARENT_VERSION
from .opponent_strength_workload import _quantile

VERSION='screen_matchup_response_v1'


def _counter():return dict(known_screen_attempts=0,unknown_screen_membership=0,known_completion_exposures=0,completions=0,unknown_completions=0,known_EPA_exposures=0,EPA_sum=0.,unknown_EPA=0,missing_source_games=0)


def _finish(c):
    n=c['known_screen_attempts'];u=c['unknown_screen_membership']or c['missing_source_games']
    return dict(**c,exact_screen_attempts=n if not u else None,
        completion_rate=c['completions']/n if n and not(u or c['unknown_completions'])else None,
        EPA_per_screen_attempt=c['EPA_sum']/n if n and not(u or c['unknown_EPA'])else None,
        known_outcome_sample_completion_rate=c['completions']/c['known_completion_exposures']if c['known_completion_exposures']else None,
        known_outcome_sample_EPA=c['EPA_sum']/c['known_EPA_exposures']if c['known_EPA_exposures']else None)


def _pool(rows):return _finish({k:sum(r[k]for r in rows)for k in _counter()})


def build_screen_matchup_response(parent,charting,*,reference_before_week=4,max_prior_games=8):
    if parent.get('version')!=PARENT_VERSION or parent.get('pregame_serving_eligible')is not False:raise ValueError('Verified nonserving native attempt basis required')
    if reference_before_week!=4 or max_prior_games!=8:raise ValueError('Predeclared W1–3 reference and last8scheduled games required')
    season=parent['season'];source=charting.get('source',{})
    if not source.get('snapshot_id')or not re.fullmatch(r'[0-9a-f]{64}',source.get('content_sha256',''))or not source.get('source_uri','').endswith(f'ftn_charting_{season}.parquet'):raise ValueError('Immutable exact-season native FTN source required')
    charts={};expected={g['game_id']:g for g in parent['expected_games']};index={};groups=defaultdict(list);events=[];seen=set()
    if len(expected)!=len(parent['expected_games']):raise ValueError('Unique expected native games required')
    for g in expected.values():
        if g['season']!=season or len(set(g['sides']))!=2:raise ValueError('Expected native game season/sides required')
        for team in g['sides']:
            index[(g['game_id'],team)]=dict(game_id=g['game_id'],season=season,week=g['week'],team=team,opponent=next(t for t in g['sides']if t!=team),
                game_date=g['game_date'],offense=_counter(),defense=_counter())
            groups[team].append(g)
    for r in charting['rows']:
        key=(r['game_id'],r['play_id'])
        if key in charts:raise ValueError('Duplicate FTN native game/play')
        charts[key]=r
    missing=set(parent['missing_PBP_game_ids'])
    for (gid,team),row in index.items():
        if gid in missing:row['offense']['missing_source_games']=1;row['defense']['missing_source_games']=1
    for e in parent['event_basis']:
        gid=e['game_id'];key=(gid,e['play_id']);g=expected.get(gid)
        if key in seen or g is None:raise ValueError('Unique expected attempt game/play required')
        seen.add(key);chart=charts.get(key)
        if chart and(chart['season'],chart['week'])!=(season,g['week']):raise ValueError('FTN native period conflicts with attempt basis')
        screen=chart['flags'].get('is_screen_pass')if chart else None
        if type(screen)is not bool:screen=None
        eligible=e['eligible_target_attempt'];membership=False if eligible is False or screen is False else True if eligible is True and screen is True else None
        if membership is False:continue
        off=e['offense'];defense=e['defense'];sides=set(g['sides'])
        if any(t is not None and t not in sides for t in(off,defense))or off is not None and off==defense:raise ValueError('Native screen event sides conflict')
        scoped=off is not None and defense is not None
        for role,team in(('offense',off),('defense',defense)):
            for candidate in({team}if team is not None else sides):
                c=index[(gid,candidate)][role]
                if membership is None or not scoped:c['unknown_screen_membership']+=1
                else:
                    c['known_screen_attempts']+=1
                    if e['complete_pass']is None:c['unknown_completions']+=1
                    else:c['known_completion_exposures']+=1;c['completions']+=int(e['complete_pass'])
                    if e['target_play_EPA']is None:c['unknown_EPA']+=1
                    else:c['known_EPA_exposures']+=1;c['EPA_sum']+=e['target_play_EPA']
        events.append(dict(game_id=gid,play_id=e['play_id'],offense=off,defense=defense,screen_attempt=membership,
            original_is_screen_pass=screen,official_nonspike_attempt=eligible,source_FTN_present=chart is not None,complete_pass=e['complete_pass'],target_play_EPA=e['target_play_EPA']))
    references={};values=[]
    for team,games in sorted(groups.items()):
        if any(not g['game_date']for g in games)or len({g['game_date']for g in games})!=len(games):raise ValueError('Unique native scheduled dates required')
        games.sort(key=lambda r:r['game_date']);refs=[index[(g['game_id'],team)]['defense']for g in games if g['week']<reference_before_week]
        pooled=_pool(refs);references[team]=dict(team=team,contributing_game_ids=[g['game_id']for g in games if g['week']<reference_before_week],**pooled)
        if pooled['EPA_per_screen_attempt']is not None:values.append(pooled['EPA_per_screen_attempt'])
    low=_quantile(values,1/3)if len(values)>=2 else None;high=_quantile(values,2/3)if len(values)>=2 else None
    valid=low is not None and high is not None and low<high
    for team,games in groups.items():
        for i,g in enumerate(games):
            prior=games[max(0,i-max_prior_games):i]
            if any(old['season']*100+old['week']>=season*100+g['week']for old in prior):raise ValueError('Strictly prior scheduled defense games required')
            lag=_pool([index[(old['game_id'],team)]['defense']for old in prior]);value=lag['EPA_per_screen_attempt']
            reference_ready=g['week']>=reference_before_week
            group=None if not reference_ready or not valid or value is None else'strong'if value<=low else'weak'if value>=high else'middle'
            index[(g['game_id'],team)]['lagged_screen_defense']=dict(contributing_game_ids=[old['game_id']for old in prior],max_contributing_period=max((season*100+old['week']for old in prior),default=None),strength_group=group,reference_ready=reference_ready,reference_available_from_period=season*100+reference_before_week,**lag)
    game_rows=[];profiles=[]
    for team,games in sorted(groups.items()):
        cells={k:[]for k in('strong','weak','middle')};unknown=[];response_games=[]
        for g in games:
            row=index[(g['game_id'],team)];row=deepcopy(row);row['offense']=_finish(row['offense']);row['defense']=_finish(row['defense'])
            opponent=index[(g['game_id'],row['opponent'])]['lagged_screen_defense'];row['opposing_prior_screen_defense']=deepcopy(opponent)
            row['evaluation_after_reference']=g['week']>=reference_before_week
            game_rows.append(row)
            if not row['evaluation_after_reference']:continue
            group=opponent['strength_group'];response_games.append(g['game_id'])
            if group is None:unknown.append(g['game_id'])
            else:cells[group].append(row['offense'])
        summaries={k:_pool(v)for k,v in cells.items()};known_sample=deepcopy(summaries)
        if unknown:
            for cell in summaries.values():
                for field in('exact_screen_attempts','completion_rate','EPA_per_screen_attempt'):cell[field]=None
        strong,weak=summaries['strong'],summaries['weak']
        profiles.append(dict(season=season,team=team,evaluated_game_ids=response_games,unknown_opponent_condition_game_ids=unknown,
            condition_game_ids={k:[g['game_id']for g in games if g['week']>=reference_before_week and index[(g['game_id'],index[(g['game_id'],team)]['opponent'])]['lagged_screen_defense']['strength_group']==k]for k in cells},
            cells=summaries,known_condition_sample=known_sample,
            strong_minus_weak_screen_EPA=strong['EPA_per_screen_attempt']-weak['EPA_per_screen_attempt']if strong['EPA_per_screen_attempt']is not None and weak['EPA_per_screen_attempt']is not None else None,
            strong_minus_weak_screen_completion=strong['completion_rate']-weak['completion_rate']if strong['completion_rate']is not None and weak['completion_rate']is not None else None))
    core=dict(version=VERSION,catalog_id='G16-M06',season=season,before_period=parent['before_period'],game_rows=game_rows,profiles=profiles,event_basis=events,
        reference=dict(before_week=reference_before_week,available_from_period=season*100+reference_before_week,per_defense=references,known_defenses=len(values),strong_upper_EPA_tercile=low,weak_lower_EPA_tercile=high,nondegenerate=valid),
        definitions=dict(screen='Direct FTN is_screen_pass on official nonspike attempt; no receiver-attribution filter or air-yard proxy',
            defense='Pooled screen EPA allowed/official screen attempt in strictly prior<=8scheduled games; missing source/flag/side/outcome unknown',
            response='Same offense team/season observed screen completion/EPA per matched screen attempt against strong vs weak PRIOR opposing screen defense',
            reference='Fixed per-defense first3scheduled-week observed screen EPA rates define terciles before evaluationW4+; not fitted or calibrated',
            scope='Observed logs; final/complete-game original availability unverified; conditional source summaries not causal matchup forecasts'))
    return dict(**core,semantic_sha256=digest(core),provenance=dict(parent_semantic_sha256=parent['semantic_sha256'],FTN_source=deepcopy(source)),
        evidence_use='historical_revised_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None)
