import csv
import io
from copy import deepcopy
from datetime import UTC,datetime,timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine,select
from sqlalchemy.orm import Session
from backend.app.models import Base,IngestRun,UnresolvedPlayerQueue
from backend.app.db import get_db_session
from backend.app.product_services import tiers,tiers_export
from backend.app.api.tiers_routes import router

NOW=datetime(2026,10,16,12,tzinfo=UTC)
IDS=[f'00000000-0000-0000-0000-{i:012d}' for i in range(1,5)]
HEADER=['Position','Name + ID','Name','ID','Roster Position','Game Info','TeamAbbrev','AvgPointsPerGame','Status']
NATIVE=[['QB','A (1)','A','1','T1','BUF@LV 10/18/2026 04:25PM ET','BUF','10',''],['QB','B (2)','B','2','T1','BAL@CLE 10/18/2026 01:00PM ET','BAL','8',''],['WR','C (3)','C','3','T2','BUF@LV 10/18/2026 04:25PM ET','BUF','9',''],['WR','D (4)','D','4','T2','BAL@CLE 10/18/2026 01:00PM ET','BAL','1','']]
def csv_text(rows):
 s=io.StringIO();csv.writer(s).writerows(rows);return s.getvalue()
def request():return tiers.PoolImport(season=2026,week=6,native_draft_group_id='fixture',source_name='native.csv',source_reference='fixture',native_csv=csv_text([HEADER]+NATIVE),rules_text='Lineups must consist of one player from each Tier and must include players representing at least 2 different NFL games.',projection_snapshot_sha256='a'*64)
def snapshot():
 return dict(scope=dict(season=2026,week=6,slate='SUNDAY_MAIN',contest_format='classic'),classification='PRELIMINARY_RESEARCH',projection_run_id='projection',source_sha256='s',data_cutoff_at='2026-10-15T12:00:00+00:00',normal_readiness={'status':'NOT_READY'},assumption_manifest_sha256='m',assumption_manifest={'exclude_player_ids':[]},source_manifest={'games':[dict(home_team='LV',away_team='BUF',kickoff_at='2026-10-18T20:25:00+00:00'),dict(home_team='CLE',away_team='BAL',kickoff_at='2026-10-18T17:00:00+00:00')]},pool=[dict(player_id=IDS[i],player_team=r[6],position=r[0],projection=float(r[7]),p90=float(r[7])+5,availability_status='ACT') for i,r in enumerate(NATIVE)])
def pool(tmp_path,req=None,snap=None):return tiers.import_pool(req or request(),None,directory=tmp_path,now=NOW,resolver=lambda r:(IDS[int(r['source_player_id'])-1],'fixture_native'),snapshot_loader=lambda key:snap or snapshot())
def optimize(tmp_path,imported=None,**kwargs):return tiers.optimize(tiers.Optimize(pool_sha256=(imported or pool(tmp_path))['sha256'],accept_baseline_research=True,**kwargs),directory=tmp_path,now=NOW)
def template(pool):
 n=len(pool['tier_labels']);rows=[pool['tier_labels']+['','Instructions'],['']*(n+1)+['Keep this instruction'],[' '],['']*(n+1)+HEADER[:-1]]
 rows.extend(['']*(n+1)+r[:-1] for r in NATIVE)
 return csv_text(rows)
def bound_template(tmp_path,p):return tiers_export.import_template(tiers_export.TemplateImport(pool_sha256=p['sha256'],source_name='template.csv',source_reference='fixture',template_csv=template(p)),directory=tmp_path,now=NOW)

def test_exact_tiers_one_per_and_two_games_without_salary_or_position_limits(tmp_path):
 p=pool(tmp_path);r=optimize(tmp_path,p);line=r['lineups'][0]
 assert line['projected_points']==17 # A+C=19 is illegal: same game; B+C=17 wins
 assert [x['name'] for x in line['players']]==['B','C']
 assert tiers.legal_lineup(line['players'],['T1','T2'])
 assert r['rules']['salary_cap'] is None and r['rules']['captain_multiplier'] is None
 assert r['lineup_count']==1 and r['entry_ready'] is False and r['constraints_relaxed'] is False
 assert tiers.load(r['sha256'],tmp_path)==r
 assert p['native_csv_sha256']==tiers.hashlib.sha256(request().native_csv.encode()).hexdigest()
 assert (tiers.Path(p['raw_directory'])/'rules.txt').read_text()==request().rules_text

