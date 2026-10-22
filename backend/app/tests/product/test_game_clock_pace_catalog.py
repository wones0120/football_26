from copy import deepcopy
import pytest
from backend.app.product_services.game_clock_pace_catalog import native_order_proof,build_game_clock_pace_catalog,IDS
from backend.app.product_services.environment_context_evidence import DEFINITIONS

def native(play=1,sequence=1,**extra):return dict(season_type='REG',season=2026,week=1,game_id='2026_01_WAS_SF',play_id=play,order_sequence=sequence,**extra)
def context():return dict(version='environment_context_evidence_v1',before_period=202606,definitions=deepcopy(DEFINITIONS),semantic_measurements_sha256='source',provenance={},game_rows=[dict(game_id='2026_01_WAS_SF',season=2026,week=1,team='WAS',interval_rejections={'source_control_break':1},metrics={mid:dict(eligible_events=2,known_outcome_events=2,unknown_outcome_events=0,unknown_eligibility_events=0,observed_outcome_sum=30.,observed_known_mean=15.,all_eligible_mean=15.) for mid in IDS})])
def build(c=None,rows=None):return build_game_clock_pace_catalog(c or context(),native_order_proof(rows or [native(),native(2,2)],before_period=202606),before_period=202606)
def test_exact_game_clock_definition_not_wallclock_and_controls_retained():
 r=build();assert set(r['game_rows'][0]['metrics'])==set(IDS) and r['game_rows'][0]['metrics']['G01-M04']['value']==15
 assert r['game_rows'][0]['interval_rejections']['source_control_break']==1
 assert 'Game-clock' in r['definitions']['G01-M04'] and r['pregame_serving_eligible'] is False

def test_native_control_missing_order_masks_instead_of_skip():
 r=build(rows=[native(),native(2,None,play_type='no_play'),native(3,3)])['game_rows'][0]
 assert r['native_timeline_order']['native_timeline_rows']==3 and r['metrics']['G01-M04']['value'] is None
 assert r['metrics']['G01-M04']['legacy_play_id_sorted_mean']==15

@pytest.mark.parametrize('rows',[[native(),native(2,1)],[native(1,2),native(2,1)],[native(1,1),native(1.0,2)]])
def test_duplicate_or_nonmonotonic_order_cannot_certify(rows):
 assert build(rows=rows)['game_rows'][0]['metrics']['G01-M05']['value'] is None

def test_provider_row_reordering_preserves_canonical_native_order_proof():
 assert build(rows=[native(2,2),native()])['semantic_sha256']==build()['semantic_sha256']

def test_unknown_clock_and_subset_outcomes_mask_exact():
 c=context();m=c['game_rows'][0]['metrics']['G01-M05'];m.update(known_outcome_events=1,unknown_outcome_events=1,observed_outcome_sum=15.,all_eligible_mean=None)
 m=build(c)['game_rows'][0]['metrics']['G01-M05'];assert m['value'] is None and m['known_ordered_sample_mean']==15

def test_zero_elapsed_game_clock_is_observed_not_missing():
 c=context()
 for m in c['game_rows'][0]['metrics'].values():m.update(observed_outcome_sum=0.,observed_known_mean=0.,all_eligible_mean=0.)
 assert build(c)['game_rows'][0]['metrics']['G01-M04']['value']==0

def test_pooled_window_uses_known_exposures_not_average_game_means():
 c=context();r=deepcopy(c['game_rows'][0]);r.update(game_id='2026_02_WAS_SF',week=2)
 for m in r['metrics'].values():m.update(eligible_events=1,known_outcome_events=1,observed_outcome_sum=60.,observed_known_mean=60.,all_eligible_mean=60.)
 c['game_rows'].append(r);p=native_order_proof([native(),native(2,2),dict(native(),week=2,game_id=r['game_id'])],before_period=202606)
 assert build_game_clock_pace_catalog(c,p,before_period=202606)['team_windows'][0]['metrics']['G01-M04']['value']==30

def test_native_timeline_scope_and_source_mean_contradictions_rejected():
 r=native();r['game_id']='2025_01_WAS_SF'
 with pytest.raises(ValueError):build(rows=[r])
 c=context();c['game_rows'][0]['metrics']['G01-M04']['all_eligible_mean']=99
 with pytest.raises(ValueError):build(c)

def _parent(rows,controls=()):
 from backend.app.product_services.opportunity_events import build_event_evidence
 from backend.app.tests.product.test_defense_context_evidence import SOURCE,CUTOFF,IDS
 return dict(event_evidence=build_event_evidence(rows,canonical_ids=IDS,source_receipt=SOURCE,cutoff=CUTOFF),scoped_administrative_rows=list(controls))

