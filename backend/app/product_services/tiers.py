"""Native NFL Tiers evidence and exact baseline research; no shared optimizer state."""
from __future__ import annotations
import csv
import hashlib
import heapq
import io
import json
import math
import re
from datetime import UTC, datetime
from itertools import product
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from Database.dst import normalize_team
from ..models import IngestRun, OperationalJob, UnresolvedPlayerQueue
from ..services.matching import find_player_master_id, upsert_alias
from . import preliminary_optimizer as snapshots

LEDGER = Path('artifacts/tiers_ledger')
CONTRACT = 'nfl_tiers_research_v1'
RULES = dict(version='nfl_tiers_supplied_rules_v1', one_per_native_tier=True, minimum_games=2,
    salary_cap=None, position_requirements=None, team_maximum=None, captain_multiplier=None,
    scoring='DK PPR: passing TD4, passing yards .04, INT-1; rush/receive TD6, yards .1, reception1; 300 pass/100 rush/100 receive bonus3; lost fumble-1; conversions2; return/offensive recovery TD6')
EXPORT = dict(enabled=False, reason='Check current saved-lineup research CSV readiness; native salary IDs supply the upload roster. No final entry clearance.')

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')

class PoolImport(Strict):
    season: int = Field(ge=2000, le=2200)
    week: int = Field(ge=1, le=25)
    slate: str = Field(default='SUNDAY_MAIN_TIERS', min_length=1, max_length=64)
    native_draft_group_id: str = Field(min_length=1, max_length=64)
    source_name: str = Field(min_length=1, max_length=200)
    source_reference: str = Field(min_length=1, max_length=1000)
    native_csv: str = Field(min_length=1, max_length=2_000_000)
    rules_text: str = Field(min_length=1, max_length=100_000)
    projection_snapshot_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')

class Optimize(Strict):
    pool_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    num_lineups: int = Field(default=1, ge=1, le=20)
    exclude_questionable: bool = True
    excluded_player_ids: list[str] = Field(default_factory=list, max_length=200)
    accept_baseline_research: bool = False


def clock(value):
    at = datetime.fromisoformat(str(value).replace('Z', '+00:00')) if not isinstance(value, datetime) else value
    if at.tzinfo is None: raise ValueError('Timezone-aware source clock required')
    return at.astimezone(UTC)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def save(value, directory=None):
    root = Path(directory) if directory is not None else LEDGER
    root.mkdir(parents=True, exist_ok=True)
    key = digest(value); record = {**value, 'sha256': key}
    try:
        with (root / (key + '.json')).open('x') as f: json.dump(record, f, indent=2, allow_nan=False)
    except FileExistsError:
        if load(key, directory) != record: raise ValueError('Immutable Tiers record conflict')
    return record


def load(key, directory=None):
    if not re.fullmatch(r'[0-9a-f]{64}', key): raise ValueError('Invalid Tiers record hash')
    path = (Path(directory) if directory is not None else LEDGER) / (key + '.json')
    if path.stat().st_size > 12_000_000: raise ValueError('Tiers record exceeds read limit')
    record = json.loads(path.read_text())
    if record.get('contract_id') != CONTRACT or digest({k:v for k,v in record.items() if k != 'sha256'}) != key:
        raise ValueError('Tiers content hash/contract mismatch')
    return record


def catalog(directory=None):
    root = Path(directory) if directory is not None else LEDGER
    rows=[]
    for path in sorted(root.glob('*.json'), key=lambda p:p.stat().st_mtime, reverse=True)[:100]:
        try:
            record=load(path.stem,directory)
            rows.append({k:record.get(k) for k in ('sha256','kind','season','week','slate','created_at','native_draft_group_id','tier_labels','lineup_count','projection_snapshot_sha256')})
        except (OSError,ValueError,KeyError): continue
    return rows


