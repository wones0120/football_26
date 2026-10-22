"""Retrospective full-game analog stress research; never a forecast/probability model.

The source games remain paired. Role mapping leaves unrepresented production in
residual buckets, including backup quarterbacks and user-excluded role holders.
"""
from collections import Counter
from copy import deepcopy
from itertools import combinations
import math
import random
import statistics

import pulp

from .analyst_shadow import digest
from .cbc_solver import make_cbc_solver
from .scenario_allocation import AllocationControls, audit_construction, measurement, team, opponent
from .scenario_breadth import signature

CONTRACT = 'full_game_role_analog_stress_v1'
SCORING_CONTRACT = 'draftkings_nfl_typed_v2_lost_fumble_minus_one'


def strict_dk(stats):
    """NFL weekly typed categories, no unknown-to-zero or nonnegative clipping."""
    weights = {'passing_yards':.04, 'passing_tds':4, 'passing_interceptions':-1,
        'rushing_yards':.1, 'rushing_tds':6, 'receptions':1, 'receiving_yards':.1,
        'receiving_tds':6, 'passing_2pt_conversions':2, 'rushing_2pt_conversions':2,
        'receiving_2pt_conversions':2, 'special_teams_tds':6, 'fumble_recovery_tds':6,
        'rushing_fumbles_lost':-1, 'receiving_fumbles_lost':-1, 'sack_fumbles_lost':-1}
    if any(type(stats.get(k)) not in (int,float) or not math.isfinite(stats[k]) for k in weights):
        raise ValueError('Unknown typed fantasy scoring component; no zero fill')
    return sum(stats[k]*w for k,w in weights.items()) + 3*sum(stats[k]>=boundary for k,boundary in
        [('passing_yards',300),('rushing_yards',100),('receiving_yards',100)])


def unavailable(row):
    return row.get('role_availability') == 'unavailable' or row.get('model_availability_used') == 0 or 'confirmed_unavailable' in (row.get('exclusion_reasons') or [])


def role_universe(full_rows, eligible):
    """Preference eligibility never determines team opportunity rank."""
    universe, audit = {}, {'unavailable':[], 'unknown_role':[], 'quarterback_assumptions':[]}
    for row in full_rows:
        if unavailable(row):
            audit['unavailable'].append(row['player_id']); continue
        pos = row['position']; key = (team(row),pos)
        if pos == 'DST':
            universe.setdefault(key,[]).append((row,0,None)); continue
        if pos == 'QB':
            if row.get('expected_depth_role') != 'expected_starter':
                continue
            value,basis = measurement(row,'carries')
            if value is None:
                raise ValueError('Starting QB style unknown; cannot invent analog context')
            universe.setdefault(key,[]).append((row,value,basis))
            audit['quarterback_assumptions'].append({'player_master_id':row['player_id'],'team':team(row),
                'status':row.get('player_status'),'official_status':row.get('official_availability_status'),
                'basis':'Frozen model expected starter; conditional assumption, not newly verified', 'carries_proxy':value})
        elif pos in {'RB','WR','TE'}:
            target,tbasis = measurement(row,'targets'); carry,cbasis = measurement(row,'carries')
            value = (target+carry if target is not None and carry is not None else None) if pos=='RB' else target
            if value is None or value <= 0 or row.get('expected_depth_role')=='long_snapper':
                audit['unknown_role'].append(row['player_id']); continue
            universe.setdefault(key,[]).append((row,value,tbasis+(' + '+cbasis if pos=='RB' else '')))
    for key,values in universe.items():
        values.sort(key=lambda x:(-x[1],x[0]['player_id']))
        if key[1] in {'QB','DST'} and len(values)!=1:
            raise ValueError('Ambiguous frozen starting QB or defense identity')
    mapped = {r['player_id'] for values in universe.values() for r,_,_ in values}
    if {r['player_master_id'] for r in eligible} - mapped:
        raise ValueError('An eligible player has unknown opportunity rank; no silent zero')
    return universe,audit


