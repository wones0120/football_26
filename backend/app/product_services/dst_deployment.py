"""Explicit, versioned DST serving component; an empty selection retains legacy.

Selection is an acceptance decision, separate from research rank superiority.
Configured failures stop Prepare rather than silently substituting legacy means.
"""
from __future__ import annotations

from io import BytesIO
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .dst_feature_pipeline import POLICY, repair_dst_frame
from .dst_training_labels import SCORING_CONTRACT

CONTRACT = 'verified_dst_serving_component_v1'
MANIFEST_CONTRACT = 'verified_dst_deployment_selection_v1'
POLICIES = {'existing_mae_policy', 'ensemble'}


def score_component(component, target):
    """Return canonical-keyed means and corrected inputs, never change offense."""
    if component.get('contract') != CONTRACT or component.get('policy') not in POLICIES:
        raise ValueError('Unsupported DST serving component')
    selected = target.loc[target.position.astype(str).str.upper().eq('DST')].copy()
    if selected.empty:
        return selected.assign(mean=pd.Series(dtype=float)), dict(rows=0)
    if selected.player_master_id.astype(str).duplicated().any():
        raise ValueError('Ambiguous canonical DST target identity')
    periods = pd.to_numeric(selected.season)*100 + pd.to_numeric(selected.week)
    if not periods.eq(int(component['target_period'])).all():
        raise ValueError('DST component expired or targets overlap its validated period')
    if int(component['training_end']) >= int(periods.min()):
        raise ValueError('DST component training overlaps prediction period')
    repaired, audit = repair_dst_frame(selected, component['context'])
    means = component['policies'].predict(repaired, policy=component['policy'])
    if len(means) != len(selected) or not np.isfinite(means).all():
        raise ValueError('Invalid DST serving predictions')
    repaired['mean'] = means
    return repaired, audit


def load_selection(path, sha256):
    """Load only a pinned, explicitly accepted selection, then trusted joblib."""
    raw = Path(path).expanduser().read_bytes()
    if not sha256 or hashlib.sha256(raw).hexdigest() != sha256:
        raise ValueError('DST deployment selection checksum mismatch')
    manifest = json.loads(raw)
    decision = manifest.get('acceptance', {})
    if (manifest.get('contract') != MANIFEST_CONTRACT
            or manifest.get('feature_policy') != POLICY
            or manifest.get('scoring_contract') != SCORING_CONTRACT
            or decision.get('status') != 'approved'
            or not decision.get('decision_id') or not decision.get('standard')
            or not decision.get('limitations_acknowledged')
            or not decision.get('evidence_sha256')):
        raise ValueError('DST deployment requires an explicit recorded acceptance decision')
    artifact = manifest['artifact']
    data = Path(artifact['path']).expanduser().read_bytes()
    if hashlib.sha256(data).hexdigest() != artifact['sha256']:
        raise ValueError('DST serving component checksum mismatch')
    component = joblib.load(BytesIO(data))  # checksum-pinned local application artifact
    if (component.get('contract') != CONTRACT or component.get('policy') != manifest.get('policy')
            or component.get('scoring_contract') != SCORING_CONTRACT
            or component.get('feature_policy') != POLICY):
        raise ValueError('DST deployment manifest/component contract mismatch')
    if (component['context'].source_sha256 != component['source_hashes']['events']
            or component['context'].identities_sha256 != component['source_hashes']['identities']
            or any('qb' in col.lower() for col in component['policies'].columns)):
        raise ValueError('DST component source/feature contract mismatch')
    profile = component['calibration']
    offsets = [profile['residual_quantiles'][name] for name in ['p10','p25','p50','p75','p90']]
    if profile['sample_size'] < 30 or not np.isfinite(offsets).all() or (np.diff(offsets) < 0).any():
        raise ValueError('Invalid DST component residual calibration')
    audit = dict(status='selected', contract=CONTRACT, policy=component['policy'],
                 selection_sha256=sha256, artifact_sha256=artifact['sha256'],
                 acceptance=decision, training_end=component['training_end'],
                 target_period=component['target_period'],
                 source_hashes=component['source_hashes'],
                 training_features_sha256=component['training_features_sha256'],
                 calibration_evidence_sha256=component['calibration_evidence_sha256'],
                 chronology=component['context'].chronology,
                 original_source_clock_attestation=False)
    return component, audit


def configured_component(target):
    from ..config import get_settings
    settings = get_settings()
    path = settings.dst_deployment_manifest_path
    if not path or not target.position.astype(str).str.upper().eq('DST').any():
        return None, dict(status='incumbent_retained', contract='incumbent_dst_matrix_legacy_v1')
    # No exception swallowing: configured-but-invalid means explicit Prepare failure.
    return load_selection(path, settings.dst_deployment_manifest_sha256)


def apply_component(means, target, component):
    result = np.asarray(means, dtype=float).copy()
    overlay, audit = score_component(component, target)
    if overlay.empty:
        return result, audit
    by_id = overlay.set_index(overlay.player_master_id.astype(str))['mean']
    mask = target.position.astype(str).str.upper().eq('DST')
    result[np.flatnonzero(mask.to_numpy())] = target.loc[mask, 'player_master_id'].astype(str).map(by_id).to_numpy()
    return result, audit


def component_profile(component):
    from .predictions import ResidualCalibrationProfile
    profile = component['calibration']
    return ResidualCalibrationProfile(position='DST', sample_size=int(profile['sample_size']),
        source=profile['source'], residual_quantiles=profile['residual_quantiles'])


def runtime_status():
    """Safe process-level selection attestation for API and worker diagnostics."""
    from ..config import get_settings
    settings = get_settings()
    if not settings.dst_deployment_manifest_path:
        return dict(status='incumbent_retained', contract='incumbent_dst_matrix_legacy_v1')
    try:
        _, audit = load_selection(settings.dst_deployment_manifest_path,
                                  settings.dst_deployment_manifest_sha256)
        return audit
    except Exception as exc:
        return dict(status='invalid_selection', error=str(exc),
                    configured_selection_sha256=settings.dst_deployment_manifest_sha256,
                    prepare_policy='fail_explicitly_no_silent_fallback')
