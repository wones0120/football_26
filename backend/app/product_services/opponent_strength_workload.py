"""Strict prior observed opponent EPA strength and official workload cohorts."""
from collections import defaultdict
from copy import deepcopy
from datetime import datetime,UTC
from pathlib import Path
import hashlib,math,re
from .evaluation_record import digest
from .market_snapshots import canonical_team
from .factual_designation import clock
from .fumble_event_components import _flag,_eligibility
from .participation_source_components import _int
from .schedule_context_features import VERSION as SCHEDULE_VERSION
from .workload_venue_splits import build_workload_venue_splits,CHANNELS

VERSION='opponent_strength_workload_v1'
CONTEXT_VERSION='lagged_defense_epa_strength_v1'
FIELDS=('game_id','play_id','season','week','season_type','posteam','defteam','play_type','play_type_nfl','pass_attempt','rush_attempt','sack','two_point_attempt','epa')


def _and(a,b):return False if a is False or b is False else True if a is True and b is True else None


def _number(value):
    if value in(None,'')or type(value)is bool:return None
    try:n=float(value)
    except(TypeError,ValueError):return None
    return n if math.isfinite(n)else None


def _quantile(values,q):
    values=sorted(values);index=(len(values)-1)*q;lo=int(index);hi=math.ceil(index)
    return values[lo]+(values[hi]-values[lo])*(index-lo)


def _pool(rows):
    known=sum(r['known_physical_exposures']for r in rows);epa=sum(r['known_epa_sum']for r in rows)
    unknown=sum(r['unknown_physical_eligibility_or_side']for r in rows);missing=sum(r['unknown_epa_outcomes']for r in rows)
    uncovered=sum(not r['source_game_present']for r in rows)
    return dict(known_physical_exposures=known,known_epa_sum=epa,unknown_physical_eligibility_or_side=unknown,unknown_epa_outcomes=missing,missing_source_games=uncovered,
        exact_exposures=known if rows and not(unknown or uncovered)else None,exact_epa_sum=epa if rows and not(unknown or missing or uncovered)else None,
        epa_per_physical_play=epa/known if rows and known and not(unknown or missing or uncovered)else None)


