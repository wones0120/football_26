from copy import deepcopy
from datetime import timedelta
from uuid import UUID
import json

import pandas as pd
import pytest

from backend.app.product_services.captain_game_cases import build, checked_history, composition, kicking_profile, FG_DISTANCE_POINTS, FIELDS, VERSION
from backend.app.product_services.captain_case_selection import solve
from backend.app.product_services.optimizer import OptimizerService
from backend.app.product_services.evaluation_record import digest
from backend.app.product_services.showdown_captain_shortlist import build_captain_shortlist
from backend.app.product_services.slate_preparation import SlatePreparationRequest, preparation_summary
from backend.app.tests.product.test_opportunity_yards import yard_receipt
from backend.app.tests.product.test_workload_new_count_consumer import NOW


def sources(monkeypatch):
    pool,_,receipt=yard_receipt(monkeypatch);records=[]
    # The old count fixture intentionally has only30 QB carries, below that
    # producer's40-opportunity peer minimum. Supply explicit synthetic efficiency
    # for this independent scenario fixture (the source records below use12/3).
    for actor in receipt['players']:
        if actor['position']=='QB':
            actor['efficiency']['rushing_yards']=dict(value=4.,fixture_evidence='12 yards /3 carries')
            actor['projected_yards']['rushing_yards']=actor['counts']['rush_attempts']*4
            actor['utility']=actor['projected_yards']['passing_yards']*.04+actor['projected_yards']['rushing_yards']*.1
            actor['reasons']=[]
    for team_index,team in enumerate(('SF','WAS')):
        members=[p for p in pool if p['player_team']==team]
        kicker=str(UUID(int=100+team_index))
        pool.append(dict(player_id=kicker,name=team+' kicker',player_team=team,opponent_team='WAS' if team=='SF' else 'SF',position='K',salary=3000,
            projection=8,p90=12,canonical_role='expected_starter',role_optimizer_eligible=True,showdown_captain_shortlisted=True))
        receipt['players'].append(dict(player_master_id=kicker,team=team,position='K',name=team+' kicker',native_salary_actor=True,
            counts=dict(pass_attempts=None,rush_attempts=None,targets=None),utility=None,reasons=['not modeled: offensive workload domain only']))
        for season in (2023,2024,2025,2026):
            for week in range(1,7 if season==2026 else 19):
                ptd=(week+team_index)%4;fg=1+(week+2*team_index)%3
                for row in [*members,dict(player_id=kicker,position='K')]:
                    pos=row['position'];raw=dict.fromkeys(FIELDS,0.)
                    raw.update(pass_attempts=30. if pos=='QB' else 0.,completions=float(18+week%5) if pos=='QB' else 0.,passing_yards=float((18+week%5)*(9+week%3)) if pos=='QB' else 0.,rush_attempts={'QB':3.,'RB':17.,'WR':0.,'TE':0.,'K':0.}[pos],
                        targets={'QB':0.,'RB':5.,'WR':12.,'TE':8.,'K':0.}[pos],receptions={'QB':0.,'RB':3.,'WR':8.,'TE':5.,'K':0.}[pos],
                        passing_tds=float(ptd) if pos=='QB' else 0.,rushing_tds=1. if pos=='RB' else 0.,
                        receiving_tds=float(max(0,ptd-1)) if pos=='WR' else float(min(1,ptd)) if pos=='TE' else 0.,rushing_yards=68. if pos=='RB' else 12. if pos=='QB' else 0.)
                    if pos=='K':raw.update(fg_att=float(fg+1),fg_made=float(fg),fg_made_20_29=1.,fg_made_40_49=float(fg-1),pat_att=float(ptd+1),pat_made=float(ptd+1))
                    records.append(dict(player_master_id=row['player_id'],source_player_id='native:'+row['player_id'],team=team,opponent='WAS' if team=='SF' else 'SF',position=pos,
                        period=season*100+week,source_id=len(records)+1,imported_at=NOW.isoformat(),**raw))
    games=[dict(game_id='2026_07_WAS_SF',home_team='SF',away_team='WAS')]
    markets=[dict(game_id=games[0]['game_id'],game_total=50.5,home_spread=-3.,source='fixture',observed_at=NOW.isoformat())]
    return pool,receipt,records,games,markets


