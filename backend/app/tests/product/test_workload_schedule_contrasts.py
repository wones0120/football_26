from copy import deepcopy
import pytest
from backend.app.product_services.workload_schedule_contrasts import build_workload_schedule_contrasts
from backend.app.tests.product.test_workload_venue_splits import sources


def fixture():
    w,s=sources()
    for g in s['game_rows']:
        rest=6 if g['week']%2 else 7;g['source_roof']='closed' if g['week']%2 else 'open'
        g['team_rows']=[dict(team=t,metrics={'G20-M09':dict(value=rest)}) for t in (g['home_team'],g['away_team'])]
        for r in g['team_rows']:
            if r['team']=='LA':r['team']='LAR'
    return w,s


def run(w=None,s=None):
    a,b=fixture();return build_workload_schedule_contrasts(w or a,s or b,before_period=202607)


def test_declared_threshold_roof_and_official_counts():
    r=run()['rows'][0]
    for mid in ('G21-M05','G21-M07'):
        m=r['metrics'][mid]['channels']['rush_attempts']
        assert m['positive']['observed_logs']==2 and m['negative']['observed_logs']==2
        assert m['positive_minus_negative']==-1
    assert run()['pregame_serving_eligible'] is False


@pytest.mark.parametrize('field',['rest','roof'])
def test_unknown_context_masks_comparison_not_completecase_skip(field):
    w,s=fixture()
    if field=='rest':s['game_rows'][0]['team_rows'][0]['metrics']['G20-M09']['value']=None
    else:s['game_rows'][0]['source_roof']=None
    mid='G21-M05' if field=='rest' else 'G21-M07'
    m=run(w,s)['rows'][0]['metrics'][mid]
    assert m['unknown_context_logs']==1 and m['channels']['rush_attempts']['positive_minus_negative'] is None


def test_missing_exposure_and_single_cohort_not_zero():
    w,s=fixture();w['rows'][0]['metrics']['G07-M01']['denominator']=None
    assert run(w,s)['rows'][0]['metrics']['G21-M05']['channels']['rush_attempts']['positive_minus_negative'] is None
    w,s=fixture()
    for g in s['game_rows']:g['source_roof']='dome'
    assert run(w,s)['rows'][0]['metrics']['G21-M07']['channels']['rush_attempts']['negative']['per_observed_log'] is None


@pytest.mark.parametrize('rest',[-1,1.5,float('inf'),True])
def test_invalid_known_rest_rejected(rest):
    w,s=fixture();s['game_rows'][0]['team_rows'][0]['metrics']['G20-M09']['value']=rest
    with pytest.raises(ValueError):run(w,s)


def test_source_provenance_and_recapture_stability():
    w,s=fixture();expected=run(w,s)['semantic_sha256']
    for r in w['rows']:r['source_ref']['imported_at']='2026-10-20T00:00:00Z'
    assert run(w,s)['semantic_sha256']==expected
    assert run(w,s)['rows'][0]['logs'][0]['source_ref']==w['rows'][0]['source_ref']
