"""Source-reported weekly passing air yards per matching official attempt."""
from copy import deepcopy
from datetime import datetime,UTC
import math
from .factual_designation import clock
from .market_snapshots import canonical_team
from .weekly_effectiveness_catalog_features import VERSION as INPUT_VERSION
from .evaluation_record import digest
VERSION='official_weekly_passing_air_per_attempt_v1'


def _number(value,*,count=False):
    if value is None or value=='':return None
    if isinstance(value,bool):return None
    try:n=float(value)
    except (TypeError,ValueError):return None
    if not math.isfinite(n) or (count and (n<0 or int(n)!=n)):return None
    return n


def build_weekly_passing_air_efficiency(weekly,extract,*,cutoff):
    decision=clock(cutoff)
    if decision is None or decision>datetime.now(UTC) or clock(extract.get('actual_read_at')) is None or clock(extract['actual_read_at'])>decision:raise ValueError('Actual nonfuture air source revision clock required')
    if weekly.get('version')!=INPUT_VERSION or weekly.get('pregame_serving_eligible') is not False or extract.get('before_period')!=weekly.get('before_period'):raise ValueError('Matching reviewed weekly scope required')
    indexed={}
    for record in extract['rows']:
        key=str(record['source_id'])
        if key in indexed:raise ValueError('Duplicate raw weekly revision ID')
        indexed[key]=record
    rows=[];used=set()
    for old in weekly['rows']:
        if type(old['season']) is not int or type(old['week']) is not int or not 1<=old['week']<=18 or old['season']*100+old['week']>=weekly['before_period']:raise ValueError('Strict prior weekly source period required')
        if not old['QB_scope_source_proven']:continue
        source=old['source_ref'];record=indexed.get(str(source['source_id']));issue=None;air=None;attempts=None;game_basis='Missing current raw revision'
        if record is not None:
            used.add(str(source['source_id']));raw=record['raw_row_json']
            same=(record['source_player_id']==old['source_player_id'] and record['season']==old['season'] and record['week']==old['week'] and record.get('position')=='QB' and raw.get('season_type')=='REG' and (raw.get('position') if raw.get('position') is not None else raw.get('pos')) in (None,'QB'))
            try:same=same and canonical_team(record['team'])==old['team']
            except (ValueError,TypeError):same=False
            for field in ('position','pos'):
                if raw.get(field) not in (None,'','QB'):same=False
            current_game=record.get('game_id') or None;old_game=old.get('native_game_id') or None
            if current_game is not None:
                parts=str(current_game).split('_')
                try:game_valid=len(parts)==4 and int(parts[0])==old['season'] and int(parts[1])==old['week'] and old['team'] in {canonical_team(p) for p in parts[2:]}
                except (ValueError,TypeError):game_valid=False
                same=same and game_valid and (old_game is None or current_game==old_game)
                game_basis='Matched original native game ID' if old_game is not None else 'Current native game independently matches original period/team; original native game ID absent'
            else:
                same=same and old_game is None
                game_basis='Provider native game ID absent in both revisions; explicit native player/week/team grain only' if old_game is None else 'Current native game ID missing against original known game'
            for field in ('player_id','gsis_id'):
                if raw.get(field) not in (None,old['source_player_id']):same=False
            for field,expected in (('season',old['season']),('game_season',old['season']),('week',old['week']),('game_week',old['week'])):
                if raw.get(field) is not None and str(raw[field]) not in {str(expected),str(float(expected))}:same=False
            for field in ('team','recent_team'):
                if raw.get(field) not in (None,''):
                    try:same=same and canonical_team(str(raw[field]))==old['team']
                    except ValueError:same=False
            imported=clock(record.get('imported_at'))
            if imported is None or imported>decision or imported!=clock(source['imported_at']) or str(record.get('ingest_run_id'))!=str(source['ingest_run_id']):same=False
            attempt_values=[_number(raw[k],count=True) for k in ('attempts','passing_attempts') if k in raw and raw[k] not in (None,'')]
            attempts=attempt_values[0] if attempt_values and None not in attempt_values and len(set(attempt_values))==1 else None
            if not same:issue='Native raw revision scope/role/import clock differs from reviewed weekly source'
            elif attempts is None or attempts!=old['metrics']['G04-M01']['denominator']:issue='Fresh official attempts do not match reviewed same-row exposure'
            else:air=_number(raw.get('passing_air_yards'))
        else:issue='Reviewed raw weekly row no longer present in current retained revision; air yards unknown'
        value=air/attempts if issue is None and air is not None and attempts is not None and attempts>0 else None
        rows.append({k:deepcopy(old[k]) for k in ('season','week','team','source_player_id','player_master_id','native_game_id')}|dict(value=value,source_reported_passing_air_yards=air,official_attempts=attempts,source_revision_issue=issue,native_game_binding_basis=game_basis,
            source_field_present='passing_air_yards' in record['raw_row_json'] if record else False,raw_revision=deepcopy(record),reviewed_source_ref=deepcopy(source)))
    if set(indexed)-used:raise ValueError('Air source rows outside declared reviewed QB cohort')
    basis=dict(version=VERSION,candidate_id='G04-M04',before_period=weekly['before_period'],rows=rows,
        definition='Source-reported signed weekly passing air yards (includes incomplete passes) / matched same-row official NFL pass attempts; source-proven QB only')
    return basis|dict(semantic_sha256=digest(basis),identity_review_requests=deepcopy(weekly['identity_review_requests']),
        evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,
        limitations=['Provider-reported aggregate, not independent proof that every individual pass has charted air depth','New actual raw-field revision freeze is not the original HTTP capture or historical pregame availability','Missing raw fields/revisions or conflicting attempts stay unknown; zero attempts undefined; signed air yards preserved','Canonical collisions/unresolved identities inherited from the full reviewed weekly cohort; no name join or new alias inference'],forecast=None,model_consumed=False,optimizer_consumed=False)


