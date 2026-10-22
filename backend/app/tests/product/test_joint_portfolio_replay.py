from copy import deepcopy
import json
from types import SimpleNamespace
from backend.app.product_services.analyst_shadow import digest
from backend.app.product_services import joint_portfolio_replay as service
from backend.app.tests.product.test_scenario_breadth import prepared
from backend.app.product_services.scenario_allocation import plan_slots,AllocationControls


def test_solver_limit_is_saved_as_inconclusive_without_500_or_fake_rosters(tmp_path,monkeypatch):
    snapshot,rows,ideas,worlds=prepared()
    config={'num_lineups':2,'strategy_runtime':{'football_analyst':{'input_snapshot':snapshot,'scenario_allocation_plan':plan_slots(ideas,2,AllocationControls()),'scenario_definitions':worlds}}}
    source={'source_optimizer_run_id':'00000000-0000-0000-0000-000000000001','input_identity':{'source_config_sha256':digest(config)},'artifact_sha256':'test', 'requested':2,'candidates':[],'comparisons':{},'generation':{'variants':0},'assumptions':[],'scope':snapshot['scope']}
    monkeypatch.setattr(service.parent,'read',lambda parent_id:deepcopy(source))
    monkeypatch.setattr(service.parent,'ROOT',tmp_path)
    monkeypatch.setattr(service,'ROOT',tmp_path/'joint')
    (tmp_path/('a'*64+'.states.json')).write_text(json.dumps({'states':[]}))
    monkeypatch.setattr(service,'select_pool',lambda *a,**k:([],{'solver_status':'unproven_joint_research_limit'}))
    class Session:
        def execute(self,*args,**kwargs):return self
        def mappings(self):return self
        def first(self):return {'constraint_config_json':config}
    result=service.build(Session(),'a'*64)
    assert result['status']=='underfilled' and result['comparisons']['joint_worst_regret']['achieved']==0
    assert result['comparisons']['joint_worst_regret']['worst_relative_best_roster_coverage']is None
    assert result['comparisons']['joint_worst_regret']['selection']['solver_status']=='unproven_joint_research_limit'
    assert service.read(result['replay_id'])['artifact_sha256']==result['artifact_sha256']
