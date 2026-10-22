"""Conditional full-roster policy, independent of a live solver or slate."""
from copy import deepcopy
from uuid import UUID

import pytest

from backend.app.product_services.shared_world_selection import (
    Limits, MEAN_CONTRACT, ORACLE_SIZE, select_shared_world_portfolio,
)

SCOPE = {'contest_format': 'showdown', 'game_id': '2026_06_WAS_SF'}
SHA = 'a' * 64
PIDS = [str(UUID(int=i+1)) for i in range(8)]


def inputs():
    def candidate(cid, variable, captain=PIDS[0]):
        ids = PIDS[:5] + [variable]
        return dict(candidate_id=cid, input_sha256=SHA, frozen_scope=SCOPE,
                    roster=[dict(player_master_id=p, role='CPT' if p == captain else 'FLEX', salary=5000) for p in ids])
    candidates = [candidate('A', PIDS[5]), candidate('B', PIDS[6]), candidate('C', PIDS[7])]
    base = {p: 10 for p in PIDS}; base.update({PIDS[5]: 30, PIDS[6]: 20, PIDS[7]: 10})
    def world(wid, kind, values):
        means = {p: 10 for p in PIDS};means.update(dict(zip(PIDS[5:], values)))
        return dict(world_id=wid, kind=kind, frozen_scope=SCOPE, input_sha256=SHA,
                    mean_contract=MEAN_CONTRACT, player_means=means,
                    likelihood='unknown', source_refs=['frozen_source'], mechanism='Authored conditional path '+wid)
    worlds = [world('expected', 'baseline', [30,20,10]), world('response', 'contrary', [0,40,20])]
    worlds[0]['anchor_basis']='authored_EXPECTED_GAME'
    return candidates,worlds,base


def proof(**kwargs):
    return dict(status='feasible', constraint_sha256='b'*64, target_size=kwargs['requested'],
                achieved_size_semantics=ORACLE_SIZE, feasible_completion_size=kwargs['requested'], proof='Fixture exact completion')


def run(candidates, worlds, base, requested=2, oracle=proof, **kwargs):
    return select_shared_world_portfolio(candidates,worlds,base_player_means=base, requested=requested,
        completion_feasible=oracle,anchor_world_id='expected',**kwargs)


def names(selected):
    return [r['variant_ids'][0] for r in selected]


def test_anchor_then_positive_contrary_gain_not_minimax():
    c,w,b=inputs();chosen,r=run(c,w,b)
    assert names(chosen)==['A','B']
    assert r['selection_steps'][0]['anchor_conditional_mean_points']==85
    assert r['selection_steps'][1]['maximum_incremental_gain_points']==40
    assert r['selection_steps'][1]['coverage_status']=='incremental_scenario_coverage'
    assert r['selection_steps'][1]['strongest_admissible_alternative']['incremental_gain_by_world']
    assert r['probability_status'].startswith('Unknown')
    assert len(r['candidate_evaluations'])==3
    assert all(len(x['world_scores'])==2 for x in r['candidate_evaluations'])
    assert r['selection_steps'][1]['target_world_ids']==['response']


def test_contrary_changes_later_entry_without_vetoing_anchor():
    c,w,b=inputs();w[1]['player_means'][PIDS[7]]=100
    chosen,r=run(c,w,b)
    assert names(chosen)==['A','C']
    assert r['selection_steps'][1]['maximum_incremental_gain_points']==100
    assert any(a['kind']=='contrary' for x in r['score_equivalent_worlds'] for a in x['aliases'])


def test_order_duplicate_world_and_roster_invariance_with_aliases():
    c,w,b=inputs();original,r=run(c,w,b)
    duplicate=deepcopy(c[0]);duplicate['candidate_id']='Z'
    alias=deepcopy(w[1]);alias.update(world_id='response_alias',mechanism='Distinct prose, same numeric scores',source_refs=['other_source'])
    chosen,receipt=run([duplicate]+list(reversed(c)),list(reversed(w))+[alias],b)
    assert [x['canonical_id'] for x in chosen]==[x['canonical_id'] for x in original]
    assert receipt['distinct_world_score_columns']==2 and receipt['original_worlds']==3
    assert receipt['distinct_canonical_rosters']==3 and receipt['candidate_variants']==4
    assert len(next(x for x in receipt['score_equivalent_worlds'] if len(x['aliases'])==2)['aliases'])==2


def test_captain_once_unknown_score_and_no_count_bonus():
    c,w,b=inputs();chosen,r=run(c,w,b,requested=1)
    assert sum(x['conditional_points'] for x in r['selection_steps'][0]['world_assessments'][1]['player_contributions']) in {55,85}
    assert r['selection_steps'][0]['anchor_conditional_mean_points']==85 # 5*10 + Captain extra5 + variable30
    del w[1]['player_means'][PIDS[5]]
    with pytest.raises(ValueError,match='known finite'):run(c,w,b)
    c,w,b=inputs();w[1]['count_bonus']=4
    with pytest.raises(ValueError,match='bonuses'):run(c,w,b)


