"""Observed physical TD fraction among declared source-credited explosive plays."""
from copy import deepcopy
from .opportunity_events import validate_event_evidence,_flag
from .defense_context_evidence import _number
from .environment_context_evidence import _and
from .player_effectiveness_components import _yards
from .evaluation_record import digest

VERSION='source_credited_explosive_td_features_v1'
THRESHOLDS={'pass':20.,'rush':10.}


def _counter():return dict(known_explosive_plays=0,known_explosive_tds=0,unknown_explosive_eligibility=0,unknown_explosive_td_outcomes=0)

def build_explosive_touchdown_features(receipt,*,before_period,cutoff):
    evidence=validate_event_evidence(receipt,before_period=before_period,cutoff=cutoff);games={}
    for e in evidence['events']:
        raw=e['raw_flags'];channels={o['channel'] for o in e['opportunities']}
        conditions={name:True if channel in channels else None if channel in e['unknown_channels'] else False for name,channel in [('pass','pass_attempts'),('rush','rush_attempts')]}
        if conditions['pass'] is True and conditions['rush'] is True:raise ValueError('Physical official pass/rush overlap')
        if all(v is False for v in conditions.values()):continue
        g=games.setdefault((e['game_id'],e['team']),dict(game_id=e['game_id'],team=e['team'],season=e['season'],week=e['week'],channels={n:_counter() for n in ('pass','rush','physical_union')},events=[]))
        classified=[]
        for name in ('pass','rush'):
            eligible=conditions[name]
            yards=(_yards(raw,'passing_yards') if name=='pass' else _number(raw.get('rushing_yards'))) if eligible is not False else None
            explosive=_and(eligible,None if yards is None else yards>=THRESHOLDS[name])
            td=_flag(raw.get('pass_touchdown' if name=='pass' else 'rush_touchdown'))
            fact=dict(channel=name,official_eligibility=eligible,source_credited_yards=yards,explosive=explosive,touchdown=td)
            classified.append(fact)
            m=g['channels'][name]
            if explosive is None:m['unknown_explosive_eligibility']+=1
            elif explosive:
                m['known_explosive_plays']+=1
                if td is None:m['unknown_explosive_td_outcomes']+=1
                else:m['known_explosive_tds']+=td
        known=[r for r in classified if r['explosive'] is True];unknown=[r for r in classified if r['explosive'] is None]
        m=g['channels']['physical_union']
        if len(known)>1:raise ValueError('Explosive event counted twice')
        if known:
            m['known_explosive_plays']+=1
            flags=[_flag(raw.get(k)) for k in ('pass_touchdown','rush_touchdown')]
            td=True if True in flags else False if all(v is False for v in flags) else None
            if td is None:m['unknown_explosive_td_outcomes']+=1
            else:m['known_explosive_tds']+=td
        elif unknown:m['unknown_explosive_eligibility']+=1
        g['events'].append(dict(play_id=e['play_id'],channels=classified))
    rows=[]
    for _,g in sorted(games.items()):
        for m in g['channels'].values():
            n=m['known_explosive_plays'];known=n-m['unknown_explosive_td_outcomes']
            m['value']=m['known_explosive_tds']/n if n and not(m['unknown_explosive_eligibility'] or m['unknown_explosive_td_outcomes']) else None
            m['known_sample_rate']=m['known_explosive_tds']/known if known else None
        rows.append(g)
    basis=dict(version=VERSION,candidate_id='G12-M09',before_period=before_period,thresholds=THRESHOLDS,game_rows=rows,source_event_sha256=evidence['sha256'])
    return basis|dict(semantic_sha256=digest(basis),source=deepcopy(evidence['source']),evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None,model_consumed=False,optimizer_consumed=False,
        limitations=['Source-credited passing/rushing yards, no initial-receiver or team-net substitution','Threshold conventions reuse reviewed10rush/20pass definitions; no optimization/tuning to observedTDs','Rates are observed descriptions, not predicted TD probability; empty explosive populations undefined'])


def derive_retrospective_explosive_tds(parent_ref,snapshot,*,actual_read_at,directory=None):
    from datetime import datetime,UTC
    from pathlib import Path
    import hashlib
    from .factual_designation import clock
    from .opportunity_source_capture import load_event_artifact
    original,actual,lock=(clock(v) for v in (parent_ref['decision_cutoff_at'],actual_read_at,snapshot.slate_lock_at))
    if None in (original,actual,lock) or not original<lock<=actual<=datetime.now(UTC):raise ValueError('Explicit retrospective source boundary required')
    parent=load_event_artifact(parent_ref,snapshot,before_period=parent_ref['before_period'],cutoff=original,directory=directory)
    result=build_explosive_touchdown_features(parent['event_evidence'],before_period=parent_ref['before_period'],cutoff=actual)
    result['provenance']=dict(parent_ref=deepcopy(parent_ref),original_evidence_boundary_at=original.isoformat(),source_lock_at=lock.isoformat(),actual_read_at=actual.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return result


def require_feature_use(value,*,purpose):
    if value.get('version')!=VERSION or purpose!='offline_descriptive' or value.get('pregame_serving_eligible') is not False:raise ValueError('Observed explosive TD rates cannot serve forecasts/models/optimizer')
    return value