def projection_sources(session, season, week):
    """Discover existing explicit snapshots through saved operational receipts."""
    jobs=session.scalars(select(OperationalJob).where(OperationalJob.job_type=='preliminary_optimizer_run').order_by(OperationalJob.created_at.desc()).limit(100)).all()
    out=[]; seen=set()
    for job in jobs:
        req=job.request_json or {}; opt=req.get('optimizer') or {}; key=req.get('snapshot_sha256')
        if not key or key in seen or (opt.get('season'),opt.get('week'),str(opt.get('slate','')).upper())!=(season,week,'SUNDAY_MAIN'): continue
        seen.add(key)
        try:
            snap=snapshots.load_snapshot(key)
            out.append(dict(sha256=key,projection_run_id=snap['projection_run_id'],data_cutoff_at=snap['data_cutoff_at'],classification=snap['classification'],player_count=len(snap['pool'])))
        except (OSError,ValueError,KeyError): continue
        if len(out)>=10: break
    return out


def parse_csv(text):
    reader=csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
    if not reader.fieldnames or len(set(reader.fieldnames))!=len(reader.fieldnames):raise ValueError('Native Tiers CSV column names must be unique')
    rows=list(reader)
    required={'Position','Name','ID','Roster Position','Game Info','TeamAbbrev'}
    if not rows or len(rows)>500 or not required<=set(rows[0]): raise ValueError('Tiers CSV requires native ID, tier, position, name, team and Game Info columns (1–500 rows)')
    seen=set(); out=[]
    for r in rows:
        tier=r['Roster Position'].strip(); native=r['ID'].strip()
        if not re.fullmatch(r'T[1-9][0-9]*',tier): raise ValueError('Native Tiers labels must be T1, T2, …; Classic/Showdown pools are not Tiers')
        if not native.isascii() or not native.isdigit() or native in seen: raise ValueError('Native IDs must be numeric and unique')
        seen.add(native)
        match=re.fullmatch(r'([A-Z]{2,3})@([A-Z]{2,3}) (\d{2}/\d{2}/\d{4}) (\d{2}:\d{2}[AP]M) ET',r['Game Info'].strip())
        if not match: raise ValueError('Native Game Info must include away/home teams and scheduled Eastern kickoff')
        away,home,day,time=match.groups();away,home=normalize_team(away),normalize_team(home);team=normalize_team(r['TeamAbbrev'])
        if team not in {away,home}: raise ValueError('Player team does not match native game')
        kickoff=datetime.strptime(day+' '+time,'%m/%d/%Y %I:%M%p').replace(tzinfo=ZoneInfo('America/New_York')).astimezone(UTC)
        out.append(dict(source_player_id=native,name=r['Name'].strip(),tier=tier,team=team,position=r['Position'].strip().upper(),game_id=away+'@'+home,kickoff_at=kickoff.isoformat(),native_game_info=r['Game Info'],native_status=(r.get('Status') or '').strip().upper(),raw=r))
    labels=sorted({r['tier'] for r in out},key=lambda t:int(t[1:]))
    if labels!=['T'+str(i) for i in range(1,len(labels)+1)] or len(labels)<2: raise ValueError('Native tier labels must be contiguous from T1 with at least two tiers')
    if len({r['game_id'] for r in out})<2: raise ValueError('Tiers Game Set must include at least two games')
    return out,labels


