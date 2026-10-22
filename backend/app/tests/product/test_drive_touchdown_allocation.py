from copy import deepcopy
import pytest
from backend.app.product_services.drive_touchdown_allocation import build_drive_touchdown_allocation,DRIVE_VERSION,TERMINAL_VERSION,OFFICIAL_VERSION,SCORING_VERSION

A='00-0000001';B='00-0000002';C='00-0000003';G='2026_01_BUF_MIA';P='00000000-0000-0000-0000-000000000001';Q='00000000-0000-0000-0000-000000000002'


def inputs():
    drives=[];ends=[];official=[];scores=[];links=[]
    for did,start,outcome in((1,80,'pass'),(2,10,'rush'),(3,80,'neither'),(4,10,'pass')):
        pid=str(did*10);drives.append(dict(original_drive_id=did,start_yardline100=start))
        ends.append(dict(original_drive_id=did,native_boundary_and_cohort_verified=True,verified_terminal_class='FIELD_GOAL'if outcome=='neither'else'TOUCHDOWN'))
        opportunities=[dict(channel='rush_attempts',source_player_id=A)]if outcome=='rush'else[dict(channel='pass_attempts',source_player_id=A),dict(channel='targets',source_player_id=B)]
        official.append(dict(game_id=G,play_id=pid,team='BUF',source_order=did*10,opportunities=opportunities,unknown_channels=[]))
        scores.append(dict(game_id=G,play_id=pid,team='BUF',rush_TD=outcome=='rush',passing_and_receiving_same_TD=outcome=='pass',rusher=A,receiver=B,original_receiver=B,original_rusher=A))
        links.append(dict(game_id=G,play_id=pid,team='BUF',original_drive_id=did))
    parent=lambda v,**kw:dict(version=v,before_period=202606,pregame_serving_eligible=False,**kw)
    original=parent(DRIVE_VERSION,game_rows=[dict(game_id=G,team='BUF',drives=drives,unknown_original_drive_events=0)])
    terminal=parent(TERMINAL_VERSION,game_rows=[dict(native_game_id=G,team='BUF',drives=ends)])
    official=parent(OFFICIAL_VERSION,official_channel_event_basis=official)
    scoring=parent(SCORING_VERSION,event_basis=scores)
    identities=[dict(native_GSIS=n,player_master_id=p,canonical_candidate_ids=[p],identity_proven=True,source_position=role)for n,p,role in((A,P,'QB'),(B,Q,'WR'))]
    return original,terminal,official,scoring,links,identities


def actor(result,native=A):return next(r for r in result['actor_profiles']if r['native_GSIS']==native)


def test_matched_actor_drive_and_fieldposition_joint_allocation():
    r=build_drive_touchdown_allocation(*inputs());p=actor(r)
    own=p['cells']['own_half']['exact'];zone=p['cells']['inside20']['exact']
    assert own['drives']==2 and zone['drives']==2
    assert own['physical_pass_vs_rush']['mean_a']==.5 and own['physical_pass_vs_rush']['mean_b']==0
    assert zone['physical_pass_vs_rush']['covariance']==-.25
    assert zone['physical_pass_vs_rush']['cooccurrence']==0 and zone['physical_pass_vs_rush']['marginal_product']==.25
    c=p['across_starting_field_bin_comparisons']['inside20_minus_own_half']
    assert c['actor_pass_vs_rush']['rush_rate']==.5 and c['physical_pass_vs_rush']['covariance']==-.25
    assert len(r['drive_rows'])==4 and len(p['actor_drive_rows'])==4


def test_actor_cohort_independent_of_TD_outcome_not_an_onfield_census():
    r=build_drive_touchdown_allocation(*inputs());p=actor(r,B)
    assert len(p['actor_drive_rows'])==3 # No opportunity for B on rush drive: do not fabricate zero.
    assert any(x['outcome']=='neither'for x in p['actor_drive_rows'])
    assert p['cells']['own_half']['exact']['receiving_TD_credits']==1


