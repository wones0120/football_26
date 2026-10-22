"""Dated practice/game facts from retained official final-report bodies.

No retrieval-clock practice dates, source downloads, forecast or live context
writes. Identity uses persisted native aliases or exact team/position-family
and normalized name matching, never an unscoped display-name join.
"""
from copy import deepcopy
from datetime import timedelta
import json,re
from pathlib import Path
from zoneinfo import ZoneInfo
from Database.player_identity import normalize_player_name,normalize_position
from .evaluation_record import digest
from .factual_designation import clock
from .final_injury_report import parse_final_report
from .official_injuries import _Document,resolve_official_player
from ..services.source_capture import verify_snapshot_artifact

VERSION='official_role_report_features_v1'
DAYS=['monday','tuesday','wednesday','thursday','friday','saturday','sunday']
PRACTICE={'FULL':'FP','LIMITED':'LP','DNP':'DNP','DID NOT PARTICIPATE':'DNP','DID NOT PARTICIPATE IN PRACTICE':'DNP'}


def _position_family(value):
    p=normalize_position(value)
    if '/' in p:
        families={_position_family(part) for part in p.split('/') if part}
        if len(families)==1:return next(iter(families))
    if p in {'C','OC','G','OG','T','OT','OL','LT','RT','LG','RG'}:return 'OL'
    if p in {'CB','S','FS','SS','DB','LCB','RCB','NB'}:return 'DB'
    if p in {'DT','DE','NT','DL'}:return 'DL'
    if p in {'LB','ILB','OLB','MLB'}:return 'LB'
    return p


def parse_dated_practice_rows(body,**scope):
    """Final-report validation supplies exact game/week and finalness first."""
    parsed=parse_final_report(body,**scope)
    kickoff=clock(scope['kickoff_at']).astimezone(ZoneInfo('America/New_York'))
    final_date=kickoff.date()-timedelta(days=1 if kickoff.weekday()==3 else 2)
    result=[]
    for table in _Document(body).root.find('table'):
        headers=[n.content().strip().lower().replace('satruday','saturday') for n in table.find('th')]
        if len(headers)!=6 or headers[:2]!=['player','injury'] or headers[-1] not in {'status','game status'}:continue
        names=headers[2:5]
        if any(day not in DAYS for day in names) or names[-1]!=DAYS[final_date.weekday()]:continue
        dates=[final_date-timedelta(days=(final_date.weekday()-DAYS.index(day))%7) for day in names]
        if dates!=sorted(set(dates)) or (dates[-1]-dates[0]).days>6:raise ValueError('Practice table days are not an ordered game-week sequence')
        for tr in table.find('tr'):
            cells=[n.content().strip() for n in tr.find('td')]
            if not cells:continue
            match=re.fullmatch(r'(QB|RB|WR|TE|K|[A-Z/]+)\s+(.+)',cells[0]) if len(cells)==6 else None
            if not match:raise ValueError('Invalid scoped practice row identity')
            position,name=match.groups();key=scope['source_uri']+'#'+position+'-'+normalize_player_name(name)
            result.append(dict(player_name=name,position=position,team=scope['team'],source_key=key,
                practices=[dict(practice_date=day.isoformat(),practice_status=PRACTICE.get(status.upper()),raw_participation=status) for day,status in zip(dates,cells[2:5])]))
    if len(result)!=len({r['source_key'] for r in result}) or len(result)!=len(parsed['rows']) or {r['source_key'] for r in result}!={r['source_key'] for r in parsed['rows']}:raise ValueError('Practice rows differ from validated final report')
    return parsed,result


