from copy import deepcopy

import pytest

from backend.app.product_services.analyst_research_requests import semantic_dependencies
from backend.app.tests.product.test_analyst_preparation import inputs


def test_component_model_and_replacement_values_bind_once_per_game_not_execution_clocks():
    _,rows,_,result=inputs('SHOWDOWN');game=result['source_manifest']['games'][0]
    game.update(season=2099,week=1)
    season=game['season'];week=game['week'];period=season*100+week
    team=game['teams'][0]
    values=dict(reference=dict(players=[],teams={team:{}},availability_conditions={'semantic_sha256':'fraction-a'}),
        new=dict(players=[],teams={team:{}},availability_conditions={'semantic_sha256':'fraction-a'}),players=[],
        efficiency=dict(actors={},teams={team:{}}),reference_shared_budgets={},new_shared_budgets={})
    receipt=dict(version='SYNTHETIC',players=[],component_response=dict(before_period=period,semantic_values=values),
        team_opportunity_model_inference=dict(status='forecast_complete',semantic_values=dict(version='SYNTHETIC-model',rows=[]),
            inference_rows=[dict(game_id=game['game_id'],features=dict(game_total_line=50))]))
    def dep():return semantic_dependencies(games=result['source_manifest']['games'],rows=rows,checked_at='2099-09-01T12:30:00Z',
        source_manifest=result['source_manifest'],workload_receipt=receipt)
    original=dep()
    receipt['team_opportunity_model_inference']['provenance']={'decision_cutoff_at':'2099-09-01T12:29:00Z'}
    assert dep()['dependency_sha256']==original['dependency_sha256']
    for mutate in ('component','model','replacement','features'):
        before=deepcopy(receipt)
        if mutate=='component':receipt['component_response']['semantic_values']['players']=[dict(team=team,delta_points=1)]
        if mutate=='model':receipt['team_opportunity_model_inference']['semantic_values']['version']='changed-model'
        if mutate=='replacement':receipt['component_response']['semantic_values']['new']['availability_conditions']['semantic_sha256']='fraction-b'
        if mutate=='features':receipt['team_opportunity_model_inference']['inference_rows'][0]['features']['game_total_line']=51
        assert dep()['dependency_sha256']!=original['dependency_sha256']
        receipt.clear();receipt.update(before)
    receipt['component_response']['before_period']=period-1
    with pytest.raises(ValueError,match='period differs'):dep()