def map_game(template, home, away, universe):
    points, ledger = {}, []
    for side,current_team in zip(template['sides'],[home,away]):
        side_ledger=[]
        for pos in ['QB','RB','WR','TE','K']:
            source = [p for p in side['players'] if p['position']==pos]
            def prior(p):
                return p['prior']['attempts'] if pos=='QB' else p['prior']['targets']+p['prior']['carries'] if pos=='RB' else p['prior']['targets']
            source.sort(key=lambda p:(-prior(p),p['source_player_id']))
            current=universe.get((current_team,pos),[])
            # Backup passer production remains a distinct anonymous actor. No volume transfer.
            for rank,p in enumerate(source):
                mapped=current[rank] if rank<len(current) and (pos!='QB' or rank==0) else None
                pid=mapped[0]['player_id'] if mapped else None
                score = strict_dk(p['stats'])
                if pos=='K':
                    keys={'fg_made_0_19':3,'fg_made_20_29':3,'fg_made_30_39':3,'fg_made_40_49':4,'fg_made_50_59':5,'fg_made_60_':5,'pat_made':1}
                    if any(type(p['stats'].get(k)) not in (int,float) for k in keys):raise ValueError('Unknown kicking component')
                    score+=sum(p['stats'][k]*w for k,w in keys.items())
                if pid:
                    # Receiving-role rank does not establish punt/kick-return duties.
                    # Keep these real source events anonymous unless separately mapped.
                    return_points=6*p['stats']['special_teams_tds']
                    points[pid]=score-return_points
                    if return_points:
                        side_ledger.append({'position':'RETURN_SPECIALIST','source_player_id':p['source_player_id'],
                            'player_master_id':None,'residual':True,'dk_points':return_points,
                            'basis':'Current return role unverified; no receiving-rank transfer'})
                side_ledger.append({'source_player_id':p['source_player_id'],'position':pos,'pregame_role_rank':rank+1,
                    'player_master_id':pid,'residual':pid is None,'dk_points':points[pid] if pid else score,'stats':{k:p['stats'][k] for k in
                      ['attempts','completions','targets','carries','passing_yards','receiving_yards','rushing_yards','passing_tds','receiving_tds','rushing_tds']},
                    'source_prior':p['prior'],'current_rank_proxy':mapped[1] if mapped else None,
                    'current_rank_basis':mapped[2] if mapped else None,'source_zero_basis':p.get('zero_basis')})
            for row,_,basis in current[len(source):]:
                points[row['player_id']]=0.0
                side_ledger.append({'player_master_id':row['player_id'],'position':pos,'dk_points':0.,
                    'basis':'Complete analog realization contains no additional role holder; conditional realized zero, not expected zero',
                    'current_rank_basis':basis,'residual':False})
        dst=universe[(current_team,'DST')][0][0]['player_id'];points[dst]=side['dst']
        # Recheck the complete ledgers, including unselected and anonymous actors.
        for a,b in [('passing_yards','receiving_yards'),('passing_tds','receiving_tds'),('completions','receptions')]:
            if sum(p['stats'][a] for p in side['players']) != sum(p['stats'][b] for p in side['players']):
                raise ValueError('Paired source game violates passing/receiving accounting')
        ledger.append({'current_team':current_team,'source_team':side['team'],'budget':side['budget'],
            'corrected_dst_points':side['dst'],'actors':side_ledger})
    return points,ledger


