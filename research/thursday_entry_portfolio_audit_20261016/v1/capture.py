"""Read-only capture of original Thursday evidence; no report rebuild or repair."""
from pathlib import Path
from datetime import datetime,UTC
import hashlib,json
from sqlalchemy import text
from backend.app.product_services.optimizer import OptimizerService,_json_safe
from backend.app.product_services.slate_learning import SlateLearningService
from backend.app.product_services.weekly_learning_library import list_reports,load_report
P=Path(__file__).resolve().parent
RUNS=['706ae9ad-0327-4b76-8254-6585adc073ef','5cf2ed29-824f-4ef7-84d1-cf770b5e0142']
def save(name,value):
 encoded=json.dumps(_json_safe(value),sort_keys=True,separators=(',',':'),allow_nan=False).encode();path=P/name
 if path.exists() and path.read_bytes()!=encoded:raise ValueError(f'Capture already exists: {name}')
 if not path.exists():path.write_bytes(encoded)
 return dict(path=str(path),sha256=hashlib.sha256(encoded).hexdigest(),bytes=len(encoded))
engine=OptimizerService().engine;service=SlateLearningService(engine=engine);files={}
with engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'))
 reports=[dict(r) for r in c.execute(text("SELECT report_id,season,week,slate,entry_user,evidence_hash,status,created_at FROM target.slate_learning_report WHERE season=2026 AND week=6 ORDER BY created_at DESC,report_id DESC")).mappings()]
 files['report_inventory']=save('report_inventory.json',reports)
 selected=next(r for r in reports if r['slate'].upper()=='THURSDAY_NIGHT')
 report=c.execute(text('SELECT report_json FROM target.slate_learning_report WHERE report_id=:id'),dict(id=selected['report_id'])).scalar_one()
 files['latest_slate_report']=save('latest_slate_report.json',report)
 username=selected['entry_user'];evidence=service._load_evidence(c,season=2026,week=6,slate='THURSDAY_NIGHT',entry_user=username)
 files['raw_evidence']=save('raw_evidence.json',evidence)
 runs=[]
 for run_id in RUNS:
  run=dict(c.execute(text('SELECT * FROM target.optimizer_run WHERE optimizer_run_id=:id'),dict(id=run_id)).mappings().one())
  run['lineups']=[dict(r) for r in c.execute(text('SELECT l.*,p.slot_index,p.roster_position,p.player_id,p.projection,p.player_json FROM target.lineup l JOIN target.lineup_player p USING(lineup_id) WHERE l.optimizer_run_id=:id ORDER BY l.lineup_number,p.slot_index'),dict(id=run_id)).mappings()]
  runs.append(run)
 files['saved_runs']=save('saved_runs.json',runs)
 exports=[dict(r) for r in c.execute(text("SELECT * FROM target.evaluation_record WHERE optimizer_run_id IN (:a,:b) ORDER BY recorded_at,record_id"),dict(a=RUNS[0],b=RUNS[1])).mappings()]
 files['run_evaluation_records']=save('run_evaluation_records.json',exports)
 details=[dict(r) for r in c.execute(text('SELECT * FROM target.slate_learning_run_detail WHERE detail_id IN (SELECT value->\'candidate_detail\'->>\'detail_id\' FROM target.slate_learning_report r CROSS JOIN LATERAL jsonb_array_elements(r.report_json->\'optimizer_effectiveness\'->\'runs\') value WHERE r.report_id=:id) OR detail_id IN (SELECT value->\'entry_evidence\'->>\'detail_id\' FROM target.slate_learning_report r CROSS JOIN LATERAL jsonb_array_elements(r.report_json->\'entries\') value WHERE r.report_id=:id)'),dict(id=selected['report_id'])).mappings()]
 files['latest_report_details']=save('latest_report_details.json',details)
 history=[dict(r) for r in c.execute(text("SELECT content_sha256,original_path,imported_at,encode(sha256(raw_content),'hex') AS actual_raw_sha256 FROM target.dk_entry_history_snapshot ORDER BY imported_at")).mappings()]
 files['entry_history_sources']=save('entry_history_sources.json',history)
weekly=list_reports(entry_user=username,season=2026,week=6,latest_per_week=False)
files['weekly_inventory']=save('weekly_inventory.json',weekly)
if weekly:
 receipt,report,raw=load_report(weekly[0]['sha256'],entry_user=username)
 files['latest_weekly_report']=save('latest_weekly_report.json',report)
 files['latest_weekly_receipt']=save('latest_weekly_receipt.json',receipt)
manifest=dict(captured_at=datetime.now(UTC).isoformat(),read_only=True,report_id=selected['report_id'],entry_user=username,files=files,
 original_evidence_unchanged=True,no_report_rebuild=True,no_optimizer_rerun=True)
(P/'capture_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(dict(report_id=selected['report_id'],contests=len(evidence['contests']),observed_user_entries=len(evidence['entries']),field_rows=len(evidence['field_entries']),saved_runs=len(evidence['optimizer_runs']),latest_detail_records=len(details),weekly_versions=len(weekly)),indent=2))
