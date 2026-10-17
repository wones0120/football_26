import json
from datetime import UTC,datetime
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from backend.app.product_services import weekly_learning_library as library
from backend.app.api.weekly_learning_library_routes import router


def report(week=5,user='wones0120',at='2026-10-13T13:28:57+00:00'):
 return dict(report_id='weekly-original',contract_id='weekly_learning_report_v2',season=2026,week=week,entry_user=user,generated_at=at,status='partial',summary={'slates':8,'entries':16},slate_reports=[],evidence_hash='original-evidence',missing_evidence=['historical-gap'],interpretation='Original historical evidence, not rebuilt')


def test_original_recovery_preserves_bytes_clocks_and_retries(tmp_path):
 original=report();raw=json.dumps(original,indent=4).encode()+b'\n';a=library.save_report(original,directory=tmp_path,original_bytes=raw,recovered_from='artifacts/original.json');b=library.save_report(original,directory=tmp_path,original_bytes=raw,recovered_from='different-reference')
 assert a==b and a['generated_at']==original['generated_at'] and a['storage_provenance']=='recovered_original'
 record,got,stored=library.load_report(a['sha256'],entry_user=' WONES0120 ',directory=tmp_path)
 assert got==original and stored==raw and record['original_reference']=='artifacts/original.json'


def test_latest_per_week_scope_versions_and_generated_not_saved_order(tmp_path):
 old=library.save_report(report(at='2026-10-13T12:00:00+00:00'),directory=tmp_path)
 new=library.save_report(report(),directory=tmp_path)
 library.save_report(report(at='2026-10-13T11:00:00+00:00'),directory=tmp_path) # recovered later is not newer evidence
 other=library.save_report(report(2),directory=tmp_path);library.save_report(report(user='someoneelse'),directory=tmp_path)
 rows=library.list_reports(entry_user='wones0120',directory=tmp_path)
 assert [r['week'] for r in rows]==[5,2] and rows[0]['sha256']==new['sha256'] and rows[0]['version_count']==3
 assert len(library.list_reports(entry_user='wones0120',week=5,season=2026,latest_per_week=False,directory=tmp_path))==3
 assert library.list_reports(entry_user='wones0120',season=2025,directory=tmp_path)==[]
 with pytest.raises(ValueError,match='another username'):library.load_report(old['sha256'],entry_user='someoneelse',directory=tmp_path)


def test_corrupt_missing_or_traversal_original_is_never_rebuilt(tmp_path):
 saved=library.save_report(report(),directory=tmp_path);(tmp_path/(saved['sha256']+'.json')).write_bytes(b'changed')
 assert library.list_reports(entry_user='wones0120',directory=tmp_path)==[]
 with pytest.raises(ValueError,match='hash'):library.load_report(saved['sha256'],entry_user='wones0120',directory=tmp_path)
 with pytest.raises(ValueError):library.load_report('../x',entry_user='wones0120',directory=tmp_path)
 with pytest.raises(ValueError):library.save_report(report(),directory=tmp_path,original_bytes=b'{}')


def test_library_api_reopen_and_download_exact_content_after_new_client(tmp_path,monkeypatch):
 monkeypatch.setattr(library,'LEDGER',tmp_path);value=report();raw=json.dumps(value,indent=2).encode();saved=library.save_report(value,original_bytes=raw,recovered_from='original.json')
 app=FastAPI();app.include_router(router)
 client=TestClient(app);rows=client.get('/api/learning/weekly-library',params={'entry_user':'wones0120'}).json();assert rows['rows'][0]['sha256']==saved['sha256'] and rows['rebuild_performed'] is False
 reopened=TestClient(app).get('/api/learning/weekly-library/'+saved['sha256'],params={'entry_user':'wones0120'}).json();assert reopened['report']==value and reopened['rebuild_performed'] is False
 download=client.get('/api/learning/weekly-library/'+saved['sha256']+'/download',params={'entry_user':'wones0120'});assert download.content==raw and download.headers['x-report-content-sha256']==saved['sha256']
 assert client.get('/api/learning/weekly-library/'+saved['sha256'],params={'entry_user':'other'}).status_code==404
 assert client.get('/api/learning/weekly-library',params={'entry_user':'other'}).json()['rows']==[]
