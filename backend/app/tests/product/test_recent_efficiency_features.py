from copy import deepcopy
import pytest
from backend.app.product_services.recent_efficiency_features import build_recent_efficiency
from backend.app.tests.product.test_weekly_effectiveness_catalog_features import build, row


def source():
    rows = []
    for week in range(1, 5):
        r = row(); r['week'] = week
        r['raw_row_json']['week'] = week
        r['source_id'] = week
        r['raw_row_json']['carries'] = week
        r['raw_row_json']['rushing_yards'] = -week if week < 4 else 8
        rows.append(r)
    return build(rows)


def run(s=None):
    return build_recent_efficiency(s or source(), before_period=202607)


def test_signed_pooled_prior_and_separate_units():
    s = source(); result = run(s); m = result['rows'][0]['metrics']['G07-M01']
    assert (m['reference_numerator'], m['reference_denominator'], m['reference_value'], m['change']) == (-6, 6, -1, 3)
    assert result['forecast'] is None and result['pregame_serving_eligible'] is False
    assert result['rows'][0]['source_refs'][0] == s['rows'][0]['source_ref']


def test_missing_latest_not_last_positive_or_zero():
    s = source(); other = deepcopy(s['rows'][-1]); other['source_player_id'] = '00-9999999'; other['player_master_id'] = None
    s['rows'][-1] = other
    r = next(r for r in run(s)['rows'] if r['source_player_id'] != '00-9999999')
    assert r['metrics']['G07-M01']['latest_value'] is None
    assert r['metrics']['G07-M01']['change'] is None


def test_missing_reference_zero_exposure_and_known_zero():
    s = source(); s['rows'][0]['metrics']['G07-M01'] = dict(value=None, numerator=0, denominator=0)
    assert run(s)['rows'][0]['metrics']['G07-M01']['reference_denominator'] == 5
    s['rows'][0]['metrics']['G07-M01']['numerator'] = None
    assert run(s)['rows'][0]['metrics']['G07-M01']['reference_value'] is None


def test_short_window_undefined_and_no_season_team_crossing():
    s = source(); s['rows'][0]['season'] = 2024
    assert all(r['metrics']['G07-M01']['change'] is None for r in run(s)['rows'])
    s = source(); s['rows'][0]['team'] = 'SF'
    assert all(r['metrics']['G07-M01']['change'] is None for r in run(s)['rows'])


@pytest.mark.parametrize('mutation', ['future', 'duplicate', 'ratio', 'negative', 'identity', 'serving'])
def test_source_boundary_rejects(mutation):
    s = source()
    if mutation == 'future': s['rows'][0].update(week=7, season=2026)
    if mutation == 'duplicate': s['rows'].append(deepcopy(s['rows'][0]))
    if mutation == 'ratio': s['rows'][0]['metrics']['G07-M01']['value'] = 88
    if mutation == 'negative': s['rows'][0]['metrics']['G07-M01']['denominator'] = -1
    if mutation == 'identity': s['rows'][0]['player_master_id'] = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
    if mutation == 'serving': s['pregame_serving_eligible'] = True
    with pytest.raises(ValueError): run(s)


def test_order_and_capture_clocks_do_not_change_measurement():
    s = source(); expected = run(s)['semantic_sha256']; s['rows'].reverse()
    for r in s['rows']: r['source_ref']['imported_at'] = '2026-10-20T04:00:00Z'
    assert run(s)['semantic_sha256'] == expected


def test_nonQB_missing_QB_channels_remain_unknown():
    s = source()
    for r in s['rows']:
        for k in list(r['metrics']):
            if k.startswith('G04'): del r['metrics'][k]
    assert run(s)['rows'][0]['metrics']['G04-M01']['change'] is None


def test_pooled_exposure_not_mean_of_ratios_and_unknown_team_masks_actor():
    s = source(); s['rows'][0]['metrics']['G07-M01'] = dict(value=10, numerator=10, denominator=1)
    m = run(s)['rows'][0]['metrics']['G07-M01']
    assert m['reference_value'] == 5/6
    unknown = deepcopy(s['rows'][0]); unknown['week'] = 5; unknown['team'] = None
    s['rows'].append(unknown)
    assert run(s)['rows'][0]['native_team_scope_unknown']
    assert run(s)['rows'][0]['metrics']['G07-M01']['change'] is None
