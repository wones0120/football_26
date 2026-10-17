"""Exact native Tiers template binding and research-only, single-lineup CSVs."""
import csv
import io
import hashlib
import json
from pathlib import Path
from datetime import UTC, datetime
from pydantic import Field
from . import tiers
from .native_lineup_csv import render_native_lineup_csv, SCHEMA_VERSION

class TemplateImport(tiers.Strict):
    pool_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')
    source_name:str=Field(min_length=1,max_length=200)
    source_reference:str=Field(min_length=1,max_length=1000)
    template_csv:str=Field(min_length=1,max_length=2_000_000)


def parse_template(text,labels):
    rows=list(csv.reader(io.StringIO(text.lstrip('\ufeff'))));n=len(labels)
    if not rows or rows[0]!=labels+['','Instructions']:raise ValueError('Template header must exactly preserve the native tier order, blank separator and Instructions column')
    header=['Position','Name + ID','Name','ID','Roster Position','Game Info','TeamAbbrev','AvgPointsPerGame']
    starts=[i for i,r in enumerate(rows) if r[:n+1]==['']*(n+1) and r[n+1:]==header]
    if len(starts)!=1 or starts[0]<2:raise ValueError('One exact embedded native Tiers player table is required')
    start=starts[0]
    if len(rows[1])<n or any(any(cell.strip() for cell in r[:n]) for r in rows[1:start]):raise ValueError('Use a blank lineup template; existing roster cells cannot be replaced')
    players={}
    for row in rows[start+1:]:
        if not any(c.strip() for c in row):continue
        if len(row)!=n+9 or row[:n+1]!=['']*(n+1):raise ValueError('Unexpected native Tiers reference row')
        pos,name_id,name,pid,tier,game,team,average=row[n+1:]
        if not pid.isdigit() or pid in players or tier not in labels or name_id!=f'{name} ({pid})':raise ValueError('Invalid/duplicate native template ID, tier or Name + ID')
        players[pid]=dict(position=pos,name=name,tier=tier,native_game_info=game,team=team)
    if not players:raise ValueError('Native template player reference is empty')
    return rows,players


def validate_pool(pool,players):
    expected={r['source_player_id']:r for r in pool['players']}
    if set(expected)!=set(players):raise ValueError('Template native ID set does not match the saved Tiers pool; no substitution allowed')
    for pid,p in players.items():
        r=expected[pid]
        for k in ('tier','position','name','native_game_info'):
            if p[k]!=r[k]:raise ValueError('Template native ID has mismatched '+k)
        if tiers.normalize_team(p['team'])!=r['team']:raise ValueError('Template native team mismatch')


def import_template(request,*,directory=None,now=None):
    now=now or datetime.now(UTC);pool=tiers.load(request.pool_sha256,directory)
    if pool['kind']!='pool':raise ValueError('Template requires a saved Tiers pool')
    rows,players=parse_template(request.template_csv,pool['tier_labels']);validate_pool(pool,players)
    value=dict(contract_id=tiers.CONTRACT,kind='template',season=pool['season'],week=pool['week'],slate=pool['slate'],native_draft_group_id=pool['native_draft_group_id'],tier_labels=pool['tier_labels'],created_at=now.isoformat(),pool_sha256=pool['sha256'],source=request.model_dump(mode='json'),template_source_sha256=hashlib.sha256(request.template_csv.encode()).hexdigest(),classification='VERIFIED_NATIVE_TIERS_TEMPLATE',entry_ready=False)
    # Stable semantic key: retry returns the first receipt without renewing source clocks.
    req_sha=tiers.digest(request.model_dump(mode='json'));root=Path(directory) if directory is not None else tiers.LEDGER;receipt=root/'templates'/(req_sha+'.json')
    if receipt.exists():return tiers.load(json.loads(receipt.read_text())['template_sha256'],directory)
    record=tiers.save(value,directory);receipt.parent.mkdir(parents=True,exist_ok=True)
    try:
        with receipt.open('x') as f:json.dump({'template_sha256':record['sha256']},f)
    except FileExistsError:return tiers.load(json.loads(receipt.read_text())['template_sha256'],directory)
    return record


def validate_native_source(pool,report=None):
    if pool.get('kind')!='pool':raise ValueError('A saved native Tiers pool is required')
    if report and any(report.get(k)!=pool.get(k) for k in ('season','week','slate','native_draft_group_id','tier_labels','projection_snapshot_sha256')):raise ValueError('Saved Tiers report/pool scope mismatch')
    raw=(Path(pool['raw_directory'])/'native.csv').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=pool['native_csv_sha256']:raise ValueError('Original native Tiers source content hash mismatch')
    players,labels=tiers.parse_csv(raw.decode('utf-8'))
    if labels!=pool['tier_labels']:raise ValueError('Original native Tiers tier order mismatch')
    validate_pool(pool,{p['source_player_id']:p for p in players})


