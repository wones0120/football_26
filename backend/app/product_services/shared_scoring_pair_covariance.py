"""Observed QB/receiver pair covariance with explicit participation and TD proof.

Shared TD credit is one physical event. No future joint law or full FP estimate.
"""
from collections import Counter,defaultdict
from copy import deepcopy
from itertools import product
from uuid import UUID
import math,re
from .evaluation_record import digest
from .market_snapshots import canonical_team

VERSION='shared_scoring_pair_covariance_v1'
SCORING=dict(version='observed_passing_receiving_TD_components_v1',passing_TD_points=4,receiving_TD_points=6,full_fantasy_scoring=False)
RECEIVING_ROLES={'WR','TE','RB','FB'}
NATIVE=re.compile(r'00-\d{7}\Z')


def _count(value):
    if value is None or type(value)is bool:return None
    try:n=float(value)
    except(TypeError,ValueError):return None
    return int(n)if math.isfinite(n)and n>=0 and n.is_integer()else None


def _and(*values):return False if False in values else None if None in values else True


def _stats(points):
    n=len(points)
    if not n:return dict(samples=0,mean_x=None,mean_y=None,covariance=None,correlation=None,population_variance_x=None,population_variance_y=None,marginal_product_baseline=None)
    x=[p[0]for p in points];y=[p[1]for p in points];mx=sum(x)/n;my=sum(y)/n
    vx=sum((v-mx)**2 for v in x)/n;vy=sum((v-my)**2 for v in y)/n;cov=sum((a-mx)*(b-my)for a,b in points)/n
    return dict(samples=n,mean_x=mx,mean_y=my,covariance=cov if n>=2 else None,correlation=cov/math.sqrt(vx*vy)if n>=2 and vx>0 and vy>0 else None,population_variance_x=vx if n>=2 else None,population_variance_y=vy if n>=2 else None,marginal_product_baseline=mx*my)


