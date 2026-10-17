"""Native-pool Single Stat research CSVs; optional compatible template evidence."""
import csv
from datetime import UTC, datetime
import hashlib
import io
from pathlib import Path

from pydantic import Field

from . import single_stat as stat
from .native_lineup_csv import render_native_lineup_csv, SCHEMA_VERSION


class TemplateImport(stat.Strict):
    pool_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    source_name: str = Field(min_length=1,max_length=200)
    source_reference: str = Field(min_length=1,max_length=1000)
    source_observed_at: datetime
    template_csv: str = Field(min_length=1,max_length=4_000_000)


def parse_template(text):
    rows=list(csv.reader(io.StringIO(text.lstrip('\ufeff'))))
    if not rows or rows[0] != ['FLEX','FLEX','FLEX','','Instructions']:
        raise ValueError('Unsupported template header: expected exactly three positional FLEX columns and the supplied Instructions column')
    if len(rows)<4 or any(any(cell.strip() for cell in row[:3]) for row in rows[1:]):
        raise ValueError('Template must be blank: existing roster cells cannot be replaced or assigned')
    wanted=['Position','Name + ID','Name','ID','Roster Position','Game Info','TeamAbbrev','AvgPointsPerGame']
    headers=[i for i,row in enumerate(rows) if row[:4]==['','','',''] and row[4:]==wanted]
    if len(headers)!=1: raise ValueError('A single exact embedded player-pool header is required')
    start=headers[0];players={}
    if start<2 or len(rows[1])<3:raise ValueError('Template has no blank lineup row before its player reference table')
    for row in rows[start+1:]:
        if not any(cell.strip() for cell in row):continue
        if len(row)!=12 or row[:4]!=['','','','']: raise ValueError('Unexpected embedded pool row or metadata')
        position,name_id,name,pid,slot,game,team,average=row[4:]
        if not pid.isdigit() or pid in players or slot!='FLEX' or not game or not team:
            raise ValueError('Template player IDs must be unique numeric IDs with FLEX/game/team evidence')
        if name_id != f'{name} ({pid})': raise ValueError('Template Name + ID does not agree with the numeric player ID')
        players[pid]=dict(source_player_id=pid,name=name,team=team,native_game_info=game,position=position)
    if not players: raise ValueError('Template contains no native pool')
    return rows,players


def validate_pool(pool,players):
    expected={p['source_player_id']:p for p in pool['players']}
    if set(players)!=set(expected):
        games=sorted({p['native_game_info'] for p in players.values()})
        raise ValueError(f'Template belongs to a different native pool: {len(players)} template IDs, {len(expected)} saved pool IDs; template games: {", ".join(games)}. Supply the exact template for this saved pool; IDs cannot be substituted.')
    for pid,p in players.items():
        source=expected[pid]
        if p['team']!=source['team'] or p['native_game_info']!=source.get('native_game_info',source['game_id']):
            raise ValueError('Template native ID has contradictory team/game evidence')


def import_template(request,*,directory=None,now=None):
    now=now or datetime.now(UTC)
    if stat.clock(request.source_observed_at)>now:raise ValueError('Template source clock is in the future')
    pool=stat.load(request.pool_sha256,directory)
    if pool['kind']!='pool':raise ValueError('Template must bind to a saved native pool')
    rows,players=parse_template(request.template_csv)
    # Capture supplied evidence even on a rejected binding; never promote it to usable.
    value=dict(contract_id=stat.CONTRACT,kind='template',variant=pool['variant'],game_set_id=pool['game_set_id'],
        classification='UNMATCHED_NATIVE_TEMPLATE',created_at=now.isoformat(),pool_sha256=pool['sha256'],
        source=request.model_dump(mode='json'),template_sha256=hashlib.sha256(request.template_csv.encode()).hexdigest(),
        native_player_ids=sorted(players),entry_ready=False,export=dict(enabled=False,reason='Native template binding not verified'))
    try:validate_pool(pool,players)
    except ValueError as exc:
        value['validation_error']=str(exc);stat._save(value,directory);raise
    value.update(classification='VERIFIED_NATIVE_TEMPLATE',export=dict(enabled=True,reason='Exact native pool and three FLEX template verified; current player locks still apply'))
    # A retry with identical source/evidence returns the original immutable template record.
    root=Path(directory) if directory is not None else stat.LEDGER
    for path in root.glob('*.json'):
        try:old=stat.load(path.stem,directory)
        except (ValueError,OSError,KeyError):continue
        if old.get('kind')=='template' and old.get('classification')=='VERIFIED_NATIVE_TEMPLATE' and old.get('source')==value['source']:return old
    return stat._save(value,directory)