def prepared(monkeypatch):
    pool,receipt,records,games,markets=sources(monkeypatch)
    result=build(receipt,records,pool,before_period=202607,cutoff=NOW,games=games,markets=markets)
    return pool,result


def test_shared_football_events_and_count_budgets_reconcile(monkeypatch):
    pool,receipt=prepared(monkeypatch)
    assert receipt['scenario_first']['world_count']==20
    assert receipt['scenario_first']['likelihood']=='unknown'
    primary=receipt['scenario_first']['primary_scenario']
    assert len(primary['case_ids'])==4 and len(primary['diagnostic_case_ids'])==16
    assert primary['implied_points']=={'SF':26.75,'WAS':23.75}
    for world in receipt['scenario_first']['worlds']:
        for team,ledger in world['teams'].items():
            ids={p['player_master_id'] for p in receipt['players'] if p['team']==team}
            stats=[s for pid,s in world['player_stats'].items() if pid in ids]+[ledger['unknown']]
            for channel in ('pass_attempts','rush_attempts','targets'):
                assert sum(s[channel] for s in stats)==ledger[channel]
            import math
            for channel in ('targets','rush_attempts'):
                audit=ledger['opportunity_allocation'][channel]
                assert not audit['additional_count_noise']
                for pid,expected in audit['conditional_expected'].items():
                    assert math.floor(expected)<=world['player_stats'][pid][channel]<=math.ceil(expected)
            assert sum(s['passing_tds'] for s in stats)==sum(s['receiving_tds'] for s in stats)==ledger['passing_tds']
            assert sum(s['rushing_tds'] for s in stats)==ledger['rushing_tds']
            assert sum(s['pat_made'] for s in stats)==ledger['made_pats']
            assert sum(s['passing_yards'] for s in stats)==pytest.approx(sum(s['receiving_yards'] for s in stats))
            assert ledger['points']==6*ledger['touchdowns']+ledger['made_pats']+3*ledger['made_field_goals']
            assert ledger['targets']<=ledger['pass_attempts']
            kick=ledger['kicking_profile']
            assert ledger['made_field_goals']+ledger['missed_field_goals']==ledger['field_goal_attempts']==kick['attempts']
            assert sum(kick['distance_counts'].values())==kick['made']==ledger['made_field_goals']
            assert sum(v['fg_points'] for v in stats)==kick['fg_points']==sum(kick['distance_counts'][k]*p for k,p in FG_DISTANCE_POINTS.items())
            assert len([e for e in world['events'] if e['team']==team and e['kind']=='missed_fg'])==kick['missed']
            assert all(s['receiving_tds']<=s['receptions']<=s['targets'] and s['passing_tds']<=s['pass_attempts'] and s['rushing_tds']<=s['rush_attempts'] for s in stats)
            # These complete fixture donors have exactly one observed passer.
            # Independent model disagreement must not manufacture a backup.
            qb=receipt['starter_ids'][team];qb_stats=world['player_stats'][qb]
            assert ledger['quarterback_pass_residual']==0
            assert qb_stats['pass_attempts']==ledger['pass_attempts']
            assert qb_stats['passing_tds']==ledger['passing_tds']
            assert qb_stats['passing_yards']==pytest.approx(ledger['passing_yards'])
            assert sum(r['case_attempts'] for r in ledger['passing_allocation'])==ledger['pass_attempts']
    assert all(p['utility'] is not None for p in receipt['players'] if p['position']=='K')
    json.dumps(receipt,allow_nan=False)


