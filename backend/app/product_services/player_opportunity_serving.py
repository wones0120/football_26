"""Server-owned player-count artifact registry; inference never fits models.

Retrospective model contracts are usable for isolated evaluation, not as proof
that revised observations were available before a historical game.
"""
from datetime import UTC,datetime
from io import BytesIO
from pathlib import Path
import hashlib,json,re
from sqlalchemy import text
from .evaluation_record import append_record,digest
from .factual_designation import clock
from .feature_block_model_inputs import VERSION,ACTIVE_VERSION,ACTIVE_MODEL_VERSIONS,RB_RUSH_MEAN_VERSION,SPARSE_WR_VERSION,predict_player_families,apply_player_count_predictions
from .offensive_volume_features import ACTIVE_VERSION as ACTIVE_MATRIX_VERSION
from .offensive_volume_features import digest as matrix_digest

DIRECTORY=Path(__file__).resolve().parents[3]/'artifacts/player_opportunity_models'
KIND='player_opportunity_model_publication'
CONTRACT='served_player_opportunity_v1'


def _json(sha,directory):
    if not re.fullmatch(r'[0-9a-f]{64}',sha):raise ValueError('Invalid managed player result SHA')
    path=Path(directory or DIRECTORY).resolve()/(sha+'.json')
    if not path.is_file() or path.stat().st_size>8*1024*1024:raise ValueError('Missing or oversized managed player result')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Managed player result checksum mismatch')
    return json.loads(raw)


def _bundle(ref,*,directory,cutoff,before_period):
    # Joblib executes code: only refs from a verified server-produced result or
    # its ledger record reach this private loader; no client path/bytes API.
    import joblib
    sha=ref.get('sha256','')
    if not re.fullmatch(r'[0-9a-f]{64}',sha):raise ValueError('Invalid player model SHA')
    root=Path(directory or DIRECTORY).resolve();path=root/(sha+'.joblib')
    if Path(ref['path']).resolve()!=path or path.resolve().parent!=root:raise ValueError('Player model outside managed root')
    if path.stat().st_size!=ref['bytes'] or path.stat().st_size>32*1024*1024:raise ValueError('Player model size mismatch')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Player model byte hash mismatch')
    envelope=joblib.load(BytesIO(raw));bundle=envelope['bundle'];r=bundle['receipt']
    if envelope.get('contract')!='player_opportunity_model_artifact_v1' or ref.get('contract')!=envelope['contract']:raise ValueError('Unsupported player model artifact')
    if envelope['published_at']!=ref['published_at'] or clock(envelope['published_at'])>clock(cutoff) or clock(r['completed_at'])>clock(envelope['published_at']):raise ValueError('Player model unavailable at decision')
    if r['version'] not in {VERSION,*ACTIVE_MODEL_VERSIONS} or r['status']!='fit_complete' or r['family']!=ref['family'] or r['training_max_period']>=before_period:raise ValueError('Incomplete or future player model')
    if matrix_digest(r)!=ref['receipt_sha256']:raise ValueError('Player estimator metadata mismatch')
    if r['version'] in {RB_RUSH_MEAN_VERSION,SPARSE_WR_VERSION}:
        head=r.get('rb_rush_mean_head') or {};scaler=head.get('target_scaler') or {}
        import math
        if (head.get('position')!='RB' or head.get('channel')!='rush_attempts'
                or head.get('transform')!='standardized_raw_count_mse_v1' or 'rb_rush_attempts' not in bundle['estimators']
                or any(isinstance(scaler.get(k),bool) or not isinstance(scaler.get(k),(int,float)) or not math.isfinite(scaler[k]) for k in ('center','scale'))
                or scaler['scale']<=0):raise ValueError('Invalid scoped RB rush mean contract')
    if r['version']==SPARSE_WR_VERSION:
        head=r.get('sparse_wr_count_heads') or {}
        if (head.get('position')!='WR' or head.get('prior_games')!=2
                or head.get('transform')!='standardized_raw_count_mse_v1'
                or set(head.get('heads',{}))!={'targets','rush_attempts'}):raise ValueError('Invalid sparse WR count contract')
        for channel,spec in head['heads'].items():
            scaler=spec.get('target_scaler') or {}
            if ('sparse_wr_'+channel not in bundle['estimators'] or spec.get('training_rows',0)<100
                    or spec.get('training_max_period',before_period)>=before_period
                    or any(isinstance(scaler.get(k),bool) or not isinstance(scaler.get(k),(int,float)) or not math.isfinite(scaler[k]) for k in ('center','scale'))
                    or scaler['scale']<=0):raise ValueError('Invalid sparse WR estimator/scaler')
    return bundle


