from copy import deepcopy
import pytest
from backend.app.product_services.opportunity_events import build_event_evidence
from backend.app.product_services.player_opportunity_components import build_player_opportunity_components
from backend.app.tests.product.test_defense_context_evidence import play,SOURCE,CUTOFF,IDS
from backend.app.tests.product.test_defense_context_extensions import rush,proof,NATIVE,CANONICAL


def build(rows,ids=None,proofs=(),source=None):
    parent=dict(event_evidence=build_event_evidence(rows,canonical_ids=ids or IDS,source_receipt=source or SOURCE,cutoff=CUTOFF))
    return build_player_opportunity_components(parent,before_period=202606,cutoff=CUTOFF,position_evidence=proofs)


def actor(result,native):return next(r for r in result['actor_game_rows'] if r['source_player_id']==native)


def count(row,key):return row['metrics'][key]['observed_outcome_sum']


def test_pass_attempt_spike_sack_scramble_are_distinct_physical_events():
    result=build([play(1,complete_pass=1),play(2,qb_spike=1,receiver_player_id=None),
        play(3,sack=1,pass_attempt=1),rush(4,qb_dropback=1,qb_scramble=1,passer_player_id='q')])
    q=actor(result,'q')
    assert count(q,'official_pass_attempts')==2
    assert count(q,'spikes')==1
    assert count(q,'nonspike_dropbacks')==3
    assert count(q,'sacks')==1
    assert q['metrics']['completions']['unknown_outcome_events']==1
    assert count(q,'scrambles_per_dropback')==1
    assert count(actor(result,NATIVE),'scrambles')==1


def test_rush_splits_use_preplay_conditions_kneels_separate_and_unknown_not_zero():
    result=build([rush(1,qtr=2,half_seconds_remaining=100,down=1,score_differential=7,yardline_100=4),
        rush(2,qtr=4,half_seconds_remaining=121,down=3,score_differential=-1,yardline_100=21),
        rush(3,qb_kneel=1),rush(4,qtr=None,down=None,half_seconds_remaining=None,score_differential=None,yardline_100=None)])
    r=actor(result,NATIVE)
    assert count(r,'official_rush_attempts')==4 and count(r,'nonkneel_rush_attempts')==3
    assert count(r,'kneels')==1 and count(r,'two_minute_carries')==1
    assert count(r,'early_down_carries')==1 and count(r,'third_down_carries')==1
    assert count(r,'leading_carries')==1 and count(r,'trailing_carries')==1
    assert count(r,'inside5_carries')==1
    assert r['metrics']['inside5_carries']['unknown_eligibility_events']==1
    assert r['metrics']['first_half_carries']['all_eligible_mean'] is None


def test_air_yards_signed_and_full_team_target_denominator_preserved_for_unmapped_receiver():
    result=build([play(1,air_yards=-3),play(2,receiver_player_id='other',air_yards=9)])
    receiver=actor(result,'w')
    assert count(receiver,'targets')==1 and count(receiver,'air_yards')==-3
    assert receiver['shares']['target_share']==.5
    assert receiver['shares']['signed_air_yard_share']==-.5
    assert receiver['shares']['average_target_depth']==-3
    assert result['team_denominators'][0]['official']['counts']['targets']==2
    assert result['identity_review_requests'][0]['source_player_id']=='other'


def test_unknown_target_or_air_yard_exposure_cannot_supply_zero_or_exact_share():
    result=build([play(1,air_yards=None),play(2,receiver_player_id=None,air_yards=10)])
    r=actor(result,'w')
    assert r['metrics']['air_yards']['observed_outcome_sum'] is None
    assert r['shares']['target_share'] is None and r['shares']['average_target_depth'] is None
    assert r['inherited_team_unknown_eligibility']['targets']==1
    assert result['unattributed_events'][-1]['role']=='receiver'


def test_native_scoped_position_only_no_name_or_rush_flag_infers_qb():
    absent=build([rush()],ids={NATIVE:CANONICAL})
    assert actor(absent,NATIVE)['position'] is None
    known=build([rush()],ids={NATIVE:CANONICAL},proofs=[proof()])
    assert actor(known,NATIVE)['position']=='QB'
    assert actor(known,NATIVE)['player_master_id']==CANONICAL
    with pytest.raises(ValueError,match='contradicts'):
        build([rush()],ids={NATIVE:CANONICAL},proofs=[proof(player_master_id='00000000-0000-0000-0000-000000000099')])


def test_excluded_no_play_and_two_point_never_create_official_opportunities():
    result=build([play(1,no_play=1),rush(2,two_point_attempt=1)])
    assert result['actor_game_rows']==[]
    assert result['team_denominators'][0]['measured']['nonkneel_rush_attempts']['known_outcome_events']==0


def test_invalid_binary_measurement_is_unknown_not_two_completions():
    result=build([play(1,complete_pass=2)])
    value=actor(result,'q')['metrics']['completions']
    assert value['known_outcome_events']==0 and value['unknown_outcome_events']==1


def test_order_recapture_stable_actual_air_yards_and_position_change_semantics():
    rows=[play(1,air_yards=1),rush(2)]
    first=build(rows,proofs=[proof(player_master_id="00000000-0000-0000-0000-000000000003")])
    source=deepcopy(SOURCE);source['captured_at']=source['received_at']='2026-10-19T19:30:00Z'
    later=build(rows[::-1],proofs=[proof(player_master_id='00000000-0000-0000-0000-000000000003',source_id='new',available_at='2026-10-19T19:30:00Z')],source=source)
    assert first['semantic_measurements_sha256']==later['semantic_measurements_sha256']
    assert first['semantic_measurements_sha256']!=build(rows,proofs=[proof(player_master_id='00000000-0000-0000-0000-000000000003',position='RB')])['semantic_measurements_sha256']
    rows[0]['air_yards']=2
    assert first['semantic_measurements_sha256']!=build(rows,proofs=[proof(player_master_id="00000000-0000-0000-0000-000000000003")])['semantic_measurements_sha256']



