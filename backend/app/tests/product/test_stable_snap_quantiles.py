from copy import deepcopy
import pytest
from backend.app.product_services.stable_snap_quantiles import build_stable_snap_quantiles,_qualification,normalize_stability_snaps
from backend.app.product_services.weekly_effectiveness_catalog_features import VERSION
from backend.app.product_services.recent_snap_features import VERSION as SNAP_VERSION

PID='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';CUTOFF='2026-10-20T09:00:00Z'


def sources():
    weekly=dict(version=VERSION,before_period=202607,pregame_serving_eligible=False,provenance=dict(actual_derived_at='2026-10-20T03:00:00Z'),rows=[])
    from backend.app.product_services.schedule_context_features import VERSION as SCHEDULE_VERSION
    schedule=dict(version=SCHEDULE_VERSION,pregame_serving_eligible=False,provenance={},game_rows=[])
    snaps=dict(version='source_native_snap_stability_inputs_v1',before_period=202606,pregame_serving_eligible=False,provenance={},identity_review_requests=[],rows=[])
    for week in range(1,6):
        gid=f'2026_{week:02}_SF_LAR'
        schedule['game_rows'].append(dict(game_id=gid,season=2026,week=week,game_type='REG',away_team='SF',home_team='LAR'))
        weekly['rows'].append(dict(season=2026,week=week,team='SF',native_game_id=gid,player_master_id=PID,
            metrics={'G09-M01':dict(denominator=0 if week==4 else 10),'G07-M01':dict(denominator=week)},source_ref=dict(row=week)))
        snaps['rows'].append(dict(season=2026,week=week,team='SF',native_game_id=gid,pfr_player_id='TestPl01',player_master_id=PID,
            offense_snaps=40,offense_fraction=.7,source_position='RB',source_records=[dict(id=week)]))
    return weekly,schedule,snaps


def run(src=None):return build_stable_snap_quantiles(*(src or sources()),before_period=202606,cutoff=CUTOFF)


def metric(x,mid='X02-M06'):return x['rows'][0]['metrics'][mid]


def test_empirical_linear_q90_and_prior3_only():
    m=metric(run());assert m['known_response_counts']==[0,10] and m['exact_conditional_q90']==9
    assert m['slots'][0]['prior_native_game_ids']==['2026_01_SF_LAR','2026_02_SF_LAR','2026_03_SF_LAR']
    assert metric(run(),'X02-M07')['exact_conditional_q90']==4.9


def test_current_outcome_does_not_qualify_its_own_prior_role():
    w,s,p=sources();p['rows'][3]['offense_fraction']=0
    m=metric(run((w,s,p)));assert m['slots'][0]['qualified'] is True
    assert m['slots'][1]['qualified'] is False
    w['rows'][3]['metrics']['G09-M01']['denominator']=999
    assert metric(run((w,s,p)))['slots'][0]['qualified'] is True


def test_missing_immediate_game_is_unknown_no_skip():
    w,s,p=sources();p['rows']=[r for r in p['rows'] if r['week']!=2]
    m=metric(run((w,s,p)));assert m['unknown_qualification_games']==2 and m['exact_conditional_q90'] is None


def test_missing_qualified_response_not_zero_or_complete_case():
    w,s,p=sources();w['rows']=[r for r in w['rows'] if r['week']!=4]
    m=metric(run((w,s,p)));assert m['known_sample_q90']==10 and m['missing_qualified_responses']==1
    assert m['exact_conditional_q90'] is None


def test_known_unstable_can_exclude_despite_other_missing_prior():
    p=sources()[2]['rows'][:3];p[1]=None;p[0]['offense_fraction']=.59
    assert _qualification(p,{'RB'}) is False


@pytest.mark.parametrize('field,value',[('offense_snaps',None),('offense_fraction',None),('source_position',None)])
def test_unknown_prior_condition_masks_full_quantile(field,value):
    w,s,p=sources();p['rows'][1][field]=value;m=metric(run((w,s,p)))
    assert m['unknown_qualification_games']==2 and m['exact_conditional_q90'] is None


