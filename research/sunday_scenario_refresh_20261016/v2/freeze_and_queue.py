from pathlib import Path
from datetime import datetime,UTC
from types import SimpleNamespace
from copy import deepcopy
import json,uuid,httpx
from backend.app.product_services.preliminary_optimizer import save_snapshot
from backend.app.product_services.analyst_preparation import prepare_handoff,HANDOFF_LEDGER
from backend.app.product_services.analyst_packets import load_packet,packet_digest
from backend.app.product_services.analyst_shadow import digest
P=Path(__file__).resolve().parent;load=lambda p:json.loads(Path(p).read_text());base=load('artifacts/preliminary_optimizer_snapshots/6d662321caa3a513bb7720d68f836aca4cad96581314757c5e35d7d794ae207a.json');new=load(P.parent/'v1/packet.json');oldchecked=load_packet('693befcad20dd476c265112431ef39cf0d756795561ea3a10d2603737f23aeca');old=load('research/sunday_refresh_20261015/v2/packet.json');assert packet_digest(old)==oldchecked['preparation_compatibility']['original_packet_sha256'];statuses=load(P/'current_canonical_status_review.json')['rows'];ex=[r for r in statuses if r.get('game_status') in {'OUT','DOUBTFUL','QUESTIONABLE'}];params=load('research/sunday_accepted_defense_refresh_20261016/v2/saved_settings.json')['params'];params['analyst_joint_opportunity_enabled']=False
assert not any(P.glob('*_request.json')), 'Immutable request evidence exists; use a new research version'
for arm,packet in [('old_scenarios_friday_eligibility',old),('refreshed_scenarios',new)]:
 snapshot=deepcopy(base);snapshot.pop('sha256');snapshot['research_derivation']=dict(kind='authored_scenario_comparison_child',parent_snapshot_sha256=base['sha256'],arm=arm,created_at=datetime.now(UTC).isoformat(),projection_cells_unchanged=True,pool_cells_unchanged=True,friday_status_review_path=str(P/'current_canonical_status_review.json'),current_market_review_path=str(P.parent/'v1/current_market_review.json'),limitation='Fresh current evidence informs conservative eligibility and Analyst narrative only. Frozen model/ownership/market values retain morning clocks; no normal preparation or source promotion claimed.')
 manifest=snapshot['assumption_manifest'];manifest['declared_at']=datetime.now(UTC).isoformat();manifest['exclude_player_ids']=sorted(set(manifest['exclude_player_ids'])|{r['player_id'] for r in ex});manifest['friday_source_exclusions']=ex;manifest['other_player_assumption']+=' Current Q/OUT/doubtful are additionally excluded from research; no previously blocked player reinstated.';snapshot['assumption_manifest_sha256']=digest(manifest)
 snapshot['normal_readiness']['status']='NOT_READY';snapshot['normal_readiness']['reason_codes']=sorted(set(snapshot['normal_readiness']['reason_codes'])|{'frozen_forecast_not_refreshed_to_friday_sources'})
 snapshot=save_snapshot(snapshot);assert snapshot['pool']==base['pool']
 result=dict(source_manifest=snapshot['source_manifest'],source_sha256=snapshot['source_sha256'],projection_run_id=snapshot['projection_run_id'])
 request=SimpleNamespace(season=2026,week=6,slate='SUNDAY_MAIN',contest_format='classic',analyst_mode='AUTO',analyst_strategy='MERGED_SCENARIOS')
 handoff=prepare_handoff(request=request,result=result,rows=snapshot['pool'],checked_at=datetime.now(UTC).isoformat(),packets={packet_digest(packet):packet},preliminary_snapshot_sha256=snapshot['sha256'])
 assert handoff['checked_packet_sha256'],handoff
 path=HANDOFF_LEDGER/(snapshot['sha256']+'.json');path.write_text(json.dumps(handoff,indent=2)+'\n')
 armparams=deepcopy(params);armparams.update(analyst_packet_sha256=handoff['checked_packet_sha256'],analyst_handoff_compatibility_sha256=handoff['compatibility_sha256'],analyst_strategy='MERGED_SCENARIOS',analyst_candidates_per_thesis=2,analyst_portfolio_mode='SCENARIO_FIRST')
 req=dict(snapshot_sha256=snapshot['sha256'],optimizer=dict(season=2026,week=6,slate='SUNDAY_MAIN',strategy='classic_large_gpp_v1',contest_format='classic',objective='gpp',optimizer_run_id=str(uuid.uuid4()),projection_run_id=snapshot['projection_run_id'],params=armparams))
 (P/(arm+'_request.json')).write_text(json.dumps(req,indent=2)+'\n');(P/(arm+'_handoff.json')).write_text(json.dumps(handoff,indent=2)+'\n');response=httpx.post('http://127.0.0.1:8000/api/optimizer/preliminary/jobs',json=req,timeout=60);(P/(arm+'_queued.json')).write_text(response.text+'\n');response.raise_for_status();print(arm,response.json()['job']['job_id'],req['optimizer']['optimizer_run_id'],'checked',handoff['checked_packet_sha256'],'changes',len(handoff['changes']),flush=True)
