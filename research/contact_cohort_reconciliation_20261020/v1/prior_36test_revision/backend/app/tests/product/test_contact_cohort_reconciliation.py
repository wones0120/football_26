import pytest
from backend.app.product_services.contact_cohort_reconciliation import official_rush_eligibility


def row(**changes):
    return dict(play_type='run',play_type_nfl='RUSH',rush_attempt=1,pass_attempt=0,sack=0,qb_scramble=0,qb_spike=0,qb_kneel=0,two_point_attempt=0,fumble=0)|changes


def test_official_cohort_includes_kneels_scrambles_and_signed_yards():
    assert official_rush_eligibility(row())is True
    assert official_rush_eligibility(row(play_type='qb_kneel',qb_kneel=1,rushing_yards=-1))is True
    assert official_rush_eligibility(row(qb_scramble=1))is True


@pytest.mark.parametrize('change',[dict(no_play=1),dict(play_type='no_play'),dict(two_point_attempt=1)])
def test_known_exclusions_precede_raw_positive_attempt(change):
    assert official_rush_eligibility(row(**change))is False


@pytest.mark.parametrize('change',[dict(no_play=None),dict(play_type_nfl='UNSPECIFIED'),dict(pass_attempt=1),dict(pass_attempt=None),dict(sack=1),dict(qb_scramble=1,rush_attempt=0)])
def test_unknown_live_and_conflicting_physical_flags_remain_unknown(change):
    assert official_rush_eligibility(row(**change))is None


def test_known_no_rush_excludes_even_with_unresolved_eligibility_but_not_conflicting_scramble():
    assert official_rush_eligibility(row(rush_attempt=0,no_play=None))is False

from copy import deepcopy
from datetime import datetime,UTC,timedelta
from backend.app.product_services.contact_cohort_reconciliation import build_official_rushing_cohort,resolve_contact_identity,reconcile_contact_cohorts
A='00-0000001';B='00-0000002';P='00000000-0000-0000-0000-000000000001';Q='00000000-0000-0000-0000-000000000002';G='2023_01_BUF_MIA';CUTOFF='2026-10-20T00:00:00+00:00'


def rush(play=1,**changes):
    return row(game_id=G,play_id=play,season=2023,week=1,season_type='REG',posteam='BUF',defteam='MIA',rusher_player_id=A,rushing_yards=4,lateral_rush=0,lateral_rusher_player_id=None,lateral_rushing_yards=0)|changes


def alias(system,native,pid=P,**changes):
    return dict(source_system=system,source_key=native,player_master_id=pid,created_at='2020-01-01T00:00:00+00:00',player_master_created_at='2020-01-01T00:00:00+00:00')|changes


def proofs(system,keys,aliases=None):
    a=aliases if aliases is not None else[alias(system,n)for n in keys]
    return resolve_contact_identity(set(keys),a,source_system=system,cutoff=CUTOFF)[0]


def contact(native='PfrA00',**changes):
    return dict(game_id=G,team='BUF',pfr_player_id=native,carries=1,before=1,after=3)|changes


def result(rows=None,pfr=None,gsis=None,pfrids=None):
    c=build_official_rushing_cohort(rows or[rush()],before_period=202607)
    r=reconcile_contact_cohorts(c,pfr if pfr is not None else[contact()],gsis if gsis is not None else proofs('nflreadpy',[A]),pfrids if pfrids is not None else proofs('pfr',['PfrA00']))
    return next(g for g in r['game_rows']if g['opposing_offense']=='BUF'),r


def test_exact_native_actor_carry_partition_and_total_percarry_are_distinct():
    g,r=result()
    assert g['full_observed_cohort_proven']is True
    assert g['metrics']['G15-M05']['value']==1 and g['metrics']['G15-M06']['value']==3
    assert g['matched_actor_links'][0]['native_GSIS']==A
    assert g['matched_actor_links'][0]['native_PFR']=='PfrA00'
    assert not r['pregame_serving_eligible']and r['forecast']is None