def test_same_source_position_and_role_applicability():
    w,s,p=sources();p['rows'][1]['source_position']='WR';assert metric(run((w,s,p)))['qualified_target_games']==0
    w,s,p=sources()
    for r in p['rows']:r['source_position']='WR'
    x=run((w,s,p));assert metric(x)['exact_conditional_q90']==9
    assert metric(x,'X02-M07')['qualified_target_games']==0


def test_fraction_range_boundaries_and_known_zero_snaps():
    p=sources()[2]['rows'][:3]
    for r,v in zip(p,[.6,.65,.7]):r['offense_fraction']=v
    assert _qualification(p,{'RB'}) is True
    p[2]['offense_fraction']=.71;assert _qualification(p,{'RB'}) is False
    p[2]['offense_fraction']=.7;p[0]['offense_snaps']=0;assert _qualification(p,{'RB'}) is False


def test_unresolved_native_identity_not_attached_by_name():
    w,s,p=sources()
    for r in p['rows']:r['player_master_id']=None
    x=run((w,s,p));assert x['rows'][0]['player_master_id'] is None
    assert metric(x)['missing_qualified_responses']==2 and metric(x)['exact_conditional_q90'] is None


def test_future_weekly_rows_cannot_change_quantiles():
    w,s,p=sources();a=run((w,s,p))['semantic_sha256'];extra=deepcopy(w['rows'][-1]);extra.update(week=6,native_game_id='2026_06_SF_LAR');extra['metrics']['G09-M01']['denominator']=9999;w['rows'].append(extra)
    assert run((w,s,p))['semantic_sha256']==a


@pytest.mark.parametrize('change',['duplicate_snap','wrong_snap_game','wrong_weekly_game','duplicate_schedule','future_clock'])
def test_native_scope_and_clock_guards(change):
    w,s,p=sources()
    if change=='duplicate_snap':p['rows'].append(deepcopy(p['rows'][0]))
    if change=='wrong_snap_game':p['rows'][0]['native_game_id']='wrong'
    if change=='wrong_weekly_game':w['rows'][0]['native_game_id']='wrong'
    if change=='duplicate_schedule':s['game_rows'].append(deepcopy(s['game_rows'][0]))
    if change=='future_clock':w['provenance']['actual_derived_at']='2026-10-21T00:00:00Z'
    with pytest.raises(ValueError):run((w,s,p))


def test_normalizer_native_alias_scope_equivalent_revision_and_share_units():
    r=dict(source_row_id=1,ingest_run_id='a',created_at='2026-10-01T00:00:00Z',raw=dict(season=2026,week=1,game_type='REG',team='SF',game_id='2026_01_SF_LAR',pfr_player_id='TestPl01',offense_snaps=50,offense_pct=.8,position='RB'))
    v=dict(version=SNAP_VERSION,before_period=202606,actor_trends=[dict(pfr_player_id='TestPl01',team='SF',player_master_id=PID)],provenance={},identity_review_requests=[])
    r2=deepcopy(r);r2.update(source_row_id=2,ingest_run_id='b')
    x=normalize_stability_snaps(dict(rows=[r,r2]),v,before_period=202606)
    assert len(x['rows'])==1 and len(x['rows'][0]['source_records'])==2 and x['rows'][0]['offense_fraction']==.8
    r['raw']['offense_pct']=80;x=normalize_stability_snaps(dict(rows=[r]),v,before_period=202606)
    assert x['rows'][0]['offense_fraction'] is None


def test_nonserving_quantile_and_normalized_pct_guard():
    from backend.app.product_services.stable_snap_quantiles import require_feature_use
    x=run();assert require_feature_use(x,purpose='offline_descriptive') is x
    with pytest.raises(ValueError):require_feature_use(x,purpose='forecast')
    w,s,p=sources();p['rows'][0]['offense_fraction']=80
    with pytest.raises(ValueError):run((w,s,p))