def build_lagged_defense_strength(records,schedule,*,season,before_period,reference_week=4,max_prior_games=8):
    if schedule.get('version')!=SCHEDULE_VERSION or schedule.get('pregame_serving_eligible')is not False:raise ValueError('Reviewed historical schedule required')
    if type(season)is not int or type(before_period)is not int or not 1<=before_period%100<=18 or type(reference_week)is not int or reference_week!=4 or type(max_prior_games)is not int or max_prior_games!=8:raise ValueError('Declared prior scope/reference/8-game window required')
    expected={};team_games=defaultdict(list)
    for game in schedule['game_rows']:
        if game['season']!=season or game['game_type']!='REG'or season*100+game['week']>=before_period:continue
        gid=game['game_id'];week=game['week'];parts=gid.split('_');home=canonical_team(game['home_team']);away=canonical_team(game['away_team'])
        if len(parts)!=4 or parts[:2]!=[str(season),f'{week:02d}']or {home,away}!={canonical_team(t)for t in parts[2:]}or home==away:raise ValueError('Native schedule game/period/sides required')
        if gid in expected:raise ValueError('Duplicate native schedule game')
        expected[gid]=(week,{home,away})
        for team in(home,away):team_games[team].append((week,gid))
    for games in team_games.values():
        if len({w for w,g in games})!=len(games):raise ValueError('Multiple same-team scheduled games in one week')
        games.sort()
    counts={(gid,t):dict(game_id=gid,season=season,week=week,defense=t,source_game_present=False,known_physical_exposures=0,known_epa_sum=0.,known_epa_values=[],unknown_physical_eligibility_or_side=0,unknown_epa_outcomes=0)for gid,(week,sides)in expected.items()for t in sides}
    seen=set();basis=[]
    for raw in records:
        year=_int(raw['season']);week=_int(raw['week']);gid=raw['game_id'];parts=gid.split('_');play=str(_int(raw['play_id']))
        if len(parts)!=4 or parts[:2]!=[str(year),f'{week:02d}']or year!=season or not 1<=week<=22:raise ValueError('Native PBP period/game differs')
        key=(gid,play)
        if key in seen:raise ValueError('Duplicate native PBP game/play')
        seen.add(key)
        phase=raw.get('season_type')
        if phase not in(None,'REG')or season*100+week>=before_period:continue
        if gid not in expected:raise ValueError('PBP REG game absent expected schedule')
        sides=expected[gid][1]
        off=canonical_team(raw['posteam'])if raw.get('posteam')else None;defense=canonical_team(raw['defteam'])if raw.get('defteam')else None
        if any(t is not None and t not in sides for t in(off,defense))or off is not None and off==defense:raise ValueError('PBP native sides contradict game')
        for team in sides:counts[(gid,team)]['source_game_present']=True
        flags=[_flag(raw.get(f))for f in('pass_attempt','rush_attempt','sack')]
        physical=True if any(f is True for f in flags)else False if all(f is False for f in flags)else None
        if raw.get('play_type')in {'field_goal','extra_point','punt','kickoff'}:physical=None if physical is True else False
        live,_=_eligibility(raw);eligible=_and(live,physical)
        if phase is None:eligible=_and(eligible,None)
        if eligible is False:continue
        epa=_number(raw.get('epa'));known_side=off is not None and defense is not None
        for team in {defense}if known_side else sides:
            c=counts[(gid,team)]
            if eligible is None or not known_side:c['unknown_physical_eligibility_or_side']+=1
            else:
                c['known_physical_exposures']+=1
                if epa is None:c['unknown_epa_outcomes']+=1
                else:c['known_epa_values'].append(epa)
        basis.append(dict(game_id=gid,play_id=play,offense=off,defense=defense,eligible=eligible,epa=epa))
    for counter in counts.values():counter['known_epa_sum']=math.fsum(counter.pop('known_epa_values'))
    game_rows=[r for key,r in sorted(counts.items())]
    references=[]
    for team,games in sorted(team_games.items()):
        sample=[counts[(gid,team)]for week,gid in games if week<reference_week]
        references.append(dict(defense=team,contributing_games=[r['game_id']for r in sample],max_contributing_period=max((season*100+r['week']for r in sample),default=None),**_pool(sample)))
    values=[r['epa_per_physical_play']for r in references if r['epa_per_physical_play']is not None]
    cuts=(_quantile(values,1/3),_quantile(values,2/3))if len(values)>=3 else(None,None)
    contexts=[]
    for team,games in sorted(team_games.items()):
        for week,gid in games:
            prior=[counts[(g,team)]for w,g in games if w<week][-max_prior_games:];pooled=_pool(prior);value=pooled['epa_per_physical_play']
            ref_ready=week>=reference_week and cuts[0]is not None and cuts[0]<cuts[1]
            group=None if not ref_ready or value is None else 'strong'if value<=cuts[0]else 'weak'if value>=cuts[1]else 'middle'
            contexts.append(dict(game_id=gid,season=season,week=week,defense=team,group=group,reference_ready=ref_ready,
                contributing_games=[r['game_id']for r in prior],max_contributing_period=max((season*100+r['week']for r in prior),default=None),**pooled))
    core=dict(version=CONTEXT_VERSION,season=season,before_period=before_period,reference_before_period=season*100+reference_week,max_prior_games=max_prior_games,
        reference_terciles=dict(lower=cuts[0],upper=cuts[1],known_defenses=len(values),unknown_defenses=len(references)-len(values)),reference_rows=references,
        game_rows=game_rows,contexts=contexts,event_basis=sorted(basis,key=lambda e:(e['game_id'],int(e['play_id']))),
        evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,
        definition='Provider-derived EPA allowed per observed official physical pass/rush/sack union once, including spikes/kneels; strict prior same-season last<=8 scheduled games, unknowns mask; fixed first3week per-defense pooled known reference terciles, evaluate week4+')
    return dict(**core,semantic_sha256=digest(core))


