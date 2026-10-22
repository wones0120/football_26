from copy import deepcopy
import hashlib
import json

import pytest

from backend.app.product_services.opportunity_events import build_event_evidence, validate_event_evidence
from backend.app.product_services.workload_count_forecast import forecast
from backend.app.tests.product.test_workload_count_forecast import MODEL, actors, history

IDS = {"q": "00000000-0000-0000-0000-000000000001",
       "w": "00000000-0000-0000-0000-000000000002",
       "r": "00000000-0000-0000-0000-000000000003"}
CUTOFF = "2025-09-01T00:00:00Z"
SOURCE = dict(snapshot_id="immutable-capture", content_sha256="a"*64,
    captured_at="2025-08-31T00:00:00Z", received_at="2025-08-31T01:00:00Z",
    verification="snapshot_artifact_sha256_verified")


def play(number=1, **changes):
    return dict(dict(game_id="2025_08_A_B", play_id=number, season=2025, week=8,season_type="REG",
        posteam="A", play_type="pass", pass_attempt=1, rush_attempt=0, sack=0,
        qb_spike=0, qb_scramble=0, qb_kneel=0, qb_dropback=1,
        two_point_attempt=0, penalty=0, passer_player_id="q", receiver_player_id="w",
        yardline_100=20, goal_to_go=0), **changes)


def build(rows, **kwargs):
    return build_event_evidence(rows, canonical_ids=IDS, source_receipt=SOURCE, cutoff=CUTOFF, **kwargs)


@pytest.mark.parametrize("yardline,zone", [(0,"inside5"),(5,"inside5"),(6,"six_to_twenty"),
    (20,"six_to_twenty"),(21,"outside20"),(None,"unknown"),(-1,"unknown")])
def test_disjoint_zone_boundaries_and_shared_physical_pass(yardline, zone):
    result = build([play(yardline_100=yardline, goal_to_go=1)])
    team = result["teams"][0]
    for channel in ("targets", "pass_attempts"):
        assert sum(team["zones"][channel].values()) == team["counts"][channel] == 1
        assert team["zones"][channel][zone] == team["goal_to_go"][channel] == 1
    assert len(result["events"]) == 1 and len(result["events"][0]["opportunities"]) == 2


def test_sack_spike_kneel_scramble_two_point_and_no_play_taxonomy():
    rows = [play(1,sack=1), play(2,qb_spike=1,receiver_player_id=None),
        play(3,play_type="run",pass_attempt=0,rush_attempt=1,qb_dropback=0,qb_kneel=1,rusher_player_id="q"),
        play(4,play_type="run",pass_attempt=0,rush_attempt=1,qb_scramble=1,rusher_player_id="q"),
        play(5,two_point_attempt=1), play(6,play_type="no_play",penalty=1)]
    result = build(rows)
    team = result["teams"][0]
    assert team["counts"] == dict(pass_attempts=1,rush_attempts=2,targets=0)
    assert result["events"][0]["reported_dropback"] is True
    assert result["events"][1]["opportunities"][0]["subtype"] == "spike"
    assert result["events"][2]["opportunities"][0]["subtype"] == "kneel"
    assert result["events"][3]["opportunities"][0]["subtype"] == "scramble"
    assert result["coverage"]["excluded"] == 2


def test_valid_penalty_play_counts_but_explicit_no_play_does_not():
    result = build([play(1,penalty=1),play(2,penalty=1,no_play=True)])
    assert result["teams"][0]["counts"]["pass_attempts"] == 1
    assert result["events"][1]["status"] == "excluded"


def test_missing_flags_unknown_not_zero_and_no_receiver_not_fabricated_target():
    result = build([play(1,sack=None),play(2,two_point_attempt=None),play(3,receiver_player_id=None)])
    assert result["coverage"]["unknown"] == 2
    assert result["teams"][0]["counts"] == dict.fromkeys(("pass_attempts","rush_attempts","targets"))
    assert result["teams"][0]["counted_lower_bound"] == dict(pass_attempts=1,rush_attempts=0,targets=0)
    assert result["teams"][0]["unknown_eligibility_events"] == dict(pass_attempts=2,rush_attempts=1,targets=3)
    assert len(result["events"][2]["opportunities"]) == 1


