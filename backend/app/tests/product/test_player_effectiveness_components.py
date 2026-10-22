from copy import deepcopy
import pytest
from backend.app.product_services.opportunity_events import build_event_evidence
from backend.app.product_services.player_effectiveness_components import build_player_effectiveness_components,DEFINITIONS
from backend.app.tests.product.test_defense_context_evidence import play,SOURCE,CUTOFF,IDS
from backend.app.tests.product.test_defense_context_extensions import rush,proof,NATIVE,CANONICAL


def build(rows,ids=None,proofs=(),source=None):
 parent=dict(event_evidence=build_event_evidence(rows,canonical_ids=ids or IDS,source_receipt=source or SOURCE,cutoff=CUTOFF))
 return build_player_effectiveness_components(parent,before_period=202606,cutoff=CUTOFF,position_evidence=proofs)


def actor(block,native):return next(r for r in block['actor_game_rows'] if r['source_player_id']==native)

def mean(row,key):return row['metrics'][key]['known_attributed_sample_mean']


def test_official_spikes_vs_dropback_sacks_scrambles_and_independent_denominators():
 rows=[play(1,complete_pass=1,passing_yards=10,receiving_yards=10,air_yards=8,cpoe=15,interception=0,pass_touchdown=0,epa=1),
       play(2,complete_pass=0,passing_yards=None,receiving_yards=None,air_yards=20,cpoe=-10,interception=1,pass_touchdown=0,epa=-1),
       play(3,complete_pass=1,passing_yards=30,receiving_yards=30,air_yards=20,cpoe=5,interception=0,pass_touchdown=1,epa=.5),
       play(4,sack=1,epa=-2),rush(5,passer_player_id='q',qb_dropback=1,qb_scramble=1,epa=.8),
       play(6,qb_spike=1,receiver_player_id=None,complete_pass=0,passing_yards=0,interception=0,pass_touchdown=0)]
 result=build(rows);q=actor(result,'q')
 assert len(DEFINITIONS)==24
 assert mean(q,'G04-M01')==.5 and mean(q,'G04-M03')==10
 assert mean(q,'G04-M05')==20 and mean(q,'G04-M02')==pytest.approx(10/3)
 assert q['metrics']['G04-M06']['known_outcome_events']==5
 assert mean(q,'G04-M06')==pytest.approx(-.7/5)
 assert mean(q,'G04-M07')==.6 and mean(q,'G04-M09')==.2
 assert mean(q,'G04-M08')==.25 and mean(q,'G04-M10')==.25


def test_incomplete_proves_zero_yards_but_not_zero_completion_or_yac_denominators():
 result=build([play(1,complete_pass=1,passing_yards=20,receiving_yards=20,yards_after_catch=7),
               play(2,complete_pass=0,passing_yards=None,receiving_yards=None,yards_after_catch=None)])
 q=actor(result,'q');w=actor(result,'w')
 assert mean(q,'G04-M03')==10 and mean(q,'G04-M05')==20
 assert mean(w,'G09-M01')==.5 and mean(w,'G09-M03')==10
 assert mean(w,'G09-M04')==20 and mean(w,'G09-M08')==7
 assert w['metrics']['G09-M08']['eligible_events']==1
 assert mean(w,'G09-M10')==1


def test_rushing_signed_yards_play_net_explosive_stuff_and_td_firstdown_non_kneel():
 result=build([rush(1,rushing_yards=7,yards_gained=10,epa=.5,first_down_rush=0,rush_touchdown=1),
               rush(2,rushing_yards=-2,yards_gained=-2,epa=-1,first_down_rush=0,rush_touchdown=0),
               rush(3,qb_kneel=1,rushing_yards=-1,yards_gained=-1,epa=-1)])
 r=actor(result,NATIVE)
 assert mean(r,'G07-M01')==2.5 and mean(r,'G07-M02')==-.25
 assert mean(r,'G07-M03')==.5 and mean(r,'G07-M04')==.5 and mean(r,'G07-M05')==.5
 assert mean(r,'G07-M06')==.5 and r['metrics']['G07-M01']['eligible_events']==2


