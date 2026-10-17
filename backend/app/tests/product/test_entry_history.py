import csv
import io
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.app.product_services.entry_history import REQUIRED, parse_history, merge_history, summarize, enrich_contests, EntryHistoryService
from backend.app.product_services.optimizer_effectiveness import field_benchmarks
from backend.app.api.product_routes import import_entry_history
from backend.app.product_schemas import EntryHistoryImportRequest


def csv_bytes(**changes):
    row=dict(Sport='NFL',Game_Type='Classic',Entry_Key='101',Entry='NFL Play-Action',Contest_Key='200',
             Contest_Date_EST='2026-10-04 13:00:00',Place='1',Points='120.5',Winnings_Non_Ticket='$20.00',
             Winnings_Ticket='$0.00',Contest_Entries='3',Entry_Fee='$3.00',Prize_Pool='$30.00',Places_Paid='2')
    row.update(changes)
    out=io.StringIO();w=csv.DictWriter(out,fieldnames=sorted(REQUIRED));w.writeheader();w.writerow(row)
    return out.getvalue().encode()


def test_parse_and_idempotent_merge_keep_native_ids_and_currency():
    rows=parse_history(csv_bytes())
    assert rows[0]['entry_id']=='101'
    assert rows[0]['entry_fee']==3
    merged,conflicts=merge_history([dict(entries_json=rows),dict(entries_json=rows)])
    assert merged==rows and not conflicts


@pytest.mark.parametrize('change',[dict(Entry_Key=''),dict(Points='NaN'),dict(Entry_Fee='-1'),
    dict(Winnings_Ticket='unknown'),dict(Places_Paid='4'),dict(Place='0'),dict(Contest_Date_EST='bad')])
def test_invalid_export_fails_explicitly(change):
    with pytest.raises(ValueError,match='row 2'):
        parse_history(csv_bytes(**change))


def test_conflicts_are_excluded_and_reported():
    rows=parse_history(csv_bytes());other=deepcopy(rows);other[0]['cash_winnings']=50
    merged,conflicts=merge_history([dict(entries_json=rows),dict(entries_json=other)])
    assert not merged and conflicts==[('200','101')]


def test_summary_separates_free_non_nfl_unknown_and_ticket_results():
    rows=parse_history(csv_bytes(Winnings_Non_Ticket='$0',Winnings_Ticket='$10'))
    rows+=parse_history(csv_bytes(Entry_Key='102',Entry_Fee='$0'))
    rows+=parse_history(csv_bytes(Entry_Key='103',Sport='NBA'))
    rows+=parse_history(csv_bytes(Entry_Key='104',Entry='Unclassified',Winnings_Non_Ticket='$0'))
    r=summarize(rows,[],2026,[])
    assert r['summary']['entries']==2 and r['summary']['paid_finishes']==1
    assert r['summary']['cash_net_return']==-6 and r['summary']['ticket_winnings']==10
    assert r['gpp_summary']['entries']==1 and r['free_entries']==1
    assert r['unknown_type_entries']==1 and r['unmatched_contest_ids']==['200']


def test_exported_paid_places_enrich_only_matching_complete_fields():
    rows=parse_history(csv_bytes())
    original=[dict(contest_id='200',field_size=3,contest_type='unknown')]
    enriched=enrich_contests(original,rows)
    assert enriched[0]['places_paid']==2 and enriched[0]['contest_type']=='gpp'
    assert 'places_paid' not in original[0]
    benchmark=field_benchmarks(enriched[0],[dict(entry_points=x) for x in (120,100,80)],[])
    assert benchmark['cash_line']==100 and benchmark['cash_rank']==2
    assert 'places_paid' not in enrich_contests([dict(original[0],field_size=5)],rows)[0]


def test_import_dry_run_never_writes_or_requires_database(tmp_path):
    path=tmp_path/'history.csv';path.write_bytes(csv_bytes())
    engine=MagicMock()
    response=EntryHistoryService(engine).import_file(path,2026,True)
    assert response['status']=='validated' and response['rows']==1
    engine.begin.assert_not_called()


def test_route_reports_bad_file_as_actionable_422():
    with patch.object(EntryHistoryService,'import_file',side_effect=ValueError('invalid CSV')):
        with pytest.raises(HTTPException) as exc:
            import_entry_history(EntryHistoryImportRequest(path='bad',year=2026))
        assert exc.value.status_code==422


def test_learning_uses_personal_winnings_without_payout_ladder():
    from backend.app.tests.product.test_slate_learning import complete_evidence, NOW
    from backend.app.product_services.slate_learning import build_slate_learning_report
    evidence=complete_evidence();evidence['payout_tiers']=[]
    entry=evidence['entries'][0]
    evidence['entry_history']=[dict(contest_id=entry['contest_id'],entry_id=entry['entry_id'],
        entry_fee=3.,cash_winnings=8.,ticket_winnings=0.)]
    report=build_slate_learning_report(season=2026,week=1,slate='SUNDAY_NIGHT',entry_user='wones0120',evidence=evidence,generated_at=NOW)
    financial=report['entries'][0]['financial']
    assert financial['profit']==5 and financial['payout_source']=='entry_history'
    assert financial['paid_finish'] is True


