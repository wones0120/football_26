"""Ordinary gamebook Not Active evidence; never infer absence from missing stats."""
from copy import deepcopy
from datetime import datetime,UTC
import hashlib,re
from uuid import UUID
from pypdf import PdfReader
from io import BytesIO
from Database.player_identity import normalize_player_name
from .gamebook_weather import parse_gamebook_temperature
from .market_snapshots import canonical_team
from .factual_designation import clock
from .player_role_features import KNOWN_POSITIONS
from .weekly_effectiveness_catalog_features import VERSION as WEEKLY_VERSION
from .official_role_report_features import _position_family

VERSION='official_gamebook_absence_source_v1'


def absence_layout(payload):
    if not isinstance(payload,bytes) or not 0<len(payload)<=16*1024*1024 or not payload.startswith(b'%PDF-'):
        raise ValueError('Bounded original PDF bytes required')
    reader=PdfReader(BytesIO(payload))
    if not 1<=len(reader.pages)<=100:raise ValueError('Bounded source page count required')
    layout=reader.pages[0].extract_text(extraction_mode='layout')
    if not layout or len(layout)>100000:raise ValueError('Bounded first-page layout required')
    return layout


def parse_absence_layout(layout,game,*,source_sha256):
    header=parse_gamebook_temperature(layout)  # Missing weather does not reject the document header.
    if (game.get('game_type')!='REG' or header['game_date']!=str(game['game_date'])[:10]
            or (header['away_team'],header['home_team'])!=(game['away_team'],game['home_team'])
            or str(game['game_id']).split('_')[:2]!=[str(game['season']),f"{game['week']:02}"]
            or not re.fullmatch(r'[0-9a-f]{64}',source_sha256)):
        raise ValueError('Native gamebook date/team/period binding differs')
    lines=layout.splitlines();markers=[]
    for i,line in enumerate(lines):
        found=list(re.finditer(r'\bNot Active\b',line))
        if found:markers.append((i,found))
    if len(markers)!=1 or len(markers[0][1])!=2:raise ValueError('Two explicit source inactive columns required')
    start,labels=markers[0]
    split=round(sum((m.start()+m.end())/2 for m in labels)/2)
    if labels[0].end()>=split or labels[1].start()<=split:raise ValueError('Source column gutter ambiguous')
    end=[i for i in range(start+1,len(lines)) if 'Field Goals' in lines[i]]
    if len(end)!=1:raise ValueError('Explicit following source-section boundary required')
    did=[(i,list(re.finditer(r'\bDid Not Play\b',line))) for i,line in enumerate(lines[:start]) if 'Did Not Play' in line]
    sections=[('NOT_ACTIVE',start+1,end[0])]
    if did:
        if len(did)!=1 or len(did[0][1])!=2:raise ValueError('DidNotPlay source columns ambiguous')
        sections.append(('DID_NOT_PLAY',did[0][0]+1,start))
    rows=[]
    for domain,a,b in sections:
        for side,team in enumerate((game['away_team'],game['home_team'])):
            text=' '.join((line[:split] if side==0 else line[split:]).strip() for line in lines[a:b]).strip()
            if not text:continue  # Source-empty domain, not an inferred player status.
            for ordinal,entry in enumerate(text.split(',')):
                match=re.fullmatch(r'\s*(3QB|[A-Z]{1,4})\s+(\d{1,2})\s+([^,]+?)\s*',entry)
                if not match or match[1] not in KNOWN_POSITIONS|{'3QB','DB'}:
                    raise ValueError('Unparsed roster fragment; do not silently drop source names')
                role,jersey,name=match[1],int(match[2]),match[3]
                state='EMERGENCY_THIRD_QB_EXCEPTION' if role=='3QB' else domain
                rows.append(dict(source_row_key=f'{source_sha256}:page1:{domain}:{side}:{ordinal}',
                    source_status=state,ordinary_absence_anchor=state=='NOT_ACTIVE',
                    native_game_id=game['game_id'],season=game['season'],week=game['week'],team=team,
                    source_position=role,source_jersey_number=jersey,source_abbreviated_name=name,
                    source_sha256=source_sha256))
    keys={(r['team'],r['source_position'],r['source_jersey_number']) for r in rows}
    if len(keys)!=len(rows):raise ValueError('Duplicate or contradictory source player/status tuple')
    return dict(version=VERSION,native_game_id=game['game_id'],game_date=header['game_date'],rows=rows,
                column_split_basis='Midpoint of two source-centered labels; strict entire-entry parsing and following section required',
                no_name_only_identity_join=True,pregame_serving_eligible=False)


