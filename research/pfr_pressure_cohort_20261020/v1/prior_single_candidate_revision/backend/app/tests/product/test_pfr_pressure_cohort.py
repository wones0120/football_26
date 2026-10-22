from copy import deepcopy
import pytest
from backend.app.product_services.pfr_pressure_cohort import nonspike_dropback,build_pressure_dropbacks,reconcile_pressure_cohorts
from backend.app.product_services.contact_cohort_reconciliation import resolve_contact_identity
A='00-0000001';B='00-0000002';P='00000000-0000-0000-0000-000000000001';Q='00000000-0000-0000-0000-000000000002';G='2023_01_BUF_MIA'


def row(play=1,**changes):
    return dict(game_id=G,season=2023,week=1,season_type='REG',play_id=play,posteam='BUF',defteam='MIA',play_type='pass',play_type_nfl='PASS',pass_attempt=1,rush_attempt=0,sack=0,qb_scramble=0,qb_spike=0,qb_kneel=0,qb_dropback=1,two_point_attempt=0,fumble=0,passer_player_id=A,rusher_player_id=None)|changes


def proofs(system,keys):
    return resolve_contact_identity(set(keys),[dict(source_system=system,source_key=n,player_master_id=p,created_at='2020-01-01T00:00:00Z',player_master_created_at='2020-01-01T00:00:00Z')for n,p in keys.items()],source_system=system,cutoff='2026-10-20T00:00:00Z')[0]


def source(**changes):
    return dict(game_id=G,team='BUF',pfr_player_id='PfrA00',times_hurried=0,times_hit=1,times_sacked=0,times_pressured=1,times_pressured_pct=1)|changes


def build(rows=None,sources=None):
    c=build_pressure_dropbacks(rows or[row()],before_period=202607)
    return reconcile_pressure_cohorts(c,sources if sources is not None else[source()],proofs('nflreadpy',{A:P}),proofs('pfr',{'PfrA00':P}))


def test_exact_same_passer_HHS_partition_and_matched_nonspike_exposure():
    r=build();g=next(g for g in r['game_rows']if g['offense']=='BUF')
    assert g['pressure_rate']==1 and g['full_observed_cohort_proven']
    assert not r['pregame_serving_eligible']and r['forecast']is None


def test_missing_opposite_offense_not_zero():
    g=next(g for g in build()['game_rows']if g['offense']=='MIA')
    assert g['pressure_rate']is None and not g['full_observed_cohort_proven']


@pytest.mark.parametrize('change',[dict(no_play=None),dict(pass_attempt=1,rush_attempt=1),dict(qb_spike=None),dict(play_type_nfl='UNSPECIFIED'),dict(qb_scramble=1,rush_attempt=0)])
def test_unknown_or_contradictory_eligibility_not_certified(change):
    assert nonspike_dropback(row(**change))[0]is None


@pytest.mark.parametrize('change',[dict(no_play=1),dict(two_point_attempt=1),dict(play_type='no_play')])
def test_known_exclusion_precedes_positive_flags(change):
    assert nonspike_dropback(row(**change))[0]is False


def test_spike_excluded_sack_and_scramble_count_once_without_QB_position_filter():
    assert nonspike_dropback(row(qb_spike=1,play_type='qb_spike'))[0]is False
    sack=row(2,pass_attempt=0,sack=1,play_type_nfl='SACK')
    scramble=row(3,pass_attempt=0,rush_attempt=1,qb_scramble=1,play_type='run',play_type_nfl='RUSH',rusher_player_id=A)
    c=build_pressure_dropbacks([row(),sack,scramble],before_period=202607)
    g=next(g for g in c['game_rows']if g['offense']=='BUF')
    assert g['known_dropbacks']==3 and g['known_sacks']==1
    assert g['actors'][A]['dropbacks']==3
    assert nonspike_dropback(scramble|dict(passer_player_id=B))[0]is None


@pytest.mark.parametrize('change,reason',[(dict(times_pressured=None),'unknown_PFR_HHS_component'),(dict(times_hurried=1),'PFR_HHS_partition_conflict'),(dict(times_sacked=1,times_hit=0),'per_passer_sack_count_conflict'),(dict(times_hit=2,times_pressured=2),'pressure_outside_declared_dropback_bounds'),(dict(times_pressured_pct=.8),'published_fraction_vs_declared_exposure_semantic_gap')])
def test_source_semantic_or_component_gaps_mask_rate(change,reason):
    g=next(g for g in build(sources=[source(**change)])['game_rows']if g['offense']=='BUF')
    assert g['pressure_rate']is None and reason in g['unknown_or_incompatible_reasons']


def test_rounded_percentage_only_checks_compatibility_never_recovers_exposure():
    g=next(g for g in build([row(),row(2),row(3)],[source(times_pressured_pct=.333)])['game_rows']if g['offense']=='BUF')
    assert g['known_dropbacks']==3 and g['pressure_rate']==1/3
    assert g['matched_native_passers'][0]['rounded_fraction_compatible']
    c=build_pressure_dropbacks([row(passer_player_id=None)],before_period=202607)
    r=reconcile_pressure_cohorts(c,[source()],{},proofs('pfr',{'PfrA00':P}))
    assert next(g for g in r['game_rows']if g['offense']=='BUF')['pressure_rate']is None


def test_missing_or_extra_source_actor_and_duplicate_native_rows_not_silent():
    g=next(g for g in build(sources=[])['game_rows']if g['offense']=='BUF')
    assert 'missing_or_extra_native_passer'in g['unknown_or_incompatible_reasons']
    with pytest.raises(ValueError,match='cardinality'):
        build(sources=[source(),source()])
    with pytest.raises(ValueError,match='Duplicate'):
        build_pressure_dropbacks([row(),row()],before_period=202607)


def test_observed_no_dropbacks_zero_total_does_not_define_fraction():
    r=build([row(pass_attempt=0,rush_attempt=1,qb_dropback=0,play_type='run',play_type_nfl='RUSH')],[])
    g=next(g for g in r['game_rows']if g['offense']=='BUF')
    assert g['full_observed_cohort_proven']and g['known_dropbacks']==0 and g['pressure_rate']is None


def test_frozen_identity_candidate_edges_and_scope_are_authenticated():
    c=build_pressure_dropbacks([row()],before_period=202607)
    gp=proofs('nflreadpy',{A:P});pp=proofs('pfr',{'PfrA00':P})
    gp[A]['player_master_id']=Q
    with pytest.raises(ValueError,match='candidate-edge'):
        reconcile_pressure_cohorts(c,[source()],gp,pp)
    gp=proofs('nflreadpy',{A:P});gp[A]['source_system']='pfr'
    with pytest.raises(ValueError,match='scope'):
        reconcile_pressure_cohorts(c,[source()],gp,pp)


def test_native_pass_attempt_and_sack_positive_union_is_one_physical_exposure():
    # Actual nflfastR source flag includes sacks in pass_attempt.
    raw=row(sack=1,play_type_nfl='SACK')
    assert nonspike_dropback(raw)[0]is True
    c=build_pressure_dropbacks([raw],before_period=202607)
    g=next(g for g in c['game_rows']if g['offense']=='BUF')
    assert g['known_dropbacks']==g['known_sacks']==g['actors'][A]['dropbacks']==1
