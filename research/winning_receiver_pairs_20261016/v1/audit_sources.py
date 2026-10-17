from pathlib import Path
import json,hashlib,zipfile,csv,io
P=Path(__file__).resolve().parent
inv=json.loads((P/"inventory.json").read_text())
audit=[]
for source in inv['sources']:
 candidates=[Path(source['original_path']),Path('/Users/wones/NFL')/source['file_name'],Path('/Users/wones/NFL/Processed')/source['file_name'],Path('/Users/wones/Downloads')/source['file_name']];path=next((x for x in candidates if x.exists()),None)
 item=dict(source_file_id=source['source_file_id'],original_path=source['original_path'],located_path=str(path) if path else None,expected_sha256=source['content_sha256'])
 if path:
  h=hashlib.sha256()
  with path.open('rb') as f:
   while chunk:=f.read(1024*1024):h.update(chunk)
  item['sha256']=h.hexdigest();item['hash_matches']=h.hexdigest()==source['content_sha256']
  if path.suffix.lower()=='.zip':
   with zipfile.ZipFile(path) as z:
    names=[n for n in z.namelist() if n.lower().endswith('.csv')];item['zip_members']=names
    with z.open(names[0]) as f:item['headers']=next(csv.reader(io.TextIOWrapper(f,encoding='utf-8-sig')))
    with z.open(names[0]) as f:
     memberhash=hashlib.sha256()
     while chunk:=f.read(1024*1024):memberhash.update(chunk)
    item['csv_member_sha256']=memberhash.hexdigest();item['hash_matches']=memberhash.hexdigest()==source['content_sha256'];item['hash_semantics']='imported uncompressed CSV bytes'
  else:
   with path.open(encoding='utf-8-sig') as f:item['headers']=next(csv.reader(f))
 audit.append(item)
(P/'source_audit.json').write_text(json.dumps(audit,indent=2));print('sources',len(audit),'located',sum(bool(x['located_path']) for x in audit),'hashmatch',sum(x.get('hash_matches',False) for x in audit),flush=True)
