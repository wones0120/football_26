"""Match saved team pass outputs to unchanged source pass labels; no fit."""
from pathlib import Path
from collections import Counter
import hashlib,json
R=Path(__file__).resolve().parent
m=json.loads((R/'MANIFEST.json').read_text())
meta=json.loads(Path(m['group_metadata_ref']['path']).read_text())
keys={(g['game_id'],g['team']):(i,g)for i,g in enumerate(meta)};out={}
for exp in('pressure_count_model_fits_20261020','workload_direct_count_fits_20261020'):
 for family in('tree','neural'):
  j=json.loads(Path('research',exp,'v1','team_'+family+'.json').read_text());ref=j['prediction_ref'];b=Path(ref['path']).read_bytes();assert len(b)==ref['bytes']and hashlib.sha256(b).hexdigest()==ref['sha256'];rows=json.loads(b)
  if isinstance(rows,dict):rows=rows['rows']
  matches=[];stats=Counter()
  for row in rows:
   key=row['game_id'],row['team']
   if key not in keys:continue
   i,g=keys[key];year=str(g['period']//100)
   if row['actual']['pass_attempts']!=g['pass_budget_label']:stats[year+'_changed_or_unknown_label']+=1;continue
   matches.append(dict(group_index=i,actual=g['pass_budget_label'],saved_prediction=row['predicted']['pass_attempts']));stats[year+'_matched']+=1
  out[exp+'_'+family]=dict(prediction_ref=ref,coverage=dict(stats),matches=matches)
path=R/'TEAM_PASS_BASELINE_MATCHES.json'
encoded=(json.dumps(out,indent=2)+'\n').encode()
if path.exists():assert path.read_bytes()==encoded
else:path.write_bytes(encoded)
m['team_pass_baseline_matches_ref']=dict(path=str(path.resolve()),sha256=hashlib.sha256(encoded).hexdigest(),bytes=len(encoded))
(R/'MANIFEST.json').write_text(json.dumps(m,indent=2)+'\n')
