"""Observed source-QB scramble fraction on the same provider-pressured dropback."""
from collections import defaultdict
import re
from .participation_defense_catalog import VERSION as BASIS_VERSION
from .participation_source_components import VERSION as PART_VERSION,_int
from .fumble_event_components import _flag
from .market_snapshots import canonical_team
from .evaluation_record import digest

VERSION='provider_pressure_scramble_v1'


def _native(value):
    if value is None or value=='':return None
    if not isinstance(value,str) or not re.fullmatch(r'00-\d{7}',value):raise ValueError('Native GSIS identity required, never name join')
    return value


def _summary(events):
    known=[e for e in events if e['eligible_pressure_for_actor'] is True]
    uncertain=sum(e['eligible_pressure_for_actor'] is None for e in events)
    successes=sum(e['same_actor_official_scramble'] is True for e in known)
    unknown_outcomes=sum(e['same_actor_official_scramble'] is None for e in known)
    n=len(known);sample=sum(e['same_actor_official_scramble'] is not None for e in known)
    return dict(known_pressured_dropbacks=n,known_same_QB_scrambles=successes,unknown_pressured_membership=uncertain,unknown_scramble_outcomes=unknown_outcomes,
        exact_pressured_dropbacks=n if not uncertain else None,exact_scrambles=successes if not uncertain and not unknown_outcomes else None,
        scramble_fraction=successes/n if n and not uncertain and not unknown_outcomes else None,
        known_outcome_sample_fraction=successes/sample if sample else None,zero_known_pressure_denominator=n==0)