def build_opponent_strength_workload(weekly,schedule,strength_contexts,*,before_period):
    base=build_workload_venue_splits(weekly,schedule,before_period=before_period);lookup={};thresholds={};hashes={}
    for context in strength_contexts:
        if context.get('version')!=CONTEXT_VERSION or context.get('before_period')!=before_period or context.get('pregame_serving_eligible')is not False:raise ValueError('Matched nonserving strength context required')
        year=context['season']
        if year in thresholds:raise ValueError('Duplicate source season strength')
        thresholds[year]=deepcopy(context['reference_terciles']);hashes[year]=context['semantic_sha256']
        for reference in context['reference_rows']:
            periods=[]
            for game in reference['contributing_games']:
                parts=game.split('_');period=int(parts[0])*100+int(parts[1])
                if len(parts)!=4 or int(parts[0])!=year or canonical_team(reference['defense'])not in {canonical_team(t)for t in parts[2:]}or period>=context['reference_before_period']:raise ValueError('Reference contains target/future or mismatched game')
                periods.append(period)
            if max(periods,default=None)!=reference['max_contributing_period']:raise ValueError('Reference contribution clock differs')
        for row in context['contexts']:
            parts=row['game_id'].split('_')
            if len(parts)!=4 or parts[:2]!=[str(year),f"{row['week']:02d}"]or row['season']!=year or canonical_team(row['defense'])not in {canonical_team(t)for t in parts[2:]}or year*100+row['week']>=before_period:raise ValueError('Native strength target scope differs')
            contributing=[]
            for game in row['contributing_games']:
                pieces=game.split('_');period=int(pieces[0])*100+int(pieces[1])
                if len(pieces)!=4 or int(pieces[0])!=year or canonical_team(row['defense'])not in {canonical_team(t)for t in pieces[2:]}or period>=year*100+row['week']:raise ValueError('Strength contains target/future game')
                contributing.append(period)
            if max(contributing,default=None)!=row['max_contributing_period']:raise ValueError('Strength contribution clock differs')
            period=row['season']*100+row['week'];maximum=row['max_contributing_period']
            if maximum is not None and maximum>=period:raise ValueError('Strength contains target/future game')
            if row['reference_ready']and context['reference_before_period']>period:raise ValueError('Reference not prior to evaluation')
            key=(row['game_id'],row['defense'])
            if key in lookup:raise ValueError('Duplicate strength native game/side')
            lookup[key]=row
    rows=[]
    for actor in base['rows']:
        logs=[]
        for log in actor['logs']:
            gid=log['native_game_id'];parts=gid.split('_')if gid else[];other=next((canonical_team(t)for t in parts[2:]if canonical_team(t)!=actor['team']),None)
            context=lookup.get((gid,other));evaluated=log['week']>=4
            group=context['group']if evaluated and context is not None else None
            logs.append(deepcopy(log)|dict(opponent=other,strength_group=group,strength_context_key=[gid,other],evaluation_scope=evaluated))
        sample=[r for r in logs if r['evaluation_scope']];unknown=sum(r['strength_group']is None for r in sample);channels={}
        for channel in CHANNELS:
            cells={}
            for group in('strong','weak','middle'):
                selected=[r for r in sample if r['strength_group']==group];known=[r['counts'][channel]for r in selected if r['counts'][channel]is not None];missing=len(selected)-len(known);total=sum(known)
                exact=not(unknown or missing or actor['native_team_scope_unknown'])
                cells[group]=dict(observed_logs=len(selected),unknown_count_logs=missing,known_count_sum=total,known_sample_mean=total/len(known)if known else None,
                    exact_sum=total if exact else None,per_observed_log=total/len(selected)if exact and selected else None)
            a,b=cells['strong']['per_observed_log'],cells['weak']['per_observed_log']
            channels[channel]=dict(cells=cells,strong_minus_weak=a-b if a is not None and b is not None else None,unit='official_opportunities_per_observed_source_log')
        rows.append({k:deepcopy(actor[k])for k in('season','team','source_player_id','player_master_id','native_team_scope_unknown')}|dict(logs=logs,channels=channels,unknown_strength_membership=unknown))
    semantic_rows=[{**r,'logs':[{k:v for k,v in log.items()if k!='source_ref'}for log in r['logs']]}for r in rows]
    core=dict(version=VERSION,catalog_id='G21-M09',before_period=before_period,rows=semantic_rows,strength_context_rows=[r for k,r in sorted(lookup.items())],reference_terciles=thresholds,
        definition='Same-season/team observed official counts against strictly lagged low-EPAallowed strong versus high-EPAallowed weak defenses; fixed first3week reference bins, evaluationW4+; middle and unknown retained')
    return dict(**(core|dict(rows=rows)),semantic_sha256=digest(core),source_semantic_hashes=base['source_semantic_hashes']|dict(strength=hashes),provenance=deepcopy(base['provenance']),
        identity_review_requests=deepcopy(base['identity_review_requests']),evidence_use=base['evidence_use'],pregame_serving_eligible=False,forecast=None,models_or_optimizer_consumed=False,
        limitations=base['limitations']+['EPA is provider-derived, not a raw physical fact or forecast','Missing/unknown prior games and outcomes mask strength; no hidden complete-case opponent skipping','Reference bins are fixed on known first3week defensive summaries; original historical availability unknown','No reputation, causal effect, predictive rating, fit or future workload adjustment'])