def test_market_changes_scenarios_without_altering_original_forecasts(monkeypatch):
    pool,receipt,records,games,markets=sources(monkeypatch);original=deepcopy(receipt)
    high=build(receipt,records,pool,before_period=202607,cutoff=NOW,games=games,markets=markets)
    low=build(receipt,records,pool,before_period=202607,cutoff=NOW,games=games,markets=[{**markets[0],'game_total':36.}])
    assert receipt==original
    assert high['scenario_first']['worlds'][0]['teams']['SF']['points']>low['scenario_first']['worlds'][0]['teams']['SF']['points']
    assert low['scenario_first']['primary_scenario']['implied_points']=={'SF':19.5,'WAS':16.5}
    reversed_market=build(receipt,records,pool,before_period=202607,cutoff=NOW,games=games,markets=[{**markets[0],'home_spread':3.}])
    assert reversed_market['scenario_first']['primary_scenario']['implied_points']=={'SF':23.75,'WAS':26.75}
    for w in high['scenario_first']['worlds'][:4]:
        for team,t in w['teams'].items():
            assert t['target_points']==high['scenario_first']['primary_scenario']['implied_points'][team]
            assert abs(t['points']-t['target_points'])<=3
    for a in high['players']:
        if a['utility'] is not None:
            assert a['utility']==pytest.approx(sum(a['scenario_scores'][wid] for wid in high['scenario_first']['primary_scenario']['case_ids'])/4)
    assert [a['scenario_scores'] for a in high['players']]!=[a['scenario_scores'] for a in low['players']]
    assert [a['counts'] for a in high['players']]==[a['counts'] for a in original['players']]
    assert high['scenario_first']['volume_response']['training_max_period']<202607
    # Arbitrary display names and point projections cannot change physical cases.
    renamed=deepcopy(pool)
    for p in renamed:p.update(name='Renamed',projection=999999,p90=999999)
    again=build(receipt,records,renamed,before_period=202607,cutoff=NOW,games=games,markets=markets)
    assert again['scenario_first']['worlds']==high['scenario_first']['worlds']


def test_future_and_missing_kicking_evidence_are_explicit(monkeypatch):
    pool,receipt,records,games,markets=sources(monkeypatch)
    future=deepcopy(records);future[0]['period']=202607
    with pytest.raises(ValueError,match='future'):checked_history(future,before_period=202607,cutoff=NOW)
    future=deepcopy(records);future[0]['imported_at']=(NOW+timedelta(days=1)).isoformat()
    with pytest.raises(ValueError,match='future'):checked_history(future,before_period=202607,cutoff=NOW)
    kicker=next(p for p in pool if p['position']=='K')['player_id']
    for r in records:
        if r['player_master_id']==kicker and r['period']//100==2026:r['pat_att']=None
    result=build(receipt,records,pool,before_period=202607,cutoff=NOW,games=games,markets=markets)
    actor=next(a for a in result['players'] if a['player_master_id']==kicker)
    assert actor['utility'] is None and 'Missing current-team FG/PAT' in ' '.join(actor['reasons'])
    assert all(w['teams']['SF']['kicker']=='__unallocated__' for w in result['scenario_first']['worlds'])
    for w in result['scenario_first']['worlds']:
        t=w['teams']['SF'];assert t['unknown']['fg_points']==t['kicking_profile']['fg_points'] and t['unknown']['pat_made']==t['made_pats']