def load_player_result(sha,*,before_period,cutoff,directory=None):
    if isinstance(before_period,bool) or not isinstance(before_period,int) or not 1<=before_period%100<=18:raise ValueError('Invalid REG player forecast period')
    result=_json(sha,directory)
    if result.get('status')!='actual_two_player_families_fitted_not_registered_or_app_consumed' or result.get('actual_family_fits')!=2:raise ValueError('Incomplete player fit result')
    if clock(result['completed_at'])>clock(cutoff):raise ValueError('Player fit unavailable at decision')
    pair={k:_bundle(result['model_refs'][k],directory=directory,cutoff=cutoff,before_period=before_period) for k in ('tree','neural')}
    a,b=(pair[k]['receipt'] for k in ('tree','neural'))
    if any(a[k]!=b[k] for k in ('version','matrix_sha256','prepared_sha256','preprocessing','target_columns')):raise ValueError('Player family contracts differ')
    if a.get('rb_rush_mean_head')!=b.get('rb_rush_mean_head'):raise ValueError('Player family RB rush contracts differ')
    if a.get('sparse_wr_count_heads')!=b.get('sparse_wr_count_heads'):raise ValueError('Player family sparse WR contracts differ')
    return result,pair


def publish_player_models(session,*,result_sha256,before_period,now=None,directory=None):
    now=clock(now or datetime.now(UTC));result,_=load_player_result(result_sha256,before_period=before_period,cutoff=now,directory=directory)
    rows=session.execute(text("SELECT record_id,record_json FROM target.evaluation_record WHERE kind=:kind AND record_json->'payload'->>'result_sha256'=:sha"),dict(kind=KIND,sha=result_sha256)).mappings().all()
    if rows:
        row=rows[0]
        if row['record_id']!='evaluation-'+digest(row['record_json']):raise ValueError('Player registry checksum mismatch')
        return dict(record_id=row['record_id'],**row['record_json']['payload'],reused=True)
    payload=dict(contract=CONTRACT,result_sha256=result_sha256,model_refs=result['model_refs'],published_at=now.isoformat(),trained_before_period=before_period)
    rid=append_record(session,KIND,payload,source=dict(operation='publish_managed_player_count_models'))
    return dict(record_id=rid,**payload,reused=False)