def test_shared_pass_credits_onephysicalTD_with_role_partitions():
    r=build_drive_touchdown_allocation(*inputs());d=r['drive_rows'][0]
    assert len(d['known_physical_TD_events'])==1 and d['outcome']=='pass'
    assert d['role_typed_credit_partitions']['passing_TD_credit']['observed_used_actor_credit_units']==1
    assert d['role_typed_credit_partitions']['receiving_TD_credit']['observed_used_actor_credit_units']==1
    assert d['role_typed_credit_partitions']['rushing_TD_credit']['physical_event_credit_units']==0


def test_lateral_actual_scorer_outside_used_cohort_stays_native_rest():
    o,t,u,s,l,ids=inputs();s['event_basis'][0]['receiver']=C
    r=build_drive_touchdown_allocation(o,t,u,s,l,ids);d=r['drive_rows'][0]
    assert d['rest_scorer_native_ids']==[C]and d['known_physical_TD_events'][0]['original_receiver']==B
    assert d['role_typed_credit_partitions']['receiving_TD_credit']['native_rest_credit_units']==1
    assert actor(r,B)['cells']['own_half']['exact']['receiving_TD_credits']==0
    assert not any(p['native_GSIS']==C for p in r['actor_profiles'])


def test_nonQB_trick_passer_kept_not_role_inferred():
    o,t,u,s,l,ids=inputs();ids[0]['source_position']='WR'
    r=build_drive_touchdown_allocation(o,t,u,s,l,ids)
    assert actor(r)['identity']['source_positions']==['WR']
    assert actor(r)['cells']['own_half']['exact']['actor_pass_vs_rush']['mean_a']==.5


@pytest.mark.parametrize('fault',['missing_terminal','censored','missing_boundary','TD_transition_without_TD'])
def test_neither_needs_certified_terminal_not_no_observed_TD(fault):
    o,t,u,s,l,ids=inputs()
    if fault=='missing_terminal':t['game_rows'][0]['drives']=[d for d in t['game_rows'][0]['drives']if d['original_drive_id']!=3]
    elif fault=='censored':t['game_rows'][0]['drives'][2]['verified_terminal_class']=None
    elif fault=='missing_boundary':t['game_rows'][0]['drives'][2]['native_boundary_and_cohort_verified']=False
    else:t['game_rows'][0]['drives'][2]['verified_terminal_class']='TOUCHDOWN'
    r=build_drive_touchdown_allocation(o,t,u,s,l,ids)
    assert r['drive_rows'][2]['outcome']is None
    assert actor(r)['cells']['own_half']['exact']is None
    assert actor(r)['cells']['own_half']['known_complete_sample']['drives']==1


def test_unknown_TD_scorer_preserves_physical_type_but_masks_actor_credit_sample():
    o,t,u,s,l,ids=inputs();s['event_basis'][0]['receiver']=None
    r=build_drive_touchdown_allocation(o,t,u,s,l,ids);d=r['drive_rows'][0]
    assert d['outcome']=='pass'and not d['credit_known']
    assert d['role_typed_credit_partitions']['receiving_TD_credit']['unknown_actor_credit_units']==1
    assert actor(r)['cells']['own_half']['exact']is None


def test_unknown_actor_opportunity_masks_possible_used_cohort_not_known_others():
    o,t,u,s,l,ids=inputs();u['official_channel_event_basis'][1]['opportunities'][0]['source_player_id']=None
    r=build_drive_touchdown_allocation(o,t,u,s,l,ids)
    assert r['drive_rows'][1]['unknown_actor_membership']
    assert r['unknown_actor_residual'][0]['unknown_other_actors']
    assert actor(r,B)['cells']['inside20']['exact']is None


