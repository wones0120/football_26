from copy import deepcopy
import pytest
from backend.app.product_services.return_touchdown_components import build_return_touchdown_components,EXTRA
from backend.app.tests.product.test_fumble_event_components import play,fumble,A,B,C,D

def row(number=1,**changes):
    r=play(number)
    r.update({k:0 for k in EXTRA});r.update(td_team=None,return_team=None,interception_player_id=None,kickoff_returner_player_id=None,punt_returner_player_id=None)
    return r|changes

def build(records):return build_return_touchdown_components(records,before_period=202606,source=dict(snapshot_id='snapshot',content_sha256='a'*64))
def team(result,name='MIA'):return next(r for r in result['team_game_rows']if r['team']==name)

def test_interception_possession_and_realized_touchdown_are_separate():
    r=build([row(interception=1,interception_player_id=A,play_type_nfl='INTERCEPTION',return_team='MIA')])
    c=team(r)['channels']['interception_possessions']
    assert c['exact_exposures']==1 and c['exact_matched_return_TDs']==0
    assert team(r)['exact_physical_return_TDs']==0
    r=build([row(interception=1,interception_player_id=A,play_type_nfl='INTERCEPTION',return_team='MIA',return_touchdown=1,touchdown=1,td_team='MIA')])
    assert team(r)['exact_physical_return_TDs']==1
    assert team(r)['channels']['interception_possessions']['observed_TD_per_exposure']==1

def test_same_td_overlapping_int_and_fumble_channels_never_double_physical_td():
    r=row(interception=1,interception_player_id=A,play_type_nfl='INTERCEPTION',return_team='MIA',return_touchdown=1,touchdown=1,td_team='BUF',
        fumble=1,fumble_lost=1,fumbled_1_team='MIA',fumbled_1_player_id=A,fumble_recovery_1_team='BUF',fumble_recovery_1_player_id=B)
    out=build([r]);assert team(out,'BUF')['exact_physical_return_TDs']==1
    assert team(out)['channels']['interception_possessions']['exact_exposures']==1
    assert team(out,'BUF')['channels']['opponent_fumble_recoveries']['exact_exposures']==1
    assert sum(t['known_physical_return_TDs']for t in out['team_game_rows'])==1

def kick(number=1,kind='kickoff',**changes):
    return row(number,play_type=kind,play_type_nfl='KICK_OFF'if kind=='kickoff'else 'PUNT',pass_attempt=0,qb_dropback=0,
        **{('kickoff_attempt'if kind=='kickoff'else 'punt_attempt'):1,('kickoff_returner_player_id'if kind=='kickoff'else 'punt_returner_player_id'):A},return_team='MIA')|changes

@pytest.mark.parametrize('kind',['kickoff','punt'])
def test_actual_return_including_zero_negative_yards_not_all_attempts(kind):
    r=build([kick(kind=kind,return_yards=0),kick(2,kind,return_yards=-3),kick(3,kind,touchback=1,**{('kickoff_returner_player_id'if kind=='kickoff'else 'punt_returner_player_id'):None})])
    c=team(r)['channels'][kind+'_actual_returns'];assert c['exact_exposures']==2
    assert team(r)['exact_physical_return_TDs']==0

@pytest.mark.parametrize('change',[dict(kickoff_returner_player_id=None),dict(kickoff_fair_catch=None),dict(return_team=None),dict(own_kickoff_recovery=1)])
def test_unknown_return_membership_never_zero_imputed(change):
    c=team(build([kick(**change)]))['channels']['kickoff_actual_returns']
    assert c['exact_exposures']is None and c['known_exposures']==0

def test_blocked_punt_is_explicit_gap_not_ordinary_return_proof():
    r=build([kick(kind='punt',punt_blocked=1)]);c=team(r)['channels']['punt_actual_returns']
    assert c['exact_exposures']is None and r['mechanism_scope_gaps']['blocked_punt_mechanism_events']==1

@pytest.mark.parametrize('field',['no_play','return_touchdown','touchdown','td_team'])
def test_known_return_td_with_unknown_field_masks_relevant_team(field):
    changes=dict(return_touchdown=1,touchdown=1,td_team='MIA');changes[field]=None
    r=build([row(**changes)])
    assert team(r)['exact_physical_return_TDs']is None
    assert r['pregame_serving_eligible']is False and r['forecast']is None

def test_known_no_touchdown_cannot_hide_td_when_return_flag_unknown():
    assert team(build([row(return_touchdown=None,touchdown=0)]))['exact_physical_return_TDs']==0

def test_no_play_and_two_point_excluded_even_if_return_td_flag_positive():
    for change in (dict(no_play=1),dict(two_point_attempt=1)):
        r=build([row(return_touchdown=1,touchdown=1,td_team='MIA',**change)])
        assert team(r)['exact_physical_return_TDs']==0


