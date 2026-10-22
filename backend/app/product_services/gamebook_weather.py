"""Explicit-unit official NFL gamebook weather; never an inferred forecast."""
from copy import deepcopy
from datetime import datetime,UTC
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import Request,urlopen
from urllib.parse import urlparse
import hashlib,io,re
from .factual_designation import clock
from .market_snapshots import canonical_team
from .evaluation_record import digest
VERSION='official_gamebook_explicit_temperature_v1'
MAX_BYTES=16*1024*1024


def official_uri(uri):
    p=urlparse(uri)
    return p.scheme=='https' and p.hostname in {'static.clubs.nfl.com','static.www.nfl.com'} and not p.username and not p.password


def first_page_text(payload):
    from pypdf import PdfReader
    if not isinstance(payload,bytes) or not 0<len(payload)<=MAX_BYTES or not payload.startswith(b'%PDF-'):raise ValueError('Bounded original PDF bytes required')
    reader=PdfReader(io.BytesIO(payload),strict=True)
    if reader.is_encrypted or not 1<=len(reader.pages)<=100:raise ValueError('Readable bounded NFL gamebook required')
    text=reader.pages[0].extract_text() or ''
    if len(text)>100000:raise ValueError('Gamebook first-page text bound exceeded')
    return text,len(reader.pages)


def parse_gamebook_temperature(text):
    if not isinstance(text,str) or len(text)>100000:raise ValueError('Bounded original first-page text required')
    flat=re.sub(r'\s+',' ',text)
    if 'National Football League Game Summary' not in flat:raise ValueError('Official NFL summary heading required')
    dates=set(re.findall(r'\bDate:\s*[A-Za-z]+,\s*(\d{1,2}/\d{1,2}/\d{4})',flat))
    if len(dates)!=1:raise ValueError('Unique native gamebook date required')
    game_date=datetime.strptime(next(iter(dates)),'%m/%d/%Y').date().isoformat()
    teams={}
    for label,role in (('VISITOR','away_team'),('HOME','home_team')):
        names=re.findall(r'\b'+label+r':\s*([A-Za-z .]+?)(?=\s+[+-]?\d)',flat)
        if len(names)!=1:raise ValueError('Unique explicit gamebook home/visitor team required')
        teams[role]=canonical_team(names[0].strip())
    if teams['home_team']==teams['away_team']:raise ValueError('Distinct native gamebook teams required')
    number=r'([+-]?\d+(?:\.\d+)?)'
    tokens=re.findall(r'\bTemp:\s*'+number+r'\s*°?\s*F(?:\s*\(\s*'+number+r'\s*°?\s*C\s*\))?',flat)
    unique=set(tokens);issue=None;f=None;c=None
    if len(unique)==1:
        a,b=next(iter(unique));f=float(a);c=float(b) if b else None
        # Both displayed units are rounded independently: whole F and tenth C.
        if c is not None and abs((f-32)*5/9-c)>.35:issue='Contradictory displayed Fahrenheit/Celsius pair';f=None
    else:issue='Missing explicit Fahrenheit unit' if not unique else 'Multiple conflicting temperature reports on first page'
    venue=re.search(r'\bat\s+([A-Za-z0-9 .’\-]+?),\s*[A-Za-z .]+,\s*[A-Z]{2}\b',flat)
    return dict(game_date=game_date,**teams,reported_venue=venue.group(1).strip() if venue else None,
        temperature_f=f,displayed_temperature_c=c,temperature_unit='degrees_Fahrenheit' if f is not None else None,
        original_temperature_tokens=[list(t) for t in tokens],measurement_issue=issue,
        measurement_kind='official_reported_game_day_weather_not_forecast',original_first_page_sha256=hashlib.sha256(text.encode()).hexdigest())


def bind_gamebook_temperature(parsed,schedule,*,before_period):
    matches=[r for r in schedule['game_rows'] if r['game_type']=='REG' and r['game_date']==parsed['game_date'] and r['home_team']==parsed['home_team'] and r['away_team']==parsed['away_team']]
    if len(matches)!=1:raise ValueError('Unique indexed native game/date/home-away binding required')
    game=matches[0]
    if game['season']*100+game['week']>=before_period:raise ValueError('Gamebook must be strictly prior REG scope')
    basis=dict(version=VERSION,candidate_id='G20-M04',before_period=before_period,game_id=game['game_id'],season=game['season'],week=game['week'],
        reported_weather=deepcopy(parsed),native_game_binding=dict(game_date=game['game_date'],home_team=game['home_team'],away_team=game['away_team'],basis='Unique indexed native REG date and explicit official visitor/home team pair'),
        team_rows=[dict(team=t,value=parsed['temperature_f'],unit=parsed['temperature_unit']) for t in (game['away_team'],game['home_team'])])
    return basis|dict(semantic_sha256=digest(basis),evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,
        limitations=['Reported game-day measurement, not source-verified observation time or pregame forecast','Explicit units apply only to this authenticated gamebook; unlabeled schedule temperature units remain unknown','No precipitation/zero-rain, sustained-wind/gust or thermal-performance inference','No player parsing/identity join; no historical original publication proof'],forecast=None,model_consumed=False,optimizer_consumed=False)