def _jersey(value):
    if value in (None,'') or isinstance(value,bool):return None
    try:n=float(value)
    except (ValueError,TypeError):return None
    return int(n) if 0<=n<=99 and n==int(n) else None


def _name_matches(short,full):
    a,b=normalize_player_name(short).split(),normalize_player_name(full).split()
    return bool(a and b and a[0][0]==b[0][0] and a[-1]==b[-1])


def resolve_absence_roster(parsed,roster,weekly,*,cutoff):
    decision=clock(cutoff)
    if decision is None or decision>datetime.now(UTC):raise ValueError('Actual nonfuture identity cutoff required')
    if (weekly.get('version')!=WEEKLY_VERSION or weekly.get('pregame_serving_eligible') is not False
            or clock(weekly.get('provenance',{}).get('actual_derived_at')) is None
            or clock(weekly['provenance']['actual_derived_at'])>decision):
        raise ValueError('Reviewed frozen canonical weekly source required')
    mappings={}
    for r in weekly['rows']:mappings.setdefault(r['source_player_id'],set()).add(r['player_master_id'])
    resolved=[];requests=[]
    for fact in parsed['rows']:
        candidates={};uncertain=[]
        family=_position_family('QB' if fact['source_position']=='3QB' else fact['source_position'])
        for r in roster:
            if (r['season'],r['week'])!=(fact['season'],fact['week']):raise ValueError('Exact source roster game-week required')
            if clock(r.get('imported_at')) is None or clock(r['imported_at'])>decision or not r.get('ingest_run_id') or r.get('source_id') is None:
                raise ValueError('Original roster source/ingest clock required')
            if canonical_team(r['team'])!=fact['team']:continue
            raw=r['raw_row_json']
            phases={str(x) for x in (r.get('game_type'),raw.get('game_type'),raw.get('season_type')) if x not in (None,'')}
            if phases and 'REG' not in phases:continue
            phase_unknown=not phases or phases!={'REG'}
            for field,expected in (('season',r['season']),('week',r['week'])):
                if raw.get(field) is not None and str(raw[field]) not in {str(expected),str(float(expected))}:
                    raise ValueError('Roster indexed/raw period differs')
            for field in ('gsis_id','player_id'):
                if raw.get(field) not in (None,'',r.get('gsis_id')):raise ValueError('Roster indexed/raw native identity differs')
            for field in ('team','recent_team'):
                if raw.get(field) not in (None,'') and canonical_team(raw[field])!=canonical_team(r['team']):
                    raise ValueError('Roster indexed/raw team differs')
            roles={_position_family(x) for x in (r.get('position'),raw.get('position'),raw.get('pos')) if x not in (None,'')}
            role=next(iter(roles)) if len(roles)==1 else None
            if role not in {'OL','DB','DL','LB','QB','RB','FB','WR','TE','K','P','LS'}:role=None
            jerseys=[_jersey(raw[k]) for k in ('jersey_number','jersey') if k in raw]
            jersey=jerseys[0] if jerseys and None not in jerseys and len(set(jerseys))==1 else None
            if role not in (family,None):continue
            if jersey is not None and jersey!=fact['source_jersey_number']:continue
            native=r.get('gsis_id')
            if (phase_unknown or role is None or jersey is None or not isinstance(native,str) or re.fullmatch(r'00-\d{7}',native) is None):
                uncertain.append(r['source_id']);continue
            candidates.setdefault(native,[]).append(r)
        native=next(iter(candidates)) if len(candidates)==1 and not uncertain else None
        proof=candidates.get(native,[]);ids=mappings.get(native,set());pid=next(iter(ids)) if len(ids)==1 and None not in ids else None
        # Abbreviation corroborates the unique native tuple; it never selects one candidate from a tie.
        names=[r.get('player_name') for r in proof]
        name_ok=bool(names) and all(_name_matches(fact['source_abbreviated_name'],n) for n in names)
        if pid is not None and str(UUID(str(pid)))!=pid:raise ValueError('Canonical UUID spelling required')
        if not name_ok:pid=None
        output=deepcopy(fact)|dict(source_native_gsis_id=native,player_master_id=pid,
            native_roster_source_ids=sorted(r['source_id'] for r in proof),
            native_candidate_gsis_ids=sorted(candidates),uncertain_roster_source_ids=sorted(uncertain),
            identity_basis='unique native game-week/team/jersey/position plus abbreviation corroboration and frozen native UUID evidence' if pid else None)
        resolved.append(output)
        if pid is None:requests.append(dict(source_record_key=fact['source_row_key'],source_player_id=native,
            team=fact['team'],season=fact['season'],week=fact['week'],
            reason='Unresolved/ambiguous native gamebook-to-roster or frozen canonical attachment',candidate_gsis_ids=sorted(candidates),
            uncertain_source_ids=sorted(uncertain)))
    return dict(**{k:v for k,v in parsed.items() if k!='rows'},rows=resolved,identity_review_requests=requests,
        evidence_use='postlock_descriptive_not_pregame_or_serving',forecast=None,model_or_optimizer_consumed=False)


