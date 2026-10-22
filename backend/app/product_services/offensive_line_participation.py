"""Historical source-proven starting OL family continuity, no projected starters."""
from collections import Counter,defaultdict
from copy import deepcopy
from datetime import datetime,UTC,date
from decimal import Decimal,InvalidOperation
from uuid import UUID
import re
from .evaluation_record import digest
from .factual_designation import clock
from .market_snapshots import canonical_team
from .participation_source_components import VERSION as SOURCE_VERSION,_int
from .fumble_event_components import _eligibility,_flag,INDICATORS

VERSION='offensive_line_participation_v1'
FAMILIES={'C':1,'G':2,'T':2}


def resolve_line_identity(native_ids,alias_rows,*,cutoff):
    boundary=clock(cutoff);eligible=defaultdict(list);future=[]
    for r in alias_rows:
        if r['source_system']!='nflreadpy'or r['source_key']not in native_ids:raise ValueError('Exact requested native GSIS alias evidence required')
        if not re.fullmatch(r'00-\d{7}',r['source_key']):raise ValueError('Native GSIS alias key required')
        created=clock(r['created_at']);master_created=clock(r['player_master_created_at']);pid=r['player_master_id']
        if str(UUID(str(pid)))!=pid:raise ValueError('Canonical UUID spelling required')
        receipt={**deepcopy(r),'created_at_UTC':created.isoformat()}
        if created>boundary or master_created>boundary:future.append(receipt)
        else:eligible[r['source_key']].append(receipt)
    values={n:next(iter({r['player_master_id']for r in eligible[n]}))if len({r['player_master_id']for r in eligible[n]})==1 else None for n in native_ids}
    inverse=defaultdict(set)
    for native,pid in values.items():
        if pid is not None:inverse[pid].add(native)
    conflicting={n for ns in inverse.values()if len(ns)>1 for n in ns}|{n for n in native_ids if len({r['player_master_id']for r in eligible[n]})>1}
    receipts={}
    for native in sorted(native_ids):
        receipts[native]=dict(player_master_id=None if native in conflicting else values[native],
            status='canonical_native_conflict'if native in conflicting else 'unique_native_alias'if values[native]is not None else 'unresolved_native_key',
            original_alias_evidence=sorted(eligible[native],key=lambda r:(str(r.get('alias_id')),r['player_master_id'])))
    return receipts,future


def _physical(r):
    flags=[_flag(r.get(k))for k in ('pass_attempt','rush_attempt','sack')]
    union=True if True in flags else False if all(v is False for v in flags)else None
    eligible=_eligibility(r)[0]
    if r.get('play_type')=='no_play'or _flag(r.get('no_play'))is True:
        if r.get('play_type_nfl')=='TIMEOUT'and all(_flag(r.get(k))is not True for k in INDICATORS):return False
        if r.get('play_type_nfl')=='PENALTY'or union is not False:return None
    if _flag(r.get('two_point_attempt'))is True and union is not False:return None
    return False if eligible is False or union is False else True if eligible is True and union is True else None


def _order(v):
    if v in (None,'')or isinstance(v,bool):return None
    try:n=Decimal(str(v))
    except InvalidOperation:return None
    return n if n.is_finite()else None


