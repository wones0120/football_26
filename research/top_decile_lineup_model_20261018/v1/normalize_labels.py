"""Versioned label correction: official DK cent precision, never input features."""
import csv,gzip,hashlib,io,json,pathlib,zipfile
from backend.app.product_services.lineup_top_decile_research import top_decile_boundary
P=pathlib.Path(__file__).resolve().parent
sources=json.loads(pathlib.Path('research/season_projection_accuracy_20261018/v1/source_completion.json').read_text());inventory=json.loads((P/'dataset_inventory.json').read_text());contexts={r['source_file_id']:r for r in inventory};out=[]
(P/'contests_v2').mkdir(exist_ok=True)
for source in sources:
 path=pathlib.Path(source['path']);data=path.read_bytes();raw=zipfile.ZipFile(io.BytesIO(data)).read(zipfile.ZipFile(io.BytesIO(data)).namelist()[0])if path.suffix=='.zip'else data
 expected=source['source_file_id'].removeprefix('dk_file_')
 if expected not in {hashlib.sha256(data).hexdigest(),hashlib.sha256(raw).hexdigest()}:raise ValueError('Changed source '+str(path))
 points=[];ids=set()
 for r in csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))):
  if not r.get('EntryId')or r['EntryId']in ids:continue
  ids.add(r['EntryId'])
  try:
   score=float(r['Points']);remaining=float(r['TimeRemaining'])
  except(ValueError,TypeError):continue
  if remaining==0:points.append(score)
 boundary=top_decile_boundary(points)
 context=contexts.get(source['source_file_id'])
 if not context:
  out.append(dict(source_file_id=source['source_file_id'],status='not_model_eligible_no_resolved_canonical_source_observations',**boundary));continue
 filename=f"{context['contest_id']}_{source['source_file_id'][-8:]}.json.gz"
 with gzip.open(P/'contests'/filename,'rt')as f:payload=json.load(f)
 context={**context,**boundary,'label_version':'contest_top_decile_dk_cent_v2','source_sha256':expected};payload['context']=context
 for r in payload['rosters']:r['label']=int(round(r['points'],2)>=boundary['points_cutoff'])
 context['coverage_upper_bound_top10_candidates']=sum(r['label']for r in payload['rosters'])
 with gzip.open(P/'contests_v2'/filename,'wt')as f:json.dump(payload,f,allow_nan=False)
 out.append(context)
(P/'dataset_inventory_v2.json').write_text(json.dumps(out,indent=2))
print('verified_sources',len(out),'feature_eligible_contests',sum(r.get('sampled_rosters',0)>0 for r in out),'sampled_rows',sum(r.get('sampled_rosters',0)for r in out),'rich',sum(r.get('rich_sampled_rosters',0)for r in out))
