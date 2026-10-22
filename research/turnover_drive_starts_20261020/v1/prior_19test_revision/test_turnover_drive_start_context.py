from copy import deepcopy
import pytest
from backend.app.product_services.turnover_drive_start_context import build_turnover_drive_start_context, _summary
from backend.app.product_services.fumble_event_components import build_fumble_event_components

G='2026_01_BUF_MIA'

def row(play=1,**changes):
    return dict(game_id=G,season=2026,week=1,season_type='REG',play_id=play,order_sequence=play,
        posteam='BUF',defteam='MIA',drive=1,game_half='Half1',play_type='pass',play_type_nfl='PASS',
        pass_attempt=1,rush_attempt=0,sack=0,qb_spike=0,qb_scramble=0,qb_kneel=0,qb_dropback=1,
        two_point_attempt=0,fumble=0,fumble_lost=0,interception=0,touchdown=0,return_touchdown=0,
        own_kickoff_recovery=0,return_team=None,drive_start_transition='INTERCEPTION',
        fumbled_1_team=None,fumbled_1_player_id=None,fumbled_2_team=None,fumbled_2_player_id=None,
        fumble_recovery_1_team=None,fumble_recovery_1_player_id=None,fumble_recovery_2_team=None,fumble_recovery_2_player_id=None)|changes

def incoming(play=2,**changes):
    return row(play,posteam='MIA',defteam='BUF',drive=2,**changes)

def build(rows,*,label='INTERCEPTION',team='MIA',start=30,first_link=True,extra=0):
    parent=dict(version='source_original_drive_field_context_v1',before_period=202606,source=dict(content_sha256='a'*64),
        game_rows=[dict(game_id=G,team=team,season=2026,week=1,unknown_original_drive_events=extra,
            drives=[dict(original_drive_id=2,first_play_link_verified=first_link,source_first_play_id=2,
                reported_start_yardline100=start,start_yardline100=start,first_observed_physical_snap_yardline100=35)])])
    for r in rows:
        if r['drive']==2:r['drive_start_transition']=label
    order=dict(version='validated_native_order_map_v1',before_period=202606,source_byte_sha256='a'*64,unknown_order_games=[],
        rows=[dict(game_id=G,play_id=str(r['play_id']),order_sequence=r['order_sequence'],native_order_verified=True)for r in rows])
    f=build_fumble_event_components(rows,before_period=202606,source=dict(content_sha256='a'*64))
    return build_turnover_drive_start_context(rows,parent,order,f)

def drive(out):return out['game_rows'][0]['drives'][0]

def test_interception_native_order_not_numeric_play_id_and_start_not_first_los():
    out=build([row(900,order_sequence=1,interception=1),incoming(2,order_sequence=2)])
    d=drive(out)
    assert d['classification']=='giveaway' and d['acquisition']['play_id']=='900'
    assert d['start_yardline100']==30 and d['first_physical_snap_yardline100']==35
    assert d['opponent_defense']=='BUF' and out['pregame_serving_eligible']is False

def test_first_snap_interception_does_not_become_its_own_origin():
    assert drive(build([row(),incoming(interception=1)]))['classification']is None

def test_intervening_ordinary_physical_snap_blocks_older_turnover():
    d=drive(build([row(interception=1),row(2),incoming(3)]))
    assert d['classification']is None and d['acquisition']['play_id']=='2'

def test_unknown_eligibility_or_null_reset_blocks_older_turnover():
    for change in ({'play_type_nfl':'UNSPECIFIED'}, {'no_play':None}, {'interception':None}):
        d=drive(build([row(interception=1),row(2,**change),incoming(3)]))
        assert d['classification']is None and d['acquisition']['play_id']=='2'

def test_quiet_timeout_can_skip_but_half_or_game_reset_cannot():
    quiet=row(2,play_type='time_out',play_type_nfl='TIMEOUT',pass_attempt=0,qb_dropback=0)
    assert drive(build([row(interception=1),quiet,incoming(3)]))['classification']=='giveaway'
    for native in ('END_HALF','END_GAME','GAME_START'):
        q=quiet|dict(play_type=None,play_type_nfl=native)
        assert drive(build([row(interception=1),q,incoming(3)]))['classification']is None

def test_return_touchdown_is_censored_not_zero_start():
    out=build([row(interception=1,return_touchdown=1,touchdown=1),incoming()])
    assert drive(out)['classification']is None

def test_fumbler_recoverer_teams_not_initial_offense_and_no_slot_zip():
    f=row(fumble=1,fumble_lost=1,fumbled_1_team='BUF',fumbled_1_player_id='00-0000001',
        fumble_recovery_1_team='MIA',fumble_recovery_1_player_id='00-0000002')
    d=drive(build([f,incoming()],label='FUMBLE'))
    assert d['classification']=='giveaway' and d['acquisition']['winner']=='MIA'
    # A return-team fumbler can lose to the initial offense; the same native proof applies.
    f.update(posteam='MIA',defteam='BUF')
    assert drive(build([f,incoming()],label='FUMBLE'))['classification']=='giveaway'
    for change in ({'fumbled_2_team':'MIA','fumbled_2_player_id':'00-0000003'},
                   {'fumble_recovery_1_team':None}, {'interception':1}):
        assert drive(build([f|change,incoming()],label='FUMBLE'))['classification']is None

