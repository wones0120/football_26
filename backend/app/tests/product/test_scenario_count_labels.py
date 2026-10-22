from copy import deepcopy
import json
from pathlib import Path
import pytest
from research.game_progression_pilot_20261020.scenario_03.count_labels import reconcile,FIELDS

def fixture():
    # Native game/source bindings are required; no player display-name join.
    official=json.loads((Path(__file__).resolve().parents[4]/'research/game_progression_pilot_20261020/scenario_03/GAMEBOOK_EVIDENCE.json').read_text())['games'][0]
    values=[{f:official['teams'][t][f]for f in FIELDS}for t in ('KC','DEN')]
    pbp=dict(game_id=official['game_id'],source_sides=['KC','DEN'],metrics_admitted=True,regulation_score_certified=True,independently_completed=True,
        overtime_rows_retained=0,regulation_scores=[31,10],production_by_side=deepcopy(values),known_production_sums_by_side=deepcopy(values),
        unknown_production_play_ids_by_side=[{f:[]for f in FIELDS}for _ in (0,1)])
    scope=dict(game_id=official['game_id'],season=2026,week=1,teams=['DEN','KC'],game_date=official['game_date'],native_quarters=[1,2,3,4],
        unknown_period_rows=0,all_native_rows_retained=True,unique_native_play_keys=True)
    return pbp,official,scope

def test_independent_official_total_preserves_unknown_event_credit_and_inputs():
    pbp,book,scope=fixture()
    for side in (0,1):
        for f in FIELDS:
            pbp['production_by_side'][side][f]=None;pbp['unknown_production_play_ids_by_side'][side][f]=['3748']
    pbp['known_production_sums_by_side'][1]['official_pass_attempts']-=1
    pbp['known_production_sums_by_side'][1]['official_targets']-=1
    pbp['known_production_sums_by_side'][1]['physical_plays']-=1
    before=deepcopy((pbp,book,scope));out=reconcile(pbp,book,scope)
    assert out['production_by_side'][1]['official_pass_attempts']==28
    assert out['production_by_side'][0]['official_targets']==25
    assert out['original_pbp_record']==pbp and (pbp,book,scope)==before
    assert not out['conflicts']and not out['event_level_unknowns_resolved']and not out['activation']
    assert out['count_source_evidence_by_side'][1]['official_targets']['pbp_unknown_native_play_ids']==['3748']

def test_known_counts_require_exact_agreement():
    pbp,book,scope=fixture();pbp['production_by_side'][0]['official_targets']=24;pbp['known_production_sums_by_side'][0]['official_targets']=24
    out=reconcile(pbp,book,scope)
    assert out['production_by_side'][0]['official_targets']is None
    assert len(out['conflicts'])==1 and out['conflicts'][0]['official_total']==25
    assert out['original_pbp_record']['production_by_side'][0]['official_targets']==24
    assert out['production_by_side'][0]['official_carries']==38

def test_official_total_outside_unresolved_opportunity_bounds_stays_unknown():
    pbp,book,scope=fixture();pbp['production_by_side'][1]['official_targets']=None
    pbp['known_production_sums_by_side'][1]['official_targets']=25
    pbp['unknown_production_play_ids_by_side'][1]['official_targets']=['3748']
    out=reconcile(pbp,book,scope)
    assert out['production_by_side'][1]['official_targets']is None and out['conflicts']

@pytest.mark.parametrize('change',[
    {'game_id':'2026_01_MIN_CHI'},{'season':2025},{'week':2},{'game_date':'2026-09-15'},
    {'native_quarters':[1,2,3,4,5]},{'native_quarters':[1,2,3]},
    {'unknown_period_rows':1},{'all_native_rows_retained':False},{'unique_native_play_keys':False},{'teams':['MIN','CHI']},
])
def test_native_scope_uncertainty_cannot_admit_whole_game_as_regulation(change):
    pbp,book,scope=fixture();scope.update(change)
    with pytest.raises(ValueError):reconcile(pbp,book,scope)

@pytest.mark.parametrize('change',[
    {'game_id':'2026_02_DEN_KC'},{'reviewed_final_tables':False},{'pdf_sha256':'bad'},{'team_page':None},{'individual_page':None},
])
def test_unreviewed_or_wrong_document_is_not_count_truth(change):
    pbp,book,scope=fixture();book.update(change)
    with pytest.raises(ValueError):reconcile(pbp,book,scope)

@pytest.mark.parametrize('change',[
    {'official_targets':None},{'official_targets':-1},{'official_targets':25.5},{'official_targets':True},
    {'official_targets':28},{'completions':26},{'physical_plays':66},{'sacks':None},{'receiving_target_rows':[1]},
    {'final_score':30},
])
def test_missing_counts_contradictions_or_incomplete_target_table_are_not_filled(change):
    pbp,book,scope=fixture();book['teams']['KC'].update(change)
    with pytest.raises(ValueError):reconcile(pbp,book,scope)

@pytest.mark.parametrize('change',[{'metrics_admitted':False},{'regulation_score_certified':False},{'independently_completed':False},{'overtime_rows_retained':1}])
def test_uncertified_regulation_scope_stays_unsupported(change):
    pbp,book,scope=fixture();pbp.update(change)
    with pytest.raises(ValueError):reconcile(pbp,book,scope)

def test_duplicate_unknown_event_keys_are_not_extra_opportunity_mass():
    pbp,book,scope=fixture();pbp['production_by_side'][0]['official_targets']=None
    pbp['unknown_production_play_ids_by_side'][0]['official_targets']=['10','10']
    with pytest.raises(ValueError):reconcile(pbp,book,scope)
