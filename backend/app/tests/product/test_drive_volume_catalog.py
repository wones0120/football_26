from copy import deepcopy
import pytest
from backend.app.product_services.drive_volume_catalog import build_drive_volume_catalog
from backend.app.product_services.environment_context_evidence import DEFINITIONS

def source(**extra):
    row=dict(game_id='2026_01_WAS_SF',team='WAS',season=2026,week=1,
        native_drive_ids=['1','9'],known_offensive_snaps=6,known_drive_snaps=6,
        unknown_drive_snap_ids=0,unknown_snap_eligibility=0)
    row.update(extra)
    return dict(version='environment_context_evidence_v1',before_period=202606,forecast=None,
        definitions=deepcopy(DEFINITIONS),semantic_measurements_sha256='source',game_rows=[row])

def build(c=None):return build_drive_volume_catalog(c or source(),before_period=202606)

def test_distinct_native_drives_not_maximum_and_no_fake_complete_possessions():
    r=build();m=r['game_rows'][0]['metrics']
    assert m['G01-M02']['value']==3 and m['G01-M02']['observed_native_drives']==2
    assert m['G01-M03']['value'] is None and m['G01-M03']['observed_offensive_native_drive_lower_bound']==2
    assert r['pregame_serving_eligible'] is False and r['forecast'] is None

@pytest.mark.parametrize('extra',[dict(unknown_snap_eligibility=1),dict(known_offensive_snaps=7,unknown_drive_snap_ids=1)])
def test_unknown_exposure_masks_exact_not_known_sample(extra):
    m=build(source(**extra))['game_rows'][0]['metrics']['G01-M02']
    assert m['value'] is None and m['known_attached_sample_mean']==3

def test_empty_observed_log_is_undefined_ratio_not_missing_game_zero():
    m=build(source(native_drive_ids=[],known_offensive_snaps=0,known_drive_snaps=0))['game_rows'][0]['metrics']
    assert m['G01-M02']['value'] is None and m['G01-M03']['value'] is None
    assert m['G01-M03']['observed_offensive_native_drive_lower_bound']==0

@pytest.mark.parametrize('extra',[dict(native_drive_ids=['1','1.0']),dict(native_drive_ids=['a']),dict(known_offensive_snaps=7),dict(known_drive_snaps=1,known_offensive_snaps=1),dict(native_drive_ids=[],known_drive_snaps=6)])
def test_native_accounting_contradictions_reject(extra):
    with pytest.raises(ValueError):build(source(**extra))

def test_pool_summed_snaps_over_summed_drives_and_row_order_invariance():
    c=source();r=deepcopy(c['game_rows'][0]);r.update(game_id='2026_02_WAS_SF',week=2,native_drive_ids=['1'],known_offensive_snaps=9,known_drive_snaps=9);c['game_rows'].append(r)
    a=build(c);assert a['team_windows'][0]['metrics']['G01-M02']['value']==5
    c['game_rows'].reverse();assert build(c)['semantic_sha256']==a['semantic_sha256']

@pytest.mark.parametrize('extra',[dict(week=6,game_id='2026_06_WAS_SF'),dict(team='GB'),dict(game_id='2025_01_WAS_SF')])
def test_prior_native_scope_required(extra):
    with pytest.raises(ValueError):build(source(**extra))

def test_prior_season_rows_retained_but_not_current_window():
    c=source();r=deepcopy(c['game_rows'][0]);r.update(season=2025,game_id='2025_01_WAS_SF');c['game_rows'].append(r)
    a=build(c);assert len(a['game_rows'])==2 and a['team_windows'][0]['observed_game_ids']==['2026_01_WAS_SF']
