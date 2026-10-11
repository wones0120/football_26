from copy import deepcopy
import pytest
from scripts.shadow_single_gpp_shortlist import projection_contract, reconstruct, compare
from backend.app.product_services.classic_strategy_contract import digest


def contract():
    c=dict(execution_mode='PRODUCTION',strategy_id='classic_large_gpp_v1',strategy_label='live',deviations=[],
        effective=dict(resolved_config=dict(objective_weights=dict(projection=.35,ceiling=.45,correlation=.15,leverage=.05),team_cap=2),
            pipeline_options=dict(num_lineups=5,max_exposure=.8),eligible_player_ids=['a','b']),sources={},metadata={})
    c['effective_sha256']=digest(c['effective']);c['sha256']=digest(c)
    return c


def test_classic_probe_changes_only_objective_and_research_metadata():
    c=contract();before=deepcopy(c);shadow=projection_contract(c)
    assert c==before
    expected=deepcopy(c['effective'])
    expected['resolved_config']['objective_weights']=dict(projection=1.,ceiling=0.,correlation=0.,leverage=0.)
    assert shadow['effective']==expected
    assert shadow['execution_mode']=='RESEARCH_SHADOW'
    assert digest({k:v for k,v in shadow.items() if k!='sha256'})==shadow['sha256']


def inputs():
    pool={};native={};players=[]
    for i in range(6):
        pid=str(i);slot='CPT' if i==0 else 'FLEX'
        pool[pid]=dict(player_id=pid,name=pid,player_team='A' if i<3 else 'B',position='QB' if i==0 else 'WR',
            projection=10,p90=20,game_id='A@B',dk_player_id=str(100+i),dk_captain_id=str(200+i))
        native[str(100+i)]={'Salary':'5000','Roster Position':'FLEX'}
        native[str(200+i)]={'Salary':'7500','Roster Position':'CPT'}
        players.append(dict(player_id=pid,slot=slot))
    candidate=dict(players=players,comparison_basis='common_baseline',baseline_mean=65,baseline_p90=130,salary=32500)
    return candidate,pool,native


def test_captain_applies_multiplier_once_from_frozen_base_evidence():
    c,p,n=inputs();before=deepcopy((c,p,n));rows=reconstruct(c,p,n,{})
    assert sum(r['projection'] for r in rows)==65
    assert rows[0]['salary']==7500 and rows[0]['dk_captain_id']=='200'
    assert (c,p,n)==before


@pytest.mark.parametrize('controls',[{'exclude_player_ids':['0']},{'locked_player_ids':['missing']},
    {'flex_only_player_ids':['0']},{'no_qb_captain':True},{'no_qbs':True},{'captain_positions':['WR']}])
def test_shadow_cannot_bypass_user_preferences(controls):
    with pytest.raises(ValueError): reconstruct(*inputs(),controls)


@pytest.mark.parametrize('change',[{'baseline_mean':66},{'comparison_basis':'favorable_scenario'},{'actual_points':200}])
def test_rejects_inconsistent_or_postgame_candidate(change):
    c,p,n=inputs();c.update(change)
    with pytest.raises(ValueError): reconstruct(c,p,n,{})


def test_missing_native_slot_and_questionable_exclusion_fail_closed():
    c,p,n=inputs();n['200']['Roster Position']='FLEX'
    with pytest.raises(ValueError): reconstruct(c,p,n,{})
    c,p,n=inputs();p['1']['injury_status']='Q'
    with pytest.raises(ValueError): reconstruct(c,p,n,{'exclude_questionable':True})


def test_expanded_comparison_is_deterministic_and_does_not_use_outcomes():
    c,p,n=inputs();rows=reconstruct(c,p,n,{})
    source=dict(optimizer_run_id='r',season=2026,week=5,slate_id='SUNDAY_NIGHT',contest_format='showdown',projection_run_id='p',data_cutoff_at='2026-10-10T10:00:00Z')
    report=compare([rows,deepcopy(rows)],source)
    assert len(report['candidates'])==1
    assert report['recommended']['projected_points']==65
    assert report['recommended']['paid_finish_probability'] is None
    rows[0]['actual_score']=20
    with pytest.raises(ValueError): compare([rows],source)


def test_classic_rejects_other_scope_before_running_solver():
    from scripts.shadow_single_gpp_shortlist import classic
    source={'constraint_config_json':{'effective_strategy_contract':{},'strategy_runtime':{
        'classic_run_input_snapshot':{'payload':{'metadata':{'season':2026,'week':6,'slate':'SUNDAY_MAIN'}}}}}}
    with pytest.raises(ValueError,match='limited to 2026 Week 5'):
        classic(source)