@pytest.mark.parametrize('label,change',[
    ('PUNT',dict(play_type='punt',play_type_nfl='PUNT',pass_attempt=0,punt_attempt=1,punt_blocked=0)),
    ('DOWNS',dict(fourth_down_failed=1)),
    ('MISSED_FG',dict(play_type='field_goal',play_type_nfl='FIELD_GOAL',pass_attempt=0,field_goal_attempt=1,field_goal_result='missed')),
    ('BLOCKED_PUNT,_DOWNS',dict(play_type='punt',play_type_nfl='PUNT',pass_attempt=0,punt_attempt=1,punt_blocked=1,fourth_down_failed=1)),
])
def test_explicit_normal_subclasses_separate_downs_from_giveaways(label,change):
    d=drive(build([row(**change),incoming()],label=label))
    assert d['classification']=='non_giveaway' and d['acquisition']['kind']==label

def test_kickoff_return_team_not_defteam_and_own_recovery_unknown():
    k=row(play_type='kickoff',play_type_nfl='KICK_OFF',pass_attempt=0,kickoff_attempt=1,posteam='MIA',defteam='BUF',return_team='MIA')
    assert drive(build([k,incoming()],label='KICKOFF'))['classification']=='non_giveaway'
    for change in ({'own_kickoff_recovery':1},{'own_kickoff_recovery':None},{'return_team':None}):
        assert drive(build([k|change,incoming()],label='KICKOFF'))['classification']is None

def test_enum_side_and_first_link_conflicts_are_unknown():
    assert drive(build([row(interception=1),incoming()],label='PUNT'))['classification']is None
    assert drive(build([row(interception=1),incoming()],first_link=False))['classification']is None

def test_summary_masks_class_and_start_unknown_and_empty_conditions():
    def d(c,v):return dict(classification=c,start_yardline100=v,acquisition=dict(kind='PUNT'))
    s=_summary([d('giveaway',25),d('non_giveaway',75)])
    assert s['giveaway_minus_non_giveaway_start_yardline100']==-50
    for rows,extra in (([d('giveaway',25),d('non_giveaway',None)],0),([d('giveaway',25),d('non_giveaway',75),d(None,20)],0),([d('giveaway',25),d('non_giveaway',75)],1)):
        assert _summary(rows,extra)['giveaway_minus_non_giveaway_start_yardline100']is None
    assert _summary([])['giveaway_minus_non_giveaway_start_yardline100']is None

def test_unknown_first_snap_before_known_endpoint_and_missing_order_source_rejected():
    u=incoming(play=2,no_play=None);out=build([row(interception=1),u,incoming(3)])
    assert drive(out)['first_physical_boundary_unknown']is True
    with pytest.raises(ValueError,match='Duplicate'):
        build([row(),row(),incoming()])


def test_return_td_anchor_retained_as_censored_and_unknown_fumble_not_assigned():
    out=build([row(interception=1,touchdown=1,return_touchdown=1),incoming()])
    assert len(out['censored_giveaway_anchors'])==1
    assert out['censored_giveaway_anchors'][0]['typed_classification']=='giveaway'
    unknown=row(fumble=0,fumbled_1_team='BUF',fumbled_1_player_id='00-0000001')
    assert drive(build([unknown,incoming()],label='FUMBLE'))['classification']is None


def test_reader_rejects_future_read_or_order_publication_before_any_source_access():
    from datetime import datetime,UTC,timedelta
    from types import SimpleNamespace
    from backend.app.product_services.turnover_drive_start_context import derive_retrospective_drive_starts
    now=datetime.now(UTC);s=SimpleNamespace(slate_lock_at=now-timedelta(hours=1))
    with pytest.raises(ValueError,match='nonfuture'):
        derive_retrospective_drive_starts(s,{}, {}, {},order_published_at=now,actual_read_at=now+timedelta(days=1))
    with pytest.raises(ValueError,match='publication'):
        derive_retrospective_drive_starts(s,{}, {}, {},order_published_at=now+timedelta(days=1),actual_read_at=now)


@pytest.mark.parametrize('half',[None,'Half2'])
def test_unknown_or_changed_native_half_does_not_inherit_old_origin(half):
    out=build([row(interception=1),row(2,play_type='quarter_end',play_type_nfl='END_QUARTER',pass_attempt=0),incoming(3,game_half=half)])
    assert drive(out)['classification'] is None
    assert drive(out)['acquisition']['reason']=='unknown_or_changed_native_half_requires_new_possession_proof'
