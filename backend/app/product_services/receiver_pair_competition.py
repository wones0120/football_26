"""Observed same-sample target-allocation / provider-EPA covariance identities."""
from collections import defaultdict
from copy import deepcopy
from itertools import combinations
import math
from .evaluation_record import digest
from .coverage_receiver_performance import VERSION as SOURCE_VERSION

VERSION='receiver_pair_competition_v1'


def covariance(xs,ys):
    if len(xs)!=len(ys)or not xs:return None
    n=len(xs);mx=sum(xs)/n;my=sum(ys)/n
    return sum((a-mx)*(b-my)for a,b in zip(xs,ys))/n


def decompose(rows):
    """Population algebra on one fixed, complete observed pair/game sample."""
    n=len(rows)
    if n<2:return None
    for r in rows:
        if any(type(r[k])is not int or r[k]<0 for k in ('targets_a','targets_b','team_targets'))or r['targets_a']+r['targets_b']>r['team_targets']:raise ValueError('Conserved nonnegative native target budgets required')
        if any(type(r[k])is bool or not isinstance(r[k],(int,float))or not math.isfinite(r[k])for k in ('EPA_a','EPA_b')):raise ValueError('Finite source EPA required')
        if any(r['targets_'+k]==0 and r['EPA_'+k]!=0 for k in ('a','b')):raise ValueError('No target-play EPA without recipient targets')
    ta=[r['targets_a']for r in rows];tb=[r['targets_b']for r in rows];ya=[r['EPA_a']for r in rows];yb=[r['EPA_b']for r in rows]
    target_cov=covariance(ta,tb);strata=defaultdict(list)
    for r in rows:strata[r['team_targets']].append(r)
    ma=sum(ta)/n;mb=sum(tb)/n;within=0.;between=0.;cells=[]
    for budget,rs in sorted(strata.items()):
        x=[r['targets_a']for r in rs];y=[r['targets_b']for r in rs];weight=len(rs)/n;cx=covariance(x,y);mx=sum(x)/len(rs);my=sum(y)/len(rs)
        within+=weight*cx;between+=weight*(mx-ma)*(my-mb)
        cells.append(dict(team_target_budget=budget,samples=len(rs),weight=weight,mean_targets_a=mx,mean_targets_b=my,within_population_covariance=cx,single_sample_algebra_only=len(rs)==1))
    assert math.isclose(within+between,target_cov,abs_tol=1e-10)
    out=dict(samples=n,target_count_covariance=target_cov,team_budget_strata=cells,within_budget_target_covariance=within,between_budget_target_covariance=between,pooled_targets_a=sum(ta),pooled_targets_b=sum(tb),pooled_rest_targets=sum(r['team_targets']-r['targets_a']-r['targets_b']for r in rows),pooled_team_targets=sum(r['team_targets']for r in rows),observed_EPA_covariance=covariance(ya,yb),EPA_decomposition=None)
    if not sum(ta)or not sum(tb):return out
    ea=sum(ya)/sum(ta);eb=sum(yb)/sum(tb);ra=[a-ea*t for a,t in zip(ya,ta)];rb=[b-eb*t for b,t in zip(yb,tb)]
    terms=dict(target_allocation_scaled_by_observed_efficiencies=ea*eb*target_cov,targets_a_with_b_EPA_difference=ea*covariance(ta,rb),a_EPA_difference_with_targets_b=eb*covariance(ra,tb),paired_EPA_difference_covariance=covariance(ra,rb))
    total=sum(terms.values());assert math.isclose(total,out['observed_EPA_covariance'],abs_tol=1e-9)
    out['EPA_decomposition']=dict(target_weighted_EPA_per_target_a=ea,target_weighted_EPA_per_target_b=eb,terms=terms,reconstructed_EPA_covariance=total,pooled_EPA_a=sum(ya),pooled_EPA_b=sum(yb))
    return out


