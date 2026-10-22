from copy import deepcopy
import pytest
from backend.app.tests.product.test_weekly_effectiveness_catalog_features import row,build
from backend.app.product_services.qb_rushing_allowed_catalog import build_qb_rushing_allowed
from backend.app.product_services.schedule_context_features import VERSION

def schedules():return dict(version=VERSION,pregame_serving_eligible=False,semantic_sha256='native-schedule',provenance={'snapshot_id':'schedule'},game_rows=[dict(game_id='2025_01_LA_SF',game_type='REG',season=2025,week=1,home_team='SF',away_team='LAR')])
def result(w=None,s=None,**kw):return build_qb_rushing_allowed(w or build(),s or schedules(),before_period=202607,**kw)
def test_exact_official_QB_yards_allowed_opponent_and_signed_totals():
 m=result()['game_rows'][0];assert m['defense_team']=='SF' and m['offense_team']=='LAR'
 assert m['metrics']['G15-M10']['value']==-2 and m['metrics']['G15-M10']['exact_official_carries']==3
 assert m['metrics']['G15-M10']['yards_per_official_carry']==-2/3

def test_multiple_source_QBs_preserve_team_budget_not_average_rates():
 a=row();b=row(source_id=2,source_player_id='00-0031235',player_master_id='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb');b['raw_row_json'].update(player_id=b['source_player_id'],rushing_yards=10,carries=1)
 m=result(build([a,b]))['game_rows'][0]['metrics']['G15-M10'];assert m['value']==8 and m['exact_official_carries']==4 and m['yards_per_official_carry']==2

def test_unresolved_QB_identity_native_counts_retained_but_exact_masked():
 r=result(build([row(player_master_id=None)]))['game_rows'][0]['metrics']['G15-M10'];assert r['value'] is None and r['known_source_QB_yards_sum']==-2 and r['unknown_identity_or_role_rows']==1

def test_unknown_source_position_potential_QB_never_guessed():
 x=row(position=None);x['raw_row_json']['position']=None;r=result(build([x]))['game_rows'][0]['metrics']['G15-M10'];assert r['value'] is None and r['observed_native_QB_rows']==0

def test_missing_native_rows_not_erased_from_possible_QB_cohort():
 r=result(excluded_source_rows=[row(source_player_id=None)])['game_rows'][0]['metrics']['G15-M10'];assert r['value'] is None

def test_unknown_team_masks_period_without_guessing_opponent():
 a=row();b=row(source_id=2,source_player_id='00-0031235',team=None);b['raw_row_json']['player_id']=b['source_player_id'];r=result(build([a,b]));assert r['game_rows'][0]['metrics']['G15-M10']['value'] is None and r['unbound_rows']

def test_absent_QBs_not_zero_and_zero_carries_undefined_rate():
 s=schedules();s['game_rows'].append(dict(game_id='2025_01_WAS_NYG',game_type='REG',season=2025,week=1,home_team='NYG',away_team='WAS'))
 assert len(result(s=s)['game_rows'])==1
 x=row();x['raw_row_json'].update(carries=0,rushing_yards=0);m=result(build([x]))['game_rows'][0]['metrics']['G15-M10'];assert m['value']==0 and m['yards_per_official_carry'] is None

def test_ambiguous_schedule_and_native_game_conflict_rejected():
 s=schedules();s['game_rows'].append(deepcopy(s['game_rows'][0]))
 with pytest.raises(ValueError,match='Ambiguous'):result(s=s)
 w=build();w['rows'][0]['native_game_id']='different'
 with pytest.raises(ValueError,match='contradicts'):result(w)
