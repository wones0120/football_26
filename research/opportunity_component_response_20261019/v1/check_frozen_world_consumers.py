"""Read-only frozen actual diagnostic; no operational generation, fit or source refresh."""
import json
from pathlib import Path
import pandas as pd
from backend.app.product_services.analyst_packets import load_packet,packet_digest
from backend.app.product_services.analyst_scenarios import build_scenarios,projection_distribution_pool
from backend.app.product_services.analyst_research_requests import semantic_dependencies,ensure_requests,load_request
from backend.app.product_services.count_scenario_response import count_world
from backend.app.product_services.shared_world_runtime import common_worlds
from backend.app.product_services.optimizer import _json_safe
ROOT=Path(__file__).resolve().parent
receipt=json.loads((ROOT/'actual_diagnostic_count_receipt.json').read_text())
rows=json.loads((ROOT/'actual_frozen_pool.json').read_text())
prepared=json.loads((ROOT/'failed_numeric_checkpoint.json').read_text())['preparation_result']
cutoff=prepared['data_cutoff_at']
packet=load_packet('993ec342957f6431c00d3dee0b294d175e2804974617b61d9b52e060ae3f16f2')
pool,_=projection_distribution_pool(pd.DataFrame(rows),mean_only=True)
worlds=build_scenarios(packet,_json_safe(pool.to_dict('records')),fmt='SHOWDOWN',decision_at=cutoff,
    mean_only=True,measurement_rows=rows,count_receipt=receipt)
assert len(worlds)==2
assert all(w.get('count_component_response') for w in worlds)
assert all(m['response_ancestry']=='matched_linear_count_response_v1' for w in worlds for m in w['moments'].values() if m.get('component_response'))
base={p['player_id']:p.get('projection') for p in rows}
replacement=count_world(receipt,dict(scenario_id='DIAGNOSTIC_NOT_AUTHORED_OR_OPERATIONAL',label='Sensitivity only; fractions not fitted or promoted',assumptions=[
    dict(kind='workload_transfer',game_id='2026_06_WAS_SF',team='WAS',workload='carries',from_player_master_id='1c9ad383-3607-4fe2-98f2-1c5e0b594b0b',to_player_master_id=pid,fraction=fraction,elasticity=.7)
    for pid,fraction in [('c7797b6e-5b7e-410f-9714-ddcef07d2d91',.5),('d9545b80-2326-4d32-8982-f7208318a32d',.25)]]),base,cutoff=cutoff)
by_id={p['player_master_id']:p for p in replacement['response']['players']}
assert by_id['1c9ad383-3607-4fe2-98f2-1c5e0b594b0b']['conditional_mean']==0
assert by_id['c7797b6e-5b7e-410f-9714-ddcef07d2d91']['conditional_mean']>base['c7797b6e-5b7e-410f-9714-ddcef07d2d91']
assert by_id['d9545b80-2326-4d32-8982-f7208318a32d']['conditional_mean']==base['d9545b80-2326-4d32-8982-f7208318a32d']
assert replacement['response']['semantic_values']['new']['players']
deps=semantic_dependencies(games=prepared['source_manifest']['games'],rows=rows,checked_at=cutoff,
    source_manifest=prepared['source_manifest'],workload_receipt=receipt)
requests=ensure_requests(deps,prior_packet_sha256=packet_digest(packet),requested_at=cutoff,directory=ROOT/'diagnostic_request_artifacts')
for request in requests:
 loaded=load_request(request['request_id'],directory=ROOT/'diagnostic_request_artifacts')
 assert loaded['identity']['dependency_sha256']==request['identity']['dependency_sha256']
# Exact serialization boundary used by persisted results and app payloads.
serialized=json.dumps(_json_safe(dict(scenarios=worlds,replacement=replacement)),allow_nan=False)
(ROOT/'actual_world_consumer_diagnostic.json').write_text(json.dumps(dict(status='pass',diagnostic_only=True,
    new_fits=0,native_actors=len(rows),full_count_actors=len(receipt['players']),common_scenarios=len(worlds),
    scenario_vector_actors=[len(w['moments']) for w in worlds],serialized_world_bytes=len(serialized.encode()),
    diagnostic_request_ids=[r['request_id'] for r in requests],dependency_sha256=deps['dependency_sha256'],
    request_bytes=[(ROOT/'diagnostic_request_artifacts'/'requests'/(r['request_id']+'.json')).stat().st_size for r in requests],
    white_conditional_fp=by_id['c7797b6e-5b7e-410f-9714-ddcef07d2d91']['conditional_mean'],
    ekeler_unknown_preserved=by_id['d9545b80-2326-4d32-8982-f7208318a32d']['conditional_mean'],
    caveat='Old published packet exercised only as frozen diagnostic input; it is NOT authorized research for new counts. Replacement fractions diagnostic assumptions, not forecasts or recommendations.'),indent=2))
print((ROOT/'actual_world_consumer_diagnostic.json').read_text())