def load_retained_defense_strength_context(descriptor,schedule,*,before_period,actual_read_at=None,max_bytes=128*1024*1024,max_rows=200000):
    """Read original retained Parquet/manifest for explicit offline measurement."""
    entry=descriptor['manifest'];path=Path(descriptor['path']);read=clock(actual_read_at or datetime.now(UTC));received=clock(entry.get('received_at'))
    match=re.fullmatch(r'https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_(\d{4})\.parquet',entry.get('url',''))
    if match is None or received is None or read is None or not received<=read<=datetime.now(UTC):raise ValueError('Original source URI/actual receipt and read clocks required')
    if path.stat().st_size!=entry['bytes']or path.stat().st_size>max_bytes:raise ValueError('Retained byte size/bound differs')
    h=hashlib.sha256()
    with path.open('rb')as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    if h.hexdigest()!=entry['sha256']:raise ValueError('Retained source hash differs')
    import pyarrow.parquet as pq
    source=pq.ParquetFile(path);available=set(source.schema_arrow.names)
    if source.metadata.num_rows>max_rows or not set(FIELDS)<=available:raise ValueError('Native PBP source schema/row bound differs')
    columns=list(FIELDS)+[k for k in('no_play','quarter_end','desc','fumble','qb_dropback','qb_kneel','qb_spike','qb_scramble')if k in available]
    result=build_lagged_defense_strength(source.read(columns=columns).to_pylist(),schedule,season=int(match[1]),before_period=before_period)
    result['provenance']=dict(original_source_descriptor=deepcopy(descriptor),actual_read_at=read.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),original_rows=source.metadata.num_rows,
        producer_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),eligibility_helper_sha256=hashlib.sha256(Path(__file__).with_name('fumble_event_components.py').read_bytes()).hexdigest(),
        historical_availability='Actual later revised capture; original pregame availability unknown',game_completeness='Observed source log only, not independently completed-game coverage',identity_scope='Native team-grain, every physical actor retained, no individual canonical/name attachment')
    return result
