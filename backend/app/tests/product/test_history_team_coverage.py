from copy import deepcopy
import pytest
from backend.app.tests.product.test_workload_starting_qb_context import sources
from backend.app.product_services.history_team_coverage import build_history_team_coverage,require_feature_use


def source():
    w,_,_=sources()
    for r in w['rows']:
        r['team']='LAR' if r['week']<3 else 'SF'
        r['metrics']['G07-M01']['denominator']=r['week']
    return w


def run(w=None,**kwargs):return build_history_team_coverage(w or source(),before_period=202607,**kwargs)


def test_strict_prior_same_team_and_other_team_exposure_fraction():
    x=run();r=x['rows'][-1];m=r['metrics']['rush_attempts']
    assert r['week']==4 and r['same_team_log_fraction']==pytest.approx(1/3)
    assert m['same_team']['exact_exposure_sum']==3 and m['other_team_observed']['exact_exposure_sum']==3
    assert m['same_team_exposure_fraction']==.5
    assert x['rows'][0]['same_team_log_fraction'] is None and x['forecast'] is None


def test_current_target_outcome_does_not_enter_own_history_feature():
    w=source();old=run(w)['rows'][-1];w['rows'][-1]['metrics']['G07-M01']['denominator']=999
    assert run(w)['rows'][-1]==old


def test_unknown_team_or_count_masks_no_latest_team_guess():
    w=source();w['rows'][0]['team']=None;r=run(w)['rows'][-1]
    assert r['same_team_log_fraction'] is None and r['unknown_team_logs']==1
    assert r['metrics']['rush_attempts']['same_team_exposure_fraction'] is None
    assert r['metrics']['rush_attempts']['same_team']['known_exposure_sum']==3
    assert r['metrics']['rush_attempts']['other_team_observed']['known_exposure_sum']==2
    assert r['same_team_prior_logs']==r['other_team_prior_logs']==1
    assert r['metrics']['rush_attempts']['same_team']['exact_exposure_sum'] is None
    w=source();w['rows'][0]['metrics']['G07-M01']['denominator']=None
    m=run(w)['rows'][-1]['metrics']['rush_attempts'];assert m['same_team_exposure_fraction'] is None and m['other_team_observed']['unknown_exposure_logs']==1


def test_zero_exposure_denominator_undefined_not_zero_same_team():
    w=source()
    for r in w['rows']:r['metrics']['G07-M01']['denominator']=0
    assert run(w)['rows'][-1]['metrics']['rush_attempts']['same_team_exposure_fraction'] is None


def test_crossseason_history_explicit_and_window_declared():
    w=source();w['rows'][0].update(season=2025,week=18)
    r=run(w,last_n=2)['rows'][-1]
    assert len(r['prior_native_periods'])==2 and r['prior_native_periods'][0][1]==2
    assert run(w)['rows'][1]['prior_native_periods'][0][0]==2025


@pytest.mark.parametrize('kind',['duplicate','future','canonical','negative','same_period_tie'])
def test_identity_count_and_chronology_guards(kind):
    w=source()
    if kind=='duplicate':w['rows'].append(deepcopy(w['rows'][0]))
    if kind=='future':w['rows'][0]['week']=7
    if kind=='canonical':w['rows'][0]['player_master_id']='name'
    if kind=='negative':w['rows'][0]['metrics']['G07-M01']['denominator']=-1
    if kind=='same_period_tie':r=deepcopy(w['rows'][0]);r['team']='BUF';w['rows'].append(r)
    with pytest.raises(ValueError):run(w,last_n=1)


def test_native_unmapped_history_retained_and_clocks_outside_semantics():
    w=source()
    for r in w['rows']:r['player_master_id']=None
    a=run(w);assert all(r['player_master_id'] is None for r in a['rows'])
    w['rows'].reverse();w['provenance']['captured_at']='recaptured'
    assert run(w)['semantic_sha256']==a['semantic_sha256']
    assert require_feature_use(a,purpose='offline_descriptive') is a
    with pytest.raises(ValueError):require_feature_use(a,purpose='model')


def test_compact_scope_arrays_and_single_unit_definition_keep_exact_parent_periods():
    x=run();r=x['rows'][-1]
    assert x['prior_native_period_fields']==['season','week','team']
    assert r['prior_native_periods']==[[2026,1,'LAR'],[2026,2,'LAR'],[2026,3,'SF']]
    assert r['same_team_prior_logs']==1 and r['other_team_prior_logs']==2
    assert 'unit' not in r['metrics']['targets']
    assert x['exposure_fraction_unit']=='fraction_of_observed_prior_official_opportunities'