def read_absence_roster_revision(engine,game,*,cutoff):
    """Read/freeze caller's exact week/team rows; never run roster ingestion."""
    from sqlalchemy import text
    decision=clock(cutoff)
    if decision is None or decision>datetime.now(UTC):raise ValueError('Actual nonfuture roster cutoff required')
    fields=['season','week','game_type','season_type','team','recent_team','position','pos','gsis_id','player_id',
            'jersey_number','jersey','full_name','first_name','last_name','football_name']
    with engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
        with connection.begin():
            rows=connection.execute(text('''SELECT raw_nfl_weekly_roster_id AS source_id,ingest_run_id,created_at AS imported_at,
                season,week,game_type,team,position,gsis_id,player_name,
                (SELECT COALESCE(jsonb_object_agg(f.key,f.value),'{}'::jsonb) FROM jsonb_each(r.raw_row_json::jsonb) f
                 WHERE f.key=ANY(CAST(:fields AS text[]))) AS raw_row_json
                FROM public.raw_nfl_weekly_roster r WHERE season=:season AND week=:week
                AND team=ANY(CAST(:teams AS text[])) AND source_system='nflreadpy'
                AND created_at AT TIME ZONE 'UTC'<=:cutoff ORDER BY raw_nfl_weekly_roster_id LIMIT 1001'''),
                dict(season=game['season'],week=game['week'],teams=[game['home_team'],game['away_team']],fields=fields,cutoff=decision)).mappings().all()
            if not rows or len(rows)>1000:raise ValueError('Bounded complete scoped roster projection required')
    return dict(contract='retained_weekly_roster_attachment_revision_v1',native_game_id=game['game_id'],
        actual_read_at=decision.isoformat(),source_fields=fields,source_origin='Actual current retained DB revision, not original HTTP or original game-time availability',
        rows=[dict(r,ingest_run_id=str(r['ingest_run_id']),imported_at=clock(r['imported_at']).isoformat()) for r in rows])


def persist_absence_identity_incidents(connection,features,*,source_refs):
    """Frozen attachment incidents, not assertions of current missing aliases."""
    import json
    from sqlalchemy import text
    if features.get('version')!=VERSION or not source_refs:raise ValueError('Bound frozen source incident scope required')
    records=[]
    for q in features['identity_review_requests']:
        scope=dict(source_record_key=q['source_record_key'],source_refs=source_refs)
        key='gamebook-absence-attachment:'+hashlib.sha256(json.dumps(scope,sort_keys=True).encode()).hexdigest()
        qid='gamebook-absence:'+hashlib.sha256(key.encode()).hexdigest()[:32]
        connection.execute(text('''INSERT INTO target.identity_quarantine
          (identity_quarantine_id,entity_type,source_schema,source_table,source_record_key,source_system,
           season,week,slate,source_player_key,display_name,team_id,position,reason_code,candidate_player_ids,status,first_seen_at,updated_at)
          VALUES (:qid,'player','public','source_snapshot',:key,'nfl_official_gamebook',:season,:week,'FEATURE_INVENTORY',
           :native,NULL,:team,NULL,'frozen_gamebook_native_attachment_unresolved',CAST('[]' AS jsonb),'open',now(),now())
          ON CONFLICT (source_schema,source_table,source_record_key) DO NOTHING'''),
          dict(qid=qid,key=key,season=q['season'],week=q['week'],native=q.get('source_player_id'),team=q['team']))
        records.append(dict(identity_quarantine_id=qid,source_record_key=key,source_refs=source_refs,
                            original_request=deepcopy(q),current_alias_missing_claim=False))
    return dict(records=records,requests=len(records),aliases_mutated=False,resolved_cases_reopened=False)
