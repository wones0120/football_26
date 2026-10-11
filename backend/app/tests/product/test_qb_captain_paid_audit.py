from copy import deepcopy
from scripts.audit_qb_captain_paid_rushing import paid_status, position_summary
from scripts.shadow_single_gpp_shortlist import captain_allowed


def test_paid_boundary_and_unknown_are_not_losses():
    assert paid_status(8,3,10)=='paid'
    assert paid_status(9,3,10)=='unknown'
    assert paid_status(11,2,10)=='unpaid'
    assert paid_status(1,1,None)=='unknown'
    assert paid_status(None,1,10)=='unknown'


def test_summary_uses_entire_field_and_excludes_unverified_contests():
    counts={'QB':dict(entries=10,paid=2,unpaid=7,unknown=1),
            'WR':dict(entries=20,paid=8,unpaid=12,unknown=0),
            'RB':dict(entries=5,paid=1,unpaid=4,unknown=0)}
    contests=[dict(paid_ready=True,position_counts=counts),dict(paid_ready=False,position_counts=counts)]
    result=position_summary(contests)
    assert result['QB']['entries']==10
    assert result['QB']['paid_rate_lower']==.2
    assert result['QB']['paid_rate_upper']==.3
    assert result['NON_QB']['entries']==25
    assert result['NON_QB']['paid']==9


def test_captain_restriction_preserves_qb_flex_without_mutation():
    roster=[dict(position='WR',roster_position='CPT'),dict(position='QB',roster_position='FLEX')]
    before=deepcopy(roster)
    assert captain_allowed(roster)
    assert roster==before
    assert not captain_allowed([dict(position='QB',roster_position='CPT')])


def test_wr_captain_requires_same_team_qb_flex():
    from scripts.shadow_single_gpp_shortlist import wr_rb_captain_allowed
    wr=dict(position='WR',roster_position='CPT',player_team='ATL')
    qb=dict(position='QB',roster_position='FLEX',player_team='ATL')
    assert wr_rb_captain_allowed([wr,qb])
    assert not wr_rb_captain_allowed([wr])
    assert not wr_rb_captain_allowed([wr,dict(qb,player_team='BAL')])
    assert not wr_rb_captain_allowed([dict(wr,player_team=None),dict(qb,player_team=None)])
    assert not wr_rb_captain_allowed([wr,dict(qb,roster_position='CPT')])


def test_rb_captain_needs_no_qb_and_other_positions_are_excluded():
    from scripts.shadow_single_gpp_shortlist import wr_rb_captain_allowed
    assert wr_rb_captain_allowed([dict(position='RB',roster_position='CPT')])
    for pos in ['QB','TE','K','DST']:
        assert not wr_rb_captain_allowed([dict(position=pos,roster_position='CPT')])
