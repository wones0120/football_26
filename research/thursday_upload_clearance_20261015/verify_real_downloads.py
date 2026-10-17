"""Read-only audit of Chrome-created Thursday CSVs and immutable server receipts."""
from pathlib import Path
import csv,io,json,hashlib,shutil
import httpx
from sqlalchemy import text
from backend.app.product_dependencies import get_optimizer_service
from backend.app.product_services.gpp_recommendation import recommended_lineup
from backend.app.product_services.saved_upload_readiness import require_clearance
root=Path(__file__).resolve().parent
service=get_optimizer_service(); proof=[]
for label,rid in [('normal','706ae9ad-0327-4b76-8254-6585adc073ef'),('contrarian','5cf2ed29-824f-4ef7-84d1-cf770b5e0142')]:
 job=service.get_job(rid)
 assert job.params['entry_readiness']['entry_ready'] is False
 clearance_id=require_clearance(service.engine,job)
 with service.engine.connect() as c:
  clearance=dict(c.execute(text('SELECT record_id,recorded_at,record_json FROM target.evaluation_record WHERE record_id=:id'),{'id':clearance_id}).mappings().one())
  receipts=[dict(r) for r in c.execute(text("SELECT record_id,recorded_at,record_json FROM target.evaluation_record WHERE optimizer_run_id=:id AND kind='export' ORDER BY recorded_at"),{'id':rid}).mappings()]
 (root/f'{label}_clearance.json').write_text(json.dumps(clearance,indent=2,default=str)+'\n')
 saved_lineups=job.results
 for mode in ['recommended','all']:
  suffix='_recommended' if mode=='recommended' else ''
  path=Path('/Users/wones/Downloads')/f'draftkings_showdown_{rid}{suffix}.csv'
  content=path.read_bytes()
  response=httpx.get(f'http://127.0.0.1:8000/api/optimizer/results/{rid}/draftkings/download',params={'recommended_only':mode=='recommended'},timeout=30)
  assert response.status_code==200 and response.content==content, (response.status_code,response.text[:250])
  sha=hashlib.sha256(content).hexdigest()
  parsed=list(csv.reader(io.StringIO(content.decode())))
  assert parsed[0]==['CPT']+['FLEX']*5
  selected=[recommended_lineup(job)] if mode=='recommended' else saved_lineups
  assert len(parsed)-1==len(selected)==(1 if mode=='recommended' else 4)
  numbers=[]
  for native,lineup in zip(parsed[1:],selected):
   cpt=[p for p in lineup if p['roster_position']=='CPT']; flex=[p for p in lineup if p['roster_position']=='FLEX']
   assert len(cpt)==1 and len(flex)==5 and len({p['player_id'] for p in lineup})==6
   assert native[0]==cpt[0]['dk_captain_id'] and set(native[1:])=={p['dk_player_id'] for p in flex}
   assert len(native)==6 and all(v.isdigit() for v in native)
   assert sum(p['salary'] for p in lineup)<=50000
   numbers.append(next(n for n,l in enumerate(saved_lineups,1) if l==lineup))
  matches=[r for r in receipts if r['record_json']['payload']['content_sha256']==sha]
  assert len(matches)==1, matches
  receipt=matches[0]; payload=receipt['record_json']['payload']
  assert bytes.fromhex(payload['content_hex'])==content and payload['submission_confirmed'] is False
  assert payload['upload_clearance_record_id']==clearance_id
  assert len(payload['rows'])==len(selected) and all(r['saved_lineup_ids'] for r in payload['rows'])
  copy=root/f'{label}_{mode}.csv';shutil.copyfile(path,copy)
  (root/f'{label}_{mode}_export_receipt.json').write_text(json.dumps(receipt,indent=2,default=str)+'\n')
  proof.append(dict(intent=label,mode=mode,optimizer_run_id=rid,browser_download_path=str(path),deliverable_path=str(copy),
   row_count=len(parsed)-1,sha256=sha,export_receipt_id=receipt['record_id'],clearance_record_id=clearance_id,
   selected_saved_numbers=numbers,clearance_status=clearance['record_json']['payload']['status'],
   checked_at=clearance['record_json']['payload']['checked_at'],valid_until=clearance['record_json']['payload']['valid_until'],
   final_active_confirmed=False,submission_confirmed=False,salaries=[sum(p['salary'] for p in l) for l in selected]))
(root/'VERIFIED_DOWNLOADS.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps([{k:r[k] for k in ['intent','mode','row_count','selected_saved_numbers','sha256','clearance_status']} for r in proof],indent=2))
