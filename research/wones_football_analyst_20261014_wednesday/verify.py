"""Check every keyword used by the documented simple schema and semantic gate.

Not a general JSON Schema engine; rejects unknown vocabulary rather than skipping it.
"""
from pathlib import Path
from datetime import datetime,timezone
from uuid import UUID
import json,hashlib,re
from backend.app.product_services.analyst_packets import validate
P=Path(__file__).resolve().parent;O=P/'v1'
packet=json.loads((O/'packet.json').read_text());schema_path=Path('research/pregame_ai_packet_20261013/packet.schema.json');schema=json.loads(schema_path.read_text())
errors=[]
allowed={'$schema','$id','title','type','const','required','properties','items','enum','minItems','maxItems','uniqueItems','minLength','pattern','format'}
def check(x,s,path='$'):
 unknown=set(s)-allowed
 if unknown:errors.append(path+' unknown schema vocabulary '+str(unknown));return
 types={'object':dict,'array':list,'string':str,'null':type(None),'boolean':bool}
 if 'type' in s:
  ts=s['type'] if isinstance(s['type'],list) else [s['type']]
  if not any(isinstance(x,types[t]) for t in ts):errors.append(path+' type');return
 if 'const' in s and x!=s['const']:errors.append(path+' const')
 if 'enum' in s and x not in s['enum']:errors.append(path+' enum')
 if isinstance(x,dict):
  for k in s.get('required',[]):
   if k not in x:errors.append(path+' missing '+k)
  for k,child in s.get('properties',{}).items():
   if k in x:check(x[k],child,path+'.'+k)
 if isinstance(x,list):
  if len(x)<s.get('minItems',0) or len(x)>s.get('maxItems',float('inf')):errors.append(path+' item count')
  if s.get('uniqueItems') and len({json.dumps(y,sort_keys=True) for y in x})!=len(x):errors.append(path+' duplicates')
  for i,y in enumerate(x):check(y,s.get('items',{}),path+f'[{i}]')
 if isinstance(x,str):
  if len(x)<s.get('minLength',0):errors.append(path+' length')
  if 'pattern' in s and not re.search(s['pattern'],x):errors.append(path+' pattern')
  try:
   if s.get('format')=='uuid':UUID(x)
   if s.get('format')=='date-time':
    if datetime.fromisoformat(x.replace('Z','+00:00')).tzinfo is None:raise ValueError('timezone')
  except ValueError:errors.append(path+' format')
check(packet,schema);semantic=validate(packet)
assert not errors+semantic,errors+semantic
(O/'validation.json').write_text(json.dumps({'valid':True,'errors':semantic,'documented_schema_errors':errors,'schema_path':str(schema_path),'schema_check':'All used schema keywords checked by local limited-vocabulary checker; jsonschema package unavailable.','validator':'backend.app.product_services.analyst_packets.validate','checked_at':datetime.now(timezone.utc).isoformat()},indent=2)+'\n')
(O/'evidence_index.json').write_text(json.dumps({'sources':packet['sources'],'prior_workload_reused':True,'prior_baseline_reused':True,'new_model_run':False,'new_database_import':False,'prime_time_gaps':packet['prime_time_previews']},indent=2)+'\n')
external=[Path(x['path']) for x in packet['predecessors']]+[Path(packet['baseline_binding']['snapshot_path']),schema_path,Path('research/pregame_ai_packet_20261013/PROTOCOL.md'),Path('backend/app/product_services/analyst_packets.py')]
files={str(f.resolve()):hashlib.sha256(f.read_bytes()).hexdigest() for f in list(P.rglob('*'))+external if f.is_file() and f.name!='manifest.json'}
manifest={'created_at':datetime.now(timezone.utc).isoformat(),'packet_id':packet['packet_id'],'packet_sha256':hashlib.sha256((O/'packet.json').read_bytes()).hexdigest(),'files':files,'validation_errors':semantic,'documented_schema_errors':errors,'database_access':'SET TRANSACTION READ ONLY; rollback','live_mutations':False,'new_files_only':True,'coverage':'Ten Sunday preliminary game opinions; Thursday conditional player review; SNF/MNF game previews without salary/canonical-role coverage'}
(O/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print('Semantic and documented schema checks passed;',len(files),'manifest files')