def test_same_aggregate_carries_wrong_individual_cohort_does_not_certify_total():
    g,_=result(pfrids=proofs('pfr',['PfrA00'],[alias('pfr','PfrA00',Q)]))
    assert g['PFR_known_carries']==g['known_official_carries']==1
    assert g['metrics']['G15-M05']['value']is None
    assert 'missing_or_extra_positive_actor'in g['unknown_or_incompatible_reasons']


def test_individual_carry_mismatch_can_hide_behind_matching_team_sum():
    rows=[rush(),rush(2),rush(3,rusher_player_id=B)]
    ga=proofs('nflreadpy',[A,B],[alias('nflreadpy',A),alias('nflreadpy',B,Q)])
    pa=proofs('pfr',['PfrA00','PfrB00'],[alias('pfr','PfrA00'),alias('pfr','PfrB00',Q)])
    g,_=result(rows,[contact(carries=1,before=2,after=6),contact('PfrB00',carries=2,before=1,after=3)],ga,pa)
    assert g['PFR_known_carries']==g['known_official_carries']==3
    assert g['metrics']['G15-M06']['value']is None and 'individual_carry_count_mismatch'in g['unknown_or_incompatible_reasons']


@pytest.mark.parametrize('changes',[dict(before=None),dict(after=None),dict(before=2,after=3),dict(carries=None),dict(carries=0),dict(carries=-1)])
def test_missing_components_counts_or_incompatible_yard_partition_masks_both_totals(changes):
    g,_=result(pfr=[contact(**changes)])
    assert all(m['value']is None for m in g['metrics'].values())


def test_signed_source_partition_preserved_including_kneeling():
    g,_=result([rush(play_type='qb_kneel',qb_kneel=1,rushing_yards=-2)],[contact(before=-2,after=0)])
    assert g['metrics']['G15-M05']['value']==-2
    assert g['metrics']['G15-M05']['per_official_carry']==-2


@pytest.mark.parametrize('changes',[dict(no_play=None),dict(rusher_player_id=None),dict(lateral_rush=None),dict(lateral_rush=1,lateral_rusher_player_id=B),dict(rushing_yards=None),dict(defteam=None)])
def test_unknown_eligibility_native_actor_lateral_yards_or_side_blocks_full_cohort(changes):
    g,_=result([rush(**changes)])
    assert g['full_observed_cohort_proven']is False
    assert g['metrics']['G15-M05']['value']is None


def test_global_alias_collision_withholds_every_implicated_key_across_periods():
    keys={A,B};p=proofs('nflreadpy',keys,[alias('nflreadpy',A),alias('nflreadpy',B)])
    assert all(p[n]['player_master_id']is None for n in keys)
    g,r=result(gsis=p)
    assert g['metrics']['G15-M06']['value']is None and r['identity_review_requests'][0]['reason']=='canonical_native_conflict'
    assert p[A]['original_alias_evidence']


def test_future_or_missing_canonical_creation_evidence_never_attaches():
    for changes in (dict(created_at='2027-01-01T00:00:00+00:00'),dict(player_master_created_at='2027-01-01T00:00:00+00:00'),dict(player_master_created_at=None)):
        p=proofs('nflreadpy',[A],[alias('nflreadpy',A,**changes)])
        assert p[A]['player_master_id']is None
        assert result(gsis=p)[0]['metrics']['G15-M05']['value']is None
    with pytest.raises(ValueError,match='nonfuture'):
        resolve_contact_identity({A},[],source_system='nflreadpy',cutoff=datetime.now(UTC)+timedelta(days=1))


def test_extra_positive_source_actor_and_missing_source_actor_are_not_dropped():
    pa=proofs('pfr',['PfrA00','PfrB00'],[alias('pfr','PfrA00'),alias('pfr','PfrB00',Q)])
    g,_=result(pfr=[contact(),contact('PfrB00')],pfrids=pa)
    assert g['native_PFR_actor_count']==2 and g['metrics']['G15-M05']['value']is None
    assert result(pfr=[])[0]['metrics']['G15-M05']['value']is None


