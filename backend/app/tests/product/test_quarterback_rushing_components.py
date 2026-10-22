from copy import deepcopy
import pytest
from backend.app.product_services.opportunity_events import build_event_evidence
from backend.app.product_services.player_opportunity_components import build_player_opportunity_components,require_component_use,RETROSPECTIVE_USE
from backend.app.product_services.player_effectiveness_components import build_player_effectiveness_components
from backend.app.product_services.quarterback_rushing_components import build_quarterback_rushing_components
from backend.app.tests.product.test_defense_context_evidence import SOURCE,CUTOFF,IDS
from backend.app.tests.product.test_defense_context_extensions import rush,proof,NATIVE,CANONICAL


def blocks(rows,proofs=None):
 parent=dict(event_evidence=build_event_evidence(rows,canonical_ids={**IDS,NATIVE:CANONICAL},source_receipt=SOURCE,cutoff=CUTOFF))
 kwargs=dict(before_period=202606,cutoff=CUTOFF,position_evidence=[proof()] if proofs is None else proofs)
 return build_player_opportunity_components(parent,**kwargs),build_player_effectiveness_components(parent,**kwargs)


def compose(a,b):return build_quarterback_rushing_components(a,b,before_period=202606)


def test_scoped_QB_counts_reuse_measures_rates_and_explicit_source_gaps():
 a,b=blocks([rush(1,qb_scramble=1,rushing_yards=8,epa=.5,first_down_rush=1,rush_touchdown=0,yardline_100=4),
  rush(2,qb_kneel=1,rushing_yards=-1,epa=-1,yardline_100=25),rush(3,rushing_yards=2,epa=-.2,first_down_rush=0,rush_touchdown=1,yardline_100=8)])
 result=compose(a,b);row=result['actor_game_rows'][0];m=row['metrics']
 assert row['position']=='QB' and row['player_master_id']==CANONICAL
 assert [m[x]['exact_within_log_count'] for x in ('G05-M02','G05-M03','G05-M07','G05-M08','G05-M09','G05-M10')]==[1,1,1,2,1,1]
 assert m['G05-M05']['exact_within_log_mean']==5 and m['G05-M06']['exact_within_log_mean']==.5
 assert row['nonscramble_or_other_support']['exact_within_log_count']==1
 assert set(result['source_gaps'])=={'G05-M01','G05-M04'}
 assert 'G05-M01' not in m and result['forecast'] is None
 assert result['full_team_denominators']==a['team_denominators']


def test_unproven_or_nonQB_position_does_not_silently_become_QB():
 for proofs in ([],[proof(position='RB')]):
  result=compose(*blocks([rush(1,rushing_yards=5)],proofs))
  assert result['actor_game_rows']==[] and result['excluded_unproven_or_nonQB']


def test_missing_native_rusher_masks_exact_counts_and_rates_retaining_lowerbounds():
 result=compose(*blocks([rush(1,rushing_yards=5,epa=.5),rush(2,rusher_player_id=None,rushing_yards=3,epa=.3)]));m=result['actor_game_rows'][0]['metrics']
 assert m['G05-M08']['counted_lower_bound']==1 and m['G05-M08']['exact_within_log_count'] is None
 assert m['G05-M08']['unknown_native_rusher_exposures']==1
 assert m['G05-M05']['known_attributed_sample_mean']==5 and m['G05-M05']['exact_within_log_mean'] is None


def test_missing_outcomes_are_unknown_not_zero():
 result=compose(*blocks([rush(1,rushing_yards=None,epa=None,first_down_rush=None,rush_touchdown=None)]));m=result['actor_game_rows'][0]['metrics']
 assert m['G05-M10']['exact_within_log_count'] is None
 assert m['G05-M05']['known_attributed_sample_mean'] is None
 assert m['G05-M06']['exact_within_log_mean'] is None


@pytest.mark.parametrize('change',['source','period','identity','duplicate','version','use','event_scope'])
def test_contradictory_component_lineage_and_identity_rejected(change):
 a,b=blocks([rush(1,rushing_yards=3)])
 if change=='source':b['provenance']['source']['content_sha256']='b'*64
 elif change=='period':b['before_period']=202607
 elif change=='identity':b['actor_game_rows'][0]['player_master_id']='00000000-0000-0000-0000-000000000099'
 elif change=='duplicate':b['actor_game_rows'].append(deepcopy(b['actor_game_rows'][0]))
 elif change=='version':b['version']='unknown'
 elif change=='event_scope':b['provenance']['event_receipt_sha256']='b'*64
 else:b['evidence_use']='postlock_descriptive_not_pregame_or_serving'
 with pytest.raises(ValueError):compose(a,b)


def test_prior_native_game_and_nonserving_marker_enforced():
 a,b=blocks([rush(1,rushing_yards=3)])
 for block in (a,b):block.update(evidence_use=RETROSPECTIVE_USE,pregame_serving_eligible=False)
 result=compose(a,b)
 with pytest.raises(ValueError,match='cannot be registered'):require_component_use(result,purpose='forecast')
 b['actor_game_rows'][0]['game_id']='2026_06_BUF_MIA'
 with pytest.raises(ValueError,match='Nonprior'):compose(a,b)


def test_order_invariance_and_material_change_significant():
 rows=[rush(1,rushing_yards=3,epa=.1),rush(2,rushing_yards=5,epa=.5)]
 first=compose(*blocks(rows))
 assert first['semantic_measurements_sha256']==compose(*blocks(rows[::-1]))['semantic_measurements_sha256']
 rows[0]['rushing_yards']=8
 assert first['semantic_measurements_sha256']!=compose(*blocks(rows))['semantic_measurements_sha256']
