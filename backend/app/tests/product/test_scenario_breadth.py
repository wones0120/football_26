from copy import deepcopy

import pytest

from backend.app.product_services.scenario_allocation import AllocationControls, build_ideas, conditional_world, plan_slots
from backend.app.product_services.scenario_breadth import generate_pool, select_pool, signature, compose_world
from backend.app.tests.product.test_scenario_allocation import supported_fixture


def prepared():
    packet, snapshot = supported_fixture()
    original = deepcopy(packet['scenario_assumptions']['scenarios'][0])
    packet['scenario_assumptions']['scenarios'] = []
    for index, game in enumerate(packet['games']):
        scenario = deepcopy(original)
        scenario.update(scenario_id='game_' + str(index), assumptions=[a for a in original['assumptions'] if a['game_id'] == game['game_id']])
        packet['scenario_assumptions']['scenarios'].append(scenario)
    rows = snapshot['players']
    ideas, _ = build_ideas(packet, rows, AllocationControls())
    worlds = [conditional_world(i, rows, packet, AllocationControls()) for i in ideas]
    return snapshot, rows, ideas, worlds


def test_every_credible_idea_attempted_and_projection_truth_unchanged():
    snapshot, rows, ideas, worlds = prepared()
    before = deepcopy(snapshot)
    pool, audit = generate_pool(snapshot, rows, ideas, worlds, {}, 3)
    assert len(audit['attempts']) == 2 * len(ideas)
    assert {x['idea_id'] for x in audit['attempts']} == {i['idea_id'] for i in ideas}
    assert audit['distinct_canonical_rosters'] > 3
    assert all(c['construction_audit']['passed'] and len(c['roster']) == 9 for c in pool)
    assert all(len({signature(c) for c in pool if c['allocated_idea_id'] == i['idea_id']}) == 2 for i in ideas)
    assert snapshot == before
    assert audit['outcomes_used'] is False


def test_composition_is_disjoint_and_conserves_each_opportunity_budget():
    _, rows, ideas, worlds = prepared()
    first = worlds[0]
    other = next(w for i, w in zip(ideas, worlds) if i['game_id'] != ideas[0]['game_id'])
    joined = compose_world(first, other, rows)
    for key in ['opportunity_budget', 'supporting_opportunity_budget']:
        assert joined[key]['conditional_targets'] + joined[key]['conditional_carries'] == pytest.approx(100)
    with pytest.raises(ValueError, match='same game'):
        compose_world(first, first, rows)


def test_selector_preserves_caps_overlap_and_duplicate_rosters_not_extra_entries():
    snapshot, rows, ideas, worlds = prepared()
    pool, _ = generate_pool(snapshot, rows, ideas, worlds, {}, 3)
    pool += [deepcopy(pool[0])]
    plan = plan_slots(ideas, 3, AllocationControls())
    selected, result = select_pool(pool, worlds, rows, {'max_exposure': 1, 'max_lineup_overlap': 5}, 3, plan)
    assert result['achieved'] == 3 and not result['constraints_relaxed']
    assert len({signature(c) for c in selected}) == 3
    for i, c in enumerate(selected):
        for previous in selected[:i]:
            assert len(set(signature(c)) & set(signature(previous))) <= 5
    baseline, mean_result = select_pool(pool, worlds, rows, {'max_exposure': 1}, 3, plan, objective='BASELINE_MEAN')
    assert mean_result['objective'] == 'BASELINE_MEAN' and len(baseline) == 3
    assert 'highest summed baseline mean' in mean_result['selection_reason']


def test_zero_eligibility_and_missing_candidates_underfill_without_relaxation():
    snapshot, rows, ideas, worlds = prepared()
    params = {'maximum_exposure_by_player': {r['player_id']: 0 for r in rows}}
    pool, audit = generate_pool(snapshot, rows, ideas, worlds, params, 3)
    assert pool == [] and all(x['solver_status'] == 'Infeasible' for x in audit['attempts'])


def test_saved_replay_is_immutable_idempotent_and_rejects_hash_tamper(tmp_path):
    from backend.app.product_services.scenario_allocation import generate_allocated
    from backend.app.product_services.scenario_breadth_replay import build_from_config, read_replay
    snapshot, rows, ideas, worlds = prepared()
    plan = plan_slots(ideas, 3, AllocationControls())
    pool, _ = generate_pool(snapshot, rows, ideas, worlds, {}, 3)
    chosen, _ = select_pool(pool, worlds, rows, {}, 3, plan)
    config = dict(num_lineups=3, strategy_runtime={'football_analyst':dict(portfolio_mode='SCENARIO_FIRST', input_snapshot=snapshot, scenario_allocation_plan=plan, scenario_definitions=worlds, candidates=chosen)})
    first = build_from_config('00000000-0000-0000-0000-000000000001', config, directory=tmp_path, code_hash='test')
    second = build_from_config('00000000-0000-0000-0000-000000000001', config, directory=tmp_path, code_hash='test')
    assert first == second and first['research_only'] and not first['entry_clearance']
    assert first['projection_mutation'] is False and first['outcomes_used'] is False
    import json
    path = tmp_path / (first['replay_id'] + '.json')
    altered = json.loads(path.read_text()); altered['status'] = 'fake'; path.write_text(json.dumps(altered))
    with pytest.raises(ValueError, match='integrity'):
        read_replay(first['replay_id'], directory=tmp_path)


def test_external_complete_lineup_utility_preserves_truth_and_hard_controls():
    snapshot, rows, ideas, worlds = prepared()
    before=deepcopy(rows)
    pool,_=generate_pool(snapshot,rows,ideas,worlds,{},3)
    plan=plan_slots(ideas,3,AllocationControls())
    values=[i/max(1,len(pool)-1) for i in range(len(pool))]
    selected,result=select_pool(pool,worlds,rows,{'max_exposure':1,'max_lineup_overlap':5},3,plan,objective='EXTERNAL_LINEUP_SCORE',candidate_utilities=values)
    assert rows==before and len(selected)==3 and not result['constraints_relaxed']
    with pytest.raises(ValueError,match='External complete-lineup'):
        select_pool(pool,worlds,rows,{},3,plan,objective='EXTERNAL_LINEUP_SCORE',candidate_utilities=[float('nan')]*len(pool))


def test_shared_state_selector_values_complementary_complete_rosters_not_labels():
    snapshot,rows,ideas,worlds=prepared()
    pool,_=generate_pool(snapshot,rows,ideas,worlds,{},3)
    pool=list({signature(c):c for c in pool}.values())[:3]
    plan=plan_slots(ideas,2,AllocationControls())
    before=deepcopy(rows)
    # Same three legal rosters, two shared outcomes. Candidate0 is balanced;
    # candidates1/2 cover genuinely complementary outcomes under this fixture.
    values={'first':[6.,10.,0.],'second':[6.,0.,10.]}
    selected,audit=select_pool(pool,worlds,rows,{},2,plan,objective='JOINT_WORST_REGRET',joint_state_scores=values)
    assert {c['candidate_id']for c in selected}=={pool[1]['candidate_id'],pool[2]['candidate_id']}
    assert audit['joint_worst_relative_coverage']==pytest.approx(1)
    assert len(audit['joint_selection_stages'])==3 and rows==before
    assert not audit['constraints_relaxed']
    with pytest.raises(ValueError,match='joint-state'):
        select_pool(pool,worlds,rows,{},2,plan,objective='JOINT_WORST_REGRET',joint_state_scores={'bad':[1,float('nan'),2]})
