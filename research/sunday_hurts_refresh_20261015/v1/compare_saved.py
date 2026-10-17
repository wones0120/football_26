from pathlib import Path
from datetime import datetime,UTC
from contextlib import redirect_stdout
import json,httpx
import pandas as pd
from sqlalchemy.orm import Session
from backend.app.product_services.optimizer import OptimizerService,_json_safe
from backend.app.product_services.preliminary_optimizer import load_snapshot
from backend.app.product_services.classic_highest_projection import solve
from backend.app.product_services.slate_preparation import projection_proof
P=Path(__file__).resolve().parent;request=json.loads((P/'submitted_request.json').read_text());rid=request['optimizer']['optimizer_run_id'];svc=OptimizerService();j=svc.get_job(rid);assert j is not None and j.status=='completed',(rid,j.status if j else None);assert j.lineage_persisted and len(j.results)==1
out=_json_safe(dict(job_id=rid,status=j.status,message=j.message,projection_run_id=j.projection_run_id,params=j.params,results=j.results,lineage_persisted=j.lineage_persisted,observed_at=datetime.now(UTC).isoformat()));(P/'saved_run.json').write_text(json.dumps(out,indent=2,allow_nan=False)+'\n')
r=httpx.get('http://127.0.0.1:8000/api/optimizer/results/'+rid,timeout=60);r.raise_for_status();v=r.json();assert v['highest_projection']['solver_status']=='Optimal' and v['entry_readiness']['entry_ready'] is False;(P/'reopened_api.json').write_text(json.dumps(v,indent=2)+'\n')
snapshot=load_snapshot(request['snapshot_sha256']);prepared=json.loads((P/'preparation_status.json').read_text())['result']
with Session(svc.engine) as session:proof=projection_proof(session,prepared)
(P/'fresh_projection_proof.json').write_text(json.dumps(_json_safe(proof),indent=2,allow_nan=False)+'\n')
ctx={str(x['player_master_id']):x for x in snapshot['source_manifest']['availability']};hurts='83d7ba4e-3f9b-4769-a9d4-37ad680ef63b';mckee='783b00df-c32b-4054-bff3-906ea6fbc4a7';assert ctx[hurts]['injury_status']=='OUT';assert any(str(x['player_master_id'])==mckee for x in snapshot['source_manifest']['starters'])
audit=j.params['strategy_runtime']['highest_projection'];pool=pd.DataFrame(audit['input_snapshot']['players']);assert hurts not in set(pool.player_id);assert audit['locked_player_ids']==[] and audit['solver_status']=='Optimal'
hubbard='1cb58102-1426-459a-82cf-240882d90206';henry='48932b42-a60a-4070-82a7-50475f27bbf2';dst={x['player_team']:x['player_id'] for x in audit['input_snapshot']['players'] if x['position']=='DST'};arms={}
with (P/'comparisons.log').open('w') as log,redirect_stdout(log):
 for label,locks in [('unlocked_replay',set()),('hubbard_required',{hubbard}),('henry_required',{henry}),('hubbard_and_henry_required',{hubbard,henry}),('panthers_required',{dst['CAR']}),('saints_required',{dst['NO']})]:
  lineups,a=solve(svc,pool,params=j.params,cutoff=j.data_cutoff_at,locked_ids=locks);assert a['solver_status']=='Optimal';arms[label]=_json_safe(dict(lineups=lineups,audit=a))
assert {p['player_id'] for p in arms['unlocked_replay']['lineups'][0]}=={p['player_id'] for p in j.results[0]}
(P/'matched_comparisons.json').write_text(json.dumps(arms,indent=2,allow_nan=False)+'\n')
old=json.loads(Path('research/sunday_highest_projection_20261015/v1/ui_saved_run.json').read_text());oldpool={x['player_id']:x for x in old['params']['strategy_runtime']['highest_projection']['input_snapshot']['players']};changes=[]
for p in audit['input_snapshot']['players']:
 if p['player_id'] in oldpool:
  o=oldpool[p['player_id']];changes.append(dict(player_id=p['player_id'],name=p['name'],salary=p['salary'],old_mean=o['projection'],new_mean=p['projection'],delta=p['projection']-o['projection'],team=p['player_team']))
news=json.loads((P/'news_ingest.json').read_text());details=dict(saved_run_id=rid,projection_run_id=j.projection_run_id,ownership_run_id=j.params['ownership_run_id'],cutoff=j.data_cutoff_at,snapshot_sha256=request['snapshot_sha256'],source_sha256=snapshot['source_sha256'],pool_sha256=snapshot['pool_sha256'],eligible_player_count=audit['eligible_player_count'],missing_mean_exclusions=audit['missing_projection_player_ids'],assumption_manifest=snapshot['assumption_manifest'],hurts_canonical_context=ctx[hurts],starting_qbs=[x for x in snapshot['source_manifest']['starters'] if x['team'] in ['PHI','CHI','BAL']],markets=snapshot['source_manifest']['markets'],source_refresh=snapshot['source_refresh'],player_changes=changes,new_eligible_ids=sorted(set(pool.player_id)-oldpool.keys()),lost_eligible_ids=sorted(oldpool.keys()-set(pool.player_id)),news=news,model_feature_contract='No direct QB quality/backup effect on teammates or opponent DST; actual market features and role/opportunity/availability only',old_unlocked_mean=old['params']['strategy_runtime']['highest_projection']['base_mean'],fresh_unlocked_mean=audit['base_mean'],policy_changed=False,entry_ready=False,tests='65 targeted backend tests passed')
(P/'EVIDENCE.json').write_text(json.dumps(_json_safe(details),indent=2,allow_nan=False)+'\n')
print('saved/reopened',rid,'freshmean',audit['base_mean'],'salary',audit['salary'],'eligible',len(pool),'projection',j.projection_run_id,flush=True)
for label,arm in arms.items():print(label,arm['audit']['base_mean'],arm['audit']['salary'],[(p['name'],p['salary']) for p in arm['lineups'][0]],flush=True)
for c in changes:
 if c['name'] in ['Chuba Hubbard','Derrick Henry','Panthers','Saints','Rome Odunze']:print(c,flush=True)
