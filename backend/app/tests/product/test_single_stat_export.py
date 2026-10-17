import csv
import io
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.product_services import single_stat as stat
from backend.app.product_services import single_stat_export as export
from backend.app.api.single_stat_routes import router
from backend.app.tests.product.test_single_stat import pool,NOW


def template(imported):
    out=io.StringIO();writer=csv.writer(out)
    writer.writerow(['FLEX','FLEX','FLEX','','Instructions'])
    writer.writerow(['','','','','Copy numeric IDs; maximum 500 lineups'])
    writer.writerow(['','','','','Position','Name + ID','Name','ID','Roster Position','Game Info','TeamAbbrev','AvgPointsPerGame'])
    for p in imported['players']:writer.writerow(['','','','','RB',f'{p["name"]} ({p["source_player_id"]})',p['name'],p['source_player_id'],'FLEX',p['native_game_info'],p['team'],'999'])
    return out.getvalue()


def setup(tmp_path,variant='total_yards'):
    imported=pool(tmp_path,variant)
    report=stat.optimize(stat.Optimize(pool_sha256=imported['sha256']),directory=tmp_path,now=NOW)
    req=export.TemplateImport(pool_sha256=imported['sha256'],source_name='template.csv',source_reference='fixture',source_observed_at=NOW,template_csv=template(imported))
    verified=export.import_template(req,directory=tmp_path,now=NOW)
    return imported,report,req,verified


@pytest.mark.parametrize('variant',['total_yards','touchdowns'])
def test_exact_template_export_roundtrip(tmp_path,variant):
    imported,report,req,verified=setup(tmp_path,variant)
    name,content,receipt=export.build_download(report['sha256'],verified['sha256'],accept_research=True,directory=tmp_path,now=NOW)
    actual=list(csv.reader(io.StringIO(content.decode())));original=list(csv.reader(io.StringIO(req.template_csv)))
    assert actual[0]==['FLEX','FLEX','FLEX','','Instructions']
    assert actual[1][:3]==[p['source_player_id'] for p in report['players']]
    actual[1][:3]=['','',''];assert actual==original
    assert 'research' in name and receipt['entry_ready'] is False and receipt['submission_confirmed'] is False and receipt['assignment_created'] is False
    assert stat.load(receipt['sha256'],tmp_path)['content_hex']==content.hex()
    assert export.import_template(req,directory=tmp_path,now=NOW+timedelta(seconds=1))['sha256']==verified['sha256']


def test_wrong_pool_and_contradictory_native_game(tmp_path):
    imported,report,req,verified=setup(tmp_path)
    req.template_csv=req.template_csv.replace('1)', '91)').replace(',1,FLEX',',91,FLEX')
    with pytest.raises(ValueError,match='different native pool'):export.import_template(req,directory=tmp_path,now=NOW)
    req.template_csv=template(imported).replace(',g,',',other-game,')
    with pytest.raises(ValueError,match='contradictory'):export.import_template(req,directory=tmp_path,now=NOW)


def test_duplicate_slots_not_dict_overwritten_and_no_assignment(tmp_path):
    imported,report,req,verified=setup(tmp_path)
    with pytest.raises(ValueError,match='header'):export.parse_template(req.template_csv.replace('FLEX,FLEX,FLEX,','FLEX,FLEX,FLEX,FLEX,',1))
    with pytest.raises(ValueError,match='blank'):export.parse_template(req.template_csv.replace(',,,,Copy','1,,, ,Copy'))
    with pytest.raises(ValueError,match='header'):export.parse_template('Entry ID,FLEX,FLEX,FLEX\n')
    _, _, receipt = export.build_download(report['sha256'],verified['sha256'],directory=tmp_path,now=NOW)
    assert receipt['ordinary_download_request'] and not receipt['research_acknowledgment_required']
    with pytest.raises(ValueError,match='player_locked'):export.build_download(report['sha256'],verified['sha256'],accept_research=True,directory=tmp_path,now=NOW+timedelta(hours=3))


def test_cross_format_template_binding_and_api_headers(tmp_path,monkeypatch):
    imported,report,req,verified=setup(tmp_path)
    other=pool(tmp_path,'touchdowns');other_report=stat.optimize(stat.Optimize(pool_sha256=other['sha256']),directory=tmp_path,now=NOW)
    with pytest.raises(ValueError,match='binding mismatch'):export.build_download(other_report['sha256'],verified['sha256'],accept_research=True,directory=tmp_path,now=NOW)
    monkeypatch.setattr(stat,'LEDGER',tmp_path)
    original=export.build_download
    monkeypatch.setattr(export,'build_download',lambda key,template,accept_research:original(key,template,accept_research=accept_research,now=NOW))
    app=FastAPI();app.include_router(router);client=TestClient(app)
    url=f'/api/single-stat/records/{report["sha256"]}/download?template_sha256={verified["sha256"]}'
    response=client.get(url)
    assert response.status_code==200 and response.headers['x-single-stat-entry-ready']=='false'
    assert response.headers['x-single-stat-classification']=='RESEARCH_CSV_NOT_SUBMITTED'
    assert response.content.startswith(b'FLEX,FLEX,FLEX,,Instructions')