def test_unmapped_or_missing_actor_retains_team_opportunity_and_queue_request():
    for native in ("unmapped",None):
        result = build([play(receiver_player_id=native)])
        assert result["teams"][0]["counts"]["pass_attempts"] == 1
        if native is not None:
            assert result["teams"][0]["counts"]["targets"] == 1
            assert result["identity_review_requests"][0]["source_player_id"] == native
            assert result["players"][-1]["player_master_id"] is None
    result = build([play(passer_player_id=None)])
    assert result["teams"][0]["counts"]["pass_attempts"] == 1
    assert any(r["source_player_id"] is None for r in result["identity_review_requests"])


def test_native_event_duplicates_and_ambiguous_canonical_identity_rejected():
    with pytest.raises(ValueError,match="Duplicate native"):
        build([play(),play()])
    with pytest.raises(ValueError,match="cardinality"):
        build_event_evidence([play()],canonical_ids={"q":IDS["q"],"w":IDS["q"]},source_receipt=SOURCE,cutoff=CUTOFF)
    with pytest.raises(ValueError,match="UUID"):
        build_event_evidence([play()],canonical_ids={"q":"display-name"},source_receipt=SOURCE,cutoff=CUTOFF)


def test_official_weekly_components_reconcile_without_overwriting_mismatch():
    official = [dict(game_id="2025_08_A_B",team="A",source_player_id="q",pass_attempts=2),
                dict(game_id="2025_08_A_B",team="A",source_player_id="w",targets=1)]
    result = build([play()],official_components=official)
    assert [r["status"] for r in result["official_reconciliation"]] == ["unverified_or_mismatch","matched"]
    assert result["official_reconciliation"][0]["derived"] == 1


def test_verified_receipt_checksum_future_scope_and_actual_count_consumer():
    receipt = build([play()])
    valid = validate_event_evidence(receipt,before_period=202509,cutoff=CUTOFF)
    assert valid == receipt
    damaged = deepcopy(receipt);damaged["teams"][0]["counts"]["targets"] = 99
    with pytest.raises(ValueError,match="checksum"):
        validate_event_evidence(damaged,before_period=202509,cutoff=CUTOFF)
    with pytest.raises(ValueError,match="future game"):
        validate_event_evidence(receipt,before_period=202508,cutoff=CUTOFF)
    kwargs = dict(before_period=202509,starters={"A":"Aq"},model=MODEL,cutoff=CUTOFF)
    old = forecast(history(),actors(),**kwargs)
    new = forecast(history(),actors(),event_evidence=receipt,**kwargs)
    assert old["event_evidence"]["status"] == "unavailable"
    assert new["event_evidence"] == receipt
    assert old["players"] == new["players"] and old["teams"] == new["teams"]


def test_future_or_unverified_capture_cannot_be_consumed():
    source = {**SOURCE,"captured_at":"2025-09-02T00:00:00Z"}
    with pytest.raises(ValueError,match="after decision cutoff"):
        build_event_evidence([play()],canonical_ids=IDS,source_receipt=source,cutoff=CUTOFF)
    receipt = build([play()]);receipt["source"].pop("verification")
    receipt.pop("sha256");receipt["sha256"]=hashlib.sha256(json.dumps(receipt,sort_keys=True,allow_nan=False).encode()).hexdigest()
    with pytest.raises(ValueError,match="verified source"):
        validate_event_evidence(receipt,before_period=202509,cutoff=CUTOFF)
    receipt = build([play()]);receipt["source"].pop("captured_at")
    receipt.pop("sha256");receipt["sha256"]=hashlib.sha256(json.dumps(receipt,sort_keys=True,allow_nan=False).encode()).hexdigest()
    with pytest.raises(ValueError,match="capture/receipt missing"):
        validate_event_evidence(receipt,before_period=202509,cutoff=CUTOFF)
    with pytest.raises(ValueError,match="publication after"):
        build_event_evidence([play()],canonical_ids=IDS,
            source_receipt={**SOURCE,"published_at":"2025-09-02T00:00:00Z"},cutoff=CUTOFF)


