from copy import deepcopy
import pytest
from backend.app.product_services.historical_workload_trends import build_historical_workload_trends
from backend.app.tests.product.test_weekly_effectiveness_catalog_features import row,build,P,Q
from backend.app.product_services.schedule_context_features import VERSION
CUTOFF='2026-10-20T10:00:00Z'

def sources(weeks=range(1,10)):
 records=[];games=[]
 for w in weeks:
  gid=f'2025_{w:02d}_SF_LA';games.append(dict(game_id=gid,season=2025,week=w,game_type='REG',home_team='LA',away_team='SF'))
  for i in(0,1):
   r=row(source_id=10*w+i,season=2025,week=w,source_player_id=f'00-003123{4+i}',player_master_id=P if i==0 else Q,position='QB'if i==0 else'WR')
   r['raw_row_json'].update(season=2025,week=w,player_id=r['source_player_id'],position=r['position'],game_id=gid,attempts=20+w if i==0 else 0,completions=0,interceptions=0,passing_tds=0,carries=w if i==0 else 10,targets=w if i==0 else 10,receptions=0)
   records.append(r)
 weekly=build(records);weekly['provenance']['actual_derived_at']='2026-10-20T04:00:00Z'
 schedule=dict(version=VERSION,game_rows=games,pregame_serving_eligible=False,semantic_sha256='schedule',provenance={})
 return [weekly,schedule,dict(rows=records)]


def run(x=None,missing=()):return build_historical_workload_trends(*(x or sources()),before_period=202607,cutoff=CUTOFF,positive_participants_missing_weekly=missing)
def actor(x):return next(r for r in x['rows']if r['source_player_id']=='00-0031234')
def channel(x,mid='G22-M01',c='rush_attempts'):return actor(x)['metrics'][mid]['channels'][c]


def test_latest_scheduled_against_exact_eight_prior_games_pooled_shares_not_mean_shares():
 x=run();r=channel(x);assert r['recent']['periods']==[202509] and r['reference']['periods']==list(range(202501,202509))
 assert r['count_mean_difference']==4.5
 assert r['pooled_share_difference']==pytest.approx(9/19-36/116)
 assert actor(x)['target_boundary_period']==202519 and x['models_or_optimizer_consumed']is False


def test_recent_three_against_same_season_all_prior_source_games_with_overlap_explicit():
 x=run();r=channel(x,'G22-M02');assert r['recent']['periods']==[202507,202508,202509]
 assert r['reference']['periods']==list(range(202501,202510))
 assert r['count_mean_difference']==3 and r['pooled_share_difference']==pytest.approx(24/54-45/135)
 assert actor(x)['metrics']['G22-M02']['recent_reference_overlap']is True


def test_less_than_eight_predecessors_stays_unknown_not_upto_eight():
 r=channel(run(sources(range(1,9))));assert r['reference']['achieved_scheduled_games']==7 and r['count_mean_difference']is None


def test_bye_is_not_a_scheduled_missing_game_and_no_source_game_skipped():
 x=sources([1,2,3,4,6,7,8,9,10]);r=channel(run(x));assert len(r['reference']['periods'])==8 and 202505 not in r['reference']['periods']
 x[1]['game_rows'].append(dict(game_id='2025_11_SF_LA',season=2025,week=11,game_type='REG',home_team='LA',away_team='SF'))
 r=channel(run(x));assert r['recent']['periods']==[202511] and r['count_mean_difference']is None


def test_missing_actor_week_is_unknown_never_zero_or_latest_available_substitution():
 x=sources();x[0]['rows']=[r for r in x[0]['rows']if not(r['week']==8 and r['source_player_id']=='00-0031234')]
 r=channel(run(x));assert r['reference']['known_count_games']==7 and r['reference']['unknown_count_game_ids']==['2025_08_SF_LA']
 assert r['count_mean_difference']is None and r['pooled_share_difference']is None


def test_unmapped_other_actor_kept_in_full_native_source_budget():
 x=sources()
 for r in x[0]['rows']:
  if r['source_player_id']=='00-0031235':r['player_master_id']=None
 assert channel(run(x))['pooled_share_difference']==pytest.approx(9/19-36/116)


def test_quarantined_native_raw_actor_retained_in_team_budget():
 x=sources()
 for r in x[2]['rows']:
  if r['source_player_id']=='00-0031235':r['source_player_id']='malformed';r['raw_row_json']['player_id']='malformed'
 x[0]=build(x[2]['rows']);x[0]['provenance']['actual_derived_at']='2026-10-20T04:00:00Z'
 assert channel(run(x))['pooled_share_difference']==pytest.approx(9/19-36/116)


def test_nonQB_pass_actor_inapplicable_but_native_passing_budget_not_donated():
 x=run();other=next(r for r in x['rows']if r['source_player_id']=='00-0031235')
 assert other['metrics']['G22-M01']['channels']['pass_attempts']['count_mean_difference']is None
 assert channel(x,c='pass_attempts')['count_mean_difference']==4.5


def test_zero_count_budget_undefined_share_while_count_mean_difference_valid():
 x=sources()
 for r in x[2]['rows']:r['raw_row_json'].update(carries=0)
 x[0]=build(x[2]['rows']);x[0]['provenance']['actual_derived_at']='2026-10-20T04:00:00Z'
 r=channel(run(x));assert r['count_mean_difference']==0 and r['pooled_share_difference']is None and r['reference']['known_zero_team_budget']is True


def test_positive_participant_missing_weekly_retained_and_masks_team_budget():
 x=sources();x[0]['rows']=[r for r in x[0]['rows']if not(r['week']==5 and r['source_player_id']=='00-0031234')]
 p=dict(season=2025,week=5,team='LAR',source_player_id=None,player_master_id=P,native_game_id='2025_05_SF_LA',source_position=None,offense_snaps=4)
 r=channel(run(x,[p]));assert r['reference']['unknown_count_game_ids']==['2025_05_SF_LA'] and r['count_mean_difference']is None
 assert r['reference']['unknown_team_budget_game_ids']==['2025_05_SF_LA']

@pytest.mark.parametrize('bad',['checksum','revision','game','duplicate','future','budget_scope'])
def test_source_native_revisions_and_chronology_reject(bad):
 x=sources()
 if bad=='checksum':x[2]['rows'][0]['raw_row_json']['carries']=999
 if bad=='revision':x[2]['rows'][0]['ingest_run_id']='other'
 if bad=='game':x[0]['rows'][0]['native_game_id']='2025_01_BUF_MIA'
 if bad=='duplicate':x[2]['rows'].append(deepcopy(x[2]['rows'][0]))
 if bad=='future':x[2]['rows'][0]['imported_at']='2026-10-21T00:00:00Z'
 if bad=='budget_scope':x[2]['rows'][0]['team']='MIA'
 with pytest.raises(ValueError):run(x)