def test_duplicate_native_source_or_unproven_global_identity_cannot_pick_arbitrary_row():
    with pytest.raises(ValueError,match='Duplicate native rush'):
        build_official_rushing_cohort([rush(),rush()],before_period=202607)
    with pytest.raises(ValueError,match='Duplicate native PFR'):
        result(pfr=[contact(),contact()])
    p=proofs('nflreadpy',[A]);p[B]=deepcopy(p[A]);p[B]['source_key']=B
    with pytest.raises(ValueError,match='Global native/canonical'):
        result(gsis=p)


def test_zero_exposure_total_zero_and_ratio_undefined_without_missing_source_zero_fill():
    g,_=result([rush(rush_attempt=0)],pfr=[])
    assert g['metrics']['G15-M05']['value']==0 and g['metrics']['G15-M05']['per_official_carry']is None
    g,_=result(pfr=[contact(before=None)])
    assert g['metrics']['G15-M05']['value']is None and g['metrics']['G15-M05']['unknown_source_components']==1


def test_identity_persistence_keeps_existing_resolved_case_id_status_and_clocks():
    from backend.app.product_services.contact_cohort_reconciliation import persist_contact_identity_requests
    _,r=result(gsis=proofs('nflreadpy',[A],[]))
    old=dict(identity_quarantine_id='existing',source_table='source_snapshot',source_record_key='nflreadpy-gsis:'+A,source_player_key=A,status='resolved',first_seen_at='old',updated_at='unchanged')
    class Result:
        def __init__(self,rows):self.rows=rows
        def mappings(self):return self.rows
    class Connection:
        def execute(self,sql,params):
            if str(sql).lstrip().startswith('SELECT'):return Result([deepcopy(old)])
            assert 'DO NOTHING'in str(sql)and'UPDATE'not in str(sql)
            return Result([])
    out=persist_contact_identity_requests(Connection(),r,source_refs=[])
    assert out['created_new']==0 and out['existing_unchanged']==1
    assert out['records'][0]['identity_quarantine_id']=='existing'and out['records'][0]['status']=='resolved'


def test_unresolved_zero_carry_source_actor_is_reviewed_without_inventing_volume():
    p=proofs('pfr',['PfrA00','PfrB00'],[alias('pfr','PfrA00')])
    g,r=result(pfr=[contact(),contact('PfrB00',carries=0,before=0,after=0)],pfrids=p)
    assert g['known_official_carries']==1 and g['metrics']['G15-M05']['value']==1
    assert any(q['source_key']=='PfrB00'for q in r['identity_review_requests'])


def test_new_native_queue_insert_is_idempotent_with_original_record_preserved():
    from backend.app.product_services.contact_cohort_reconciliation import persist_contact_identity_requests
    _,r=result(gsis=proofs('nflreadpy',[A],[]))
    class Result:
        def __init__(self,rows):self.rows=rows
        def mappings(self):return deepcopy(self.rows)
    class Connection:
        def __init__(self):self.rows={}
        def execute(self,sql,params):
            if str(sql).lstrip().startswith('SELECT'):return Result(list(self.rows.values()))
            assert 'DO NOTHING'in str(sql)and'UPDATE'not in str(sql)
            for p in params:
                self.rows.setdefault((p['table'],p['key']),dict(identity_quarantine_id=p['qid'],source_table=p['table'],source_record_key=p['key'],source_player_key=p['native'],status='open',first_seen_at='original',updated_at='original'))
            return Result([])
    c=Connection();first=persist_contact_identity_requests(c,r,source_refs=[]);saved=deepcopy(c.rows)
    second=persist_contact_identity_requests(c,r,source_refs=[])
    assert first['created_new']==1 and second['created_new']==0 and second['existing_unchanged']==1 and c.rows==saved


def test_selected_defense_metrics_retain_global_opponent_identity_cases():
    from research.contact_cohort_reconciliation_20261020.v1.selection import select_contact_scope
    _,r=result(gsis=proofs('nflreadpy',[A],[]))
    out=select_contact_scope(r,{'MIA'})
    assert len(out['game_rows'])==1 and out['game_rows'][0]['defense']=='MIA'
    assert out['identity_review_requests']==r['identity_review_requests']
    assert out['identity_review_requests'][0]['team']=='BUF'
    assert out['native_GSIS_identity_proofs']==r['native_GSIS_identity_proofs']
