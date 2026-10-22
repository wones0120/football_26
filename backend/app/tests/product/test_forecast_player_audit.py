from copy import deepcopy
import pytest
from backend.app.product_services.forecast_player_audit import audit_inputs,audit_primary


def fixture():
    a=dict(player_master_id='rb',name='Observed back',team='BUF',position='RB',counts=dict(pass_attempts=None,rush_attempts=4.,targets=2.))
    f=dict(rush_attempts_mean3=12.,rush_attempts_known3=3,event_official_rush_attempts_known3=2,event_official_rush_attempts_unknown3=1,
        targets_mean3=0.,targets_known3=3,event_targets_known3=0,event_targets_unknown3=3)
    m=dict(rows=[dict(player_master_id='rb',period=202607,history_periods=[202604,202605,202606],features=f)])
    p=[dict(player_master_id='rb',counts=dict(pass_attempts=0.,rush_attempts=4.,targets=2.),components=dict(tree=dict(rush_attempts=6.,targets=2.),neural=dict(rush_attempts=2.,targets=2.)))]
    budget=dict(pass_attempts=30.,rush_attempts=25.,targets=28.,reconciliation={c:dict(unallocated=v) for c,v in [('pass_attempts',30.),('rush_attempts',21.),('targets',26.)]})
    counts=dict(players=[a],teams=dict(BUF=budget))
    players=[dict(player_master_id='rb',conditional_mean=7.,new_model_evidence=dict(position='RB',source='complete_dk_score_head'))]
    return [a],m,p,counts,players


def test_review_flags_do_not_rewrite_counts_or_confuse_zero_with_missing_attribution():
    a,m,p,c,players=fixture();before=deepcopy((a,m,p,c,players))
    out=audit_primary(players,c,m,p,before_period=202607)
    assert (a,m,p,c,players)==before
    assert out['errors']==[]
    flags=out['players'][0]['findings']
    assert {f['code'] for f in flags}=={'workload_ratio_review','incomplete_event_window','family_disagreement'}
    assert all(f['channel']=='rush_attempts' for f in flags)
    assert out['team_accounting'][1]['applicable_unknown_actors']==0
    assert out['team_accounting'][0]['applicable_unknown_actors']==0  # RB passes are nonapplicable.


@pytest.mark.parametrize('change,code',[('future','future_or_wrong_period_features'),('mask','invalid_event_coverage_mask'),('negative','invalid_model_count'),('duplicate','duplicate_canonical_actor')])
def test_exact_input_invariants_detected(change,code):
    a,m,p,_,_=fixture()
    if change=='future':m['rows'][0]['history_periods'].append(202607)
    if change=='mask':m['rows'][0]['features']['event_targets_unknown3']=2
    if change=='negative':p[0]['counts']['rush_attempts']=-1.
    if change=='duplicate':a.append(deepcopy(a[0]))
    assert code in {e['code'] for e in audit_inputs(a,m,p,before_period=202607)['errors']}


def test_unknown_required_count_cannot_hide_behind_a_complete_score_and_residuals_must_balance():
    _,m,p,c,players=fixture();c['players'][0]['counts']['targets']=None
    out=audit_primary(players,c,m,p,before_period=202607)
    assert {'scored_unknown_required_count','team_count_accounting'}<={e['code'] for e in out['errors']}
    c['teams']['BUF']['reconciliation']['targets']['unallocated']=28.
    players[0]['conditional_mean']=None
    assert audit_primary(players,c,m,p,before_period=202607)['errors']==[]


def test_factual_unavailable_zero_does_not_claim_a_learned_score():
    _,m,p,c,players=fixture();c['players'][0]['world_activity']=False
    players[0].update(conditional_mean=0.,new_model_evidence=dict(position='RB',source='factual_unavailable_zero'))
    out=audit_primary(players,c,m,p,before_period=202607)
    assert out['errors']==[] and out['players'][0]['score_source']=='factual_unavailable_zero'


def test_frozen_audit_hash_survives_later_player_warning_and_count_annotations():
    from backend.app.product_services.evaluation_record import digest
    _,m,p,c,players=fixture();players[0]['missing_evidence']=[]
    out=audit_primary(players,c,m,p,before_period=202607)
    players[0]['missing_evidence'].append('Later display warning')
    c['players'][0]['counts']['rush_attempts']=99.
    assert out['players'][0]['missing_evidence']==[]
    assert out['players'][0]['served_counts']['rush_attempts']==4.
    assert out['sha256']==digest({k:v for k,v in out.items() if k!='sha256'})


def test_negative_dst_fantasy_estimate_is_not_an_impossible_physical_count():
    _,m,p,c,players=fixture()
    c['players'].append(dict(player_master_id='dst',team='BUF',position='DST',counts=dict.fromkeys(['pass_attempts','rush_attempts','targets'])))
    players.append(dict(player_master_id='dst',conditional_mean=-.5,new_model_evidence=dict(position='DST',source='explicit_selected_dst_expert')))
    out=audit_primary(players,c,m,p,before_period=202607)
    assert out['errors']==[]
    assert out['players'][-1]['served_score']==-.5
