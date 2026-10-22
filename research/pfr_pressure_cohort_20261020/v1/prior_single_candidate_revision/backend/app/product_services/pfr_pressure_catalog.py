"""Catalog views of source-compatible HHS pressure/dropback observations."""
from copy import deepcopy
from .pfr_pressure_cohort import VERSION as SOURCE_VERSION
from .evaluation_record import digest

VERSION='pfr_pressure_catalog_v1'


def build_pressure_catalog(source):
    if source.get('version')!=SOURCE_VERSION or source.get('pregame_serving_eligible')is not False:raise ValueError('Exact nonserving pressure cohort required')
    rows=[];requests={}
    for g in source['game_rows']:
        row=deepcopy(g)
        row['metrics']={mid:dict(value=g['pressure_rate'],known_pressure_count=g['known_pressure_lower_bound'],known_physical_nonspike_dropbacks=g['known_dropbacks'],exact_pressure_count=g['known_pressure_lower_bound']if g['full_observed_cohort_proven']else None,exact_dropback_count=g['known_dropbacks']if g['full_observed_cohort_proven']else None,unit='PFR_HHS_pressures_per_official_nonspike_physical_dropback',perspective=perspective)for mid,perspective in (('G13-M03','offense_pressure_allowed'),('G14-M01','opposing_offense_pressure_generated'))}
        rows.append(row)
    profiles=[]
    for season,team in sorted({(g['season'],g['offense'])for g in rows}):
        for mid,axis in (('G13-M03','offense'),('G14-M01','defense')):
            gs=[g for g in rows if g['season']==season and g[axis]==team];known=[g for g in gs if g['full_observed_cohort_proven']];num=sum(g['known_pressure_lower_bound']for g in known);den=sum(g['known_dropbacks']for g in known)
            profiles.append(dict(season=season,team=team,catalog_id=mid,observed_game_ids=[g['game_id']for g in gs],known_complete_games=len(known),unknown_games=len(gs)-len(known),known_complete_pressure_sum=num,known_complete_dropback_sum=den,known_complete_sample_rate=num/den if den else None,value=num/den if len(known)==len(gs)and den else None,unit='PFR_HHS_pressures_per_official_nonspike_physical_dropback'))
    basis=source['provenance']['official_dropback_cohort']['event_basis'];native_context={e['native_passer']:(e['game_id'],e['offense'])for e in basis if e['native_passer_valid']}
    for r in source['provenance']['PFR_raw_actor_rows']:native_context[('pfr',r['pfr_player_id'])]=(r['game_id'],r['team'])
    for system,name in (('nflreadpy','native_GSIS_identity_proofs'),('pfr','native_PFR_identity_proofs')):
        for native,proof in source[name].items():
            if proof['player_master_id']is not None:continue
            gid,team=native_context[native if system=='nflreadpy'else(system,native)]
            requests[(system,native)]=dict(source_system=system,source_key=native,reason=proof['status'],evidence=deepcopy(proof),game_id=gid,team=team)
    core=dict(version=VERSION,catalog_ids=['G13-M03','G14-M01'],game_rows=rows,profiles=profiles,identity_review_requests=list(requests.values()),
        definition='Same-event all-native-passer PFR hurry+hit+sack pressures over exact compatible official nonspike physical dropback cohort; offense and opposite defense perspectives',
        evidence_use='historical_revised_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None,
        limitations=['Observed retained source logs, not independently complete games or original historical pregame inputs','Compatible cohort requires every native actor, per-passer sacks and rounded native percentage check; unknown or incompatible games remain null','PFR HHS attribution, not causal offensive-line or individual defender assignment','No raw percentage inversion, defender-vote sums, missing-to-zero repair or future pressure forecast'])
    return dict(**core,semantic_sha256=digest(core))


def persist_pressure_identity_requests(connection,features,*,source_refs):
    """Append or retain native review cases; never alter resolved status/aliases."""
    from sqlalchemy import text
    import hashlib,json
    if features.get('version')!=VERSION or features.get('pregame_serving_eligible')is not False:raise ValueError('Exact nonserving pressure catalog contract required')
    entries=[]
    for q in features['identity_review_requests']:
        system=q['source_system'];native=q['source_key'];proof=q.get('evidence')or{};evidence=proof.get('original_alias_evidence',[])
        conflict=q['reason']=='canonical_native_conflict';table='player_alias'if conflict else'source_snapshot'
        key=('pressure-native-conflict:'+system+':'+native+':'+digest(evidence))if conflict else('nflreadpy-gsis:'+native if system=='nflreadpy'else'pfr-player:'+native)
        entries.append(dict(qid='pressure-native:'+hashlib.sha256(key.encode()).hexdigest()[:32],table=table,key=key,system=system,native=native,
            season=int(q['game_id'][:4]),week=int(q['game_id'].split('_')[1]),team=q['team'],reason='pressure_'+q['reason'],
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
