"""Immutable observed Tiers/Single Stat standings, outside fantasy ownership/ROI.

Standings scores are source observations. Name-only rows never become canonical
facts; native IDs must bind to one explicit saved pool before forecast matching.
"""
from contextlib import contextmanager
import csv
from datetime import datetime, UTC
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import tempfile
from zipfile import ZipFile

LEDGER = Path('artifacts/special_contest_results')
UNITS = {'tiers':'dk_fantasy_points','touchdowns':'touchdowns','total_yards':'yards','passing_yards':'yards'}

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

@contextmanager
def csv_rows(path):
    path=Path(path)
    with path.open('rb') as stream:magic=stream.read(2)
    if path.suffix.lower()=='.zip' or magic==b'PK':
        with ZipFile(path) as archive:
            names=[n for n in archive.namelist() if n.lower().endswith('.csv') and not n.endswith('/')]
            if len(names)!=1:raise ValueError('Exactly one standings CSV is required per archive')
            if archive.getinfo(names[0]).file_size > 128*1024*1024:raise ValueError('Uncompressed standings exceeds128MiB limit')
            with archive.open(names[0]) as stream:
                yield csv.DictReader(io.TextIOWrapper(stream,encoding='utf-8-sig'))
    else:
        with path.open(encoding='utf-8-sig',newline='') as stream:yield csv.DictReader(stream)

def roster(lineup):
    matches=list(re.finditer(r'(?:^|\s)(T\d+|FLEX|CPT|QB|RB|WR|TE|DST)\s+',str(lineup)))
    return [(m.group(1),str(lineup)[m.end():matches[i+1].start() if i+1<len(matches) else None].strip())for i,m in enumerate(matches)]

def format_hint(path):
    with csv_rows(path) as rows:
        for i,row in enumerate(rows):
            slots=[s for s,_ in roster(row.get('Lineup',''))]
            if slots and all(re.fullmatch('T[1-9][0-9]*',s)for s in slots):return 'tiers'
            if slots==['FLEX']*3:return 'single_stat'
            if i>=7:break
    return None

def _number(value):
    try:n=float(value)
    except (TypeError,ValueError):raise ValueError('Observed score/rank is missing or nonnumeric')
    if not math.isfinite(n):raise ValueError('Observed score/rank must be finite')
    return n

def load(key, directory=None):
    if not re.fullmatch('[a-f0-9]{64}',str(key)):raise ValueError('Invalid result record ID')
    root=Path(directory or LEDGER);record=json.loads((root/key/'record.json').read_text())
    payload={k:v for k,v in record.items()if k not in {'record_id','created_at','source_name'}}
    if digest(payload)!=key:raise ValueError('Result record integrity mismatch')
    if hashlib.sha256((root/key/'source.bin').read_bytes()).hexdigest()!=record['source_sha256']:raise ValueError('Raw standings hash mismatch')
    return record

def catalog(directory=None):
    root=Path(directory or LEDGER)
    return [load(p.name,root) for p in sorted(root.glob('[a-f0-9]'*64)) if (p/'record.json').exists()]

def _pool(key,fmt):
    if not key:return None
    from . import tiers,single_stat
    pool=(tiers if fmt=='tiers' else single_stat).load(key)
    if pool['kind']!='pool':raise ValueError('Native pool record required')
    return pool

def validate_scope(fmt,variant,pool,*,season,week,slate):
    if fmt not in {'tiers','single_stat'}:raise ValueError('Typed standings require Tiers or Single Stat')
    if fmt=='tiers' and variant not in {'','tiers',None}:raise ValueError('Tiers uses DK fantasy points, not a Single Stat metric')
    if fmt=='single_stat' and variant not in {'touchdowns','total_yards','passing_yards'}:raise ValueError('Choose the verified Single Stat variant; three FLEX slots cannot establish it')
    if pool:
        scope=pool if fmt=='tiers' else pool['source']
        if (scope['season'],scope['week'])!=(season,week):raise ValueError('Saved pool season/week conflicts with result assignment')
        if fmt=='tiers' and pool['slate'] not in {slate, slate+'_TIERS'}:raise ValueError('Saved pool slate conflicts with result assignment')
        if fmt=='single_stat' and pool['variant']!=variant:raise ValueError('Saved pool scoring variant conflicts with result assignment')

def _validate_roster(slots,fmt,tiers=None):
    roles=[s for s,_ in slots];names=[n for _,n in slots]
    if fmt=='single_stat' and roles!=['FLEX']*3:raise ValueError('Single Stat requires exactly three FLEX athletes')
    if fmt=='tiers' and (not roles or any(not re.fullmatch('T[1-9][0-9]*',s)for s in roles) or len(set(roles))!=len(roles) or set(roles)!=set(tiers or ['T1','T2','T3','T4','T5','T6'])):
        raise ValueError('Tiers requires exactly one athlete per native tier')
    if len(set(names))!=len(names):raise ValueError('Duplicate athlete in observed roster')