def build_states(library, full_rows, eligible, *, seed=7):
    games=library['games']
    if len(games)<20:
        raise ValueError('Insufficient reconciled paired-game analog support')
    universe,audit=role_universe(full_rows,eligible)
    target_ids=sorted({r['game_id'] for r in eligible})
    if len(target_ids)>10:
        raise ValueError('Bounded research supports at most ten games')
    schedule={g['game_id']:g for g in library['target_schedule']}
    contexts,analogs={},{}
    vector=lambda g:[float(g['total_line']),float(g['home_margin_line']),*[float(s['qb_prior_carries']) for s in g['sides']]]
    vectors=[vector(g) for g in games]
    scales=[statistics.pstdev(v[j] for v in vectors) or 1 for j in range(4)]
    for gid in target_ids:
        native=schedule[gid];home=native['home_team'].replace('LA','LAR') if native['home_team']=='LA' else native['home_team'];away=native['away_team']
        if away=='LA':away='LAR'
        rows=[r for r in eligible if r['game_id']==gid]
        h=next((r for r in rows if team(r)==home),None);a=next((r for r in rows if team(r)==away),None)
        ref=h or a
        if ref is None:raise ValueError('Missing frozen market')
        margin=-float(h['team_spread_line']) if h else float(a['team_spread_line'])
        target=[float(ref['game_total_line']),margin,universe[(home,'QB')][0][1],universe[(away,'QB')][0][1]]
        nearest=sorted(enumerate(games),key=lambda pair:(sum(((v-t)/s)**2 for v,t,s in zip(vectors[pair[0]],target,scales)),pair[1]['game_id']))[:40]
        distances=[sum(((v-t)/s)**2 for v,t,s in zip(vectors[i],target,scales)) for i,g in nearest]
        weights=[math.exp(-.5*(d-min(distances))) for d in distances]
        analogs[gid]=([g for _,g in nearest],weights)
        contexts[gid]={'home':home,'away':away,'total_line':target[0],'home_margin_line':margin,
            'qb_carries_proxies':target[2:],'nearest_squared_distance':min(distances),'furthest_squared_distance':max(distances),
            'effective_kernel_support':sum(weights)**2/sum(w*w for w in weights),'retained_analogs':len(nearest)}
    rng=random.Random(seed)
    def sampled():return {gid:rng.choices(*analogs[gid],k=1)[0] for gid in target_ids}
    plans=[('seeded_context_'+str(i+1),sampled(),None) for i in range(8)]
    for kind in ['favored_stalled','low_pace','productive_both']:
        for gid in target_ids:
            selected=sampled();near,_=analogs[gid];favored=0 if contexts[gid]['home_margin_line']>=0 else 1
            if kind=='favored_stalled':
                median=statistics.median(g['sides'][favored]['budget']['plays'] for g in near)
                choices=[g for g in near if g['sides'][favored]['budget']['plays']>=median]
                chosen=min(choices,key=lambda g:(g['sides'][favored]['budget']['points']/max(1,g['sides'][favored]['budget']['drives']),g['game_id']))
            elif kind=='low_pace':chosen=min(near,key=lambda g:(sum(s['budget']['plays'] for s in g['sides']),g['game_id']))
            else:chosen=max(near,key=lambda g:(min(s['budget']['points'] for s in g['sides']),g['game_id']))
            selected[gid]=chosen;plans.append((kind+':'+gid,selected,gid))
    states=[]
    for sid,chosen,stress_game in plans:
        points={};ledgers=[]
        for gid,template in chosen.items():
            c=contexts[gid];p,ledger=map_game(template,c['home'],c['away'],universe)
            if set(p)&set(points):raise ValueError('Canonical player occurs in two games')
            points.update(p);ledgers.append({'game_id':gid,'source_game_id':template['game_id'],'teams':ledger})
        if any(r['player_master_id'] not in points for r in eligible):raise ValueError('Unscored eligible role')
        states.append({'state_id':sid,'stress_game_id':stress_game,'points':points,'games':ledgers})
    return states,{'role_audit':audit,'contexts':contexts,'scales':scales,'historical_games':len(games),
        'probability_status':'Designed conditional stress states and analog kernel, not calibrated forward probabilities',
        'limitations':['Healthy-leading-role conditioned historical library; strong selection bias',
          'Cross-season within-position pregame role-rank transport is unvalidated',
          'Frozen starting-QB assumptions include questionable players; exclusion does not transfer their volume',
          'No rescaling to player means; this is a generation stress experiment, not a replacement projection model']}


