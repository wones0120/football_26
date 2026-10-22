from copy import deepcopy
from datetime import timedelta
import pytest
from backend.app.product_services.coverage_receiver_performance import build_native_coverage_performance,attach_and_window_performance
from backend.app.product_services.participation_source_components import normalize_participation_rows
from backend.app.product_services.schedule_context_features import VERSION as SCHEDULE_VERSION
from backend.app.tests.product.test_offensive_line_participation import source,snap,schedule,aliases,native,gid,NOW


def build(records=None,sources=None,weeks=(1,2,3)):
    records=records if records is not None else [snap(w,number=number,receiver_player_id=native(7),complete_pass=int(number==100),epa=2. if number==100 else -1.,qb_spike=0,qb_scramble=0)for w in weeks for number in(100,101)]
    sources=sources if sources is not None else [source(w,number=number,defense_man_zone_type='MAN_COVERAGE'if number==100 else'ZONE_COVERAGE')for w in weeks for number in(100,101)]
    p=normalize_participation_rows(sources,season=2023)
    return build_native_coverage_performance(p,records,dict(version=SCHEDULE_VERSION,game_rows=schedule(weeks),pregame_serving_eligible=False),before_period=202607,event_source_sha256='a'*64)


def actor(out,week=1,n=7):return next(r for r in out['game_rows']if r['game_id']==gid(week)and r['source_player_id']==native(n))
def attached(block,a=None):return attach_and_window_performance([block],aliases(range(1,12))if a is None else a,cutoff=NOW,identity_universe=set(block['native_identity_universe']))


def test_matched_direct_categories_completion_epa_and_strict_prior_window():
    b=build();r=actor(b)
    assert r['cells']['man']['completion_rate']==1 and r['cells']['zone']['completion_rate']==0
    assert r['man_minus_zone_target_EPA']==3 and r['man_minus_zone_completion_rate']==1
    out=attached(b);w=next(r for r in out['prior_windows']if r['game_id']==gid(3)and r['source_player_id']==native(7))
    assert w['max_contributing_period']==202302 and w['target_period']==202303
    assert w['cells']['man']['known_targets']==2 and w['man_minus_zone_target_EPA']==3
    assert b['pregame_serving_eligible']is False and out['forecast']is None


def test_unknown_recipient_masks_on_field_actor_but_verified_off_field_is_excluded():
    records=[snap(1,number=100,receiver_player_id=native(7),complete_pass=1,epa=2,qb_spike=0,qb_scramble=0),snap(1,number=101,receiver_player_id=None,complete_pass=0,epa=-1,qb_spike=0,qb_scramble=0)]
    sources=[source(1,number=100,defense_man_zone_type='MAN_COVERAGE'),source(1,number=101,replace=(6,22),defense_man_zone_type='MAN_COVERAGE')]
    b=build(records,sources,weeks=(1,));r=actor(b)
    assert r['cells']['man']['exact_targets']==1 and r['cells']['man']['completion_rate']==1
    assert r['unknown_recipient_events_excluded_by_verified_off_field']==1
    assert actor(b,n=8)['cells']['man']['unknown_target_membership']==1
    assert len(b['unassigned_residual'])==1 and native(1)in b['unassigned_residual'][0]['potential_native_players']


@pytest.mark.parametrize('mode',['missing','duplicate','side','phase','positions'])
def test_unverified_participation_cannot_exclude_unknown_recipient(mode):
    records=[snap(1,number=n,receiver_player_id=native(7)if n==100 else None,complete_pass=1,epa=1,qb_spike=0,qb_scramble=0)for n in(100,101)]
    sources=[source(1,number=n,defense_man_zone_type='MAN_COVERAGE')for n in(100,101)]
    if mode=='missing':sources=sources[:1]
    elif mode=='duplicate':sources[1]['offense_players'][-1]=native(1)
    elif mode=='side':sources[1]['possession_team']='MIA'
    elif mode=='phase':sources[1]['season_type']='POST'
    else:sources[1]['offense_positions']=None
    b=build(records,sources,weeks=(1,))
    assert actor(b)['cells']['man']['exact_targets']is None


def test_known_other_recipient_excludes_actor_without_position_shortcut():
    records=[snap(1,receiver_player_id=native(1),complete_pass=1,epa=-3,qb_spike=0,qb_scramble=0)]
    b=build(records,[source(1,defense_man_zone_type='MAN_COVERAGE')],weeks=(1,))
    assert actor(b,n=1)['cells']['man']['completion_rate']==1 # Center trick target retained.
    assert actor(b,n=7)['cells']['man']['exact_targets']==0
    assert actor(b,n=7)['cells']['man']['completion_rate']is None


def test_recipient_not_in_known_eleven_is_conflict_not_false_off_field_proof():
    b=build([snap(1,receiver_player_id=native(22),complete_pass=1,epa=2,qb_spike=0,qb_scramble=0)],[source(1,defense_man_zone_type='MAN_COVERAGE')],weeks=(1,))
    assert b['event_basis'][0]['attribution_conflict']is True
    assert actor(b,n=22)['cells']['man']['exact_targets']is None
    assert actor(b,n=7)['cells']['man']['exact_targets']is None


def test_unknown_category_and_outcome_do_not_become_zone_complement_or_zero():
    records=[snap(1,receiver_player_id=native(7),complete_pass=None,epa=float('nan'),qb_spike=0,qb_scramble=0)]
    b=build(records,[source(1,defense_man_zone_type='COVER_1')],weeks=(1,))
    assert all(c['exact_targets']is None for c in actor(b)['cells'].values())
    b=build(records,[source(1,defense_man_zone_type='MAN_COVERAGE')],weeks=(1,))
    assert actor(b)['cells']['man']['exact_targets']==1 and actor(b)['cells']['man']['completion_rate']is None
    assert actor(b)['cells']['man']['target_EPA_per_target']is None


