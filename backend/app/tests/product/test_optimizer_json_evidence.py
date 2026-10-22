import json
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from backend.app.product_services.optimizer import _json_safe
from backend.app.product_services.analyst_research_requests import semantic_dependencies
from backend.app.tests.product.test_analyst_preparation import inputs


def test_datetime_missingness_is_null_without_changing_dates_zero_or_false():
    at = datetime(2026, 10, 19, 18, tzinfo=UTC)
    source = dict(observed_at=pd.NaT, nested=[dict(received_at=pd.NaT)],
        valid=at, timestamp=pd.Timestamp(at), zero=0, false=False,
        numpy_zero=np.int64(0), numpy_false=np.bool_(False), optional=pd.NA)
    result = _json_safe(source)
    assert result == dict(observed_at=None, nested=[dict(received_at=None)],
        valid=at.isoformat(), timestamp=at.isoformat(), zero=0, false=False,
        numpy_zero=0, numpy_false=False, optional=None)
    assert json.loads(json.dumps(result, allow_nan=False)) == result
    assert source["observed_at"] is pd.NaT


def test_public_prepare_serializer_to_semantic_dependencies_keeps_unknown_clocks():
    _, rows, _, result = inputs('SHOWDOWN')
    rows[0].update(practice_observed_at=pd.NaT, starting_qb_observed_at=pd.NaT,
        role_starter_evidence=dict(observed_at=pd.NaT, received_at=pd.NaT),
        role_active=False, projected_targets=0)
    result['source_manifest']['availability'] = [dict(player_master_id=rows[0]['player_id'],
        published_at=pd.NaT, evidence_json=dict(observed_at=pd.NaT, modified_at=pd.NaT))]
    safe_rows = _json_safe(rows); safe_manifest = _json_safe(result['source_manifest'])
    snapshot = semantic_dependencies(games=safe_manifest['games'], rows=safe_rows,
        checked_at='2099-09-01T12:30:00Z', source_manifest=safe_manifest)
    assert snapshot['dependency_sha256']
    assert safe_rows[0]['practice_observed_at'] is None
    assert safe_rows[0]['role_starter_evidence']['observed_at'] is None
    assert safe_rows[0]['projected_targets'] == 0 and safe_rows[0]['role_active'] is False
    safe_rows[0]['role_observed_at'] = '2099-09-01T14:00:00Z'
    with pytest.raises(ValueError, match='Future research'):
        semantic_dependencies(games=safe_manifest['games'], rows=safe_rows,
            checked_at='2099-09-01T12:30:00Z', source_manifest=safe_manifest)
    safe_rows[0]['role_observed_at'] = 'not-a-real-clock'
    with pytest.raises(ValueError):
        semantic_dependencies(games=safe_manifest['games'], rows=safe_rows,
            checked_at='2099-09-01T12:30:00Z', source_manifest=safe_manifest)
