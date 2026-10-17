from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import patch

import pandas as pd
import pytest

from backend.app.product_services.analyst_packets import validate, import_packet, load_packet
from backend.app.product_services.analyst_scenarios import build_scenarios, run_merged, select_portfolio
from backend.app.product_services.captain_analyst import condition_captains, STATES, DIMENSIONS
from backend.app.product_services.optimizer import OptimizerService
from scripts.run_merged_analyst_fixture import scenario_fixture

NOW=datetime(2099,9,1,12,tzinfo=timezone.utc)


def captain_fixture(capability='competitive_scoring'):
    packet,snapshot=scenario_fixture('SHOWDOWN')
    packet['captain_analysis']=dict(contract_id='captain_analysis_v1',opponents=[],captains=[])
    qb=next(p for p in packet['players'] if p['team']=='BBB' and p['position']=='QB')
    evidence={d:dict(status='reviewed',summary='SYNTHETIC '+d+' evidence; not NFL research',source_ids=['synthetic'],player_master_ids=[qb['player_master_id']]) for d in DIMENSIONS}
    packet['captain_analysis']['opponents']=[dict(game_id='SYNTH_A_B',team='BBB',capability=capability,alternative_capabilities=[s for s in STATES if s!=capability][:1],
        evidence=evidence,supporting_evidence=['SYNTHETIC support'],contrary_evidence=['SYNTHETIC disconfirmation'],unknowns=['Uncalibrated magnitude'],hypothesis_ids=['synthetic_context'],expires_at='2099-09-02T12:00:00Z')]
    for row in snapshot['players']:
        row.update(canonical_role='expected_starter',role_source='synthetic_sourced_depth',is_starting_qb=row['position']=='QB')
        player=next(p for p in packet['players'] if p['player_master_id']==row['player_id'])
        for channel in ['targets','carries']:
            player['workload_evidence']['derived_proxies']['projected_'+channel]=dict(status='observed',value=5)
    return packet,snapshot


def run(packet,snapshot,**extra):
    kwargs=dict(contest_type='captain',score_col='p90',stack_params={'enabled':False},locked_player_ids=set(snapshot['policy']['locked_ids']),exposure_remaining={snapshot['policy']['zero_remaining_exposure_ids'][0]:0},include_control_comparison=False)
    kwargs.update(extra)
    with patch('backend.app.product_services.analyst_scenarios.datetime') as clock:
        clock.now.return_value=NOW
        return run_merged(OptimizerService.__new__(OptimizerService),pd.DataFrame(snapshot['players']),params=dict(max_exposure=1,analyst_candidates_per_thesis=2),packet=packet,fmt='SHOWDOWN',season=2099,week=1,slate='SYNTHETIC_CAPTAIN',requested=2,solve_kwargs=kwargs)


def test_sourced_opponent_branches_change_flex_without_forced_bringback():
    packet,snapshot=captain_fixture()
    captain=next(p for p in snapshot['players'] if p['team']=='AAA' and p['position']=='WR')
    packet['captain_analysis']['opponents'][0]['alternative_capabilities']=['drive_stall_runout']
    lineups,report=run(packet,snapshot,locked_captain_player_id=captain['player_id'])
    assert len(lineups)==2
    scenarios=report['scenario_definitions']
    assert len(scenarios)==2  # Duplicate volume-only source stories do not double-weight coverage.
    assert {s['opponent_capability_branch'] for s in scenarios}=={'competitive_scoring','drive_stall_runout'}
    assert all(s['captain_player_master_id']==captain['player_id'] for s in scenarios)
    by_state={s['opponent_capability_branch']:s for s in scenarios}
    opponent_qb=next(p for p in snapshot['players'] if p['team']=='BBB' and p['position']=='QB')['player_id']
    assert by_state['competitive_scoring']['moments'][opponent_qb]['mean']>by_state['drive_stall_runout']['moments'][opponent_qb]['mean']
    generated={state:[] for state in by_state}
    for c in report['candidates']:
        assert any(p['role']=='CPT' and p['player_master_id']==captain['player_id'] for p in c['roster'])
        for sid in c['scenario_ids']:
            generated[next(s['opponent_capability_branch'] for s in scenarios if s['scenario_id']==sid)].append(tuple(sorted(p['player_master_id'] for p in c['roster'] if p['role']=='FLEX')))
    assert set(generated['competitive_scoring'])!=set(generated['drive_stall_runout'])
    assert report['captain_analysis']['forced_bringback'] is False
    assert any(c['captain_conditioned_flex_comparison']['added'] for c in report['candidates'])
    for lineup in lineups:
        assert sum(p['salary'] for p in lineup)<=50000
        assert len(lineup)==6 and len({p['player_id'] for p in lineup})==6
        assert next(p for p in lineup if p['roster_position']=='CPT')['player_id']==captain['player_id']
        assert len({p['team'] for p in lineup})==2
        assert set(snapshot['policy']['locked_ids']) <= {p['player_id'] for p in lineup}
        assert not set(snapshot['policy']['zero_remaining_exposure_ids']) & {p['player_id'] for p in lineup}
        assert lineup[0]['analyst_captain_assessment']['opponent_capability']=='competitive_scoring'
        assert lineup[0]['analyst_captain_flex_comparison']['baseline_veto'] is False
    assert report['quality_screen']=='none'