@pytest.mark.parametrize('values,chosen',[([100.,0.],'safe'),([100.,100.,0.],'volatile')])
def test_whole_roster_objective_differs_from_mean_with_same_legal_pool(monkeypatch,values,chosen):
    pool,receipt=prepared(monkeypatch)
    pool=[p for p in pool if p['position']!='K'];sf=[p for p in pool if p['player_team']=='SF'];was=[p for p in pool if p['player_team']=='WAS']
    volatile=next(p for p in sf if p['position']=='QB')['player_id'];safe=next(p for p in sf if p['position']=='TE')['player_id']
    captain=next(p for p in sf if p['position']=='RB')['player_id'];locked={p['player_id'] for p in sf if p['position'] in {'RB','WR'}}|{p['player_id'] for p in was if p['position'] in {'QB','RB','WR'}}
    worlds=[]
    for index,value in enumerate(values):
        scores={p['player_id']:10. for p in pool};scores[volatile]=value;scores[safe]=40.
        worlds.append(dict(world_id='case'+str(index),coordinate='central',player_scores=scores,player_stats={pid:dict(receiving_tds=0,rushing_tds=0,passing_tds=0,fg_points=0,pat_made=0) for pid in scores},teams={}))
    primary_ids=[w['world_id'] for w in worlds]
    diagnostic=deepcopy(worlds[0]);diagnostic.update(world_id='alternative',coordinate='home_ahead')
    diagnostic['player_scores'][volatile]=100000.
    worlds.append(diagnostic)
    receipt['scenario_first']['worlds']=worlds
    receipt['scenario_first']['primary_scenario'].update(case_ids=primary_ids,diagnostic_case_ids=['alternative'])
    for a in receipt['players']:
        a['scenario_scores']={w['world_id']:w['player_scores'][a['player_master_id']] for w in worlds} if a['player_master_id'] in worlds[0]['player_scores'] else {}
        a['utility']=sum(a['scenario_scores'].values())/len(worlds) if a['scenario_scores'] else None
    params=dict(workload_comparison='scenario_first',captain_positions=['RB','WR'],num_lineups=1,max_exposure=1,captain_max_exposure=1,
        prepared_input_evidence=dict(workload_forecast=receipt))
    frame,shortlist=build_captain_shortlist(pd.DataFrame(pool),params=params,flex_only_ids=set())
    assert shortlist['policy_id']=='scenario_first_supported_captains_v1'
    kwargs=dict(receipt=receipt,params=params,contest_type='captain',stack_params=dict(captain_positions=['RB','WR'],max_players_per_team=4,hard_qb_correlations=True),
        locked_ids=locked,flex_only_ids=set(),avoid_dst_opponents=True,enforce_single_te=False,requested_captain_id=captain)
    lineups,report=solve(OptimizerService.__new__(OptimizerService),frame,**kwargs)
    ids={p['player_id'] for p in lineups[0]};assert (safe in ids and volatile not in ids) if chosen=='safe' else (volatile in ids and safe not in ids)
    assert sum(w['player_scores'][volatile] for w in worlds)>sum(w['player_scores'][safe] for w in worlds) # mean would prefer volatile
    assert report['worst_capture_ratio']==pytest.approx(95/155 if chosen=='safe' else 55/95)
    assert report['competitive_cases']==(1 if chosen=='safe' else 2)
    assert report['total_cases']==len(values) and len(report['selection']['oracles'])==len(values)
    assert report['selection']['alternative_scripts_consumed'] is False
    assert report['alternative_script_evaluations'][0]['selection_consumed'] is False
    assert report['selection']['primary_case_ids']==primary_ids
    assert report['selection']['solver_execution'].startswith('CBC serial')
    assert report['solver_audits'][0]['input_sha256']==digest(report['solver_audits'][0]['input_snapshot'])
    assert all(sum(p['player_team']==t for p in lineups[0])==3 for t in ['SF','WAS'])
    changed=frame.copy();changed['projection']=-999999.;changed['p90']=float('nan')
    # Arbitrarily changing every alternative-script score cannot change the
    # primary objective, its legal benchmarks, tie-break or selected roster.
    changed_receipt=deepcopy(receipt)
    for pid in changed_receipt['scenario_first']['worlds'][-1]['player_scores']:
        changed_receipt['scenario_first']['worlds'][-1]['player_scores'][pid]=999999. if pid==safe else 0.
    kwargs['receipt']=changed_receipt
    other,again=solve(OptimizerService.__new__(OptimizerService),changed,**kwargs)
    assert {(p['player_id'],p['roster_position']) for p in other[0]}=={(p['player_id'],p['roster_position']) for p in lineups[0]}
    assert again['selection_value']==report['selection_value']
    assert again['selection']['case_optima']==report['selection']['case_optima']
    invalid=deepcopy(receipt);invalid['scenario_first']['primary_scenario']['case_ids'].append('alternative')
    with pytest.raises(ValueError,match='market-centered primary'):
        solve(OptimizerService.__new__(OptimizerService),frame,**{**kwargs,'receipt':invalid})
    params['num_lineups']=2
    with pytest.raises(ValueError,match='exactly one'):solve(None,frame,**kwargs)


