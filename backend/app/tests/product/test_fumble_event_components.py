from copy import deepcopy
import pytest
from backend.app.product_services.fumble_event_components import build_fumble_event_components

A='00-0000001';B='00-0000002';C='00-0000003';D='00-0000004'


def play(number=1,**changes):
    r=dict(game_id='2026_01_BUF_MIA',play_id=number,season=2026,week=1,season_type='REG',posteam='BUF',defteam='MIA',
        play_type='pass',play_type_nfl='PASS',pass_attempt=1,rush_attempt=0,sack=0,qb_dropback=1,qb_spike=0,qb_kneel=0,qb_scramble=0,two_point_attempt=0,
        fumble=0,fumble_lost=0,fumble_out_of_bounds=0,fumbled_1_team=None,fumbled_1_player_id=None,fumbled_2_team=None,fumbled_2_player_id=None,
        fumble_recovery_1_team=None,fumble_recovery_1_player_id=None,fumble_recovery_2_team=None,fumble_recovery_2_player_id=None)
    return r|changes


def fumble(number=1,**changes):
    return play(number,fumble=1,fumbled_1_team='BUF',fumbled_1_player_id=A,fumble_recovery_1_team='BUF',fumble_recovery_1_player_id=B)|changes


def build(rows):return build_fumble_event_components(rows,before_period=202606,source=dict(snapshot_id='frozen',content_sha256='a'*64))


def test_occurrence_and_recovery_are_different_denominators_and_unknown_not_zero():
    r=build([fumble(),play(2),fumble(3,fumble_lost=1,fumble_recovery_1_team='MIA')]);g=r['game_rows'][0]
    assert g['fumble_play_incidence']==2/3 and g['known_single_fumble_loss_fraction']==.5
    assert g['all_fumble_loss_fraction']==.5 and g['known_fumble_plays']==2
    assert r['pregame_serving_eligible']is False and r['forecast']is None


def test_recovery_belongs_to_explicit_fumbler_team_not_original_offense():
    r=build([fumble(fumbled_1_team='MIA',fumble_recovery_1_team='BUF',fumble_lost=1)])
    f=r['fumble_ledger'][0]
    assert f['reported_fumblers'][0]['team']=='MIA' and f['lost_from_fumbler_team']is True


def test_two_fumbles_are_one_any_fumble_play_and_recovery_slots_not_zipped():
    r=build([fumble(fumbled_2_team='MIA',fumbled_2_player_id=C,fumble_recovery_2_team='MIA',fumble_recovery_2_player_id=D)])
    g=r['game_rows'][0];f=r['fumble_ledger'][0]
    assert g['exact_fumble_play_count']==1 and len(f['reported_fumblers'])==2
    assert g['all_fumble_loss_fraction']is None and g['unknown_recovery_fumble_plays']==1
    assert f['lost_from_fumbler_team']is None


@pytest.mark.parametrize('changes',[dict(fumble_recovery_1_team=None,fumble_recovery_1_player_id=None),dict(fumbled_1_player_id=None),dict(fumble_recovery_1_player_id=None)])
def test_missing_native_occurrence_or_recovery_is_unknown(changes):
    g=build([fumble(**changes)])['game_rows'][0]
    assert g['known_fumble_plays']==1 and g['unknown_recovery_fumble_plays']==1
    assert g['all_fumble_loss_fraction']is None


def test_native_lost_flag_conflict_not_resolved_by_guessing_or_zero():
    r=build([fumble(fumble_lost=1)])
    assert r['fumble_ledger'][0]['recovery_proof']=='conflicting_native_lost_flag'
    assert r['game_rows'][0]['all_fumble_loss_fraction']is None


def test_no_fumble_vs_zero_exposure_have_undefined_conditional_recovery():
    g=build([play()])['game_rows'][0]
    assert g['fumble_play_incidence']==0 and g['all_fumble_loss_fraction']is None
    g=build([play(play_type='no_play',fumble=1)])['game_rows'][0]
    assert g['fumble_play_incidence']is None and g['exact_fumble_play_count']==0


def test_explicit_null_no_play_and_unknown_native_class_cannot_certify_attempt():
    for change in (dict(no_play=None),dict(play_type_nfl='UNSPECIFIED')):
        g=build([fumble(**change)])['game_rows'][0]
        assert g['unknown_live_eligibility']==1 and g['exact_fumble_play_count']is None
    assert build([fumble(no_play=0)])['game_rows'][0]['fumble_play_incidence']==1


def test_kick_and_punt_events_preserve_typed_fumbler_and_are_not_offense_snaps():
    rows=[fumble(play_type='punt',play_type_nfl='PUNT',pass_attempt=0,qb_dropback=0,fumbled_1_team='MIA',fumble_recovery_1_team='MIA'),
        fumble(2,play_type='kickoff',play_type_nfl='KICK_OFF',pass_attempt=0,qb_dropback=0)]
    g=build(rows)['game_rows'][0]
    assert g['known_live_plays']==2 and g['known_fumble_plays']==2


def test_quiet_admin_marker_does_not_swallow_positive_fumble():
    r=play(play_type=None,play_type_nfl=None,pass_attempt=0,qb_dropback=0,desc='END GAME')
    assert build([r])['game_rows'][0]['excluded_source_rows']==1
    r['fumble']=1
    assert build([r])['game_rows'][0]['unknown_live_eligibility']==1