def test_unknown_start_masks_compatible_cells_without_assigning_known_sample():
    o,t,u,s,l,ids=inputs();o['game_rows'][0]['drives'][0]['start_yardline100']=None
    r=build_drive_touchdown_allocation(o,t,u,s,l,ids);p=actor(r)
    assert p['cells']['inside20']['exact']is None and p['cells']['own_half']['exact']is None
    assert p['cells']['inside20']['known_complete_sample']['drives']==2
    assert p['cells']['own_half']['known_complete_sample']['drives']==1


def test_missing_original_drive_link_masks_game_possible_cohort():
    o,t,u,s,l,ids=inputs();l.pop(0)
    r=build_drive_touchdown_allocation(o,t,u,s,l,ids)
    assert len(r['unbound_official_source_events'])==1 and len(r['unbound_physical_TD_events'])==1
    assert all(d['outcome']is None for d in r['drive_rows'])


def test_known_nonoffensive_zerochannel_control_missing_link_is_not_possible_usage():
    o,t,u,s,l,ids=inputs();u['official_channel_event_basis'].append(dict(game_id=G,play_id='1',team='BUF',source_order=1,opportunities=[],unknown_channels=[]))
    r=build_drive_touchdown_allocation(o,t,u,s,l,ids)
    assert not r['unbound_official_source_events']and actor(r)['cells']['own_half']['exact']is not None


def test_all_global_alias_edges_withhold_other_period_or_nonselected_actor():
    o,t,u,s,l,ids=inputs();ids.append(dict(native_GSIS=C,player_master_id=None,canonical_candidate_ids=[P,Q],identity_proven=False))
    r=build_drive_touchdown_allocation(o,t,u,s,l,ids)
    assert actor(r)['identity']['player_master_id']is None
    assert actor(r)['cells']['own_half']['exact']is not None
    assert actor(r)['across_starting_field_bin_comparisons']['inside20_minus_own_half']['actor_pass_vs_rush']is None


def test_inherited_identity_withholding_never_reattaches_and_no_name_join():
    o,t,u,s,l,ids=inputs();ids[0]['identity_proven']=False
    r=build_drive_touchdown_allocation(o,t,u,s,l,ids)
    assert not actor(r)['identity']['canonical_qualified']
    assert actor(r)['identity']['inherited_withheld']


@pytest.mark.parametrize('fault',['pass_rush_overlap','duplicate_links','duplicate_official','duplicate_scoring','scope','invalid_start'])
def test_source_conflicts_and_scope_rejected(fault):
    o,t,u,s,l,ids=inputs()
    if fault=='pass_rush_overlap':s['event_basis'][0]['rush_TD']=True
    elif fault=='duplicate_links':l.append(deepcopy(l[0]))
    elif fault=='duplicate_official':u['official_channel_event_basis'].append(deepcopy(u['official_channel_event_basis'][0]))
    elif fault=='duplicate_scoring':s['event_basis'].append(deepcopy(s['event_basis'][0]))
    elif fault=='scope':t['before_period']=202605
    else:o['game_rows'][0]['drives'][0]['start_yardline100']=101
    with pytest.raises(ValueError):build_drive_touchdown_allocation(o,t,u,s,l,ids)


def test_same_actor_linked_pass_and_receiving_credit_not_two_physical_TDs():
    o,t,u,s,l,ids=inputs();s['event_basis'][0]['receiver']=A
    r=build_drive_touchdown_allocation(o,t,u,s,l,ids);log=actor(r)['actor_drive_rows'][0]
    assert log['actor_passing_TD']==1 and log['actor_receiving_TD']==1
    assert log['actor_linked_pass_TD']==1 and log['team_pass_TD']==1
    assert len(r['drive_rows'][0]['known_physical_TD_events'])==1