def import_results(path,*,season,week,slate,contest_id,contest_format,variant=None,pool_sha256=None,
                   source_reference='',correction_of=None,directory=None,pool_loader=None,dry_run=False):
    if not source_reference.strip():raise ValueError('Record the contest scoring/scope evidence reference before loading')
    path=Path(path);fmt=contest_format;pool=(pool_loader or _pool)(pool_sha256,fmt)
    if path.stat().st_size>128*1024*1024:raise ValueError('Standings exceeds128MiB import limit')
    validate_scope(fmt,variant,pool,season=season,week=week,slate=slate)
    variant='tiers' if fmt=='tiers' else variant
    hint=format_hint(path)
    if hint!=fmt:raise ValueError('Assigned format conflicts with the observed roster slots')
    count=0;best=None;seen=set();labels=set();unavailable_lineups=0
    with csv_rows(path) as rows:
        for row in rows:
            if not row.get('EntryId'):continue
            entry_id=str(row['EntryId']).strip()
            if entry_id in seen:raise ValueError('Duplicate entry ID in standings')
            seen.add(entry_id);count+=1;score=_number(row.get('Points'));rank=_number(row.get('Rank'))
            if rank<1 or rank!=int(rank):raise ValueError('Observed rank must be a positive integer')
            if fmt=='single_stat' and (abs(score-round(score))>1e-4 or variant=='touchdowns' and score<0):raise ValueError('Single Stat score has incompatible units')
            slots=roster(row.get('Lineup',''))
            if not str(row.get('Lineup') or '').strip():
                unavailable_lineups+=1
                best=score if best is None else max(best,score)
                continue
            _validate_roster(slots,fmt,pool.get('tier_labels')if pool else None)
            if pool:
                resolved=[_identity(label,role,pool)for role,label in slots]
                ids=[p['player_id']for p in resolved if p['player_id']]
                if len(set(ids))!=len(ids):raise ValueError('Duplicate canonical athlete in observed roster')
                if len(ids)==len(slots):
                    key='game_id' if fmt=='tiers' else 'team'
                    if len({p[key]for p in resolved})<2:raise ValueError('Roster needs at least two games for Tiers or two teams for Single Stat')
            if fmt=='tiers':
                current=tuple(sorted(s for s,_ in slots))
                if labels and current not in labels:raise ValueError('Inconsistent Tiers roster labels')
                labels.add(current)
            best=score if best is None else max(best,score)
    if not count:raise ValueError('No observed entries found')
    raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest()
    assignment=dict(season=season,week=week,slate=slate,contest_id=str(contest_id or 'source:'+sha),contest_format=fmt,
        variant=variant,units=UNITS[variant],pool_sha256=pool_sha256,source_reference=source_reference.strip(),
        scope_status='operator_assigned; provider scope not independently verified',
        classification='fixture_research' if source_reference.startswith('fixture:') else 'observed_standings')
    record=dict(contract_id='typed_contest_results_v1',**assignment,source_sha256=sha,source_file_id='dk_file_'+sha,
        entry_count=count,best_observed_score=best,correction_of=correction_of,
        native_game_pool_id=(pool.get('native_draft_group_id') or pool.get('game_set_id'))if pool else None,
        native_pool_slate=pool.get('slate') if pool else None,
        scoring_source='DraftKings observed contest Points; no NFL component reconstruction',
        source_observed_at=None,standings_finality='unverified; source snapshot not asserted final',
        reconciliation_status='unverified_components',financial_accounting='excluded; entry history remains authoritative')
    if unavailable_lineups:record['unavailable_lineups']=unavailable_lineups
    key=digest(record);root=Path(directory or LEDGER)
    if (root/key/'record.json').exists():return load(key,root),True
    others=[r for r in catalog(root)if r['contest_id']==record['contest_id'] and r['classification']==record['classification']]
    if others and not correction_of:raise ValueError('Existing contest result differs; explicit correction record ID required')
    if correction_of:
        prior=load(correction_of,root)
        if prior['contest_id']!=record['contest_id'] or prior['classification']!=record['classification']:raise ValueError('Correction must reference the same contest')
    if correction_of and any(r.get('correction_of')==correction_of for r in catalog(root)):
        raise ValueError('Correction must extend the current result lineage, not create a conflicting branch')
    if dry_run:return {**record,'record_id':key},False
    root.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root,prefix='.pending-') as staging:
        stage=Path(staging);(stage/'source.bin').write_bytes(raw)
        record.update(record_id=key,created_at=datetime.now(UTC).isoformat(),source_name=path.name)
        (stage/'record.json').write_text(json.dumps(record,indent=2,allow_nan=False))
        try:os.rename(stage,root/key)
        except FileExistsError:return load(key,root),True
    return load(key,root),False

