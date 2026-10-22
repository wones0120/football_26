"""Observed independently proven first-snap center changes and sack responses."""
from collections import Counter,defaultdict
from copy import deepcopy
from datetime import date,datetime,UTC
import re
from .evaluation_record import digest
from .market_snapshots import canonical_team
from .factual_designation import clock
from .participation_source_components import VERSION as PARTICIPATION_VERSION,_int
from .offensive_line_participation import _physical,_order,resolve_line_identity
from .fumble_event_components import _flag
from .schedule_context_features import VERSION as SCHEDULE_VERSION
from .participation_defense_catalog import VERSION as COVERAGE_VERSION

VERSION='center_sack_response_v1'
UNIT_VERSION='native_first_snap_center_v1'
ROLES={'C','G','T','QB','RB','FB','TE','WR','DE','DT','NT','ILB','OLB','MLB','LB','CB','FS','SS','S','DB','DL','K','P','LS'}
INDICATORS=('pass_attempt','rush_attempt','sack','qb_dropback','qb_spike','qb_kneel','qb_scramble','two_point_attempt')


def build_first_snap_centers(participation,records,schedule,*,before_period,event_source_sha256):
    if participation.get('version')!=PARTICIPATION_VERSION or schedule.get('version')!=SCHEDULE_VERSION or any(v.get('pregame_serving_eligible')is not False for v in(participation,schedule)):raise ValueError('Reviewed nonserving native sources required')
    if not isinstance(event_source_sha256,str)or not re.fullmatch(r'[0-9a-f]{64}',event_source_sha256):raise ValueError('Original verified PBP hash required')
    if type(before_period)is not int or not 1<=before_period%100<=18:raise ValueError('Explicit strict prior REG boundary required')
    season=participation['season'];expected={};timeline=defaultdict(list);sources={};seen=set()
    for g in schedule['game_rows']:
        if g['season']!=season or g['game_type']!='REG'or season*100+g['week']>=before_period:continue
        pair={canonical_team(g['home_team']),canonical_team(g['away_team'])};parts=g['game_id'].split('_')
        if len(pair)!=2 or len(parts)!=4 or parts[:2]!=[str(season),f"{g['week']:02d}"]or pair!={canonical_team(t)for t in parts[2:]}or g['game_id']in expected:raise ValueError('Unique native schedule game/period/sides required')
        expected[g['game_id']]=dict(week=g['week'],sides=pair,game_date=g.get('game_date'))
    for r in participation['rows']:
        key=(r['game_id'],r['play_id'])
        if key in sources:raise ValueError('Duplicate native participation')
        sources[key]=r
    for raw in records:
        gid=raw['game_id'];parts=gid.split('_');year=_int(raw['season']);week=_int(raw['week']);play=str(_int(raw['play_id']))
        if len(parts)!=4 or parts[:2]!=[str(year),f'{week:02d}']or year!=season or not 1<=week<=22:raise ValueError('Native PBP game/period required')
        key=(gid,play)
        if key in seen:raise ValueError('Duplicate native PBP play')
        seen.add(key)
        if raw.get('season_type')!='REG'or year*100+week>=before_period:continue
        if gid not in expected:raise ValueError('PBP game missing expected schedule')
        team=canonical_team(raw['posteam'])if raw.get('posteam')else None
        if team is not None and team not in expected[gid]['sides']:raise ValueError('PBP offense contradicts native game')
        start=raw.get('play_type_nfl')=='GAME_START'and all(_flag(raw.get(f))is not True for f in(*INDICATORS,'fumble'))
        timeline[gid].append(dict(play_id=play,order=_order(raw.get('order_sequence')),team=team,physical=_physical(raw),native_start=start))
    units=[]
    for gid,meta in sorted(expected.items()):
        events=timeline[gid];starts=[e for e in events if e['native_start']];orders=[e['order']for e in events if e['order']is not None]
        beginning=starts[0]if len(starts)==1 and starts[0]['order']is not None and len(orders)==len(set(orders))else None
        for team in sorted(meta['sides']):
            possible=[e for e in events if e['team']in(None,team)and e['physical']is not False];known=[e for e in possible if e['team']==team and e['physical']is True and e['order']is not None]
            first=min(known,key=lambda e:e['order'])if known else None
            earlier=[e for e in possible if e is not first and(first is None or e['order']is None or e['order']<first['order'])]
            reason=None
            if beginning is None:reason='Native beginning/order proof missing or ambiguous'
            elif first is None:reason='First physical offensive snap unknown'
            elif beginning['order']>=first['order']or earlier:reason='Earlier possible/nullified offense or unknown native order'
            source=sources.get((gid,first['play_id']))if first else None;scope=source['participant_scopes']['offense']if source else None
            positions=scope.get('position_by_native_id')if scope else None;ids=scope.get('native_player_ids')if scope else None
            valid=bool(scope and scope.get('status')=='aligned_native_position_list'and isinstance(positions,dict)and ids is not None and len(ids)==11 and len(set(ids))==11 and set(ids)==set(positions)and all(p in ROLES for p in positions.values()))
            if reason is None and(source is None or source.get('possession_team')!=team or source.get('native_phase')not in(None,'REG')):reason='First-snap source native team/phase missing or conflicting'
            if reason is None and not valid:reason='Eleven unique aligned known-position participants not proven'
            centers=sorted(n for n,p in positions.items()if p=='C')if valid else[]
            if reason is None and len(centers)!=1:reason='Exactly one source-reported C not proven'
            roles=Counter(positions.values())if valid else Counter()
            proof=dict(unique_quiet_native_GAME_START=beginning is not None,native_beginning_play_id=beginning['play_id']if beginning else None,
                first_physical_play_id=first['play_id']if first else None,first_physical_native_order=str(first['order'])if first else None,
                no_earlier_possible_offense=not earlier and beginning is not None and first is not None and beginning['order']<first['order'],
                earlier_possible_play_ids=sorted(e['play_id']for e in earlier),eleven_unique_aligned_positions=valid,
                original_first_snap_position_by_native_id=deepcopy(positions),source_center_candidates=centers,
                full_CGT_native_count_match=(roles['C']==1 and roles['G']==2 and roles['T']==2)if valid else None)
            units.append(dict(game_id=gid,season=season,week=meta['week'],team=team,game_date=meta['game_date'],source_center_id=centers[0]if reason is None else None,source_proven_center=reason is None,unknown_reason=reason,proof=proof))
    core=dict(version=UNIT_VERSION,season=season,before_period=before_period,units=units,evidence_use='historical_postseason_revised_descriptive_not_pregame_or_serving',pregame_serving_eligible=False)
    return dict(**core,semantic_sha256=digest(core),provenance=dict(participation_semantic_sha256=participation['semantic_sha256'],event_source_sha256=event_source_sha256))