def test_unknown_yards_flags_or_epa_are_not_zero_or_yards_gained_substitutes():
 result=build([rush(1,rushing_yards=None,yards_gained=9,epa=None,first_down_rush=None,rush_touchdown=0)])
 r=actor(result,NATIVE)
 assert mean(r,'G07-M01') is None and mean(r,'G07-M02') is None and mean(r,'G07-M03') is None
 assert r['metrics']['G07-M01']['unknown_outcome_events']==1
 assert mean(r,'G07-M06') is None


def test_unknown_native_receiver_or_rusher_masks_exact_rates_not_known_sample():
 result=build([play(1,complete_pass=1,passing_yards=10,receiving_yards=10),play(2,receiver_player_id=None,complete_pass=0),
               rush(3,rushing_yards=5),rush(4,rusher_player_id=None,rushing_yards=1)])
 w=actor(result,'w');r=actor(result,NATIVE)
 assert mean(w,'G09-M03')==10 and w['metrics']['G09-M03']['exact_within_log_mean'] is None
 assert mean(r,'G07-M01')==5 and r['metrics']['G07-M01']['exact_within_log_mean'] is None
 assert result['unattributed_events']


def test_signed_air_yards_yac_and_vendor_percentage_points_not_probability():
 result=build([play(1,complete_pass=1,passing_yards=-2,receiving_yards=-2,air_yards=-3,yards_after_catch=-1,cpoe=25)])
 q=actor(result,'q');w=actor(result,'w')
 assert mean(q,'G04-M04')==-3 and mean(w,'G09-M08')==-1
 assert mean(w,'G09-M02')==25
 assert result['definitions']['G09-M02']['catalog_status'].startswith('partial_')
 assert result['source_gaps']['G09-M05'].startswith('routes unavailable')


@pytest.mark.parametrize('field',['passing_yards','receiving_yards'])
def test_incomplete_nonzero_official_yards_conflict_rejected(field):
 with pytest.raises(ValueError,match='Incomplete pass conflicts'):
  build([play(1,complete_pass=0,**{field:1})])


def test_bad_cpoe_and_future_period_or_position_proof_rejected():
 with pytest.raises(ValueError,match='CPOE outside'):build([play(1,cpoe=100.1)])
 with pytest.raises(ValueError):build([play(1,game_id='2026_06_BUF_MIA',week=6)])
 with pytest.raises(ValueError):build([rush()],proofs=[proof(available_at='2026-10-20T01:00:00Z')])


def test_native_identity_position_scope_and_unresolved_queue_preserved():
 absent=build([rush(1,rushing_yards=5)])
 assert actor(absent,NATIVE)['position'] is None and absent['identity_review_requests']
 known=build([rush(1,rushing_yards=5)],ids={NATIVE:CANONICAL},proofs=[proof()])
 assert actor(known,NATIVE)['position']=='QB'
 assert actor(known,NATIVE)['player_master_id']==CANONICAL
 with pytest.raises(ValueError):build([rush()],ids={NATIVE:CANONICAL},proofs=[proof(player_master_id='00000000-0000-0000-0000-000000000099')])


def test_source_order_and_recapture_stable_material_yards_quality_change_significant():
 rows=[play(1,complete_pass=1,passing_yards=10,receiving_yards=10),rush(2,rushing_yards=5)]
 first=build(rows);source=deepcopy(SOURCE);source['captured_at']=source['received_at']='2026-10-19T19:30:00Z'
 assert first['semantic_measurements_sha256']==build(rows[::-1],source=source)['semantic_measurements_sha256']
 rows[0]['passing_yards']=11
 assert first['semantic_measurements_sha256']!=build(rows)['semantic_measurements_sha256']
 source['full_game_coverage']='independently_verified'
 assert build(rows)['semantic_measurements_sha256']!=build(rows,source=source)['semantic_measurements_sha256']


