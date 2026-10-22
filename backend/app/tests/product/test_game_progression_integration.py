"""Narrow integration safeguards without empirical-source reads or simulation."""
from copy import deepcopy
import pytest
from research.game_progression_pilot_20261020.v1.prepare_integrated import target_context
from research.game_progression_pilot_20261020.v1.run_smoke import planned_keys, complete_capped_rows
from research.game_progression_pilot_20261020.v1 import run_smoke
from research.game_progression_pilot_20261020.v1 import run_smoke_v2
import json

def context():
    return dict(game_id='2026_04_A_B',team='B',period=202604,
        windows={a:dict(game_ids=['g1','g2','g3'],periods=[202601,202602,202603]) for a in ('own','opponent')},
        features={f'weekly3_{a}_{c}_attempts_mean': v for a in ('own','opponent') for c,v in [('pass',20),('rush',10)]})

def test_prior_formula_and_missing_are_not_outcome_fills():
    c=context();assert target_context(c)['own_pass_share']==2/3
    c['windows']['own']['game_ids']=[];assert target_context(c)['own_pass_share'] is None
    c=context();c['features']['weekly3_own_pass_attempts_mean']=None;assert target_context(c)['own_pass_share'] is None

def test_strict_target_prior_scope():
    for periods in ([202601,202602,202604],[202503,202602,202603]):
        c=context();c['windows']['own']['periods']=periods
        with pytest.raises(ValueError):target_context(c)
    c=context();c['windows']['own']['game_ids']=['g1','g1','g2']
    with pytest.raises(ValueError):target_context(c)

def test_cap_backfill_preserves_every_path_and_unknown_not_zero():
    games=[dict(game_id=f'2026_0{i}_A_B') for i in range(1,6)];keys=planned_keys(games)
    assert len(keys)==320 and keys==planned_keys(list(reversed(games)))
    g,p,a=keys[0];row=dict(game_id=g,path=p,arm=a,result=dict(status='UNKNOWN_SOURCE_BLOCK',full_law_known=False))
    original=deepcopy(row);rest=complete_capped_rows([row],keys)
    assert len(rest)==319 and row==original
    assert all(r['result']==dict(status='NOT_FINISHED_HARD_JOB_CAP',full_law_known=False) for r in rest)
    with pytest.raises(ValueError):complete_capped_rows([row,row],keys)

def test_no_scope_substitution():
    with pytest.raises(ValueError):planned_keys([dict(game_id='x')]*5)

@pytest.mark.parametrize('runner',[run_smoke,run_smoke_v2])
def test_whole_job_cap_preserves_paths_without_optimizer_or_real_simulation(tmp_path,monkeypatch,runner):
    games=[dict(game_id=f'2026_0{i}_A_B') for i in range(1,6)]
    manifest=dict(selection_ref={'kind':'selection'},policy_ref={'kind':'policy'},openings_ref={'kind':'openings'},games_ref={'kind':'games'},scope={'planned_paths':320},implementation_refs=[])
    def load(ref):
        if 'kind' not in ref:return manifest
        return {'selection':dict(selected=games),'policy':{},'openings':[],'games':games}[ref['kind']]
    def smoke(policy,openings,actual_games,*,publish_path):
        assert actual_games==games
        g,p,a=planned_keys(games)[0]
        publish_path(dict(game_id=g,path=p,arm=a,seed=17,result=dict(status='UNKNOWN_SOURCE_OPENING',full_law_known=False)))
        raise TimeoutError('fake outer cap after one durable path')
    monkeypatch.setattr(runner,'load',load);monkeypatch.setattr(runner,'mechanics_smoke',smoke)
    dest=tmp_path/'attempt';runner.run(dest)
    summary=json.loads((dest/'SUMMARY.json').read_text());rows=[json.loads(line) for line in (dest/'paths.jsonl').read_text().splitlines()]
    assert summary['status']=='INCOMPLETE_HARD_JOB_CAP' and summary['published_paths']==320
    assert summary['complete_full_law_paths']==0 and rows[0]['result']['status']=='UNKNOWN_SOURCE_OPENING'
    assert summary['status_counts']['NOT_FINISHED_HARD_JOB_CAP']==319
    with pytest.raises(ValueError):runner.run(dest)