def test_unknown_research_preserves_all_alternatives_and_current_shortlist():
    packet,snapshot=captain_fixture();packet['captain_analysis']['opponents']=[]
    base=build_scenarios(packet,snapshot['players'],fmt='SHOWDOWN',decision_at=NOW.isoformat())
    scenarios,report=condition_captains(packet,snapshot['players'],base,decision_at=NOW.isoformat())
    eligible={p['player_id'] for p in snapshot['players'] if p['showdown_captain_shortlisted']}
    assert {a['player_master_id'] for a in report['assessments']}==eligible
    assert report['shortlist_expanded'] is False
    assert all(a['opponent_capability']=='unknown' and a['mechanism_status']=='unknown' for a in report['assessments'])
    for a in report['assessments']:
        paths={s['opponent_capability_branch'] for s in scenarios if s['captain_player_master_id']==a['player_master_id']}
        assert paths==set(STATES) if a['position'] in {'QB','RB','WR','TE'} else not paths
    with pytest.raises(ValueError,match='outside.*shortlist'):
        condition_captains(packet,snapshot['players'],base,decision_at=NOW.isoformat(),locked_captain=snapshot['players'][1]['player_id'])


def test_trailing_passing_is_distinct_from_competitive_and_stalled():
    packet,snapshot=captain_fixture('trailing_productive_passing')
    packet['captain_analysis']['opponents'][0]['alternative_capabilities']=['competitive_scoring','drive_stall_runout']
    pid=next(p['player_id'] for p in snapshot['players'] if p['team']=='AAA' and p['position']=='QB')
    base=build_scenarios(packet,snapshot['players'],fmt='SHOWDOWN',decision_at=NOW.isoformat())
    scenarios,_=condition_captains(packet,snapshot['players'],base,decision_at=NOW.isoformat(),locked_captain=pid)
    by_state={s['opponent_capability_branch']:s for s in scenarios}
    qb=next(p['player_id'] for p in snapshot['players'] if p['team']=='BBB' and p['position']=='QB')
    rb=next(p['player_id'] for p in snapshot['players'] if p['team']=='BBB' and p['position']=='RB')
    assert by_state['trailing_productive_passing']['moments'][rb]['mean']<by_state['competitive_scoring']['moments'][rb]['mean']
    assert by_state['trailing_productive_passing']['moments'][qb]['mean']>by_state['drive_stall_runout']['moments'][qb]['mean']


def test_concentration_conserves_complete_measured_targets():
    packet,snapshot=captain_fixture()
    for player in packet['players']:
        if player['position'] in {'RB','WR','TE'}:
            player['workload_evidence']['historical']['targets_mean_3']=dict(status='observed',available=True,value=5)
    captain=next(p['player_id'] for p in snapshot['players'] if p['team']=='AAA' and p['position']=='WR')
    scenarios,_=condition_captains(packet,snapshot['players'],build_scenarios(packet,snapshot['players'],fmt='SHOWDOWN',decision_at=NOW.isoformat()),decision_at=NOW.isoformat(),locked_captain=captain)
    changes=[c for m in scenarios[0]['moments'].values() for c in m['changes'] if c['assumption']['kind']=='target_concentration']
    assert changes and sum(c['workload_before']*c['ratio'] for c in changes)==pytest.approx(sum(c['workload_before'] for c in changes))


