"""Official rush cohort primitives for exact source-contact reconciliation.

No contact total is certified by a matching aggregate carry count alone.
"""
from collections import defaultdict
from copy import deepcopy
from uuid import UUID
from datetime import datetime,UTC
import math,re
from .fumble_event_components import _flag,_eligibility
from .factual_designation import clock
from .market_snapshots import canonical_team
from .participation_source_components import _int
from .evaluation_record import digest

VERSION='contact_cohort_reconciliation_v1'


def official_rush_eligibility(raw):
    live,_=_eligibility(raw)
    if live is False:return False
    rush,passing,sack,scramble,spike=(_flag(raw.get(k)) for k in ('rush_attempt','pass_attempt','sack','qb_scramble','qb_spike'))
    conflict=(rush is True and (passing is not False or sack is not False or spike is True)) or (scramble is True and (rush is not True or passing is True or sack is True))
    if conflict:return None
    if rush is False:return False
    return True if live is True and rush is True else None


def _number(value):
    if value in (None,'')or type(value)is bool:return None
    try:n=float(value)
    except(TypeError,ValueError):return None
    return n if math.isfinite(n) else None


def _clock(value):
    try:return clock(value)
    except(TypeError,ValueError):return None


def build_official_rushing_cohort(records,*,before_period):
    if type(before_period)is not int or not 1<=before_period%100<=18:raise ValueError('Explicit prior REG boundary required')
    groups={};seen=set();basis=[]
    for raw in records:
        if raw.get('season_type')!='REG':continue
        year=_int(raw['season']);week=_int(raw['week']);gid=raw['game_id'];play=str(_int(raw['play_id']));parts=gid.split('_')
        if len(parts)!=4 or parts[:2]!=[str(year),f'{week:02d}'] or not 1<=week<=18:raise ValueError('Native rush game/period required')
        if year*100+week>=before_period:continue
        key=(gid,play)
        if key in seen:raise ValueError('Duplicate native rush source play')
        seen.add(key);pair={canonical_team(t)for t in parts[2:]}
        if len(pair)!=2:raise ValueError('Two native game sides required')
        for team in pair:groups.setdefault((gid,team),dict(game_id=gid,season=year,week=week,offense=team,defense=next(t for t in pair if t!=team),
            source_offense_rows=0,known_official_carries=0,unknown_official_rush_membership=0,unknown_rusher_events=0,unknown_rushing_yard_events=0,
            lateral_or_unknown_lateral_events=0,actors={}))
        off=canonical_team(raw['posteam'])if raw.get('posteam')else None;defense=canonical_team(raw['defteam'])if raw.get('defteam')else None
        if any(t is not None and t not in pair for t in(off,defense))or off is not None and off==defense:raise ValueError('Native rush sides contradict game')
        if off is not None and defense is not None:groups[(gid,off)]['source_offense_rows']+=1
        eligible=official_rush_eligibility(raw)
        if eligible is False:continue
        native=raw.get('rusher_player_id')or None;valid=bool(isinstance(native,str)and re.fullmatch(r'00-\d{7}',native))
        yards=_number(raw.get('rushing_yards'));lateral=_flag(raw.get('lateral_rush'))
        lateral_unknown=lateral is not False or bool(raw.get('lateral_rusher_player_id')) or _number(raw.get('lateral_rushing_yards')) not in (None,0.)
        event=dict(game_id=gid,play_id=play,offense=off,defense=defense,eligible=eligible,native_rusher=native,
            native_rusher_valid=valid,source_rushing_yards=yards,lateral_rush=lateral,reported_lateral_rusher=raw.get('lateral_rusher_player_id')or None,
            reported_lateral_yards=_number(raw.get('lateral_rushing_yards')),possible_lateral_credit=lateral_unknown)
        basis.append(event)
        for team in {off}if off is not None and defense is not None else pair:
            c=groups[(gid,team)]
            if eligible is None or off is None or defense is None:c['unknown_official_rush_membership']+=1;continue
            c['known_official_carries']+=1
            if lateral_unknown:c['lateral_or_unknown_lateral_events']+=1
            if yards is None:c['unknown_rushing_yard_events']+=1
            if not valid:c['unknown_rusher_events']+=1;continue
            a=c['actors'].setdefault(native,dict(native_GSIS=native,official_carries=0,known_rushing_yards=0.,unknown_rushing_yards=0,play_ids=[]))
            a['official_carries']+=1;a['play_ids'].append(play)
            if yards is None:a['unknown_rushing_yards']+=1
            else:a['known_rushing_yards']+=yards
    return dict(version=VERSION,before_period=before_period,game_rows=[r for _,r in sorted(groups.items())],event_basis=basis)