def capture_gamebook_weather(service,*,uri,season,week,slate_lock_at,fetcher=None):
    if not official_uri(uri):raise ValueError('Official primary NFL asset URL required')
    headers={}
    if fetcher is None:
        with urlopen(Request(uri,headers={'User-Agent':'Football feature source verification','Accept':'application/pdf'}),timeout=30) as response:
            if not official_uri(response.geturl()):raise ValueError('Official PDF redirected outside primary NFL source')
            payload=response.read(MAX_BYTES+1);headers={k:response.headers.get(k) for k in ('Date','Last-Modified','ETag','Content-Type') if response.headers.get(k)}
    else:payload=fetcher(uri)
    if not isinstance(payload,bytes) or not 0<len(payload)<=MAX_BYTES:raise ValueError('Bounded original response bytes required')
    parsed=None;pages=None;error=None
    try:
        text,pages=first_page_text(payload);parsed=parse_gamebook_temperature(text)
        if int(parsed['game_date'][:4])!=season:raise ValueError('Gamebook native year differs from capture scope')
    except Exception as exc:
        error=type(exc).__name__+': '+str(exc)[:250]
    with TemporaryDirectory(prefix='football_gamebook_') as tmp:
        path=Path(tmp)/'original_gamebook.pdf';path.write_bytes(payload)
        return service.capture_file(path,source_system='nfl_official_gamebook',dataset='game_summary',season=season,week=week,slate='historical_feature_sources',
            source_license='NFL copyright retained; gamebook notice restricts reuse; no open license assumed',source_uri=uri,slate_lock_at=clock(slate_lock_at),observation_basis='capture_clock',row_count=1 if error is None else None,media_type='application/pdf' if payload.startswith(b'%PDF-') else 'application/octet-stream',
            metadata=dict(contract=VERSION,original_remote_pdf_bytes=True,original_sha256=hashlib.sha256(payload).hexdigest(),pdf_pages=pages,http_headers=headers,
                initial_validation_error=error,original_weather_observation_at=None,original_publication_at=None,original_source_notice='NFL game summary copyright/media-purpose notice retained in original PDF',initial_parsed_weather=parsed))


def load_gamebook_temperature(snapshot,schedule,*,before_period,actual_read_at):
    from backend.app.services.source_capture import verify_snapshot_artifact
    decision=clock(actual_read_at);p=snapshot.metadata_json or {}
    if decision is None or decision>datetime.now(UTC) or clock(snapshot.captured_at) is None or clock(snapshot.observed_at) is None or not clock(snapshot.observed_at)<=clock(snapshot.captured_at)<=decision:raise ValueError('Original source unavailable at actual read')
    if snapshot.source_system!='nfl_official_gamebook' or snapshot.dataset!='game_summary' or snapshot.media_type!='application/pdf' or not official_uri(snapshot.source_uri) or p.get('contract')!=VERSION or p.get('original_remote_pdf_bytes') is not True or p.get('original_sha256')!=snapshot.content_sha256:raise ValueError('Indexed original gamebook contract differs')
    if p.get('initial_validation_error') is not None:raise ValueError('Captured original failed native gamebook validation')
    if not 0<snapshot.byte_count<=MAX_BYTES or snapshot.row_count!=1:raise ValueError('Gamebook source size/game bound differs')
    verify_snapshot_artifact(snapshot);text,pages=first_page_text(Path(snapshot.artifact_path).read_bytes());parsed=parse_gamebook_temperature(text)
    if parsed['game_date']>decision.date().isoformat() or clock(snapshot.slate_lock_at) is None or clock(snapshot.slate_lock_at)>clock(snapshot.captured_at):raise ValueError('Historical reported gamebook boundary required')
    result=bind_gamebook_temperature(parsed,schedule,before_period=before_period)
    if result['season']!=snapshot.season or result['week']!=snapshot.week or pages!=p['pdf_pages'] or parsed!=p['initial_parsed_weather']:raise ValueError('Indexed gamebook native scope/parse differs')
    if schedule.get('version')!='native_schedule_context_features_v1' or schedule.get('evidence_use')!='postlock_descriptive_not_pregame_or_serving' or schedule.get('pregame_serving_eligible') is not False or clock(schedule['provenance'].get('captured_at')) is None or clock(schedule['provenance']['captured_at'])>decision:raise ValueError('Authenticated descriptive schedule required')
    result['provenance']=dict(source_snapshot_id=str(snapshot.snapshot_id),source_sha256=snapshot.content_sha256,source_uri=snapshot.source_uri,source_observed_at=clock(snapshot.observed_at).isoformat(),source_captured_at=clock(snapshot.captured_at).isoformat(),
        schedule_provenance=deepcopy(schedule['provenance']),original_weather_observation_at=None,original_publication_at=None,actual_read_at=decision.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return result


def require_feature_use(value,*,purpose):
    if value.get('version')!=VERSION or value.get('pregame_serving_eligible') is not False or purpose!='offline_descriptive':raise ValueError('Reported retrospective game weather cannot serve forecasts/models/optimizer')
    return value