def read_retained_air_projection(engine,weekly,*,cutoff):
    """Read only the old reviewed QB row IDs, retaining a new actual revision."""
    from sqlalchemy import text
    ids=[int(r['source_ref']['source_id']) for r in weekly['rows'] if r['QB_scope_source_proven']]
    if len(ids)>10000 or len(ids)!=len(set(ids)):raise ValueError('Bounded unique reviewed QB raw row IDs required')
    fields=['season_type','season','game_season','week','game_week','player_id','gsis_id','team','recent_team','position','pos','attempts','passing_attempts','passing_air_yards']
    with engine.connect() as connection:
        data=connection.execute(text('''SELECT r.raw_nfl_weekly_stat_id AS source_id,r.ingest_run_id,r.created_at AS imported_at,
        r.player_id AS source_player_id,r.season,r.week,r.team,r.position,r.game_id,
        (SELECT COALESCE(jsonb_object_agg(f.key,f.value),'{}'::jsonb) FROM jsonb_each(r.raw_row_json::jsonb) f
         WHERE f.key=ANY(CAST(:fields AS text[]))) AS raw_row_json
        FROM public.raw_nfl_weekly_stat r WHERE r.raw_nfl_weekly_stat_id=ANY(CAST(:ids AS bigint[]))
        AND r.source_system='nflreadpy' AND r.created_at AT TIME ZONE 'UTC'<=:cutoff
        ORDER BY r.raw_nfl_weekly_stat_id LIMIT 10001'''),dict(ids=ids,fields=fields,cutoff=clock(cutoff))).mappings().all()
    if len(data)>10000:raise ValueError('Retained QB source bound exceeded')
    return dict(source_kind='actual_database_retained_weekly_air_field_revision',before_period=weekly['before_period'],actual_read_at=clock(cutoff).isoformat(),
        source_projection_fields=fields,expected_reviewed_QB_rows=len(ids),rows=[dict(r,ingest_run_id=str(r['ingest_run_id']) if r['ingest_run_id'] is not None else None,imported_at=r['imported_at'].isoformat()) for r in data],
        original_availability='Current retained raw-field revision, not original immutable HTTP snapshot or historical pregame publication proof')


def load_reviewed_weekly_input(ref,*,cutoff):
    import hashlib,json
    from pathlib import Path
    from . import weekly_effectiveness_catalog_features as module
    path=Path(ref['path']).resolve();decision=clock(cutoff)
    if decision is None or decision>datetime.now(UTC):raise ValueError('Nonfuture actual read clock required')
    if path.parent!=Path('artifacts/weekly_effectiveness_catalog').resolve() or path.name!=ref['sha256']+'.json' or ref['bytes']>96*1024*1024:raise ValueError('Managed reviewed weekly source required')
    raw=path.read_bytes()
    if len(raw)!=ref['bytes'] or hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('Reviewed weekly bytes differ')
    weekly=json.loads(raw);p=weekly['provenance'];published=clock(p.get('actual_publication_at'))
    if published is None or published>decision:raise ValueError('Reviewed weekly publication unavailable/future')
    if p.get('producer_code_sha256')!=hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest():raise ValueError('Reviewed weekly producer differs')
    return weekly


def require_feature_use(value,*,purpose):
    if value.get('version')!=VERSION or value.get('pregame_serving_eligible') is not False or purpose!='offline_descriptive':raise ValueError('Revised official air aggregates cannot serve forecasts/models/optimizer')
    return value
