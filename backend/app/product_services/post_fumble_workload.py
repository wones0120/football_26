"""Observed same-game opportunity share before/after a known native fumble.

No benching, discipline or future-role forecast is inferred.
"""
from collections import defaultdict
from copy import deepcopy
from .opportunity_events import validate_event_evidence,_flag,CHANNELS
from .evaluation_record import digest
from .market_snapshots import canonical_team

VERSION='native_order_post_fumble_workload_v1'


def build_post_fumble_workload(event_receipt,order_map,*,before_period,cutoff):
    evidence=validate_event_evidence(event_receipt,before_period=before_period,cutoff=cutoff)
    if order_map.get('version')!='validated_native_order_map_v1' or order_map.get('before_period')!=before_period:
        raise ValueError('Matching validated native timeline required')
    if (order_map.get('source_snapshot_id')!=evidence['source']['snapshot_id'] or order_map.get('source_byte_sha256')!=evidence['source']['content_sha256'] or order_map.get('event_receipt_sha256')!=evidence['sha256']):
        raise ValueError('Native timeline/event source differs')
    basis={k:order_map[k] for k in ('version','before_period','rows','unknown_order_games')}
    if order_map.get('semantic_sha256')!=digest(basis):raise ValueError('Native order map checksum differs')
    order={};seen_orders=set()
    for r in order_map['rows']:
        key=(r['game_id'],str(int(r['play_id'])))
        if key in order:raise ValueError('Duplicate native timeline event')
        if r['native_order_verified']:
            n=r['order_sequence']
            if type(n) not in (int,float) or (r['game_id'],n) in seen_orders:raise ValueError('Unique finite native order required')
            import math
            if not math.isfinite(n):raise ValueError('Unique finite native order required')
            seen_orders.add((r['game_id'],n))
        order[key]=r
    identities={};bygame=defaultdict(list);anchors={};unknown=[]
    for r in evidence['players']:
        key=(r['game_id'],canonical_team(r['team']),r['source_player_id']);pid=r['player_master_id']
        if key in identities and identities[key]!=pid:raise ValueError('Native fumbler identity contradicts source')
        identities[key]=pid
    for e in evidence['events']:
        key=(e['game_id'],e['play_id']);proof=order.get(key)
        if proof is None:raise ValueError('Event missing native timeline proof')
        if not proof['native_order_verified']:
            unknown.append(dict(game_id=e['game_id'],play_id=e['play_id'],reason='Native game order uncertain'));continue
        bygame[e['game_id']].append((proof['order_sequence'],e))
        raw=e['raw_flags']
        if _flag(raw.get('fumble')) is not True:continue
        # This package certifies official offensive-event anchors only. Controls/returns stay a source-scope gap.
        if e['status'] not in {'counted','partial'}:
            unknown.append(dict(game_id=e['game_id'],play_id=e['play_id'],reason='Fumble official-event eligibility unknown or excluded'));continue
        found=False
        for index in (1,2):
            native=raw.get(f'fumbled_{index}_player_id')
            try:team=canonical_team(raw.get(f'fumbled_{index}_team'))
            except (ValueError,TypeError,AttributeError):team=None
            if not native:continue
            found=True;parts=e['game_id'].split('_')
            if not team or team not in {canonical_team(x) for x in parts[2:]}:
                unknown.append(dict(game_id=e['game_id'],play_id=e['play_id'],source_player_id=native,reason='Native fumbler team scope unknown'));continue
            actor=(e['game_id'],team,str(native));value=dict(game_id=e['game_id'],team=team,source_player_id=str(native),player_master_id=identities.get(actor),anchor_play_id=e['play_id'],anchor_order_sequence=proof['order_sequence'])
            if actor not in anchors or proof['order_sequence']<anchors[actor]['anchor_order_sequence']:anchors[actor]=value
        if not found:unknown.append(dict(game_id=e['game_id'],play_id=e['play_id'],reason='Known fumble native actor absent'))
    rows=[];requests=[]
    for actor,anchor in sorted(anchors.items()):
        metrics={}
        for channel in CHANNELS:
            sides={}
            for label,predicate in (('before',lambda n:n<anchor['anchor_order_sequence']),('after',lambda n:n>anchor['anchor_order_sequence'])):
                events=[e for n,e in bygame[anchor['game_id']] if predicate(n) and canonical_team(e['team'])==anchor['team']]
                team_count=actor_count=unknown_eligibility=unknown_actor=0
                for e in events:
                    unknown_eligibility+=channel in e['unknown_channels']
                    for o in e['opportunities']:
                        if o['channel']!=channel:continue
                        team_count+=1
                        native=o.get('source_player_id')
                        if native is None:unknown_actor+=1
                        elif str(native)==anchor['source_player_id']:actor_count+=1
                sides[label]=dict(known_actor_opportunities=actor_count,known_team_opportunities=team_count,unknown_team_eligibility_events=unknown_eligibility,unknown_actor_attribution_events=unknown_actor,
                    exact_actor_count=actor_count if not(unknown_eligibility or unknown_actor) else None,
                    exact_share=actor_count/team_count if team_count and not(unknown_eligibility or unknown_actor) else None)
            a,b=sides['before']['exact_share'],sides['after']['exact_share']
            metrics[channel]=sides|dict(after_minus_before=b-a if a is not None and b is not None else None,unit='fraction_of_same_team_official_channel_opportunities')
        rows.append(anchor|dict(metrics=metrics))
        if anchor['player_master_id'] is None:requests.append({**anchor,'reason':'Native fumbler lacks canonical attachment in verified event source'})
    facts=dict(version=VERSION,candidate_id='G22-M10',before_period=before_period,definition='Same-game team channel opportunity share after-minus-before first known official offensive-event fumble by native actor; anchor play excluded',rows=rows,unknown_anchor_evidence=unknown)
    return facts|dict(semantic_sha256=digest(facts),identity_review_requests=requests,source_event_sha256=evidence['sha256'],native_order_semantic_sha256=order_map['semantic_sha256'],
        evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None,model_consumed=False,optimizer_consumed=False,
        limitations=['Known official offensive-event fumbles only; special-team/defensive-return/control-row anchors are not certified by this scoped variant',
            'First known fumble per native actor/game is anchored by provider order, not numeric play ID; anchor play excluded from both sides',
            'Same-game observed count share is not benching/discipline causality or next-game opportunity/participation forecast',
            'Zero before/after denominator stays undefined; missing eligibility/native attribution remains unknown, not no usage'])


