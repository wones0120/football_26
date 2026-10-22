"""Isolated server registry/current-source contracts; no fits, DB, or fetch."""
from copy import deepcopy
from types import SimpleNamespace
from pathlib import Path
import hashlib
import json

import numpy as np
import pytest

from backend.app.product_services import team_opportunity_serving as serving
from backend.app.product_services.evaluation_record import digest
from backend.app.product_services.team_opportunity_models import freeze_team_family
from backend.app.product_services.team_opportunity_matrix import FEATURES
from backend.app.tests.product.test_team_opportunity_models import bundle
from backend.app.tests.product.test_team_opportunity_matrix import contexts,weekly,live_market,CUTOFF


class FieldHead:
    def __init__(self,index):self.index=index
    def predict(self,x):return x[:,self.index]*.02


class FieldPair:
    def predict(self,x):return np.column_stack((x[:,FEATURES.index('game_total_line')]*.03,x[:,FEATURES.index('team_spread_line')]*.03))


class Ledger:
    def __init__(self):self.records=[]
    def execute(self,sql,params):
        records=self.records
        if 'sha' in params:records=[r for r in records if r['record_json']['payload']['result_sha256']==params['sha']]
        return SimpleNamespace(mappings=lambda:SimpleNamespace(all=lambda:list(reversed(records))))


@pytest.fixture
def fixture(tmp_path,monkeypatch):
    models={family:bundle(family) for family in ('tree','neural')}
    # This fixture's fake heads explicitly consume markets. The generic bundle
    # was prepared without markets, so remove their never-observed masks here;
    # otherwise the serving test correctly freezes both quotes as unknown.
    for model in models.values():
        p=model['receipt']['preprocessing']
        p['entirely_missing_train_columns']=[k for k in p['entirely_missing_train_columns']
            if k not in {'game_total_line','team_spread_line'}]
    models['tree']['estimators']=[FieldHead(FEATURES.index('game_total_line')),FieldHead(FEATURES.index('team_spread_line'))]
    models['neural']['estimators']=FieldPair()
    refs={family:freeze_team_family(value,directory=tmp_path,producer_clock=lambda:'2026-10-19T19:00:00Z') for family,value in models.items()}
    value=dict(status='actual_two_families_fitted_current_budget_predictions_not_yet_app_consumed',actual_family_fits=2,
        completed_at='2026-10-19T19:00:00Z',model_refs=refs,matrix=dict(feature_columns=list(FEATURES),target_columns=['pass_attempts','rush_attempts']))
    def save(value):
        payload=json.dumps(value,sort_keys=True,separators=(',',':')).encode();sha=hashlib.sha256(payload).hexdigest();(tmp_path/(sha+'.json')).write_bytes(payload);return sha
    sha=save(value);ledger=Ledger()
    def append(session,kind,payload,*,source=None,run_id=None):
        envelope=dict(contract='evaluation_record_v1',kind=kind,optimizer_run_id=run_id,source=source,payload=deepcopy(payload))
        rid='evaluation-'+digest(envelope);session.records.append(dict(record_id=rid,record_json=envelope));return rid
    monkeypatch.setattr(serving,'append_record',append)
    context=contexts()[0]
    source=dict(status='available_descriptive',before_period=202606,facts=dict(contexts=context),semantic_measurements_sha256='a'*64,
        provenance=dict(source=dict(snapshot_id='actual-shaped-source',captured_at='2026-10-19T18:00:00Z')))
    return SimpleNamespace(root=tmp_path,models=models,refs=refs,value=value,sha=sha,save=save,ledger=ledger,source=source)


def publish(f):return serving.publish_team_models(f.ledger,result_sha256=f.sha,before_period=202606,now=CUTOFF,directory=f.root)

def predict(f,source=None,markets=None):
    return serving.predict_registered_teams(f.ledger,weekly(),source or f.source,[dict(game_id='2026_06_BUF_MIA')],
        [live_market()] if markets is None else markets,before_period=202606,cutoff=CUTOFF,directory=f.root)


def test_actual_result_schema_pair_validation_does_not_predict_empty_and_registry_idempotent(fixture):
    first=publish(fixture);second=publish(fixture)
    assert first['record_id']==second['record_id'] and second['reused']
    assert len(fixture.ledger.records)==1
    assert first['target_columns']==['pass_attempts','rush_attempts']
    assert first['feature_columns']==list(FEATURES)


def test_real_shaped_current_inference_separates_training_hash_and_source_lineage(fixture):
    publish(fixture);result=predict(fixture)
    assert result['status']=='forecast_complete'
    assert {p['team'] for p in result['predictions']}=={'BUF','MIA'}
    assert result['inference_matrix_sha256']!=result['predictions'][0]['matrix_sha256']
    assert result['source_measurements_sha256']=='a'*64
    assert all(row['labels']==dict(pass_attempts=None,rush_attempts=None) for row in result['inference_rows'])
    assert all('components' in p and 'disagreement' in p for p in result['predictions'])
    assert result['provenance']['markets'][0]['source_snapshot_id']=='raw'


