from copy import deepcopy
import pytest
from backend.app.product_services.forecast_input_clock_age import build_forecast_input_clock_age as build


def fixture():
    index=dict(snapshot_id='id',sha256='sha',source_uri='native',captured_at='2026-10-01T23:45:00Z',observed_at='2026-10-01T23:44:00Z',slate_lock_at='2026-10-02T00:15:00Z')
    parent=dict(version='nws_hourly_precipitation_context_v1',candidate_ids=['G20-M07'],game_id='native_game',kickoff_at='2026-10-02T00:15:00Z',
        original_forecast_generated_at='2026-10-01T22:45:00Z',original_forecast_updated_at='2026-10-01T19:45:00Z',
        native_period=dict(startTime='2026-10-01T20:00:00-04:00',endTime='2026-10-01T21:00:00-04:00'),provenance=dict(original_nws_source_index=index))
    manifest=dict(snapshot_id='id',content_sha256='sha',source_uri='native',dataset='showdown_weather_hourly',
        captured_at=index['captured_at'],observed_at=index['observed_at'],slate_lock_at=index['slate_lock_at'],effective_at=index['captured_at'],observation_basis='capture_clock')
    return parent,manifest


def test_distinct_clock_ages_signed_effective_start_and_kickoff():
    rows=build(*fixture())['reference_points'];first=rows[0]['clock_ages'];last=rows[1]['clock_ages']
    assert first['source_captured_at']['age_seconds']==0
    assert first['forecast_generated_at']['age_seconds']==3600
    assert first['forecast_updated_at']['age_seconds']==14400
    assert first['forecast_valid_start']['age_seconds']==-900
    assert first['forecast_valid_start']['clock_after_reference'] is True
    assert last['forecast_valid_start']['age_seconds']==900
    assert last['source_captured_at']['age_seconds']==1800
    assert last['provider_issued_at']['age_seconds'] is None


@pytest.mark.parametrize('field',[ 'original_forecast_generated_at','original_forecast_updated_at'])
def test_missing_or_naive_publication_clock_unknown_not_capture_fill(field):
    for value in (None,'2026-10-01T22:45:00'):
        parent,manifest=fixture();parent[field]=value
        key='forecast_generated_at' if field.endswith('generated_at') else 'forecast_updated_at'
        assert build(parent,manifest)['reference_points'][0]['clock_ages'][key]['age_seconds'] is None


def test_missing_period_never_uses_snapshot_capture_effective_time():
    parent,manifest=fixture();parent['native_period']=None
    ages=build(parent,manifest)['reference_points'][0]['clock_ages']
    assert ages['snapshot_effective_at']['age_seconds']==0 and ages['forecast_valid_start']['age_seconds'] is None


def test_negative_generated_age_exposes_future_clock_not_zero():
    parent,manifest=fixture();parent['original_forecast_generated_at']='2026-10-02T00:00:00Z'
    result=build(parent,manifest)['reference_points'][0]['clock_ages']['forecast_generated_at']
    assert result['age_seconds']==-900 and result['clock_after_reference'] is True


def test_equivalent_offsets_bind_same_original_instant():
    parent,manifest=fixture();manifest['captured_at']='2026-10-01T19:45:00-04:00'
    assert build(parent,manifest)['reference_points'][0]['clock_ages']['source_captured_at']['age_seconds']==0


@pytest.mark.parametrize('field,value',[('captured_at','2026-10-01T23:46:00Z'),('snapshot_id','other'),('content_sha256','other'),('source_uri','other')])
def test_changed_clock_or_source_identity_rejected(field,value):
    parent,manifest=fixture();manifest[field]=value
    with pytest.raises(ValueError):build(parent,manifest)


def test_empty_reference_unknown_and_provider_issue_remains_unknown():
    parent,manifest=fixture();parent['kickoff_at']=None
    last=build(parent,manifest)['reference_points'][1]
    assert last['reference_at'] is None and all(v['age_seconds'] is None for v in last['clock_ages'].values())
