from copy import deepcopy

import pytest

from research.game_progression_pilot_20261020.player_opportunity_accounting.allocation import allocate, CHANNELS
from research.game_progression_pilot_20261020.player_opportunity_accounting.fixtures import inputs, cases


@pytest.mark.parametrize('name,case', cases())
def test_conservation_and_input_preservation(name, case):
    before = deepcopy(case)
    result = allocate(**case)
    assert case == before and allocate(**case) == result
    assert not result['activation'] and not result['forecast_validated']
    assert result['physical_play_count'] is None and result['scoring'] is None
    for channel, row in result['accounting'].items():
        if row['team_budget'] is None:
            assert row['residual_mean'] is None and row['status'] == 'UNKNOWN_TEAM_BUDGET'
        else:
            assert row['assigned_known_mean'] + row['residual_mean'] == pytest.approx(row['team_budget'])
            assert row['assigned_known_mean'] == pytest.approx(sum(
                p['conditional_mean_counts'][channel] or 0 for p in result['players']))
    if name == 'partial_full_team':
        assert result['accounting']['targets']['residual_mean'] == 5
        assert result['accounting']['rush_attempts']['residual_mean'] == 4
        assert result['no_target_pass_mean'] == 5
    if name in {'unknown_role', 'unknown_availability', 'unavailable_vacancy'}:
        assert result['accounting']['targets']['residual_mean'] == 15
        assert result['players'][1]['conditional_mean_counts']['targets'] == 5
    if name == 'zero_budget':
        assert all(v == 0 for p in result['players'] for v in p['conditional_mean_counts'].values())


@pytest.mark.parametrize('value', [-1, float('nan'), float('inf'), True, '3'])
def test_invalid_budgets_rejected(value):
    case = inputs(); case['budgets']['targets'] = value
    with pytest.raises(ValueError): allocate(**case)


@pytest.mark.parametrize('value', [-.1, 1.1, float('nan'), float('inf'), True, '.4'])
def test_invalid_role_shares_rejected(value):
    case = inputs(); case['role_snapshot']['actors'][2]['shares']['targets'] = value
    with pytest.raises(ValueError): allocate(**case)


@pytest.mark.parametrize('change', ['target_budget', 'overallocated', 'duplicate', 'display_name',
    'future', 'naive_clock', 'foreign_team', 'foreign_game', 'unavailable_work',
    'bad_availability', 'missing_channel', 'historical_claim'])
def test_invalid_scope_identity_chronology_and_accounting_rejected(change):
    case = inputs(); snapshot = case['role_snapshot']; actors = snapshot['actors']
    if change == 'target_budget': case['budgets']['targets'] = 31
    if change == 'overallocated': actors[2]['shares']['targets'] = .9
    if change == 'duplicate': actors.append(deepcopy(actors[2]))
    if change == 'display_name': actors[2]['player_master_id'] = 'Receiver Name'
    if change == 'future': snapshot['as_of'] = '2023-09-02T00:00:00Z'
    if change == 'naive_clock': snapshot['as_of'] = '2023-09-01T00:00:00'
    if change == 'foreign_team': snapshot['team'] = 'other-team'
    if change == 'foreign_game': snapshot['game_id'] = 'other-game'
    if change == 'unavailable_work': actors[2]['availability'] = 'unavailable'
    if change == 'bad_availability': actors[2]['availability'] = 'questionable-means-active'
    if change == 'missing_channel': del actors[2]['shares']['targets']
    if change == 'historical_claim': snapshot['evidence_kind'] = 'verified_historical'
    with pytest.raises(ValueError): allocate(**case)


def test_empty_actor_universe_retains_all_budget_as_residual():
    case = inputs(); case['role_snapshot']['actors'] = []
    result = allocate(**case)
    assert result['players'] == []
    for channel in CHANNELS:
        assert result['accounting'][channel]['residual_mean'] == case['budgets'][channel]


def test_unknown_pass_budget_cannot_certify_joint_pass_target_support():
    case = inputs(); case['budgets']['pass_attempts'] = None
    result = allocate(**case)
    assert result['joint_pass_target_support'] == 'UNKNOWN'
    assert result['no_target_pass_mean'] is None
    assert result['players'][0]['conditional_mean_counts']['pass_attempts'] is None
    assert result['accounting']['targets']['team_budget'] == 25


def test_omitting_salary_pool_member_leaves_residual_without_changing_other_means():
    case = inputs(); original = allocate(**case)
    del case['role_snapshot']['actors'][2]
    subset = allocate(**case)
    assert subset['accounting']['targets']['residual_mean'] == 15
    assert subset['players'][1] == original['players'][1]


def test_optimizer_preference_metadata_cannot_change_model_allocations():
    case = inputs(); original = allocate(**case)
    case['role_snapshot']['actors'][2]['optimizer_user_excluded'] = True
    assert allocate(**case) == original