def test_explicit_prepare_handoff_and_compact_summary(monkeypatch):
    from backend.app.product_services.analyst_preparation import bind_handoff
    pool,receipt=prepared(monkeypatch)
    request=SlatePreparationRequest(season=2026,week=7,slate='TEST',action='prepare',contest_format='showdown',scenario_first_captain=True)
    assert request.include_workload_forecast and request.learned_opportunities and request.opportunity_yards
    with pytest.raises(ValueError,match='Showdown Prepare'):
        SlatePreparationRequest(season=2026,week=7,slate='TEST',action='prepare',scenario_first_captain=True)
    payload=dict(params=dict(workload_comparison='scenario_first'));bind_handoff(payload,dict(workload_forecast=receipt))
    with pytest.raises(ValueError,match='scenario-first'):
        bind_handoff(dict(params=dict(workload_comparison='learned_yards')),dict(workload_forecast=receipt))
    for version in ['captain_shared_scoring_cases_v1','captain_shared_scoring_cases_v2','captain_shared_scoring_cases_v3','captain_shared_scoring_cases_v4','captain_shared_scoring_cases_v5']:
        old=deepcopy(receipt);old['scenario_first']['version']=version
        with pytest.raises(ValueError,match='current scenario-first case version'):
            bind_handoff(dict(params=dict(workload_comparison='scenario_first')),dict(workload_forecast=old))
    before=deepcopy(receipt);summary=preparation_summary(dict(workload_forecast=receipt))['workload_forecast']
    assert summary['scenario_first']['world_count']==20
    assert 'worlds' not in summary['scenario_first'] and 'source_ids' not in summary['scenario_first']
    assert summary['players'][0]['scenario_role_evidence'] is not None
    assert receipt==before


def test_missing_current_starter_proof_cannot_receive_unallocated_passing(monkeypatch):
    pool,receipt,records,games,markets=sources(monkeypatch)
    starter=receipt['starter_ids']['SF'];actor=next(a for a in receipt['players'] if a['player_master_id']==starter)
    actor['current_role_evidence']=None
    with pytest.raises(ValueError,match='Sourced current starter'):
        build(receipt,records,pool,before_period=202607,cutoff=NOW,games=games,markets=markets)


def test_scoring_profile_never_extrapolates_low_score_field_goals():
    rows=[dict(period=202601,pass_tds=0,rush_tds=0,fg_made=3,source_ids=[1]),
          dict(period=202602,pass_tds=2,rush_tds=1,fg_made=2,source_ids=[2]),
          dict(period=202603,pass_tds=1,rush_tds=2,fg_made=1,source_ids=[3])]
    for draw in range(4):
        td,fg,ids=composition(26.75,rows,draw)
        assert (td,fg,ids) in [(3,2,[2]),(3,1,[3])]  # Actual nearby combinations; no scaled FG-only profile
    with pytest.raises(ValueError,match='source-supported'):
        composition(26.75,rows[:1],0)


def test_feasible_only_benchmark_never_becomes_optimal_fallback(monkeypatch):
    import pulp
    pool,receipt=prepared(monkeypatch)
    params=dict(num_lineups=1,max_exposure=1,captain_max_exposure=1,captain_positions=['RB','WR'])
    def feasible_only(model,*args,**kwargs):
        model.status=pulp.LpStatusOptimal  # CBC/PuLP can report this on a timed incumbent.
        model.sol_status=pulp.LpSolutionIntegerFeasible
        return model.status
    monkeypatch.setattr(pulp.LpProblem,'solve',feasible_only)
    with pytest.raises(ValueError,match='lacks Optimal proof'):
        solve(OptimizerService.__new__(OptimizerService),pd.DataFrame(pool),receipt=receipt,params=params,
            contest_type='captain',stack_params=dict(captain_positions=['RB','WR'],max_players_per_team=4),
            locked_ids=set(),flex_only_ids=set(),avoid_dst_opponents=True,enforce_single_te=False,requested_captain_id=None)