def derive_retrospective_post_fumble(parent_ref,snapshot,*,actual_read_at,directory=None):
    from datetime import datetime,UTC
    from pathlib import Path
    import hashlib
    from .factual_designation import clock
    from .opportunity_source_capture import load_event_artifact
    from .game_clock_pace_catalog import validated_native_order_map
    original,actual,lock=(clock(v) for v in (parent_ref['decision_cutoff_at'],actual_read_at,snapshot.slate_lock_at))
    if None in (original,actual,lock) or not original<lock<=actual<=datetime.now(UTC):raise ValueError('Explicit nonfuture postlock retrospective boundary required')
    parent=load_event_artifact(parent_ref,snapshot,before_period=parent_ref['before_period'],cutoff=original,directory=directory)
    order=validated_native_order_map(parent,before_period=parent_ref['before_period'],cutoff=actual)
    result=build_post_fumble_workload(parent['event_evidence'],order,before_period=parent_ref['before_period'],cutoff=actual)
    result['provenance']=dict(parent_artifact_ref=deepcopy(parent_ref),source=deepcopy(parent['event_evidence']['source']),
        producer_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),actual_read_at=actual.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),
        original_evidence_boundary_at=original.isoformat(),source_lock_at=lock.isoformat(),original_historical_availability='Unknown revised source; not historical pregame evidence')
    return result


def require_feature_use(block,*,purpose):
    if block.get('version')!=VERSION or purpose!='offline_descriptive' or block.get('pregame_serving_eligible') is not False:
        raise ValueError('Post-fumble descriptive usage cannot serve models/forecasts/optimizer')
    return block