def import_pool(request, session, *, directory=None, now=None, resolver=None, snapshot_loader=None):
    now=now or datetime.now(UTC); raw_rows,labels=parse_csv(request.native_csv)
    rules=' '.join(request.rules_text.lower().split())
    if 'one player from each tier' not in rules or 'at least 2 different nfl games' not in rules:
        raise ValueError('Supply the reviewed NFL Tiers rules declaring one player per tier and at least 2 different NFL games')
    root=Path(directory) if directory is not None else LEDGER
    req_sha=digest(dict(import_schema_version=2,payload=request.model_dump(mode='json')));receipt=root/'imports'/(req_sha+'.json')
    if receipt.exists(): return load(json.loads(receipt.read_text())['pool_sha256'],directory)
    snap=(snapshot_loader or snapshots.load_snapshot)(request.projection_snapshot_sha256)
    if (snap['scope']['season'],snap['scope']['week'],str(snap['scope']['slate']).upper(),snap['scope']['contest_format'])!=(request.season,request.week,'SUNDAY_MAIN','classic'):
        raise ValueError('Projection snapshot must match this season/week Sunday Main Classic DK-scoring source')
    if clock(snap['data_cutoff_at'])>now: raise ValueError('Projection source cutoff is in the future')
    schedule={frozenset(normalize_team(g[k]) for k in ('home_team','away_team')):g for g in snap['source_manifest']['games']}
    source={str(r['player_id']):r for r in snap['pool']};excluded=set(snap['assumption_manifest']['exclude_player_ids']);players=[];canon=set()
    for r in raw_rows:
        pair=frozenset(r['game_id'].split('@')); game=schedule.get(pair)
        if not game or clock(game['kickoff_at'])!=clock(r['kickoff_at']): raise ValueError('Native game/kickoff outside the frozen canonical schedule')
        pid,reason=(resolver(r) if resolver else find_player_master_id(session,'draftkings',r['source_player_id'],r['name'],r['team'],r['position']))
        if pid and pid in canon: raise ValueError('Duplicate canonical player in native Tiers pool')
        row=source.get(pid) if pid else None
        if pid: canon.add(pid)
        if row and (normalize_team(row.get('player_team',row.get('team')))!=r['team'] or row.get('position')!=r['position']): raise ValueError('Canonical projection team/position conflicts with native Tiers identity')
        if pid and not resolver: upsert_alias(session,pid,'draftkings',r['source_player_id'],r['name'],r['team'],r['position'],request.season,request.week)
        mean=row.get('projection') if row else None;p90=row.get('p90',row.get('predicted_p90')) if row else None
        if type(mean) not in (int,float) or not math.isfinite(mean):mean=None
        if type(p90) not in (int,float) or not math.isfinite(p90):p90=None
        blocks=[]
        if not pid:blocks.append('identity_unresolved')
        if row is None or mean is None:blocks.append('frozen_projection_missing')
        if pid in excluded:blocks.append('frozen_availability_or_role_unknown_exclusion')
        statuses={r['native_status'],*(str(row.get(k) or '').upper() for k in ('availability_status','injury_status','official_availability_status','roster_status'))} if row else {r['native_status']}
        if statuses&{'OUT','O','IR','INACTIVE','PUP','SUSPENDED','D','DOUBTFUL','CUT','DEV','RES'}:blocks.append('known_unavailable_or_doubtful')
        if row and (row.get('role_active') is False or row.get('role_rostered') is False):blocks.append('canonical_role_unavailable')
        from .workload_evidence import build_workload_evidence
        evidence_keys=('player_id','position','player_team','availability_status','injury_status','official_availability_status','roster_status','role_active','role_rostered','canonical_role','is_starting_qb','game_total_line','team_spread_line','team_implied_total','role_source','role_source_ids','role_observed_at','availability_source','availability_source_ids','availability_observed_at','salary_ingest_run_id','projection_run_id')
        # The original snapshot remains the full immutable evidence. Keep bounded
        # relevant lineage here rather than duplicating every Classic report.
        source_evidence={k:row.get(k) for k in evidence_keys} if row else None
        workload=build_workload_evidence(row,projection_run_id=snap['projection_run_id'],cutoff=snap['data_cutoff_at']) if row else None
        players.append({**r,'player_master_id':pid,'identity_reason':reason,'projection':mean,'p90':p90,'questionable':bool(statuses&{'Q','QUESTIONABLE'}),'reason_codes':blocks,'source_projection':source_evidence,'workload_evidence':workload,'projection_run_id':snap['projection_run_id']})
    source_dir=root/'raw'/req_sha;source_dir.mkdir(parents=True,exist_ok=True)
    for filename,text in [('native.csv',request.native_csv),('rules.txt',request.rules_text)]:
        path=source_dir/filename
        try:
            with path.open('x') as f:f.write(text)
        except FileExistsError:
            if path.read_text()!=text:raise ValueError('Immutable raw Tiers source conflict')
    handoff=None
    if snapshot_loader is None:
        from .analyst_preparation import load_snapshot_handoff
        saved=load_snapshot_handoff(request.projection_snapshot_sha256)
        if saved:handoff={k:saved.get(k) for k in ('status','checked_at','source_packet_sha256','checked_packet_sha256','compatibility_sha256')}
    run_id=str(uuid5(NAMESPACE_URL,CONTRACT+req_sha))
    normal={k:snap['normal_readiness'].get(k) for k in ('status','reason_codes','evaluated_at')}
    record=save(dict(contract_id=CONTRACT,kind='pool',season=request.season,week=request.week,slate=request.slate,native_draft_group_id=request.native_draft_group_id,created_at=now.isoformat(),tier_labels=labels,players=players,ingest_run_id=run_id,source_name=request.source_name,source_reference=request.source_reference,native_csv_sha256=hashlib.sha256(request.native_csv.encode()).hexdigest(),rules_text_sha256=hashlib.sha256(request.rules_text.encode()).hexdigest(),raw_directory=str(source_dir),rules=RULES,projection_snapshot_sha256=request.projection_snapshot_sha256,projection_source=dict(projection_run_id=snap['projection_run_id'],data_cutoff_at=snap['data_cutoff_at'],source_sha256=snap['source_sha256'],classification=snap['classification'],normal_readiness=normal,assumption_manifest_sha256=snap['assumption_manifest_sha256']),analyst_context=dict(usage='Read-only source context; Classic scenarios/preferences are not applied to Tiers',handoff=handoff),scoring_compatibility=dict(status='COMMON_DK_BASELINE_ONLY',unmodeled_components=['return_touchdowns','offensive_fumble_recovery_touchdowns'],limitation='Existing common DK PPR baseline is reused unchanged. Rare return/recovery TD forecasts are not verified; no exact full-scoring optimum or calibrated Tiers model is claimed.'),entry_ready=False,export=EXPORT),directory)
    if session is not None and resolver is None:
        if session.get(IngestRun,run_id) is None:
            session.add(IngestRun(ingest_run_id=run_id,source_system='draftkings',source_table='tiers_native_pool_v1',source_path=str(source_dir/'native.csv'),source_checksum=record['native_csv_sha256'],season=request.season,week=request.week,slate=request.slate,status='completed',rows_raw=len(players),rows_curated=len(canon),rows_unresolved=len(players)-len(canon),started_at=now.replace(tzinfo=None),completed_at=now.replace(tzinfo=None)));session.flush()
            for r in players:
                if not r['player_master_id']:
                    session.add(UnresolvedPlayerQueue(unresolved_id=str(uuid5(NAMESPACE_URL,run_id+r['source_player_id'])),ingest_run_id=run_id,source_system='draftkings',source_table='tiers_native_pool_v1',source_player_key=r['source_player_id'],season=request.season,week=request.week,slate=request.slate,raw_row_json=r,normalized_name=r['name'].casefold(),team=r['team'],notes='Tiers native identity unresolved; retained in pool '+record['sha256']))
        session.commit()
    receipt.parent.mkdir(parents=True,exist_ok=True)
    try:
        with receipt.open('x') as f:json.dump({'pool_sha256':record['sha256']},f)
    except FileExistsError: return load(json.loads(receipt.read_text())['pool_sha256'],directory)
    return record


