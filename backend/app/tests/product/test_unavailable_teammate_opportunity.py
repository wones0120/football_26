from copy import deepcopy
import pytest
from backend.app.product_services.unavailable_teammate_opportunity import build_unavailable_opportunity
from backend.app.product_services.official_absence_source import VERSION as AV
from backend.app.product_services.weekly_effectiveness_catalog_features import VERSION as WV
from backend.app.product_services.weekly_feature_ancestry import VERSION as DV
PID='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';A='00-0000001';B='00-0000002'
def fixture():
 games=[dict(game_id=f'2025_{w:02d}_DEN_LAC',season=2025,week=w,game_type='REG',home_team='LAC',away_team='DEN')for w in(1,2,3)]
 fact=dict(source_row_key='source-notactive0',ordinary_absence_anchor=True,source_status='NOT_ACTIVE',season=2025,week=3,team='DEN',native_game_id=games[2]['game_id'],source_native_gsis_id=A,player_master_id=PID,source_position='TE')
 absences=dict(version=AV,pregame_serving_eligible=False,rows=[fact]);weekly=dict(version=WV,pregame_serving_eligible=False,before_period=202507,rows=[]);ancestry=dict(version=DV,pregame_serving_eligible=False,before_period=202507,field_order=['attempts','carries','targets'],rows=[])
 for w,t in[(1,4),(2,2)]:
  weekly['rows'].append(dict(season=2025,week=w,season_type='REG',source_player_id=A,player_master_id=PID,team='DEN',native_game_id=games[w-1]['game_id'],source_ref=dict(source_id=w)))
  ancestry['rows'].append(dict(source_id=w,source_player_id=A,player_master_id=PID,season=2025,week=w,team='DEN',quarantined=False,fields=[['KNOWN',0,['PRESENT']],['KNOWN',0,['PRESENT']],['KNOWN',t,['PRESENT']]]))
 return absences,weekly,ancestry,games

def run(args=None):return build_unavailable_opportunity(*(args or fixture()))
def m(x,c='targets'):return x['rows'][0]['metrics'][c]
def test_fixed_two_scheduled_counts_and_no_redistribution():
 x=run();assert m(x)['catalog_unavailable_prior_mean']==3 and m(x,'pass_attempts')['catalog_unavailable_prior_mean']==0
 assert x['team_game_totals'][0]['metrics']['targets']['complete_unavailable_prior_mean_sum']==3 and x['replacement_redistribution']is None

def test_all_source_absences_kept_unknown_mass_and_partial_not_called_total():
 a,w,d,g=fixture();b=deepcopy(a['rows'][0]);b.update(source_row_key='unknown0',source_native_gsis_id=B,player_master_id=None,source_position='LB');a['rows'].append(b);x=run((a,w,d,g));t=x['team_game_totals'][0]['metrics']['targets']
 assert len(x['rows'])==2 and t['complete_unavailable_prior_mean_sum']is None and t['known_partial_sum']==3 and t['unknown_actor_count']==1
 assert x['rows'][1]['metrics']['targets']['catalog_unavailable_prior_mean']is None

@pytest.mark.parametrize('kind',['missing','firstgame','unknownteam','unknowncount','canonical'])
def test_no_skipped_games_or_position_zero_or_alias_donation(kind):
 a,w,d,g=fixture()
 if kind=='missing':w['rows'].pop()
 if kind=='firstgame':g.pop(0)
 if kind=='unknownteam':w['rows'][1]['team']=None
 if kind=='unknowncount':d['rows'][1]['fields'][2]=['NULL_OR_EMPTY',None,['NULL']]
 if kind=='canonical':a['rows'][0]['player_master_id']=None
 x=run((a,w,d,g));assert m(x)['catalog_unavailable_prior_mean']is None

def test_bye_uses_two_immediate_scheduled_games_not_calendar_week_or_latest_available():
 a,w,d,g=fixture();g[1]['week']=3;g[1]['game_id']='2025_03_DEN_LAC';g[2]['week']=4;g[2]['game_id']='2025_04_DEN_LAC';a['rows'][0].update(week=4,native_game_id=g[2]['game_id']);w['rows'][1].update(week=3,native_game_id=g[1]['game_id']);d['rows'][1]['week']=3
 assert m(run((a,w,d,g)))['catalog_unavailable_prior_mean']==3

@pytest.mark.parametrize('status',['DID_NOT_PLAY','EMERGENCY_THIRD_QB_EXCEPTION'])
def test_nonordinary_domains_preserved_separately_not_added_to_missing_volume(status):
 a,w,d,g=fixture();b=deepcopy(a['rows'][0]);b.update(source_row_key='excluded',source_status=status,ordinary_absence_anchor=False);a['rows'].append(b);x=run((a,w,d,g));assert len(x['rows'])==1 and len(x['excluded_source_domains'])==1

@pytest.mark.parametrize('bad',['factduplicate','nativeduplicate','weeklyduplicate','diagduplicate','nativegame','sourceid','pid','phase','knownnegative','unknownfilled','anchorgame'])
def test_source_scope_and_quantity_integrity_guards(bad):
 a,w,d,g=fixture()
 if bad=='factduplicate':a['rows'].append(deepcopy(a['rows'][0]))
 if bad=='nativeduplicate':b=deepcopy(a['rows'][0]);b['source_row_key']='other';a['rows'].append(b)
 if bad=='weeklyduplicate':w['rows'].append(deepcopy(w['rows'][0]))
 if bad=='diagduplicate':d['rows'].append(deepcopy(d['rows'][0]))
 if bad=='nativegame':w['rows'][0]['native_game_id']='2025_01_DEN_KC'
 if bad=='sourceid':d['rows'][0]['source_id']=99
 if bad=='pid':d['rows'][0]['player_master_id']='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
 if bad=='phase':w['rows'][0]['season_type']='POST'
 if bad=='knownnegative':d['rows'][0]['fields'][2][1]=-1
 if bad=='unknownfilled':d['rows'][0]['fields'][2]=['NULL',0,['NULL']]
 if bad=='anchorgame':a['rows'][0]['native_game_id']='2025_03_DEN_KC'
 with pytest.raises(ValueError):run((a,w,d,g))

def test_unresolved_native_fact_never_joined_by_literal_name_or_position():
 a,w,d,g=fixture();a['rows'][0].update(source_native_gsis_id=None,player_master_id=None,source_position='OL');x=run((a,w,d,g));assert m(x)['catalog_unavailable_prior_mean']is None and x['team_game_totals'][0]['metrics']['targets']['known_partial_sum']is None
