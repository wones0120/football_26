"""Validate the frozen completion artifact independently of its narrative."""
from collections import Counter
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path

import pytest

from backend.app.product_services.classic_prospective import digest_payload
from scripts.complete_week4_thesis_analysis import allocation_delta
from scripts.render_week4_thesis_completion import render


ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture(scope='module')
def evidence():
    def read(name):
        return json.loads((ROOT / 'artifacts' / name).read_text())
    return (read('week4-thesis-frozen-analysis-inputs-8b5c114c.json'),
            read('week4-dynamic-thesis-shadow-8b5c114c.json'),
            read('week4-thesis-opportunity-cost-8b5c114c-v2.json'))


def test_frozen_lineage_and_production_boundary(evidence):
    inputs, shadow, supplement = evidence
    for record in (shadow, supplement):
        assert digest_payload({k:v for k,v in record.items() if k!='sha256'}) == record['sha256']
    report=inputs['report']
    assert len(report['all_candidates']) == 205
    assert report['selected_ranks'] == [31,48,83,90,93]
    assert report['frozen_solver_snapshot']['payload']['options']['portfolio_constraints'] == {
        'distinct_qb_paths':True,'max_lineup_overlap':4}
    assert digest_payload(inputs)==supplement['input_sha256']
    assert digest_payload({'candidates':report['all_candidates']})==shadow['source']['candidate_universe_sha256']
    assert supplement['source_shadow_sha256']==shadow['sha256']
    assert sha256((ROOT/'scripts/complete_week4_thesis_analysis.py').read_bytes()).hexdigest()==supplement['analysis_script_sha256']
    assert datetime.fromisoformat(supplement['frozen_at'])<datetime.fromisoformat(shadow['source']['first_kickoff_at'])
    for name, expected in supplement['code_sha256'].items():
        assert sha256((ROOT/'backend/app/product_services'/name).read_bytes()).hexdigest()==expected


def test_diagnostic_rosters_are_legal_and_accounting_conserves_points(evidence):
    inputs, shadow, supplement=evidence
    from backend.app.product_services.gpp_optimizer import Player
    players={p['player_id']:Player(**{**p,'tags':set(p['tags'])}) for p in supplement['players']}
    risk={r['player_id']:r for r in inputs['report']['prospective_experiment']['availability_risk']['players']}
    candidates=inputs['report']['all_candidates']
    frontier=max(c['objective_score'] for c in candidates)
    all_rows=[]
    for control in supplement['qb_controls']:
        for kind in ('comparable','relaxed'):
            row=control[kind]
            assert control['qb_id'] in row['player_ids']
            all_rows.append(row)
            delta=allocation_delta(supplement['base'],row,players)
            for axis in ('mean','p90'):
                assert delta[f'non_qb_{axis}_gain']-delta[f'qb_{axis}_sacrificed']==pytest.approx(delta[f'net_{axis}_gain'])
                assert sum(d[f'{axis}_gain'] for d in delta['positions'].values())==pytest.approx(delta[f'non_qb_{axis}_gain'])
            assert sum(d['salary_gain'] for d in delta['positions'].values())==delta['non_qb_salary_gain']
            if kind=='comparable':
                assert row['stack']['partner_count']==2 and row['stack']['bring_back_count']==0
                assert sum(players[pid].position=='RB' for pid in row['player_ids'])==3
                assert len(set(row['player_ids'])&set(supplement['base']['player_ids']))>=4
                assert any(players[pid].position=='TE' and players[pid].team==row['qb']['team'] for pid in row['player_ids'])
    for d in supplement['forced_diagnostics']:
        assert d['candidate_count']==0
        assert d['player_id'] in d['best']['player_ids']
        assert d['best']['objective_score']==max(r['objective_score'] for r in d['template_probes'] if r)
        assert d['single_swap_cap_feasible']
        all_rows += [r for r in d['template_probes'] if r]
    for row in all_rows:
        roster=[players[pid] for pid in row['player_ids']]
        assert len(roster)==len(set(row['player_ids']))==9
        counts=Counter(p.position for p in roster)
        assert counts['QB']==counts['DST']==counts['TE']==1
        assert counts['RB']>=2 and counts['WR']>=3
        assert row['salary']==sum(p.salary for p in roster)<=50000
        assert row['mean']==pytest.approx(sum(p.projection for p in roster))
        assert row['p90']==pytest.approx(sum(p.ceiling for p in roster))
        assert row['objective_score']==pytest.approx(sum(row['components'].values()))
        assert row['equivalent_global_rank']==1+sum(c['objective_score']>row['objective_score']+1e-9 for c in candidates)
        assert row['frontier_loss']==pytest.approx(frontier-row['objective_score'])
        assert max(Counter(p.team for p in roster).values())<=4
        assert max(Counter(p.game_id for p in roster).values())<=5
        assert sum('punt' in p.tags for p in roster)<=2
        assert sum(risk.get(p.player_id,{}).get('bucket')=='questionable_elevated' for p in roster)<=1
        dst=next(p for p in roster if p.position=='DST')
        assert not any(p.team==dst.opponent for p in roster if p.position!='DST')


def test_final_report_is_reproducible_and_covers_requirements(evidence):
    report=render(*evidence)
    assert report==(ROOT/'WEEK4_DYNAMIC_THESIS_PORTFOLIO_SHADOW.md').read_text()
    for phrase in ('Required final answers','Where the saved salary goes','Overlap',
                   'GENUINE SALARY-EFFICIENCY THESIS','Jaxon Smith-Njigba','Lamar Jackson',
                   'Justin Jefferson','Bucky Irving','Brock Bowers'):
        assert phrase in report
    _,shadow,supplement=evidence
    assert shadow['shadow_portfolios']['5']['selected_ranks']==[1,6,31,48,83]
    assert shadow['shadow_portfolios']['20']['directional_qb_exposure']=={
        'Trevor Lawrence':12,'Joe Burrow':4,'Jacoby Brissett':4}
    jsn=next(d for d in supplement['forced_diagnostics'] if d['player']=='Jaxon Smith-Njigba')
    assert jsn['best']['frontier_loss']<.20
    assert jsn['best']['stack']['partner_count']==3