def generate(snapshot, states, params, *, research_solver_seconds=None):
    if research_solver_seconds is not None and (not 0 < research_solver_seconds <= 10 or len(states)>38):
        raise ValueError('Invalid bounded workload research generation budget')
    candidates,attempts=[],[]
    lookup={r['player_master_id']:r for r in snapshot['players']}
    for state in states:
        variables,model=pulp.LpProblem.fromDict(deepcopy(snapshot['model']))
        pvars={ref['player_master_id']:variables[name] for name,ref in snapshot['variable_players'].items()}
        for pid,var in pvars.items():
            if float((params.get('maximum_exposure_by_player') or {}).get(pid,params.get('max_exposure',1)))==0:model+=var==0
        model.setObjective(pulp.lpSum(state['points'][pid]*var for pid,var in pvars.items()))
        solver=make_cbc_solver();solver.options.extend(['randomSeed 7','randomCbcSeed 7'])
        if research_solver_seconds is not None:solver.timeLimit=research_solver_seconds;solver.threads=1
        model.solve(solver)
        proven=model.status==pulp.LpStatusOptimal and model.sol_status==pulp.LpSolutionOptimal
        attempts.append({'state_id':state['state_id'],'solver_status':pulp.LpStatus[model.status] if research_solver_seconds is None or proven else 'unproven_abstained'})
        if model.status!=pulp.LpStatusOptimal or (research_solver_seconds is not None and not proven):continue
        ids=sorted(pid for pid,var in pvars.items() if pulp.value(var)>.5)
        if len(ids)!=9:raise ValueError('Invalid canonical roster')
        candidates.append({'candidate_id':CONTRACT+':'+state['state_id'],'roster':[{'player_master_id':pid,'role':'SELECTED'} for pid in ids],
            'allocated_idea_id':'empirical:'+state['state_id'],'generation_state_id':state['state_id'],'scenario_ids':[],
            'baseline_mean':sum(lookup[pid]['projection'] for pid in ids),'salary':sum(lookup[pid]['salary'] for pid in ids),
            'candidate_objective':'Complete paired-game joint realized DK score; conditional stress, likelihood unknown',
            'conditional_state_score':sum(state['points'][pid] for pid in ids)})
    return candidates,{'scoring_contract':SCORING_CONTRACT,'attempts':attempts,'variants':len(candidates),'distinct_canonical_rosters':len({signature(c) for c in candidates}),
        'generation_experiment':True,'outcomes_used':False,'base_projections_changed':False}