def test_native_producer_rederives_reverse_play_id_order_not_legacy_mean():
 from backend.app.tests.product.test_environment_context_evidence import event
 from backend.app.tests.product.test_defense_context_evidence import CUTOFF
 from backend.app.product_services.game_clock_pace_catalog import build_native_game_clock_context
 rows=[event(10,order_sequence=1,game_seconds_remaining=3500),event(1,order_sequence=2,game_seconds_remaining=3480)]
 ctx=build_native_game_clock_context(_parent(rows),before_period=202606,cutoff=CUTOFF)
 proof=native_order_proof(rows,before_period=202606);r=build_game_clock_pace_catalog(ctx,proof,before_period=202606)
 assert proof['game_proofs'][0]['play_id_order_matches_native_order'] is False
 assert r['game_rows'][0]['metrics']['G01-M04']['value']==20

def test_native_control_sequence_breaks_true_adjacent_plays():
 from backend.app.tests.product.test_environment_context_evidence import event
 from backend.app.tests.product.test_defense_context_evidence import CUTOFF
 from backend.app.product_services.game_clock_pace_catalog import build_native_game_clock_context
 rows=[event(10,order_sequence=1),event(20,order_sequence=3)]
 control=event(1,order_sequence=2,play_type='quarter_end')
 ctx=build_native_game_clock_context(_parent(rows,[control]),before_period=202606,cutoff=CUTOFF)
 m=ctx['game_rows'][0];assert m['metrics']['G01-M04']['known_outcome_events']==0 and m['interval_rejections']['source_control_break']==1

def test_native_missing_order_and_clock_never_zero():
 from backend.app.tests.product.test_environment_context_evidence import event
 from backend.app.tests.product.test_defense_context_evidence import CUTOFF
 from backend.app.product_services.game_clock_pace_catalog import build_native_game_clock_context
 rows=[event(10,order_sequence=1),event(20,order_sequence=None)]
 ctx=build_native_game_clock_context(_parent(rows),before_period=202606,cutoff=CUTOFF)
 assert ctx['source_order_unknown_games'] and ctx['game_rows'][0]['metrics']['G01-M04']['all_eligible_mean'] is None

def test_native_drive_after_entry_uses_provider_order_and_rejects_terminal_before_entry():
 from backend.app.tests.product.test_environment_context_evidence import event
 from backend.app.tests.product.test_defense_context_evidence import CUTOFF
 from backend.app.product_services.game_clock_pace_catalog import build_native_redzone_drives
 rows=[event(10,order_sequence=1,yardline_100=15,pass_touchdown=0),event(1,order_sequence=2,yardline_100=25,pass_touchdown=1)]
 ctx=build_native_redzone_drives(_parent(rows),before_period=202606,cutoff=CUTOFF)
 assert ctx['game_rows'][0]['metrics']['G14-M10']['all_eligible_mean']==1
 p=ctx['game_rows'][0]['drive_quality']['drive_outcomes'][0];assert p['first_entry_play_id']==10 and p['terminal_native_orders'][0]['play_id']==1 and p['terminal_precedes_entry'] is False
 rows=[event(1,order_sequence=2,yardline_100=15,pass_touchdown=0),event(10,order_sequence=1,yardline_100=25,pass_touchdown=1)]
 ctx=build_native_redzone_drives(_parent(rows),before_period=202606,cutoff=CUTOFF)
 assert ctx['game_rows'][0]['metrics']['G14-M10']['all_eligible_mean'] is None and ctx['game_rows'][0]['drive_quality']['drive_outcomes'][0]['terminal_precedes_entry'] is True

def test_public_order_map_retains_native_keys_controls_and_unknown_state():
 from backend.app.tests.product.test_environment_context_evidence import event
 from backend.app.tests.product.test_defense_context_evidence import CUTOFF
 from backend.app.product_services.game_clock_pace_catalog import validated_native_order_map
 rows=[event(10,order_sequence=1),event(1,order_sequence=3)];control=event(20,order_sequence=2)
 r=validated_native_order_map(_parent(rows,[control]),before_period=202606,cutoff=CUTOFF)
 assert [x['play_id'] for x in r['rows']]==[10,20,1] and r['rows'][1]['is_control'] and not r['unknown_order_games']


def test_native_drive_rushing_terminal_remains_proven_no_passingTD():
 from backend.app.tests.product.test_environment_context_evidence import event
 from backend.app.tests.product.test_defense_context_evidence import CUTOFF
 from backend.app.product_services.game_clock_pace_catalog import build_native_redzone_drives
 rows=[event(10,order_sequence=1,yardline_100=15,pass_touchdown=0),event(1,order_sequence=2,yardline_100=5,play_type='run',pass_attempt=0,rush_attempt=1,qb_dropback=0,qb_scramble=0,rush_touchdown=1)]
 r=build_native_redzone_drives(_parent(rows),before_period=202606,cutoff=CUTOFF)['game_rows'][0]
 assert r['metrics']['G14-M10']['all_eligible_mean']==0 and r['drive_quality']['drive_outcomes'][0]['completion_basis']=='observed_rushing_touchdown'
