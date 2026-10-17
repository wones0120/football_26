from pathlib import Path
import json,uuid,httpx
P=Path(__file__).resolve().parent;c=httpx.Client(base_url='http://127.0.0.1:8000',timeout=300)
jid=json.loads((P/'preliminary_prepare_queued.json').read_text())['job']['job_id'];v=c.get('/api/jobs/'+jid).json();(P/'preliminary_prepare_status.json').write_text(json.dumps(v,indent=2)+'\n');assert v['status']=='completed',v
r=c.post('/api/optimizer/preliminary/snapshots',json=dict(preparation_job_id=jid,injury_policy='exclude_unknown_and_questionable',analyst_mode='AUTO'));(P/'snapshot_response.json').write_text(r.text+'\n');r.raise_for_status();f=r.json();handoff=f['analyst_handoff'];assert handoff['checked_packet_sha256'],handoff
params=json.loads((P/'saved_settings.json').read_text())['params'];params['analyst_handoff_compatibility_sha256']=handoff['compatibility_sha256'];params['analyst_packet_sha256']=handoff['checked_packet_sha256'];params['analyst_strategy']=handoff['preferred_strategy'];params['analyst_candidates_per_thesis']=2
if params['analyst_strategy']=='MERGED_SCENARIOS':params['analyst_portfolio_mode']='SCENARIO_FIRST'
params['football_news_evidence']=json.loads(Path('research/sunday_normal_refresh_20261016/v1/qb_refresh.json').read_text())
# Explicitly preserve the failed experimental mechanism as disabled.
params['analyst_joint_opportunity_enabled']=False
req=dict(snapshot_sha256=f['snapshot_sha256'],optimizer=dict(season=2026,week=6,slate='SUNDAY_MAIN',strategy='classic_large_gpp_v1',contest_format='classic',objective='gpp',optimizer_run_id=str(uuid.uuid4()),projection_run_id=f['projection_run_id'],params=params))
assert all(params['season_ppg_top_pct_'+p]==50 for p in ['qb','rb','wr','te']);assert params['max_lineup_overlap']==5
(P/'submitted_request.json').write_text(json.dumps(req,indent=2)+'\n');r=c.post('/api/optimizer/preliminary/jobs',json=req);(P/'optimizer_queued.json').write_text(r.text+'\n');r.raise_for_status();print(json.dumps(dict(projection=f['projection_run_id'],snapshot=f['snapshot_sha256'],checked_packet=handoff['checked_packet_sha256'],queue=r.json()),indent=2))
