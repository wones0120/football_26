from copy import deepcopy
import pytest
from backend.app.product_services.opportunity_events import build_event_evidence
from backend.app.product_services.defensive_event_distributions import build_defensive_event_distributions
from backend.app.tests.product.test_defense_context_evidence import play,SOURCE,CUTOFF,IDS


def build(rows):
    rows=[dict(interception=0,**r) if 'interception'not in r else r for r in rows]
    parent=dict(event_evidence=build_event_evidence(rows,canonical_ids=IDS,source_receipt=SOURCE,cutoff=CUTOFF))
    return build_defensive_event_distributions(parent,before_period=202606,cutoff=CUTOFF)


def defense(r,mid='X06-M06'):return next(x for x in r['game_rows'] if x['defense_team']=='MIA')['metrics'][mid]


def test_sack_union_counts_spike_scramble_once_and_interception_only_official_pass():
    r=build([play(1),play(2,sack=1,pass_attempt=0),play(3,qb_spike=1),
        play(4,play_type='run',pass_attempt=0,rush_attempt=1,qb_scramble=1),play(5,interception=1)])
    s=defense(r);i=defense(r,'X06-M07')
    assert (s['exact_observed_exposure'],s['exact_observed_event_count'])==(5,1)
    assert (i['exact_observed_exposure'],i['exact_observed_event_count'])==(3,1)
    assert s['observed_event_rate']==.2


def test_excluded_nullified_and_two_point_events_do_not_count():
    r=build([play(1),play(2,no_play=1,interception=1),play(3,two_point_attempt=1,sack=1)])
    assert defense(r)['exact_observed_exposure']==1
    assert defense(r,'X06-M07')['exact_observed_event_count']==0


def test_missing_interception_and_sack_flags_are_unknown_not_zero():
    r=build([play(1),play(2,sack=None,interception=None)])
    assert defense(r)['exact_observed_event_count']is None
    assert defense(r)['unknown_event_outcome']+defense(r)['unknown_exposure']==1
    assert defense(r,'X06-M07')['exact_observed_event_count']is None


def test_missing_side_not_absent_game_zero_and_native_unmapped_not_dropped():
    r=build([play(1,passer_player_id='unknown',receiver_player_id=None)])
    assert defense(r)['exact_observed_exposure']==1
    missing=next(x for x in r['game_rows'] if x['defense_team']=='BUF')['metrics']['X06-M06']
    assert missing['missing_offense_log'] and missing['exact_observed_exposure']is None


def test_all_rush_game_known_zero_passes_has_undefined_rate_not_missing():
    r=build([play(1,play_type='run',pass_attempt=0,rush_attempt=1,qb_dropback=0,qb_scramble=0)])
    s=defense(r)
    assert s['exact_observed_exposure']==s['exact_observed_event_count']==0
    assert s['observed_event_rate']is None and not s['missing_offense_log']


def test_empirical_conditional_counts_use_same_game_exposures():
    r=build([play(1,sack=1,pass_attempt=0),play(2),play(3,game_id='2026_02_BUF_MIA',week=2),
        play(4,game_id='2026_02_BUF_MIA',week=2),play(5,game_id='2026_02_BUF_MIA',week=2)])
    p=next(x for x in r['team_distributions'] if x['defense_team']=='MIA')['metrics']['X06-M06']
    assert p['mean_event_count']==.5 and p['population_variance']==.25
    assert [(x['opponent_exposure'],x['count_frequencies'][0]['event_count']) for x in p['conditional_distributions']]==[(2,1),(3,0)]
    assert 'not next-game'in p['interpretation']


def test_unknown_game_membership_masks_exact_conditional_but_retains_known_sample():
    r=build([play(1),play(2,game_id='2026_02_BUF_MIA',week=2,sack=None)])
    p=next(x for x in r['team_distributions'] if x['defense_team']=='MIA')['metrics']['X06-M06']
    assert p['unknown_game_pairs']==1 and p['mean_event_count']is None
    c=p['conditional_distributions'][0]
    assert c['count_frequencies'][0]['known_sample_frequency']==1
    assert c['count_frequencies'][0]['all_observed_games_frequency']is None


def test_event_order_not_chronology_dependent_and_source_conflict_rejected():
    rows=[play(1),play(2,sack=1,pass_attempt=0)]
    assert build(rows)['semantic_sha256']==build(rows[::-1])['semantic_sha256']
    with pytest.raises(ValueError):build([play(1,defteam='NYJ')])


def test_known_interception_on_nonpass_rejected_not_hidden():
    with pytest.raises(ValueError,match='Interception contradicts'):
        build([play(1,play_type='run',pass_attempt=0,rush_attempt=1,qb_dropback=0,interception=1)])


def test_retrospective_reader_keeps_real_clocks_and_original_boundary_separate(monkeypatch):
    from datetime import datetime,UTC,timedelta
    from types import SimpleNamespace
    from backend.app.product_services.defensive_event_distributions import derive_retrospective_defensive_events
    from backend.app.product_services import opportunity_source_capture
    now=datetime.now(UTC);original=now-timedelta(days=2);lock=now-timedelta(days=1)
    parent=dict(event_evidence=build_event_evidence([play(1,interception=0)],canonical_ids=IDS,source_receipt=SOURCE,cutoff=CUTOFF))
    ref=dict(decision_cutoff_at=original.isoformat(),before_period=202606)
    calls=[]
    def load(*args,**kwargs):calls.append(kwargs);return parent
    monkeypatch.setattr(opportunity_source_capture,'load_event_artifact',load)
    r=derive_retrospective_defensive_events(ref,SimpleNamespace(slate_lock_at=lock),actual_read_at=now)
    assert calls[0]['cutoff']==original
    assert r['evidence_use']=='postlock_descriptive_not_pregame_or_serving' and r['pregame_serving_eligible']is False
    assert r['provenance']['retrospective_read']['actual_read_at']==now.isoformat()
    with pytest.raises(ValueError,match='postlock'):
        derive_retrospective_defensive_events(ref,SimpleNamespace(slate_lock_at=lock),actual_read_at=now+timedelta(days=1))
