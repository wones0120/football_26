import pytest
from backend.app.tests.product.test_opportunity_events import play,build,CUTOFF
from backend.app.product_services.scoring_zone_decisions import build_scoring_zone_decisions


def run(rows=None):
    rows=rows or [play(1,down=1,ydstogo=5,yardline_100=5,goal_to_go=1),play(2,down=1,ydstogo=5,yardline_100=5,goal_to_go=1,play_type='run',pass_attempt=0,rush_attempt=1,qb_dropback=0,rusher_player_id='r')]
    for r in rows:r.update(game_id='2025_08_SF_WAS',posteam='SF')
    return build_scoring_zone_decisions(build(rows),before_period=202509,cutoff=CUTOFF)


def cell(x,mid='X05-M04'):return x['game_rows'][0]['metrics'][mid]['cells'][0]


def test_same_physical_decision_fractions_by_down_distance_and_GTG():
    x=run();m=cell(x)
    assert m['down']==1 and m['yards_to_go']==5 and m['exact_decisions']==2
    assert m['pass_fraction']==m['rush_fraction']==.5
    assert cell(x,'X05-M05')['pass_fraction']==.5 and x['forecast'] is None


def test_sacks_and_scrambles_pass_decision_once_spikes_kneels_excluded():
    rows=[play(1,sack=1,down=2,ydstogo=3,yardline_100=3,goal_to_go=1),play(2,play_type='run',pass_attempt=0,rush_attempt=1,qb_scramble=1,qb_dropback=1,rusher_player_id='q',down=2,ydstogo=3,yardline_100=3,goal_to_go=1),play(3,qb_spike=1,down=2,ydstogo=3,yardline_100=3),play(4,play_type='run',pass_attempt=0,rush_attempt=1,qb_dropback=0,qb_kneel=1,rusher_player_id='q')]
    m=cell(run(rows));assert m['pass_calls']==2 and m['rush_calls']==0 and m['pass_fraction']==1


def test_unknown_membership_masks_own_cell_and_outside_does_not_mask():
    rows=[play(1,down=1,ydstogo=5,yardline_100=5),play(2,down=1,ydstogo=5,yardline_100=None),play(3,down=2,ydstogo=6,yardline_100=5)]
    table=run(rows)['game_rows'][0]['metrics']['X05-M04'];assert table['cells'][0]['pass_fraction'] is None
    assert table['cells'][1]['pass_fraction']==1
    rows[-1]['yardline_100']=6
    assert len(run(rows)['game_rows'][0]['metrics']['X05-M04']['cells'])==1


def test_unknown_coordinates_masks_all_exact_rates_preserving_samples():
    x=run([play(1,down=1,ydstogo=5,yardline_100=5),play(2,down=None,ydstogo=5,yardline_100=5)])
    m=cell(x);assert m['pass_fraction'] is None and m['known_sample_pass_fraction']==1
    assert x['game_rows'][0]['metrics']['X05-M04']['unknown_coordinate_events']==1


def test_exact_distance_cells_not_tuned_bins_or_fake_empty_cells():
    x=run([play(1,down=1,ydstogo=1,yardline_100=2),play(2,down=1,ydstogo=2,yardline_100=2)])
    assert [r['yards_to_go'] for r in x['game_rows'][0]['metrics']['X05-M04']['cells']]==[1,2]


def test_unknown_call_keeps_denominator_uncertain_not_zero_rush():
    m=cell(run([play(1,down=1,ydstogo=5,yardline_100=5,qb_dropback=None)]))
    assert m['unknown_call_events']==1 and m['pass_fraction'] is None and m['exact_decisions'] is None


def test_goal_to_go_is_not_imputed_from_yardline_and_no_serving():
    from backend.app.product_services.scoring_zone_decisions import require_feature_use
    x=run([play(1,down=1,ydstogo=2,yardline_100=2,goal_to_go=None)])
    assert cell(x,'X05-M05')['pass_fraction'] is None and cell(x)['pass_fraction']==1
    assert require_feature_use(x,purpose='offline_descriptive') is x
    with pytest.raises(ValueError):require_feature_use(x,purpose='forecast')


def test_retrospective_reader_original_boundary_not_backdated_current_measurement(monkeypatch):
    from types import SimpleNamespace
    from backend.app.product_services.scoring_zone_decisions import derive_retrospective_scoring_zone_decisions
    import backend.app.product_services.opportunity_source_capture as source
    events=[play(1,game_id='2025_08_SF_WAS',posteam='SF',down=1,ydstogo=5,yardline_100=5)]
    calls=[]
    def loader(ref,snapshot,**kw):calls.append(kw);return {'event_evidence':build(events)}
    monkeypatch.setattr(source,'load_event_artifact',loader)
    ref=dict(decision_cutoff_at=CUTOFF,before_period=202509);snap=SimpleNamespace(slate_lock_at='2025-09-02T00:00:00Z')
    x=derive_retrospective_scoring_zone_decisions(ref,snap,actual_read_at='2026-10-20T05:00:00Z')
    assert calls[0]['cutoff'].isoformat()=='2025-09-01T00:00:00+00:00'
    assert x['provenance']['original_evidence_boundary_at']!=x['provenance']['actual_read_at']
    with pytest.raises(ValueError):derive_retrospective_scoring_zone_decisions(ref,snap,actual_read_at='2025-09-01T01:00:00Z')
