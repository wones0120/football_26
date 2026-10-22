import pytest
from backend.app.product_services.workload_wind_groups import build_workload_wind_groups
from backend.app.tests.product.test_workload_venue_splits import sources

def fixture():
 w,s=sources()
 for g in s['game_rows']:
  g['team_rows']=[dict(team='LAR' if t=='LA' else t,metrics={'G20-M05':dict(value=15 if g['week']%2 else 14,unit='source_wind_mph')}) for t in [g['home_team'],g['away_team']]]
 return w,s

def run(w=None,s=None):
 a,b=fixture();return build_workload_wind_groups(w or a,s or b,before_period=202607)

def test_declared_boundary_and_observed_counts():
 r=run()['rows'][0]['metrics']['G21-M08']['channels']['rush_attempts']
 assert r['positive']['observed_logs']==r['negative']['observed_logs']==2 and r['positive_minus_negative']==-1
 assert run()['pregame_serving_eligible'] is False

def test_unknown_wind_masks_whole_comparison_not_completecase():
 w,s=fixture();s['game_rows'][0]['team_rows'][0]['metrics']['G20-M05']['value']=None
 r=run(w,s)['rows'][0]['metrics']['G21-M08'];assert r['unknown_context_logs']==1 and r['channels']['rush_attempts']['positive_minus_negative'] is None
 assert r['channels']['rush_attempts']['positive']['observed_logs']==1

def test_indoor_missing_wind_not_zero():
 w,s=fixture();s['game_rows'][0]['source_roof']='dome';s['game_rows'][0]['team_rows'][0]['metrics']['G20-M05']['value']=None
 assert run(w,s)['rows'][0]['metrics']['G21-M08']['unknown_context_logs']==1

@pytest.mark.parametrize('value',[-1,float('inf'),True])
def test_invalid_known_wind_rejects(value):
 w,s=fixture();s['game_rows'][0]['team_rows'][0]['metrics']['G20-M05']['value']=value
 with pytest.raises(ValueError):run(w,s)

def test_unit_not_guessed():
 w,s=fixture();s['game_rows'][0]['team_rows'][0]['metrics']['G20-M05']['unit']='unknown'
 with pytest.raises(ValueError):run(w,s)

def test_missing_count_not_zero_and_empty_cohort_undefined():
 w,s=fixture();w['rows'][0]['metrics']['G07-M01']['denominator']=None
 assert run(w,s)['rows'][0]['metrics']['G21-M08']['channels']['rush_attempts']['positive_minus_negative'] is None
 w,s=fixture()
 for g in s['game_rows']:
  for t in g['team_rows']:t['metrics']['G20-M05']['value']=0
 assert run(w,s)['rows'][0]['metrics']['G21-M08']['channels']['rush_attempts']['positive']['per_observed_log'] is None

def test_equivalent_recapture_keeps_semantics():
 w,s=fixture();expected=run(w,s)['semantic_sha256']
 for r in w['rows']:r['source_ref']['imported_at']='2026-10-20T00:00:00Z'
 assert run(w,s)['semantic_sha256']==expected