def _identity(label,role,pool):
    match=re.fullmatch(r'.+?\s*\((\d+)\)',label)
    if not pool or not match:return dict(display_name=label,role=role,identity_status='unverified_name_only',player_id=None)
    native=match[1];matches=[p for p in pool['players'] if str(p['source_player_id'])==native]
    if len(matches)!=1:raise ValueError('Native player ID is missing or ambiguous in selected pool')
    if not matches[0].get('player_master_id'):return dict(display_name=label,role=role,identity_status='unresolved_native_id',player_id=None,native_id=native)
    p=matches[0]
    if role.startswith('T') and p.get('tier')!=role:raise ValueError('Native player belongs to a different tier')
    return dict(display_name=label,role=role,identity_status='resolved_native_pool',player_id=p['player_master_id'],native_id=native,team=p['team'],game_id=p['game_id'])


def forecast_comparison(record, players):
    """Compare canonical role rosters without asserting origin or submission."""
    if not players or not record.get('pool_sha256') or any(not p.get('player_id') for p in players):
        return dict(status='unmatched',reason='Canonical identity and exact saved pool are required; no name-only join')
    from . import tiers, single_stat
    service = tiers if record['contest_format']=='tiers' else single_stat
    wanted=sorted((p['role'],p['player_id'])for p in players)
    matches=[]
    for item in service.catalog():
        if item.get('kind')!='report':continue
        report=service.load(item['sha256'])
        if report.get('pool_sha256')!=record['pool_sha256']:continue
        if record['contest_format']=='single_stat' and (report.get('variant')!=record['variant'] or report.get('units')!=record['units']):continue
        lineups=report.get('lineups',[]) if record['contest_format']=='tiers' else [dict(players=report['players'],projected_points=report['expected_metric'])]
        for lineup in lineups:
            actual=sorted((p.get('tier','FLEX'),p.get('player_master_id'))for p in lineup['players'])
            if actual==wanted:
                matches.append(dict(report_sha256=report['sha256'],lineup_rank=lineup.get('rank'),forecast=lineup['projected_points'],units=record['units'],objective=report['objective'],forecast_coverage=report.get('forecast_coverage')or report.get('scoring_compatibility'),created_at=report['created_at']))
    return dict(status='unique_roster_correspondence' if len(matches)==1 else 'ambiguous_roster_correspondence' if matches else 'unmatched',
        matches=matches,origin_proven=False,submission_proven=False,chronology_verified=False,
        reason='Canonical roster correspondence only; no assignment/submission or pre-lock chronology proof is inferred')

def entries(record,entry_user,*,directory=None,pool_loader=None):
    root=Path(directory or LEDGER);record=load(record['record_id'],root)
    pool=(pool_loader or _pool)(record['pool_sha256'],record['contest_format']);found=[]
    with csv_rows(root/record['record_id']/'source.bin') as rows:
        for row in rows:
            if not row.get('EntryId') or re.sub(r'\s+\(\d+/\d+\)$','',str(row.get('EntryName',''))).casefold()!=entry_user.strip().casefold():continue
            players=[_identity(label,role,pool)for role,label in roster(row['Lineup'])]
            ids=[p['player_id'] for p in players if p['player_id']]
            if len(set(ids))!=len(ids):raise ValueError('Duplicate canonical athlete in result roster')
            found.append(dict(entry_id=row['EntryId'],entry_name=row['EntryName'],rank=int(_number(row['Rank'])),observed_score=_number(row['Points']),raw_score=row['Points'],observed_time_remaining=row.get('TimeRemaining'),players=players,
                identity_status='roster_unavailable' if not players else 'resolved' if len(ids)==len(players) else 'unverified',
                forecast_comparison=forecast_comparison(record,players),
                component_reconciliation='unverified; observed contest score preserved',fee=None,payout=None,roi=None))
    return found

def learning_groups(*,season,week,entry_user,directory=None):
    all_records=catalog(directory)
    records=[r for r in all_records if(r['season'],r['week'])==(season,week)]
    superseded={r['correction_of'] for r in all_records if r.get('correction_of')}
    groups=[]
    for record in records:
        if record['record_id'] in superseded:continue
        observed=entries(record,entry_user,directory=directory)
        if observed:groups.append({**record,'entries':observed,'status':'observed_only','financial_accounting':'not included in financial totals'})
    return groups