def test_completion_oracle_prevents_captain_exposure_dead_end():
    c,w,b=inputs()
    # A and B share Captain1. C has Captain2; a two-entry 50% Captain cap
    # therefore requires C even though B has greater contrary gain.
    c[2]['roster'][0]['role']='FLEX';c[2]['roster'][1]['role']='CPT'
    signatures={}
    from backend.app.product_services.shared_world_selection import _roster
    from backend.app.product_services.analyst_shadow import digest
    for row in c:signatures[digest(_roster(row,'showdown')[0])]=next(x['player_master_id'] for x in row['roster'] if x['role']=='CPT')
    calls=[]
    def oracle(**kw):
        calls.append(kw['prefix_ids']);r=proof(**kw)
        captains=[signatures[x] for x in kw['prefix_ids']]
        r['status']='infeasible' if len(captains)!=len(set(captains)) else 'feasible'
        return r
    chosen,r=run(c,w,b,oracle=oracle)
    assert names(chosen)==['A','C']
    assert r['status']=='completed' and r['achieved']==2
    assert calls[0]==()


def test_timeout_of_better_candidate_never_selects_inferior():
    c,w,b=inputs()
    def oracle(**kw):
        r=proof(**kw)
        if kw['prefix_ids']:r['status']='timeout'
        return r
    chosen,r=run(c,w,b,oracle=oracle)
    assert chosen==[] and r['status']=='bounded_incomplete' and r['achieved']==0


def test_underfill_bool_missing_anchor_and_lineage_are_explicit():
    c,w,b=inputs()
    def impossible(**kw):r=proof(**kw);r['status']='infeasible';return r
    chosen,r=run(c,w,b,requested=4,oracle=impossible)
    assert chosen==[] and r['status']=='infeasible_requested_portfolio'
    with pytest.raises(ValueError,match='boolean'):run(c,w,b,oracle=lambda **kw:True)
    del w[0]['anchor_basis']
    with pytest.raises(ValueError,match='anchor'):run(c,w,b)
    c,w,b=inputs();w[1]['input_sha256']='c'*64
    with pytest.raises(ValueError,match='lineage'):run(c,w,b)


def test_no_incremental_coverage_does_not_manufacture_variation():
    c,w,b=inputs();w[1]['player_means']=deepcopy(w[0]['player_means'])
    chosen,r=run(c,w,b)
    assert names(chosen)==['A','B']
    assert r['selection_steps'][1]['coverage_status']=='no_incremental_scenario_coverage'
    assert r['selection_steps'][1]['maximum_incremental_gain_points']==0


def test_oracle_bound_returns_explicit_incomplete():
    c,w,b=inputs();chosen,r=run(c,w,b,limits=Limits(max_oracle_calls=1))
    assert chosen==[] and r['stop_reason']=='oracle_call_limit'


def test_duplicate_roster_rejects_offsetting_role_salary_conflicts():
    c,w,b=inputs();duplicate=deepcopy(c[0]);duplicate['candidate_id']='offset'
    duplicate['roster'][0]['salary']+=100
    duplicate['roster'][1]['salary']-=100
    for variants in [c+[duplicate],[duplicate]+c]:
        with pytest.raises(ValueError,match='salary mapping'):run(variants,w,b)


def test_noncanonical_uuid_spellings_rejected_before_scoring():
    c,w,b=inputs();c[0]['roster'][0]['player_master_id']=PIDS[0].replace('-','')
    with pytest.raises(ValueError,match='canonical player UUID'):run(c,w,b)


def test_equal_roster_totals_retain_different_actor_allocations():
    c,w,b=inputs();alias=deepcopy(w[1]);alias['world_id']='other_allocation'
    # Both actors are FLEX in all candidates, so every total remains identical.
    alias['player_means'][PIDS[1]]+=7;alias['player_means'][PIDS[2]]-=7
    chosen,r=run(c,w+[alias],b)
    assert r['distinct_world_score_columns']==2
    original={x['world_id']:x for x in r['frozen_world_inputs']}
    assert original['response']['player_means'][PIDS[1]]==10
    assert original['other_allocation']['player_means'][PIDS[1]]==17
    shared=next(x for x in r['selection_steps'][0]['world_assessments'] if len(x['world_aliases'])==2)
    assert shared['player_contributions_representative_world_id']=='other_allocation'
    assert 'Frozen candidate-pool' in r['gap_diagnostic_basis']
