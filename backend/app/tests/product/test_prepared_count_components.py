"""Public Prepare producer seam: real count allocation and component response."""
from copy import deepcopy

import pytest

from backend.app.product_services import workload_count_forecast as counts
from backend.app.tests.product.test_count_component_response import fixture, IDS, NOW


def test_prepare_consumes_new_team_model_counts_into_player_and_fp_components(monkeypatch):
    weekly,reference,bases=fixture()
    monkeypatch.setattr(counts,'load_history',lambda *a,**k:weekly)
    monkeypatch.setattr('backend.app.product_services.workload_gamebook_participation.load_verified_gaps',lambda *a,**k:[])
    model=dict(training_max_period=202503,center=[0]*4,scale=[1]*4,coefficients=[[0]*4,[0]*4],intercept=[10,5])
    monkeypatch.setattr(counts,'fit_team_model',lambda *a,**k:deepcopy(model))
    issued=dict(status='forecast_complete',version='SYNTHETIC-validated-model',before_period=202604,
        predictions=[dict(team='BUF',counts=dict(pass_attempts=20.,rush_attempts=10.))],
        inference_matrix_sha256='SYNTHETIC-inference',source_measurements_sha256='SYNTHETIC-source')
    monkeypatch.setattr('backend.app.product_services.team_opportunity_serving.predict_registered_teams',lambda *a,**k:deepcopy(issued))
    pool=[dict(player_id=pid,team='BUF',player_team='BUF',position=position,projection=bases[pid],
        is_starting_qb=position=='QB',starting_qb_source='SYNTHETIC-sourced-role' if position=='QB' else None)
        for pid,position in zip(IDS,['QB','RB','WR'])]
    value=counts.prepare_receipt(None,pool,season=2026,week=4,cutoff=NOW,projection_run_id='SYNTHETIC-projection',
        opportunity_source_context={'status':'available_descriptive'},games=[{'game_id':'2026_04_BUF_MIA'}],markets=[])
    players={p['player_master_id']:p for p in value['players']}
    assert value['teams']['BUF']['pass_attempts']==20
    assert players[IDS[0]]['counts']['pass_attempts']==20
    assert players[IDS[2]]['counts']['targets']==pytest.approx(10.)
    assert value['reference_count_forecast']['teams']['BUF']['pass_attempts']==10
    response={p['player_master_id']:p for p in value['component_response']['players']}
    assert response[IDS[0]]['conditional_mean']==pytest.approx(12.4)
    assert response[IDS[2]]['conditional_mean']==pytest.approx(22.)
    assert value['team_budget_model_contract']['inference_matrix_sha256']=='SYNTHETIC-inference'
    assert len(value['sha256'])==64