def export_readiness(report_key,*,directory=None,now=None):
    report=tiers.load(report_key,directory)
    if report['kind']!='report':raise ValueError('A saved Tiers lineup report is required')
    root=Path(directory) if directory is not None else tiers.LEDGER;templates=[]
    for path in root.glob('*.json'):
        try:r=tiers.load(path.stem,directory)
        except (ValueError,OSError,KeyError):continue
        if r['kind']=='template' and r.get('pool_sha256')==report['pool_sha256'] and r.get('classification')=='VERIFIED_NATIVE_TIERS_TEMPLATE':templates.append(r['sha256'])
    pool=tiers.load(report['pool_sha256'],directory);validate_native_source(pool,report);ready=tiers.readiness(pool,now=now,exclude_questionable=report['settings']['exclude_questionable'],excluded_player_ids=report['settings']['excluded_player_ids']);by_id={p['player_master_id']:p for p in ready['players']};reasons=[]
    for lineup in report['lineups']:
        for p in lineup['players']:reasons.extend(by_id.get(p['player_master_id'],{'reason_codes':['identity_missing']})['reason_codes'])
    return dict(enabled=not reasons,reason_codes=sorted(set(reasons)),template_sha256=sorted(templates)[0] if templates else None,entry_ready=False,warning='Research CSV only. Frozen source/scoring limitations remain; no contest assignment, submission or final entry clearance.')


def build_download(report_key,template_key=None,*,entry=1,accept_research=False,directory=None,now=None):
    # Legacy accept_research is accepted for older clients; downloads need no acknowledgment.
    now=now or datetime.now(UTC)
    report=tiers.load(report_key,directory);template=tiers.load(template_key,directory) if template_key else None
    if report['kind']!='report' or (template and (template['kind']!='template' or template.get('classification')!='VERIFIED_NATIVE_TIERS_TEMPLATE' or template['pool_sha256']!=report['pool_sha256'])):raise ValueError('Saved report/template pool binding mismatch')
    if entry<1 or entry>len(report['lineups']):raise ValueError('Saved lineup entry does not exist')
    ready=export_readiness(report_key,directory=directory,now=now)
    if not ready['enabled']:raise ValueError('Research CSV blocked: '+', '.join(ready['reason_codes']))
    pool=tiers.load(report['pool_sha256'],directory);native={p['source_player_id']:p for p in pool['players']};lineup=report['lineups'][entry-1]['players']
    if template:
        rows,native=parse_template(template['source']['template_csv'],pool['tier_labels']);validate_pool(pool,native)
    if not tiers.legal_lineup(lineup,pool['tier_labels']):raise ValueError('Saved lineup violates native Tiers roster rules')
    originals={p['player_master_id']:p for p in pool['players']};by_tier={p['tier']:p for p in lineup};ids=[]
    for label in pool['tier_labels']:
        p=by_tier[label];original=originals.get(p['player_master_id'])
        if not original or original['source_player_id']!=p['source_player_id'] or native[p['source_player_id']]['tier']!=label:raise ValueError('Saved canonical/native/tier linkage mismatch')
        ids.append(p['source_player_id'])
    if template:
        rows[1][:len(ids)]=ids;stream=io.StringIO(newline='');csv.writer(stream,lineterminator='\r\n').writerows(rows);content=stream.getvalue().encode('utf-8-sig' if template['source']['template_csv'].startswith('\ufeff') else 'utf-8')
    else:content=render_native_lineup_csv(pool['tier_labels'],[ids])
    filename=f'tiers-research-{report_key[:12]}-entry-{entry}.csv'
    receipt_key=tiers.digest(dict(report_sha256=report_key,template_sha256=template_key,entry=entry));root=Path(directory) if directory is not None else tiers.LEDGER;receipt_path=root/'exports'/(receipt_key+'.json')
    if receipt_path.exists():
        old=tiers.load(json.loads(receipt_path.read_text())['export_sha256'],directory)
        if old['content_sha256']!=hashlib.sha256(content).hexdigest():raise ValueError('Immutable Tiers export content conflict')
        return filename,content,old
    receipt=tiers.save(dict(contract_id=tiers.CONTRACT,kind='export',season=pool['season'],week=pool['week'],slate=pool['slate'],created_at=now.isoformat(),report_sha256=report_key,pool_sha256=pool['sha256'],template_sha256=template_key,csv_schema_version=SCHEMA_VERSION,native_csv_sha256=pool['native_csv_sha256'],entry=entry,native_roster_ids=ids,content_sha256=hashlib.sha256(content).hexdigest(),filename=filename,entry_ready=False,assignment_created=False,submission_confirmed=False,ordinary_download_request=True,research_acknowledgment_required=False),directory)
    receipt_path.parent.mkdir(parents=True,exist_ok=True)
    try:
        with receipt_path.open('x') as f:json.dump({'export_sha256':receipt['sha256']},f)
    except FileExistsError:return filename,content,tiers.load(json.loads(receipt_path.read_text())['export_sha256'],directory)
    return filename,content,receipt