def build_provider_pressure_scrambles(basis,participation,pbp_rows):
    if basis.get('version')!=BASIS_VERSION or participation.get('version')!=PART_VERSION or any(x.get('pregame_serving_eligible')is not False for x in(basis,participation)):raise ValueError('Reviewed nonserving source bases required')
    if basis['season']!=participation['season']:raise ValueError('Matched native season required')
    year=basis['season'];before=basis['before_period'];raw_index={};part_index={};cohort=defaultdict(set);universe=set();game_info={}
    for p in participation['rows']:
        key=(p['game_id'],p['play_id'])
        if key in part_index:raise ValueError('Unique native participation key required')
        part_index[key]=p
    for r in pbp_rows:
        if r.get('season_type')!='REG':continue
        season=_int(r['season']);week=_int(r['week']);gid=r['game_id'];pid=_int(r['play_id'])
        if season!=year or week is None or pid is None or gid.split('_')[:2]!=[str(year),f'{week:02d}']:raise ValueError('Native REG period/play required')
        if season*100+week>=before:continue
        pair={canonical_team(t)for t in gid.split('_')[2:]}
        if len(pair)!=2:raise ValueError('Native game team pair required')
        key=(gid,str(pid))
        if key in raw_index:raise ValueError('Unique native PBP event required')
        raw_index[key]=r;game_info[gid]=dict(season=season,week=week,sides=pair)
        for field in('passer_player_id','rusher_player_id'):
            native=_native(r.get(field))
            if native:universe.add(native)
        p=part_index.get(key);off=canonical_team(r['posteam'])if r.get('posteam')else None
        if off is not None and off not in pair:raise ValueError('Native offense outside game')
        aligned,positions=_roles(p,off)
        if aligned:
            for native,role in positions.items():
                if role=='QB':cohort[(gid,off)].add(native);universe.add(native)
    events=[];residual=[];seen=set()
    for e in basis['event_basis']:
        key=(e['game_id'],e['play_id'])
        if key in seen:raise ValueError('Unique reviewed dropback basis required')
        seen.add(key);r=raw_index.get(key)
        if r is None:raise ValueError('Every reviewed eligible or possible dropback needs same native raw event')
        gid=e['game_id'];pair=game_info[gid]['sides'];off=canonical_team(r['posteam'])if r.get('posteam')else None
        if off!=e['offense']:raise ValueError('Native raw/reviewed offense differs')
        p=part_index.get(key);aligned,positions=_roles(p,off)
        pressure=e['native_pressure'];eligible=e['eligible_nonspike_dropback'];scramble=_flag(r.get('qb_scramble'));rush=_flag(r.get('rush_attempt'))
        if pressure not in(True,False,None)or eligible not in(True,False,None):raise ValueError('Typed reviewed pressure/eligibility required')
        passer=_native(r.get('passer_player_id'));rusher=_native(r.get('rusher_player_id'))
        # Unknown scramble cannot silently choose a passer over a different possible rusher.
        candidates={x for x in(passer,rusher)if x}if scramble is None else ({rusher}if scramble is True and rusher else {passer}if scramble is False and passer else set())
        actor=next(iter(candidates))if len(candidates)==1 else None
        identity_conflict=bool(scramble is True and passer and rusher and passer!=rusher)
        proven=bool(actor and aligned and positions.get(actor)=='QB'and not identity_conflict)
        sides_known=off is not None and e.get('defense')is not None and off!=e['defense']
        membership=False if eligible is False or pressure is False else True if eligible is True and pressure is True and sides_known else None
        outcome=None
        if scramble is False:outcome=False
        elif scramble is True and rush is True and rusher==actor:outcome=True
        # Contradictory scramble/nonrush remains unknown rather than a certified zero.
        event=dict(game_id=gid,play_id=key[1],offense=off,eligible_nonspike_dropback=eligible,provider_pressure=pressure,
            reported_passer_id=passer,reported_rusher_id=rusher,qb_scramble=scramble,official_rush=rush,proven_QB_actor=actor if proven else None,
            verified_offensive_eleven=aligned,native_offensive_players=sorted(positions)if aligned else None,
            possible_reported_QBs=sorted(candidates),conditional_membership=membership,same_actor_official_scramble=outcome,
            source_pressure_sack_conflict=e.get('pressure_sack_conflict',False),reported_QB_identity_conflict=identity_conflict)
        events.append(event)
        if membership is not False and(not proven or off is None):residual.append(dict(game_id=gid,play_id=key[1],offense=off,possible_reported_native_ids=sorted(candidates),unknown_other_candidates=True,reason='Unproven conditional QB identity/role/side; no phantom team-qualified actor'))
    bygame=defaultdict(list)
    for e in events:bygame[e['game_id']].append(e)
    rows=[];grouped=defaultdict(list)
    for (gid,team),natives in sorted(cohort.items()):
        for native in sorted(natives):
            relevant=[]
            for e in bygame[gid]:
                if e['offense']is not None and e['offense']!=team:continue
                membership=e['conditional_membership'];actor=e['proven_QB_actor']
                if membership is False:continue
                if e['offense']==team and actor is not None:
                    if actor!=native:continue
                    relevant.append(dict(eligible_pressure_for_actor=membership,same_actor_official_scramble=e['same_actor_official_scramble']))
                elif e['verified_offensive_eleven']and native not in e['native_offensive_players']and e['proven_QB_actor']is not None:continue
                else:relevant.append(dict(eligible_pressure_for_actor=None,same_actor_official_scramble=None))
            row=dict(game_id=gid,team=team,season=year,week=game_info[gid]['week'],source_player_id=native,source_role='QB',**_summary(relevant));rows.append(row);grouped[(team,native)].extend(relevant)
    profiles=[dict(season=year,team=team,source_player_id=native,source_role='QB',**_summary(ev))for(team,native),ev in sorted(grouped.items())]
    core=dict(version=VERSION,candidate_id='G05-M04',season=year,before_period=before,game_rows=rows,profiles=profiles,event_basis=events,
        unassigned_QB_residual=residual,native_identity_universe=sorted(universe),definitions=dict(denominator='Same measured source-QB provider-pressure=True eligible nonspike physical dropback events',numerator='Same event/same proven QB official rush AND qb_scramble=True',provider='Direct native provider was_pressure, not PFR HHS taxonomy equivalence',zero='Zero pressure denominator undefined; missing source values not no-pressure'))
    return dict(**core,semantic_sha256=digest(core),pregame_serving_eligible=False,forecast=None,model_or_optimizer_consumed=False,
        limitations=['Historical postseason revised FTN observations, not current2026 or original pregame evidence','QB role is source event position proof, not healthy/available/projected starter','Unknown identity/pressure/role/scramble remains residual and masks compatible full ratios','No causal scramble response/future probability or model serving'])


def _roles(part,offense):
    if part is None or offense is None or part.get('native_phase')not in(None,'REG')or part.get('possession_team')!=offense:return False,{}
    scope=part['participant_scopes']['offense'];ids=scope.get('native_player_ids');positions=scope.get('position_by_native_id')
    aligned=bool(scope.get('status')=='aligned_native_position_list'and ids is not None and positions is not None and len(ids)==len(set(ids))==11 and set(ids)==set(positions))
    return aligned,positions if aligned else {}


def attach_pressure_identity(blocks,alias_rows,*,cutoff,identity_universe):
    from copy import deepcopy
    from .contact_cohort_reconciliation import resolve_contact_identity
    if not blocks or any(b.get('version')!=VERSION or b.get('pregame_serving_eligible')is not False for b in blocks):raise ValueError('Exact nonserving pressure native blocks required')
    universe=set(identity_universe);needed={n for b in blocks for n in b['native_identity_universe']}
    if not needed<=universe:raise ValueError('Full potential source passer/rusher identity universe required')
    proofs,future=resolve_contact_identity(universe,alias_rows,source_system='nflreadpy',cutoff=cutoff)
    out=deepcopy(blocks);requests=[]
    for b in out:
        for field in('game_rows','profiles'):
            for r in b[field]:
                native=r['source_player_id'];p=proofs[native];r['player_master_id']=p['player_master_id'];r['identity_status']=p['status']
                r['canonical_qualified_scramble_fraction']=r['scramble_fraction']if p['player_master_id']is not None else None
                if field=='game_rows'and p['player_master_id']is None:
                    requests.append(dict(source_player_id=native,game_id=r['game_id'],team=r['team'],reason=p['status'],alias_evidence=p['original_alias_evidence'],evidence_scope='Frozen native identity receipt, not current missing-alias assertion'))
        b['identity_receipts']=proofs;b['future_alias_evidence_excluded']=future;b['identity_review_requests']=[r for r in requests if int(r['game_id'][:4])==b['season']]
        b['native_semantic_sha256']=b.pop('semantic_sha256');b['identity_semantic_sha256']=digest({k:b[k]for k in('version','native_semantic_sha256','game_rows','profiles','identity_receipts','identity_review_requests')})
    return out


