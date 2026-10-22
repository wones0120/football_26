"""Ledger-owned team count models, fresh immutable inference, no serving fits."""
from datetime import UTC, datetime
from copy import deepcopy
import json
import re

from sqlalchemy import text
from pydantic import BaseModel, ConfigDict, Field

from .evaluation_record import append_record, digest
from .factual_designation import clock
from .opportunity_source_publication import _managed_json
from .team_opportunity_matrix import build_team_matrix
from .team_opportunity_models import MODEL_DIRECTORY, load_team_family, predict_team_families

KIND = 'team_opportunity_model_publication'
CONTRACT = 'served_team_opportunity_v1'


class TeamModelPublicationRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    result_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')
    before_period:int=Field(ge=200001,le=220018,strict=True)


def _result(sha, *, before_period, cutoff, directory=None):
    value, _, _ = _managed_json(directory or MODEL_DIRECTORY, sha, max_bytes=2*1024*1024)
    if value.get('status') not in {'completed','actual_two_families_fitted_current_budget_predictions_not_yet_app_consumed'} or value.get('actual_family_fits') != 2:
        raise ValueError('Managed team fit result is incomplete')
    if clock(value['completed_at']) > clock(cutoff): raise ValueError('Team fit completed after decision')
    refs = value['model_refs']
    bundles = {family: load_team_family(refs[family],before_period=before_period,cutoff=cutoff,directory=directory)
               for family in ('tree','neural')}
    # Pair inference enforces identical target/preprocessing/training contracts.
    a=bundles['tree']['receipt'];b=bundles['neural']['receipt']
    if (a['family'],b['family'])!=('tree','neural') or any(a[k]!=b[k] for k in ('matrix_sha256','prepared_sha256','target_columns','preprocessing')):
        raise ValueError('Registered model families differ in frozen feature/target contract')
    if value['matrix']['feature_columns']!=a['preprocessing']['columns'] or value['matrix']['target_columns']!=a['target_columns']:
        raise ValueError('Managed result advertised feature/target contract differs from estimator')
    return value, bundles


def publish_team_models(session, *, result_sha256, before_period, now=None, directory=None):
    """Accept only a content-addressed server-produced result, never joblib/path."""
    if not 1<=before_period%100<=18:raise ValueError('Invalid team model publication period')
    if not re.fullmatch(r'[0-9a-f]{64}',result_sha256): raise ValueError('Invalid managed result SHA')
    now=clock(now or datetime.now(UTC))
    value,_=_result(result_sha256,before_period=before_period,cutoff=now,directory=directory)
    # Exact same registration is append-idempotent; no execution clock churn.
    rows=session.execute(text("SELECT record_id,record_json FROM target.evaluation_record WHERE kind=:kind AND record_json->'payload'->>'result_sha256'=:sha"),dict(kind=KIND,sha=result_sha256)).mappings().all()
    if rows:
        row=rows[0]
        if row['record_id']!='evaluation-'+digest(row['record_json']): raise ValueError('Model registry hash mismatch')
        return dict(record_id=row['record_id'],**row['record_json']['payload'],reused=True)
    payload=dict(contract=CONTRACT,result_sha256=result_sha256,published_at=now.isoformat(),
        trained_before_period=before_period,model_refs=value['model_refs'],
        feature_columns=value['matrix']['feature_columns'],target_columns=value['matrix']['target_columns'])
    rid=append_record(session,KIND,payload,source=dict(operation='publish_managed_team_count_models'))
    return dict(record_id=rid,**payload,reused=False)


def predict_registered_teams(session, weekly, source_context, games, markets, *, before_period, cutoff, directory=None):
    """Fresh target rows from verified full-source measurements and native quotes."""
    if source_context.get('status')!='available_descriptive':
        return dict(status='source_unavailable',reason=source_context.get('status'),predictions=None)
    facts=source_context['facts'];contexts=facts.get('contexts',{})
    if not {'defense','environment'}.issubset(contexts):
        return dict(status='source_component_missing',predictions=None)
    rows=session.execute(text("SELECT record_id,record_json FROM target.evaluation_record WHERE kind=:kind ORDER BY recorded_at DESC,record_id DESC LIMIT 100"),dict(kind=KIND)).mappings().all()
    chosen=None
    for row in rows:
        envelope=row['record_json'];value=envelope.get('payload',{})
        if clock(value['published_at'])>clock(cutoff):continue
        if row['record_id']!='evaluation-'+digest(envelope):raise ValueError('Model registry hash mismatch')
        result,bundles=_result(value['result_sha256'],before_period=before_period,cutoff=cutoff,directory=directory)
        if result['model_refs']!=value['model_refs']:raise ValueError('Registered model lineage changed')
        chosen=(row,value,bundles);break
    if chosen is None:return dict(status='model_unavailable',predictions=None)
    targets=[]
    for game in games:
        gid=game['game_id'];parts=gid.split('_')
        away,home=parts[2:]
        for team,opponent in ((away,home),(home,away)):
            targets.append(dict(game_id=gid,season=before_period//100,week=before_period%100,team=team,opponent=opponent))
    matrix=build_team_matrix(weekly,targets,[dict(defense=contexts['defense'],environment=contexts['environment'],
        source=source_context['provenance']['source'])],before_period=before_period,cutoff=cutoff,market_rows=markets)
    row,value,bundles=chosen
    predictions=predict_team_families(bundles['tree'],bundles['neural'],matrix['rows'],before_period=before_period)
    # Training matrix hashes identify model ancestry; fresh current rows have a
    # separate semantic identity, excluding acquisition/decision envelope clocks.
    current=deepcopy(matrix['rows'])
    semantic=dict(version=CONTRACT,feature_columns=matrix['feature_columns'],target_columns=matrix['target_columns'],
        rows=current,model_refs={k:{f:v for f,v in ref.items() if f not in {'path','published_at'}} for k,ref in value['model_refs'].items()},
        source_measurements_sha256=source_context['semantic_measurements_sha256'])
    return dict(status='forecast_complete',version=CONTRACT,before_period=before_period,
        predictions=predictions,inference_rows=current,inference_matrix_sha256=digest(semantic),
        semantic_values=semantic,model_publication_record_id=row['record_id'],model_refs=value['model_refs'],
        source_measurements_sha256=source_context['semantic_measurements_sha256'],
        provenance=dict(decision_cutoff_at=str(cutoff),model_published_at=value['published_at'],
            markets=deepcopy(markets),source=source_context['provenance']),
        limitations=matrix['limits'])
