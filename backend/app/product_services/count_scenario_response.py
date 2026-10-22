"""One count-transform ancestry for supported authored conditional worlds."""
from copy import deepcopy

from .count_component_response import component_response, VERSION
from .evaluation_record import digest
from .opportunity_role_allocation import allocate_factual_vacancies


def count_world(receipt, scenario, base_means, *, cutoff):
    reference=receipt['reference_count_forecast']
    current={k:deepcopy(receipt[k]) for k in ('version','before_period','teams','players','team_budget_model_contract','availability_conditions') if k in receipt}
    # Avoid nested model/source receipts inside each actor/world; immutable parent
    # receipt remains the authoritative provenance and efficiency anchor.
    changes=[];allocations=[]
    for assumption in scenario['assumptions']:
        kind=assumption['kind'];team=assumption['team']
        if team not in current['teams']:raise ValueError('Count world team outside frozen full-source universe')
        if kind in {'passing_volume','rushing_volume'}:
            factor=float(assumption['factor'])
            if not 0<=factor<=2:raise ValueError('Invalid physical conditional volume factor')
            channels=('pass_attempts','targets') if kind=='passing_volume' else ('rush_attempts',)
            for channel in channels:
                if current['teams'][team].get(channel) is not None:current['teams'][team][channel]*=factor
                for donor,proxy in (current.get('availability_conditions') or {}).get('hypothetical_active_role_vacancies',{}).items():
                    if any(p['player_master_id']==donor and p['team']==team for p in current['players']) and proxy.get(channel) is not None:proxy[channel]*=factor
                for actor in current['players']:
                    if actor['team']==team and actor['counts'].get(channel) is not None:actor['counts'][channel]*=factor
        elif kind=='target_concentration':
            selected=set(assumption['player_master_ids']);members=[p for p in current['players'] if p['team']==team]
            if any(p['counts'].get('targets') is None for p in members if p['position'] in {'RB','WR','TE'}):
                raise ValueError('Count concentration requires known full-source skill target allocations')
            known=[p for p in members if p['counts'].get('targets') is not None]
            total=sum(p['counts']['targets'] for p in known);target=sum(p['counts']['targets'] for p in known if p['player_master_id'] in selected)
            rest=total-target;delta=float(assumption['share_delta'])*total
            if target<=0 or rest<=0 or target+delta<0 or rest-delta<0:raise ValueError('Count concentration exceeds known physical allocations')
            for actor in known:
                actor['counts']['targets']*=((target+delta)/target if actor['player_master_id'] in selected else (rest-delta)/rest)
        elif kind=='workload_transfer':
            channel='rush_attempts' if assumption.get('workload')=='carries' else 'targets'
            donor=assumption['from_player_master_id'];recipient=assumption['to_player_master_id']
            by_id={p['player_master_id']:p for p in current['players']}
            # Only a factual OUT vacancy can power injury replacement. Ordinary
            # active-player transfers retain explicit source-supported quantities.
            if by_id[donor].get('world_activity') is False:
                allocations.append(dict(donor_player_master_id=donor,recipient_player_master_id=recipient,channel=channel,
                    fraction=assumption['fraction'],assumption_id=scenario['scenario_id']+':'+str(len(changes)),
                    rationale=assumption.get('rationale') or scenario.get('label') or 'Authored conditional replacement allocation'))
            else:
                a=by_id[donor];b=by_id[recipient]
                if a['team']!=team or b['team']!=team:raise ValueError('Conditional transfer crosses team')
                if b.get('world_activity') is False:raise ValueError('Conditional transfer recipient is factually inactive')
                x=a['counts'].get(channel);y=b['counts'].get(channel)
                if x is None or y is None:raise ValueError('Unknown conditional transfer amount stays unallocated')
                moved=x*float(assumption['fraction']);a['counts'][channel]-=moved;b['counts'][channel]+=moved
        else:raise ValueError('Unsupported count-world mechanism')
        changes.append(dict(assumption=deepcopy(assumption),legacy_elasticity_consumption='not_consumed',
            ancestry='Physical count transform then matched linear DK component difference; no total-FP elasticity'))
    if allocations:
        # Restore hypothetical donor counts only for allocator's vacancy proxy;
        # its returned world always returns those factual OUT actors to zero.
        conditions=current.get('availability_conditions') or {}
        for actor in current['players']:
            proxy=conditions.get('hypothetical_active_role_vacancies',{}).get(actor['player_master_id'])
            if proxy is not None:actor['counts']=deepcopy(proxy)
        current=allocate_factual_vacancies(current,unavailable=conditions['factual_unavailable'],allocations=allocations,cutoff=cutoff)
    # Recompute count residuals after every physical world transform; retaining
    # the pre-transform reconciliation would report stale vacancy/volume work.
    for team,budget in current['teams'].items():
        if budget is None:continue
        budget['reconciliation']={}
        for channel in ('pass_attempts','rush_attempts','targets'):
            values=[p['counts'].get(channel) for p in current['players'] if p['team']==team]
            allocated=sum(v for v in values if v is not None);available=budget.get(channel)
            if available is not None and allocated>available+1e-6:raise ValueError('Conditional world exceeds full-source count budget')
            budget['reconciliation'][channel]=dict(allocated_known=allocated,
                unallocated=available-allocated if available is not None else None,
                unknown_actors=sum(v is None for v in values),redistribution_from_user_preferences=False)
    response=component_response(None,reference,current,base_means,before_period=receipt['before_period'],cutoff=cutoff,
        efficiency=receipt['component_response']['efficiency_receipt'])
    return dict(version=VERSION,scenario_id=scenario['scenario_id'],response=response,changes=changes,
        parent_count_receipt_sha256=receipt['sha256'],semantic_sha256=digest(dict(response=response['semantic_sha256'],changes=changes)))
