from copy import deepcopy
import pytest
from backend.app.product_services.opportunity_events import build_event_evidence
from backend.app.product_services.official_efficiency_features import build_official_efficiency
from backend.app.tests.product.test_defense_context_evidence import play, SOURCE, CUTOFF, IDS
from backend.app.tests.product.test_defense_context_extensions import rush, proof, NATIVE, CANONICAL
from backend.app.tests.product.test_official_workload_components import QN, QP


def build(rows, proofs=None, source=None):
    rows=deepcopy(rows)
    for r in rows:
        for k in ('passer_player_id','rusher_player_id'):
            if r.get(k)=='q':r[k]=QN
    parent=dict(event_evidence=build_event_evidence(rows,canonical_ids={QN:QP,NATIVE:CANONICAL,'w':IDS['w']},source_receipt=source or SOURCE,cutoff=CUTOFF))
    return build_official_efficiency(parent,before_period=202606,cutoff=CUTOFF,position_evidence=proofs if proofs is not None else [proof(source_player_id=QN,player_master_id=QP),proof(position='RB')])


def actor(v,native=QN):return next(r for r in v['actor_game_rows'] if r['source_player_id']==native)
def exact(v,mid,native=QN):return actor(v,native)['metrics'][mid]['exact_within_log_mean']


def test_official_physical_dropbacks_spikes_sacks_scrambles_once():
    rows=[play(1,epa=1),play(2,sack=1,epa=-1),play(3,qb_spike=1,receiver_player_id=None,epa=-.4),rush(4,rusher_player_id='q',passer_player_id='q',qb_scramble=1,epa=.5),rush(5,rusher_player_id='q',qb_kneel=1,epa=-1)]
    v=build(rows);q=actor(v)['metrics']
    assert q['G04-M06']['eligible_events']==4 and exact(v,'G04-M06')==pytest.approx(.1/4)
    assert exact(v,'G04-M07')==.5 and exact(v,'G04-M09')==.75
    assert exact(v,'G05-M06')==-.25


def test_official_carries_include_kneels_and_separate_yard_outcomes():
    rows=[rush(1,epa=.5,rushing_yards=12,first_down_rush=1,rush_touchdown=0),rush(2,qb_kneel=1,epa=-1,rushing_yards=-1,first_down_rush=0,rush_touchdown=0)]
    v=build(rows)
    assert [exact(v,m,NATIVE) for m in ('G07-M02','G07-M03','G07-M04','G07-M05','G07-M06')]==[-.25,.5,.5,.5,.5]


def test_lateral_team_net_not_credited_rusher_explosive():
    v=build([rush(1,yards_gained=65,rushing_yards=5,epa=1,first_down_rush=1,rush_touchdown=0)])
    assert exact(v,'G07-M04',NATIVE)==0


def test_missing_native_masks_exact_mean_keeps_known_attributed_sample():
    v=build([play(1,epa=1),play(2,passer_player_id=None,epa=-1)])
    m=actor(v)['metrics']['G04-M06']
    assert m['exact_within_log_mean'] is None and m['known_attributed_sample_mean']==1
    assert m['inherited_unattributed_eligible_events']==1 and 'all_eligible_mean' not in m
    assert v['full_team_measurements'][0]['metrics']['G04-M06']['eligible_events']==2


def test_missing_outcome_not_zero_or_completecase_and_other_outcomes_survive():
    v=build([rush(1,epa=None,rushing_yards=12,first_down_rush=0,rush_touchdown=0)])
    assert exact(v,'G07-M02',NATIVE) is None and exact(v,'G07-M04',NATIVE)==1
    assert actor(v,NATIVE)['metrics']['G07-M02']['unknown_outcome_events']==1


def test_explicit_exclusions_never_add_opportunities():
    v=build([play(1,no_play=1),rush(2,two_point_attempt=1)])
    assert all(m['eligible_events']==0 for t in v['full_team_measurements'] for m in t['metrics'].values())


def test_no_source_QB_proof_no_QB_catalog_claim():
    v=build([play(1,epa=1),rush(2,rushing_yards=5)],proofs=[])
    assert not any(m.startswith(('G04','G05')) for r in v['actor_game_rows'] for m in r['metrics'])


def test_official_union_does_not_require_redundant_qb_dropback_flag():
    v=build([play(1,qb_dropback=None,epa=1),play(2,sack=1,qb_dropback=None,epa=-1)])
    assert actor(v)['metrics']['G04-M06']['eligible_events']==2 and exact(v,'G04-M06')==0


def test_source_native_scramble_conflict_rejects():
    with pytest.raises(ValueError):build([rush(1,rusher_player_id=NATIVE,passer_player_id='q',qb_scramble=1)])


def test_source_clock_period_and_position_proofs_remain_guarded():
    with pytest.raises(ValueError):build([play(1)],proofs=[proof(source_player_id=QN,player_master_id=QP,available_at='2026-10-20T01:00:00Z')])
    with pytest.raises(ValueError):build([play(1,game_id='2026_06_BUF_MIA',week=6)])


def test_row_order_and_recapture_clocks_do_not_change_metrics():
    rows=[play(1,epa=1),rush(2,epa=-.5,rushing_yards=0)];a=build(rows);source=deepcopy(SOURCE)
    source['captured_at']=source['received_at']='2026-10-19T19:30:00Z'
    assert build(rows[::-1],source=source)['semantic_measurements_sha256']==a['semantic_measurements_sha256']


def test_offline_reader_future_missing_clocks_and_current_use_rejected():
    from types import SimpleNamespace
    from backend.app.product_services.official_efficiency_features import derive_retrospective_official_efficiency,require_official_efficiency_use
    snapshot=SimpleNamespace(slate_lock_at='2026-10-20T00:15:00Z')
    for actual in ('2099-01-01T00:00:00Z','2026-10-19T19:00:00Z'):
        with pytest.raises(ValueError):derive_retrospective_official_efficiency(dict(decision_cutoff_at='2026-10-19T19:53:00Z'),snapshot,actual_read_at=actual)
    with pytest.raises(ValueError):require_official_efficiency_use(dict(evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False),purpose='forecast')


def test_actual_parent_envelope_reader_source_provenance(monkeypatch):
    from types import SimpleNamespace
    from backend.app.product_services import opportunity_source_capture
    from backend.app.product_services.official_efficiency_features import derive_retrospective_official_efficiency
    raw=play(1,epa=1);raw['passer_player_id']=QN
    parent=dict(event_evidence=build_event_evidence([raw],canonical_ids={QN:QP,'w':IDS['w']},source_receipt=SOURCE,cutoff=CUTOFF))
    seen=[]
    def load(ref,snapshot,**kwargs):
        seen.append(kwargs);return parent
    monkeypatch.setattr(opportunity_source_capture,'load_event_artifact',load)
    ref=dict(decision_cutoff_at='2026-10-19T19:53:00Z',before_period=202606)
    result=derive_retrospective_official_efficiency(ref,SimpleNamespace(slate_lock_at='2026-10-20T00:15:00Z'),actual_read_at='2026-10-20T01:00:00Z',position_evidence=[proof(source_player_id=QN,player_master_id=QP)])
    assert result['provenance']['source']==parent['event_evidence']['source']
    assert result['provenance']['event_receipt_sha256']==parent['event_evidence']['sha256']
    assert result['pregame_serving_eligible'] is False and len(seen)==1
    assert seen[0]['cutoff'].isoformat()=='2026-10-19T19:53:00+00:00'