def test_receiver_linked_pass_response_conditioned_on_native_actor_and_field_bin():
    r=build_drive_touchdown_allocation(*inputs());p=actor(r,B)
    assert p['cells']['inside20']['exact']['actor_receiving_vs_rush']['mean_a']==1
    assert p['cells']['own_half']['exact']['actor_receiving_vs_rush']['mean_a']==.5
    assert p['across_starting_field_bin_comparisons']['inside20_minus_own_half']['actor_linked_pass_vs_rush']['pass_rate']==.5


def test_duplicate_original_neither_drive_never_doubles_zero_outcomes():
    o,t,u,s,l,ids=inputs();o['game_rows'][0]['drives'].append(deepcopy(o['game_rows'][0]['drives'][2]))
    with pytest.raises(ValueError,match='Unique original'):build_drive_touchdown_allocation(o,t,u,s,l,ids)


def link_inputs():
    raw=dict(game_id=G,play_id='10.0',season='2026.0',week='1.0',season_type='REG',posteam='BUF',drive='1.0',order_sequence='12.0')
    order=dict(version='validated_native_order_map_v1',before_period=202606,rows=[dict(game_id=G,play_id=10,order_sequence=12.)])
    return raw,order


def test_csv_numeric_projection_matches_exact_native_order_and_original_not_fixed_drive():
    from backend.app.product_services.drive_touchdown_allocation import project_original_drive_links
    raw,order=link_inputs();raw['fixed_drive']='99'
    assert project_original_drive_links([raw],order,before_period=202606)==[dict(game_id=G,play_id='10',team='BUF',original_drive_id=1,source_order=12.)]
    raw['drive']='';assert project_original_drive_links([raw],order,before_period=202606)[0]['original_drive_id']is None


@pytest.mark.parametrize('fault',['order','missingkey','duplicate','side','fraction'])
def test_source_projection_cannot_forge_native_order_keys_or_scope(fault):
    from backend.app.product_services.drive_touchdown_allocation import project_original_drive_links
    raw,order=link_inputs();rows=[raw]
    if fault=='order':raw['order_sequence']='10'
    elif fault=='missingkey':rows=[]
    elif fault=='duplicate':rows.append(deepcopy(raw))
    elif fault=='side':raw['posteam']='NYJ'
    else:raw['play_id']='10.5'
    with pytest.raises(ValueError):project_original_drive_links(rows,order,before_period=202606)


def extra_nonopportunity_group_inputs():
    o,t,u,s,l,ids=inputs();e=deepcopy(u['official_channel_event_basis'][0]);e.update(play_id='999',opportunities=[],unknown_channels=[]);u['official_channel_event_basis'].append(e)
    e=deepcopy(s['event_basis'][0]);e.update(play_id='999',rush_TD=False,passing_and_receiving_same_TD=False);s['event_basis'].append(e)
    l.append(dict(game_id=G,play_id='999',team='BUF',original_drive_id=99))
    return o,t,u,s,l,ids


def test_known_zero_opportunity_and_TD_group_excluded_with_explicit_native_receipt():
    r=build_drive_touchdown_allocation(*extra_nonopportunity_group_inputs())
    excluded=r['excluded_known_nonopportunity_nonTD_original_groups']
    assert len(excluded)==1 and excluded[0]['source_play_ids']==['999']and excluded[0]['original_drive_id']==99
    assert len(r['drive_rows'])==4 and actor(r)['cells']['own_half']['exact']['drives']==2


@pytest.mark.parametrize('fault',['unknown_usage','unknown_TD','positive_TD'])
def test_uncertain_or_positive_absent_original_group_cannot_be_excluded(fault):
    o,t,u,s,l,ids=extra_nonopportunity_group_inputs()
    if fault=='unknown_usage':u['official_channel_event_basis'][-1]['unknown_channels']=['pass_attempts']
    else:s['event_basis'][-1]['rush_TD']=None if fault=='unknown_TD'else True
    with pytest.raises(ValueError,match='Possible opportunity'):build_drive_touchdown_allocation(o,t,u,s,l,ids)
