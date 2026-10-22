"""Conserved, explicitly conditional allocation of factual injury vacancies.

An active-role reference is a counterfactual proxy, not an OUT player's forecast.
Recipient fractions are authored assumptions, never inferred from user exclusions.
"""
from copy import deepcopy
from uuid import UUID

from .evaluation_record import digest
from .factual_designation import clock
from .workload_count_forecast import CHANNELS, finite
from .player_roles import UNAVAILABLE, PRACTICE

VERSION = 'factual_out_conditional_allocation_v1'


def _proof(evidence, pid, team, cutoff, before_period):
    if not isinstance(evidence, dict) or str(evidence.get('player_id')) != pid or evidence.get('team') != team:
        raise ValueError('Role allocation evidence identity/team mismatch')
    if not evidence.get('source_ids') or not evidence.get('source_uri'):
        raise ValueError('Role allocation requires sourced evidence')
    roster_bound=evidence.get('fact_type')=='roster_status' and evidence.get('decision_period')==before_period and evidence.get('scope_basis')=='validated_current_canonical_roster_participation_prohibition'
    if not roster_bound and (evidence.get('season') != before_period//100 or evidence.get('week') != before_period%100):
        raise ValueError('Role allocation evidence period mismatch')
    if evidence.get('game_id'):
        parts=evidence['game_id'].split('_')
        if len(parts)!=4 or parts[:2]!=[str(before_period//100),f'{before_period%100:02d}'] or team not in parts[2:]:
            raise ValueError('Role allocation evidence game scope mismatch')
    observed = clock(evidence.get('observed_at')); received = clock(evidence.get('received_at'))
    if observed is None or received is None or not observed <= received <= clock(cutoff):
        raise ValueError('Role allocation evidence is missing/future')


def allocate_factual_vacancies(reference, *, unavailable, allocations=(), cutoff):
    """Apply OUT facts, then optional explicitly authored fractions of known work.

    `unavailable`: canonical actor/team/designation plus typed source evidence.
    `allocations`: donor/recipient/channel/fraction + rationale/assumption_id;
    recipient requires current canonical-role evidence. No preference inputs.
    Full-team budgets remain unchanged; missing donor/recipient counts abstain.
    """
    result = deepcopy(reference)
    before_period=reference['before_period']
    actors = {str(p['player_master_id']): p for p in result['players']}
    if len(actors) != len(result['players']): raise ValueError('Duplicate canonical role actor')
    for pid in actors: UUID(pid)
    vacancies = {}; facts = []; transitions = []; seen=set()
    for fact in unavailable:
        pid = str(fact['player_master_id']); actor = actors.get(pid)
        if actor is None or actor['team'] != fact.get('team'): raise ValueError('OUT actor outside full source universe')
        if pid in seen: raise ValueError('Duplicate OUT fact')
        seen.add(pid)
        if fact.get('designation') not in UNAVAILABLE | PRACTICE | {'CUT'}:
            raise ValueError('Only factual unavailable designations create a vacancy; Q/user exclusion does not')
        _proof(fact.get('evidence'), pid, actor['team'], cutoff, before_period)
        if fact['evidence'].get('designation') != fact['designation']:
            raise ValueError('Unavailable designation differs from bound factual evidence')
        if fact['evidence'].get('fact_type') not in {'game_status', 'reserve_status', 'roster_status'}:
            raise ValueError('Unavailable fact must be game/reserve status, not salary/preference')
        # Practice-squad non-elevation is a current participation condition,
        # never evidence of vacated normal-role work for another player.
        replacement_vacancy= fact['designation'] not in PRACTICE
        if replacement_vacancy:vacancies[pid] = deepcopy(actor['counts'])
        actor['replacement_vacancy_eligible']=replacement_vacancy
        facts.append(deepcopy(fact))
        actor['hypothetical_active_role_reference_counts'] = deepcopy(actor['counts'])
        actor['counts'] = {c: 0. for c in CHANNELS}  # Factual nonparticipation proves no football production, not historical zeros.
        actor['world_activity'] = False
        actor['world_activity_reason'] = ('Source-verified factual unavailable; not user exclusion' if replacement_vacancy else 'Current practice-squad role; conditional on no sourced elevation, no replacement vacancy inferred')
        actor.setdefault('reasons', []).append('Active-role history retained only as hypothetical vacancy proxy')
    used = {}
    for assumption in allocations:
        donor = str(assumption['donor_player_master_id']); recipient = str(assumption['recipient_player_master_id'])
        channel = assumption['channel']; fraction = finite(assumption.get('fraction'))
        if donor not in vacancies or recipient not in actors or recipient in seen or actors.get(recipient,{}).get("world_activity") is False or channel not in CHANNELS:
            raise ValueError('Invalid conditional vacancy actors/channel')
        source = actors[donor]; target = actors[recipient]
        if source['team'] != target['team']: raise ValueError('No cross-team replacement allocation')
        if fraction is None or fraction > 1 or not assumption.get('assumption_id') or not assumption.get('rationale'):
            raise ValueError('Explicit conditional fraction/rationale required')
        proof = target.get('current_role_evidence')
        _proof(proof, recipient, target['team'], cutoff, before_period)
        if proof.get('role') not in {'expected_starter', 'expected_backup', 'rotational'}:
            raise ValueError('Recipient role unsupported')
        key = (donor, channel); used[key] = used.get(key, 0.) + fraction
        if used[key] > 1 + 1e-9: raise ValueError('Conditional fractions exceed vacancy')
        vacancy = finite(vacancies[donor].get(channel)); before = finite(target['counts'].get(channel))
        amount = vacancy * fraction if vacancy is not None and before is not None else None
        if amount is not None: target['counts'][channel] = before + amount
        target['conditional_on'] = 'Active participation and authored injury-replacement allocation; likelihood unknown'
        transitions.append(dict(**deepcopy(assumption), team=source['team'], vacancy_proxy=vacancy,
            recipient_reference_count=before, transferred=amount,
            status='conditional_supported_reference_allocation' if amount is not None else 'unavailable_missing_reference_or_recipient_count',
            meaning='Declared sensitivity assumption, not measured recipient share or fitted probability'))
    for team, budget in result['teams'].items():
        if budget is None: continue
        budget['reconciliation'] = {}
        for channel in CHANNELS:
            known = [p['counts'].get(channel) for p in actors.values() if p['team'] == team]
            total = sum(v for v in known if v is not None); available = finite(budget.get(channel))
            if available is not None and total > available + 1e-6: raise ValueError('Conditional allocation exceeds physical team budget')
            budget['reconciliation'][channel] = dict(allocated_known=total,
                unallocated=available-total if available is not None else None,
                unknown_actors=sum(v is None for v in known), redistribution_from_user_preferences=False)
    result['availability_conditions'] = dict(version=VERSION, factual_unavailable=facts,
        hypothetical_active_role_vacancies=vacancies, conditional_allocations=transitions,
        likelihood='unknown', residual_policy='Unassigned and unknown work stays residual; excluded actors never donate')
    # Execution/source receipt IDs remain provenance; factual clocks validate above.
    def semantic(v):
        if isinstance(v, dict): return {k: semantic(x) for k,x in v.items() if k not in {'observed_at','received_at','source_ids','source_uri'}}
        if isinstance(v, list): return [semantic(x) for x in v]
        return v
    result['availability_conditions']['semantic_sha256'] = digest(semantic(result['availability_conditions']))
    return result


def unavailable_from_canonical_rows(rows, *, before_period, cutoff):
    """Use matching retained scoped proof, not only newest native chosen flag."""
    from .factual_designation import CONTRACT, status
    from .market_snapshots import canonical_team
    facts=[];unknown=[]
    for source in rows:
        from .showdown_player_context import _binding_roster_unavailability
        if _binding_roster_unavailability(source,cutoff=cutoff,evaluated_at=cutoff,max_age_hours=24):
            original=source['binding_roster_unavailability'];pid=str(source.get('player_id'));team=canonical_team(source.get('player_team') or source.get('team'))
            if str(original.get('player_id'))!=pid or original.get('team')!=team:raise ValueError('Bound roster proof identity differs from count actor')
            token=status(original['status'])
            facts.append(dict(player_master_id=pid,team=team,designation=token,evidence={**original,                'designation':token,'fact_type':'roster_status','decision_period':before_period,                'scope_basis':'validated_current_canonical_roster_participation_prohibition'},                chosen_eligibility_fact=deepcopy((source.get('designation_resolution') or {}).get('chosen_fact')),                retained_designation_conflicts=deepcopy((source.get('designation_resolution') or {}).get('conflicts'))))
            continue
        resolved=source.get('designation_resolution') or {};token=status(resolved.get('effective_designation'))
        if resolved.get('contract')!=CONTRACT or resolved.get('status')!='resolved' or token not in {'OUT','IR','PUP','NFI','SUSPENDED','RESERVE'}:continue
        pid=str(source.get('player_id'));team=canonical_team(source.get('player_team') or source.get('team'))
        proof=None
        candidates=[resolved.get('chosen_fact') or {},*resolved.get('source_facts',[])]
        # Administrative IR and an exact scoped official OUT both establish
        # nonparticipation. Preserve their distinct tokens rather than relabeling
        # the official fact as IR or interpreting Q/ACTIVE as unavailable.
        candidates=sorted(candidates,key=lambda c:status(c.get('status'))!=token)
        for candidate in candidates:
            proof_token=status(candidate.get('status'))
            if proof_token not in UNAVAILABLE or candidate.get('kind') not in {'game_status','reserve_status'}:continue
            evidence={**candidate,'designation':proof_token,'fact_type':candidate.get('kind')}
            try:_proof(evidence,pid,team,cutoff,before_period)
            except (ValueError,TypeError):continue
            proof=evidence;break
        if proof is None:
            unknown.append(dict(player_master_id=pid,effective_designation=token,
                reason='Resolved unavailable, but no matched scoped original fact for vacancy; do not infer replacement work'))
        else:facts.append(dict(player_master_id=pid,team=team,designation=proof['designation'],evidence=proof,
            effective_designation_at_cutoff=token,chosen_eligibility_fact=deepcopy(resolved.get('chosen_fact'))))
    return facts,unknown
