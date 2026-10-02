"""Prospective discovery contracts and canonical Week 4 regression fixtures."""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import json
from pathlib import Path

import pulp
import pytest

from backend.app.product_services.classic_candidate_completeness import (
    DiscoveryRequest, admission_lineage, capture_model, compare_targets,
    constrained_model, discovery_requests, diversity, enumerate_frontier,
    load_context, meaningful_players, recall, roster_key, saturation, solve_request,
    validate_prospective,
)
from backend.app.product_services.classic_prospective import digest_payload
from backend.app.product_services.gpp_optimizer import (
    LineupTagCaps, ObjectiveWeights, Player, PortfolioTargets, SlateConfig,
    StackRules, TagThresholds,
)

ROOT = Path(__file__).resolve().parents[4]
INPUTS = ROOT / 'artifacts/week4-thesis-frozen-analysis-inputs-8b5c114c.json'
ARTIFACT = ROOT / 'artifacts/candidate_completeness/week4-8b5c114c-reviewed.json'


def _row(ids, score=10, qb='q', game='A|B', family='q|QB+1|BB0'):
    return {'player_ids': ids, 'objective_score': score, 'mean': score,
            'qb': {'player_id': qb}, 'game_key': game, 'family_key': family}


def _oracle(rows):
    def solve(cuts):
        available = [r for r in rows if roster_key(r) not in cuts]
        return {'status': 'optimal', **max(available, key=lambda r: r['objective_score'])} if available else {'status': 'infeasible'}
    return solve


def test_deterministic_enumeration_and_exact_uniqueness():
    rows = [_row(['q', 'a', 'b'], 10), _row(['q', 'a', 'c'], 9.99), _row(['q', 'b', 'c'], 9.99)]
    a = enumerate_frontier(_oracle(rows), safety_max=10, tolerance=.20)
    b = enumerate_frontier(_oracle(rows), safety_max=10, tolerance=.20)
    assert a == b
    assert len(a['rows']) == 3
    assert a['complete'] and a['stop'] == 'exhausted'
    assert len({roster_key(r) for r in a['rows']}) == 3


def test_selector_tolerance_inclusive_boundary_and_safety_censoring():
    rows = [_row(['a'], 10), _row(['b'], 9.8), _row(['c'], 9.79)]
    result = enumerate_frontier(_oracle(rows), safety_max=10, tolerance=.2)
    assert [r['player_ids'] for r in result['rows']] == [['a'], ['b']]
    assert result['stop'] == 'tolerance' and result['boundary_score'] == 9.79
    censored = enumerate_frontier(_oracle(rows), safety_max=1, tolerance=.2)
    assert not censored['complete'] and censored['stop'] == 'safety_max'
    unproven = enumerate_frontier(lambda _: {'status': 'unproven'}, safety_max=2, tolerance=.2)
    assert not unproven['complete']


def test_no_good_cut_failure_is_not_silent():
    with pytest.raises(ValueError, match='No-good cut'):
        enumerate_frontier(lambda _: {'status': 'optimal', **_row(['a'])}, safety_max=2, tolerance=None)


def test_numerical_nonmonotonic_sequence_is_unproven():
    rows = iter([{'status': 'optimal', **_row(['a'], 10)}, {'status': 'optimal', **_row(['b'], 10.01)}])
    result = enumerate_frontier(lambda _: next(rows), safety_max=2, tolerance=.2)
    assert result['stop'] == 'numerical_nonmonotonic' and not result['complete']
    assert result['numerical_warning']['next_score'] == 10.01


def _toy_context():
    players = []
    for team, opponent in [('A', 'B'), ('C', 'D')]:
        for pos, count in [('QB', 1), ('RB', 3), ('WR', 4), ('TE', 1), ('DST', 1)]:
            for i in range(count):
                pid = f'{team}_{pos}_{i}'
                players.append(Player(pid, pid, team, opponent, pos, 4000,
                    10 + i * .27, 18 + i * .33, 5, game_id=f'{team}@{opponent}',
                    optimizer_receiving_role_strength=.6 if pos in {'WR', 'TE'} else 0))
    config = SlateConfig(StackRules(min_bring_backs=0, max_from_team=7, pass_catcher_positions=['WR', 'TE']),
        TagThresholds(), ObjectiveWeights(projection=1, ceiling=.2, leverage=0, correlation=0),
        LineupTagCaps(max_chalk=9, min_leverage=0, max_punts=9), portfolio_targets=PortfolioTargets())
    return {'players': players, 'config': config,
            'options': {'enforce_single_te': True, 'avoid_dst_opponents': True, 'locked_player_ids': []},
            'excluded': set(), 'elevated': {'A_WR_0', 'C_WR_0'},
            'policy': {'max_elevated_per_lineup': 1}, 'source': {}, 'caps': {p.player_id: 1 for p in players}}


