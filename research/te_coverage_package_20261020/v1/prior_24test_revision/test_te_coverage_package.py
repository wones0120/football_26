from copy import deepcopy
import pytest
from backend.app.product_services.te_coverage_package import build_te_coverage_package,POSITION_VERSION,TARGET_VERSION
A='00-0000007';B='00-0000010';P='00000000-0000-0000-0000-000000000001';G='2023_01_BUF_MIA'


def inputs():
    positions=[];events=[]
    for play,db,recipient,complete,epa in ((1,6,A,False,2.),(2,5,A,True,-1.),(3,5,'00-0000008',True,1.)):
        off={f'00-{i:07d}':'TE'if i in(7,10)else'WR'for i in range(1,12)}
        roles=['CB']*db+['LB']*(8-db)+['DE','DT','DT']
        defense={f'00-{i:07d}':v for i,v in zip(range(12,23),roles)}
        scope=lambda m:dict(status='aligned_native_position_list',native_player_ids=list(m),position_by_native_id=m,exact_eleven_native_proven=True,exact_eleven_positions_proven=True)
        positions.append(dict(game_id=G,play_id=str(play),possession_team='BUF',native_phase='REG',source_row_ordinal=play-1,participant_scopes=dict(offense=scope(off),defense=scope(defense)),measurements=dict(defense_man_zone_type='MAN_COVERAGE',defense_coverage_type='COVER_1')))
        events.append(dict(game_id=G,play_id=str(play),offense='BUF',defense='MIA',eligible_target_attempt=True,attributed_receiver_id=recipient,native_receiver_id=recipient,attribution_conflict=False,complete_pass=complete,target_play_EPA=epa))
    pos=dict(version=POSITION_VERSION,season=2023,pregame_serving_eligible=False,semantic_sha256='pos',rows=positions)
    tar=dict(version=TARGET_VERSION,season=2023,before_period=202607,pregame_serving_eligible=False,semantic_sha256='target',expected_games=[dict(game_id=G,sides=['BUF','MIA'],season=2023,week=1)],event_basis=events,game_rows=[dict(game_id=G,team='BUF',source_player_id=A,source_roles=['TE','explicit_native_target_actor'])])
    return pos,tar,{A:dict(status='unique_native_alias',player_master_id=P)}


def test_direct_coverage_and_package_both_consumed_with_exact_matched_denominators():
    r=build_te_coverage_package(*inputs());a=r['actor_game_rows'][0];cells=a['cells']['man']
    assert cells['DB_count_ge6']['target_rate']==1 and cells['DB_count_le5']['target_rate']==.5
    assert cells['DB_count_ge6']['provider_EPA_per_TE_target']==2 and cells['DB_count_le5']['provider_EPA_per_TE_target']==-1
    assert a['DB_ge6_minus_le5']['man']==dict(target_rate=.5,completion_rate=-1.,provider_EPA_per_TE_target=3.)
    assert a['DB_ge6_minus_le5']['zone']['target_rate']is None
    assert r['event_basis'][0]['reported_personnel_tuple']['DB']==6


def test_known_zero_targets_are_not_unknown_and_no_fake_completion_denominator():
    p,t,ids=inputs();t['game_rows'].append(dict(game_id=G,team='BUF',source_player_id=B,source_roles=['TE']));ids[B]=dict(status='unique_native_alias',player_master_id='00000000-0000-0000-0000-000000000002')
    r=build_te_coverage_package(p,t,ids);a=next(x for x in r['actor_game_rows']if x['native_GSIS']==B)
    assert a['cells']['man']['DB_count_ge6']['exact_TE_targets']==0 and a['cells']['man']['DB_count_ge6']['target_rate']==0
    assert a['cells']['man']['DB_count_ge6']['completion_rate']is None
    assert a['DB_ge6_minus_le5']['man']['target_rate']==0
    assert len(r['event_basis'])==3 # Two TE player-exposures are not extra physical plays.