def actor_channels(block,identities):
    """Consume already-authenticated native source evidence; no coverage filter."""
    if block.get('version')!=SOURCE_VERSION or block.get('pregame_serving_eligible')is not False:raise ValueError('Reviewed nonserving target-event parent required')
    if not set(block['native_identity_universe'])<=set(identities):raise ValueError('Complete frozen global identity universe required')
    expected={g['game_id']:g for g in block['expected_games']};events=defaultdict(list);seen=set()
    for e in block['event_basis']:
        key=(e['game_id'],str(e['play_id']))
        if key in seen:raise ValueError('Unique native physical target-attempt key required')
        seen.add(key);g=expected.get(e['game_id'])
        if g is None or e['offense']is not None and e['offense']not in g['sides']:raise ValueError('Native event sides differ')
        if e['eligible_target_attempt']is not None and type(e['eligible_target_attempt'])is not bool:raise ValueError('Tri-state target eligibility required')
        if e['verified_offensive_eleven']and(not isinstance(e['native_offensive_players'],list)or len(e['native_offensive_players'])!=11 or len(set(e['native_offensive_players']))!=11):raise ValueError('Exact11 unique frozen off-field proof required')
        for t in [e['offense']]if e['offense']is not None else g['sides']:events[(e['game_id'],t)].append(e)
    team_rows={};actors={}
    for g in block['expected_games']:
        for t in g['sides']:
            es=events[(g['game_id'],t)];known=0;unknown=0;owned=sum(e['offense']==t for e in es)
            for e in es:
                if e['eligible_target_attempt']is False:continue
                if e['eligible_target_attempt']is True and e['offense']==t and e['attributed_receiver_id']is not None:known+=1
                else:unknown+=1
            team_rows[(g['game_id'],t)]=dict(game_id=g['game_id'],team=t,known_targets=known,unknown_target_budget_events=unknown,own_source_target_attempt_rows=owned,exact_team_targets=known if owned and not unknown else None)
    for a in block['game_rows']:
        gid=a['game_id'];team=a['team'];native=a['source_player_id'];key=(gid,team,native)
        if key in actors:raise ValueError('Unique source actor/game cohort required')
        if not set(a['source_roles'])&{'WR','TE','RB','FB','explicit_native_target_actor'}:raise ValueError('Native receiving-role/explicit recipient proof required')
        proof=identities[native];n=0;epa=0.;unknown=0;missing_epa=0
        for e in events[(gid,team)]:
            eligible=e['eligible_target_attempt'];recipient=e['attributed_receiver_id']
            if eligible is False:continue
            if eligible is True and recipient is not None and e['offense']==team:
                if recipient!=native:continue
                n+=1
                if e['target_play_EPA']is None:missing_epa+=1
                else:
                    v=e['target_play_EPA']
                    if type(v)is bool or not isinstance(v,(float,int))or not math.isfinite(v):raise ValueError('Finite native EPA required')
                    epa+=v
            elif e['verified_offensive_eleven']and native not in e['native_offensive_players']and not e['attribution_conflict']:continue
            else:unknown+=1
        tr=team_rows[(gid,team)];canonical=proof.get('player_master_id')if proof.get('status')=='unique_native_alias'else None
        actors[key]=dict(game_id=gid,team=team,native_GSIS=native,player_master_id=canonical,source_roles=deepcopy(a['source_roles']),known_targets=n,known_EPA_sum=epa,unknown_target_membership=unknown,unknown_EPA=missing_epa,exact_targets=n if tr['own_source_target_attempt_rows']and not unknown else None,exact_EPA_sum=epa if tr['own_source_target_attempt_rows']and not(unknown or missing_epa)else None)
    return team_rows,actors