def build_offensive_line_continuity(participation,pbp_rows,schedule_games,alias_rows,*,before_period,cutoff,identity_universe=None):
    if participation.get('version')!=SOURCE_VERSION or participation.get('pregame_serving_eligible')is not False:raise ValueError('Verified historical native participation required')
    season=participation['season'];expected={};teams=defaultdict(list);timeline=defaultdict(list);seen=set();sources={}
    for r in schedule_games:
        if r['season']!=season or r['game_type']!='REG'or r['season']*100+r['week']>=before_period:continue
        gid=r['game_id'];parts=gid.split('_')
        if len(parts)!=4 or parts[:2]!=[str(season),f"{r['week']:02d}"]or gid in expected:raise ValueError('Unique native expected schedule game required')
        sides={canonical_team(t)for t in parts[2:]}
        if sides!={r['home_team'],r['away_team']}:raise ValueError('Native schedule sides differ')
        expected[gid]=r
        for team in sides:teams[team].append(r)
    for r in participation['rows']:
        key=(r['game_id'],r['play_id'])
        if key in sources:raise ValueError('Duplicate native participation play')
        sources[key]=r
    for r in pbp_rows:
        gid=r['game_id'];year=_int(r['season']);week=_int(r['week']);play=str(_int(r['play_id']));parts=gid.split('_')
        if len(parts)!=4 or parts[:2]!=[str(year),f'{week:02d}']or year!=season:raise ValueError('Native PBP game/period differs')
        key=(gid,play)
        if key in seen:raise ValueError('Duplicate native PBP game/play')
        seen.add(key)
        if r.get('season_type')!='REG'or year*100+week>=before_period:continue
        if gid not in expected:raise ValueError('Observed game missing expected schedule cohort')
        team=canonical_team(r['posteam'])if r.get('posteam')else None
        if team is not None and team not in {canonical_team(t)for t in parts[2:]}:raise ValueError('Native offense contradicts game')
        start=r.get('play_type_nfl')=='GAME_START'and all(_flag(r.get(k))is not True for k in (*INDICATORS,'fumble'))
        timeline[gid].append(dict(game_id=gid,play_id=play,team=team,order=_order(r.get('order_sequence')),physical=_physical(r),native_start=start))
    units=[];native_ids=set()
    for gid,schedule in sorted(expected.items()):
        events=timeline[gid];starts=[r for r in events if r['native_start']];orders=[r['order']for r in events if r['order']is not None]
        beginning=starts[0]if len(starts)==1 and starts[0]['order']is not None and len(orders)==len(set(orders))else None
        for team in {schedule['home_team'],schedule['away_team']}:
            reason=None;first=None;members=[]
            possible=[r for r in events if r['physical']is not False and r['team']in (None,team)]
            known=[r for r in possible if r['physical']is True and r['team']==team and r['order']is not None]
            if beginning is None:reason='Missing/ambiguous native game beginning or order'
            elif not known:reason='No proven first physical offensive snap'
            else:
                first=min(known,key=lambda r:r['order'])
                if beginning['order']>=first['order']or any(r['order']is None or r['order']<first['order']for r in possible if r is not first):reason='Earlier possible offensive snap or missing native order'
            source=sources.get((gid,first['play_id']))if first else None
            if reason is None:
                scope=source['participant_scopes']['offense']if source else None
                if source is None or source['possession_team']!=team or source['native_phase']not in (None,'REG'):reason='Missing/conflicting first-snap participation'
                elif scope['position_by_native_id']is None or scope['native_player_ids']is None or len(scope['native_player_ids'])!=11:reason='First-snap native participant/position proof incomplete'
                else:
                    members=[dict(source_player_id=n,position_family=p)for n,p in scope['position_by_native_id'].items()if p in FAMILIES]
                    if Counter(r['position_family']for r in members)!=Counter(FAMILIES):reason='Starting unit is not exactly C1/G2/T2; no five-player selection shortcut'
            if reason is None:native_ids.update(r['source_player_id']for r in members)
            units.append(dict(game_id=gid,season=season,team=team,game_date=schedule.get('game_date'),native_start_play_id=beginning['play_id']if beginning else None,
                first_physical_play_id=first['play_id']if first else None,source_proven_starting_unit=reason is None,unknown_reason=reason,
                native_line_members=sorted(members,key=lambda r:(r['position_family'],r['source_player_id'])),
                beginning_basis='Unique native GAME_START and retained native-order timeline, no earlier possible offense'if reason is None else None))
    return _finish_units(units,teams,native_ids,alias_rows,before_period=before_period,cutoff=cutoff,season=season,identity_universe=identity_universe,participation_semantic_sha256=participation['semantic_sha256'])


