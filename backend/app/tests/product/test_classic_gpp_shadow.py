from copy import deepcopy
from backend.app.product_services.classic_gpp_shadow import freeze_shadow
from backend.app.tests.product.test_gpp_recommendation import lineup


def shadow(candidates):
    return freeze_shadow(candidates,run_id='run',season=2026,week=5,slate='SUNDAY_MAIN',
        contest_format='classic',projection_run_id='projection',data_cutoff_at='2026-10-10T12:00:00Z')


def test_fixed_mean_band_and_preserved_inputs():
    rows=[lineup(0,10,20),lineup(20,9.9,25),lineup(40,9,40)]
    before=deepcopy(rows);r=shadow(rows)
    assert r['baseline']['lineup_number']==1
    assert r['challenger']['lineup_number']==2
    assert r['eligible_count']==2 and rows==before


def test_missing_upside_abstains_without_cherry_picking():
    a,b=lineup(),lineup(20);del b[0]['p90']
    assert shadow([a,b])['challenger'] is None


def test_invalid_candidate_cannot_win():
    a=lineup(20,10,100);a[0]['salary']=60000
    r=shadow([lineup(),a])
    assert r['challenger']['lineup_number']==1


def test_same_candidate_set_canonical_tie_and_outcomes_do_not_change_choice():
    a,b=lineup(),lineup(20)
    r=shadow([a,b]);s=shadow([b,a])
    assert r['challenger']['candidate_id']==s['challenger']['candidate_id']
    a[0]['actual_points']=999
    assert shadow([a,b])['challenger']['candidate_id']==r['challenger']['candidate_id']