def test_real_solver_capture_and_no_good_roster_cuts_preserve_production_factory():
    from backend.app.product_services import gpp_optimizer
    context = _toy_context()
    factory = gpp_optimizer.make_cbc_solver
    base = capture_model(context)
    assert gpp_optimizer.make_cbc_solver is factory
    request = DiscoveryRequest('test', safety_max=3)
    a = solve_request(base, context, request, 'bundled')
    b = solve_request(base, context, request, 'bundled')
    assert [r['player_ids'] for r in a['rows']] == [r['player_ids'] for r in b['rows']]
    assert len(a['rows']) == len({roster_key(r) for r in a['rows']}) == 3
    assert len(base.constraints) < len(constrained_model(base, context, request).constraints)
    assert all(len(set(r['player_ids']) & context['elevated']) <= 1 for r in a['rows'])


def test_qb_stack_templates_player_forcing_and_structures_are_player_agnostic():
    context = _toy_context()
    requests = discovery_requests(context, [])
    for qb in ['A_QB_0', 'C_QB_0']:
        assert {r.template for r in requests if r.source == 'qb_direction' and r.qb_id == qb} == {(n, b) for n in (1, 2, 3) for b in (0, 1)}
        partner = [r for r in requests if r.source == 'stack_partner' and r.qb_id == qb]
        assert {len(r.required_ids) for r in partner} == {1, 2, 3}
        assert any(any('_TE_' in p for p in r.required_ids) for r in partner)
    assert {r.required_ids[0] for r in requests if r.source == 'player_forced'} == {p.player_id for p in meaningful_players(context, [])}
    assert 'structure:flex:TE' not in {r.source for r in requests}
    base = capture_model(context)
    result = solve_request(base, context, DiscoveryRequest('player_forced', required_ids=('C_WR_3',)), 'bundled')
    assert result['rows'] and 'C_WR_3' in result['rows'][0]['player_ids']
    with pytest.raises(ValueError, match='ineligible'):
        constrained_model(base, context, DiscoveryRequest('bad', required_ids=('missing',)))
    with pytest.raises(ValueError, match='relax'):
        constrained_model(base, context, DiscoveryRequest('bad', qb_id='A_QB_0', template=(0, 0)))


def test_raw_vs_admitted_exact_primary_reasons_and_swap_evidence():
    a, b, c, injury = _row(['q', 'a'], 10), _row(['r', 'b'], 9), _row(['q', 'b'], 8), _row(['x', 'y'], 7)
    # Both q and b already at 1/2. A direct insertion conflicts with both; no
    # single swap works and no equal-cardinality feasible subset contains c.
    rows = [a, b, c, injury, deepcopy(a)]
    reasons = admission_lineage(rows, [a, b], {'q': .5, 'b': .5}, {'x', 'y'}, 1, 'bundled')
    assert [r['primary_reason'] for r in reasons] == ['accepted_into_candidate_pool', 'accepted_into_candidate_pool',
        'player_cap_conflict', 'injury_risk_rejected', 'duplicate_rejected']
    assert {r['player_id'] for r in reasons[2]['aggregate_cap_conflicts']} == {'q', 'b'}
    assert all(r['exposure_before_admission'] == 1 and r['cap_count'] == 1 for r in reasons[2]['aggregate_cap_conflicts'])
    d = _row(['q', 'z'], 8)
    reason = admission_lineage([a, b, d], [a, b], {'q': .5}, set(), 1, 'bundled')[-1]
    assert reason['primary_reason'] == 'admission_target_competition'
    assert reason['single_swap_feasible'] and reason['joint_displacement_feasible']
    assert reason['displaceable_roster_sha256']
    assert len(reason['stage_trace']) == 10
    assert next(s for s in reason['stage_trace'] if s['stage'] == 'quality_threshold')['status'] == 'not_applied'
    assert rows == [a, b, c, injury, a]  # diagnostics did not mutate source rosters


