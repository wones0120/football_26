from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import patch

import pandas as pd
import pytest
from sqlalchemy import create_engine

from backend.app.product_services.analyst_generation import generate_showdown, merge_showdown
from backend.app.product_services.analyst_packets import import_packet, load_packet, validate
from backend.app.product_services.gpp_optimizer import Player, run_gpp_pipeline
from backend.app.product_services.optimizer import OptimizerService
from scripts.build_analyst_shadow_fixtures import fixture


NOW=datetime(2099,9,1,12,tzinfo=timezone.utc)


def test_import_idempotent_and_revalidates_ledger(tmp_path):
    packet,_=fixture('SHOWDOWN')
    assert not validate(packet)
    first=import_packet(packet,directory=tmp_path)
    assert first==import_packet(packet,directory=tmp_path)
    assert load_packet(first['analyst_packet_sha256'],directory=tmp_path)==packet
    path=tmp_path/(first['analyst_packet_sha256']+'.json')
    path.write_text('{}')
    with pytest.raises(ValueError,match='hash mismatch'):load_packet(first['analyst_packet_sha256'],directory=tmp_path)
    with pytest.raises(ValueError,match='unavailable'):load_packet('a'*64,directory=tmp_path)


def test_normal_showdown_same_solver_and_constraints(tmp_path):
    packet,snapshot=fixture('SHOWDOWN'); before=deepcopy(snapshot)
    receipt=import_packet(packet,directory=tmp_path)
    pool=pd.DataFrame(snapshot['players']); service=OptimizerService.__new__(OptimizerService)
    kwargs=dict(contest_type='captain',score_col='p90',stack_params={'enabled':False},
                locked_player_ids=set(snapshot['policy']['locked_ids']),exposure_remaining={snapshot['policy']['zero_remaining_exposure_ids'][0]:0},include_control_comparison=False)
    with patch('backend.app.product_services.analyst_generation.load_packet',return_value=packet), patch('backend.app.product_services.analyst_generation.datetime') as clock:
        clock.now.return_value=NOW
        lineups,report=generate_showdown(service,pool,params={'analyst_packet_sha256':receipt['analyst_packet_sha256']},season=2099,week=1,slate='SYNTHETIC_SHOWDOWN',solve_kwargs=kwargs)
    assert report['eligible_generated_count']>0 and report['mode']=='ANALYST_CONSTRUCTION'
    for lineup in lineups:
        ids={p['player_id'] for p in lineup}
        assert len(ids)==6 and sum(p['salary'] for p in lineup)<=50000
        assert set(snapshot['policy']['locked_ids'])<=ids
        assert not set(snapshot['policy']['zero_remaining_exposure_ids']) & ids
        assert lineup[0]['analyst_thesis_ids']
    merged=merge_showdown(deepcopy(lineups),lineups)
    assert len(merged)==len(lineups)
    assert snapshot==before
    assert generate_showdown(service,pool,params={},season=2099,week=1,slate='SYNTHETIC_SHOWDOWN',solve_kwargs=kwargs)==([],None)


def test_classic_large_gpp_exact_caps_and_baseline_selection():
    packet,snapshot=fixture('CLASSIC')
    def players():
        return [Player(player_id=p['player_id'],name=p['name'],team=p['team'],opponent=p['opponent_team'],position=p['position'],salary=p['salary'],projection=p['projection'],ceiling=p['p90'],ownership=None) for p in snapshot['players']]
    kwargs=dict(season=2099,week=1,slate='SYNTHETIC_CLASSIC',num_lineups=2,engine=create_engine('sqlite://'),ownership_available=False,max_exposure=1.0,large_gpp=True,include_control_comparisons=False,minimum_uniqueness=2,max_lineups_per_primary_game=1,
                maximum_exposure_by_player={snapshot['players'][3]['player_id']:.5})
    original=run_gpp_pipeline(players=players(),**kwargs)
    with patch('backend.app.product_services.gpp_optimizer.datetime') as clock:
        clock.now.return_value=NOW
        result=run_gpp_pipeline(players=players(),analyst_packet=packet,**kwargs)
    assert result.status==original.status=='completed'
    assert [[p.player_id for p in l] for l in result.lineups]==[[p.player_id for p in l] for l in original.lineups]
    reports=[s['football_analyst'] for s in result.selection_trace]
    assert any(r['shadow'] for r in reports)
    assert all(sum(p.salary for p in l)<=50000 for l in result.lineups)
    for step,report in zip(result.selection_trace,reports):
        for candidate in report['shadow']:
            ids={p['player_master_id'] for p in candidate['roster']}
            assert all(step['exposure_remaining'][pid]>0 for pid in ids)
            assert candidate['baseline_objective']<=step['objective_score']+1e-7
    assert all(p.projection==next(row['projection'] for row in snapshot['players'] if row['player_id']==p.player_id) for lineup in result.lineups for p in lineup)


