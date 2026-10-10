from copy import deepcopy

import pandas as pd
import pytest

from backend.app.product_services.classic_strategy_contract import digest
from scripts.shadow_sunday_workload import evidence_rows, workload_contract


def contract():
    source = dict(strategy_id='classic', effective=dict(
        players=[dict(player_id='canonical', projection=10., ceiling=20., salary=5000,
                      tags=['starter'], ownership=.2)],
        pipeline_options={'num_lineups':5, 'max_exposure':.8},
        resolved_config={'objective_weights':{'projection':.35, 'ceiling':.45}}))
    source['effective_sha256'] = digest(source['effective'])
    source['sha256'] = digest(source)
    return source


def test_workload_shadow_preserves_every_non_projection_input_and_source():
    source = contract()
    original = deepcopy(source)
    result = workload_contract(source, pd.DataFrame([dict(player_id='canonical',mean=12.,p90=22.)]).set_index('player_id'))
    assert source == original
    expected = deepcopy(source['effective'])
    expected['players'][0].update(projection=12.,ceiling=22.)
    assert result['effective'] == expected
    assert result['execution_mode'] == 'RESEARCH_SHADOW'
    assert result['effective_sha256'] == digest(expected)
    unsigned = deepcopy(result)
    unsigned.pop('sha256')
    assert result['sha256'] == digest(unsigned)


@pytest.mark.parametrize('mean,ceiling', [(float('nan'),20),(-1,20),(25,20)])
def test_invalid_shadow_forecasts_fail_closed(mean,ceiling):
    with pytest.raises(ValueError, match='Invalid shadow prediction'):
        workload_contract(contract(),pd.DataFrame([dict(player_id='canonical',mean=mean,p90=ceiling)]).set_index('player_id'))


def test_missing_player_is_not_silently_replaced_or_joined_by_name():
    with pytest.raises(KeyError):
        workload_contract(contract(),pd.DataFrame([dict(player_id='another-id',mean=12,p90=22)]).set_index('player_id'))


def test_derived_forecasts_do_not_fill_explicit_evidence_and_partial_history_is_visible():
    row = dict(player_id='canonical',position='RB',season=2026,
               projected_carries=12,projected_targets=3,
               opportunity_history_status='same_team_common_window',
               opportunity_history_observed_games=1,
               opportunity_history_window=[dict(season=2025,week=18),dict(season=2026,week=1)])
    result = evidence_rows(pd.DataFrame([row]))[0]
    assert len(result['missing_explicit_fields']) == 6
    assert result['projected_carries'] == 12
    assert set(result['review_reasons']) == {'partial_current_team_window','prior_season_window'}


def test_missing_history_stays_a_review_exception():
    row = dict(player_id='canonical',position='WR',season=2026,
               projected_targets=None,opportunity_history_status='no_same_team_window_history',
               opportunity_history_window=[])
    result = evidence_rows(pd.DataFrame([row]))[0]
    assert result['projected_targets'] is None
    assert result['review_reasons'] == ['missing_current_team_history']
