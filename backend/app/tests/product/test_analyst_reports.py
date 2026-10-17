"""Report API uses isolated files and no database/session lifespan."""
import json
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.app.api.analyst_report_routes import router
from backend.app.product_services import analyst_reports as service

@pytest.fixture
def library(tmp_path, monkeypatch):
    root = tmp_path / 'research'; root.mkdir(); (root / 'edition').mkdir()
    (root / 'edition/report.md').write_text('# Briefing\n\n[Evidence](receipt.json) [Other](../other.md) [Unlisted](hidden.json)\n\n<script>alert(1)</script>')
    (root / 'edition/receipt.json').write_text('{"source":"original"}')
    (root / 'other.md').write_text('# Preserved report')
    rows = [dict(report_id='briefing-v1',title='Briefing',category='briefing',version='v1',path='edition/report.md',application_status='research_only',summary='Research',evidence=[dict(evidence_id='receipt',path='edition/receipt.json')]), dict(report_id='other-v1',title='Other',category='specialist',version='v1',path='other.md',application_status='unknown',summary='Preserved')]
    catalog = root / 'catalog.json'; catalog.write_text(json.dumps(dict(schema_version=1,reports=rows)))
    monkeypatch.setattr(service, 'RESEARCH_ROOT', root); monkeypatch.setattr(service, 'CATALOG', catalog)
    app = FastAPI(); app.include_router(router)
    return TestClient(app), root, rows

def replace_catalog(root, rows):
    (root / 'catalog.json').write_text(json.dumps(dict(schema_version=1,reports=rows)))

def test_catalog_read_and_controlled_evidence_no_absolute_paths(library):
    client, root, _ = library; response = client.get('/api/analyst-reports'); assert response.status_code == 200
    entry = response.json()['rows'][0]; assert 'path' not in entry and 'evidence' not in entry and entry['available']
    read = client.get('/api/analyst-reports/briefing-v1'); assert read.status_code == 200
    result = read.json(); assert len(result['sha256']) == 64 and '<script>' in result['markdown'] # raw text, never HTML response
    assert result['links'] == [dict(target='receipt.json',kind='evidence',evidence_id='receipt'),dict(target='../other.md',kind='report',report_id='other-v1',fragment=''),dict(target='hidden.json',kind='unavailable')]
    evidence = client.get('/api/analyst-reports/briefing-v1/evidence/receipt'); assert evidence.status_code == 200
    assert evidence.json()['content'] == '{"source":"original"}' and str(root) not in evidence.text
    assert read.headers['content-type'].startswith('application/json')

@pytest.mark.parametrize('suffix', ['unknown','..%2F..%2F.env','briefing-v1/evidence/unknown','briefing-v1/evidence/receipt.json'])
def test_unknown_and_traversal_requests_cannot_read_files(library, suffix):
    client, _, _ = library; assert client.get('/api/analyst-reports/' + suffix).status_code == 404

@pytest.mark.parametrize('path', ['../secret.md','/tmp/secret.md','edition/.env','edition/receipt.json'])
def test_bad_catalog_paths_fail_closed(library, path):
    client, root, rows = library; rows[0]['path'] = path; replace_catalog(root, rows)
    response = client.get('/api/analyst-reports'); assert response.status_code == 503 and str(root) not in response.text

def test_symlink_escape_for_report_evidence_and_catalog(library, tmp_path):
    client, root, rows = library; outside = tmp_path / 'secret.md'; outside.write_text('private')
    (root / 'edition/escape.md').symlink_to(outside); rows[0]['path']='edition/escape.md'; replace_catalog(root, rows)
    assert client.get('/api/analyst-reports/briefing-v1').status_code == 503
    rows[0]['path']='edition/report.md'; rows[0]['evidence'][0]['path']='edition/escape.md'; replace_catalog(root, rows)
    assert client.get('/api/analyst-reports/briefing-v1/evidence/receipt').status_code == 503
    monkey_catalog = root / 'catalog.json'; monkey_catalog.unlink(); monkey_catalog.symlink_to(outside)
    assert client.get('/api/analyst-reports').status_code == 503

def test_missing_files_and_oversize_text_are_explicit(library, monkeypatch):
    client, root, _ = library; (root / 'edition/report.md').unlink()
    assert client.get('/api/analyst-reports').json()['rows'][0]['available'] is False
    assert client.get('/api/analyst-reports/briefing-v1').status_code == 404
    (root / 'edition/report.md').write_text('x' * (service.MAX_BYTES + 1))
    assert client.get('/api/analyst-reports/briefing-v1').status_code == 503
    assert client.post('/api/analyst-reports/briefing-v1').status_code == 405

def test_actual_controlled_catalog_has_main_briefing_and_no_model_training_reports():
    catalog = service.list_reports()['rows']; assert len(catalog) >= 8
    assert next(r for r in catalog if r['report_id']=='wednesday-briefing-v1')['category']=='briefing'
    assert all(r['available'] and r['week']==6 for r in catalog)
    assert not any('training' in r['report_id'] or 'neural' in r['report_id'] for r in catalog)
