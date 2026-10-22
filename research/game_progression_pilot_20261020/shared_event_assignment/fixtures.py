"""Explicit event mechanisms and actor assignments; no player probabilities."""
from copy import deepcopy

IDS={k:f'00000000-0000-0000-0000-{n:012d}' for n,k in enumerate(('qb','rb','wr','other'),1)}


def roster():
    return [dict(player_master_id=IDS[k],team='A' if k!='other' else 'B',roles=roles,
                 participation='conditional_participation') for k,roles in
        [('qb',['passer','rusher']),('rb',['rusher','receiver']),('wr',['receiver']),('other',['receiver'])]]


def event(number,kind,**slots):
    return dict(game_id='fixture-game',event_id=str(number),team='A',kind=kind,
        actors=dict(dict.fromkeys(('passer','receiver','rusher')),**slots))


def cases():
    mixed=[event(1,'targeted_pass',passer=IDS['qb'],receiver=IDS['wr']),
        event(2,'no_target_pass',passer=IDS['qb']),event(3,'spike',passer=IDS['qb']),
        event(4,'sack',passer=IDS['qb']),event(5,'designed_or_other_rush',rusher=IDS['rb']),
        event(6,'scramble',rusher=IDS['qb']),event(7,'kneel',rusher=IDS['qb']),
        event(8,'no_play'),event(9,'two_point_try'),event(10,'control')]
    out=[dict(case_id='mixed_known_mechanisms',events=mixed,roster=roster(),evidence_kind='synthetic_fixture')]
    out.append(dict(case_id='unresolved_receiver',events=[event(1,'targeted_pass',passer=IDS['qb'])],roster=roster(),evidence_kind='synthetic_fixture'))
    out.append(dict(case_id='unknown_target_eligibility',events=[event(1,'pass_unknown_target',passer=IDS['qb'])],roster=roster(),evidence_kind='synthetic_fixture'))
    out.append(dict(case_id='unknown_event_mechanism',events=[event(1,'unknown')],roster=roster(),evidence_kind='synthetic_fixture'))
    for name in ('unknown_role','unknown_participation','unavailable_actor','unmapped_uuid'):
        actors=roster();events=[event(1,'targeted_pass',passer=IDS['qb'],receiver=IDS['wr'])]
        if name=='unknown_role':actors[2]['roles']=None
        if name=='unknown_participation':actors[2]['participation']='unknown'
        if name=='unavailable_actor':actors[2]['participation']='unavailable'
        if name=='unmapped_uuid':events[0]['actors']['receiver']='00000000-0000-0000-0000-000000000099'
        out.append(dict(case_id=name,events=events,roster=actors,evidence_kind='synthetic_fixture'))
    return deepcopy(out)