def test_fresh_actual_market_inputs_change_prediction_and_current_semantic_hash(fixture):
    publish(fixture);base=predict(fixture);changed=predict(fixture,markets=[live_market()|dict(game_total=49.5)])
    assert base['inference_matrix_sha256']!=changed['inference_matrix_sha256']
    assert base['predictions'][0]['counts']!=changed['predictions'][0]['counts']
    values={r['team']:r['features'] for r in base['inference_rows']}
    assert values['BUF']['team_spread_line']==3 and values['MIA']['team_spread_line']==-3
    assert values['BUF']['game_total_line']==48.5


def test_equivalent_current_quote_recapture_clocks_do_not_change_numeric_inputs(fixture):
    publish(fixture);base=predict(fixture)
    recaptured=live_market()|dict(observed_at='2026-10-19T19:10:00Z',ingested_at='2026-10-19T19:11:00Z',market_snapshot_id='new-capture')
    other=predict(fixture,markets=[recaptured])
    assert base['inference_rows']==other['inference_rows']
    assert base['inference_matrix_sha256']==other['inference_matrix_sha256']
    assert base['predictions']==other['predictions']
    assert base['provenance']!=other['provenance']


def test_source_component_and_model_unavailability_never_invent_forecasts(fixture):
    assert predict(fixture)['status']=='model_unavailable'
    missing=deepcopy(fixture.source);missing['status']='unavailable'
    assert predict(fixture,source=missing)['status']=='source_unavailable'
    missing=deepcopy(fixture.source);missing['facts']['contexts'].pop('defense')
    assert predict(fixture,source=missing)['status']=='source_component_missing'


def test_future_registration_excluded_and_corrupt_latest_registration_not_fallback(fixture):
    publish(fixture);entry=fixture.ledger.records[-1]
    entry['record_json']['payload']['published_at']='2026-10-20T01:00:00Z';entry['record_id']='evaluation-'+digest(entry['record_json'])
    assert predict(fixture)['status']=='model_unavailable'
    entry['record_json']['payload']['published_at']=CUTOFF;entry['record_id']='evaluation-'+digest(entry['record_json'])
    bad=deepcopy(entry);bad['record_json']['payload']['model_refs']['tree']['matrix_sha256']='wrong';bad['record_id']='evaluation-'+digest(bad['record_json'])
    fixture.ledger.records.append(bad)
    with pytest.raises(ValueError,match='lineage changed'):predict(fixture)


def test_pair_contract_and_future_model_completion_rejected(fixture):
    value=deepcopy(fixture.value);value['completed_at']='2026-10-20T00:00:00Z'
    with pytest.raises(ValueError,match='after decision'):
        serving.publish_team_models(fixture.ledger,result_sha256=fixture.save(value),before_period=202606,now=CUTOFF,directory=fixture.root)
    model=fixture.models['neural'];model['receipt']['prepared_sha256']='b'*64
    ref=freeze_team_family(model,directory=fixture.root,producer_clock=lambda:'2026-10-19T19:00:00Z')
    value=deepcopy(fixture.value);value['model_refs']['neural']=ref
    with pytest.raises(ValueError,match='frozen feature/target'):
        serving.publish_team_models(fixture.ledger,result_sha256=fixture.save(value),before_period=202606,now=CUTOFF,directory=fixture.root)


def test_late_live_market_rejected_and_missing_line_remains_masked(fixture):
    publish(fixture)
    with pytest.raises(ValueError,match='before decision/lock'):
        predict(fixture,markets=[live_market()|dict(observed_at='2026-10-20T01:00:00Z')])
    result=predict(fixture,markets=[])
    assert all(r['features']['game_total_line'] is None for r in result['inference_rows'])
    assert all(r['market_context']['status']=='missing' for r in result['inference_rows'])


@pytest.mark.parametrize('field',['feature_columns','target_columns'])
def test_managed_result_cannot_advertise_a_different_estimator_contract(fixture,field):
    value=deepcopy(fixture.value);value['matrix'][field]=['different']
    with pytest.raises(ValueError,match='advertised feature/target'):
        serving.publish_team_models(fixture.ledger,result_sha256=fixture.save(value),before_period=202606,now=CUTOFF,directory=fixture.root)


def test_model_publication_request_has_no_client_path_or_nonregular_period(fixture):
    with pytest.raises(ValueError):
        serving.TeamModelPublicationRequest(result_sha256=fixture.sha,before_period=202606,path='/tmp/caller.joblib')
    with pytest.raises(ValueError):
        serving.TeamModelPublicationRequest(result_sha256=fixture.sha,before_period=True)
    with pytest.raises(ValueError,match='publication period'):
        serving.publish_team_models(fixture.ledger,result_sha256=fixture.sha,before_period=202619,now=CUTOFF,directory=fixture.root)
