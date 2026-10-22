from copy import deepcopy
import pytest
from backend.app.tests.product.test_game_state_reconstruction import row
from research.game_progression_pilot_20261020.clock_gap_investigation.probe import mentions,field_format

@pytest.mark.parametrize('text,kind',[
    ('10 second runoff by rule.','runoff'),
    ('10-second run-off declined.','runoff'),
    ('The clock will start on the snap.','restart'),
    ('The clock will restart when ready for play.','restart'),
    ('The game clock reset to when the ball was snapped.','reset_or_correction'),
    ('The clock was adjusted to 00:15.','reset_or_correction'),
])
def test_source_mentions_retain_spans_without_inventing_adjudication(text,kind):
    raw=row(desc=text);before=deepcopy(raw);found=mentions(raw)
    assert any(x['kind']==kind for x in found)
    for x in found:
        assert text[slice(*x['span'])]==x['matched_text']
        assert x['play_end_game_clock']is None and x['runoff_seconds']is None and x['restart_policy']is None
        assert not x['enforcement_proven']and x['evidence_status']=='NARRATIVE_CANDIDATE_REQUIRES_ADJUDICATION'
    assert raw==before

def test_negated_runoff_and_reversed_ruling_remain_unadjudicated_candidates():
    raw=row(desc='No 10-second runoff. The play was REVERSED.',replay_or_challenge=1,replay_or_challenge_result='reversed')
    found=mentions(raw)
    assert len(found)==1 and not found[0]['source_finality_qualified']
    assert found[0]['runoff_seconds']is None and not found[0]['enforcement_proven']

@pytest.mark.parametrize('description',[None,17,'Ordinary rush for four yards.'])
def test_absent_narrative_is_not_a_clock_signal(description):
    assert mentions(row(desc=description))==[]

@pytest.mark.parametrize('field,value,expected',[
    ('end_clock_time','2023-09-10T17:03:25.203Z','WALL_TIMESTAMP'),
    ('time_of_day','2023-09-10T17:03:20Z','WALL_TIMESTAMP'),
    ('end_clock_time','01:03','QUARTER_CLOCK_LIKE_UNVALIDATED'),
    ('play_clock','0','REPORTED_ZERO_NOT_GAME_CLOCK'),
    ('play_clock',35,'REPORTED_VALUE_NOT_PLAY_END_PROOF'),
    ('end_clock_time',None,'MISSING'),
])
def test_clock_fields_are_classified_without_reinterpreting_timestamps(field,value,expected):
    assert field_format(field,value)==expected