def test_variable_tiers_top_k_and_stable_retries(tmp_path):
 p=pool(tmp_path);r=optimize(tmp_path,p,num_lineups=10)
 assert r['lineup_count']==2 and r['requested_lineups']==10 and r['solver_status']=='OPTIMAL_AVAILABLE_UNDERFILLED'
 assert len({tuple(x['player_master_id'] for x in rr['players']) for rr in r['lineups']})==2
 retry=tiers.import_pool(request(),None,directory=tmp_path,now=NOW+timedelta(hours=1),resolver=lambda _:(_ for _ in ()).throw(AssertionError('must replay')),snapshot_loader=lambda _:None)
 assert retry==p
 assert tiers.optimize(tiers.Optimize(pool_sha256=p['sha256'],num_lineups=10,accept_baseline_research=True),directory=tmp_path,now=NOW+timedelta(hours=1))==r

@pytest.mark.parametrize('mutation', ['showdown','duplicate','tier_gap','team','kickoff'])
def test_reject_malformed_native_and_schedule_scope(tmp_path,mutation):
 req=request();rr=deepcopy(NATIVE)
 if mutation=='showdown':rr[0][4]='CPT'
 if mutation=='duplicate':rr[1][3]='1'
 if mutation=='tier_gap':rr[2][4]=rr[3][4]='T3'
 if mutation=='team':rr[0][6]='NE'
 if mutation=='kickoff':rr[0][5]='BUF@LV 10/18/2026 01:00PM ET'
 req.native_csv=csv_text([HEADER]+rr)
 with pytest.raises(ValueError):pool(tmp_path,req)

def test_source_scope_and_explicit_research_acceptance(tmp_path):
 s=snapshot();s['scope']['week']=5
 with pytest.raises(ValueError,match='snapshot must match'):pool(tmp_path,snap=s)
 p=pool(tmp_path)
 with pytest.raises(ValueError,match='Explicitly accept'):tiers.optimize(tiers.Optimize(pool_sha256=p['sha256']),directory=tmp_path,now=NOW)
 with pytest.raises(ValueError,match='canonical players'):optimize(tmp_path,p,excluded_player_ids=['foreign'])
 assert tiers.readiness(p,now=NOW+timedelta(days=4))['status']=='BLOCKED'

def test_native_out_and_unknown_exclusions_do_not_rewrite_models(tmp_path):
 req=request();rows=deepcopy(NATIVE);rows[1][-1]='Q';req.native_csv=csv_text([HEADER]+rows);s=snapshot();s['assumption_manifest']['exclude_player_ids']=[IDS[3]];p=pool(tmp_path,req,s)
 with pytest.raises(ValueError,match='No legal'):optimize(tmp_path,p)
 r=optimize(tmp_path,p,exclude_questionable=False)
 assert r['lineups'][0]['players'][0]['projection']==8 and s['pool'][1]['projection']==8
 assert any('frozen_availability_or_role_unknown_exclusion' in x['reason_codes'] for x in r['readiness']['players'])

def test_duplicate_canonical_and_projection_identity_conflicts(tmp_path):
 with pytest.raises(ValueError,match='Duplicate canonical'):tiers.import_pool(request(),None,directory=tmp_path,now=NOW,resolver=lambda r:(IDS[0],'fixture'),snapshot_loader=lambda _:snapshot())
 s=snapshot();s['pool'][0]['player_team']='NE'
 with pytest.raises(ValueError,match='conflicts'):pool(tmp_path,snap=s)