def test_complete_captain_and_specified_reference_comparisons_share_the_frozen_pool(monkeypatch):
    pool,receipt=prepared(monkeypatch)
    frame,shortlist=build_captain_shortlist(pd.DataFrame(pool),params=dict(workload_comparison='scenario_first',captain_positions=['RB','WR'],prepared_input_evidence=dict(workload_forecast=receipt)),flex_only_ids=set())
    sf=[p for p in pool if p['player_team']=='SF' and p['position'] in ['QB','RB','WR']]
    was=[p for p in pool if p['player_team']=='WAS' and p['position'] in ['RB','WR','TE']]
    ids=[p['player_id'] for p in sf+was];captain=next(p['player_id'] for p in sf if p['position']=='WR')
    params=dict(num_lineups=1,max_exposure=1,captain_max_exposure=1,captain_positions=['RB','WR'],scenario_role_preference=dict(enabled=True),scenario_reference_roster=dict(player_ids=ids,captain_player_id=captain))
    before=deepcopy(receipt)
    lineups,report=solve(OptimizerService.__new__(OptimizerService),frame,receipt=receipt,params=params,contest_type='captain',
        stack_params=dict(captain_positions=['RB','WR'],max_players_per_team=4),locked_ids=set(),flex_only_ids=set(),avoid_dst_opponents=True,enforce_single_te=False,requested_captain_id=None)
    assert receipt==before
    alternative=report['different_captain_comparison'];reference=report['reference_comparison']
    assert alternative['achieved']==1 and len(alternative['roster'])==6
    selected=next(p['player_id'] for p in lineups[0] if p['roster_position']=='CPT')
    assert next(p['player_master_id'] for p in alternative['roster'] if p['role']=='CPT')!=selected
    assert alternative['selection_value']<=report['selection_value']+1e-6
    assert {p['player_master_id'] for p in reference['roster']}==set(ids)
    assert reference['legal_under_current_constraints']
    assert report['reference_captain_comparison']['achieved']==1
    assert sum(p['salary'] for p in alternative['roster'])<=50000
    assert not report['points_selection_gates_consumed']


def test_kicking_profile_retains_joint_distance_mix_misses_and_identity():
    # Four made kicks from one donor must not independently become four long
    # kicks sampled from a different marginal mix. Multiple donor kickers remain
    # explicit instead of inventing one canonical historical identity.
    rows=[]
    for sid,pid,made,attempts,short,long in [(1,'a',3,4,2,1),(2,'b',1,1,1,0)]:
        row=dict.fromkeys(FG_DISTANCE_POINTS,0.)
        row.update(source_id=sid,position='K',player_master_id=pid,source_player_id='native:'+pid,team='A',period=202601,
                   fg_made=made,fg_att=attempts,fg_made_20_29=short,fg_made_50_59=long)
        rows.append(row)
    other={**rows[0],'source_id':3,'period':202602,'fg_made_20_29':0.,'fg_made_50_59':3.}
    profile=kicking_profile([*rows,other],[1,2])
    assert profile['made']==4 and profile['attempts']==5 and profile['missed']==1
    assert profile['fg_points']==14 and profile['distance_counts']['fg_made_20_29']==3
    assert profile['source_ids']==[1,2] and {k['player_master_id'] for k in profile['donor_kickers']}=={'a','b'}
    assert rows[0]['fg_made_20_29']==2  # No input mutation.
    for change in [dict(fg_att=None),dict(fg_att=2),dict(fg_made_50_59=None),dict(fg_made_50_59=2),dict(fg_att=3.5)]:
        with pytest.raises(ValueError,match='field-goal'):kicking_profile([{**rows[0],**change}],[1])
    with pytest.raises(ValueError,match='field-goal'):kicking_profile([*rows,other],[1,3])
    zero={**rows[0],**dict.fromkeys(FG_DISTANCE_POINTS,0.),'fg_made':0.,'fg_att':1.}
    assert kicking_profile([zero],[1])['fg_points']==0
    assert kicking_profile([zero],[1])['missed']==1
