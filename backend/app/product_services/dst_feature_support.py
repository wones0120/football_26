"""Operational verified DST input sidecars, isolated from incumbent model inputs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from .dst_feature_pipeline import DstFeatureContext, POLICY, REPAIRED_COLUMNS, repair_dst_frame
from .dst_training_labels import SCORING_CONTRACT, TARGET

LEGACY_DST_CONTRACT = 'incumbent_dst_matrix_legacy_v1'
SUPPORT_MANIFEST = 'verified_dst_input_support_manifest_v1'


def build_support(train, target, *, manifest_path, manifest_sha256, output_root, cutoff):
    """Return an audit/immutable sidecar; never mutate the supplied model frames."""
    audit = dict(active_model_input_contract=LEGACY_DST_CONTRACT,
                 support_feature_contract=POLICY, model_activation=False,
                 promotion_blocker='Reliable DST ranking advantage not validated; candidate models remain inactive')
    if not manifest_path:
        return dict(audit, status='not_configured')
    raw = Path(manifest_path).expanduser().read_bytes()
    if not manifest_sha256 or hashlib.sha256(raw).hexdigest() != manifest_sha256:
        raise ValueError('DST support manifest checksum mismatch')
    manifest = json.loads(raw)
    if (manifest.get('contract') != SUPPORT_MANIFEST or manifest.get('feature_policy') != POLICY
            or manifest.get('scoring_contract') != SCORING_CONTRACT
            or manifest.get('model_activation') is not False):
        raise ValueError('Unsupported DST support contract or activation request')
    ctx = DstFeatureContext.read(
        manifest['events']['path'], manifest['identities']['path'],
        expected_events_sha256=manifest['events']['sha256'],
        expected_identities_sha256=manifest['identities']['sha256'])
    training = train.loc[train.position.astype(str).str.upper().eq('DST')].copy()
    prediction = target.loc[target.position.astype(str).str.upper().eq('DST')].copy()
    if training.empty or prediction.empty:
        return dict(audit, status='not_applicable', training_rows=len(training), prediction_rows=len(prediction))
    repaired_training, training_audit = repair_dst_frame(training, ctx, matrix_generation=True)
    if repaired_training.dk_points.isna().any():
        raise ValueError('Verified DST support does not cover every current training outcome')
    repaired_training[TARGET] = repaired_training.dk_points
    repaired_prediction, prediction_audit = repair_dst_frame(prediction, ctx)
    columns = [c for c in ['player_game_feature_matrix_id','player_master_id','source_system',
                           'season','week','team','opponent',TARGET,'dk_points','salary',
                           'game_total_line','team_spread_line','team_implied_total','opponent_implied_total',
                           *REPAIRED_COLUMNS] if c in repaired_training.columns]
    columns = list(dict.fromkeys(columns))
    prediction_columns = [c for c in columns if c not in {TARGET,'dk_points'} and c in repaired_prediction.columns]
    # DataFrame.to_json safely retains unknown values as JSON null, not fake zeros.
    payload = dict(contract=SUPPORT_MANIFEST, feature_policy=POLICY,
        active_model_input_contract=LEGACY_DST_CONTRACT, model_activation=False,
        classification='VERSIONED_RECONSTRUCTED_CANDIDATE_INPUTS_NOT_ORIGINAL_MATRIX',
        original_source_clock_attestation=False, chronology=ctx.chronology,
        cutoff=pd.Timestamp(cutoff).isoformat(), manifest_sha256=manifest_sha256,
        events_sha256=ctx.source_sha256, identities_sha256=ctx.identities_sha256,
        scoring_contract=SCORING_CONTRACT,
        training=json.loads(repaired_training[columns].to_json(orient='records',default_handler=str)),
        prediction=json.loads(repaired_prediction[prediction_columns].to_json(orient='records',default_handler=str)),
        original_training_labels=json.loads(training[[c for c in ['player_game_feature_matrix_id','player_master_id',TARGET,'dk_points'] if c in training]].to_json(orient='records',default_handler=str)),
        training_audit=training_audit,prediction_audit=prediction_audit)
    encoded = json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    destination = Path(output_root).expanduser()/f'{digest}.json'
    destination.parent.mkdir(parents=True,exist_ok=True)
    try:
        with destination.open('xb') as handle:
            handle.write(encoded)
    except FileExistsError:
        if destination.read_bytes() != encoded:
            raise ValueError('DST support sidecar collision; existing evidence preserved')
    return dict(audit,status='ready_inactive',support_id=digest,artifact_path=str(destination),
                artifact_sha256=digest,manifest_sha256=manifest_sha256,
                training_rows=len(training),prediction_rows=len(prediction),
                repaired_home_rows=int(pd.to_numeric(training.is_home,errors='coerce').fillna(0).ne(repaired_training.is_home).sum()),
                training_audit=training_audit,prediction_audit=prediction_audit,
                original_source_clock_attestation=False)


def operational_support(train,target,*,cutoff):
    from ..config import get_settings
    settings=get_settings()
    try:
        return build_support(train,target,manifest_path=settings.dst_feature_support_manifest_path,
            manifest_sha256=settings.dst_feature_support_manifest_sha256,
            output_root=settings.dst_feature_support_output_root,cutoff=cutoff)
    except Exception as exc:
        # Support failure is explicit. Never fall back to candidate predictions or
        # block/rewrite the incumbent's already established feature contract.
        return dict(status='unavailable',error=str(exc),model_activation=False,
                    active_model_input_contract=LEGACY_DST_CONTRACT,support_feature_contract=POLICY,
                    promotion_blocker='Verified support unavailable; incumbent contract retained')
