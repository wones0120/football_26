"""Source-wide first-fumble anchors and observed official before/after exposure."""
from collections import defaultdict
from copy import deepcopy
import math,re
from uuid import UUID
from .opportunity_events import validate_event_evidence,CHANNELS
from .fumble_event_components import VERSION as FUMBLE_VERSION
from .market_snapshots import canonical_team
from .evaluation_record import digest

VERSION='sourcewide_post_fumble_workload_v1'
NATIVE=re.compile(r'00-\d{7}')

def qualified_identity(edges):
    """Withhold every node touched by a multi-native/multi-UUID graph component."""
    forward=defaultdict(set);reverse=defaultdict(set)
    for native,pid in edges:
        if not isinstance(native,str) or not NATIVE.fullmatch(native):raise ValueError('Native GSIS identity required')
        if pid is not None:
            canonical=str(UUID(str(pid)))
            if canonical!=str(pid):raise ValueError('Canonical UUID spelling required')
            forward[native].add(canonical);reverse[canonical].add(native)
        else:forward[native]
    bad={n for n,ps in forward.items()if len(ps)!=1};badp={p for p,ns in reverse.items()if len(ns)!=1}
    while True:
        ns=bad|{n for p in badp for n in reverse[p]};ps=badp|{p for n in ns for p in forward[n]}
        if ns==bad and ps==badp:break
        bad,badp=ns,ps
    return {n:next(iter(ps))if n not in bad else None for n,ps in forward.items()}


