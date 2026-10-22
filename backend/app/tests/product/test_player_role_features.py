from copy import deepcopy
import pytest
from backend.app.product_services.player_role_features import build_player_role_features

P='11111111-1111-4111-8111-111111111111';Q='22222222-2222-4222-8222-222222222222'
NOW='2026-10-19T20:00:00+00:00'

def actor(pid=P,position='CB'):return dict(player_master_id=pid,team='WAS',position=position)
def fact(pid=P,position='CB',kind='game_status',**kwargs):
    return dict(player_id=pid,team='WAS',position=position,season=2026,week=6,kind=kind,status='OUT',source='official',source_ids=['s'],source_uri='https://www.commanders.com/report',observed_at='2026-10-19T19:00:00+00:00',received_at='2026-10-19T19:01:00+00:00',**kwargs)
def roster(ids=(P,)):
    return {'WAS':dict(complete=True,season=2026,week=6,player_master_ids=list(ids),source_refs=['roster'],observed_at='2026-10-19T19:00:00+00:00',received_at='2026-10-19T19:01:00+00:00')}
def build(actors=None,facts=None,**kw):return build_player_role_features(actors or [actor()],facts or [],season=2026,week=6,cutoff=NOW,**kw)


def test_exact_unavailable_team_count_requires_full_roster_not_salary_subset():
    r=build(facts=[fact()],roster_coverage=roster());p=r['players'][0]
    assert p['metrics']['G17-M01']['value']=='OUT'
    assert r['teams'][0]['metrics']['G18-M05']['value']==1
    missing=build(facts=[fact()]);m=missing['teams'][0]['metrics']['G18-M05']
    assert m['value'] is None and m['sample']['known_unavailable_lower_bound']==1
    assert not r['consumed_by_models'] and not r['consumed_by_optimizer']


def test_blank_or_roster_act_does_not_create_no_game_designation():
    f=fact(kind='roster_status');f['status']='ACT';r=build(facts=[f])
    assert r['players'][0]['metrics']['G17-M01']['value'] is None
    assert r['players'][0]['metrics']['G17-M10']['value'] is None


def test_practice_trend_uses_actual_practice_dates_not_recapture_time():
    a=fact(kind='practice',practice_status='DNP',practice_date='2026-10-17');b=fact(kind='practice',practice_status='FP',practice_date='2026-10-18')
    r=build(facts=[a,b]);m=r['players'][0]['metrics']['G17-M02']
    assert m['value']['ordinal_change']==2 and m['sample']['practice_days']==2
    a.pop('practice_date');b.pop('practice_date');assert build(facts=[a,b])['players'][0]['metrics']['G17-M02']['value'] is None


def test_conflicting_practice_day_does_not_invent_a_trend():
    a=fact(kind='practice',practice_status='DNP',practice_date='2026-10-17');b=fact(kind='practice',practice_status='FP',practice_date='2026-10-17')
    assert build(facts=[a,b])['players'][0]['metrics']['G17-M02']['missing_reason']=='conflicting_practice_day'


def test_depth_order_and_workload_restriction_are_source_values_not_forecasts():
    a=fact(kind='depth_role',depth_position=2);b=fact(kind='workload_restriction',restriction={'text':'limited snaps','maximum_snaps':None})
    p=build(facts=[a,b])['players'][0]
    assert p['metrics']['G17-M05']['value']==2 and p['metrics']['G17-M10']['value']['maximum_snaps'] is None
    assert not p['metrics']['G17-M10']['forecast']


@pytest.mark.parametrize('kind',['future','stale','wrong_week','wrong_identity','wrong_position','unscoped'])
def test_source_scope_and_clocks_cannot_clear_unknown(kind):
    f=fact()
    if kind=='future':f['received_at']='2026-10-20T20:00:00+00:00'
    if kind=='stale':f['observed_at']='2026-10-17T20:00:00+00:00'
    if kind=='wrong_week':f['week']=5
    if kind=='wrong_identity':f['player_id']=Q
    if kind=='wrong_position':f['position']='S'
    if kind=='unscoped':f['week']=None
    assert build(facts=[f])['players'][0]['metrics']['G17-M01']['value'] is None


def test_roster_missing_actor_unresolved_identity_and_unknown_status_preserved():
    r=build(actors=[actor(),actor(Q),dict(source_player_id='unmapped',team='WAS',position='CB')],facts=[fact()],roster_coverage=roster())
    assert len(r['identity_review_requests'])==1
    m=r['teams'][0]['metrics']['G18-M05'];assert m['value'] is None and m['sample']['unknown_status_actors']==1
    with pytest.raises(ValueError,match='Duplicate'):build(actors=[actor(),actor()])