def test_source_flag_vs_positive_person_record_contradiction_retained_unknown():
    r=build([fumble(fumble=0)])
    assert r['fumble_ledger'][0]['source_conflict']is True
    assert r['game_rows'][0]['exact_fumble_play_count']is None


@pytest.mark.parametrize('change',[dict(fumbled_1_team='GB'),dict(fumble_recovery_1_player_id='a name'),dict(play_id=1.5),dict(season=2025)])
def test_native_scope_and_identity_rejected(change):
    with pytest.raises(ValueError):build([fumble(**change)])


def test_duplicate_native_key_and_input_order_invariance():
    with pytest.raises(ValueError):build([play(),play(play_id=1.0)])
    rows=[fumble(),play(2)]
    assert build(rows)['semantic_sha256']==build(rows[::-1])['semantic_sha256']


def test_known_no_fumble_unknown_live_exposure_cannot_add_hidden_fumble():
    g=build([play(play_type_nfl='UNSPECIFIED')])['game_rows'][0]
    assert g['unknown_live_eligibility']==1 and g['exact_fumble_play_count']==0
    assert g['fumble_play_incidence']is None


@pytest.mark.parametrize('kind',['INTERCEPTION','FUMBLE_RECOVERED_BY_OPPONENT'])
def test_explicit_native_pass_outcome_is_live_not_administrative(kind):
    assert build([fumble(play_type_nfl=kind)])['game_rows'][0]['known_live_plays']==1


def test_native_admin_requires_empty_play_type_and_all_quiet_indicators():
    r=play(play_type=None,play_type_nfl='END_QUARTER',pass_attempt=0,qb_dropback=0)
    assert build([r])['game_rows'][0]['excluded_source_rows']==1
    r['qb_scramble']=1
    assert build([r])['game_rows'][0]['unknown_live_eligibility']==1


def test_actual_reader_provider_scope_and_postlock_guard(tmp_path,monkeypatch):
    import csv,hashlib
    from datetime import datetime,UTC,timedelta
    from types import SimpleNamespace
    from backend.app.product_services.fumble_event_components import derive_retrospective_fumble_components
    from backend.app.services import source_capture
    p=tmp_path/'raw.csv';row=fumble()
    with p.open('w',newline='')as f:
        writer=csv.DictWriter(f,fieldnames=list(row));writer.writeheader();writer.writerow(row)
    now=datetime.now(UTC)
    snapshot=SimpleNamespace(slate_lock_at=now-timedelta(hours=1),source_system='nflreadpy',dataset='play_by_play',media_type='text/csv',
        metadata_json=dict(contract_id='operational_opportunity_source_v1',loader='load_pbp'),source_uri='nflreadpy://pbp/2026',season=2026,week=6,
        byte_count=p.stat().st_size,captured_at=now-timedelta(days=1),observed_at=now-timedelta(days=1),artifact_path=p,snapshot_id='snapshot',content_sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    def verify(value):
        assert hashlib.sha256(Path(value.artifact_path).read_bytes()).hexdigest()==value.content_sha256
    from pathlib import Path
    monkeypatch.setattr(source_capture,'verify_snapshot_artifact',verify)
    result=derive_retrospective_fumble_components(snapshot,before_period=202606,actual_read_at=now)
    assert result['game_rows'][0]['fumble_play_incidence']==1
    assert result['provenance']['original_no_play_field_present']is False
    assert result['pregame_serving_eligible']is False
    snapshot.metadata_json['loader']='other'
    with pytest.raises(ValueError,match='source/scope'):derive_retrospective_fumble_components(snapshot,before_period=202606,actual_read_at=now)
    with pytest.raises(ValueError,match='postlock'):derive_retrospective_fumble_components(snapshot,before_period=202606,actual_read_at=now+timedelta(days=1))


def test_native_fumbler_team_recovery_cohort_not_initial_offense_cohort():
    r=build([fumble(fumbled_1_team='MIA',fumble_recovery_1_team='BUF',fumble_lost=1)])
    teams={r['team']:r for r in r['team_recovery_rows']}
    assert teams['MIA']['reported_source_fumbler_slots']==1
    assert teams['MIA']['all_reported_fumble_loss_fraction']==1
    assert teams['BUF']['reported_source_fumbler_slots']==0 and teams['BUF']['all_reported_fumble_loss_fraction']is None


def test_two_same_team_reported_fumblers_stay_two_unknown_recovery_slots():
    r=build([fumble(fumbled_2_team='BUF',fumbled_2_player_id=C,fumble_recovery_2_team='MIA',fumble_recovery_2_player_id=D)])
    team=next(t for t in r['team_recovery_rows']if t['team']=='BUF')
    assert team['reported_source_fumbler_slots']==2 and team['unknown_recovery_slots']==2
    assert team['all_reported_fumble_loss_fraction']is None


@pytest.mark.parametrize('unknown_branch',['eligibility','source_conflict'])
def test_unknown_team_additional_fumbler_can_pollute_other_known_team_cohort(unknown_branch):
    first=fumble(fumbled_1_team='MIA',fumble_recovery_1_team='MIA')
    second=fumble(2,fumbled_2_team=None,fumbled_2_player_id=C)
    if unknown_branch=='eligibility':second['play_type_nfl']='UNSPECIFIED'
    else:second['fumble']=0
    result=build([first,second])
    other=next(t for t in result['team_recovery_rows']if t['team']=='MIA')
    assert other['known_single_fumble_loss_fraction']==0
    assert other['unknown_condition_membership']==1
    assert other['all_reported_fumble_loss_fraction']is None
