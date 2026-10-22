from copy import deepcopy
import pytest
from research.game_progression_pilot_20261020.alternative_clock_sources.assess import bind_event,plays,schema_counts,pdf_mentions

def fixture():
    return dict(header=dict(id='401547477',competitions=[dict(date='2023-10-15T17:00Z',competitors=[
        dict(homeAway='home',team=dict(id='34',abbreviation='HOU')),
        dict(homeAway='away',team=dict(id='18',abbreviation='NO'))])]),
        drives=dict(previous=[dict(plays=[dict(id='espn-play',clock=dict(displayValue='1:09'),
            start=dict(down=1,distance=10),end=dict(down=2,distance=10),wallclock='2023-10-15T18:21:02Z')])]))

def test_native_event_binding_and_play_schema_preserve_namespace_and_missing_clock():
    source=fixture();before=deepcopy(source);event=bind_event(source,'401547477','2023-10-15','HOU','NO');rows=plays(source)
    report=schema_counts(rows)
    assert event['teams'][0]['native_team_id']=='34'and rows[0]['id']=='espn-play'
    assert report['counts']['plays']==1 and not report['counts'].get('end_clock_field_candidates')
    assert report['end_key_counts']==dict(down=1,distance=1)
    assert report['supported_play_end_clock_records']==report['supported_restart_enforcement_records']==0
    assert source==before

@pytest.mark.parametrize('event,date,home,away',[
    ('different','2023-10-15','HOU','NO'),('401547477','2023-10-16','HOU','NO'),('401547477','2023-10-15','NO','HOU')])
def test_wrong_game_date_or_home_away_is_not_attached(event,date,home,away):
    with pytest.raises(ValueError):bind_event(fixture(),event,date,home,away)

def test_duplicate_play_ids_or_live_drive_are_explicit_failures():
    source=fixture();source['drives']['previous'][0]['plays']*=2
    with pytest.raises(ValueError):plays(source)
    source=fixture();source['drives']['current']={'id':'live'}
    with pytest.raises(ValueError):plays(source)

def test_even_named_clock_or_restart_fields_need_semantic_qualification():
    rows=[dict(id='p',end=dict(clock=dict(displayValue='00:45')),restart='snap')]
    report=schema_counts(rows)
    assert report['counts']['end_clock_field_candidates']==1 and report['counts']['explicit_control_field_candidates']==1
    assert report['supported_play_end_clock_records']==report['supported_restart_enforcement_records']==0

def test_gamebook_runoff_and_clock_text_are_mentions_not_enforcement_values():
    assert pdf_mentions('10 second runoff by rule.')==['runoff']
    assert 'runoff'in pdf_mentions('No 10-second runoff was applied.')
    assert pdf_mentions('Ordinary play description.')==[]