def readiness(pool, *, now=None, exclude_questionable=True, excluded_player_ids=None):
    now=now or datetime.now(UTC);manual=set(excluded_player_ids or []);ids={r['player_master_id'] for r in pool['players'] if r['player_master_id']}
    if manual-ids:raise ValueError('Tiers exclusions must reference canonical players in this pool')
    players=[]
    for r in pool['players']:
        blocks=list(r['reason_codes'])
        if now>=clock(r['kickoff_at']):blocks.append('game_locked')
        if r['questionable'] and exclude_questionable:blocks.append('user_exclude_questionable')
        if r['player_master_id'] in manual:blocks.append('user_player_exclusion')
        players.append({**r,'reason_codes':blocks,'eligible':not blocks})
    missing=[tier for tier in pool['tier_labels'] if not any(p['tier']==tier and p['eligible'] for p in players)]
    return dict(status='BLOCKED' if missing else 'FROZEN_BASELINE_RESEARCH_ONLY',entry_ready=False,missing_tiers=missing,players=players,reason_codes=['tier_without_eligible_player:'+t for t in missing],projection_age_hours=(now-clock(pool['projection_source']['data_cutoff_at'])).total_seconds()/3600,source_limitations=[('Official status source refreshed at '+pool['status_refresh']['observed_at']+'; final designations remain incomplete. Projection, disabled-game and schedule evidence remain frozen.') if pool.get('status_refresh') else 'Frozen source clocks are retained; no current status, disabled-game or schedule refresh is claimed.','Final game-day clearance is unavailable.','Rare TD scoring forecasts not verified.'])