@pytest.mark.parametrize('mutation',['source','clock','canonical','missing_dimension','probability','duplicate','alternative'])
def test_packet_validation_rejects_unproved_capability(mutation):
    packet,_=captain_fixture();a=packet['captain_analysis']['opponents'][0]
    if mutation=='source':a['evidence']['offense']['source_ids']=['missing']
    elif mutation=='clock':packet['sources'][0]['available_at']='2099-09-02T10:00:00Z'
    elif mutation=='canonical':a['evidence']['quarterback']['player_master_ids']=['unresolved']
    elif mutation=='missing_dimension':a['evidence'].pop('pace_drives')
    elif mutation=='probability':a['probability']=.9
    elif mutation=='duplicate':packet['captain_analysis']['opponents'].append(deepcopy(a))
    else:a['alternative_capabilities']=[]
    assert validate(packet)


def test_packet_import_lineage_and_expiry(tmp_path):
    packet,snapshot=captain_fixture();assert not validate(packet)
    receipt=import_packet(packet,directory=tmp_path)
    assert load_packet(receipt['analyst_packet_sha256'],directory=tmp_path)==packet
    assert import_packet(packet,directory=tmp_path)==receipt
    packet['captain_analysis']['opponents'][0]['expires_at']='2099-09-01T12:00:01Z'
    base=build_scenarios(packet,snapshot['players'],fmt='SHOWDOWN',decision_at=NOW.isoformat())
    with pytest.raises(ValueError,match='expired'):
        condition_captains(packet,snapshot['players'],base,decision_at='2099-09-01T13:00:00Z')


def test_other_captain_is_evaluated_under_actual_shared_football_moments():
    rows=[dict(player_id=pid,position='WR',projection=10,p90=15,salary=4000) for pid in ['a','b']]
    scenarios=[dict(scenario_id='a_story',captain_player_master_id='a',moments={'a':dict(mean=10,p90=15),'b':dict(mean=100,p90=150)})]
    candidates=[dict(roster=[dict(player_master_id=pid,role='CPT')],scenario_ids=[]) for pid in ['a','b']]
    selected,_=select_portfolio(candidates,scenarios,rows,requested=1,params={},fmt='SHOWDOWN')
    assert selected[0]['roster'][0]['player_master_id']=='b'
    assert candidates[1]['scores']['a_story']>candidates[0]['scores']['a_story']


def test_opponent_roster_minimum_does_not_force_opponent_qb_or_receiver():
    packet,snapshot=captain_fixture('drive_stall_runout')
    for player in snapshot['players']:
        player['projection']=25 if player['team']=='AAA' else 10 if player['position']=='DST' else 1
        player['p90']=player['projection']+2
        player['showdown_captain_p90']=player['p90']
        player['showdown_flex_mean']=player['projection']
    captain=next(p['player_id'] for p in snapshot['players'] if p['team']=='AAA' and p['position']=='WR')
    lineups,report=run(packet,snapshot,locked_captain_player_id=captain,locked_player_ids=set(),exposure_remaining={})
    assert any([p['position'] for p in lineup if p['team']=='BBB']==['DST'] for lineup in lineups)
    assert report['captain_analysis']['forced_bringback'] is False