def _response_counter():return dict(known_dropbacks=0,known_sacks=0,known_sack_outcome_exposures=0,unknown_dropback_eligibility_or_side=0,unknown_sack_outcomes=0,missing_source_games=0)


def _response_finish(c):
    unknown=c['unknown_dropback_eligibility_or_side']or c['missing_source_games'];missing=c['unknown_sack_outcomes'];n=c['known_dropbacks'];s=c['known_sacks']
    return c|dict(exact_dropbacks=n if not unknown else None,exact_sacks=s if not(unknown or missing)else None,
        rate=s/n if n and not(unknown or missing)else None,known_outcome_sample_rate=s/c['known_sack_outcome_exposures']if c['known_sack_outcome_exposures']else None)


def build_center_sack_response(center_components,coverage_components,aliases,*,cutoff,identity_universe):
    if clock(cutoff)is None or clock(cutoff)>datetime.now(UTC):raise ValueError('Actual nonfuture alias cutoff required')
    centers={c['season']:c for c in center_components};coverage={c['season']:c for c in coverage_components}
    if len(centers)!=len(center_components)or len(coverage)!=len(coverage_components)or set(centers)!=set(coverage):raise ValueError('Unique paired source seasons required')
    boundaries={c['before_period']for c in center_components}|{c['before_period']for c in coverage_components}
    if len(boundaries)!=1:raise ValueError('One matched strict prior boundary required')
    native={u['source_center_id']for c in centers.values()for u in c['units']if u['source_proven_center']}
    if any(not isinstance(n,str)or not re.fullmatch(r'00-\d{7}',n)for n in identity_universe):raise ValueError('Exact native GSIS universe required')
    if not native<=set(identity_universe):raise ValueError('Whole native source identity universe required')
    identities,future=resolve_line_identity(identity_universe,aliases,cutoff=cutoff);rows=[];requests=[];source_hashes={}
    for season,component in sorted(centers.items()):
        other=coverage[season]
        if component.get('version')!=UNIT_VERSION or other.get('version')!=COVERAGE_VERSION or component['before_period']!=other['before_period']or any(c.get('pregame_serving_eligible')is not False for c in(component,other))or component['provenance']['participation_semantic_sha256']!=other['provenance']['participation_semantic_sha256']:raise ValueError('Matched verified native center/coverage sources required')
        if component['provenance']['event_source_sha256']!=other['provenance']['original_PBP_manifest']['sha256']:raise ValueError('Center/dropback original native event source differs')
        index={(u['game_id'],u['team']):u for u in component['units']}
        if len(index)!=len(component['units']):raise ValueError('Duplicate native center game/side')
        counts={k:_response_counter()for k in index};seen=set()
        coverage_keys={(r['game_id'],r['team'])for r in other['team_game_rows']}
        if len(coverage_keys)!=len(other['team_game_rows']):raise ValueError('Duplicate coverage native game/side')
        for gid,team in index:
            opponent=next(t for t in {canonical_team(p)for p in gid.split('_')[2:]}if t!=team)
            if(gid,opponent)not in coverage_keys:counts[(gid,team)]['missing_source_games']=1
        for e in other['event_basis']:
            key=(e['game_id'],e['play_id'])
            if key in seen:raise ValueError('Duplicate native dropback event')
            seen.add(key);parts=e['game_id'].split('_');pair={canonical_team(t)for t in parts[2:]};off=e['offense'];defense=e['defense']
            if len(parts)!=4 or int(parts[0])!=season or len(pair)!=2 or any(t is not None and t not in pair for t in(off,defense))or off is not None and off==defense:raise ValueError('Native dropback side/scope differs')
            eligible=e['eligible_nonspike_dropback'];outcome=e['source_sack']
            if eligible is False:continue
            for team in {off}if off is not None and defense is not None else pair:
                target=(e['game_id'],team)
                if target not in counts:raise ValueError('Dropback missing expected native center game')
                c=counts[target]
                if eligible is not True or off is None or defense is None:c['unknown_dropback_eligibility_or_side']+=1
                else:
                    c['known_dropbacks']+=1
                    if type(outcome)is not bool:c['unknown_sack_outcomes']+=1
                    else:c['known_sack_outcome_exposures']+=1;c['known_sacks']+=int(outcome)
        groups=defaultdict(list)
        for unit in component['units']:groups[unit['team']].append(unit)
        for team,units in sorted(groups.items()):
            dates=[u['game_date']for u in units];ordered=True
            try:
                ordered=all(isinstance(d,str)for d in dates)and len(set(dates))==len(dates)
                for d in dates:date.fromisoformat(d[:10])
            except(TypeError,ValueError):ordered=False
            units=sorted(units,key=lambda u:u['game_date'])if ordered else sorted(units,key=lambda u:u['game_id']);previous=None
            for unit in units:
                current=unit['source_center_id'];old=previous['source_center_id']if previous else None
                proof=identities.get(current)if current else None;oldproof=identities.get(old)if old else None
                conflict=any(p is not None and p['status']=='canonical_native_conflict'for p in(proof,oldproof))
                applicable=bool(previous)if ordered else None
                label=None if not ordered or not previous or current is None or old is None or conflict else 'same'if current==old else 'changed'
                canonical=bool(label is not None and proof and oldproof and proof['player_master_id']is not None and oldproof['player_master_id']is not None)
                row=dict(season=season,game_id=unit['game_id'],team=team,previous_same_season_game_id=previous['game_id']if previous else None,comparison_applicable=applicable,center_class=label,
                    source_center_id=current,previous_source_center_id=old,player_master_id=proof['player_master_id']if proof else None,previous_player_master_id=oldproof['player_master_id']if oldproof else None,
                    canonical_pair_qualified=canonical,current_proof=deepcopy(unit['proof']),current_source_unknown_reason=unit['unknown_reason'],response=_response_finish(counts[(unit['game_id'],team)]))
                rows.append(row)
                if current and proof['status']!='unique_native_alias':requests.append(dict(game_id=unit['game_id'],team=team,source_player_id=current,position='C',reason=proof['status'],alias_evidence=deepcopy(proof['original_alias_evidence'])))
                previous=unit
        source_hashes[season]=dict(center=component['semantic_sha256'],coverage=other['semantic_sha256'])
    profiles=[]
    for season,team in sorted({(r['season'],r['team'])for r in rows}):
        samples=[r for r in rows if r['season']==season and r['team']==team and r['comparison_applicable']is not False]
        unknown=sum(r['center_class']is None for r in samples);cells={}
        for label in('same','changed'):
            chosen=[r for r in samples if r['center_class']==label];pooled={k:sum(r['response'][k]for r in chosen)for k in _response_counter()};value=_response_finish(pooled)
            if unknown:value|=dict(exact_dropbacks=None,exact_sacks=None,rate=None)
            cells[label]=dict(observed_games=len(chosen),**value)
        a,b=cells['same']['rate'],cells['changed']['rate']
        profiles.append(dict(season=season,team=team,unknown_center_class_games=unknown,cells=cells,same_minus_changed_sack_rate=a-b if a is not None and b is not None else None))
    core=dict(version=VERSION,catalog_id='X04-M01',before_period=next(iter(boundaries)),game_rows=rows,profiles=profiles,source_semantic_hashes=source_hashes,native_identity_receipts=identities,identity_review_requests=requests,
        definition='Observed source-proven first-snap C identity same versus changed from previous scheduled same-team/season game; pooled official nonspike physical-dropback sack rate; firstgame N/A, unknowns mask exact cells',
        evidence_use='historical_postseason_revised_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None,
        limitations=['Independent native beginning/firstsnap/11participant/oneC proof, not an error-string shortcut or expected future starter','Generic C label does not prove health, blocking assignment or causal protection effect','No native pressure taxonomy claim; sacks and matched nonspike DB only','Known sample counts/rates separate from unknown class/response; no skip over missing previous game','Native identity separate from complete canonical pair qualification; all source conflicts retained'])
    return dict(**core,semantic_sha256=digest(core),future_alias_evidence_excluded=future,provenance=dict(actual_alias_cutoff_at=clock(cutoff).isoformat()))