def legal_lineup(players, tiers):
    return len(players)==len(tiers) and {p['tier'] for p in players}==set(tiers) and len({p['player_master_id'] for p in players})==len(players) and len({p['game_id'] for p in players})>=2


def optimize(request, *, directory=None, now=None):
    now=now or datetime.now(UTC);pool=load(request.pool_sha256,directory)
    if pool['kind']!='pool':raise ValueError('A Tiers pool record is required')
    if not request.accept_baseline_research:raise ValueError('Explicitly accept frozen common-DK baseline research and incomplete rare-TD scoring coverage')
    root=Path(directory) if directory is not None else LEDGER;req_sha=digest(request.model_dump(mode='json'));receipt=root/'runs'/(req_sha+'.json')
    if receipt.exists():return load(json.loads(receipt.read_text())['report_sha256'],directory)
    ready=readiness(pool,now=now,exclude_questionable=request.exclude_questionable,excluded_player_ids=request.excluded_player_ids)
    if ready['missing_tiers']:raise ValueError('No eligible player in '+', '.join(ready['missing_tiers']))
    groups=[[p for p in ready['players'] if p['tier']==tier and p['eligible']] for tier in pool['tier_labels']]
    count=math.prod(map(len,groups))
    if count>2_000_000:raise ValueError('Tier product exceeds the bounded exact research search (2,000,000)')
    ranked=heapq.nsmallest(request.num_lineups,(r for r in product(*groups) if legal_lineup(r,pool['tier_labels'])),key=lambda r:(-sum(p['projection'] for p in r),tuple(p['player_master_id'] for p in r)))
    if not ranked:raise ValueError('No legal Tiers lineup spans at least two NFL games')
    lineups=[dict(rank=i+1,projected_points=sum(p['projection'] for p in r),players=list(r)) for i,r in enumerate(ranked)]
    report=save(dict(contract_id=CONTRACT,kind='report',season=pool['season'],week=pool['week'],slate=pool['slate'],native_draft_group_id=pool['native_draft_group_id'],tier_labels=pool['tier_labels'],created_at=now.isoformat(),pool_sha256=pool['sha256'],projection_snapshot_sha256=pool['projection_snapshot_sha256'],projection_source=pool['projection_source'],rules=pool['rules'],scoring_compatibility=pool['scoring_compatibility'],analyst_context=pool['analyst_context'],status_refresh=pool.get('status_refresh'),settings=request.model_dump(mode='json'),objective='highest_unchanged_common_dk_baseline_projection',solver_status='OPTIMAL' if len(ranked)==request.num_lineups else 'OPTIMAL_AVAILABLE_UNDERFILLED',requested_lineups=request.num_lineups,lineup_count=len(ranked),distinct_canonical_rosters=len(ranked),candidate_product=count,constraints_relaxed=False,lineups=lineups,readiness=ready,entry_ready=False,export=EXPORT),directory)
    receipt.parent.mkdir(parents=True,exist_ok=True)
    try:
        with receipt.open('x') as f:json.dump({'report_sha256':report['sha256']},f)
    except FileExistsError:return load(json.loads(receipt.read_text())['report_sha256'],directory)
    return report
