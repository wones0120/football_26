from copy import deepcopy
import pytest
from backend.app.product_services.qb_continuity_opportunity import build_qb_continuity_opportunity
from backend.app.product_services.workload_starting_qb_context import normalize_starting_qb_context
from backend.app.product_services.schedule_context_features import VERSION
from backend.app.product_services.evaluation_record import digest
from backend.app.tests.product.test_weekly_effectiveness_catalog_features import row, build, Q

CUTOFF='2026-10-20T05:00:00Z'


def sources(role='WR'):
    records=[]; games=[]; native=[]
    for week in (1,2,3,4):
        g=dict(game_id=str(week), season=2026, week=week,game_type='REG',home_team='LAR',away_team='SF')
        games.append(g)
        native.append(g | dict(gameday=f'2026-10-0{week}',gametime='13:00',home_qb_id='00-0031111' if week<3 else '00-0032222',away_qb_id='00-0033333'))
        for i, targets in ((0,week),(1,10-week)):
            r=row(season=2026,week=week,position=role if not i else 'TE',source_id=week*10+i,
                  source_player_id='00-0031234' if not i else '00-0031235',player_master_id=row()['player_master_id'] if not i else Q)
            r['raw_row_json'].update(season=2026,week=week,position=r['position'],player_id=r['source_player_id'],targets=targets,receptions=0)
            records.append(r)
    w=build(records);w['provenance']['actual_derived_at']='2026-10-20T04:00:00Z'
    s=dict(version=VERSION, game_rows=games,pregame_serving_eligible=False,semantic_sha256='schedule',
           provenance=dict(snapshot_id='snapshot',sha256='sha',observed_at='2026-10-20T03:00:00Z',captured_at='2026-10-20T03:01:00Z'))
    return w,s,normalize_starting_qb_context(native,s),dict(rows=records)


def run(src=None, missing=()):
    return build_qb_continuity_opportunity(*(src or sources()),before_period=202607,cutoff=CUTOFF,positive_participants_missing_weekly=missing)


def first(x):return next(r for r in x['rows'] if r['source_player_id']=='00-0031234')


def rehash(q):q['semantic_sha256']=digest({k:q[k] for k in ('version','rows','role_scope')})


def test_immediate_scheduled_qb_change_and_matched_native_budget():
    r=first(run());assert [l['continuity'] for l in r['logs']]==['first_scheduled_game','same','changed','same']
    assert r['metrics']['same']['exact_targets_per_observed_log']==3
    assert r['metrics']['changed']['exact_targets_per_observed_log']==3
    assert r['metrics']['same']['exact_pooled_target_share']==.3
    assert r['changed_minus_same_pooled_target_share']==0


def test_role_scopes_and_no_causal_forecast():
    x=run(sources('RB'));assert first(x)['candidate_id']=='X03-M04'
    assert x['forecast'] is None and x['models_or_optimizer_consumed'] is False and x['pregame_serving_eligible'] is False


def test_missing_immediate_starter_is_unknown_without_skipping():
    w,s,q,r=sources()
    for a in q['rows']:
        if a['team']=='LAR' and a['week']==2:a.update(source_starter_native_id=None,original_source_qb_id=None)
    rehash(q);x=first(run((w,s,q,r)))
    assert [l['continuity'] for l in x['logs']][1:3]==['unknown','unknown']
    assert x['metrics']['same']['known_target_sum']==4
    assert x['metrics']['same']['exact_targets_per_observed_log'] is None


def test_unmapped_other_actor_remains_full_native_budget():
    w,s,q,r=sources()
    for a in w['rows']:
        if a['source_player_id']=='00-0031235':a['player_master_id']=None
    assert first(run((w,s,q,r)))['metrics']['same']['matched_full_native_team_target_sum']==20


def test_missing_target_count_masks_sum_and_budget_not_zero():
    w,s,q,r=sources();r['rows'][2]['raw_row_json']['targets']=None
    w=build(r['rows']);w['provenance']['actual_derived_at']='2026-10-20T04:00:00Z'
    x=first(run((w,s,q,r)));assert x['metrics']['same']['known_target_sum']==4
    assert x['metrics']['same']['exact_target_sum'] is None and x['metrics']['same']['exact_pooled_target_share'] is None