def load_reviewed_pressure_basis(ref,*,cutoff):
    from pathlib import Path
    import json,hashlib
    from datetime import datetime,UTC
    from . import participation_defense_catalog,participation_source_components,fumble_event_components
    from .factual_designation import clock
    p=Path(ref['path']).resolve();actual=clock(cutoff)
    if p.parent!=Path('artifacts/participation_defense_catalog').resolve()or p.name!=ref['sha256']+'.json'or not 0<ref['bytes']<=16*1024*1024:raise ValueError('Managed bounded reviewed pressure basis required')
    raw=p.read_bytes()
    if len(raw)!=ref['bytes']or hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('Pressure basis bytes differ')
    x=json.loads(raw);pr=x['provenance'];t=clock(pr.get('actual_publication_at'))
    if actual is None or actual>datetime.now(UTC)or t is None or t>actual:raise ValueError('Reviewed pressure publication unavailable')
    if x.get('version')!=BASIS_VERSION or x.get('pregame_serving_eligible')is not False or x.get('forecast')is not None:raise ValueError('Pressure source version/use differs')
    for key,module in(('producer_code_sha256',participation_defense_catalog),('source_adapter_sha256',participation_source_components),('eligibility_helper_sha256',fumble_event_components)):
        if pr.get(key)!=hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest():raise ValueError('Reviewed source producer/helper differs')
    keys=('version','before_period','season','definitions','source_category_mapping','team_game_rows','team_season_rows','event_basis')
    if x['semantic_sha256']!=digest({k:x[k]for k in keys}):raise ValueError('Pressure native source semantic core differs')
    return x


def persist_pressure_identity_requests(connection,blocks,*,source_refs):
    """Evidence-only frozen attachment review; preserve existing/resolved queue cases."""
    from sqlalchemy import text
    import hashlib,json
    if any(b.get('version')!=VERSION or b.get('pregame_serving_eligible')is not False for b in blocks):raise ValueError('Exact frozen pressure evidence required')
    requests=defaultdict(list)
    for b in blocks:
        for r in b['identity_review_requests']:requests[(r['source_player_id'],r['reason'])].append(r)
    output=[]
    for(native,reason),incidents in sorted(requests.items()):
        evidence=[{k:r[k]for k in('alias_id','source_key','player_master_id','created_at')}for q in incidents for r in q['alias_evidence']]
        evidence=sorted({digest(r):r for r in evidence}.values(),key=lambda r:(str(r['alias_id']),r['source_key']))
        key='pressure-frozen-attachment:'+native+':'+digest(dict(reason=reason,evidence=evidence))
        qid='pressure-native:'+hashlib.sha256(key.encode()).hexdigest()[:32];first=min(incidents,key=lambda r:r['game_id']);parts=first['game_id'].split('_')
        connection.execute(text("""INSERT INTO target.identity_quarantine
        (identity_quarantine_id,entity_type,source_schema,source_table,source_record_key,source_system,season,week,slate,
         source_player_key,display_name,team_id,position,reason_code,candidate_player_ids,status,first_seen_at,updated_at)
        VALUES (:qid,'player','public','source_snapshot',:key,'nflreadpy',:season,:week,'FEATURE_INVENTORY',:native,NULL,:team,'QB',:reason,CAST(:candidates AS jsonb),'open',now(),now())
        ON CONFLICT (source_schema,source_table,source_record_key) DO NOTHING"""),dict(qid=qid,key=key,native=native,season=int(parts[0]),week=int(parts[1]),team=first['team'],reason='pressure_frozen_'+reason,candidates=json.dumps(sorted({r['player_master_id']for r in evidence}))))
        output.append(dict(source_table='source_snapshot',source_record_key=key,intended_identity_quarantine_id=qid,source_player_key=native,reason=reason,native_game_ids=sorted({r['game_id']for r in incidents}),original_alias_evidence=evidence))
    return dict(records=output,requests=len(output),source_refs=source_refs,policy='Append-only frozen-attachment evidence; DO NOTHING preserves existing/resolved cases; no alias or master changes/current missing assertion')
