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