def validated_native_roster(report,pool):
    """Old reports remain usable only when their original immutable pool proves every ID."""
    if report.get('kind')!='report' or pool.get('kind')!='pool' or pool.get('source',{}).get('contest_format')!='single_stat':
        raise ValueError('Native CSV requires a saved Single Stat report and native pool')
    if report.get('pool_sha256')!=pool['sha256'] or report.get('variant')!=pool.get('variant') or report.get('game_set_id')!=pool.get('game_set_id'):
        raise ValueError('Saved report mode/stat/Game Set/native pool mismatch')
    source=pool['source']; text=source.get('native_csv')
    if not text or hashlib.sha256(text.encode()).hexdigest()!=pool.get('native_csv_sha256'):
        raise ValueError('Original immutable native CSV evidence is missing or changed')
    columns=source.get('columns',{})
    if set(columns)!={'source_player_id','name','team','game_id'}:raise ValueError('Original native column mapping is unavailable')
    reader=csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
    if any((reader.fieldnames or []).count(column)!=1 for column in columns.values()):raise ValueError('Original native CSV columns are missing or ambiguous')
    raw=list(reader);native_rows={}
    for row in raw:
        pid=(row.get(columns['source_player_id']) or '').strip()
        if not pid or pid in native_rows:raise ValueError('Missing or ambiguous native ID in original CSV')
        native_rows[pid]=row
    canonical={}
    for p in pool['players']:
        if p['player_master_id']:
            if p['player_master_id'] in canonical:raise ValueError('Ambiguous canonical player in saved native pool')
            canonical[p['player_master_id']]=p
    if not stat.legal_lineup(report['players']):raise ValueError('Saved lineup must have three distinct canonical players and at least two teams')
    ids=[]
    for p in report['players']:
        original=canonical.get(p['player_master_id']);raw_row=native_rows.get(p['source_player_id'])
        if not original or not raw_row or original['source_player_id']!=p['source_player_id'] or original['team']!=p['team']:
            raise ValueError('Saved canonical/native identity or team mismatch')
        role=(raw_row.get('Roster Position') or '').strip().upper()
        if role and role!='FLEX':raise ValueError('Original native roster role is not Single Stat FLEX')
        if p.get('game_id') and p['game_id']!=original['game_id']:raise ValueError('Saved player game identity mismatch')
        game_info=(raw_row.get(columns['game_id']) or '').strip()
        if (raw_row.get(columns['team']) or '').strip()!=p['team'] or source.get('native_game_ids',{}).get(game_info,game_info)!=original['game_id']:
            raise ValueError('Native player is outside the exact imported game/team scope')
        ids.append(p['source_player_id'])
    # Serializer also proves numeric source IDs, positional cardinality and uniqueness.
    render_native_lineup_csv(['FLEX','FLEX','FLEX'],[ids])
    return ids


def export_readiness(report_key,*,directory=None,now=None):
    report=stat.load(report_key,directory)
    if report.get('kind')!='report':raise ValueError('CSV requires a saved lineup report')
    pool=stat.load(report['pool_sha256'],directory)
    validated_native_roster(report,pool)
    current=stat.readiness(pool,now=now,partial=True)
    by_id={p['player_master_id']:p for p in current['players']}
    reasons=[r for r in current['reason_codes'] if r not in {'pool_identity_or_stat_coverage_incomplete','no_legal_three_player_lineup'}]
    for p in report['players']:
        reasons.extend(r for r in by_id[p['player_master_id']]['reason_codes'] if r not in {'stat_forecast_missing'})
    return dict(enabled=not reasons,reason_codes=sorted(set(reasons)),template_sha256=None,
        automatic_from_native_pool=True,csv_headers=['FLEX','FLEX','FLEX'],csv_schema=SCHEMA_VERSION,
        research_acceptance_required=False,entry_ready=False,
        warning='Native-pool research lineup CSV. No per-slate template required. Missing history, partial TD categories and model limitations remain; download does not assign, submit or clear a contest entry.')


def build_download(report_key,template_key=None,*,accept_research=False,directory=None,now=None):
    # Legacy accept_research is accepted for older clients; downloads need no acknowledgment.
    now=now or datetime.now(UTC)
    report=stat.load(report_key,directory)
    ready=export_readiness(report_key,directory=directory,now=now)
    if not ready['enabled']:raise ValueError('CSV blocked: '+', '.join(ready['reason_codes']))
    pool=stat.load(report['pool_sha256'],directory);ids=validated_native_roster(report,pool)
    template=None
    if template_key:
        template=stat.load(template_key,directory)
        if template.get('classification')!='VERIFIED_NATIVE_TEMPLATE' or template.get('kind')!='template' or template['pool_sha256']!=report['pool_sha256']:
            raise ValueError('Template/report native pool binding mismatch')
        rows,players=parse_template(template['source']['template_csv']);validate_pool(pool,players)
        rows[1][:3]=ids
        output=io.StringIO(newline='');csv.writer(output,lineterminator='\r\n').writerows(rows);content=output.getvalue().encode('utf-8')
    else:
        content=render_native_lineup_csv(['FLEX','FLEX','FLEX'],[ids])
    filename=f'single-stat-{report["variant"]}-research-{report_key[:12]}.csv'
    receipt=stat._save(dict(contract_id=stat.CONTRACT,kind='export',variant=report['variant'],game_set_id=report['game_set_id'],classification='RESEARCH_CSV_NOT_SUBMITTED',created_at=now.isoformat(),
        report_sha256=report_key,pool_sha256=pool['sha256'],template_record_sha256=template_key,template_source_sha256=template['template_sha256'] if template else None,
        automatic_from_native_pool=template is None,csv_schema=SCHEMA_VERSION,csv_headers=['FLEX','FLEX','FLEX'],
        format_evidence='User-provided official Single Stat template FLEX,FLEX,FLEX roster columns and numeric-ID instructions; instruction/reference columns omitted in automatic lineup-only output. Actual site acceptance is not tested by submission.',
        content_sha256=hashlib.sha256(content).hexdigest(),content_hex=content.hex(),filename=filename,native_roster_ids=ids,
        source_report_classification=report['classification'],source_objective_scope=report.get('objective_scope'),forecast_coverage=report['forecast_coverage'],
        entry_ready=False,submission_confirmed=False,assignment_created=False,ordinary_download_request=True,research_acknowledgment_required=False,export=dict(enabled=True,reason=ready['warning'])),directory)
    return filename,content,receipt