def test_folder_scan_recognizes_contents_and_skips_processed_links(tmp_path):
    (tmp_path/'unusual-name.csv').write_bytes(csv_bytes())
    (tmp_path/'bad.csv').write_bytes(csv_bytes(Place='0'))
    (tmp_path/'salaries.csv').write_text('ID,Name,Salary\n1,Example,1000\n')
    processed=tmp_path/'Processed';processed.mkdir()
    (processed/'history.csv').write_bytes(csv_bytes())
    (tmp_path/'linked.csv').symlink_to(tmp_path/'unusual-name.csv')
    engine=MagicMock()
    result=EntryHistoryService(engine).scan_directory(tmp_path,2026)
    files={Path(r['path']).name:r for r in result['files']}
    assert set(files)=={'unusual-name.csv','bad.csv'}
    assert files['unusual-name.csv']['rows']==1
    assert files['bad.csv']['status']=='failed'
    assert (tmp_path/'unusual-name.csv').exists()
    engine.begin.assert_not_called()


def folder_service():
    service=EntryHistoryService(MagicMock())
    service._ensure_schema=MagicMock()
    service.report=MagicMock(return_value={'snapshot_count':1})
    return service


def test_folder_import_commits_before_move_and_retains_byte_hash_receipt(tmp_path):
    import hashlib
    import json
    source=tmp_path/'history.csv';raw=csv_bytes();source.write_bytes(raw)
    service=folder_service()
    transaction=service.engine.begin.return_value
    transaction.__enter__.return_value.execute.return_value.scalar.return_value='inserted'
    scan=service.scan_directory(tmp_path,2026)
    original_archive=service._archive
    def archive(*args):
        transaction.__exit__.assert_called_once()
        return original_archive(*args)
    with patch('backend.app.product_services.gpp_shadow_learning.refresh_after_import',return_value='done'), patch.object(service,'_archive',side_effect=archive):
        result=service.import_directory(tmp_path,2026,scan['files'])
    row=result['files'][0]
    assert row['status']=='imported' and row['archive_status']=='processed'
    assert not source.exists()
    assert Path(row['archive_path']).read_bytes()==raw
    receipt=json.loads(Path(row['receipt_path']).read_text())
    assert receipt['original_path']==str(source)
    assert receipt['content_sha256']==hashlib.sha256(raw).hexdigest()
    assert receipt['archive_path']==row['archive_path'] and receipt['archived_at']
    params=transaction.__enter__.return_value.execute.call_args.args[1]
    assert params['raw']==raw and params['path']==str(source)


def test_folder_partial_success_invalid_and_changed_files_stay(tmp_path):
    source=tmp_path/'ok.csv';source.write_bytes(csv_bytes())
    broken=tmp_path/'bad.csv';broken.write_bytes(csv_bytes(Entry_Key='bad'))
    changed=tmp_path/'changed.csv';changed.write_bytes(csv_bytes())
    service=folder_service();files=service.scan_directory(tmp_path,2026)['files']
    changed.write_bytes(csv_bytes(Entry_Key='102'))
    with patch('backend.app.product_services.gpp_shadow_learning.refresh_after_import',return_value='done'):
        result=service.import_directory(tmp_path,2026,files)
    statuses={Path(r['path']).name:r for r in result['files']}
    assert statuses['ok.csv']['archive_status']=='processed'
    assert statuses['bad.csv']['status']=='failed' and broken.exists()
    assert statuses['changed.csv']['status']=='failed' and changed.exists()
    assert 'changed since scanning' in statuses['changed.csv']['error']
    assert service.engine.begin.call_count==1


def test_archive_pending_retry_deduplicates_and_never_overwrites(tmp_path):
    source=tmp_path/'history.csv';source.write_bytes(csv_bytes())
    service=folder_service();files=service.scan_directory(tmp_path,2026)['files']
    with patch('backend.app.product_services.gpp_shadow_learning.refresh_after_import',return_value='done'):
        with patch.object(service,'_archive',side_effect=OSError('permission denied')):
            result=service.import_directory(tmp_path,2026,files)
        assert result['files'][0]['archive_status']=='pending' and source.exists()
        service.engine.begin.return_value.__enter__.return_value.execute.return_value.scalar.return_value=None
        result=service.import_directory(tmp_path,2026,files)
    row=result['files'][0]
    assert row['status']=='deduplicated' and row['archive_status']=='processed'
    # A future download with this name and different bytes keeps both exports.
    source.write_bytes(csv_bytes(Entry_Key='102'))
    second=service.scan_directory(tmp_path,2026)['files']
    with patch('backend.app.product_services.gpp_shadow_learning.refresh_after_import',return_value='done'):
        other=service.import_directory(tmp_path,2026,second)['files'][0]
    assert other['archive_path']!=row['archive_path']
    assert Path(row['archive_path']).read_bytes()==csv_bytes()