def build_receiver_pair_competition(block,identities):
    teams,actors=actor_channels(block,identities);schedules=defaultdict(list);natives=defaultdict(set)
    for g in block['expected_games']:
        for t in g['sides']:schedules[t].append(g)
    for gid,t,n in actors:natives[t].add(n)
    game_rows=[];profiles=[];windows=[];omitted=0;candidate_windows=0
    for team,gs in sorted(schedules.items()):
        if any(not g.get('game_date')for g in gs)or len({g['game_date']for g in gs})!=len(gs):raise ValueError('Unique native scheduled dates required')
        gs.sort(key=lambda g:g['game_date'])
        for a,b in combinations(sorted(natives[team]),2):
            logs=[]
            for g in gs:
                ar=actors.get((g['game_id'],team,a));br=actors.get((g['game_id'],team,b));budget=teams[(g['game_id'],team)]['exact_team_targets']
                known=bool(ar and br and ar['player_master_id']and br['player_master_id']and ar['player_master_id']!=br['player_master_id']and budget is not None and all(r[k]is not None for r in (ar,br)for k in ('exact_targets','exact_EPA_sum')))
                r=dict(game_id=g['game_id'],season=g['season'],week=g['week'],team=team,native_a=a,native_b=b,complete=known)
                if known:r.update(targets_a=ar['exact_targets'],targets_b=br['exact_targets'],EPA_a=ar['exact_EPA_sum'],EPA_b=br['exact_EPA_sum'],team_targets=budget)
                logs.append(r);game_rows.append(r)
            sample=[r for r in logs if r['complete']];summary=decompose(sample);exact=deepcopy(summary)if len(sample)==len(logs)else None
            profiles.append(dict(season=block['season'],team=team,native_a=a,native_b=b,expected_games=len(logs),known_games=len(sample),exact=exact,known_complete_sample=summary))
            for i,g in enumerate(gs):
                if i<2:continue
                prior=logs[max(0,i-8):i]
                # Pair universe at a target uses only actors actually observed earlier.
                if not all(any((old['game_id'],team,n)in actors for old in gs[:i])for n in (a,b)):continue
                if any(old['season']*100+old['week']>=g['season']*100+g['week']for old in prior):raise ValueError('Strict prior scheduled window required')
                known=[r for r in prior if r['complete']];stats=decompose(known);candidate_windows+=1
                if stats is None:omitted+=1;continue
                windows.append(dict(target_game_id=g['game_id'],target_period=g['season']*100+g['week'],season=block['season'],team=team,native_a=a,native_b=b,player_master_id_a=identities[a].get('player_master_id')if identities[a]['status']=='unique_native_alias'else None,player_master_id_b=identities[b].get('player_master_id')if identities[b]['status']=='unique_native_alias'else None,contributing_game_ids=[r['game_id']for r in prior],unknown_game_ids=[r['game_id']for r in prior if not r['complete']],known_complete_sample=stats,exact=deepcopy(stats)if len(known)==len(prior)else None))
    core=dict(version=VERSION,catalog_id='X07-M03',season=block['season'],before_period=block['before_period'],team_game_target_budgets=list(teams.values()),actor_game_channels=list(actors.values()),pair_game_rows=game_rows,observed_profiles=profiles,strict_prior_windows=windows,window_coverage=dict(candidate_windows=candidate_windows,omitted_without_two_complete_games=omitted,omitted_values='Undefined, not zero; native pair/game ledger and source schedules retain every missing/unknown state'),source_semantic_sha256=block['semantic_sha256'],units=dict(target_covariance='target_count_squared',EPA_covariance='provider_expected_points_squared',efficiency='provider_expected_points_per_initial_recipient_target'),definitions=dict(pair='Unique unordered distinct native receiving-role/explicit recipient pair; exact frozen canonical proof',sample='Same complete pair/game target counts, provider full-target-play EPA and conserved full-team target budget; zeros included',window='Up to8 immediately preceding scheduled same-team/season games; absent participant/unknown game never skipped',efficiency='Observed target-weighted EPA ratios within each identical sample; exact algebraic four-term covariance identity, not regression/causal effects',budget='Target covariance within/between literal full-team target-count strata; singleton withinCov0 is algebraic only',exclusions='No assigned defender, full-roster effect, future response/probability/calibration or current2026 availability'),pregame_serving_eligible=False,forecast=None)
    return dict(**core,semantic_sha256=digest(core))