def test_unknown_role_log_cannot_be_silently_excluded():
    w,s,q,r=sources();r['rows'][2]['raw_row_json']['pos']='RB'
    w=build(r['rows']);w['provenance']['actual_derived_at']='2026-10-20T04:00:00Z'
    x=first(run((w,s,q,r)));assert x['metrics']['same']['known_target_sum']==4
    assert x['metrics']['same']['exact_targets_per_observed_log'] is None


def test_positive_missing_weekly_slot_is_unknown_not_dnp():
    w,s,q,r=sources();w['rows']=[a for a in w['rows'] if not(a['week']==3 and a['source_player_id']=='00-0031234')]
    p=dict(season=2026,week=3,team='LAR',source_position='WR',source_player_id='00-0031234',player_master_id=row()['player_master_id'],native_game_id='3',offense_snaps=4)
    x=first(run((w,s,q,r),[p]));assert x['metrics']['changed']['observed_logs']==1
    assert x['metrics']['changed']['exact_targets_per_observed_log'] is None
    assert x['logs'][2]['positive_missing_weekly']


@pytest.mark.parametrize('mutation',['checksum','native','incomplete','clock','pair','rawcount','rawrevision','duplicate'])
def test_scope_source_identity_clock_and_revision_guards(mutation):
    w,s,q,r=sources()
    if mutation=='checksum':q['rows'][0]['team']='DEN'
    if mutation=='native':q['rows'][0]['source_starter_native_id']='00-0099999';rehash(q)
    if mutation=='incomplete':q['rows'].pop();rehash(q)
    if mutation=='clock':q['provenance']['captured_at']='2026-10-21T00:00:00Z'
    if mutation=='pair':q['provenance']['snapshot_id']='other'
    if mutation=='rawcount':r['rows'][0]['raw_row_json']['targets']=5
    if mutation=='rawrevision':r['rows'][0]['ingest_run_id']='changed'
    if mutation=='duplicate':r['rows'].append(deepcopy(r['rows'][0]))
    with pytest.raises(ValueError):run((w,s,q,r))


def test_order_invariant_and_source_known_zero_not_missing():
    a=sources();before=run(a)['semantic_sha256']
    for b in (a[0]['rows'],a[1]['game_rows'],a[2]['rows'],a[3]['rows']):b.reverse()
    rehash(a[2]);assert run(a)['semantic_sha256']==before


def test_positive_missing_native_and_role_stays_unknown_and_masks_team_budget():
    w,s,q,r=sources();p=dict(season=2026,week=3,team='LAR',player_master_id=row()['player_master_id'],native_game_id='3',offense_snaps=4)
    x=run((w,s,q,r),[p]);a=first(x)
    assert len(x['missing_positive_participants'])==1
    assert a['metrics']['changed']['exact_targets_per_observed_log'] is None
    assert all(z['metrics']['changed']['exact_pooled_target_share'] is None for z in x['rows'])


def test_no_serving_or_model_use():
    from backend.app.product_services.qb_continuity_opportunity import require_feature_use
    x=run();assert require_feature_use(x,purpose='offline_descriptive') is x
    with pytest.raises(ValueError):require_feature_use(x,purpose='forecast')


def test_bad_native_actor_keeps_known_team_budget_without_donating_targets():
    w,s,q,r=sources();extra=deepcopy(r['rows'][4]);extra.update(source_id=999,source_player_id=None,player_master_id=None)
    extra['raw_row_json'].update(player_id=None,targets=5);r['rows'].append(extra)
    x=first(run((w,s,q,r)));assert x['metrics']['changed']['exact_targets_per_observed_log']==3
    assert x['metrics']['changed']['exact_pooled_target_share']==3/15


def test_zero_team_budget_is_undefined_share_with_known_zero_actor_mean():
    w,s,q,r=sources()
    for a in r['rows']:a['raw_row_json'].update(targets=0,receptions=0)
    w=build(r['rows']);w['provenance']['actual_derived_at']='2026-10-20T04:00:00Z'
    x=first(run((w,s,q,r)));assert x['changed_minus_same_target_mean']==0
    assert x['metrics']['same']['exact_pooled_target_share'] is None


@pytest.mark.parametrize('field,value',[('native_game_id','wrong'),('offense_snaps',0),('offense_snaps',True),('player_master_id',None)])
def test_missing_positive_native_game_and_participation_proof(field,value):
    p=dict(season=2026,week=3,team='LAR',player_master_id=row()['player_master_id'],native_game_id='3',offense_snaps=4)
    p[field]=value
    with pytest.raises(ValueError):run(missing=[p])