def test_invalid_packet_metadata_and_shapes_never_write(tmp_path):
    packet,_=fixture('SHOWDOWN'); packet.pop('packet_id')
    with pytest.raises(ValueError,match='packet_id'): import_packet(packet,directory=tmp_path)
    assert not list(tmp_path.iterdir())
    packet,_=fixture('SHOWDOWN'); packet['sources'][0]['available_at']=[]
    with pytest.raises(ValueError): import_packet(packet,directory=tmp_path)
    assert not list(tmp_path.iterdir())


def test_normal_showdown_preserves_opposing_dst_restriction():
    packet,snapshot=fixture('SHOWDOWN')
    pool=pd.DataFrame(snapshot['players']); service=OptimizerService.__new__(OptimizerService)
    kwargs=dict(contest_type='captain',score_col='p90',stack_params={'enabled':False},
                locked_player_ids=set(snapshot['policy']['locked_ids']),avoid_dst_opponents=True,include_control_comparison=False)
    with patch('backend.app.product_services.analyst_generation.load_packet',return_value=packet), patch('backend.app.product_services.analyst_generation.datetime') as clock:
        clock.now.return_value=NOW
        lineups,report=generate_showdown(service,pool,params={'analyst_packet_sha256':'a'*64},season=2099,week=1,slate='SYNTHETIC_SHOWDOWN',solve_kwargs=kwargs)
    for lineup in lineups:
        for defense in [p for p in lineup if p['position']=='DST']:
            assert not any(p['position']!='DST' and p['player_team']==defense['opponent_team'] for p in lineup)
    assert next(t for t in report['theses'] if t['thesis_id']=='rushing:0')['achieved']==0


def test_portfolio_merge_retains_baseline_scenario_variants_and_scores():
    baseline=[[
        dict(player_id='canonical-a',roster_position='CPT',showdown_scenario_id='baseline',solver_objective_value=12),
        dict(player_id='canonical-b',roster_position='FLEX')]]
    scenario=deepcopy(baseline[0]); scenario[0].update(showdown_scenario_id='team_a_decisive',solver_objective_value=14,
        conditioned_selector=19,showdown_candidate_source='existing_scenario')
    baseline.append(scenario)
    anchor=deepcopy(baseline[0]); anchor[0].update(analyst_thesis_ids=['opinion:0'],analyst_packet_sha256='a'*64)
    merged=merge_showdown(baseline,[anchor],preserve_variants=True)
    assert len(merged)==2
    assert [(l[0]['showdown_scenario_id'],l[0]['solver_objective_value']) for l in merged]==[('baseline',12),('team_a_decisive',14)]
    assert merged[1][0]['conditioned_selector']==19
    assert merged[1][0]['showdown_candidate_source']=='existing_scenario'
    assert all(l[0]['analyst_thesis_ids']==['opinion:0'] for l in merged)


def test_explicit_original_comparison_records_baseline_without_claiming_analyst_application():
    from backend.app.product_services.analyst_generation import annotate_original_construction_comparison
    r={'packet_sha256':'checked','generated_candidate_count':0,'selected_lineup_count':0}
    before=deepcopy(r)
    annotate_original_construction_comparison(r,params={'analyst_strategy':'CONSTRUCTION'},lineups=[[]],coverage={'captains':[{}]})
    assert r==before
    annotate_original_construction_comparison(r,params={'analyst_strategy':'CONSTRUCTION','analyst_optimization_intent':'EXPECTED_GAME'},lineups=[[],[]],coverage={'captains':[{},{}]})
    assert r['status']=='explicit_baseline_comparison' and not r['analyst_directives_applied']
    assert r['packet_sha256']=='checked' and r['baseline_selected_lineup_count']==2 and r['baseline_candidate_attempt_count']==2
    assert r['generated_candidate_count']==0 and r['selected_lineup_count']==0