def test_unresolved_native_rows_create_queue_not_drop(tmp_path,monkeypatch):
 monkeypatch.setattr(tiers.snapshots,'load_snapshot',lambda _:snapshot());monkeypatch.setattr(tiers,'LEDGER',tmp_path)
 from backend.app.product_services import analyst_preparation
 monkeypatch.setattr(analyst_preparation,'load_snapshot_handoff',lambda _:None)
 engine=create_engine('sqlite://');Base.metadata.create_all(engine)
 with Session(engine) as session:
  p=tiers.import_pool(request(),session,now=NOW)
  assert len(p['players'])==4 and all(r['player_master_id'] is None for r in p['players'])
  run=session.get(IngestRun,p['ingest_run_id']);assert (run.rows_raw,run.rows_curated,run.rows_unresolved)==(4,0,4)
  assert len(session.scalars(select(UnresolvedPlayerQueue)).all())==4
  assert tiers.readiness(p,now=NOW)['missing_tiers']==['T1','T2']

def test_template_roundtrip_preserves_every_reference_and_metadata_cell(tmp_path):
 p=pool(tmp_path);r=optimize(tmp_path,p);t=bound_template(tmp_path,p)
 name,data,receipt=tiers_export.build_download(r['sha256'],t['sha256'],directory=tmp_path,now=NOW)
 original=list(csv.reader(io.StringIO(t['source']['template_csv'])));got=list(csv.reader(io.StringIO(data.decode())))
 assert got[0]==['T1','T2','','Instructions'] and got[1][:2]==['2','3']
 expected=deepcopy(original);expected[1][:2]=['2','3'];assert got==expected
 assert receipt['entry_ready'] is False and receipt['submission_confirmed'] is False
 assert tiers_export.build_download(r['sha256'],t['sha256'],accept_research=True,directory=tmp_path,now=NOW+timedelta(minutes=1))[2]==receipt

@pytest.mark.parametrize('bad', ['tier_order','native_id','native_tier','existing_assignment'])
def test_template_mismatch_never_substitutes_native_ids(tmp_path,bad):
 p=pool(tmp_path);rows=list(csv.reader(io.StringIO(template(p))))
 if bad=='tier_order':rows[0][:2]=['T2','T1']
 if bad=='native_id':rows[4][6]='999'
 if bad=='native_tier':rows[4][7]='T2'
 if bad=='existing_assignment':rows[1][0]='1'
 with pytest.raises(ValueError):tiers_export.import_template(tiers_export.TemplateImport(pool_sha256=p['sha256'],source_name='bad.csv',source_reference='fixture',template_csv=csv_text(rows)),directory=tmp_path,now=NOW)

def test_api_roundtrip_read_reopen_optimize_and_csv(tmp_path,monkeypatch):
 monkeypatch.setattr(tiers,'LEDGER',tmp_path);import_at=tiers.import_pool;opt_at=tiers.optimize;ready_at=tiers.readiness
 monkeypatch.setattr(tiers,'import_pool',lambda req,session:import_at(req,session,now=NOW,resolver=lambda r:(IDS[int(r['source_player_id'])-1],'fixture'),snapshot_loader=lambda _:snapshot()))
 monkeypatch.setattr(tiers,'optimize',lambda req:opt_at(req,now=NOW));monkeypatch.setattr(tiers,'readiness',lambda p,**kw:ready_at(p,**{'now':NOW,**kw}));app=FastAPI();app.include_router(router);app.dependency_overrides[get_db_session]=lambda:None;client=TestClient(app)
 response=client.post('/api/tiers/pools',json=request().model_dump());assert response.status_code==200,response.text;p=response.json()
 response=client.post('/api/tiers/optimize',json={'pool_sha256':p['sha256'],'accept_baseline_research':True});assert response.status_code==200,response.text;r=response.json()
 assert client.get('/api/tiers/records/'+r['sha256']).json()==r
 t=client.post('/api/tiers/templates',json={'pool_sha256':p['sha256'],'source_name':'template.csv','source_reference':'fixture','template_csv':template(p)});assert t.status_code==200,t.text
 export=client.get(f"/api/tiers/records/{r['sha256']}/download",params={'template_sha256':t.json()['sha256']});assert export.status_code==200,export.text;assert list(csv.reader(io.StringIO(export.text)))[1][:2]==['2','3']
 assert client.get('/api/tiers/records/bad').status_code==404