def test_family_and_quality_reasons_remain_distinct():
    rows = [_row(['a'], 10), _row(['b'], 8), _row(['c'], 7)]
    reasons = admission_lineage(rows, [rows[0]], {}, set(), 1, 'bundled',
        family_allowed=lambda r: r['player_ids'] != ['b'], quality_floor=9)
    assert [r['primary_reason'] for r in reasons] == ['accepted_into_candidate_pool', 'family_constraint', 'quality_threshold']


def test_unlimited_player_is_not_reported_as_an_exposure_conflict():
    rows = [_row(['q', 'a'], 10), _row(['q', 'b'], 9), _row(['q', 'c'], 8)]
    reasons = admission_lineage(rows, rows[:2], {}, set(), 1, 'bundled')
    assert reasons[-1]['aggregate_cap_conflicts'] == []
    assert reasons[-1]['primary_reason'] == 'admission_target_competition'


def test_solver_request_duplicates_retain_separate_stage_lineage():
    from scripts.render_candidate_completeness import discovery_stage_audit
    unique = _row(['a', 'b'])
    ledger = admission_lineage([unique], [unique], {}, set(), 1, 'bundled')
    evidence = {'sha256': 'fixture', 'historical_raw_candidates': [], 'player_coverage': [],
                'targets': {'205': {'lineage': ledger}}, 'solve_events': [
                    {'status': 'optimal', 'player_ids': ['a', 'b'], 'objective_score': 10, 'source': 'frontier', 'request': {}, 'seconds': 1},
                    {'status': 'optimal', 'player_ids': ['b', 'a'], 'objective_score': 10, 'source': 'forced', 'request': {}, 'seconds': 1},
                    {'status': 'infeasible', 'source': 'template', 'request': {}, 'seconds': 1}]}
    result = discovery_stage_audit(evidence)
    assert result['legal_solved'] == 2 and result['duplicate_rejected'] == 1
    assert result['events'][0]['target_primary_reason']['205'] == 'accepted_into_candidate_pool'
    assert result['events'][1]['target_primary_reason']['205'] == 'duplicate_rejected'
    assert len(result['events'][1]['target_stage_trace']['205']) == 10
    assert result['events'][2]['discovery_primary_reason'] == 'solver_request_infeasible'


def test_candidate_targets_use_same_raw_universe_without_source_mutation():
    context = _toy_context()
    rows = [_row(['A_QB_0', p.player_id], 10 - i) for i, p in enumerate(context['players'][1:5])]
    before = deepcopy(rows)
    compared = compare_targets(rows, context, (2, 3), 'bundled', 10)
    assert compared['2']['diversity']['count'] == 2
    assert compared['3']['diversity']['count'] == 3
    assert rows == before
    assert compared['2']['admitted'][0]['objective_score'] == 10


def test_recall_uses_canonical_roster_intersection_and_inclusive_tolerances():
    rows = [_row(['q', 'a'], 10), _row(['q', 'b'], 9.8), _row(['q', 'c'], 9.7)]
    result = recall(rows, [_row(['a', 'q'], 10), _row(['unrelated'], 12)], 10)
    assert result['0.05']['recall'] == 1
    assert result['0.20'] == {'known_legal': 2, 'discovered': 1, 'recall': .5}
    assert result['0.30']['recall'] == pytest.approx(1 / 3)
    assert recall([], [], 10)['0.20']['recall'] is None
    assert recall(rows + [rows[0]], rows, 10)['0.05']['known_legal'] == 1


def test_saturation_requires_complete_quiet_blocks_and_tracks_new_information():
    events = [{'candidate': _row(['q', 'a'], 10)}] + [{'status': 'infeasible'}] * 149
    result = saturation(events, 10)
    assert result['proposed_stop_solve'] == 150
    assert result['curve'][0]['new_unique'] == 1
    assert result['curve'][0]['new_within_tolerance']['0.20'] == 1
    assert saturation(events[:125], 10)['proposed_stop_solve'] is None
    enriched = events + [{'candidate': _row(['r', 'b'], 9.9, qb='r', game='C|D', family='r|QB+3|BB0')}]
    last = saturation(enriched, 10)['curve'][-1]
    assert last['new_qbs'] == last['new_games'] == last['new_stack_families'] == 1
    assert last['quiet_blocks'] == 0


def test_diversity_reports_exact_average_overlap():
    rows = [_row(['q', 'a'], 10), _row(['q', 'b'], 9), _row(['r', 'b'], 8, qb='r')]
    result = diversity(rows)
    assert result['average_overlap'] == pytest.approx(2 / 3)
    assert result['duplication'] == 0 and result['qb_directions'] == 2


