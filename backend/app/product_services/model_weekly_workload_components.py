"""Frozen all-native source counts, scoped actors and source-observed budgets.

No original historical availability or complete NFL participant census is implied.
"""
from collections import defaultdict
from copy import deepcopy
from .weekly_effectiveness_catalog_features import _values,DEFINITIONS,SOURCE_FIELDS
from .market_snapshots import canonical_team
from .evaluation_record import digest
from .factual_designation import clock

VERSION='model_weekly_workload_components_v1'
CHANNEL_FIELDS={'pass_attempts':'attempts','rush_attempts':'carries','targets':'targets'}
FIELDS=tuple(sorted({f for definition in DEFINITIONS.values()for f in definition[:2]}))


def project_weekly_components(weekly,extract,schedule,*,positive_missing=()):
    if weekly.get('version')!='weekly_effectiveness_catalog_features_v1'or weekly.get('pregame_serving_eligible')is not False or extract.get('before_period')!=weekly['before_period']:raise ValueError('Matching approved weekly/raw contracts required')
    decision=clock(extract.get('actual_extracted_at')or extract.get('actual_read_at'))
    if decision is None:raise ValueError('Original frozen raw read clock required')
    expected={};games={}
    for g in schedule:
        if g['game_type']!='REG':continue
        gid=g['game_id'];s,w=g['season'],g['week'];pair={canonical_team(g['home_team']),canonical_team(g['away_team'])}
        if gid in games or gid.split('_')[:2]!=[str(s),f'{w:02d}']or pair!={canonical_team(t)for t in gid.split('_')[2:]}or len(pair)!=2:raise ValueError('Unique native schedule required')
        games[gid]=g
        for t in pair:
            key=(s,w,t)
            if key in expected:raise ValueError('Unique scheduled native team/week required')
            expected[key]=gid
    reviewed={str(r['source_ref']['source_id']):r for r in weekly['rows']}
    if len(reviewed)!=len(weekly['rows']):raise ValueError('Unique reviewed raw source IDs required')
    rows=[];unscoped=[];source_ids=set();seen_reviewed=set()
    for original in extract['rows']:
        sid=str(original['source_id']);s,w=original['season'],original['week'];raw=original['raw_row_json'];r=reviewed.get(sid)
        if sid in source_ids or type(s)is not int or type(w)is not int or not 1<=w<=18 or s*100+w>=weekly['before_period']or raw.get('season_type')!='REG':raise ValueError('Unique prior REG raw source revision required')
        source_ids.add(sid)
        if not original.get('ingest_run_id')or clock(original.get('imported_at'))is None or clock(original['imported_at'])>decision:raise ValueError('Original source import/ingest clock required and bounded')
        for field,value in(('season',s),('game_season',s),('week',w),('game_week',w)):
            if raw.get(field)is not None and str(raw[field])not in(str(value),str(float(value))):raise ValueError('Raw period aliases disagree')
        values,quality=_values(raw);teams=set();bad_team=False
        for value in(original.get('team'),raw.get('team'),raw.get('recent_team')):
            if value not in(None,''):
                try:teams.add(canonical_team(value))
                except ValueError:bad_team=True
        team=next(iter(teams))if len(teams)==1 and not bad_team else None;gid=expected.get((s,w,team))if team else None
        native=original.get('source_player_id');valid_native=isinstance(native,str)and len(native)==10 and native.startswith('00-')and native[3:].isdigit()
        for field in('player_id','gsis_id'):
            if raw.get(field)not in(None,native):valid_native=False
        scope_conflict=False
        for value in(original.get('game_id'),raw.get('game_id'),raw.get('gameid'),raw.get('old_game_id')):
            # old_game_id is a different namespace; a provider legacy value is
            # not silently treated as the current native game identifier.
            if value not in(None,'')and str(value).count('_')==3 and value!=gid:scope_conflict=True
        if r is not None:
            seen_reviewed.add(sid);ref=r['source_ref']
            if (r['season'],r['week'],r['source_player_id'],r['team'])!=(s,w,native,team)or ref['ingest_run_id']!=original.get('ingest_run_id')or ref['imported_at']!=original['imported_at']or ref['projected_source_row_sha256']!=digest({k:v for k,v in raw.items()if k in SOURCE_FIELDS}):raise ValueError('Reviewed row/native revision binding differs')
            if r['native_game_id']not in(None,'',gid):scope_conflict=True
        if gid is None or scope_conflict:
            compatible=[(t,g)for(ss,ww,t),g in expected.items()if(ss,ww)==(s,w)and(not teams or t in teams)]
            if not compatible:raise ValueError('Unscoped source has no compatible native game')
            for t,g in compatible:unscoped.append(dict(game_id=g,possible_teams=[t],source_id=sid,counts={c:values[f]for c,f in CHANNEL_FIELDS.items()},reason='raw_team_or_native_game_scope_conflict',reported_values=values))
            continue
        roles={x for x in(original.get('position'),raw.get('position'),raw.get('pos'))if x not in(None,'')};role=next(iter(roles))if len(roles)==1 else None
        pid=r['player_master_id']if r is not None and valid_native else None
        adjusted={k:v if valid_native or v==0 else None for k,v in values.items()}
        rows.append(dict(game_id=gid,season=s,week=w,team=team,source_id=sid,source_player_id=native if valid_native else None,player_master_id=pid,source_position=role,source_QB_proven=bool(valid_native and role=='QB'and r is not None and r['QB_scope_source_proven']),values=adjusted,reported_values=values if not valid_native else None,counts={c:adjusted[f]for c,f in CHANNEL_FIELDS.items()},quality=quality,imported_at=original['imported_at'],source_ref=({k:r['source_ref'].get(k)for k in('source_id','ingest_run_id','imported_at','projected_source_row_sha256')}|dict(native_alias_evidence_sha256=digest(r['source_ref'].get('native_alias_evidence',[]))))if r else dict(source_id=sid,ingest_run_id=original.get('ingest_run_id'),imported_at=original['imported_at']),malformed_native_possible_contribution=not valid_native,native_game_binding_basis='unique_source_REG_season_week_team_to_native_schedule; present native game IDs corroborated',original_game_evidence=dict(indexed_game_id=original.get('game_id'),**{k:raw.get(k)for k in('game_id','gameid','old_game_id')})))
    if seen_reviewed!=set(reviewed):raise ValueError('Every reviewed actor row requires exact raw counterpart')
    grouped=defaultdict(list)
    for r in rows:
        if r['source_player_id']is not None:grouped[(r['game_id'],r['source_player_id'])].append(r)
    duplicates={key for key,group in grouped.items()if len(group)>1};clean=[]
    for r in rows:
        key=(r['game_id'],r['source_player_id'])
        if key in duplicates:
            unscoped.append(dict(game_id=r['game_id'],possible_teams=[r['team']],source_id=r['source_id'],counts=dict.fromkeys(CHANNEL_FIELDS),reported_values=r['reported_values']or r['values'],reason='duplicate_native_actor_contribution'))
        else:clean.append(r)
    rows=clean;threats=defaultdict(list)
    for p in positive_missing:
        key=(p['season'],p['week'],canonical_team(p['team']));gid=expected.get(key)
        if gid is None or gid!=p['native_game_id']or type(p.get('offense_snaps'))not in(int,float)or not p['offense_snaps']>0:raise ValueError('Exact scoped positive-missing evidence required')
        threats[(gid,key[2])].append(deepcopy(p))
    bygame=defaultdict(list)
    for r in rows:bygame[(r['game_id'],r['team'])].append(r)
    unknown=defaultdict(list)
    for u in unscoped:
        for t in u['possible_teams']:unknown[(u['game_id'],t)].append(u)
    teams=[]
    for (s,w,t),gid in sorted(expected.items()):
        if s*100+w>=weekly['before_period']:continue
        rs=bygame[(gid,t)];missing=threats[(gid,t)];unassigned=unknown[(gid,t)];totals={}
        for field in FIELDS:
            nums=[r['values'][field]for r in rs];possible=any(u.get('reported_values',{}).get(field)!=0 for u in unassigned)
            totals[field]=sum(nums)if rs and all(v is not None for v in nums)and not missing and not possible else None
        teams.append(dict(game_id=gid,season=s,week=w,team=t,values=totals,source_rows=len(rs),unknown_native_scope_rows=len(unassigned),positive_missing_rows=len(missing),participant_census='BOUNDED_SOURCE_EVIDENCE_ONLY'if missing else'UNKNOWN',source_qualified_observed_total_not_NFL_census=True))
    core=dict(version=VERSION,before_period=weekly['before_period'],actor_rows=rows,team_game_rows=teams,unscoped_contributions=unscoped,positive_missing=deepcopy(list(positive_missing)),source_observed_universe='All retained raw native actors, before position/UUID filters; duplicate/conflicting contributions masked',historical_participant_census='UNKNOWN')
    return dict(**core,semantic_sha256=digest(core))
