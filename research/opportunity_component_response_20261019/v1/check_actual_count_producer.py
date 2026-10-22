import json,traceback
from pathlib import Path
from datetime import datetime,UTC
from unittest.mock import patch
from backend.app.db import engine
from backend.app.product_services.optimizer import OptimizerService,_json_safe
from backend.app.product_services.kicker_roles import assign_kicker_roles
from backend.app.product_services.player_roles import resolve_player_roles
from backend.app.product_services.workload_count_forecast import prepare_receipt
from backend.app.product_services.count_scenario_response import count_world
root=Path('research/opportunity_component_response_20261019/v1')
prepared=json.loads((root/'failed_numeric_checkpoint.json').read_text())['preparation_result']
model=json.loads((root/'diagnostic_existing_reference_model.json').read_text())
cutoff=datetime.fromisoformat(prepared['data_cutoff_at'])
service=OptimizerService();service.engine=engine
pool=service._load_player_pool(2026,6,'MONDAY_NIGHT',projection_run_id=prepared['projection_run_id'],ownership_run_id=prepared.get('ownership_run_id'),evidence_cutoff_at=cutoff,require_explicit_runs=True)
pool,_=assign_kicker_roles(pool);pool,_=resolve_player_roles(pool)
rows=_json_safe(pool.to_dict('records'));(root/'actual_frozen_pool.json').write_text(json.dumps(rows,indent=2))
with patch('backend.app.product_services.workload_count_forecast.fit_team_model',return_value=model):
 receipt=prepare_receipt(engine,rows,season=2026,week=6,cutoff=cutoff,projection_run_id=prepared['projection_run_id'],opportunity_source_context=prepared['source_manifest']['opportunity_source'],games=prepared['source_manifest']['games'],markets=prepared['source_manifest']['markets'])
(root/'actual_diagnostic_count_receipt.json').write_text(json.dumps(receipt,indent=2))
assert len(rows)==60
inactive=[p for p in receipt['players'] if p.get('world_activity') is False]
assert len(inactive)==24
assert all(all(v==0 for v in p['counts'].values()) for p in inactive)
practice=[p for p in inactive if p.get('replacement_vacancy_eligible') is False]
assert len(practice)==14
assert all(p['player_master_id'] not in receipt['availability_conditions']['hypothetical_active_role_vacancies'] for p in practice)
assert receipt['team_opportunity_model_inference']['status']=='forecast_complete'
for t,b in receipt['teams'].items():
 assert all(v['unallocated'] is None or v['unallocated']>=-1e-6 for v in b['reconciliation'].values())
world=count_world(receipt,dict(scenario_id='diagnostic_reference',assumptions=[dict(kind='passing_volume',game_id='2026_06_WAS_SF',team='WAS',factor=1.,elasticity=.7)]),{p['player_id']:p.get('projection') for p in rows},cutoff=cutoff)
(root/'actual_diagnostic_world.json').write_text(json.dumps(world,indent=2))
assert all(p['conditional_mean']==0 for p in world['response']['players'] if p['player_master_id'] in {a['player_master_id'] for a in inactive})
summary=dict(status='actual_full_producer_diagnostic_pass',operational=False,new_model_fits=0,canonical_native_actors=len(rows),full_source_actors=len(receipt['players']),inactive_zeros=len(inactive),practice_no_vacancies=len(practice),cutoff=str(cutoff),projection_run_id=prepared['projection_run_id'],team_inference=receipt['team_opportunity_model_inference']['predictions'],core=[])
response={p['player_master_id']:p for p in receipt['component_response']['players']}
for p in receipt['players']:
 if p.get('name') in ['Jayden Daniels','Terry McLaurin','Brock Purdy','Christian McCaffrey','George Kittle','Rachaad White','Austin Ekeler','Jacory Croskey-Merritt']:
  summary['core'].append(dict(name=p['name'],counts=p['counts'],raw_history=p['raw_history'],response=response[p['player_master_id']]))
(root/'actual_producer_diagnostic.json').write_text(json.dumps(summary,indent=2))
print(json.dumps({k:v for k,v in summary.items() if k not in ['team_inference','core']}))
print([(p['name'],p['counts'],p['response']['conditional_mean']) for p in summary['core']])
