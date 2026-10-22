from copy import deepcopy
import pytest
from backend.app.product_services.official_efficiency_catalog import build_official_efficiency_catalog
from backend.app.product_services.opportunity_events import build_event_evidence
from backend.app.tests.product.test_defense_context_evidence import play,SOURCE,CUTOFF,IDS
from backend.app.tests.product.test_defense_context_extensions import rush,proof,NATIVE,CANONICAL
from backend.app.tests.product.test_official_workload_components import QN,QP


def build(rows,source=None):
    rows=deepcopy(rows)
    for r in rows:
        for k in ('passer_player_id','rusher_player_id'):
            if r.get(k)=='q':r[k]=QN
    parent=dict(event_evidence=build_event_evidence(rows,canonical_ids={QN:QP,NATIVE:CANONICAL,'w':IDS['w']},source_receipt=source or SOURCE,cutoff=CUTOFF))
    return build_official_efficiency_catalog(parent,before_period=202606,cutoff=CUTOFF,position_evidence=[proof(source_player_id=QN,player_master_id=QP),proof(position='RB')])


def actor(v,native=QN):return next(r for r in v['actor_game_rows'] if r['source_player_id']==native)


def test_exact_sack_rate_not_avoidance_preserved():
    r=actor(build([play(1,sack=1,epa=-1),play(2,epa=1),play(3,epa=1)]))
    assert r['metrics']['G04-M09']['value']==1/3
    assert r['preserved_measured_variants']['sack_avoidance_per_official_dropback']['exact_within_log_mean']==pytest.approx(2/3)


def test_QB_success_not_epa_mean_and_signed_total_not_mean():
    r=actor(build([rush(1,rusher_player_id='q',epa=1,rushing_yards=3),rush(2,rusher_player_id='q',epa=-3,rushing_yards=-2)]))
    assert r['metrics']['G05-M06']['value']==.5
    assert r['preserved_measured_variants']['QB_epa_per_official_carry']['exact_within_log_mean']==-1
    assert r['metrics']['G07-M02']['value']==-2
    assert 'exact_within_log_mean' not in r['metrics']['G07-M02']
    assert r['preserved_measured_variants']['epa_per_official_carry']['exact_within_log_mean']==-1


def test_only_third_fourth_down_conversion_opportunities():
    rows=[rush(1,down=1,first_down_rush=1,rush_touchdown=0),rush(2,down=2,first_down_rush=1,rush_touchdown=0),rush(3,down=3,first_down_rush=1,rush_touchdown=0),rush(4,down=4,first_down_rush=0,rush_touchdown=0)]
    r=actor(build(rows),NATIVE)
    assert r['metrics']['G07-M06']['eligible_events']==2 and r['metrics']['G07-M06']['value']==.5
    assert r['preserved_measured_variants']['first_down_or_TD_fraction_all_official_carries']['eligible_events']==4


def test_TD_proves_conversion_and_unknown_outcome_not_zero():
    r=actor(build([rush(1,down=3,first_down_rush=None,rush_touchdown=1)]),NATIVE)
    assert r['metrics']['G07-M06']['value']==1
    r=actor(build([rush(1,down=3,first_down_rush=None,rush_touchdown=0)]),NATIVE)
    assert r['metrics']['G07-M06']['value'] is None


def test_missing_native_inside_conversion_masks_outside_does_not():
    rows=[rush(1,down=3,first_down_rush=1,rush_touchdown=0),rush(2,rusher_player_id=None,down=1)]
    assert actor(build(rows),NATIVE)['metrics']['G07-M06']['value']==1
    rows[1]['down']=4
    assert actor(build(rows),NATIVE)['metrics']['G07-M06']['value'] is None


def test_unknown_down_is_not_filtered_away():
    rows=[rush(1,down=3,first_down_rush=1,rush_touchdown=0),rush(2,down=None)]
    assert actor(build(rows),NATIVE)['metrics']['G07-M06']['value'] is None


def test_empty_official_rush_total_zero_but_rate_undefined():
    r=actor(build([play(1,epa=1)]))
    assert r['metrics']['G07-M02']['value']==0 and r['metrics']['G05-M06']['value'] is None
    assert r['metrics']['G07-M06']['value'] is None


def test_unattributed_or_unknown_epa_cannot_certify_total():
    r=actor(build([rush(1,epa=1),rush(2,rusher_player_id=None,epa=2)]),NATIVE)
    assert r['metrics']['G07-M02']['value'] is None
    r=actor(build([rush(1,epa=None)]),NATIVE)
    assert r['metrics']['G07-M02']['value'] is None


def test_recapture_order_stability_and_real_conversion_change():
    rows=[rush(1,down=3,first_down_rush=1,rush_touchdown=0),rush(2,down=4,first_down_rush=0,rush_touchdown=0)]
    a=build(rows)['semantic_measurements_sha256'];s=deepcopy(SOURCE);s['captured_at']=s['received_at']='2026-10-19T19:30:00Z'
    assert build(rows[::-1],source=s)['semantic_measurements_sha256']==a
    rows[1]['first_down_rush']=1
    assert build(rows)['semantic_measurements_sha256']!=a


def test_actual_parent_reader_shape_and_nonserving_outputs(monkeypatch):
    from types import SimpleNamespace
    from backend.app.product_services import opportunity_source_capture
    from backend.app.product_services.official_efficiency_catalog import derive_retrospective_efficiency_catalog
    raw=play(1,epa=1);raw['passer_player_id']=QN
    parent=dict(event_evidence=build_event_evidence([raw],canonical_ids={QN:QP,'w':IDS['w']},source_receipt=SOURCE,cutoff=CUTOFF))
    calls=[]
    def loader(ref,snapshot,**kwargs):calls.append(kwargs);return parent
    monkeypatch.setattr(opportunity_source_capture,'load_event_artifact',loader)
    ref=dict(before_period=202606,decision_cutoff_at='2026-10-19T19:53:00Z')
    result=derive_retrospective_efficiency_catalog(ref,SimpleNamespace(slate_lock_at='2026-10-20T00:15:00Z'),actual_read_at='2026-10-20T01:00:00Z',position_evidence=[proof(source_player_id=QN,player_master_id=QP)])
    assert result['provenance']['source']==parent['event_evidence']['source']
    assert result['pregame_serving_eligible'] is False
    assert len(result['full_team_source_measurements'])==len(result['full_team_conversion_measurements'])==1
    assert calls[0]['cutoff'].isoformat()=='2026-10-19T19:53:00+00:00'
    with pytest.raises(ValueError):derive_retrospective_efficiency_catalog(ref,SimpleNamespace(slate_lock_at=None),actual_read_at='2026-10-20T01:00:00Z')


def test_preserved_team_counters_have_explicit_original_definition_map():
    v=build([play(1,sack=1,epa=-1),play(2,epa=1),play(3,epa=1)])
    assert actor(v)['metrics']['G04-M09']['value']==1/3
    team=v['full_team_source_measurements'][0]['metrics']['G04-M09']
    assert team['observed_outcome_sum']==2
    assert 'one_minus_source_sack' in v['full_team_source_measurement_definitions']['G04-M09'][1]
    assert 'Preserved v1' in v['full_team_source_measurement_scope']