def test_parent_checksum_future_period_and_future_position_rejected():
    parent=dict(event_evidence=build_event_evidence([play()],canonical_ids=IDS,source_receipt=SOURCE,cutoff=CUTOFF))
    parent['event_evidence']['events'][0]['raw_flags']['air_yards']=999
    with pytest.raises(ValueError,match='checksum'):
        build_player_opportunity_components(parent,before_period=202606,cutoff=CUTOFF)
    with pytest.raises(ValueError):build([play(game_id='2026_06_BUF_MIA',week=6)])
    with pytest.raises(ValueError):build([rush()],proofs=[proof(available_at='2026-10-20T01:00:00Z')])


def test_canonical_actor_cannot_be_proof_attached_to_two_native_keys():
    with pytest.raises(ValueError,match='Canonical actor'):
        build([rush()],ids={NATIVE:CANONICAL},proofs=[proof(source_player_id='00-0000002')])


def test_source_quality_changes_invalidate_semantics_and_unknown_actor_not_exact_zero():
    rows=[play(1,air_yards=1),play(2,pass_attempt=None,rush_attempt=None,receiver_player_id=None)]
    original=build(rows)
    assert actor(original,'w')['metrics']['targets']['exact_within_log_sum'] is None
    changed=deepcopy(SOURCE);changed['full_game_coverage']='independently_verified'
    assert original['semantic_measurements_sha256']!=build(rows,source=changed)['semantic_measurements_sha256']


def test_no_events_does_not_invent_participating_actor_or_zero_workload():
    result=build([])
    assert result['actor_game_rows']==[] and result['team_denominators']==[]
    assert result['forecast'] is None



def test_known_attributed_air_yards_do_not_prove_exact_depth_with_unattributed_target():
    result=build([play(1,air_yards=10),play(2,receiver_player_id=None,air_yards=12)])
    receiver=actor(result,'w')
    assert receiver['metrics']['targets']['exact_within_log_sum'] is None
    assert receiver['inherited_team_unknown_eligibility']['targets']==1
    assert receiver['shares']['average_target_depth'] is None
    assert receiver['shares']['known_attributed_sample_depth']==10



def test_missing_native_rusher_or_passer_prevents_exact_actor_counts_and_carry_share():
    result=build([rush(1),rush(2,rusher_player_id=None),play(3),play(4,passer_player_id=None,sack=1)])
    r=actor(result,NATIVE);q=actor(result,'q')
    assert count(r,'nonkneel_rush_attempts')==1
    assert r['metrics']['nonkneel_rush_attempts']['exact_within_log_sum'] is None
    assert r['shares']['nonkneel_carry_share'] is None
    assert r['unknown_native_attribution_exposures']['rusher']==1
    assert q['metrics']['nonspike_dropbacks']['exact_within_log_sum'] is None
    assert q['unknown_native_attribution_exposures']['passer']==1


def test_separate_postlock_reader_preserves_real_clocks_and_rejects_current_use(tmp_path):
    from datetime import timedelta
    from backend.app.tests.product.test_opportunity_source_capture import capture,derive,NOW,LOCK
    from backend.app.tests.test_source_capture import _session
    from backend.app.services.source_capture import SourceCaptureService
    from backend.app.product_services.opportunity_source_capture import freeze_event_artifact,load_event_artifact
    from backend.app.product_services.player_opportunity_components import derive_retrospective_player_components,require_component_use,RETROSPECTIVE_USE
    session=_session()
    try:
        service=SourceCaptureService(session,snapshot_root=tmp_path/'raw',clock=lambda:NOW)
        snapshot=capture(service).snapshot;ref=freeze_event_artifact(derive(snapshot),snapshot,directory=tmp_path/'parents')
        before=(tmp_path/'parents'/ (ref['artifact_sha256']+'.json.gz')).read_bytes()
        actual=LOCK+timedelta(minutes=1)
        with pytest.raises(ValueError,match='precede lock'):
            load_event_artifact(ref,snapshot,before_period=202603,cutoff=actual,directory=tmp_path/'parents')
        value=derive_retrospective_player_components(ref,snapshot,actual_read_at=actual,directory=tmp_path/'parents')
        assert value['evidence_use']==RETROSPECTIVE_USE and value['pregame_serving_eligible'] is False
        clocks=value['provenance']['retrospective_read']
        assert clocks['actual_read_at']==actual.isoformat()
        assert clocks['original_evidence_boundary_at']==ref['decision_cutoff_at']
        assert 'decision_cutoff_at' not in value['provenance']
        assert require_component_use(value,purpose='offline_descriptive') is value
        for purpose in ('register_pregame','current_forecast','current_scenario'):
            with pytest.raises(ValueError,match='cannot be registered'):require_component_use(value,purpose=purpose)
        assert before==(tmp_path/'parents'/ (ref['artifact_sha256']+'.json.gz')).read_bytes()
        with pytest.raises(ValueError,match='postlock'):
            derive_retrospective_player_components(ref,snapshot,actual_read_at=NOW,directory=tmp_path/'parents')
    finally:session.close()