def test_reserve_participation_prohibition_preserves_game_status_conflict():
    a=fact();a['status']='Q';b=fact(kind='roster_status');b['status']='RES'
    r=build(facts=[a,b],roster_coverage=roster())
    assert r['players'][0]['availability_state']=='UNAVAILABLE'
    assert r['teams'][0]['metrics']['G18-M05']['value']==1
    assert r['players'][0]['metrics']['G17-M01']['value']=='QUESTIONABLE'


def test_recapture_and_user_fields_do_not_change_feature_semantics():
    f=fact();a=build(facts=[f],roster_coverage=roster());g=deepcopy(f);g.update(source_ids=['newcapture'],observed_at='2026-10-19T19:30:00+00:00',received_at='2026-10-19T19:31:00+00:00')
    b=build(actors=[dict(actor(),user_excluded=True)],facts=[g],roster_coverage=roster())
    assert a['semantic_measurements_sha256']==b['semantic_measurements_sha256']
    assert a['provenance']!=b['provenance']


@pytest.mark.parametrize('kind',['depth_role','workload_restriction'])
@pytest.mark.parametrize('field,value',[('effective_at','2026-10-20T20:00:00+00:00'),('modified_at','2026-10-20T20:00:00+00:00'),('effective_at','not-a-clock'),('modified_at','not-a-clock')])
def test_future_or_malformed_event_clock_never_selects_depth_or_restriction(kind,field,value):
    f=fact(kind=kind,depth_position=2,restriction='restricted');f[field]=value
    metric='G17-M05' if kind=='depth_role' else 'G17-M10'
    assert build(facts=[f])['players'][0]['metrics'][metric]['value'] is None


def test_ol_backup_not_counted_as_unavailable_starter_and_missing_role_unknown():
    a=actor(position='OL');out=fact(position='OL');role=fact(position='OL',kind='role',role='expected_backup')
    r=build(actors=[a],facts=[out,role],roster_coverage=roster());m=r['teams'][0]['metrics']['G18-M03']
    assert m['value']==0 and m['sample']['starter_only']
    role['role']='expected_starter';assert build(actors=[a],facts=[out,role],roster_coverage=roster())['teams'][0]['metrics']['G18-M03']['value']==1
    assert build(actors=[a],facts=[out],roster_coverage=roster())['teams'][0]['metrics']['G18-M03']['value'] is None


def test_unknown_position_or_unresolved_alias_can_belong_to_any_defensive_group():
    r=build(actors=[actor(position='UNKNOWN')],facts=[fact(position='UNKNOWN')],roster_coverage=roster())
    assert all(r['teams'][0]['metrics'][m]['value'] is None for m in ('G18-M03','G18-M04','G18-M05','G18-M06','G18-M07'))
    f=fact();f.pop('player_id');f['source_player_id']='unmapped-native'
    r=build(facts=[fact(),f],roster_coverage=roster())
    assert r['identity_review_requests'][0]['source_player_id']=='unmapped-native'
    assert r['teams'][0]['metrics']['G18-M05']['value'] is None


def test_native_designation_is_not_relabeled_official_and_act_not_known_healthy():
    f=fact();f['source_uri']='https://www.draftkings.com/native';r=build(facts=[f])
    assert r['players'][0]['metrics']['G17-M01']['value'] is None
    assert r['players'][0]['designation_resolution']['effective_designation']=='OUT'
    f=fact(kind='roster_status');f['status']='ACT';r=build(facts=[f],roster_coverage=roster())
    assert r['teams'][0]['metrics']['G18-M05']['value'] is None
    assert r['players'][0]['availability_state']=='UNKNOWN'


def test_center_oc_starter_is_in_offensive_line_group():
    r=build(actors=[actor(position='OC')],facts=[fact(position='OC'),fact(position='OC',kind='role',role='expected_starter')],roster_coverage=roster())
    assert r['teams'][0]['metrics']['G18-M03']['value']==1


def test_uuid_spelling_is_canonical_before_duplicate_or_fact_matching():
    lower='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';upper=lower.upper()
    with pytest.raises(ValueError,match='Duplicate'):build(actors=[actor(lower),actor(upper)])
    f=fact(pid=upper);r=build(actors=[actor(upper)],facts=[f],roster_coverage=roster((lower,)))
    assert r['players'][0]['player_master_id']==lower
    assert r['teams'][0]['metrics']['G18-M05']['value']==1
