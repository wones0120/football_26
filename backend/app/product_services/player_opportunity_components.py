"""Observed actor opportunities from verified prior events; never replacement shares.

The caller authenticates the immutable parent/raw source. These game-log measures
are not complete-game proof, routes, fitted next-game counts, or FP bonuses.
"""
from copy import deepcopy
import hashlib
from pathlib import Path

from .opportunity_events import validate_event_evidence, _flag
from .defense_context_evidence import _eligibility, _number, _metric, _finish, _hash
from .defense_context_extensions import _positions
from .environment_context_evidence import _and

VERSION='player_opportunity_components_v1'
DEFINITIONS={
    'official_pass_attempts':'All proven official attempts, including spikes; sacks excluded',
    'completions':'Known complete_pass on official attempts',
    'nonspike_dropbacks':'Reported qb_dropback excluding known spikes',
    'sacks':'Known sack on nonspike reported dropbacks',
    'spikes':'Known qb_spike on official attempts',
    'scrambles_per_dropback':'Known qb_scramble on nonspike reported dropbacks',
    'official_rush_attempts':'All proven official rush attempts, including kneels',
    'nonkneel_rush_attempts':'Proven official rush with qb_kneel=False',
    'designed_or_other_nonkneel_rushes':'Nonkneel rush with qb_scramble=False; not proof of designed QB play call',
    'scrambles':'Nonkneel rush with qb_scramble=True',
    'kneels':'Proven official rush with qb_kneel=True',
    'early_down_carries':'Nonkneel rush, preplay down1 or2',
    'third_down_carries':'Nonkneel rush, preplay down3',
    'short_yard_carries':'Nonkneel rush, preplay ydstogo in [0,2]',
    'two_minute_carries':'Nonkneel rush, qtr2 or4 and half_seconds_remaining in [0,120]; observed clock-window variant',
    'first_half_carries':'Nonkneel rush in qtr1 or2',
    'fourth_quarter_carries':'Nonkneel rush in qtr4',
    'leading_carries':'Nonkneel rush with preplay offense score_differential>0',
    'trailing_carries':'Nonkneel rush with preplay offense score_differential<0',
    'redzone_carries':'Nonkneel rush, preplay yardline_100 in [0,20]',
    'inside5_carries':'Nonkneel rush, preplay yardline_100 in [0,5]',
    'rush_first_downs':'Known first_down_rush on nonkneel rush',
    'rush_touchdowns':'Known rush_touchdown on nonkneel rush',
    'targets':'Known official receiver-attributed targets; not routes',
    'air_yards':'Signed supplied air_yards on known official targets; missing not zero',
}


def _binary(value):
    flag=_flag(value)
    return None if flag is None else float(flag)


def _condition(value,predicate,valid=lambda n:True):
    n=_number(value)
    return None if n is None or not valid(n) else bool(predicate(n))


def _record(metrics,key,eligible,value=1.):
    metric=metrics.setdefault(key,_metric())
    if eligible is None:metric['unknown_eligibility_events']+=1
    elif eligible:
        metric['eligible_events']+=1
        if value is None:metric['unknown_outcome_events']+=1
        else:metric['known_outcome_events']+=1;metric['observed_outcome_sum']+=value


