"""Receiver targets ending at source-reported longitudinal end-zone depth."""
from copy import deepcopy
from .opportunity_events import validate_event_evidence
from .defense_context_evidence import _number
from .environment_context_evidence import _and
from .evaluation_record import digest

VERSION='source_longitudinal_endzone_targets_v1'


def build_endzone_target_components(receipt,*,before_period,cutoff):
    evidence=validate_event_evidence(receipt,before_period=before_period,cutoff=cutoff)
    identities={};canonical={}
    for e in evidence['events']:
        for o in e['opportunities']:
            if not o.get('player_master_id') or not o.get('source_player_id'):continue
            key=(e['game_id'],e['team'],o['source_player_id']);pid=o['player_master_id']
            if key in identities and identities[key]!=pid:raise ValueError('Native target canonical conflict')
            if (e['game_id'],pid) in canonical and canonical[(e['game_id'],pid)]!=key:raise ValueError('Canonical target native/team conflict')
            identities[key]=pid;canonical[(e['game_id'],pid)]=key
    actors={};teams={};unattributed=[];events=[]
    for e in evidence['events']:
        raw=e['raw_flags'];key=(e['game_id'],e['team']);channels={o['channel'] for o in e['opportunities']}
        target=True if 'targets' in channels else None if 'targets' in e['unknown_channels'] else False
        if target is False:continue
        air=_number(raw.get('air_yards'));yard=_number(raw.get('yardline_100'))
        valid=air is not None and yard is not None and 0<=yard<=100
        depth=air-yard if valid else None;member=None if depth is None else 0<=depth<=10
        occurrence=_and(target,member);native=raw.get('receiver_player_id')
        team=teams.setdefault(key,dict(game_id=key[0],team=key[1],known_endzone_targets=0,unknown_endzone_target_events=0,unattributed_endzone_events=0,events=[]))
        fact=dict(play_id=e['play_id'],source_player_id=native,target_eligibility=target,air_yards=air,yardline_100=yard,longitudinal_endpoint_depth=depth,
            endzone_depth_membership=member,endzone_target=occurrence)
        team['events'].append(fact);events.append(dict(game_id=key[0],team=key[1],**fact))
        if occurrence is True:team['known_endzone_targets']+=1
        elif occurrence is None:team['unknown_endzone_target_events']+=1
        if not native:
            if occurrence is not False:
                team['unattributed_endzone_events']+=1;unattributed.append(dict(game_id=key[0],team=key[1],**fact))
            continue
        akey=(*key,str(native));a=actors.setdefault(akey,dict(game_id=key[0],team=key[1],source_player_id=str(native),player_master_id=identities.get(akey),known_endzone_targets=0,unknown_endzone_target_events=0,observed_target_candidate_events=0))
        a['observed_target_candidate_events']+=1
        if occurrence is True:a['known_endzone_targets']+=1
        elif occurrence is None:a['unknown_endzone_target_events']+=1
    rows=[]
    for key,a in sorted(actors.items()):
        unassigned=teams[key[:2]]['unattributed_endzone_events']
        rows.append(dict(a,unattributed_potential_endzone_events=unassigned,value=a['known_endzone_targets'] if not(a['unknown_endzone_target_events'] or unassigned) else None))
    team_rows=[dict(t,value=t['known_endzone_targets'] if not t['unknown_endzone_target_events'] else None) for _,t in sorted(teams.items())]
    basis=dict(version=VERSION,candidate_id='G12-M08',before_period=before_period,actor_game_rows=rows,team_game_rows=team_rows,unattributed_events=unattributed,
        definition='Official source receiver target with 0 <= air_yards - yardline_100 <= 10; longitudinal endpoint view at provider precision, goal/back boundary included',
        source_event_sha256=evidence['sha256'],identity_review_requests=deepcopy(evidence['identity_review_requests']),
        native_attachment_unknown_rows=[dict(game_id=r['game_id'],team=r['team'],source_player_id=r['source_player_id']) for r in rows if r['player_master_id'] is None])
    return basis|dict(semantic_sha256=digest(basis),source=deepcopy(evidence['source']),evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,
        forecast=None,model_consumed=False,optimizer_consumed=False,limitations=['No lateral coordinate or independent charted in-bounds/catching legality','Absent actor rows are not certified zero targets','Unknown source eligibility/coordinates/native attribution retained, no forced assignment'])


def derive_retrospective_endzone_targets(parent_ref,snapshot,*,actual_read_at,directory=None):
    from datetime import datetime,UTC
    from pathlib import Path
    import hashlib
    from .factual_designation import clock
    from .opportunity_source_capture import load_event_artifact
    original,actual,lock=(clock(v) for v in (parent_ref['decision_cutoff_at'],actual_read_at,snapshot.slate_lock_at))
    if None in (original,actual,lock) or not original<lock<=actual<=datetime.now(UTC):raise ValueError('Explicit retrospective source boundary required')
    parent=load_event_artifact(parent_ref,snapshot,before_period=parent_ref['before_period'],cutoff=original,directory=directory)
    result=build_endzone_target_components(parent['event_evidence'],before_period=parent_ref['before_period'],cutoff=actual)
    result['provenance']=dict(parent_ref=deepcopy(parent_ref),original_evidence_boundary_at=original.isoformat(),source_lock_at=lock.isoformat(),actual_read_at=actual.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return result


def require_feature_use(value,*,purpose):
    if value.get('version')!=VERSION or purpose!='offline_descriptive' or value.get('pregame_serving_eligible') is not False:raise ValueError('Source depth targets cannot serve forecasts/models/optimizer')
    return value