def resolve_contact_identity(native_ids,aliases,*,source_system,cutoff):
    boundary=_clock(cutoff)
    if boundary is None or boundary>datetime.now(UTC) or source_system not in {'nflreadpy','pfr'}:raise ValueError('Explicit nonfuture native alias system/cutoff required')
    known=defaultdict(list);excluded=[]
    for r in aliases:
        if r['source_system']!=source_system or r['source_key']not in native_ids:raise ValueError('Exact requested native aliases required')
        created=_clock(r.get('created_at'));master=_clock(r.get('player_master_created_at'));pid=r['player_master_id']
        if str(UUID(str(pid)))!=str(pid):raise ValueError('Canonical UUID spelling required')
        if created is None or master is None or created>boundary or master>boundary:excluded.append(deepcopy(r));continue
        known[r['source_key']].append({**deepcopy(r),'player_master_id':str(pid)})
    values={n:{r['player_master_id']for r in known[n]}for n in native_ids};inverse=defaultdict(set)
    for n,ids in values.items():
        for pid in ids:inverse[pid].add(n)
    conflicts={n for ns in inverse.values()if len(ns)>1 for n in ns}|{n for n,ids in values.items()if len(ids)>1}
    proof={n:dict(source_system=source_system,source_key=n,actual_alias_cutoff_at=boundary.isoformat(),player_master_id=next(iter(values[n]))if len(values[n])==1 and n not in conflicts else None,
        status='canonical_native_conflict'if n in conflicts else'unique_native_alias'if len(values[n])==1 else'unresolved_native_key',
        original_alias_evidence=sorted(known[n],key=lambda r:(str(r.get('alias_id')),r['player_master_id'])))for n in sorted(native_ids)}
    return proof,excluded