def build_sourcewide_post_fumble(event_receipt,order_map,fumbles,*,fumble_source_sha256,identity_edges,before_period,cutoff,uncertain_official_rows=()):
    evidence=validate_event_evidence(event_receipt,before_period=before_period,cutoff=cutoff)
    if fumbles.get('version')!=FUMBLE_VERSION or fumbles['before_period']!=before_period:raise ValueError('Matched source-wide fumble evidence required')
    if fumble_source_sha256!=evidence['source']['content_sha256'] or order_map.get('source_byte_sha256')!=fumble_source_sha256 or order_map.get('event_receipt_sha256')!=evidence['sha256']:raise ValueError('Same immutable source/event receipt required')
    if order_map.get('version')!='validated_native_order_map_v1' or order_map['before_period']!=before_period:raise ValueError('Native complete timeline required')
    core={k:order_map[k]for k in('version','before_period','rows','unknown_order_games')}
    if digest(core)!=order_map['semantic_sha256']:raise ValueError('Native order semantic differs')
    orders={};bygame=defaultdict(list);badgames=set(order_map['unknown_order_games']);seen_order=set()
    for r in order_map['rows']:
        key=(r['game_id'],str(int(r['play_id'])));n=r['order_sequence']
        if key in orders:raise ValueError('Unique native play order required')
        if r['native_order_verified']:
            if type(n)not in(int,float)or not math.isfinite(n)or(r['game_id'],n)in seen_order:raise ValueError('Unique finite provider order required')
            seen_order.add((r['game_id'],n))
        else:badgames.add(r['game_id'])
        orders[key]=n
    source_basis={(r['game_id'],str(r['play_id'])):r for r in fumbles['event_basis']}
    if len(source_basis)!=len(fumbles['event_basis'])or set(source_basis)!=set(orders):raise ValueError('Complete original-row fumble/order key parity required')
    ledger={(r['game_id'],str(r['play_id'])):r for r in fumbles['fumble_ledger']}
    if len(ledger)!=len(fumbles['fumble_ledger'])or not set(ledger)<=set(orders):raise ValueError('Unique source fumble ledger required')
    potential={r['native_id']for l in ledger.values()for r in l['reported_fumblers']if isinstance(r['native_id'],str)and NATIVE.fullmatch(r['native_id'])}
    identities=qualified_identity(list(identity_edges)+[(r['source_player_id'],r['player_master_id'])for r in evidence['players']]+[(n,None)for n in potential])
    observed=set();native_events=[]
    for e in evidence['events']:
        key=(e['game_id'],str(e['play_id']))
        if key not in orders:raise ValueError('Official event absent from original timeline')
        bygame[e['game_id']].append(e)
        for o in e['opportunities']:
            if o.get('source_player_id'):observed.add((e['game_id'],e['team'],str(o['source_player_id'])))
        native_events.append(dict(game_id=e['game_id'],play_id=e['play_id'],team=e['team'],source_order=orders[key],unknown_channels=deepcopy(e['unknown_channels']),opportunities=deepcopy(e['opportunities'])))
    event_keys={(e['game_id'],str(e['play_id']))for e in evidence['events']}
    uncertain_by_game=defaultdict(list)
    for r in uncertain_official_rows:
        key=(r['game_id'],str(r['play_id']))
        if key not in orders or key in event_keys:raise ValueError('Possible unscoped official row must be a separate complete-timeline row')
        uncertain_by_game[r['game_id']].append(r)
    known=defaultdict(list);possible=defaultdict(list);excluded=[];actors=set()
    for key,b in source_basis.items():
        if b['fumble_play']is False:continue
        l=ledger.get(key);reported=l['reported_fumblers']if l else []
        entry=dict(game_id=key[0],play_id=key[1],source_order=orders[key],eligible=b['eligible'],fumble_play=b['fumble_play'],reported_fumblers=deepcopy(reported))
        if b['eligible']is False:excluded.append(entry);continue
        slots=reported or[dict(native_id=None,team=None,slot=None)]
        for slot in slots:
            native=slot['native_id'];team=slot['team'];pair={canonical_team(t)for t in key[0].split('_')[2:]}
            if team is not None and team not in pair:raise ValueError('Native fumbler team differs from game')
            valid=isinstance(native,str)and NATIVE.fullmatch(native)is not None
            if valid and team:actors.add((key[0],team,native))
            fact=dict(entry,reported_slot=slot['slot'],native_id=native,team=team)
            if b['eligible']is True and b['fumble_play']is True and valid and team:known[(key[0],team,native)].append(fact)
            else:possible[key[0]].append(fact)
    rows=[];requests=[]
    for gid,team,native in sorted(actors):
        matches=known[(gid,team,native)];anchor=min(matches,key=lambda a:a['source_order'])if matches and gid not in badgames else None
        threats=[r for r in possible[gid]if(r['team']is None or r['team']==team)and(r['native_id']is None or not isinstance(r['native_id'],str)or not NATIVE.fullmatch(r['native_id'])or r['native_id']==native)and(anchor is None or r['source_order']is None or r['source_order']<anchor['source_order'])]
        exact_anchor=anchor is not None and not threats;has_usage=(gid,team,native)in observed;team_log=any(e['team']==team for e in bygame[gid]);metrics={}
        for channel in CHANNELS:
            sides={}
            for label in('before','after'):
                total=count=unknown_eligibility=unattributed=0
                if anchor is not None:
                    for e in bygame[gid]:
                        if e['team']!=team:continue
                        n=orders[(gid,str(e['play_id']))]
                        if n is None or not(n<anchor['source_order']if label=='before'else n>anchor['source_order']):continue
                        unknown_eligibility+=channel in e['unknown_channels']
                        for o in e['opportunities']:
                            if o['channel']!=channel:continue
                            total+=1;actor=o.get('source_player_id');unattributed+=actor is None;count+=str(actor)==native
                for r in uncertain_by_game[gid]:
                        n=orders[(gid,str(r['play_id']))]
                        if team in r['possible_teams'] and channel in r['possible_channels'] and(n is None or(n<anchor['source_order']if label=='before'else n>anchor['source_order'])):unknown_eligibility+=1
                exact=exact_anchor and has_usage and team_log and not(unknown_eligibility or unattributed)
                sides[label]=dict(known_actor_count=count,known_team_count=total,unknown_eligibility=unknown_eligibility,unattributed=unattributed,exact_actor_count=count if exact else None,exact_team_count=total if exact_anchor and team_log and not unknown_eligibility else None,exact_share=count/total if exact and total else None)
            a,b=sides['before']['exact_share'],sides['after']['exact_share'];metrics[channel]=dict(**sides,after_minus_before=b-a if a is not None and b is not None else None)
        pid=identities.get(native);row=dict(game_id=gid,team=team,source_player_id=native,player_master_id=pid,first_certified_anchor=anchor,exact_first_anchor=exact_anchor,canonical_feature_eligible=pid is not None and exact_anchor and has_usage,possible_earlier_anchor_evidence=threats,observed_official_usage=has_usage,observed_official_team_log=team_log,metrics=metrics);rows.append(row)
        if pid is None:requests.append(dict(game_id=gid,team=team,source_player_id=native,reason='Source-wide native fumbler lacks unique attachment in frozen global graph'))
    requested={(q['game_id'],q['team'],q['source_player_id'])for q in requests}
    for (gid,play),event in ledger.items():
        for actor in event['reported_fumblers']:
            native,team=actor['native_id'],actor['team'];key=(gid,team,native)
            if native in potential and identities.get(native)is None and key not in requested:
                requested.add(key);requests.append(dict(game_id=gid,team=team,source_player_id=native,reason='Potential source fumbler lacks unique attachment; unknown source team retained'))
    core=dict(version=VERSION,candidate_id='G22-M10',before_period=before_period,rows=rows,possible_anchor_evidence=[r for group in possible.values()for r in group],excluded_anchor_evidence=excluded,official_channel_event_basis=native_events,unknown_order_games=sorted(badgames),potential_native_fumbler_ids=sorted(potential),uncertain_official_rows=deepcopy(list(uncertain_official_rows)),identity_qualification=identities,identity_review_requests=requests)
    return dict(**core,semantic_sha256=digest(core),source_event_sha256=evidence['sha256'],source_sha256=fumble_source_sha256,pregame_serving_eligible=False,forecast=None,model_consumed=False,optimizer_consumed=False,definition='First source-proven live fumble by native actor on any original source row; all compatible earlier uncertain anchors block exactness; anchor excluded from same-game official before/after exposure; no official usage remains undefined',limitations=['Observed source universe, not independently complete NFL game','Fumble/recovery slot numbers never paired','No punishment, coaching causality, health, recovery opportunity or future role inference'])