def test_unknown_recipient_masks_only_relevant_known_condition_cell():
    p,t,ids=inputs();t['event_basis'][0]['attributed_receiver_id']=None;r=build_te_coverage_package(p,t,ids);cells=r['actor_game_rows'][0]['cells']['man']
    assert cells['DB_count_ge6']['exact_onfield_attempts']==1 and cells['DB_count_ge6']['target_rate']is None
    assert cells['DB_count_le5']['target_rate']==.5
    assert r['unassigned_TE_candidate_residual'][0]['unknown_other_TE_candidates']


def test_missing_participation_unknown_not_offfield_or_zero():
    p,t,ids=inputs();p['rows']=p['rows'][1:];a=build_te_coverage_package(p,t,ids)['actor_game_rows'][0]
    for cells in a['cells'].values():
        assert all(c['exact_onfield_attempts']is None for c in cells.values())


def test_source_native_TE_offfield_or_nonTE_excludes_but_unknown_role_does_not():
    for value in ('WR','UNKNOWN'):
        p,t,ids=inputs();p['rows'][0]['participant_scopes']['offense']['position_by_native_id'][A]=value
        a=build_te_coverage_package(p,t,ids)['actor_game_rows'][0]['cells']['man']['DB_count_ge6']
        if value=='WR':assert a['exact_onfield_attempts']==0
        else:assert a['exact_onfield_attempts']is None


def test_attribution_conflict_disables_own_list_certification_and_keeps_explicit_recipient():
    p,t,ids=inputs();t['event_basis'][0].update(attribution_conflict=True,attributed_receiver_id=None,native_receiver_id='00-0009999')
    r=build_te_coverage_package(p,t,ids);assert r['actor_game_rows'][0]['cells']['man']['DB_count_ge6']['exact_onfield_attempts']is None
    assert r['unassigned_TE_candidate_residual'][0]['reported_native_receiver']=='00-0009999'


def test_unknown_native_coverage_not_inferred_from_COVER1_or_package():
    p,t,ids=inputs();p['rows'][0]['measurements']['defense_man_zone_type']=None
    r=build_te_coverage_package(p,t,ids);a=r['actor_game_rows'][0]
    assert a['cells']['man']['DB_count_ge6']['exact_onfield_attempts']is None
    assert a['cells']['zone']['DB_count_ge6']['exact_onfield_attempts']is None


def test_explicit_reported_mixed_other_excluded_separate_from_missing_classification():
    p,t,ids=inputs();p['rows'][0]['measurements']['defense_man_zone_type']='MIXED'
    a=build_te_coverage_package(p,t,ids)['actor_game_rows'][0]
    assert a['reported_mixed_other_excluded']==1 and a['cells']['man']['DB_count_ge6']['exact_onfield_attempts']==0


def test_incomplete_or_unsupported_defensive_roles_do_not_become_knownpackage():
    for fault in ('eleven','unsupported'):
        p,t,ids=inputs();s=p['rows'][0]['participant_scopes']['defense']
        if fault=='eleven':s['exact_eleven_positions_proven']=False
        else:s['position_by_native_id'][next(iter(s['position_by_native_id']))]='WR'
        a=build_te_coverage_package(p,t,ids)['actor_game_rows'][0]
        assert a['cells']['man']['DB_count_ge6']['exact_onfield_attempts']is None
        assert a['cells']['man']['DB_count_le5']['exact_onfield_attempts']is None


def test_OLB_stays_LB_not_edge_DL_assignment():
    p,t,ids=inputs();s=p['rows'][0]['participant_scopes']['defense']['position_by_native_id'];k=next(k for k,v in s.items()if v=='LB');s[k]='OLB'
    r=build_te_coverage_package(p,t,ids);assert r['event_basis'][0]['reported_personnel_tuple']['LB']==2


def test_outcome_unknowns_mask_outcome_only_with_source_counts_preserved():
    p,t,ids=inputs();t['event_basis'][0].update(complete_pass=None,target_play_EPA=None)
    c=build_te_coverage_package(p,t,ids)['actor_game_rows'][0]['cells']['man']['DB_count_ge6']
    assert c['target_rate']==1 and c['exact_TE_targets']==1 and c['completion_rate']is None and c['provider_EPA_per_TE_target']is None