@pytest.fixture(scope='module')
def frozen_inputs():
    return json.loads(INPUTS.read_text())


def test_no_postgame_or_postdecision_leakage_and_prelock_guard(frozen_inputs):
    validate_prospective(frozen_inputs, now=datetime(2026, 9, 30, tzinfo=UTC))
    with pytest.raises(ValueError, match='before'):
        validate_prospective(frozen_inputs, now=datetime(2026, 10, 5, tzinfo=UTC))
    for key, value in [('actual_points', 99), ('market_observed_at', '2026-10-04T18:00:00Z')]:
        bad = deepcopy(frozen_inputs)
        s = bad['report']['frozen_solver_snapshot']
        s['payload']['pool_rows'][0][key] = value
        s['sha256'] = digest_payload(s['payload'])
        with pytest.raises(ValueError, match='Postgame|Outcome|cutoff'):
            validate_prospective(bad, now=datetime(2026, 9, 30, tzinfo=UTC))


@pytest.fixture(scope='module')
def evidence():
    if not ARTIFACT.exists():
        pytest.skip('Run the offline prospective fixture experiment to create its evidence artifact')
    data = json.loads(ARTIFACT.read_text())
    assert digest_payload({k: v for k, v in data.items() if k != 'sha256'}) == data['sha256']
    return data


@pytest.mark.parametrize('label,pid', [
    ('Bucky', 'a9f8d797-040e-4469-b9d5-bb39bf3792b2'),
    ('Bowers', 'af2cef33-41db-4417-b880-13885bff6921'),
    ('Jefferson', '37b2e76d-353b-4b03-8a4a-652774647103'),
    ('JSN', '1838dd60-35e8-4018-b307-39cde90e1f03'),
])
def test_week4_near_frontier_regressions(label, pid, evidence):
    rows = [r for r in evidence['raw_candidates'] if pid in r['player_ids']]
    best = max(rows, key=lambda r: r['objective_score'])
    assert evidence['frontier'] - best['objective_score'] <= .20 + 1e-9
    assert any(r['request']['source'] == 'player_forced' and r['request']['required_ids'] == [pid]
               for r in evidence['requests'])  # selected by the automatic pregame screen
    assert any('player_forced' in evidence['provenance']['|'.join(sorted(r['player_ids']))] for r in rows)
    if label == 'JSN':
        assert any(r['stack']['partner_count'] == 3 and evidence['frontier'] - r['objective_score'] <= .20 + 1e-9 for r in rows)
    # New discovery sources always enforce frozen elevated-questionable limits.
    risk = {r['player_id'] for r in json.loads(INPUTS.read_text())['report']['prospective_experiment']['availability_risk']['players'] if r['bucket'] == 'questionable_elevated'}
    assert all(len(set(r['player_ids']) & risk) <= 1 for r in rows
               if any(s in evidence['provenance']['|'.join(sorted(r['player_ids']))] for s in ['player_forced', 'qb_frontier', 'stack_partner', 'qb_direction']))


def test_lamar_negative_control(evidence):
    pid = 'ccab2695-91ed-49ce-b78b-938f23f4739b'
    rows = [r for r in evidence['raw_candidates'] if pid in r['player_ids']]
    assert rows
    assert evidence['frontier'] - max(r['objective_score'] for r in rows) > .30


def test_production_unchanged_and_historical_lineage_totals(evidence, frozen_inputs):
    validate_prospective(frozen_inputs, now=datetime(2026, 9, 30, tzinfo=UTC))
    r = frozen_inputs['report']
    assert len(r['all_candidates']) == 205
    assert evidence['production_candidate_sha256'] == digest_payload({'candidates': r['all_candidates']})
    assert evidence['production_selected_ranks'] == r['selected_ranks']
    assert len(evidence['historical_lineage']) == 286
    assert evidence['historical_reason_counts']['accepted_into_candidate_pool'] == 205
    assert evidence['historical_reason_counts']['injury_risk_rejected'] == 16
    assert sum(evidence['historical_reason_counts'].values()) == 286
    assert len({roster_key(c) for c in evidence['raw_candidates']}) == len(evidence['raw_candidates'])
    for target in ('205', '300', '400', '500'):
        result = evidence['targets'][target]
        assert sum(result['reason_counts'].values()) == len(evidence['raw_candidates'])
        assert result['diversity']['count'] <= int(target)