def test_all_unknown_team_and_channel_specific_partial_counts_stay_unknown():
    result = build([play(1,sack=None),play(2,game_id="other",posteam="B",two_point_attempt=None),play(3)])
    a = next(r for r in result["teams"] if r["team"]=="A")
    b = next(r for r in result["teams"] if r["team"]=="B")
    assert a["channel_coverage"] == dict(pass_attempts="partial",targets="partial",rush_attempts="complete")
    assert a["counts"] == dict(pass_attempts=None,targets=None,rush_attempts=0)
    assert a["counted_lower_bound"]["pass_attempts"] == 1
    assert set(b["channel_coverage"].values()) == {"unknown"}
    assert set(b["counts"].values()) == {None}
    assert set(b["counted_lower_bound"].values()) == {0}


@pytest.mark.parametrize("change", [dict(season_type=None),dict(season_type="POST"),dict(season_type="PRE"),
    dict(week=0),dict(week=19),dict(week=2.5),dict(season=1),dict(season=2026)])
def test_regular_season_scope_cannot_merge_unproven_or_invalid_periods(change):
    with pytest.raises(ValueError,match="season_type|event period"):
        build([play(**change)])


def test_unattributed_receiver_is_unknown_target_but_explicit_spike_is_known_no_target():
    absent = play(); absent.pop("receiver_player_id")
    for row in (absent, play(receiver_player_id=None)):
        result = build([row]); team = result["teams"][0]
        assert team["counts"]["pass_attempts"] == 1
        assert team["counts"]["targets"] is None
        assert team["counted_lower_bound"]["targets"] == 0
        assert team["channel_coverage"]["targets"] == "unknown"
        assert result["events"][0]["status"] == "partial"
    spike = build([play(qb_spike=1,receiver_player_id=None)])
    assert spike["teams"][0]["counts"]["targets"] == 0
    assert spike["teams"][0]["channel_coverage"]["targets"] == "complete"


def test_missing_play_type_cannot_silently_certify_zero_offensive_counts():
    result = build([play(play_type=None)])
    assert result["coverage"]["unknown"] == 1
    assert set(result["teams"][0]["counts"].values()) == {None}


def test_exact_clock_replay_control_retains_row_without_censoring_player_counts():
    from backend.app.product_services.player_opportunity_components import build_player_opportunity_components
    control=play(2,play_type=None,desc='The status of the game clock was assisted by replay.',
        pass_attempt=None,rush_attempt=None,sack=None,qb_dropback=None,two_point_attempt=None,
        passer_player_id=None,receiver_player_id=None,rusher_player_id=None)
    result=build([play(),control])
    assert result['events'][1]['status']=='not_applicable'
    assert result['events'][1]['raw_flags']['desc']==control['desc']
    assert result['teams'][0]['counts']==dict(pass_attempts=1,rush_attempts=0,targets=1)
    block=build_player_opportunity_components(dict(event_evidence=result),before_period=202509,cutoff=CUTOFF)
    receiver=next(r for r in block['actor_game_rows'] if r['source_player_id']=='w')
    assert receiver['metrics']['targets']['exact_within_log_sum']==1
    assert receiver['unknown_native_attribution_exposures']=={}


@pytest.mark.parametrize('changes',[dict(desc='Unidentified replay'),dict(pass_attempt=1),dict(qb_dropback=1),dict(rusher_player_id='r'),dict(touchdown=1)])
def test_clock_text_with_football_evidence_or_unknown_message_stays_unknown(changes):
    control=play(play_type=None,desc='The status of the game clock was assisted by replay.',
        pass_attempt=None,rush_attempt=None,sack=None,qb_dropback=None,two_point_attempt=None,
        passer_player_id=None,receiver_player_id=None,rusher_player_id=None)
    control.update(changes)
    assert build([control])['events'][0]['status']=='unknown'
