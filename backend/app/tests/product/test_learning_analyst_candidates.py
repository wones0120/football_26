from copy import deepcopy
from datetime import UTC,datetime
import pytest
from backend.app.product_services.optimizer_effectiveness import (extract_saved_pool,candidate_signature,candidate_snapshot,evaluate_run,chronological_validation,build_optimizer_effectiveness)


def config(fmt='showdown'):
    n=6 if fmt=='showdown'else 9
    players=[dict(player_id=f'p{i}',projection=i+1,p90=(i+1)*2,salary=1000,game_id='HOU@JAX 10/18/2026 09:30AM ET')for i in range(n)]
    roster=[dict(player_master_id=f'p{i}',role='CPT'if fmt=='showdown'and i==0 else'FLEX'if fmt=='showdown'else'SELECTED')for i in range(n)]
    raw=dict(candidate_id='source-id',roster=roster,scores={'story-a':{'mean':999,'p90':1234}},scenario_ids=['story-a'])
    return dict(strategy_runtime=dict(football_analyst=dict(candidates=[raw],input_snapshot_sha256='original-snapshot',input_snapshot=dict(players=players))))


@pytest.mark.parametrize('fmt',['classic','showdown'])
def test_adapter_preserves_source_and_never_maps_conditional_scores_to_baseline(fmt):
    cfg=config(fmt);old=deepcopy(cfg);pool=extract_saved_pool(cfg,fmt);r=pool['candidates'][0]
    assert cfg==old and pool['status']=='original_candidate_pool'
    assert r['mean']==(21.5 if fmt=='showdown'else 45) and r['p90']==r['mean']*2
    assert r.get('objective_score')is None and r['source_scenario_scores']=={'story-a':{'mean':999,'p90':1234}}
    assert r['candidate_id']=='source-id' and r['source_candidate_ordinal']==1
    run=dict(optimizer_run_id='run',contest_format=fmt,constraint_config_json=cfg)
    scored=evaluate_run(run,[],[],{f'p{i}':10 for i in range(9)},{});pre=scored['candidates'][0]['pregame']
    assert pre['mean']==r['mean'] and pre['objective_score']is None and pre['selector_rank']is None


def test_variants_remain_separate_and_captain_changes_distinct_signature():
    cfg=config();raw=cfg['strategy_runtime']['football_analyst']['candidates'];raw.append({**deepcopy(raw[0]),'scenario_ids':['story-b']});third=deepcopy(raw[0]);third['roster'][0]['role']='FLEX';third['roster'][1]['role']='CPT';raw.append(third)
    p=extract_saved_pool(cfg,'showdown');assert p['count']==3 and p['unique_roster_count']==2 and p['scenario_variant_duplicates']==1
    assert candidate_signature(p['candidates'][0],'showdown')!=candidate_signature(p['candidates'][2],'showdown')
    assert p['candidates'][0]['source_candidate_sha256']!=p['candidates'][1]['source_candidate_sha256']


@pytest.mark.parametrize('change',['missing_id','duplicate','missing_cpt','bad_role','postgame'])
def test_malformed_saved_rosters_fail_closed(change):
    cfg=config();raw=cfg['strategy_runtime']['football_analyst']['candidates'][0]
    if change=='missing_id':raw['roster'][0].pop('player_master_id')
    if change=='duplicate':raw['roster'][1]['player_master_id']='p0'
    if change=='missing_cpt':raw['roster'][0]['role']='FLEX'
    if change=='bad_role':raw['roster'][1]['role']='unknown'
    if change=='postgame':raw['actual_points']=200
    assert extract_saved_pool(cfg,'showdown')['status']=='unavailable'


def test_missing_snapshot_moments_and_actuals_stay_unknown():
    cfg=config();cfg['strategy_runtime']['football_analyst']['input_snapshot']['players'][0].pop('projection')
    run=dict(optimizer_run_id='run',contest_format='showdown',constraint_config_json=cfg)
    r=evaluate_run(run,[],[],{'p0':10},{})
    assert r['status']=='incomplete_player_actuals' and r['candidates'][0]['pregame']['mean']is None
    assert r['best_generated_actual']is None and len(r['candidates'][0]['postgame']['missing_player_ids'])==5


def test_adapter_hash_and_timestamps_are_not_original_source_availability_proof():
    cfg=config();manifest=candidate_snapshot(cfg,'showdown');cfg['strategy_runtime']['candidate_pool_manifest']=manifest
    p=extract_saved_pool(cfg,'showdown');assert p['status']=='original_candidate_pool'
    run=dict(optimizer_run_id='run',constraint_config_json=cfg,data_cutoff_at=datetime(2026,10,17,tzinfo=UTC),optimizer_created_at=datetime(2026,10,17,tzinfo=UTC))
    t=chronological_validation(run,p);assert t['stored_timing_status']=='predecision' and t['status']=='unavailable' and t['retrospective_scoring_only']
    cfg['strategy_runtime']['football_analyst']['candidates'][0]['scenario_ids']=['changed']
    assert extract_saved_pool(cfg,'showdown')['reason']=='candidate_pool_hash_mismatch'


def test_ambiguous_corresponding_run_is_read_without_inventing_origin():
    cfg=config();sig=tuple(sorted((f'p{i}',i==0)for i in range(6)))
    report=dict(run_ids={},entries=[dict(entry_id='entry',contest_id='contest',entry_points=65,identity_complete=True,players=[dict(player_id=f'p{i}',roster_position='CPT'if i==0 else'FLEX')for i in range(6)],submission_evidence=dict(saved_lineup_matches=[dict(optimizer_run_id='run')]))])
    evidence=dict(optimizer_runs=[dict(optimizer_run_id='run',contest_format='showdown')],lineup_players=[dict(optimizer_run_id='run',lineup_id='lineup',player_id=f'p{i}',roster_position='CPT'if i==0 else'FLEX')for i in range(6)],observations=[dict(player_id=f'p{i}',actual_points=10,roster_position='FLEX',resolution_status='resolved')for i in range(6)])
    result=build_optimizer_effectiveness(report,evidence,run_loader=lambda _:dict(constraint_config_json=cfg))
    r=result['runs'][0];assert r['run_scope']=='entry_correspondence' and r['best_entered_actual']==65
    assert r['entry_correspondence'][0]['match_basis']=='ambiguous_roster_correspondence' and r['entry_correspondence'][0]['origin_proven']is False