def test_unknown_eligibility_masks_knownsample_and_compatible_full_cell():
    p,t,ids=inputs();t['event_basis'][0]['eligible_target_attempt']=None
    c=build_te_coverage_package(p,t,ids)['actor_game_rows'][0]['cells']['man']['DB_count_ge6'];assert c['exact_onfield_attempts']is None


def test_source_side_phase_conflicts_and_missing_own_log_remain_unknown():
    for fault in ('side','phase','log'):
        p,t,ids=inputs()
        if fault=='side':p['rows'][0]['possession_team']='MIA'
        elif fault=='phase':p['rows'][0]['native_phase']='POST'
        else:t['event_basis']=[]
        a=build_te_coverage_package(p,t,ids)['actor_game_rows'][0]
        assert all(c['exact_onfield_attempts']is None for groups in a['cells'].values()for c in groups.values())


def test_inherited_identity_conflicts_keep_native_source_but_no_catalog_contrast():
    p,t,ids=inputs();ids[A].update(status='canonical_native_conflict',player_master_id=None)
    a=build_te_coverage_package(p,t,ids)['actor_game_rows'][0]
    assert a['player_master_id']is None and a['cells']['man']['DB_count_ge6']['target_rate']==1
    assert a['DB_ge6_minus_le5']['man']['target_rate']is None
    ids.pop(A)
    with pytest.raises(ValueError,match='identity'):build_te_coverage_package(p,t,ids)


def test_native_duplicate_and_parent_version_scope_rejected():
    p,t,ids=inputs();p['rows'].append(deepcopy(p['rows'][0]))
    with pytest.raises(ValueError,match='Unique'):build_te_coverage_package(p,t,ids)
    p,t,ids=inputs();p['season']=2024
    with pytest.raises(ValueError,match='Matched'):build_te_coverage_package(p,t,ids)


@pytest.mark.parametrize('side',['offense','defense'])
def test_forged_exact11_header_does_not_override_actual_list_cardinality(side):
    p,t,ids=inputs();s=p['rows'][0]['participant_scopes'][side];s['native_player_ids']=s['native_player_ids'][:10]
    a=build_te_coverage_package(p,t,ids)['actor_game_rows'][0]
    assert a['cells']['man']['DB_count_ge6']['exact_onfield_attempts']is None


@pytest.mark.parametrize('field,value',[('complete_pass',1),('eligible_target_attempt','true'),('target_play_EPA',True),('target_play_EPA',float('nan'))])
def test_native_flag_and_provider_EPA_types_not_coerced(field,value):
    p,t,ids=inputs();t['event_basis'][0][field]=value
    with pytest.raises(ValueError):build_te_coverage_package(p,t,ids)


def test_all_global_native_alias_edges_close_conflicts_from_nonTE_key():
    p,t,ids=inputs();other='00-0009998';second='00000000-0000-0000-0000-000000000002'
    ids[other]=dict(status='canonical_native_conflict',player_master_id=None,original_alias_evidence=[dict(player_master_id=P),dict(player_master_id=second)])
    ids[A]['original_alias_evidence']=[dict(player_master_id=P)]
    r=build_te_coverage_package(p,t,ids);a=r['actor_game_rows'][0]
    assert a['player_master_id']is None and a['DB_ge6_minus_le5']['man']['target_rate']is None
    assert {A,other}<=set(r['global_identity_scope']['conflicted_native_keys'])
    assert A in r['global_identity_scope']['novel_conflicts_requiring_UI_incident']


def test_global_identity_scope_cannot_be_narrowed_to_current_TE_candidates():
    p,t,ids=inputs();t['native_identity_universe']=[A,'00-0008888']
    with pytest.raises(ValueError,match='global identity'):build_te_coverage_package(p,t,ids)


def test_canonical_subject_ID_is_not_an_arbitrary_label():
    p,t,ids=inputs();ids[A]['player_master_id']='not-a-UUID'
    with pytest.raises(ValueError):build_te_coverage_package(p,t,ids)