def _finish_units(units,teams,native_ids,alias_rows,*,before_period,cutoff,season,identity_universe,participation_semantic_sha256):
    universe=set(identity_universe)if identity_universe is not None else native_ids
    if not native_ids<=universe or any(not re.fullmatch(r'00-\d{7}',n)for n in universe):raise ValueError('Verified full native identity universe required')
    aliases,future=resolve_line_identity(universe,alias_rows,cutoff=cutoff);requests=[]
    for u in units:
        for member in u['native_line_members']:
            native=member['source_player_id'];proof=aliases.get(native)
            member['player_master_id']=proof['player_master_id']if proof else None
            member['identity_status']=proof['status']if proof else 'unqualified_start_unit'
            if u['source_proven_starting_unit']and proof['status']!='unique_native_alias':requests.append(dict(game_id=u['game_id'],team=u['team'],source_player_id=native,position=member['position_family'],reason=proof['status'],alias_evidence=deepcopy(proof['original_alias_evidence'])))
    index={(r['game_id'],r['team']):r for r in units};comparisons=[]
    for team,games in sorted(teams.items()):
        dates=[r.get('game_date')for r in games];order_known=all(isinstance(d,str)and len(d)>=10 for d in dates)and len(dates)==len(set(dates))
        if order_known:
            try:
                for d in dates:date.fromisoformat(d[:10])
            except ValueError:order_known=False
        games=sorted(games,key=lambda r:r['game_date'])if order_known else sorted(games,key=lambda r:r['game_id'])
        previous=None
        for game in games:
            current=index[(game['game_id'],team)];prior=index[(previous['game_id'],team)]if previous else None
            reason=None if order_known else 'Native same-team game chronology unknown'
            if prior is None:reason=reason or 'No previous same-season scheduled game'
            elif not prior['source_proven_starting_unit']or not current['source_proven_starting_unit']:reason=reason or 'Current/previous scheduled game starting unit unproven; do not skip missing game'
            overlap=None;value=None;canonical=None
            if reason is None:
                old={(m['source_player_id'],m['position_family'])for m in prior['native_line_members']};new={(m['source_player_id'],m['position_family'])for m in current['native_line_members']};overlap=len(old&new)
                conflict=any(m['identity_status']=='canonical_native_conflict'for m in prior['native_line_members']+current['native_line_members'])
                value=None if conflict else overlap/5
                if conflict:reason='Contradictory native/canonical alias group withheld'
                if all(m['player_master_id']is not None for m in prior['native_line_members']+current['native_line_members']):canonical=value
            comparisons.append(dict(game_id=current['game_id'],team=team,previous_same_season_game_id=prior['game_id']if prior else None,
                value=value,unit='same_native_actor_and_CGT_role_family_retained_fraction_of_five',known_native_overlap=overlap,
                canonical_qualified_value=canonical,unknown_reason=reason))
            previous=game
    core=dict(version=VERSION,catalog_id='G13-M01',before_period=before_period,season=season,starting_units=sorted(units,key=lambda r:(r['game_id'],r['team'])),
        continuity_rows=sorted(comparisons,key=lambda r:(r['game_id'],r['team'])),native_identity_receipts=aliases,identity_review_requests=sorted(requests,key=lambda r:(r['game_id'],r['team'],r['source_player_id'])))
    return dict(**core,semantic_sha256=digest(core),future_alias_evidence_excluded=future,
        provenance=dict(participation_semantic_sha256=participation_semantic_sha256,actual_alias_cutoff_at=clock(cutoff).isoformat()),
        evidence_use='historical_postseason_revised_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None,
        limitations=['Observed first physical offensive snap, not pregame expected starters/health/availability','Generic C/G/T role families, no LT/RT assignment or blocking win-rate inference','Source-native GSIS continuity remains named separately from complete canonical linkage; unresolved aliases require queue','Native/canonical collisions withheld across entire batch, never arbitrarily selected','Same-season/team consecutive scheduled game comparison, no skip over missing units; full-game end coverage is irrelevant to start proof'])


