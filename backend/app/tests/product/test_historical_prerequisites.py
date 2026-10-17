from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from backend.app.product_services.historical_prerequisites import refresh_history

PATH = 'backend.app.product_services.historical_prerequisites.'
COMPLETE = {5: dict(expected_teams=['DEN', 'SEA'], missing_stats=[], missing_snaps=[])}
MISSING = {5: dict(expected_teams=['DEN', 'SEA'], missing_stats=[], missing_snaps=['DEN', 'SEA'])}


def test_complete_history_does_not_fetch_or_ingest():
    with patch(PATH+'coverage', return_value=COMPLETE), patch(PATH+'capture_nflreadpy_datasets') as fetch:
        result = refresh_history(MagicMock(), season=2026, week=6, slate='THURSDAY_NIGHT', lock=datetime.now(UTC))
    fetch.assert_not_called()
    assert result['captures'] == []


def test_missing_snaps_ingests_only_captured_week_and_records_lineage():
    snapshot = SimpleNamespace(snapshot_id='capture', artifact_path='immutable.csv')
    ingest = SimpleNamespace(status='completed', ingest_run_id='ingest', rows_raw=2, rows_unresolved=0)
    with patch(PATH+'coverage', side_effect=[MISSING, COMPLETE]), \
         patch(PATH+'Session'), patch(PATH+'SourceCaptureService') as service, \
         patch(PATH+'capture_nflreadpy_datasets', return_value=[SimpleNamespace(snapshot=snapshot)]) as fetch, \
         patch(PATH+'_ingest_run_id', return_value='ingest'), \
         patch('pandas.read_csv', return_value=pd.DataFrame({'week':[5,5], 'team':['DEN','SEA']})), \
         patch(PATH+'IngestService') as importer:
        importer.return_value.ingest_nflreadpy_snap_counts.return_value = ingest
        result = refresh_history(MagicMock(), season=2026, week=6, slate='THURSDAY_NIGHT', lock=datetime.now(UTC))
    assert fetch.call_args.args[1] == ['snap_counts']
    assert fetch.call_args.kwargs['week'] == 5
    call = importer.return_value.ingest_nflreadpy_snap_counts.call_args
    assert call.args[0].weeks == [5]
    assert call.kwargs['source_path'] == 'immutable.csv'
    service.return_value.link_ingest_run.assert_called_once_with('capture','ingest')
    assert result['captures'][0]['snapshot_id'] == 'capture'


def test_incomplete_provider_is_captured_but_cannot_replace_existing_history():
    with patch(PATH+'coverage', return_value=MISSING), patch(PATH+'Session'), \
         patch(PATH+'SourceCaptureService'), \
         patch(PATH+'capture_nflreadpy_datasets', return_value=[SimpleNamespace(snapshot=SimpleNamespace(snapshot_id='capture', artifact_path='immutable.csv'))]), \
         patch('pandas.read_csv', return_value=pd.DataFrame({'week':[5], 'team':['DEN']})), \
         patch(PATH+'IngestService') as importer:
        with pytest.raises(ValueError, match='still lacks teams'):
            refresh_history(MagicMock(), season=2026, week=6, slate='THURSDAY_NIGHT', lock=datetime.now(UTC))
    importer.assert_not_called()
