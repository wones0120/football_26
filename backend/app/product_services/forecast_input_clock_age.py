"""Source-clock age diagnostics over a bound forecast input, not model eligibility."""
from datetime import datetime,UTC
from .evaluation_record import digest

VERSION='forecast_input_clock_age_v1'


def _time(value):
    try:
        result=datetime.fromisoformat(value.replace('Z','+00:00')) if isinstance(value,str) else value
        return result.astimezone(UTC) if isinstance(result,datetime) and result.tzinfo is not None else None
    except (ValueError,TypeError):return None


def build_forecast_input_clock_age(parent,manifest):
    if parent.get('version')!='nws_hourly_precipitation_context_v1' or parent.get('candidate_ids')!=['G20-M07']:
        raise ValueError('Bound reviewed NWS forecast input required')
    index=parent['provenance']['original_nws_source_index']
    if (manifest.get('snapshot_id')!=index.get('snapshot_id') or manifest.get('content_sha256')!=index.get('sha256')
            or manifest.get('source_uri')!=index.get('source_uri') or manifest.get('dataset')!='showdown_weather_hourly'):
        raise ValueError('Original source manifest/input binding differs')
    for field in ('captured_at','observed_at','slate_lock_at'):
        if _time(manifest.get(field))!=_time(index.get(field)):raise ValueError('Original source clock binding differs')
    period=parent.get('native_period') or {}
    clocks=dict(forecast_generated_at=parent.get('original_forecast_generated_at'),
        forecast_updated_at=parent.get('original_forecast_updated_at'),
        source_observed_at=index.get('observed_at'),source_captured_at=index.get('captured_at'),
        snapshot_effective_at=manifest.get('effective_at'),forecast_valid_start=period.get('startTime'),
        forecast_valid_end=period.get('endTime'),provider_issued_at=None)
    rows=[]
    for label,reference in (('original_source_receipt_cutoff',index.get('captured_at')),('measured_game_kickoff',parent.get('kickoff_at'))):
        at=_time(reference);ages={}
        for name,raw in clocks.items():
            clock=_time(raw);seconds=(at-clock).total_seconds() if at is not None and clock is not None else None
            ages[name]=dict(original_clock=raw,age_seconds=seconds,clock_after_reference=seconds<0 if seconds is not None else None)
        rows.append(dict(reference_kind=label,reference_at=at.isoformat() if at else None,clock_ages=ages))
    basis=dict(version=VERSION,candidate_ids=['X08-M05'],source_snapshot_id=index.get('snapshot_id'),
        game_id=parent['game_id'],reference_points=rows,age_definition='signed reference instant minus source clock, in seconds',
        snapshot_effective_basis=manifest.get('observation_basis'),
        snapshot_effective_limitation='Capture-clock effective_at is not substituted for forecast valid_start or provider issue time',
        provider_issue_clock_status='UNKNOWN: no distinct provider-issued-at field in bound NWS input',
        original_vs_revised_binding='Original forecast clocks are retained; native schedule and venue attribution is later revised evidence')
    return dict(**basis,semantic_sha256=digest(basis),model_consumed=False,optimizer_consumed=False,
        evidence_use='source_scoped_forecast_input_clock_diagnostic_not_model_staleness_or_eligibility',
        limitations=['Negative ages expose later/future clocks and are not clamped to zero',
            'No all-input original-pregame proof, upstream issue-time imputation, forecast skill or calibration claim'])