def build_shared_scoring_pair_covariance(actor_rows,games,events,*,before_period):
    """Caller authenticates native stat/participation/identity/physical-event inputs."""
    if type(before_period)is not int or not 1<=before_period%100<=18:raise ValueError('Explicit REG boundary required')
    expected={};cohorts=defaultdict(list)
    for g in games:
        gid=g['game_id'];parts=gid.split('_');team=g['team'];year=g['season'];week=g['week']
        if len(parts)!=4 or parts[:2]!=[str(year),f'{week:02d}']or not 1<=week<=18 or year*100+week>=before_period or team!=canonical_team(team)or team not in {canonical_team(t)for t in parts[2:]}:raise ValueError('Exact prior native game/team scope required')
        key=(gid,team)
        if key in expected:raise ValueError('Duplicate expected native side')
        expected[key]=g;cohorts[(year,team)].append(g)
    candidates=defaultdict(set)
    for r in actor_rows:
        pid=r.get('player_master_id');edges=set(r['canonical_candidate_ids'])
        if pid is not None:edges.add(pid)
        if any(str(UUID(str(v)))!=v for v in edges):raise ValueError('Canonical UUID spelling required')
        candidates[r['native_GSIS']].update(edges)
    reverse=defaultdict(set)
    for native,edges in candidates.items():
        for pid in edges:reverse[pid].add(native)
    conflicts={n for ns in reverse.values()if len(ns)>1 for n in ns}|{n for n,edges in candidates.items()if len(edges)>1}
    source_qualified={n for n in candidates if all(r.get('identity_proven')is True for r in actor_rows if r['native_GSIS']==n)}
    canonical={n:next(iter(edges))if len(edges)==1 and n not in conflicts and n in source_qualified else None for n,edges in candidates.items()}
    actors={};qb=defaultdict(set);receivers=defaultdict(set);native_events=[];seen=set();owned=Counter();unknown=Counter();passing=Counter();receiving=Counter();shared=Counter();physical=Counter()
    for r in actor_rows:
        key=(r['game_id'],r['team']);native=r['native_GSIS']
        if key not in expected or not isinstance(native,str)or not NATIVE.fullmatch(native):raise ValueError('Actor native source scope required')
        if (*key,native)in actors:raise ValueError('Duplicate native actor/game')
        if r['participation']is not None and type(r['participation'])is not bool:raise ValueError('Tri-state source participation required')
        actors[(*key,native)]=r;group=(expected[key]['season'],key[1]);role=r.get('source_position')
        if role=='QB':qb[group].add(native)
        if role in RECEIVING_ROLES:receivers[group].add(native)
    for e in events:
        gid=e['game_id'];play=str(e['play_id']);key=(gid,play)
        if key in seen:raise ValueError('One physical native event required')
        seen.add(key);sides=[k for k in expected if k[0]==gid]
        if not sides:raise ValueError('Physical event lacks expected native game')
        team=e.get('team');scope=(gid,team)
        if team is not None and scope not in expected:raise ValueError('Physical event offense differs')
        if team is not None:owned[scope]+=1
        value=e['physical_passing_TD']
        if value is not None and type(value)is not bool:raise ValueError('Tri-state physical passing TD required')
        if value is False:continue
        passer=e.get('source_passer_id');scorer=e.get('source_TD_scorer_id');native_events.append(deepcopy(e))
        if value is True and team is not None:physical[scope]+=1
        if value is None or team is None or not isinstance(passer,str)or not NATIVE.fullmatch(passer)or not isinstance(scorer,str)or not NATIVE.fullmatch(scorer):
            for candidate in [scope]if team is not None else sides:unknown[candidate]+=1
            continue
        passing[(*scope,passer)]+=1;receiving[(*scope,scorer)]+=1;shared[(*scope,passer,scorer)]+=1
    profiles=[];pair_rows=[]
    for group,gs in sorted(cohorts.items()):
        for q,r in product(sorted(qb[group]),sorted(receivers[group])):
            if q==r:continue
            samples=[];uncertain=[];excluded=[];logs=[]
            for g in sorted(gs,key=lambda x:(x['week'],x['game_id'])):
                key=(g['game_id'],g['team']);qa=actors.get((*key,q));ra=actors.get((*key,r))
                def state(a,roles):
                    if a is None:return None
                    role=a.get('source_position');role_ok=None if role is None else role in roles
                    return _and(a['participation'],role_ok,True if a.get('source_scope_proven',True)is True else None,True if a.get('identity_proven')is True and canonical.get(a['native_GSIS'])==a.get('player_master_id')and a.get('player_master_id')is not None else None)
                membership=_and(state(qa,{'QB'}),state(ra,RECEIVING_ROLES))
                pass_count=_count(qa.get('official_pass_attempts'))if qa else None;targets=_count(ra.get('official_targets'))if ra else None
                td_known=bool(owned[key]and not unknown[key]);qtd=passing[(*key,q)]if td_known else None;rtd=receiving[(*key,r)]if td_known else None;pairtd=shared[(*key,q,r)]if td_known else None
                official_qtd=_count(qa.get('official_passing_TDs'))if qa else None;official_rtd=_count(ra.get('official_receiving_TDs'))if ra else None
                if qa and qa['participation']is False and(pass_count not in(None,0)or qtd not in(None,0)or official_qtd not in(None,0)):membership=None
                if ra and ra['participation']is False and(targets not in(None,0)or rtd not in(None,0)or official_rtd not in(None,0)):membership=None
                TD_credit_compatible=td_known and official_qtd is not None and official_rtd is not None and official_qtd==qtd and official_rtd==rtd
                complete=membership is True and TD_credit_compatible and pass_count is not None and targets is not None and qtd<=pass_count
                log=dict(game_id=key[0],team=key[1],QB_native_GSIS=q,receiver_native_GSIS=r,positive_pair_participation=membership,official_pass_attempts=pass_count,official_receiver_targets=targets,QB_observed_passing_TDs=qtd,receiver_observed_receiving_TDs=rtd,pair_shared_physical_TDs=pairtd,QB_official_passing_TDs=official_qtd,receiver_official_receiving_TDs=official_rtd,TD_credit_compatible=TD_credit_compatible,complete_matched_exposure=complete)
                logs.append(log);pair_rows.append(log)
                if membership is False:excluded.append(key[0])
                elif complete:samples.append(log)
                else:uncertain.append(key[0])
            counts=_stats([(v['official_pass_attempts'],v['official_receiver_targets'])for v in samples]);td=_stats([(4*v['QB_observed_passing_TDs'],6*v['receiver_observed_receiving_TDs'])for v in samples]);n=len(samples)
            px=sum(v['QB_observed_passing_TDs']>=1 for v in samples)/n if n else None;py=sum(v['receiver_observed_receiving_TDs']>=1 for v in samples)/n if n else None;joint=sum(v['QB_observed_passing_TDs']>=1 and v['receiver_observed_receiving_TDs']>=1 for v in samples)/n if n else None
            coexceed=dict(QB_TD_threshold=1,receiver_TD_threshold=1,matched_QB_marginal=px,matched_receiver_marginal=py,observed_joint=joint,independence_marginal_product=px*py if n else None,observed_minus_independence=joint-px*py if n else None)
            known=dict(pass_attempt_target=counts,TD_score_components=td,TD_coexceedance=coexceed)
            exact=deepcopy(known)if not uncertain and n>=2 else None
            profiles.append(dict(season=group[0],team=group[1],QB_native_GSIS=q,receiver_native_GSIS=r,QB_player_master_id=canonical.get(q),receiver_player_master_id=canonical.get(r),observed_expected_game_ids=[g['game_id']for g in gs],complete_matched_games=n,unknown_exposure_or_source_game_ids=uncertain,excluded_known_nonparticipating_or_nonrole_game_ids=excluded,exact=exact,known_complete_sample=known,shared_physical_TD_sum=sum(v['pair_shared_physical_TDs']for v in samples)))
    requests=[]
    for native,pid in canonical.items():
        if pid is not None:continue
        affected=[r for r in actor_rows if r['native_GSIS']==native];evidence={}
        for r in affected:
            for a in r.get('source_ref',{}).get('native_alias_evidence',[]):evidence[str(a.get('alias_id'))]=deepcopy(a)
        last=affected[-1];requests.append(dict(source_system='nflreadpy',source_key=native,reason='canonical_native_conflict'if native in conflicts else'frozen_pair_attachment_unavailable',game_id=last['game_id'],team=last['team'],evidence=dict(original_alias_evidence=[evidence[k]for k in sorted(evidence)])))
    core=dict(version=VERSION,identity_review_requests=requests,catalog_ids=['G24-M01','X07-M01'],before_period=before_period,scoring_definition=SCORING,minimum_matched_games_for_covariance=2,native_canonical_conflict_keys=sorted(conflicts),distinct_native_games=len({k[0]for k in expected}),pair_game_rows=pair_rows,profiles=profiles,physical_passing_TD_event_evidence=native_events,source_game_physical_passing_TDs=[dict(game_id=k[0],team=k[1],known_physical_passing_TDs=physical[k],unknown_TD_attribution_events=unknown[k],owned_source_rows=owned[k])for k in sorted(expected)],
        evidence_use='revised_observed_TD_components_and_official_counts_not_full_FP_or_forward_joint_law',pregame_serving_eligible=False,forecast=None)
    return dict(**core,semantic_sha256=digest(core))