def test_archive_existing_conflicting_destination_is_preserved(tmp_path):
    source=tmp_path/'history.csv';source.write_bytes(csv_bytes())
    service=folder_service();files=service.scan_directory(tmp_path,2026)['files']
    processed=tmp_path/'Processed';processed.mkdir()
    collision=processed/f"history__{files[0]['content_sha256']}.csv";collision.write_bytes(b'original evidence')
    with patch('backend.app.product_services.gpp_shadow_learning.refresh_after_import',return_value='done'):
        row=service.import_directory(tmp_path,2026,files)['files'][0]
    assert row['archive_status']=='pending' and source.exists()
    assert collision.read_bytes()==b'original evidence'


def test_folder_rejects_escape_and_symlinked_archive(tmp_path):
    source=tmp_path/'history.csv';source.write_bytes(csv_bytes())
    service=folder_service();files=service.scan_directory(tmp_path,2026)['files']
    (tmp_path/'Processed').symlink_to(tmp_path, target_is_directory=True)
    with patch('backend.app.product_services.gpp_shadow_learning.refresh_after_import',return_value='done'):
        row=service.import_directory(tmp_path,2026,files)['files'][0]
    assert row['archive_status']=='pending' and source.exists()
    with pytest.raises(ValueError):
        service._source(tmp_path,tmp_path/'..'/'outside.csv')


def test_folder_route_scan_and_explicit_selection_contract(tmp_path):
    from backend.app.api.product_routes import import_entry_history_folder
    from backend.app.product_schemas import EntryHistoryFolderRequest
    source=tmp_path/'download.csv';source.write_bytes(csv_bytes())
    result=import_entry_history_folder(EntryHistoryFolderRequest(directory=str(tmp_path),year=2026))
    assert result['dry_run'] and result['files'][0]['status']=='validated'
    with pytest.raises(HTTPException) as exc:
        import_entry_history_folder(EntryHistoryFolderRequest(directory=str(tmp_path),year=2026,dry_run=False))
    assert exc.value.status_code==422


def test_repeated_completed_folder_request_returns_committed_receipt(tmp_path):
    source=tmp_path/'history.csv';source.write_bytes(csv_bytes())
    service=folder_service();files=service.scan_directory(tmp_path,2026)['files']
    with patch('backend.app.product_services.gpp_shadow_learning.refresh_after_import',return_value='done'):
        first=service.import_directory(tmp_path,2026,files)['files'][0]
        repeated=service.import_directory(tmp_path,2026,files)['files'][0]
    assert repeated['status']=='deduplicated' and repeated['archive_status']=='processed'
    assert repeated['archive_path']==first['archive_path']
    assert service.engine.begin.call_count==1
    service.engine.connect.return_value.__enter__.return_value.execute.return_value.scalar.return_value=None
    rejected=service.import_directory(tmp_path,2026,files)['files'][0]
    assert rejected['status']=='failed' and 'no committed' in rejected['error']


def test_folder_http_api_scan_import_processed_and_retry(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.app.api.product_routes import router
    source=tmp_path/'api-download.csv';source.write_bytes(csv_bytes())
    app=FastAPI();app.include_router(router)
    service=folder_service()
    with TestClient(app) as client, patch('backend.app.api.product_routes.EntryHistoryService',return_value=service), patch('backend.app.product_services.gpp_shadow_learning.refresh_after_import',return_value='done'):
        scan=client.post('/api/imports/draftkings/entry-history/folder',json={'directory':str(tmp_path),'year':2026,'dry_run':True})
        assert scan.status_code==200 and source.exists()
        files=[{k:row[k] for k in ('path','content_sha256')} for row in scan.json()['files']]
        payload={'directory':str(tmp_path),'year':2026,'dry_run':False,'files':files}
        response=client.post('/api/imports/draftkings/entry-history/folder',json=payload)
        assert response.status_code==200
        row=response.json()['files'][0]
        assert row['archive_status']=='processed' and not source.exists()
        assert Path(row['archive_path']).read_bytes()==csv_bytes()
        retry=client.post('/api/imports/draftkings/entry-history/folder',json=payload)
        assert retry.status_code==200 and retry.json()['files'][0]['status']=='deduplicated'
        changed=dict(payload,files=[dict(files[0],content_sha256='not-a-hash')])
        assert client.post('/api/imports/draftkings/entry-history/folder',json=changed).status_code==422