def test_mixed_and_explicit_unclassified_not_forced_into_man_zone():
    for category in('MIXED','OTHER',None):
        b=build([snap(1,receiver_player_id=native(7),qb_spike=0,qb_scramble=0)],[source(1,defense_man_zone_type=category)],weeks=(1,))
        assert all(c['exact_targets']==0 for c in actor(b)['cells'].values())


@pytest.mark.parametrize('change',[dict(no_play=None),dict(rush_attempt=1),dict(qb_spike=None),dict(qb_scramble=None)])
def test_missing_conflicting_official_flags_mask_potential_target(change):
    b=build([snap(1,receiver_player_id=native(7),qb_spike=0,qb_scramble=0)|change],[source(1,defense_man_zone_type='MAN_COVERAGE')],weeks=(1,))
    assert actor(b)['cells']['man']['exact_targets']is None


def test_explicit_nullification_two_point_and_spike_exclude_before_missing_outcomes():
    for change in(dict(no_play=1),dict(two_point_attempt=1),dict(qb_spike=1,receiver_player_id=None)):
        b=build([snap(1,receiver_player_id=native(7),qb_spike=0,qb_scramble=0)|change],[source(1,defense_man_zone_type='MAN_COVERAGE')],weeks=(1,))
        assert actor(b)['cells']['man']['exact_targets']==0


def test_missing_scheduled_actor_game_masks_full_window_without_skipping():
    b=build(records=[snap(w,receiver_player_id=native(7),qb_spike=0,qb_scramble=0,epa=1,complete_pass=1)for w in(1,3)],sources=[source(w,defense_man_zone_type='MAN_COVERAGE')for w in(1,3)])
    out=attached(b);w=next(r for r in out['prior_windows']if r['game_id']==gid(3)and r['source_player_id']==native(7))
    assert w['contributing_game_ids']==[gid(1),gid(2)] and w['missing_actor_game_ids']==[gid(2)]
    assert w['cells']['man']['exact_targets']is None and w['known_observed_game_sample']['cells']['man']['exact_targets']==1
    assert b['missing_PBP_game_ids']==[gid(2)]


def test_cutoff_alias_collision_global_and_no_arbitrary_canonical_attachment():
    b=build();a=aliases(range(1,12));a[7]['player_master_id']=a[6]['player_master_id']
    out=attached(b,a);assert all(r['player_master_id']is None for r in out['game_rows']if r['source_player_id']in{native(7),native(8)})
    assert {r['source_player_id']for r in out['identity_review_requests']}=={native(7),native(8)}
    a=aliases(range(1,12));a[6]['created_at']=(NOW+timedelta(days=1)).isoformat();out=attached(b,a)
    assert len(out['future_alias_evidence_excluded'])==1
    assert all(r['player_master_id']is None for r in out['game_rows']if r['source_player_id']==native(7))


def test_duplicate_native_keys_source_guards_and_unknown_offense_membership():
    row=snap(1,receiver_player_id=native(7),qb_spike=0,qb_scramble=0)
    with pytest.raises(ValueError,match='Duplicate native PBP'):build([row,row],weeks=(1,))
    with pytest.raises(ValueError,match='GSIS'):build([row|dict(receiver_player_id='display name')],weeks=(1,))
    b=build([row,row|dict(play_id=101,posteam=None,defteam=None,receiver_player_id=None)],weeks=(1,))
    assert actor(b)['cells']['man']['exact_targets']is None


def test_identity_requests_append_only_and_never_reopen_or_repair_aliases():
    from backend.app.product_services.coverage_receiver_performance import persist_coverage_identity_requests
    calls=[]
    class Connection:
        def execute(self,sql,params):calls.append((str(sql),params))
    out=attached(build(),a=[]);result=persist_coverage_identity_requests(Connection(),[out],source_refs=[])
    assert result['requests']>0
    assert all('ON CONFLICT (source_schema,source_table,source_record_key) DO NOTHING'in sql and 'UPDATE 'not in sql for sql,p in calls)
    assert all(p['native'].startswith('00-')and p['table']=='source_snapshot'for sql,p in calls)


def test_missing_offense_retains_reported_actor_residual_without_inventing_two_team_cohorts():
    records=[snap(1,number=100,receiver_player_id=native(7),qb_spike=0,qb_scramble=0,complete_pass=1,epa=1),
             snap(1,number=101,posteam=None,defteam=None,receiver_player_id=native(22),qb_spike=0,qb_scramble=0,complete_pass=1,epa=1)]
    b=build(records,[source(1,number=n,defense_man_zone_type='MAN_COVERAGE')for n in(100,101)],weeks=(1,))
    assert not any(r['source_player_id']==native(22)for r in b['game_rows'])
    assert actor(b)['cells']['man']['exact_targets']is None
    residual=next(r for r in b['unassigned_residual']if r['play_id']=='101')
    assert residual['reported_native_receiver_id']==native(22) and residual['unknown_other_candidates']is True
    assert native(22)in b['native_identity_universe']


def test_conflicting_reported_recipient_and_eleven_preserve_nonexhaustive_residual():
    b=build([snap(1,receiver_player_id=native(22),complete_pass=1,epa=2,qb_spike=0,qb_scramble=0)],
            [source(1,defense_man_zone_type='MAN_COVERAGE')],weeks=(1,))
    residual=b['unassigned_residual'][0]
    assert residual['attribution_conflict']is True and residual['reported_native_receiver_id']==native(22)
    assert native(22)not in residual['raw_verified_offensive_players']
    assert residual['potential_native_players']is None and residual['unknown_other_candidates']is True