def test_full_optimizer_saves_captain_assessments_and_flex_changes():
    from sqlalchemy import create_engine
    from backend.app.product_services.analyst_packets import packet_digest
    class InMemoryService(OptimizerService):
        def __init__(self,pool):
            super().__init__();self.engine=create_engine('sqlite://');self.pool=pool;self.saved=[]
        def _load_player_pool(self,*args,**kwargs):return self.pool.copy(deep=True)
        def _resolve_run_lineage(self,**kwargs):return 'synthetic-projection',None,datetime(2099,9,1,10,tzinfo=timezone.utc)
        def _persist_optimizer_run(self,job):self.saved.append(deepcopy(job.params));return True
    packet,snapshot=captain_fixture()
    rows=pd.DataFrame(snapshot['players']);rows['showdown_qb_eligible']=rows['position'].eq('QB');rows['is_starting_qb']=rows['position'].eq('QB');rows['official_availability_status']='available';rows['pregame_role_uncertain']=False
    captain=next(p['player_id'] for p in snapshot['players'] if p['team']=='AAA' and p['position']=='WR')
    service=InMemoryService(rows)
    with patch('backend.app.product_services.analyst_packets.load_packet',return_value=packet),patch('backend.app.product_services.analyst_scenarios.datetime') as clock:
        clock.now.return_value=NOW
        job=service.run_job(2099,1,'SYNTHETIC_SHOWDOWN','showdown_single_entry_gpp',dict(num_lineups=2,max_exposure=1,analyst_strategy='MERGED_SCENARIOS',analyst_packet_sha256=packet_digest(packet),analyst_candidates_per_thesis=2,locked_captain_player_id=captain),contest_format='showdown',objective='gpp',allow_incomplete_evidence=True)
    assert job.status=='completed' and len(job.results)==2
    saved=service.saved[-1]['strategy_runtime']['football_analyst']
    assert saved['captain_analysis']['eligible_captain_count']==1
    assert saved['packet_sha256']==packet_digest(packet)
    assert saved['candidates'][0]['captain_conditioned_flex_comparison']['captain_player_master_id']==captain
    assert all(lineup[0]['analyst_captain_assessment']['player_master_id']==captain for lineup in job.results)


def test_original_construction_is_unchanged_by_captain_block():
    from backend.app.product_services.analyst_generation import generate_showdown
    packet,snapshot=captain_fixture();legacy=deepcopy(packet);legacy.pop('captain_analysis')
    kwargs=dict(contest_type='captain',score_col='p90',stack_params={'enabled':False},locked_player_ids=set(snapshot['policy']['locked_ids']),include_control_comparison=False)
    rosters=[]
    for source in (legacy,packet):
        with patch('backend.app.product_services.analyst_generation.load_packet',return_value=source),patch('backend.app.product_services.analyst_generation.datetime') as clock:
            clock.now.return_value=NOW
            lineups,report=generate_showdown(OptimizerService.__new__(OptimizerService),pd.DataFrame(snapshot['players']),params={'analyst_packet_sha256':'a'*64},season=2099,week=1,slate='SYNTHETIC_SHOWDOWN',solve_kwargs=kwargs)
        assert report['mode']=='ANALYST_CONSTRUCTION'
        rosters.append([sorted((p['player_id'],p['roster_position']) for p in lineup) for lineup in lineups])
    assert rosters[0]==rosters[1]


def test_unsupported_captain_remains_assessed_without_invented_high_end_cause():
    packet,snapshot=captain_fixture()
    pid=next(p['player_id'] for p in snapshot['players'] if p['team']=='AAA' and p['position']=='WR')
    packet['captain_analysis']['captains']=[dict(player_master_id=pid,mechanism_status='unsupported',high_end_path='No supported high-end cause in this fixture',
        evidence={d:dict(status='unavailable',summary='Missing '+d+' evidence',source_ids=[]) for d in DIMENSIONS},
        supporting_evidence=['No affirmative assessment'],contrary_evidence=['Role path unsupported'],unknowns=['High-end likelihood unknown'],hypothesis_ids=['synthetic_context'],expires_at='2099-09-02T12:00:00Z')]
    assert not validate(packet)
    base=build_scenarios(packet,snapshot['players'],fmt='SHOWDOWN',decision_at=NOW.isoformat())
    scenarios,report=condition_captains(packet,snapshot['players'],base,decision_at=NOW.isoformat(),locked_captain=pid)
    assert report['assessments'][0]['mechanism_status']=='unsupported'
    assert all(s['captain_mechanism']=='unmodeled_scoring_path' for s in scenarios)
    assert not any(a['kind']=='target_concentration' for s in scenarios for a in s['assumptions'])


