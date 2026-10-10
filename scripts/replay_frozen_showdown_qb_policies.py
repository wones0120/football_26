"""Selection-only historical replay from candidates scored and saved before lock."""
from collections import Counter,defaultdict
from datetime import datetime,UTC
from itertools import combinations
from pathlib import Path
from statistics import mean
from unittest.mock import patch
import hashlib
import math
import pulp
from scripts.run_showdown_qb_policy_experiment import read,write,solver
from backend.app.product_services.classic_prospective import digest_payload
from backend.app.product_services.showdown_portfolio_selection import select_showdown_portfolio,signature


def replay(destination):
    source=Path('artifacts/week4_showdown_production_research_parity/20261001T153239Z')
    frozen=read(source/'production_input_freeze.json');universe=read(source/'common_scored_universe.json');job=read(source/'production_job.json')
    assert digest_payload(frozen)==universe['input_sha256']
    kickoff=datetime.fromisoformat('2026-10-02T00:15:00+00:00')
    assert datetime.fromtimestamp((source/'common_scored_universe.json').stat().st_mtime,UTC)<kickoff
    assert datetime.fromisoformat(job['created_at'])<kickoff
    observations=read(destination/'historical-actuals.json')['observations'];values=defaultdict(set)
    for row in observations:
        if row['player_id'] and row['actual_points'] is not None and row['resolution_status']=='resolved':
            values[str(row['player_id'])].add(round(float(row['actual_points'])/(1.5 if row['roster_position']=='CPT' else 1),5))
    actuals={pid:next(iter(v)) for pid,v in values.items() if len(v)==1}
    candidates=[record['worlds']['baseline'] for record in universe['records']]
    ids=set(str(row['player_id']) for lineup in candidates for row in lineup)
    assert ids<=actuals.keys(), ids-actuals.keys()
    players={str(row['player_id']):row for row in frozen['player_pool']}
    assert players.keys() <= actuals.keys(), "Full DK oracle requires resolved actuals for every frozen salary-pool ID"
    assert all(str(row['player_id']) in players for lineup in candidates for row in lineup)
    def score(lineup): return sum(actuals[str(row['player_id'])]*(1.5 if row['roster_position']=='CPT' else 1) for row in lineup)
    # Independent actual-score oracle uses DK roster legality, with frozen salaries and canonical IDs.
    oracle_players=[r for pid,r in players.items() if pid in actuals]
    model=pulp.LpProblem('ActualScoreDKOracle',pulp.LpMaximize)
    cap={i:pulp.LpVariable(f'c{i}',cat='Binary') for i in range(len(oracle_players))};flex={i:pulp.LpVariable(f'f{i}',cat='Binary') for i in cap}
    model+=pulp.lpSum(cap.values())==1;model+=pulp.lpSum(flex.values())==5
    for i in cap:model+=cap[i]+flex[i]<=1
    model+=pulp.lpSum(float(r['salary'])*(1.5*cap[i]+flex[i]) for i,r in enumerate(oracle_players))<=50000
    for team in set(r['player_team'] for r in oracle_players):model+=pulp.lpSum(cap[i]+flex[i] for i,r in enumerate(oracle_players) if r['player_team']==team)<=5
    model+=pulp.lpSum(actuals[str(r['player_id'])]*(1.5*cap[i]+flex[i]) for i,r in enumerate(oracle_players))
    assert model.solve(solver())==pulp.LpStatusOptimal
    oracle=pulp.value(model.objective);captain_ids=[]
    for i in cap:
        test=model.copy();test+=cap[i]==1
        if test.solve(solver())==pulp.LpStatusOptimal and abs(pulp.value(test.objective)-oracle)<1e-5:captain_ids.append(str(oracle_players[i]['player_id']))
    top=[]
    for _ in range(10):
        assert model.solve(solver())==pulp.LpStatusOptimal
        top.append({'score':pulp.value(model.objective),'captain_id':next(str(oracle_players[i]['player_id']) for i in cap if cap[i].value()>.5),'player_ids':sorted(str(oracle_players[i]['player_id']) for i in cap if cap[i].value()+flex[i].value()>.5)})
        model+=pulp.lpSum(cap[i] for i in cap if cap[i].value()>.5)+pulp.lpSum(flex[i] for i in flex if flex[i].value()>.5)<=5
    policies={}
    for label,maximum in [('A',2),('B',1)]:
        eligible=[l for l in candidates if sum(r['position']=='QB' for r in l)<=maximum]
        limits={pid:math.ceil(5*(1 if r['position']=='QB' and r.get('showdown_qb_eligible') else .4 if float(r.get('base_salary',r['salary']))<=1000 else .8)) for pid,r in players.items()}
        with patch('backend.app.product_services.showdown_portfolio_selection.pulp.PULP_CBC_CMD',side_effect=solver):
            selected,report=select_showdown_portfolio(eligible,requested=5,player_limits=limits,captain_limit=3,require_scenario_diversity=False,soft_scenario_diversity=False)
        scores=[score(l) for l in selected];rosters=[set(signature(l)[1]) for l in selected];captains=[signature(l)[0] for l in selected]
        policies[label]={'selected':selected,'selection_report':report,'requested':5,'generated':len(selected),
            'best_selected_actual_score':max(scores),'best_portfolio_oracle_score':max(scores),'portfolio_total_actual_score':sum(scores),
            'mean_selected_actual_score':mean(scores),'maximum_selected_actual_score':max(scores),'optimal_lineup_regret':oracle-max(scores),
            'actual_oracle_captain_correctness_fraction':sum(c in captain_ids for c in captains)/len(selected),
            'lineups_with_actual_optimal_captain':sum(c in captain_ids for c in captains),'actual_scores':scores,
            'avg_shared_players':mean(len(a&b) for a,b in combinations(rosters,2)),
            'two_qb_exposure':sum(sum(r['position']=='QB' for r in l)==2 for l in selected)/len(selected),
            'qb_captain_exposure':sum(next(r for r in l if r['roster_position']=='CPT')['position']=='QB' for l in selected)/len(selected),
            'top_N_oracle_capture':{str(n):sum(score(l)>=top[n-1]['score']-1e-5 for l in selected) for n in [1,5,10]}}
    output={'season':2026,'week':4,'slate':'THURSDAY_NIGHT','matchup':'PIT/CLE','kickoff':kickoff.isoformat(),
        'source_projection_run_id':frozen['projection_run_id'],'source_input_sha256':digest_payload(frozen),
        'source_candidate_sha256':hashlib.sha256((source/'common_scored_universe.json').read_bytes()).hexdigest(),
        'candidate_archive_mtime':datetime.fromtimestamp((source/'common_scored_universe.json').stat().st_mtime,UTC).isoformat(),
        'source_job_created_at':job['created_at'],'method':'Selection-only replay of 533 saved prelock baseline-scored physical rosters; B removes two-QB candidates. No projection refit or postgame candidate construction.',
        'limitations':['One slate; archived candidate coverage, not a new unrestricted production generation replay.','Policy-specific 95% screen uses archived candidates. No standings success conclusion.','Oracle uses canonical frozen salary pool and DK legality; user preferences and football gates are excluded from the oracle.','Top-N capture counts selected entries scoring at least as highly as the Nth oracle roster, including ties.'],
        'actual_oracle_score':oracle,'actual_optimal_captain_ids':captain_ids,'oracle_top_10':top,'policies':policies}
    write(destination/'historical-replay.json',output)
    print({label:{k:v for k,v in r.items() if k in ['generated','best_selected_actual_score','mean_selected_actual_score','optimal_lineup_regret','two_qb_exposure','qb_captain_exposure','lineups_with_actual_optimal_captain']} for label,r in policies.items()},flush=True)

if __name__=='__main__':replay(Path('artifacts/showdown_qb_policy_controlled/2026w4-monday-2771d4f1'))
