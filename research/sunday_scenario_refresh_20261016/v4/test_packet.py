from pathlib import Path
from copy import deepcopy
import json
from backend.app.product_services.analyst_packets import validate,clock
from backend.app.product_services.scenario_allocation import build_ideas,AllocationControls
P=Path(__file__).resolve().parent
packet=json.loads((P/'packet.json').read_text());prior=json.loads((P.parent/'v2/refreshed_scenarios_saved_run.json').read_text());rows=prior['params']['strategy_runtime']['football_analyst']['input_snapshot']['players'];controls=AllocationControls.model_validate(prior['params']['strategy_runtime']['football_analyst']['scenario_allocation_plan']['controls'])
def test_authored_packet_scope_and_source_clocks():
 assert not validate(packet)
 assert len(packet['games'])==10 and len({a['game_id'] for a in packet['analyst_assessments']})==10
 assert all(clock(s['available_at'])<=clock(packet['decision_at']) for s in packet['sources'] if s['coverage']=='verified')
def test_declared_leading_side_survives_pool_order_permutation():
 first,_=build_ideas(packet,rows,controls);second,_=build_ideas(packet,list(reversed(rows)),controls)
 identity=lambda xs:{(x['source_scenario_id'],x['team'],x['script']) for x in xs}
 assert identity(first)==identity(second)
 for sid,team in [('lar_ari_response','LAR'),('buf_lv_competitive','BUF'),('ne_passing','NE'),('no_nyg_competitive','NO')]:
  assert {x['team'] for x in first if x['source_scenario_id']==sid}=={team}
def test_football_response_is_not_a_lock_or_baseline_mutation():
 assert packet['baseline_mutation'] is False and packet['user_preferences']==[]
 s=next(s for s in packet['scenario_assumptions']['scenarios'] if s['scenario_id']=='lar_ari_response')
 assert {a['team'] for a in s['assumptions']}=={'ARI','LAR'}
 assert all('probability' not in s and 'scenario_weight' not in s for s in packet['scenario_assumptions']['scenarios'])
