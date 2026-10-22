from copy import deepcopy
import pytest
from backend.app.product_services.player_opportunity_replay import html_report,read


def test_saved_report_exposes_counts_slot_multiplier_and_nonentry_state():
    value=dict(requested=1,achieved=1,status='completed',actual_created_at='2026-10-20T01:00Z',scope={},selection={},selected=[dict(roster=[dict(role='CPT',name='<Daniels>',salary=15000.,counts=dict(pass_attempts=30.,rush_attempts=6.,targets=None),base_fp=20.,conditional_fp=21.,slot_conditional_fp=31.5)])])
    html=html_report(value)
    assert 'Not entry-ready' in html and 'Pass attempts' in html and 'unknown' in html
    assert '&lt;Daniels&gt;' in html and '<Daniels>' not in html and '31.500' in html


def test_saved_artifact_integrity_cannot_silently_change(tmp_path):
    import json
    from backend.app.product_services.analyst_shadow import digest
    value=dict(replay_id='a'*64,status='completed');value['artifact_sha256']=digest(value)
    path=tmp_path/('a'*64+'.json');path.write_text(json.dumps(value));assert read('a'*64,directory=tmp_path)==value
    value['status']='entry_ready';path.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='checksum'):read('a'*64,directory=tmp_path)