def test_automatic_native_download_without_template(tmp_path):
 p=pool(tmp_path);r=optimize(tmp_path,p)
 assert tiers_export.export_readiness(r['sha256'],directory=tmp_path,now=NOW)['enabled']
 name,data,receipt=tiers_export.build_download(r['sha256'],directory=tmp_path,now=NOW)
 assert data==b'T1,T2\r\n2,3\r\n'
 assert receipt['native_roster_ids']==['2','3'] and receipt['template_sha256'] is None
 assert receipt['native_csv_sha256']==p['native_csv_sha256']
 with pytest.raises(ValueError,match='blocked'):tiers_export.build_download(r['sha256'],accept_research=True,directory=tmp_path,now=NOW+timedelta(days=4))


def test_native_download_rechecks_original_raw_and_saved_scope(tmp_path):
 p=pool(tmp_path);r=optimize(tmp_path,p)
 wrong=tiers.save({**{k:v for k,v in r.items() if k!='sha256'},'week':7},tmp_path)
 with pytest.raises(ValueError,match='scope mismatch'):tiers_export.build_download(wrong['sha256'],accept_research=True,directory=tmp_path,now=NOW)
 path=tiers.Path(p['raw_directory'])/'native.csv';path.write_bytes(path.read_bytes()+b'\n')
 with pytest.raises(ValueError,match='content hash mismatch'):tiers_export.build_download(r['sha256'],accept_research=True,directory=tmp_path,now=NOW)

def test_status_refresh_preserves_model_q_out_and_blank_uncertainty(tmp_path):
 from backend.app.product_services import tiers_status
 req=request();rows=deepcopy(NATIVE);rows[0][-1]='Q';req.native_csv=csv_text([HEADER]+rows);p=pool(tmp_path,req)
 refresh=dict(snapshot_id='official',context_run_id='context',observed_at=NOW.isoformat(),identity_unresolved=[],complete_team_coverage=True)
 facts=[dict(player_master_id=IDS[0],injury_status=None,evidence_json={'practice_report':{'practice_status':'Full Participation in Practice'}}),dict(player_master_id=IDS[1],injury_status='OUT',evidence_json={})]
 updated=tiers_status.apply_refresh(p,refresh,facts,directory=tmp_path,now=NOW)
 assert updated['parent_pool_sha256']==p['sha256'] and updated['projection_source']==p['projection_source']
 assert [x['projection'] for x in updated['players']]==[x['projection'] for x in p['players']]
 assert updated['players'][0]['questionable'] and updated['players'][0]['refreshed_status']['game_status'] is None
 assert 'refreshed_official_unavailable_or_doubtful' in updated['players'][1]['reason_codes']
 assert updated['players'][2]['refreshed_status']['listed_in_official_report'] is False
 assert updated['entry_ready'] is False and updated['status_refresh']['final_entry_ready'] is False
 assert tiers.load(p['sha256'],tmp_path)==p
 with pytest.raises(ValueError,match='incomplete'):tiers_status.apply_refresh(p,{**refresh,'complete_team_coverage':False},facts,directory=tmp_path,now=NOW)
 with pytest.raises(ValueError,match='future'):tiers_status.apply_refresh(p,{**refresh,'observed_at':(NOW+timedelta(hours=1)).isoformat()},facts,directory=tmp_path,now=NOW)


def test_native_source_rejects_ambiguous_columns_and_non_numeric_ids():
 with pytest.raises(ValueError,match='unique'):tiers.parse_csv(csv_text([HEADER+['ID']]+[r+['99'] for r in NATIVE]))
 rows=deepcopy(NATIVE);rows[0][3]='not-native-id'
 with pytest.raises(ValueError,match='numeric'):tiers.parse_csv(csv_text([HEADER]+rows))