def build_player_opportunity_components(event_receipt, *, before_period, cutoff, position_evidence=()):
    evidence=validate_event_evidence(event_receipt['event_evidence'],before_period=before_period,cutoff=cutoff)
    proofs=deepcopy(list(position_evidence));positions,_=_positions(proofs,cutoff)
    for game,_,_ in positions:
        year,week=map(int,game.split('_')[:2])
        if not 1<=week<=18 or year*100+week>=before_period:raise ValueError('Position proof must be prior REG')
    identities={};actors={};unattributed=[];used=set();basis=[]
    for row in evidence['players']:
        native=row['source_player_id'];pid=row['player_master_id']
        if native is not None and pid is not None:
            key=(row['game_id'],row['team'],native)
            if key in identities and identities[key]!=pid:raise ValueError('Native actor has conflicting canonical identity')
            identities[key]=pid
    for (game,native,team),proof in positions.items():
        key=(game,team,native);pid=proof['player_master_id']
        if pid is not None:
            if key in identities and identities[key]!=pid:raise ValueError('Scoped position canonical identity contradicts parent')
            identities[key]=pid
    canonical_native={}
    for (game,team,native),pid in identities.items():
        key=(game,pid)
        if key in canonical_native and canonical_native[key]!=(team,native):raise ValueError('Canonical actor has conflicting native/team keys')
        canonical_native[key]=(team,native)
    team_metrics={}
    for event in sorted(evidence['events'],key=lambda e:(e['game_id'],int(e['play_id']))):
        raw=event['raw_flags'];game=event['game_id'];team=event['team'];channels={o['channel'] for o in event['opportunities']}
        passing,dropback,rushing=_eligibility(event)
        official_pass=True if 'pass_attempts' in channels else None if 'pass_attempts' in event['unknown_channels'] else False
        official_rush=True if 'rush_attempts' in channels else None if 'rush_attempts' in event['unknown_channels'] else False
        target=True if 'targets' in channels else None if 'targets' in event['unknown_channels'] else False
        tm=team_metrics.setdefault((game,team),{})
        _record(tm,'nonkneel_rush_attempts',rushing)
        _record(tm,'air_yards',target,_number(raw.get('air_yards')))
        down=raw.get('down');qtr=raw.get('qtr');yard=raw.get('yardline_100');score=raw.get('score_differential')
        splits={
            'early_down_carries':_condition(down,lambda n:n in {1,2},lambda n:n in {1,2,3,4}),
            'third_down_carries':_condition(down,lambda n:n==3,lambda n:n in {1,2,3,4}),
            'short_yard_carries':_condition(raw.get('ydstogo'),lambda n:n<=2,lambda n:n>=0),
            'two_minute_carries':_and(_condition(qtr,lambda n:n in {2,4},lambda n:n in {1,2,3,4,5}),_condition(raw.get('half_seconds_remaining'),lambda n:n<=120,lambda n:0<=n<=1800)),
            'first_half_carries':_condition(qtr,lambda n:n in {1,2},lambda n:n in {1,2,3,4,5}),
            'fourth_quarter_carries':_condition(qtr,lambda n:n==4,lambda n:n in {1,2,3,4,5}),
            'leading_carries':_condition(score,lambda n:n>0),
            'trailing_carries':_condition(score,lambda n:n<0),
            'redzone_carries':_condition(yard,lambda n:n<=20,lambda n:0<=n<=100),
            'inside5_carries':_condition(yard,lambda n:n<=5,lambda n:0<=n<=100),
        }
        passer=raw.get('passer_player_id') or (raw.get('rusher_player_id') if _flag(raw.get('qb_scramble')) is True else None)
        groups=[('passer',passer,{'official_pass_attempts':(official_pass,1.),'completions':(official_pass,_binary(raw.get('complete_pass'))),
            'nonspike_dropbacks':(dropback,1.),'sacks':(dropback,_binary(raw.get('sack'))),
            'spikes':(official_pass,_binary(raw.get('qb_spike'))),'scrambles_per_dropback':(dropback,_binary(raw.get('qb_scramble')))}),
            ('rusher',raw.get('rusher_player_id'),{'official_rush_attempts':(official_rush,1.),'nonkneel_rush_attempts':(rushing,1.),
                'designed_or_other_nonkneel_rushes':(_and(rushing,None if _flag(raw.get('qb_scramble')) is None else not _flag(raw.get('qb_scramble'))),1.),
                'scrambles':(_and(rushing,_flag(raw.get('qb_scramble'))),1.),'kneels':(_and(official_rush,_flag(raw.get('qb_kneel'))),1.),
                'rush_first_downs':(rushing,_binary(raw.get('first_down_rush'))),'rush_touchdowns':(rushing,_binary(raw.get('rush_touchdown'))),
                **{m:(_and(rushing,condition),1.) for m,condition in splits.items()}}),
            ('receiver',raw.get('receiver_player_id'),{'targets':(target,1.),'air_yards':(target,_number(raw.get('air_yards')))})]
        for role,native,outcomes in groups:
            if not any(e is not False for e,_ in outcomes.values()):continue
            if not native:
                unattributed.append(dict(game_id=game,play_id=event['play_id'],team=team,role=role,reason='Native actor unavailable; team evidence retained'))
                continue
            key=(game,team,str(native));proof=positions.get((game,str(native),team))
            if proof:used.add((game,str(native),team))
            actor=actors.setdefault(key,dict(game_id=game,team=team,source_player_id=str(native),player_master_id=identities.get(key),
                position=proof['position'] if proof else None,position_status='scoped_source_proven' if proof else 'unknown',metrics={}))
            for m,(eligible,value) in outcomes.items():_record(actor['metrics'],m,eligible,value)
            basis.append(dict(game_id=game,play_id=event['play_id'],team=team,source_player_id=str(native),role=role,outcomes=outcomes))
    budgets={(r['game_id'],r['team']):r for r in evidence['teams']}
    attribution_unknown={}
    for missing in unattributed:
        roles=attribution_unknown.setdefault((missing['game_id'],missing['team']),{})
        roles[missing['role']]=roles.get(missing['role'],0)+1
    rows=[]
    for key,actor in sorted(actors.items()):
        metric=actor['metrics'];budget=budgets.get(key[:2],{});team=team_metrics[key[:2]]
        target_total=(budget.get('counts') or {}).get('targets');target_value=metric.get('targets')
        rush_value=metric.get('nonkneel_rush_attempts');rush_total=team['nonkneel_rush_attempts']
        air=metric.get('air_yards');air_total=team['air_yards']
        def ratio(n,d):return n/d if n is not None and d is not None and d!=0 else None
        def known_sum(m):return m['observed_outcome_sum'] if m and not m['unknown_eligibility_events'] and not m['unknown_outcome_events'] else None
        actor['source_channel_coverage']=deepcopy(budget.get('channel_coverage') or {})
        actor['inherited_team_unknown_eligibility']=deepcopy(budget.get('unknown_eligibility_events') or {})
        actor['unknown_native_attribution_exposures']=deepcopy(attribution_unknown.get(key[:2],{}))
        unknown_roles=actor['unknown_native_attribution_exposures']
        actor['shares']=dict(target_share=ratio(known_sum(target_value),target_total) if not unknown_roles.get('receiver') else None,nonkneel_carry_share=ratio(known_sum(rush_value),known_sum(rush_total)) if not unknown_roles.get('rusher') else None,
            signed_air_yard_share=ratio(known_sum(air),known_sum(air_total)),
            average_target_depth=ratio(known_sum(air),known_sum(target_value)) if not actor['inherited_team_unknown_eligibility'].get('targets') and not unknown_roles.get('receiver') else None,
            known_attributed_sample_depth=ratio(known_sum(air),known_sum(target_value)))
        actor['metrics']={}
        for m,v in metric.items():
            finished=_finish(v)
            channel='targets' if m in {'targets','air_yards'} else 'pass_attempts' if m in {'official_pass_attempts','completions','spikes'} else 'rush_attempts' if m not in {'nonspike_dropbacks','sacks','scrambles_per_dropback'} else None
            finished['unit']='signed_yards' if m=='air_yards' else 'events'
            role='receiver' if m in {'targets','air_yards'} else 'passer' if m in {'official_pass_attempts','completions','spikes','nonspike_dropbacks','sacks','scrambles_per_dropback'} else 'rusher'
            finished['exact_within_log_sum']=v['observed_outcome_sum'] if not unknown_roles.get(role) and not v['unknown_eligibility_events'] and not v['unknown_outcome_events'] and (channel is None or not actor['inherited_team_unknown_eligibility'].get(channel)) else None
            actor['metrics'][m]=finished
        rows.append(actor)
    result=dict(version=VERSION,before_period=before_period,definitions=DEFINITIONS,actor_game_rows=rows,
        team_denominators=[dict(game_id=g,team=t,official=deepcopy(budgets.get((g,t))),measured={m:_finish(v) for m,v in metrics.items()}) for (g,t),metrics in sorted(team_metrics.items())],
        source_quality={k:deepcopy(evidence['source'].get(k)) for k in ('game_completion','full_game_coverage')},
        official_reconciliation=[{k:v for k,v in r.items() if k not in {'official_source_id','official_imported_at'}} for r in sorted(evidence['official_reconciliation'],key=lambda r:(r['game_id'],r['team'],r['source_player_id'],r['channel']))],
        unattributed_events=unattributed,identity_review_requests=[dict(game_id=r['game_id'],team=r['team'],source_player_id=r['source_player_id'],reason='Persist unresolved native actor through existing identity queue') for r in rows if r['player_master_id'] is None],
        limitations=['Verified parent intake required; checksum is not source authentication','Observed prior logs; full-game completeness/original publication chronology unknown',
            'Position-dependent QB/RB catalog interpretation requires scoped position proof; generic passer/rusher is not QB/RB proof',
            'Designed-or-other non-scramble rush is not proof of designed QB play call','Routes/pressure/first-read/catchability/recipient replacement shares unavailable'],forecast=None)
    result['semantic_measurements_sha256']=_hash(dict(result=result,event_basis=basis,position_facts=[positions[k] for k in sorted(used)]))
    result['provenance']=dict(source=deepcopy(evidence['source']),event_receipt_sha256=evidence['sha256'],position_evidence=proofs,
        decision_cutoff_at=str(cutoff),producer_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return result


RETROSPECTIVE_USE='postlock_descriptive_not_pregame_or_serving'


def require_component_use(value, *, purpose, consumer_contract=None):
    """Explicit contract boundary for future named consumers; no implicit serving."""
    if purpose=='offline_descriptive':return value
    if value.get('evidence_use')==RETROSPECTIVE_USE:
        raise ValueError('Postlock descriptive components cannot be registered or consumed as pregame/current serving evidence')
    if value.get('pregame_serving_eligible') is not True:
        raise ValueError('Player component current-serving contract is not approved')
    if consumer_contract=='new_model_primary_v1' and value.get('current_consumer_contract')==consumer_contract:
        return value
    raise ValueError('No current model/scenario consumer contract is implemented in this measured producer')


def derive_retrospective_player_components(parent_ref,snapshot,*,actual_read_at=None,directory=None,position_evidence=()):
    """Offline revalidation of frozen bytes, not a current pregame source intake.

    The original cutoff is used ONLY to verify the already-frozen parent against
    its original boundary. Actual read/derivation clocks and a nonserving use
    restriction are separately retained. The normal intake lock guard is intact.
    """
    from datetime import UTC,datetime
    from .factual_designation import clock
    from .opportunity_source_capture import load_event_artifact
    read_at=clock(actual_read_at or datetime.now(UTC));now=datetime.now(UTC)
    lock=clock(snapshot.slate_lock_at);original=clock(parent_ref.get('decision_cutoff_at'))
    if lock is None or original is None or not original<lock<=read_at<=now:
        raise ValueError('Retrospective reader requires original prelock evidence and actual nonfuture postlock read')
    parent=load_event_artifact(parent_ref,snapshot,before_period=parent_ref['before_period'],cutoff=original,directory=directory)
    value=build_player_opportunity_components(parent,before_period=parent_ref['before_period'],cutoff=read_at,position_evidence=position_evidence)
    value['underlying_measurements_sha256']=value.pop('semantic_measurements_sha256')
    value.update(evidence_use=RETROSPECTIVE_USE,pregame_serving_eligible=False)
    value['semantic_measurements_sha256']=_hash(dict(underlying_measurements_sha256=value['underlying_measurements_sha256'],evidence_use=RETROSPECTIVE_USE,pregame_serving_eligible=False))
    value['provenance'].pop('decision_cutoff_at')
    value['provenance']['retrospective_read']=dict(original_evidence_boundary_at=original.isoformat(),source_lock_at=lock.isoformat(),
        actual_read_at=read_at.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),
        validation_meaning='Frozen parent byte/identity revalidation at its original evidence boundary, not a new pregame intake',parent_artifact_ref=deepcopy(parent_ref))
    return value