def legacy_select(candidates,worlds,rows,params,requested,plan):
    """Sequential slot policy on finite pool; original ILP search is NOT reproduced.

Only candidate choice changes: original construction/fallback order, conditional
    objective, and sequential hard portfolio controls remain explicit.
    """
    from .classic_portfolio_controls import explicit_appearance_limit
    from .classic_primary_game import canonical_primary_game
    from .single_lineup import elevated_player
    controls=AllocationControls.model_validate(plan['controls']);lookup={r['player_master_id']:r for r in rows}
    worldmap={w['scenario_id']:w for w in worlds};ideas=plan['ideas'];selected=[];counts=Counter();pairs=Counter();triples=Counter();attempts=[]
    locks=set(params.get('locked_player_ids') or []);maximums=params.get('maximum_exposure_by_player') or {};minimums=params.get('minimum_exposure_by_player') or {}
    def feasible(ids):
        remaining=requested-len(selected)
        for pid,row in lookup.items():
            limit=requested if pid in locks else math.ceil(requested*float(params.get('max_exposure',1)))
            if pid in maximums:limit=min(limit,explicit_appearance_limit(requested,float(maximums[pid])))
            if params.get('elevated_player_max_exposure') is not None and elevated_player(row,params.get('data_cutoff_at')):limit=min(limit,explicit_appearance_limit(requested,float(params['elevated_player_max_exposure'])))
            if pid in ids and counts[pid]>=limit:return False
            if math.ceil(requested*float(minimums.get(pid,0)))-counts[pid]>=remaining and pid not in ids:return False
        overlap=params.get('max_lineup_overlap',9)
        if params.get('minimum_uniqueness') is not None:overlap=min(overlap,9-int(params['minimum_uniqueness']))
        if any(len(ids&{p['player_master_id'] for p in c['roster']})>overlap for c in selected):return False
        if any(n>=math.ceil(requested*controls.receiving_core_max_fraction) and set(g)<=ids and not set(g)<=locks for g,n in pairs.items()):return False
        if any(n>=math.ceil(requested*controls.shared_triple_max_fraction) and set(g)<=ids and not set(g)<=locks for g,n in triples.items()):return False
        if params.get('max_lineups_per_primary_game') is not None:
            used=Counter(canonical_primary_game(team(lookup[p['player_master_id']]),opponent(lookup[p['player_master_id']])) for c in selected for p in c['roster'] if lookup[p['player_master_id']]['position']=='QB')
            if any(used[canonical_primary_game(team(lookup[p]),opponent(lookup[p]))]>=params['max_lineups_per_primary_game'] for p in ids if lookup[p]['position']=='QB'):return False
        return True
    for slot in plan['slots']:
        primary=next(i for i in ideas if i['idea_id']==slot['idea_id']);actual_ideas=Counter(c['allocated_idea_id'] for c in selected)
        actual_games=Counter(next(i['game_id'] for i in ideas if i['idea_id']==c['allocated_idea_id']) for c in selected)
        scripts=Counter(next(i['script'] for i in ideas if i['idea_id']==c['allocated_idea_id']) for c in selected)
        def priority(i):return (i['credibility_score']+(controls.new_script_credit if not scripts[i['script']] else 0))/(1+controls.game_repeat_penalty*actual_games[i['game_id']]+controls.idea_repeat_penalty*actual_ideas[i['idea_id']])
        alternatives=[primary]+sorted([i for i in ideas if i['idea_id']!=primary['idea_id']],key=lambda i:(-priority(i),i['idea_id']))
        for idea in alternatives:
            if actual_ideas[idea['idea_id']]>=idea.get('discovery_max_lineups',requested):continue
            matches=[]
            for index,c in enumerate(candidates):
                ids={p['player_master_id'] for p in c['roster']}
                if not feasible(ids) or not audit_construction(ids,rows,idea,controls)['passed'] or not set(idea.get('discovery_required_player_ids',[]))<=ids:continue
                w=worldmap[idea['idea_id']]
                objective=sum(w['moments'][pid]['mean']+.35*(w['moments'][pid]['p90']-w['moments'][pid]['mean']) for pid in ids)
                matches.append((objective,index,c))
            attempts.append({'slot':slot['slot'],'planned_idea_id':primary['idea_id'],'attempted_idea_id':idea['idea_id'],'feasible_candidates':len(matches),'replacement':idea is not primary})
            if not matches:continue
            objective,index,c=max(matches,key=lambda x:(x[0],-x[1]));c=deepcopy(c);c.update(allocated_idea_id=idea['idea_id'],allocation_slot=slot['slot'],legacy_conditional_objective=objective)
            selected.append(c);ids=sorted(p['player_master_id'] for p in c['roster']);counts.update(ids);triples.update(combinations(ids,3))
            for t in {team(lookup[p]) for p in ids}:pairs.update(combinations([p for p in ids if team(lookup[p])==t and lookup[p]['position'] in {'WR','TE'}],2))
            break
    return selected,{'solver_status':'finite_pool_complete' if len(selected)==requested else 'underfilled','requested':requested,'achieved':len(selected),
        'constraints_relaxed':False,'attempts':attempts,'objective':'Legacy sequential slot policy adapted to frozen candidates; mean+.35 marginal spread, not joint upside',
        'differences':['Finite pool replaces ILP candidate search','Original challenger and teammate generation stages not rerun in selector-only comparison']}