@pytest.mark.parametrize('variant',['total_yards','touchdowns'])
def test_automatic_download_uses_original_salary_ids_without_template(tmp_path,variant):
    imported=pool(tmp_path,variant)
    report=stat.optimize(stat.Optimize(pool_sha256=imported['sha256']),directory=tmp_path,now=NOW)
    assert report['export']['enabled'] is False  # Old saved evidence is not rewritten.
    ready=export.export_readiness(report['sha256'],directory=tmp_path,now=NOW)
    assert ready['enabled'] and ready['automatic_from_native_pool'] and ready['template_sha256'] is None
    filename,content,receipt=export.build_download(report['sha256'],directory=tmp_path,now=NOW)
    rows=list(csv.reader(io.StringIO(content.decode())))
    assert rows==[['FLEX','FLEX','FLEX'],[p['source_player_id'] for p in report['players']]]
    assert content.endswith(b'\r\n') and receipt['automatic_from_native_pool']
    assert receipt['ordinary_download_request'] and not receipt['research_acknowledgment_required']
    assert receipt['template_record_sha256'] is None and receipt['entry_ready'] is False
    assert stat.load(report['sha256'],tmp_path)==report


def test_automatic_rejects_cross_slate_and_mode_even_with_numeric_ids(tmp_path):
    imported=pool(tmp_path)
    report=stat.optimize(stat.Optimize(pool_sha256=imported['sha256']),directory=tmp_path,now=NOW)
    for field,value in [('game_set_id','wrong-slate'),('variant','passing_yards')]:
        changed={k:v for k,v in report.items() if k!='sha256'};changed[field]=value;bad=stat._save(changed,tmp_path)
        with pytest.raises(ValueError,match='mismatch'):export.build_download(bad['sha256'],accept_research=True,directory=tmp_path,now=NOW)
    changed={k:v for k,v in report.items() if k!='sha256'}
    changed['players']=[dict(p) for p in changed['players']];changed['players'][0]['source_player_id']='44533425'
    bad=stat._save(changed,tmp_path)
    with pytest.raises(ValueError,match='identity'):export.build_download(bad['sha256'],accept_research=True,directory=tmp_path,now=NOW)


def test_automatic_old_report_missing_native_proof_blocks(tmp_path):
    imported=pool(tmp_path)
    imported.pop('sha256');imported['source']['native_csv']='';imported=stat._save(imported,tmp_path)
    # Generate uses frozen forecasts, but download independently requires original source proof.
    report=stat.optimize(stat.Optimize(pool_sha256=imported['sha256']),directory=tmp_path,now=NOW)
    with pytest.raises(ValueError,match='evidence is missing'):export.build_download(report['sha256'],directory=tmp_path,now=NOW)


def test_shared_csv_positional_slots_and_native_id_validation():
    from backend.app.product_services.native_lineup_csv import render_native_lineup_csv
    assert render_native_lineup_csv(['FLEX']*3,[['001','2','3']])==b'FLEX,FLEX,FLEX\r\n001,2,3\r\n'
    assert render_native_lineup_csv([f'T{i}' for i in range(1,7)],[['1','2','3','4','5','6']])==b'T1,T2,T3,T4,T5,T6\r\n1,2,3,4,5,6\r\n'
    for headers,rows in [(['FLEX']*4,[['1','2','3','4']]),(['FLEX']*3,[['1','2']]),(['FLEX']*3,[['1','1','3']]),(['FLEX']*3,[['1','2','3,4']]),(['T1','T3'],[['1','2']])]:
        with pytest.raises(ValueError):render_native_lineup_csv(headers,rows)


def test_automatic_rejects_classic_showdown_roster_roles(tmp_path):
    from backend.app.tests.product.test_single_stat import package,forecast
    req=package();req.native_csv='ID,Name,Team,Game,Roster Position\n1,A,A,g,CPT\n2,B,A,g,FLEX\n3,C,B,g,FLEX\n'
    imported=stat.import_pool(req,None,directory=tmp_path,now=NOW,resolver=lambda s:s,forecaster=forecast)
    report=stat.optimize(stat.Optimize(pool_sha256=imported['sha256']),directory=tmp_path,now=NOW)
    with pytest.raises(ValueError,match='role is not Single Stat'):export.build_download(report['sha256'],directory=tmp_path,now=NOW)


def test_automatic_rejects_ambiguous_original_native_columns(tmp_path):
    import hashlib
    imported=pool(tmp_path);imported.pop('sha256')
    imported['source']['native_csv']=imported['source']['native_csv'].replace('ID,Name,','ID,ID,Name,')
    imported['native_csv_sha256']=hashlib.sha256(imported['source']['native_csv'].encode()).hexdigest();imported=stat._save(imported,tmp_path)
    report=stat.optimize(stat.Optimize(pool_sha256=imported['sha256']),directory=tmp_path,now=NOW)
    with pytest.raises(ValueError,match='columns are missing or ambiguous'):export.build_download(report['sha256'],directory=tmp_path,now=NOW)