def test_excluded_and_empty_sources_do_not_manufacture_actor_efficiency():
 assert build([])['actor_game_rows']==[]
 assert build([play(1,no_play=1),rush(2,two_point_attempt=1)])['actor_game_rows']==[]


def test_qb_catalog_scope_requires_typed_scoped_position_proof_not_passing_identity():
 rows=[play(1,passer_player_id=NATIVE,complete_pass=1,passing_yards=8)]
 unknown=build(rows,ids={NATIVE:CANONICAL})
 assert actor(unknown,NATIVE)['metrics']['G04-M01']['catalog_scope_status'].startswith('unknown_QB')
 known=build(rows,ids={NATIVE:CANONICAL},proofs=[proof()])
 assert actor(known,NATIVE)['metrics']['G04-M01']['catalog_scope_status']=='source_proven_QB'
 nonqb=build(rows,ids={NATIVE:CANONICAL},proofs=[proof(position='WR')])
 assert actor(nonqb,NATIVE)['metrics']['G04-M01']['catalog_scope_status'].startswith('non_QB')


def test_retrospective_frozen_parent_keeps_actual_clocks_and_cannot_be_current(tmp_path):
 from datetime import timedelta
 from backend.app.tests.product.test_opportunity_source_capture import capture,derive,NOW,LOCK
 from backend.app.tests.test_source_capture import _session
 from backend.app.services.source_capture import SourceCaptureService
 from backend.app.product_services.opportunity_source_capture import freeze_event_artifact
 from backend.app.product_services.player_opportunity_components import require_component_use
 from backend.app.product_services.player_effectiveness_components import derive_retrospective_player_effectiveness
 session=_session()
 try:
  service=SourceCaptureService(session,snapshot_root=tmp_path/'raw',clock=lambda:NOW)
  snapshot=capture(service).snapshot;ref=freeze_event_artifact(derive(snapshot),snapshot,directory=tmp_path/'parents')
  actual=LOCK+timedelta(minutes=1)
  result=derive_retrospective_player_effectiveness(ref,snapshot,actual_read_at=actual,directory=tmp_path/'parents')
  assert result['provenance']['retrospective_read']['actual_read_at']==actual.isoformat()
  assert result['provenance']['retrospective_read']['original_evidence_boundary_at']==ref['decision_cutoff_at']
  with pytest.raises(ValueError,match='cannot be registered'):require_component_use(result,purpose='current_forecast')
  with pytest.raises(ValueError,match='postlock'):derive_retrospective_player_effectiveness(ref,snapshot,actual_read_at=NOW,directory=tmp_path/'parents')
 finally:session.close()


def test_native_position_only_proof_retains_validated_parent_identity():
 # The position producer supplies native scope only, independent of alias joins.
 # Any conflicting canonical alias outside the authenticated parent is irrelevant.
 result=build([rush(1,rushing_yards=5)],ids={NATIVE:CANONICAL},proofs=[proof(player_master_id=None)])
 assert actor(result,NATIVE)['position']=='QB'
 assert actor(result,NATIVE)['player_master_id']==CANONICAL


def test_actual_position_producer_has_no_alias_join_or_canonical_selection():
 from pathlib import Path
 import ast
 module=ast.parse(Path('research/player_effectiveness_components_20261020/v1/derive_actual.py').read_text())
 queries=[n.value for n in ast.walk(module) if isinstance(n,ast.Constant) and isinstance(n.value,str) and 'SELECT DISTINCT ON' in n.value]
 assert len(queries)==1 and 'player_alias' not in queries[0] and 'player_master_id' not in queries[0]
 proof_calls=[n for n in ast.walk(module) if isinstance(n,ast.Call) and any(k.arg=='source_player_id' for k in n.keywords)]
 assert len(proof_calls)==1
 canonical=next(k.value for k in proof_calls[0].keywords if k.arg=='player_master_id')
 assert isinstance(canonical,ast.Constant) and canonical.value is None
