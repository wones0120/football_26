from copy import deepcopy
import pytest
from backend.app.product_services.opportunity_events import build_event_evidence
from backend.app.product_services.player_opportunity_components import build_player_opportunity_components,RETROSPECTIVE_USE,require_component_use
from backend.app.product_services.player_effectiveness_components import build_player_effectiveness_components
from backend.app.product_services.player_workload_catalog_components import build_player_workload_catalog_components
from backend.app.tests.product.test_defense_context_evidence import play,SOURCE,CUTOFF,IDS
from backend.app.tests.product.test_defense_context_extensions import rush,proof,NATIVE,CANONICAL


QBNATIVE='00-0000002'
QBUUID='00000000-0000-0000-0000-000000000003'

def blocks(rows,proofs=()):
 rows=deepcopy(rows)
 for row in rows:
  for field in ('passer_player_id','rusher_player_id'):
   if row.get(field)=='q':row[field]=QBNATIVE
 parent=dict(event_evidence=build_event_evidence(rows,canonical_ids={'w':IDS['w'],QBNATIVE:QBUUID,NATIVE:CANONICAL},source_receipt=SOURCE,cutoff=CUTOFF));kwargs=dict(before_period=202606,cutoff=CUTOFF,position_evidence=proofs)
 return build_player_opportunity_components(parent,**kwargs),build_player_effectiveness_components(parent,**kwargs)


def compose(a,b):return build_player_workload_catalog_components(a,b,before_period=202606)


def actor(result,native):return next(r for r in result['actor_game_rows'] if r['source_player_id']==(QBNATIVE if native=='q' else native))


def test_QB_physical_dropbacks_attempts_spikes_sacks_and_scrambles_not_doubleadded():
 rows=[play(1,complete_pass=1),play(2,sack=1,complete_pass=0),play(3,qb_spike=1,complete_pass=0,receiver_player_id=None),rush(4,rusher_player_id='q',passer_player_id=None,qb_scramble=1,qb_dropback=1)]
 qbproof=proof(source_player_id=QBNATIVE,player_master_id=QBUUID);r=actor(compose(*blocks(rows,[qbproof])),'q')['metrics']
 assert r['G03-M01']['exact_within_log_sum']==3
 assert r['G03-M02']['exact_within_log_sum']==2 and r['G03-M03']['exact_within_log_sum']==1
 assert r['G03-M04']['exact_within_log_sum']==1 and r['G03-M06']['exact_within_log_sum']==1
 assert r['G03-M07']['exact_within_log_value']==pytest.approx(1/3) and r['G03-M10']['exact_within_log_value']==1


def test_QB_share_fullsource_retains_unmapped_backup_not_userpool():
 rows=[play(1),play(2,passer_player_id='unmapped')];p=proof(source_player_id=QBNATIVE,player_master_id=QBUUID)
 result=compose(*blocks(rows,[p]));m=actor(result,'q')['metrics']['G03-M10']
 assert m['full_team_denominator']==2 and m['exact_within_log_value']==.5
 assert result['identity_review_requests']


def test_missing_passer_masks_fullteam_dropback_share_not_zero_donation():
 rows=[play(1),play(2,passer_player_id=None)];p=proof(source_player_id=QBNATIVE,player_master_id=QBUUID)
 result=compose(*blocks(rows,[p]));m=actor(result,'q')['metrics']['G03-M10']
 assert m['full_team_denominator'] is None and m['exact_within_log_value'] is None