def load_line_alias_evidence(connection,native_ids,*,cutoff):
    from sqlalchemy import text
    keys=sorted(set(native_ids))
    if len(keys)>10000 or any(not re.fullmatch(r'00-\d{7}',n)for n in keys):raise ValueError('Bounded native GSIS scope required')
    rows=connection.execute(text("""SELECT a.alias_id,a.source_system,a.source_key,a.player_master_id,
        a.created_at AT TIME ZONE 'UTC' AS created_at,p.created_at AT TIME ZONE 'UTC' AS player_master_created_at
        FROM public.player_alias a JOIN public.player_master p USING(player_master_id)
        WHERE a.source_system='nflreadpy' AND a.source_key=ANY(CAST(:keys AS text[]))
        AND a.created_at AT TIME ZONE 'UTC'<=:cutoff AND p.created_at AT TIME ZONE 'UTC'<=:cutoff ORDER BY a.source_key,a.alias_id"""),dict(keys=keys,cutoff=clock(cutoff))).mappings().all()
    return [{**dict(r),'created_at':clock(r['created_at']).isoformat(),'player_master_created_at':clock(r['player_master_created_at']).isoformat()}for r in rows]


def persist_line_identity_requests(connection,features,*,source_refs):
    """Append only; no alias or resolved review status mutation."""
    from sqlalchemy import text
    import json,hashlib
    requests=defaultdict(list)
    for block in features:
        if block.get('version')!=VERSION or block.get('pregame_serving_eligible')is not False:raise ValueError('Exact nonserving line source package required')
        for row in block['identity_review_requests']:requests[(row['source_player_id'],row['reason'])].append(row)
    output=[]
    for (native,reason),incidents in sorted(requests.items()):
        candidates=sorted({r['player_master_id']for q in incidents for r in q['alias_evidence']})
        evidence=[{k:r[k]for k in ('alias_id','source_key','player_master_id','created_at')}for q in incidents for r in q['alias_evidence']]
        key='nflreadpy-gsis:'+native if reason=='unresolved_native_key'else 'line-alias-conflict:'+native+':'+digest(sorted({digest(r):r for r in evidence}.values(),key=lambda r:(str(r['alias_id']),r['source_key'])))
        qid='line-native:'+hashlib.sha256(key.encode()).hexdigest()[:32];first=min(incidents,key=lambda r:r['game_id']);parts=first['game_id'].split('_')
        connection.execute(text("""INSERT INTO target.identity_quarantine
        (identity_quarantine_id,entity_type,source_schema,source_table,source_record_key,source_system,season,week,slate,
         source_player_key,display_name,team_id,position,reason_code,candidate_player_ids,status,first_seen_at,updated_at)
        VALUES (:qid,'player','public',:table,:key,'nflreadpy',:season,:week,'FEATURE_INVENTORY',:native,NULL,:team,:position,:reason,CAST(:candidates AS jsonb),'open',now(),now())
        ON CONFLICT (source_schema,source_table,source_record_key) DO NOTHING"""),dict(qid=qid,table='player_alias'if reason=='canonical_native_conflict'else 'source_snapshot',key=key,native=native,
            season=int(parts[0]),week=int(parts[1]),team=first['team'],position=first['position'],reason='ol_'+reason,candidates=json.dumps(candidates)))
        output.append(dict(source_record_key=key,source_table='player_alias'if reason=='canonical_native_conflict'else 'source_snapshot',identity_quarantine_id=qid,
            source_player_id=native,reason=reason,all_native_game_ids=sorted({r['game_id']for r in incidents}),original_alias_evidence=evidence))
    return dict(records=output,requests=len(output),source_refs=deepcopy(source_refs),policy='Append only; conflict preserves existing resolved records; no player/alias mutation; display name never joins')


def reattach_line_identities(value,alias_rows,*,cutoff,identity_universe):
    """Rebind one already-derived native unit cohort; no second source load.

    Caller authenticates the source-derived cohort, never a user-authored payload.
    """
    if value.get('version')!=VERSION or value.get('pregame_serving_eligible')is not False:raise ValueError('Exact offline source-derived line cohort required')
    units=deepcopy(value['starting_units']);teams=defaultdict(list);natives=set()
    for unit in units:
        teams[unit['team']].append(dict(game_id=unit['game_id'],game_date=unit['game_date']))
        if unit['source_proven_starting_unit']:natives.update(m['source_player_id']for m in unit['native_line_members'])
    return _finish_units(units,teams,natives,alias_rows,before_period=value['before_period'],cutoff=cutoff,season=value['season'],
        identity_universe=identity_universe,participation_semantic_sha256=value['provenance']['participation_semantic_sha256'])