def reconcile_contact_cohorts(cohort,pfr_actors,GSIS_proofs,PFR_proofs):
    if cohort.get('version')!=VERSION:raise ValueError('Official rush cohort contract required')
    for system,proofs in (('nflreadpy',GSIS_proofs),('pfr',PFR_proofs)):
        inverse={}
        for native,p in proofs.items():
            cutoff=_clock(p.get('actual_alias_cutoff_at'));pid=p.get('player_master_id')
            if p.get('source_system')!=system or p.get('source_key')!=native or cutoff is None or cutoff>datetime.now(UTC):raise ValueError('Frozen native identity proof scope/clock required')
            if pid is not None:
                if p.get('status')!='unique_native_alias' or str(UUID(str(pid)))!=pid or pid in inverse:raise ValueError('Global native/canonical uniqueness proof differs')
                inverse[pid]=native
    pfr=defaultdict(list);seen=set();requests={};rows=[]
    expected={(g['game_id'],g['offense'])for g in cohort['game_rows']}
    for a in pfr_actors:
        key=(a['game_id'],a['team']);native=a['pfr_player_id'];identity=(*key,native)
        if identity in seen:raise ValueError('Duplicate native PFR rush actor/game')
        seen.add(identity)
        if key not in expected:raise ValueError('PFR actor lacks native PBP game/side')
        pfr[key].append(a)
    for event in cohort['event_basis']:
        if not event['native_rusher_valid']:continue
        native=event['native_rusher'];proof=GSIS_proofs.get(native)
        if proof is None or proof.get('player_master_id')is None:
            requests[('nflreadpy',native)]=dict(source_system='nflreadpy',source_key=native,reason=proof['status']if proof else'unresolved_native_key',evidence=deepcopy(proof),game_id=event['game_id'],team=event['offense'])
    for g in cohort['game_rows']:
        key=(g['game_id'],g['offense']);source=pfr[key];issues=[];links=[];pbpcanonical={};pfrcanonical={}
        if not g.get('source_offense_rows'):issues.append('missing_opposing_offense_source_log')
        for field in ('unknown_official_rush_membership','unknown_rusher_events','unknown_rushing_yard_events','lateral_or_unknown_lateral_events'):
            if g[field]:issues.append(field)
        for native,a in g['actors'].items():
            proof=GSIS_proofs.get(native);pid=proof.get('player_master_id')if proof else None
            if pid is None:
                issues.append('unresolved_or_conflicted_GSIS_actor');requests[('nflreadpy',native)]=dict(source_system='nflreadpy',source_key=native,reason=proof['status']if proof else'unresolved_native_key',evidence=deepcopy(proof),game_id=g['game_id'],team=g['offense'])
            else:
                if pid in pbpcanonical:raise ValueError('Frozen GSIS proof violates actor/game cardinality')
                pbpcanonical[pid]=a
        known_sums={mid:0. for mid in ('G15-M05','G15-M06')};missing_components={mid:0 for mid in known_sums};source_carries=0.;unknown_carries=0
        for a in source:
            native=a['pfr_player_id'];carry=_number(a.get('carries'));before=_number(a.get('before'));after=_number(a.get('after'))
            if carry is None or carry<0 or not carry.is_integer():unknown_carries+=1;issues.append('unknown_source_carries')
            else:source_carries+=carry
            for mid,value in (('G15-M05',before),('G15-M06',after)):
                if value is None:missing_components[mid]+=1;issues.append('missing_source_contact_component')
                else:known_sums[mid]+=value
            proof=PFR_proofs.get(native);pid=proof.get('player_master_id')if proof else None
            if pid is None:
                requests[('pfr',native)]=dict(source_system='pfr',source_key=native,reason=proof['status']if proof else'unresolved_native_key',evidence=deepcopy(proof),game_id=g['game_id'],team=g['offense'])
            if carry==0:
                if before not in (None,0.) or after not in (None,0.):issues.append('contact_yards_with_zero_source_carries')
                continue
            if pid is None:
                issues.append('unresolved_or_conflicted_PFR_actor')
            else:
                if pid in pfrcanonical:raise ValueError('Frozen PFR proof violates actor/game cardinality')
                pfrcanonical[pid]=a
        if not source and g['known_official_carries']:issues.append('missing_PFR_rush_cohort')
        if set(pbpcanonical)!=set(pfrcanonical):issues.append('missing_or_extra_positive_actor')
        for pid in sorted(set(pbpcanonical)&set(pfrcanonical)):
            a=pbpcanonical[pid];b=pfrcanonical[pid];carry=_number(b.get('carries'));before=_number(b.get('before'));after=_number(b.get('after'))
            counts_match=carry==a['official_carries'];partition=before is not None and after is not None and not a['unknown_rushing_yards'] and abs(before+after-a['known_rushing_yards'])<1e-9
            if not counts_match:issues.append('individual_carry_count_mismatch')
            if not partition:issues.append('individual_contact_rushing_yard_credit_mismatch_or_unknown')
            links.append(dict(player_master_id=pid,native_GSIS=a['native_GSIS'],native_PFR=b['pfr_player_id'],official_carries=a['official_carries'],PFR_carries=carry,
                source_PBP_rushing_yards=a['known_rushing_yards'],PFR_before=before,PFR_after=after,carry_count_match=counts_match,compatible_yard_partition=partition))
        if unknown_carries or source_carries!=g['known_official_carries']:issues.append('full_team_carry_count_mismatch_or_unknown')
        metrics={mid:dict(value=known_sums[mid]if not issues else None,unit='PFR_reported_rushing_yards_before_first_contact'if mid=='G15-M05'else'PFR_reported_rushing_yards_after_first_contact',
            per_official_carry=known_sums[mid]/g['known_official_carries']if not issues and g['known_official_carries']else None,
            known_source_sum=known_sums[mid],unknown_source_components=missing_components[mid])for mid in known_sums}
        rows.append(dict(game_id=g['game_id'],season=g['season'],week=g['week'],defense=g['defense'],opposing_offense=g['offense'],
            source_offense_rows=g.get('source_offense_rows',0),known_official_carries=g['known_official_carries'],PFR_known_carries=source_carries,PFR_unknown_carry_rows=unknown_carries,
            native_PBP_actor_count=len(g['actors']),native_PFR_actor_count=len(source),matched_actor_links=links,full_observed_cohort_proven=not issues,
            unknown_or_incompatible_reasons=sorted(set(issues)),metrics=metrics))
    profiles=[]
    for season,defense in sorted({(g['season'],g['defense'])for g in rows}):
        gs=[g for g in rows if (g['season'],g['defense'])==(season,defense)];metrics={}
        for mid in ('G15-M05','G15-M06'):
            values=[g['metrics'][mid]['value']for g in gs];known=[v for v in values if v is not None]
            metrics[mid]=dict(value=sum(known)if len(known)==len(values)else None,known_complete_game_sum=sum(known),
                known_complete_games=len(known),unknown_games=len(values)-len(known),unit=gs[0]['metrics'][mid]['unit'])
        profiles.append(dict(season=season,defense=defense,observed_game_ids=sorted(g['game_id']for g in gs),metrics=metrics))
    core=dict(version=VERSION,before_period=cohort['before_period'],catalog_ids=['G15-M05','G15-M06'],game_rows=rows,profiles=profiles,
        native_GSIS_identity_proofs=deepcopy(GSIS_proofs),native_PFR_identity_proofs=deepcopy(PFR_proofs),identity_review_requests=list(requests.values()),
        definition='Total opposing PFR native before/after firstcontact rushing yards only after exact official-inclusive native rusher/carry/yard-credit cohort reconciliation',
        evidence_use='historical_revised_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None,
        limitations=['Observed source logs, not independently complete games or original historical pregame inputs',
            'Equal aggregate carries alone never certifies actor cohort; both partitions share same source row and carry basis',
            'Native unresolved/colliding actors remain in source sums and review queue, never zero or name-joined',
            'Lateral or unexplained yard-credit convention differences remain incompatible rather than repaired',
            'No blocking causality, forecast, model or optimizer activation'])
    return dict(**core,semantic_sha256=digest(core))


def persist_contact_identity_requests(connection,features,*,source_refs):
    """Append or retain native review cases; never alter resolved status/aliases."""
    from sqlalchemy import text
    import hashlib,json
    if features.get('version')!=VERSION or features.get('pregame_serving_eligible')is not False:raise ValueError('Exact nonserving contact source contract required')
    entries=[]
    for q in features['identity_review_requests']:
        system=q['source_system'];native=q['source_key'];proof=q.get('evidence')or{};evidence=proof.get('original_alias_evidence',[])
        conflict=q['reason']=='canonical_native_conflict';table='player_alias'if conflict else'source_snapshot'
        key=('contact-native-conflict:'+system+':'+native+':'+digest(evidence))if conflict else('nflreadpy-gsis:'+native if system=='nflreadpy'else'pfr-player:'+native)
        entries.append(dict(qid='contact-native:'+hashlib.sha256(key.encode()).hexdigest()[:32],table=table,key=key,system=system,native=native,
            season=int(q['game_id'][:4]),week=int(q['game_id'].split('_')[1]),team=q['team'],reason='contact_'+q['reason'],
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