def persist_center_identity_requests(connection,features,*,source_refs):
    """Append native identity incidents to the existing review UI; never repair aliases."""
    import json,hashlib
    from sqlalchemy import text
    if features.get('version')!=VERSION or features.get('pregame_serving_eligible')is not False:raise ValueError('Exact nonserving center feature required')
    grouped=defaultdict(list)
    for r in features['identity_review_requests']:grouped[(r['source_player_id'],r['reason'])].append(r)
    if len(grouped)>10000:raise ValueError('Native incident bound exceeded')
    records=[]
    for(native,reason),incidents in sorted(grouped.items()):
        if not re.fullmatch(r'00-\d{7}',native):raise ValueError('Native incident GSIS required')
        evidence=[{k:r[k]for k in('alias_id','source_key','player_master_id','created_at')}for q in incidents for r in q['alias_evidence']]
        evidence=sorted({digest(r):r for r in evidence}.values(),key=lambda r:(str(r['alias_id']),r['source_key']))
        key='nflreadpy-gsis:'+native if reason=='unresolved_native_key'else 'line-alias-conflict:'+native+':'+digest(evidence)
        qid='center-native:'+hashlib.sha256(key.encode()).hexdigest()[:32];first=min(incidents,key=lambda r:r['game_id']);parts=first['game_id'].split('_');table='player_alias'if reason=='canonical_native_conflict'else 'source_snapshot'
        candidates=sorted({r['player_master_id']for r in evidence})
        connection.execute(text("""INSERT INTO target.identity_quarantine
        (identity_quarantine_id,entity_type,source_schema,source_table,source_record_key,source_system,season,week,slate,
        source_player_key,display_name,team_id,position,reason_code,candidate_player_ids,status,first_seen_at,updated_at)
        VALUES (:qid,'player','public',:table,:key,'nflreadpy',:season,:week,'FEATURE_INVENTORY',:native,NULL,:team,'C',:reason,CAST(:candidates AS jsonb),'open',now(),now())
        ON CONFLICT (source_schema,source_table,source_record_key) DO NOTHING"""),dict(qid=qid,table=table,key=key,native=native,season=int(parts[0]),week=int(parts[1]),team=first['team'],reason='center_'+reason,candidates=json.dumps(candidates)))
        records.append(dict(source_record_key=key,source_table=table,source_player_id=native,intended_identity_quarantine_id=qid,reason=reason,all_native_game_ids=sorted({q['game_id']for q in incidents}),original_alias_evidence=evidence))
    return dict(records=records,requests=len(records),source_refs=deepcopy(source_refs),policy='Append only ON CONFLICT DO NOTHING; never reopen resolved cases or mutate aliases/master/name joins')
