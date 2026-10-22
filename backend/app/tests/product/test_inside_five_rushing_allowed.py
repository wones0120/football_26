import pytest
from backend.app.product_services.inside_five_rushing_allowed import build_inside_five_rushing_allowed
from backend.app.tests.product.test_fumble_event_components import play


def rush(n=1,**kw):return play(n,play_type='run',play_type_nfl='RUSH',pass_attempt=0,rush_attempt=1,qb_kneel=0,run_location='middle',yardline_100=5,rush_touchdown=0,touchdown=0,pass_touchdown=0)|kw

def build(rows):return build_inside_five_rushing_allowed(rows,before_period=202606)
def defense(out):return next(r for r in out['team_game_rows']if r['defense']=='MIA')

def test_official_inside5_includes_kneels_scrambles_and_zero_boundary():
    out=build([rush(rush_touchdown=1,touchdown=1,td_team='BUF'),rush(2,qb_kneel=1),rush(3,qb_scramble=1),rush(4,yardline_100=0)])
    r=defense(out)
    assert r['exact_official_inside5_rushes']==4 and r['exact_inside5_rush_tds']==1 and r['value']==.25
    assert out['pregame_serving_eligible']is False and out['forecast']is None

def test_knownoutside_excludes_even_unknown_rush_but_inside_unknown_masks():
    for change in(dict(rush_attempt=None,yardline_100=6),dict(yardline_100=100)):
        assert defense(build([rush(),rush(2,**change)]))['exact_official_inside5_rushes']==1
    r=defense(build([rush(),rush(2,rush_attempt=None)]))
    assert r['exact_official_inside5_rushes']is None and r['known_eligible_rush_lower_bound']==1

def test_missing_invalid_zone_is_unknown_not_inside_or_zero():
    for value in(None,-1,101,float('nan')):
        assert defense(build([rush(yardline_100=value)]))['value']is None
        assert defense(build([rush(yardline_100=value)]))['unknown_eligibility_or_side']==1

def test_zero_eligible_denominator_undefined_known_total_zero():
    r=defense(build([rush(yardline_100=6)]))
    assert r['exact_official_inside5_rushes']==r['exact_inside5_rush_tds']==0 and r['value']is None

def test_missing_outcome_keeps_eligible_count_and_measured_sample():
    r=defense(build([rush(rush_touchdown=1,touchdown=1),rush(2,rush_touchdown=None)]))
    assert r['exact_official_inside5_rushes']==2 and r['exact_inside5_rush_tds']is None
    assert r['unknown_td_outcomes']==1 and r['known_outcome_sample_fraction']==1

@pytest.mark.parametrize('change',[dict(pass_attempt=1),dict(pass_attempt=None),dict(sack=1),dict(sack=None),dict(qb_spike=1),dict(rush_attempt=0,qb_scramble=1)])
def test_official_flag_conflict_unknown_not_counted(change):
    r=defense(build([rush(),rush(2,**change)]))
    assert r['exact_official_inside5_rushes']is None and r['unknown_eligibility_or_side']==1

def test_nativeclass_absent_noplay_allowed_but_explicitnull_unknown_and_exclusions_precede():
    assert defense(build([rush()]))['exact_official_inside5_rushes']==1
    assert defense(build([rush(no_play=None)]))['exact_official_inside5_rushes']is None
    for change in(dict(no_play=1,pass_attempt=1),dict(two_point_attempt=1),dict(play_type='no_play')):
        assert defense(build([rush(**change)]))['exact_official_inside5_rushes']==0

def test_missing_side_masks_both_defense_candidates_not_known_extra_count():
    for change in(dict(posteam=None),dict(defteam=None)):
        out=build([rush(**change)])
        for r in out['team_game_rows']:
            assert r['exact_official_inside5_rushes']is None and r['known_eligible_rush_lower_bound']==0

def test_contradictory_positive_td_evidence_unknown_not_reassigned():
    for change in(dict(touchdown=0),dict(pass_touchdown=1),dict(td_team='MIA')):
        changes=dict(rush_touchdown=1,touchdown=1)|change
        r=defense(build([rush(**changes)]))
        assert r['exact_official_inside5_rushes']==1 and r['exact_inside5_rush_tds']is None

def test_nativekey_period_duplicates_post_exclusion():
    with pytest.raises(ValueError,match='Duplicate'):build([rush(),rush()])
    with pytest.raises(ValueError,match='game/period'):build([rush(week=2)])
    r=defense(build([rush(),rush(2,season_type='POST')]))
    assert r['exact_official_inside5_rushes']==1


def test_native_csv_numeric_strings_not_missing_or_zero_default():
    out=build([rush(yardline_100='5',rush_touchdown='1',touchdown='1')])
    assert defense(out)['value']==1
    assert defense(build([rush(yardline_100='')]))['unknown_eligibility_or_side']==1


def test_retrospective_reader_authenticates_scope_preserves_absent_noplay(tmp_path,monkeypatch):
    import csv
    from types import SimpleNamespace
    from datetime import datetime,UTC
    from backend.app.product_services.inside_five_rushing_allowed import derive_retrospective_inside_five_rushing_allowed
    from backend.app.services import source_capture
    path=tmp_path/'native.csv';record=rush()
    with path.open('w',newline='')as stream:
        writer=csv.DictWriter(stream,fieldnames=record);writer.writeheader();writer.writerow(record)
    snapshot=SimpleNamespace(snapshot_id='native-frozen',source_system='nflreadpy',dataset='play_by_play',media_type='text/csv',season=2026,week=6,
        source_uri='nflreadpy://pbp/2026',metadata_json=dict(contract_id='operational_opportunity_source_v1',loader='load_pbp'),artifact_path=str(path),
        slate_lock_at='2026-10-20T00:15:00Z',captured_at='2026-10-19T19:36:00Z',observed_at='2026-10-19T19:36:00Z',byte_count=path.stat().st_size,content_sha256='a'*64)
    calls=[];monkeypatch.setattr(source_capture,'verify_snapshot_artifact',lambda value:calls.append(value.snapshot_id))
    result=derive_retrospective_inside_five_rushing_allowed(snapshot,before_period=202606,actual_read_at=datetime.now(UTC))
    assert calls==['native-frozen'] and result['provenance']['original_no_play_field_present']is False
    assert result['pregame_serving_eligible']is False and defense(result)['exact_official_inside5_rushes']==1
    with pytest.raises(ValueError,match='scope'):derive_retrospective_inside_five_rushing_allowed(snapshot,before_period=202607)
    with pytest.raises(ValueError,match='postlock'):derive_retrospective_inside_five_rushing_allowed(snapshot,before_period=202606,actual_read_at='2026-10-19T20:00:00Z')
    with pytest.raises(ValueError,match='row bound'):derive_retrospective_inside_five_rushing_allowed(snapshot,before_period=202606,max_rows=0)