def infer_player_counts(result_sha256,matrix,count_receipt,*,cutoff,purpose='current_inference',directory=None):
    """Use the same numerical consumer for current and explicitly offline runs."""
    if purpose not in {'current_inference','offline_retrospective_evaluation'}:raise ValueError('Unknown player inference purpose')
    if matrix_digest({k:v for k,v in matrix.items() if k not in {'matrix_sha256','provenance'}})!=matrix.get('matrix_sha256'):raise ValueError('Player inference matrix checksum mismatch')
    if purpose=='current_inference' and matrix.get('usage')!='current_inference':raise ValueError('Revised retrospective player inputs cannot serve current forecasts')
    before=matrix['before_period']
    if count_receipt['before_period']!=before:raise ValueError('Count and player inference periods differ')
    result,pair=load_player_result(result_sha256,before_period=before,cutoff=cutoff,directory=directory)
    if (matrix['version']==ACTIVE_MATRIX_VERSION)!=(pair['tree']['receipt']['version'] in ACTIVE_MODEL_VERSIONS):
        raise ValueError('Player event-window training and inference contracts differ')
    rows=[r for r in matrix['rows'] if r.get('current_inference') and r['period']==before]
    predictions=predict_player_families(pair['tree'],pair['neural'],rows,before_period=before)
    counts=apply_player_count_predictions(count_receipt,predictions)
    if count_receipt.get('component_response') and count_receipt.get('reference_count_forecast'):
        from .count_component_response import component_response
        old=count_receipt['component_response']
        base={p['player_master_id']:p['base_fp'] for p in old['players']}
        counts['component_response']=component_response(None,count_receipt['reference_count_forecast'],counts,base,
            before_period=before,cutoff=cutoff,efficiency=old['efficiency_receipt'])
    counts['sha256']=matrix_digest(counts)
    semantic=dict(contract=CONTRACT,inference_rows=[dict(player_master_id=r['player_master_id'],team=r['team'],features=r['features'],history_periods=r['history_periods'],context_periods=r.get('context_periods',[])) for r in rows],model_result_sha256=result_sha256,predictions=predictions)
    return dict(status='forecast_complete',purpose=purpose,pregame_serving_eligible=purpose=='current_inference',counts=counts,predictions=predictions,semantic_sha256=matrix_digest(semantic),model_refs=result['model_refs'],feature_window='prior_observed_player_games' if matrix['version']==ACTIVE_MATRIX_VERSION else 'prior_team_games',count_head_contract=dict(version=pair['tree']['receipt']['version'],rb_rush_mean_head=pair['tree']['receipt'].get('rb_rush_mean_head')),provenance=dict(actual_inferred_at=datetime.now(UTC).isoformat(),decision_cutoff_at=str(cutoff),matrix=matrix['provenance']),limitations=['Count-head estimands are declared per player/head; arithmetic expected-count calibration remains unproven','Unknown role/history channels retained; full-team residual not donated','Offline revised-history evaluation is not original historical pregame evidence'])


def predict_registered_players(session,matrix,count_receipt,*,cutoff,directory=None):
    """Only ledger-owned model refs may enter current forecast consumption."""
    rows=session.execute(text("SELECT record_id,record_json FROM target.evaluation_record WHERE kind=:kind ORDER BY recorded_at DESC,record_id DESC LIMIT 100"),dict(kind=KIND)).mappings().all()
    for row in rows:
        envelope=row['record_json'];payload=envelope.get('payload',{})
        if clock(payload['published_at'])>clock(cutoff):continue
        if row['record_id']!='evaluation-'+digest(envelope):raise ValueError('Player registry checksum mismatch')
        result,pair=load_player_result(payload['result_sha256'],before_period=count_receipt['before_period'],cutoff=cutoff,directory=directory)
        if result['model_refs']!=payload['model_refs']:raise ValueError('Registered player model lineage differs')
        if (matrix['version']==ACTIVE_MATRIX_VERSION)!=(pair['tree']['receipt']['version'] in ACTIVE_MODEL_VERSIONS):continue
        output=infer_player_counts(payload['result_sha256'],matrix,count_receipt,cutoff=cutoff,directory=directory)
        output['model_publication_record_id']=row['record_id']
        return output
    return dict(status='model_unavailable',predictions=None,counts=None)


def registered_history_refs(session, *, cutoff, before_period):
    rows=session.execute(text("SELECT record_id,record_json FROM target.evaluation_record WHERE kind=:kind ORDER BY recorded_at DESC,record_id DESC LIMIT 100"),dict(kind=KIND)).mappings().all()
    for row in rows:
        envelope=row['record_json'];payload=envelope['payload']
        if clock(payload['published_at'])>clock(cutoff):continue
        if row['record_id']!='evaluation-'+digest(envelope):raise ValueError('Player registry checksum mismatch')
        result,pair=load_player_result(payload['result_sha256'],before_period=before_period,cutoff=cutoff)
        if result['model_refs']!=payload['model_refs']:raise ValueError('Registered player model lineage differs')
        if pair['tree']['receipt']['version'] not in ACTIVE_MODEL_VERSIONS:continue
        return result.get('current_history_component_refs',[])
    return []