def test_captain_generation_is_deterministic_and_keeps_base_truth():
    packet,snapshot=captain_fixture();before=deepcopy(snapshot)
    pid=next(p['player_id'] for p in snapshot['players'] if p['team']=='AAA' and p['position']=='WR')
    first,report=run(packet,snapshot,locked_captain_player_id=pid)
    repeated,again=run(packet,snapshot,locked_captain_player_id=pid)
    assert [[(p['player_id'],p['roster_position']) for p in lineup] for lineup in first]==[[(p['player_id'],p['roster_position']) for p in lineup] for lineup in repeated]
    assert report['input_snapshot_sha256']==again['input_snapshot_sha256']
    assert snapshot==before
    for lineup in first:
        for player in lineup:
            base=next(p for p in before['players'] if p['player_id']==player['player_id'])
            assert player['projection']==pytest.approx(base['projection']*(1.5 if player['roster_position']=='CPT' else 1))


def test_legal_zero_opportunity_and_secondary_roles_do_not_create_automatic_captain_story():
    packet,snapshot=captain_fixture();row=next(r for r in snapshot['players'] if r['position']=='RB');row['showdown_captain_shortlisted']=True;pid=row['player_id']
    player=next(p for p in packet['players'] if p['player_master_id']==pid)
    for group,key in [('historical','carries_mean_3'),('explicit_pregame','pregame_expected_carries'),('derived_proxies','projected_carries')]:
        player['workload_evidence'][group][key]=dict(status='observed',available=True,value=0)
    base=build_scenarios(packet,snapshot['players'],fmt='SHOWDOWN',decision_at=NOW.isoformat())
    scenarios,report=condition_captains(packet,snapshot['players'],base,decision_at=NOW.isoformat())
    a=next(a for a in report['assessments'] if a['player_master_id']==pid)
    assert a['generation_status']=='suppressed_unsupported_automatic_story' and not a['scenario_ids']
    assert not any(s['captain_player_master_id']==pid for s in scenarios)
    # A deliberate lock remains a transparent what-if, never a fabricated source opinion.
    locked,lr=condition_captains(packet,snapshot['players'],base,decision_at=NOW.isoformat(),locked_captain=pid)
    assert locked and lr['assessments'][0]['story_authority']=='explicit_locked_captain_what_if'
    row['canonical_role']='expected_backup';player['workload_evidence']['historical']['carries_mean_3']['value']=5
    _,report=condition_captains(packet,snapshot['players'],base,decision_at=NOW.isoformat())
    assert not next(a for a in report['assessments'] if a['player_master_id']==pid)['scenario_ids']


def test_equivalent_captain_labeled_worlds_do_not_multiply_outcome_votes():
    rows=[dict(player_id=pid,position='WR',projection=10,p90=15,salary=4000) for pid in ['a','b']]
    moments={'a':dict(mean=10,p90=15),'b':dict(mean=100,p90=150)}
    scenarios=[dict(scenario_id=pid,captain_player_master_id=pid,moments=deepcopy(moments)) for pid in ['a','b']]
    candidates=[dict(roster=[dict(player_master_id=pid,role='CPT')],scenario_ids=[]) for pid in ['a','b']]
    selected,report=select_portfolio(candidates,scenarios,rows,requested=1,params={},fmt='SHOWDOWN')
    assert report['unique_shared_outcome_count']==1 and selected[0]['roster'][0]['player_master_id']=='b'


def test_current_prepared_positive_proxy_can_support_primary_when_dated_packet_lacks_measurements():
    packet,snapshot=captain_fixture();row=next(r for r in snapshot['players'] if r['position']=='TE');row.update(showdown_captain_shortlisted=True,projected_targets=4.5);pid=row['player_id'];player=next(p for p in packet['players'] if p['player_master_id']==pid)
    for group,key in [('historical','targets_mean_3'),('explicit_pregame','pregame_expected_targets'),('derived_proxies','projected_targets')]:player['workload_evidence'][group][key]=dict(status='unavailable',available=False,value=None)
    base=build_scenarios(packet,snapshot['players'],fmt='SHOWDOWN',decision_at=NOW.isoformat());_,report=condition_captains(packet,snapshot['players'],base,decision_at=NOW.isoformat())
    a=next(a for a in report['assessments'] if a['player_master_id']==pid);assert a['scenario_ids'] and a['opportunity_evidence_source']=='fresh_prepared_projection_proxy:targets' and a['measured_channel_opportunity']==4.5
