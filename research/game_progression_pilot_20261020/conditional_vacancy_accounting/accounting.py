"""Retrospective vacancy sensitivities through the existing conserved allocator."""
from copy import deepcopy
from collections import defaultdict
from uuid import UUID

from backend.app.product_services.opportunity_role_allocation import allocate_factual_vacancies
from backend.app.product_services.player_roles import UNAVAILABLE, PRACTICE
from research.game_progression_pilot_20261020.player_opportunity_accounting.allocation import CHANNELS, clock, number

VERSION='retained_reference_conditional_vacancy_accounting_v1'


def prepare_reference(workload, roles):
    """Keep source reference means, not replacement or next-game estimates."""
    before=workload['before_period'];cutoff=workload['cutoff']
    if (before!=roles['season']*100+roles['week'] or
            clock(cutoff)!=clock(roles['original_source_cutoff'])):
        raise ValueError('Reference/role decision scope differs')
    actors={r['player_master_id']:r for r in roles['actors']}
    histories={r['player_master_id']:r for r in workload['players']}
    if len(actors)!=len(roles['actors']) or len(histories)!=len(workload['players']) or set(actors)!=set(histories):
        raise ValueError('Unique identical full canonical actor universe required')
    periods=workload['periods']
    if not periods or len(set(periods))!=len(periods) or any(p>=before for p in periods):
        raise ValueError('Distinct prior reference periods required')
    teams={};players=[];facts=[]
    for team in sorted({a['team'] for a in actors.values()}):
        groups=[g for g in workload['team_reconciliation'] if g['team']==team]
        if sorted(g['period'] for g in groups)!=sorted(periods):raise ValueError('Complete common team window required')
        teams[team]={}
        for channel in CHANNELS:
            values=[g['channels'][channel] for g in groups]
            if any(v['status']!='RECONCILED_FULL_SOURCE_AND_OFFICIAL' or number(v['official_denominator']) is None for v in values):
                raise ValueError('Supported full-team denominators required')
            teams[team][channel]=sum(float(v['official_denominator']) for v in values)/len(periods)
    for pid,actor in sorted(actors.items()):
        UUID(pid);history=histories[pid]
        if (history['team'],history['source_player_id'])!=(actor['team'],actor['source_player_id']):
            raise ValueError('Native identity or team differs between retained inputs')
        counts={}
        for channel in CHANNELS:
            entry=history['channels'][channel];value=entry['observed_mean']
            if value is not None and entry['status']!='SUPPORTED_OBSERVED_REFERENCE':
                raise ValueError('Unsupported observed mean cannot seed a vacancy')
            counts[channel]=None if number(value) is None else float(value)
        player=dict(player_master_id=pid,team=actor['team'],position=actor['position'],counts=counts,
            world_activity=None,reference_meaning='Two-prior-game observed reference; hypothetical active-role proxy only',
            source_availability=actor['participation'])
        # Fresh source depth order supplies a conditional recipient role, never
        # proof of dressing, playing time or a replacement share.
        rank=actor['depth_rank'];depth=actor['depth_facts']
        if actor['depth_status']=='REPORTED' and rank is not None and depth:
            proof=deepcopy(depth[0])
            if (proof['player_id']!=pid or proof['team']!=actor['team'] or proof['depth_position']!=rank
                    or proof['season']*100+proof['week']!=before
                    or not clock(proof['observed_at'])<=clock(proof['received_at'])<=clock(cutoff)
                    or (clock(cutoff)-clock(proof['observed_at'])).total_seconds()>86400):
                raise ValueError('Current source depth evidence mismatch or stale')
            proof.update(role='expected_starter' if rank==1 else 'expected_backup',
                role_basis='Derived source depth order; participation and workload remain unknown')
            player['current_role_evidence']=proof
        resolution=actor['designation_resolution'];chosen=resolution.get('chosen_fact')
        if resolution['status']=='resolved' and resolution['effective_designation']=='OUT':
            if not chosen or chosen.get('status')!='OUT':raise ValueError('OUT designation lacks matched original fact')
            facts.append(dict(player_master_id=pid,team=actor['team'],designation='OUT',
                evidence=dict(deepcopy(chosen),designation='OUT',fact_type='game_status')))
        players.append(player)
    reference=dict(before_period=before,teams=teams,players=players)
    return reference,facts


def account(workload, roles, assumptions=()):
    """Apply named authored sensitivities; missing evidence produces abstention."""
    reference,facts=prepare_reference(workload,roles)
    actors={a['player_master_id']:a for a in roles['actors']}
    donors={f['player_master_id'] for f in facts}
    accepted=[];abstentions=[];seen=set();fractions=defaultdict(lambda:0)
    for original in assumptions:
        a=deepcopy(original);donor=a['donor_player_master_id'];recipient=a['recipient_player_master_id'];channel=a['channel']
        if not a.get('assumption_id') or a['assumption_id'] in seen or not a.get('rationale'):
            raise ValueError('Unique explicit assumption ID/rationale required')
        seen.add(a['assumption_id'])
        fraction=number(a.get('fraction'))
        if fraction is None or fraction>1 or channel not in CHANNELS or donor==recipient:
            raise ValueError('Valid distinct actors/channel/fraction required')
        if donor not in actors or recipient not in actors or actors[donor]['team']!=actors[recipient]['team']:
            raise ValueError('Canonical same-team donor and recipient required')
        fractions[donor,channel]+=fraction
        if fractions[donor,channel]>1:raise ValueError('Authored vacancy fractions exceed one')
        target=actors[recipient]
        statuses={f.get('status') for f in target['roster_facts']}
        if donor not in donors:reason='NO_MATCHED_FACTUAL_OUT_DONOR'
        elif recipient in donors or statuses & (UNAVAILABLE|PRACTICE|{'CUT'}):reason='RECIPIENT_REPORTED_UNAVAILABLE_OR_REQUIRES_ELEVATION'
        elif not any(p['player_master_id']==recipient and p.get('current_role_evidence') for p in reference['players']):reason='MISSING_CURRENT_RECIPIENT_ROLE_EVIDENCE'
        else:reason=None
        if reason:abstentions.append(dict(**a,status='ABSTAIN',reason=reason,transferred=None))
        else:accepted.append(a)
    result=allocate_factual_vacancies(reference,unavailable=facts,allocations=accepted,cutoff=workload['cutoff'])
    # The existing allocator retains unknown donor proxies separately even
    # when factual OUT sets conditional world participation/counts to zero.
    return dict(version=VERSION,evidence_use='RETROSPECTIVE_CONDITIONAL_SENSITIVITY_NOT_FORECAST',
        reference=reference,conditional_world=result,abstentions=abstentions,
        scope=dict(before_period=workload['before_period'],cutoff=workload['cutoff'],periods=workload['periods']),
        unknown_identity_chronology_retained=True,likelihood='UNKNOWN',
        condition='Recipient participation and authored fraction; neither is a measured replacement probability',
        forecast=False,activation=False,production_or_scoring=None,live_consumer_connected=False)