def persist_sourcewide_identity_requests(connection,features,*,artifact_ref):
    from pathlib import Path
    import json,hashlib
    from sqlalchemy import text
    p=Path(artifact_ref['path']).resolve()
    if p.parent!=Path('artifacts/sourcewide_post_fumble_workload').resolve()or p.name!=artifact_ref['sha256']+'.json'or not 0<artifact_ref['bytes']<=64*1024*1024:raise ValueError('Managed bounded source-wide fumble evidence required')
    b=p.read_bytes()
    if len(b)!=artifact_ref['bytes']or hashlib.sha256(b).hexdigest()!=artifact_ref['sha256']or json.loads(b)!=features:raise ValueError('Immutable source-wide identity evidence differs')
    if features.get('version')!=VERSION or features.get('pregame_serving_eligible')is not False or features.get('model_consumed')is not False:raise ValueError('Offline source-wide evidence only')
    records=[]
    for q in features['identity_review_requests']:
        native=q['source_player_id']
        if native not in features['potential_native_fumbler_ids']or features['identity_qualification'].get(native)is not None:raise ValueError('Unresolved potential native fumbler proof required')
        key='sourcewide-fumble:'+features['source_event_sha256']+':'+q['game_id']+':'+str(q['team'])+':'+native
        qid='sourcewide-fumble:'+hashlib.sha256(key.encode()).hexdigest()[:32];year,week=map(int,q['game_id'].split('_')[:2])
        connection.execute(text('''INSERT INTO target.identity_quarantine
        (identity_quarantine_id,entity_type,source_schema,source_table,source_record_key,source_system,season,week,slate,source_player_key,display_name,team_id,position,reason_code,candidate_player_ids,status,first_seen_at,updated_at)
        VALUES (:qid,'player','public','source_snapshot',:key,'nflreadpy',:season,:week,'FEATURE_INVENTORY',:native,NULL,:team,NULL,'sourcewide_fumbler_attachment_missing_in_frozen_evidence','[]'::jsonb,'open',now(),now())
        ON CONFLICT (source_schema,source_table,source_record_key) DO NOTHING'''),dict(qid=qid,key=key,season=year,week=week,native=native,team=q['team']))
        records.append(dict(identity_quarantine_id=qid,source_record_key=key,source_player_key=native,team=q['team']))
    return dict(records=records,requests=len(records),aliases_changed=False,resolved_cases_reopened=False)