def test_RB_ten_contextual_measures_preplay_leadtrail_and_halfclock():
 rows=[rush(1,down=1,ydstogo=1,qtr=2,half_seconds_remaining=120,score_differential=3),
  rush(2,down=3,ydstogo=4,qtr=4,half_seconds_remaining=100,score_differential=-3),
  rush(3,down=2,ydstogo=2,qtr=4,half_seconds_remaining=121,score_differential=0),
  rush(4,qb_kneel=1,qtr=2,half_seconds_remaining=50)]
 r=actor(compose(*blocks(rows,[proof(position='RB') ])),NATIVE)['metrics']
 assert r['G06-M01']['exact_within_log_sum']==4 and r['G06-M02']['exact_within_log_value']==1
 assert [r[k]['exact_within_log_sum'] for k in ['G06-M03','G06-M04','G06-M05','G06-M06','G06-M07','G06-M08','G06-M09','G06-M10']]==[2,1,2,2,1,2,1,1]


def test_RB_share_denominator_keeps_QB_rushes_and_FB_source_taxonomy_explicit():
 rows=[rush(1),rush(2,rusher_player_id='q',qb_scramble=1,qb_dropback=1)]
 result=compose(*blocks(rows,[proof(position='FB')]))
 r=actor(result,NATIVE);assert r['position']=='RB' and r['metrics']['G06-M02']['exact_within_log_value']==.5


def test_without_typed_QB_RB_proof_only_receiving_measurements_available():
 result=compose(*blocks([play(1),rush(2)]))
 assert all(not any(m.startswith(('G03','G06')) for m in r['metrics']) for r in result['actor_game_rows'])


def test_receiving_exact_counts_shares_signed_air_and_depth_with_alltargets():
 result=compose(*blocks([play(1,air_yards=-2),play(2,air_yards=10,receiver_player_id='unmapped')]))
 w=actor(result,'w')['metrics'];assert w['G08-M01']['exact_within_log_sum']==1 and w['G08-M07']['exact_within_log_sum']==-2
 assert w['G08-M02']['exact_within_log_value']==.5 and w['G08-M08']['exact_within_log_value']==-.25
 assert w['G08-M09']['exact_within_log_value']==-2


def test_unknown_target_attribution_masks_exact_air_depth_and_target_denominators():
 r=actor(compose(*blocks([play(1,air_yards=10),play(2,receiver_player_id=None,air_yards=12)])),'w')['metrics']
 assert all(r[k]['exact_within_log_value'] is None for k in ['G08-M02','G08-M08','G08-M09'])
 assert r['G08-M07']['exact_within_log_sum'] is None


def test_missing_context_not_zero():
 result=compose(*blocks([rush(1,down=None,ydstogo=None,qtr=None,score_differential=None)],[proof(position='RB')]))
 r=actor(result,NATIVE)['metrics']
 assert r['G06-M03']['exact_within_log_sum'] is None and r['G06-M06']['exact_within_log_sum'] is None


@pytest.mark.parametrize('change',['scope','period','identity','duplicate','use'])
def test_component_scope_identity_and_chronology_guards(change):
 a,b=blocks([play(1)])
 if change=='scope':b['provenance']['event_receipt_sha256']='b'*64
 elif change=='period':b['before_period']=202607
 elif change=='identity':b['actor_game_rows'][0]['player_master_id']='00000000-0000-0000-0000-000000000099'
 elif change=='duplicate':a['actor_game_rows'].append(deepcopy(a['actor_game_rows'][0]))
 else:b['evidence_use']=RETROSPECTIVE_USE
 with pytest.raises(ValueError):compose(a,b)


def test_source_order_semantics_and_postlock_current_use_guard():
 rows=[play(1,air_yards=10),rush(2)];first=compose(*blocks(rows));assert first['semantic_measurements_sha256']==compose(*blocks(rows[::-1]))['semantic_measurements_sha256']
 a,b=blocks(rows)
 for v in (a,b):v.update(evidence_use=RETROSPECTIVE_USE,pregame_serving_eligible=False)
 with pytest.raises(ValueError,match='cannot be registered'):require_component_use(compose(a,b),purpose='forecast')
 a['actor_game_rows'][0]['game_id']='2026_06_BUF_MIA'
 with pytest.raises(ValueError,match='Nonprior'):compose(a,b)