def extract_official_role_report(snapshot,canonical_roster,aliases,*,cutoff):
    if snapshot.dataset!='official_final_game_report':raise ValueError('Official final-report snapshot required')
    if clock(snapshot.observed_at)>clock(snapshot.captured_at) or clock(snapshot.captured_at)>clock(cutoff):raise ValueError('Official role report unavailable at cutoff')
    verify_snapshot_artifact(snapshot)
    if snapshot.byte_count>4*1024*1024:raise ValueError('Official role source exceeds bounded artifact size')
    envelope=json.loads(Path(snapshot.artifact_path).read_text());meta=snapshot.metadata_json
    if envelope['source_uri']!=snapshot.source_uri or clock(envelope['received_at'])>clock(snapshot.captured_at) or clock(envelope['observed_at'])>clock(envelope['received_at']):raise ValueError('Official report source envelope clocks or URI differ')
    scope=dict(source_uri=snapshot.source_uri,season=snapshot.season,week=snapshot.week,team=meta['team'],opponent=meta['opponent'],kickoff_at=meta['kickoff_at'],observed_at=envelope['observed_at'])
    parsed,rows=parse_dated_practice_rows(envelope['body'],**scope)
    if parsed!={k:v for k,v in envelope['parsed'].items()}:raise ValueError('Retained parsed report differs from immutable body')
    # The family permits official T versus roster OT, or official CB versus
    # roster DB. It never supplies a different team's names as candidates.
    candidates=[dict(player_id=r['player_master_id'],team=r['team'],position=_position_family(r['position']),player_name=r.get('player_name') or r.get('source_player_name') or '',full_name=r.get('player_name') or r.get('source_player_name') or '') for r in canonical_roster]
    by_id={r['player_master_id']:r for r in canonical_roster};facts=[];requests=[];resolutions=[]
    final_by_key={r['source_key']:r for r in parsed['rows']}
    for row in rows:
        target=dict(row,position=_position_family(row['position']))
        pid,method=resolve_official_player(target,candidates,aliases)
        if pid is None:
            requests.append(dict(source_key=row['source_key'],team=row['team'],position=row['position'],player_name=row['player_name'],reason=method));continue
        actor=by_id[pid];resolutions.append(dict(source_key=row['source_key'],player_master_id=pid,method=method,player_name=row['player_name'],team=row['team'],position=row['position'],source_position=row['position'],roster_position=actor['position']))
        base=dict(player_id=pid,team=row['team'],position=actor['position'],source_position=row['position'],season=snapshot.season,week=snapshot.week,
            source='retained_official_final_report',source_ids=[snapshot.snapshot_id,row['source_key']],source_uri=snapshot.source_uri,
            observed_at=clock(envelope['observed_at']).isoformat(),received_at=clock(envelope['received_at']).isoformat(),published_at=parsed['published_at'],modified_at=parsed['modified_at'])
        facts.append(dict(base,kind='game_status',status=final_by_key[row['source_key']]['game_status'],**{k:parsed[k] for k in ('report_contract','report_phase','scope_verified','kickoff_at')}))
        for practice in row['practices']:
            facts.append(dict(base,kind='practice',**practice,practice_date_basis='Authored weekday table labels within validated final game-week calendar, not retrieval time'))
    semantic=dict(version=VERSION,season=snapshot.season,week=snapshot.week,facts=sorted([{k:v for k,v in f.items() if k not in {'source_ids','observed_at','received_at'}} for f in facts],key=digest),identity_review_requests=requests)
    return dict(version=VERSION,season=snapshot.season,week=snapshot.week,slate=str(snapshot.slate or '').upper(),team=scope['team'],facts=facts,identity_review_requests=requests,identity_resolution_actions=resolutions,semantic_measurements_sha256=digest(semantic),forecast=False,model_consumed=False,optimizer_consumed=False,
        source_quality=dict(practice_date_definition='Dates derived from official authored day labels and validated game calendar; original day-of-publication availability remains unproven',queue_persistence='Caller must persist resolutions/review requests using existing identity workflow'),
        provenance=dict(original_snapshot_id=snapshot.snapshot_id,source_sha256=snapshot.content_sha256,source_observed_at=str(snapshot.observed_at),source_received_at=str(snapshot.captured_at),decision_cutoff_at=str(cutoff)))


def persist_official_role_identities(connection,receipt):
    """Existing idempotent alias/quarantine workflow, in caller transaction."""
    from .official_injuries import _record_identity
    if receipt.get('version')!=VERSION or not receipt.get('slate') or not 1<=int(receipt.get('week',0))<=18:
        raise ValueError('Official role identity receipt scope required')
    scope=dict(season=receipt['season'],week=receipt['week'],slate=receipt['slate'])
    resolved=0;review=0
    for row in receipt['identity_resolution_actions']:
        if row['team']!=receipt['team']:raise ValueError('Official identity team scope differs')
        if _record_identity(connection,row,row['player_master_id'],row['method'],**scope):resolved+=1
        else:review+=1
    for row in receipt['identity_review_requests']:
        if row['team']!=receipt['team']:raise ValueError('Official identity team scope differs')
        _record_identity(connection,row,None,row['reason'],**scope);review+=1
    return dict(status='persisted' if not review else 'requires_identity_review',resolved=resolved,review=review,
        workflow='Existing official injury alias and identity_quarantine; no raw fact/projection writes')