def test_unknown_native_class_positive_td_masks_known_zero_on_other_team():
    r=build([row(play_type_nfl='UNSPECIFIED',return_touchdown=1,touchdown=1,td_team=None)])
    assert all(t['exact_physical_return_TDs']is None for t in r['team_game_rows'])

def test_offensive_return_flag_conflict_is_unknown_not_two_tds():
    r=build([row(return_touchdown=1,touchdown=1,pass_touchdown=1,td_team='MIA')])
    assert team(r)['exact_physical_return_TDs']is None
    assert r['mechanism_scope_gaps']['conflicting_offensive_return_TD_flags']==1

def test_fumble_recovery_uses_native_recoverer_not_posteam_and_never_slot_zip():
    f=row(fumble=1,fumble_lost=1,fumbled_1_team='BUF',fumbled_1_player_id=A,fumble_recovery_1_team='MIA',fumble_recovery_1_player_id=B,
        return_touchdown=1,touchdown=1,td_team='MIA')
    r=build([f]);assert team(r)['channels']['opponent_fumble_recoveries']['exact_exposures']==1
    f.update(fumbled_2_team='MIA',fumbled_2_player_id=C,fumble_recovery_2_team='BUF',fumble_recovery_2_player_id=D)
    r=build([f]);assert all(t['channels']['opponent_fumble_recoveries']['exact_exposures']is None for t in r['team_game_rows'])

def test_unknown_td_team_global_count_not_assigned_to_initial_offense():
    r=build([row(return_touchdown=1,touchdown=1,td_team=None)])
    assert all(t['known_physical_return_TDs']==0 and t['exact_physical_return_TDs']is None for t in r['team_game_rows'])

@pytest.mark.parametrize('change',[dict(return_team='GB'),dict(td_team='GB'),dict(kickoff_returner_player_id='Name Only'),dict(play_id=1.5)])
def test_contradictory_native_identity_rejects(change):
    with pytest.raises(ValueError):build([row(**change)])

def test_order_invariance_duplicate_keys_and_empty_conditional_denominator():
    rows=[kick(),row(2)]
    assert build(rows)['semantic_sha256']==build(rows[::-1])['semantic_sha256']
    with pytest.raises(ValueError):build([row(),row(play_id=1.0)])
    assert team(build([row()]))['channels']['interception_possessions']['observed_TD_per_exposure']is None


def test_false_attempt_with_positive_matching_returner_is_source_conflict_unknown():
    c=team(build([kick(kickoff_attempt=0)]))['channels']['kickoff_actual_returns']
    assert c['exact_exposures']is None


def test_authenticated_retrospective_reader_bounds_and_original_absence(tmp_path,monkeypatch):
    import csv,hashlib
    from pathlib import Path
    from types import SimpleNamespace
    from datetime import datetime,UTC,timedelta
    from backend.app.product_services.return_touchdown_components import derive_retrospective_return_components
    from backend.app.services import source_capture
    r=kick(return_touchdown=1,touchdown=1,td_team='MIA');p=tmp_path/'source.csv'
    with p.open('w',newline='')as f:
        writer=csv.DictWriter(f,fieldnames=list(r));writer.writeheader();writer.writerow(r)
    now=datetime.now(UTC);s=SimpleNamespace(slate_lock_at=now-timedelta(hours=1),source_system='nflreadpy',dataset='play_by_play',media_type='text/csv',
        metadata_json=dict(contract_id='operational_opportunity_source_v1',loader='load_pbp'),source_uri='nflreadpy://pbp/2026',season=2026,week=6,
        byte_count=p.stat().st_size,captured_at=now-timedelta(days=1),observed_at=now-timedelta(days=1),artifact_path=p,snapshot_id='snapshot',content_sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    def verify(value):assert hashlib.sha256(Path(value.artifact_path).read_bytes()).hexdigest()==value.content_sha256
    monkeypatch.setattr(source_capture,'verify_snapshot_artifact',verify)
    out=derive_retrospective_return_components(s,before_period=202606,actual_read_at=now)
    assert out['provenance']['original_no_play_field_present']is False
    assert team(out)['exact_physical_return_TDs']==1
    assert out['evidence_use']=='postlock_descriptive_not_pregame_or_serving'
    with pytest.raises(ValueError,match='postlock'):derive_retrospective_return_components(s,before_period=202606,actual_read_at=now+timedelta(days=1))
    with pytest.raises(ValueError,match='bound'):derive_retrospective_return_components(s,before_period=202606,actual_read_at=now,max_bytes=1)
    s.metadata_json['loader']='other'
    with pytest.raises(ValueError,match='source/scope'):derive_retrospective_return_components(s,before_period=202606,actual_read_at=now)
