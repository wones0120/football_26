"""Exact retained weekly TD field revision and source-backed pair actor vectors."""
from copy import deepcopy
from datetime import datetime,UTC
from uuid import UUID
import hashlib,json
from .factual_designation import clock
from .market_snapshots import canonical_team
from .shared_scoring_pair_covariance import _count,NATIVE,VERSION as PAIR_VERSION
from .evaluation_record import digest
from .active_workload_distributions import VERSION as ACTIVE_VERSION

VERSION='shared_pair_source_fields_v1'
EXTRA_TD_FIELDS=('receiving_tds','receiving_touchdowns','passing_tds','passing_touchdowns')


def validate_td_revision(records,original_rows,*,cutoff):
    boundary=clock(cutoff)
    if boundary is None or boundary>datetime.now(UTC):raise ValueError('Nonfuture actual field-read clock required')
    old={str(r['source_id']):r for r in original_rows};seen=set();out=[]
    if len(old)!=len(original_rows)or len(old)>6000:raise ValueError('Bounded unique original raw row IDs required')
    for row in records:
        key=str(row['source_id']);prior=old.get(key)
        if key in seen or prior is None:raise ValueError('Exact original raw row ID set required')
        seen.add(key)
        for field in ('source_player_id','season','week','team','position','game_id'):
            if row.get(field)!=prior.get(field):raise ValueError('Original native weekly metadata changed')
        imported=clock(row.get('imported_at'))
        if imported is None or imported>boundary or imported!=clock(prior.get('imported_at'))or str(row.get('ingest_run_id'))!=str(prior.get('ingest_run_id')):raise ValueError('Original import/run evidence changed or future')
        current=row['raw_row_json'];original=prior['raw_row_json']
        original_json=json.dumps(original,sort_keys=True,separators=(',',':'),default=str)
        if any(k not in current for k in original)or json.dumps({k:current[k]for k in original},sort_keys=True,separators=(',',':'),default=str)!=original_json:raise ValueError('Original retained source projection changed')
        out.append({**deepcopy(row),'source_id':key,'imported_at':imported.isoformat(),'original_projection_sha256':hashlib.sha256(json.dumps(original,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()})
    if seen!=set(old):raise ValueError('Original weekly source rows missing from field revision')
    return dict(version=VERSION,actual_fields_read_at=boundary.isoformat(),rows=sorted(out,key=lambda r:r['source_id']),new_field_availability='Observed at this new capture only; original row import clock does not prove original TD-field publication',pregame_serving_eligible=False)


def read_exact_td_revision(engine,original_rows,*,cutoff):
    from sqlalchemy import text
    fields=sorted({k for r in original_rows for k in r['raw_row_json']}|set(EXTRA_TD_FIELDS));ids=sorted(str(r['source_id'])for r in original_rows)
    if not ids or len(ids)>6000 or len(ids)!=len(set(ids)):raise ValueError('Bounded exact original source IDs required')
    with engine.connect()as c:
        c.execute(text("SET LOCAL statement_timeout='15000ms'"))
        records=[]
        for offset in range(0,len(ids),3000):
            records.extend(dict(r)for r in c.execute(text("""SELECT raw_nfl_weekly_stat_id AS source_id,player_id AS source_player_id,season,week,team,position,game_id,ingest_run_id,created_at AS imported_at,
            (SELECT COALESCE(jsonb_object_agg(f.key,f.value),'{}'::jsonb) FROM jsonb_each(raw_row_json::jsonb)f WHERE f.key=ANY(CAST(:fields AS text[])))AS raw_row_json
            FROM public.raw_nfl_weekly_stat WHERE source_system='nflreadpy' AND raw_nfl_weekly_stat_id::text=ANY(CAST(:ids AS text[])) LIMIT 3001"""),dict(fields=fields,ids=ids[offset:offset+3000])).mappings())
    result=validate_td_revision(records,original_rows,cutoff=datetime.now(UTC))
    result['actual_fields_read_started_at']=clock(cutoff).isoformat()
    return result


def _td(raw,fields):
    values=[_count(raw[k])for k in fields if k in raw and raw[k]not in(None,'')]
    return values[0]if values and None not in values and len(set(values))==1 else None


def prepare_pair_actor_rows(active,weekly,extract,revision,*,before_period,cutoff):
    if active.get('version')!=ACTIVE_VERSION or active.get('pregame_serving_eligible')is not False or revision.get('version')!=VERSION:raise ValueError('Exact nonserving source parents required')
    boundary=clock(cutoff);alias_boundary=clock(extract.get('actual_alias_evidence_read_at',extract.get('actual_extracted_at')))
    if boundary is None or boundary>datetime.now(UTC)or alias_boundary is None or alias_boundary>boundary or clock(revision['actual_fields_read_at'])>boundary:raise ValueError('Actual source clocks required')
    raw={str(r['source_id']):r for r in revision['rows']};weekly_byid={str(r['source_ref']['source_id']):r for r in weekly['rows']};output=[];unbound=[]
    unbound_native={a['source_player_id']for a in active['rows']if a['season']==before_period//100 and (a['team']is None or any(not l.get('native_game_id')for l in a['logs']if a['season']*100+l['week']<before_period))}
    for actor in active['rows']:
        if actor['season']!=before_period//100:continue
        native=actor['source_player_id'];team=actor['team'];pid=actor['player_master_id']
        if not isinstance(native,str)or not NATIVE.fullmatch(native):raise ValueError('Explicit source GSIS required')
        if pid is not None and str(UUID(pid))!=pid:raise ValueError('Canonical spelling required')
        for log in actor['logs']:
            if actor['season']*100+log['week']>=before_period:continue
            gid=log.get('native_game_id');key=str(log['source_ref']['source_id']);old=weekly_byid.get(key);record=raw.get(key)
            if team is None or gid is None:unbound.append(dict(native_GSIS=native,team=team,week=log['week'],source_id=key));continue
            if old is None or record is None:raise ValueError('Every prepared source log needs original weekly/TD revision evidence')
            if (old['source_player_id'],old['season'],old['week'],old['team'],old['player_master_id'])!=(native,actor['season'],log['week'],team,pid):raise ValueError('Original native role/count/canonical scope differs')
            if log['source_ref']!=old['source_ref']:raise ValueError('Original weekly source receipt differs')
            for ch,mid in (('pass_attempts','G04-M01'),('targets','G09-M01')):
                if log['counts'][ch]!=old['metrics'].get(mid,{}).get('denominator'):raise ValueError('Same-row official exposure differs')
            parts=gid.split('_')
            if len(parts)!=4 or parts[:2]!=[str(actor['season']),f"{log['week']:02d}"]or team not in {canonical_team(t)for t in parts[2:]}or old.get('native_game_id')not in(None,'',gid)or record.get('game_id')not in(None,'',gid):raise ValueError('Native actor game binding differs')
            r=record['raw_row_json'];role=actor['source_position'];role_known=role==old['source_position']==record['position']and(role!='QB'or old['QB_scope_source_proven'])and all(r.get(k)in(None,'',role)for k in ('position','pos'))
            positive=log['positive_offensive_participation_proven'];proof=log.get('participation_ref');participation=None
            if positive:
                n=_count(proof.get('offense_snaps'))if proof else None
                if n is None or n<=0 or (proof['native_game_id'],proof['season'],proof['week'],proof['team'],proof['player_master_id'])!=(gid,actor['season'],log['week'],team,pid):raise ValueError('Positive native participation proof differs')
                participation=True
            aliases=log['source_ref'].get('native_alias_evidence',[]);candidates=set()
            for alias in aliases:
                if alias.get('source_key')!=native or alias.get('source_system')!='nflreadpy'or clock(alias.get('created_at'))is None or clock(alias['created_at'])>alias_boundary:raise ValueError('Frozen native alias evidence scope/clock differs')
                candidates.add(alias['player_master_id'])
            identity=pid is not None and candidates=={pid}
            output.append(dict(game_id=gid,team=team,native_GSIS=native,source_position=role if role_known else None,participation=participation,identity_proven=identity,player_master_id=pid,canonical_candidate_ids=sorted(candidates),source_scope_proven=native not in unbound_native,
                official_pass_attempts=log['counts']['pass_attempts'],official_targets=log['counts']['targets'],official_passing_TDs=_td(r,('passing_tds','passing_touchdowns')),official_receiving_TDs=_td(r,('receiving_tds','receiving_touchdowns')),
                source_ref=deepcopy(log['source_ref']),TD_field_revision_source_id=key,participation_ref=deepcopy(proof),source_role_proven=role_known))
    return dict(actor_rows=output,unbound_source_rows=unbound,unbound_native_scope_keys=sorted(unbound_native),positive_participants_missing_weekly_rows=deepcopy(active['positive_participants_missing_weekly_rows']),unresolved_participation_rows=deepcopy(active['unresolved_participation_rows']))


def persist_pair_identity_requests(connection,features,*,source_refs):
    """Append or retain native review cases; never alter resolved status/aliases."""
    from sqlalchemy import text
    import hashlib,json
    if features.get('version')!=PAIR_VERSION or features.get('pregame_serving_eligible')is not False:raise ValueError('Exact nonserving shared-pair source contract required')
    entries=[]
    for q in features['identity_review_requests']:
        system=q['source_system'];native=q['source_key'];proof=q.get('evidence')or{};evidence=proof.get('original_alias_evidence',[])
        conflict=True;table='player_alias'if conflict else'source_snapshot'
        key=('shared-pair-frozen-identity:'+system+':'+native+':'+digest(evidence))if conflict else('nflreadpy-gsis:'+native if system=='nflreadpy'else'pfr-player:'+native)
        entries.append(dict(qid='shared-pair-native:'+hashlib.sha256(key.encode()).hexdigest()[:32],table=table,key=key,system=system,native=native,
            season=int(q['game_id'][:4]),week=int(q['game_id'].split('_')[1]),team=q['team'],reason='shared_pair_'+q['reason'],
            candidates=json.dumps(sorted({str(a['player_master_id'])for a in evidence}))))
    if len(entries)>1000:raise ValueError('Bounded native identity queue required')
    if not entries:return dict(requests=0,created_new=0,existing_unchanged=0,records=[])
    read=text("SELECT identity_quarantine_id,source_table,source_record_key,source_player_key,status,first_seen_at,updated_at FROM target.identity_quarantine WHERE source_schema='public' AND source_record_key=ANY(CAST(:keys AS text[]))")
    keys=sorted({e['key']for e in entries});before={(r['source_table'],r['source_record_key']):dict(r)for r in connection.execute(read,dict(keys=keys)).mappings()}
    connection.execute(text("""INSERT INTO target.identity_quarantine
        (identity_quarantine_id,entity_type,source_schema,source_table,source_record_key,source_system,season,week,slate,source_player_key,
         display_name,team_id,position,reason_code,candidate_player_ids,status,first_seen_at,updated_at)
        VALUES (:qid,'player','public',:table,:key,:system,:season,:week,'FEATURE_INVENTORY',:native,NULL,:team,NULL,:reason,CAST(:candidates AS jsonb),'open',now(),now())
        ON CONFLICT(source_schema,source_table,source_record_key) DO NOTHING"""),entries)
    after={(r['source_table'],r['source_record_key']):dict(r)for r in connection.execute(read,dict(keys=keys)).mappings()};records=[];created=0
    for e in entries:
        key=(e['table'],e['key']);value=after.get(key)
        if value is None:raise ValueError('Durable native review readback missing')
        if key in before:
            if before[key]!=value:raise ValueError('Existing native review case unexpectedly changed')
        else:created+=1
        records.append({**value,'source_refs':deepcopy(source_refs),'created_new':key not in before})
    return dict(requests=len(entries),created_new=created,existing_unchanged=len(entries)-created,records=records,
        alias_or_canonical_mutations=False,resolved_cases_reopened=False)
