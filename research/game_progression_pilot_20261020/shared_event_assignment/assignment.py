"""Synthetic shared physical-event opportunity accounting; no sampling/model."""
from copy import deepcopy
from uuid import UUID

from backend.app.product_services.opportunity_events import CHANNELS

VERSION='shared_event_player_assignment_fixture_v1'
SLOTS=('passer','receiver','rusher')
# Official attempt/target scope; tries and no-play remain separately retained.
KINDS={
    'targeted_pass':(1,('passer','receiver'),('pass_attempts','targets'),()),
    'no_target_pass':(1,('passer',),('pass_attempts',),()),
    'pass_unknown_target':(1,('passer',),('pass_attempts',),('targets',)),
    'spike':(1,('passer',),('pass_attempts',),()),
    'sack':(1,('passer',),(),()),
    'designed_or_other_rush':(1,('rusher',),('rush_attempts',),()),
    'scramble':(1,('rusher',),('rush_attempts',),()),
    'kneel':(1,('rusher',),('rush_attempts',),()),
    'no_play':(0,(),(),()),
    'two_point_try':(0,(),(),()),
    'control':(0,(),(),()),
    'unknown':(None,SLOTS,(),CHANNELS),
}
CHANNEL_ROLE={'pass_attempts':'passer','targets':'receiver','rush_attempts':'rusher'}


def canonical(value):
    if not isinstance(value,str):raise ValueError('One explicit canonical UUID per actor slot required')
    return str(UUID(value))


def assign(events, roster, *, evidence_kind):
    """Assign fixture-authored actors once per shared event/channel.

    Declared conditional participation is a fixture assumption, not evidence of
    dressing. Missing identity, role or participation retains residual units.
    Unknown event eligibility is separate from a known unassigned unit.
    """
    if evidence_kind!='synthetic_fixture':raise ValueError('Synthetic fixture scope only')
    actors={};native_teams=set()
    for original in roster:
        actor=deepcopy(original);pid=canonical(actor['player_master_id'])
        if pid in actors or not actor.get('team'):raise ValueError('Unique scoped canonical actors required')
        if actor['participation'] not in {'conditional_participation','unknown','unavailable'}:
            raise ValueError('Explicit fixture participation condition required')
        if actor['roles'] is not None and (not isinstance(actor['roles'],list) or set(actor['roles'])-set(SLOTS)):
            raise ValueError('Explicit role capabilities or unknown required')
        actor['player_master_id']=pid;actors[pid]=actor;native_teams.add(actor['team'])
    seen=set();ledger=[];queue=[];teams={};game_ids=set()
    player_counts={pid:dict.fromkeys(CHANNELS,0) for pid in actors}
    for original in events:
        event=deepcopy(original)
        if not all(isinstance(event.get(k),str) and event[k] for k in ('game_id','event_id','team','kind')):
            raise ValueError('Explicit event identity/team/kind required')
        key=(event['game_id'],event['event_id'])
        game_ids.add(event['game_id'])
        if len(game_ids)>1:raise ValueError('One fixture game per assignment ledger required')
        if key in seen:raise ValueError('Duplicate shared physical event identity')
        seen.add(key)
        if event['kind'] not in KINDS or event['team'] not in native_teams:
            raise ValueError('Supported fixture kind and full-team scope required')
        if set(event['actors'])!=set(SLOTS):raise ValueError('Exact explicit actor slots required')
        physical,slots,channels,unknown=KINDS[event['kind']]
        for slot,pid in event['actors'].items():
            if pid is None:continue
            pid=canonical(pid);event['actors'][slot]=pid
            if slot not in slots:raise ValueError('Actor slot conflicts with event mechanism')
            if pid in actors and actors[pid]['team']!=event['team']:
                raise ValueError('Cross-team player assignment')
        team_key=(event['game_id'],event['team'])
        state=teams.setdefault(team_key,dict(known_physical_count=0,unknown_physical_events=0,
            channels={c:dict(known_eligible_count=0,assigned_count=0,residual_count=0,unknown_eligibility_events=0) for c in CHANNELS}))
        if physical is None:state['unknown_physical_events']+=1
        else:state['known_physical_count']+=physical
        for channel in unknown:state['channels'][channel]['unknown_eligibility_events']+=1
        credits=[]
        for channel in channels:
            slot=CHANNEL_ROLE[channel];requested=event['actors'][slot];actor=actors.get(requested)
            if actor is None:reason='CANONICAL_IDENTITY_UNRESOLVED_OR_OUTSIDE_ROSTER'
            elif actor['participation']!='conditional_participation':reason='PARTICIPATION_UNPROVEN_OR_UNAVAILABLE'
            elif actor['roles'] is None or slot not in actor['roles']:reason='ROLE_EVIDENCE_MISSING'
            else:reason=None
            credit=dict(channel=channel,actor_slot=slot,requested_player_master_id=requested,
                player_master_id=requested if reason is None else None,residual_reason=reason)
            credits.append(credit)
            count=state['channels'][channel];count['known_eligible_count']+=1
            if reason:
                count['residual_count']+=1
                queue.append(dict(game_id=key[0],event_id=key[1],team=event['team'],**credit))
            else:
                count['assigned_count']+=1;player_counts[requested][channel]+=1
        ledger.append(dict(game_id=key[0],event_id=key[1],team=event['team'],kind=event['kind'],
            input_event=event,official_physical_count=physical,credits=credits,
            unknown_eligibility_channels=list(unknown),
            excluded_official_count_scope=event['kind'] in {'no_play','two_point_try','control'},
            production=None,scoring=None))
    result_teams=[]
    for (game,team),state in sorted(teams.items()):
        for c,value in state['channels'].items():
            assert value['assigned_count']+value['residual_count']==value['known_eligible_count']
            value['exact_count']=None if value['unknown_eligibility_events'] else value['known_eligible_count']
        result_teams.append(dict(game_id=game,team=team,**state,
            exact_physical_count=None if state['unknown_physical_events'] else state['known_physical_count']))
    # Per-player tallies are explicitly assigned lower bounds when a team's
    # event eligibility is unresolved; absence of credit is not a proven zero.
    players=[]
    for pid,actor in sorted(actors.items()):
        affected=[t for t in result_teams if t['team']==actor['team']]
        players.append(dict(**actor,assigned_counts_lower_bound=player_counts[pid],
            channel_eligibility_unknown={c:any(t['channels'][c]['unknown_eligibility_events'] for t in affected) for c in CHANNELS}))
    return dict(version=VERSION,evidence_kind=evidence_kind,events=ledger,teams=result_teams,players=players,
        unresolved_assignments=queue,assignment_policy='Explicit fixture-authored actor; no probability draw, preference filter or redistribution',
        likelihood='UNKNOWN',forecast=False,activation=False,live_consumer_connected=False)
