"""Observed unordered starting guard-pair continuity and interior rush response."""
from collections import defaultdict
from copy import deepcopy
import re
from .evaluation_record import digest
from .center_sack_response import UNIT_VERSION,ROLES
from .participation_source_components import VERSION as PART_VERSION
from .defensive_front_rush_exposure import VERSION as RUSH_VERSION
from .offensive_line_participation import resolve_line_identity,_order

VERSION='guard_interior_response_v1'


def _interior(event):
    loc=event.get('original_run_location');gap=event.get('original_run_gap')
    a=loc=='middle'if loc in{'left','middle','right'}else None
    b=gap=='guard'if gap in{'guard','tackle','end'}else None
    return True if a is True or b is True else False if a is False and b is False else None


def _counter():return dict(known_interior_rushes=0,unknown_interior_membership=0,known_yards_exposures=0,rushing_yards_sum=0.,unknown_yards=0,known_EPA_exposures=0,EPA_sum=0.,unknown_EPA=0,missing_source_games=0)


def _finish(c,unknown_class_games=0):
    n=c['known_interior_rushes'];unknown=c['unknown_interior_membership']or c['missing_source_games']or unknown_class_games
    return dict(**c,unknown_class_games=unknown_class_games,exact_interior_rushes=n if not unknown else None,
        yards_per_interior_rush=c['rushing_yards_sum']/n if n and not(unknown or c['unknown_yards'])else None,
        EPA_per_interior_rush=c['EPA_sum']/n if n and not(unknown or c['unknown_EPA'])else None,
        known_outcome_sample_yards=c['rushing_yards_sum']/c['known_yards_exposures']if c['known_yards_exposures']else None,
        known_outcome_sample_EPA=c['EPA_sum']/c['known_EPA_exposures']if c['known_EPA_exposures']else None)


def _summarize(games):
    cells={name:_counter()for name in('same','changed')};unknown=0
    for game in games:
        if game['comparison_applicable']is False:continue
        c=game['interior_response'];group=game['guard_class']
        if group is None:
            unknown+=int(bool(c['known_interior_rushes']or c['unknown_interior_membership']or c['missing_source_games']))
        else:
            for k in _counter():cells[group][k]+=c[k]
    cells={k:_finish(c,unknown)for k,c in cells.items()};a,b=cells['same'],cells['changed']
    return dict(cells=cells,same_minus_changed_yards=a['yards_per_interior_rush']-b['yards_per_interior_rush']if a['yards_per_interior_rush']is not None and b['yards_per_interior_rush']is not None else None,
        same_minus_changed_EPA=a['EPA_per_interior_rush']-b['EPA_per_interior_rush']if a['EPA_per_interior_rush']is not None and b['EPA_per_interior_rush']is not None else None)


def build_guard_interior_response(first_sources,rush_sources,participations,alias_rows,*,cutoff,identity_universe):
    def by_season(values):
        out={v['season']:v for v in values}
        if len(out)!=len(values):raise ValueError('Unique source seasons required')
        return out
    first=by_season(first_sources);rush=by_season(rush_sources);parts=by_season(participations)
    if not first or set(first)!=set(rush)or set(first)!=set(parts):raise ValueError('Matched firstsnap/rush/participation seasons required')
    identities,future=resolve_line_identity(set(identity_universe),alias_rows,cutoff=cutoff);all_units=[];rows=[];profiles=[];windows=[];requests=[];basis=[]
    for season,source in sorted(first.items()):
        r=rush[season];p=parts[season]
        if source.get('version')!=UNIT_VERSION or r.get('version')!=RUSH_VERSION or p.get('version')!=PART_VERSION or any(v.get('pregame_serving_eligible')is not False for v in(source,r,p)):raise ValueError('Exact nonserving reviewed sources required')
        if source['before_period']!=r['before_period']or source['provenance']['participation_semantic_sha256']!=p['semantic_sha256']or r['provenance']['participation_semantic_sha256']!=p['semantic_sha256']:raise ValueError('Same native participation and strict boundary required')
        if source['provenance']['event_source_sha256']!=r['provenance']['original_PBP_manifest']['sha256']:raise ValueError('Same original native PBP hash required')
        part_index={(x['game_id'],x['play_id']):x for x in p['rows']}
        if len(part_index)!=len(p['rows']):raise ValueError('Duplicate native participation key')
        unit_index={};teams=defaultdict(list)
        for item in source['units']:
            gid=item['game_id'];team=item['team'];key=(gid,team)
            if key in unit_index:raise ValueError('Duplicate firstsnap native game/side')
            proof=item['proof'];position_map=proof['original_first_snap_position_by_native_id'];play=proof['first_physical_play_id'];part=part_index.get((gid,play))
            aligned=bool(proof['unique_quiet_native_GAME_START']is True and proof['no_earlier_possible_offense']is True and not proof['earlier_possible_play_ids']and proof['eleven_unique_aligned_positions']is True and play is not None and _order(proof['first_physical_native_order'])is not None)
            side_proven=bool(part and part.get('native_phase')in(None,'REG')and part.get('possession_team')==team)
            scope=part['participant_scopes']['offense']if part else None;ids=scope.get('native_player_ids')if scope else None;mapping=scope.get('position_by_native_id')if scope else None
            eleven=bool(scope and scope.get('status')=='aligned_native_position_list'and ids is not None and len(ids)==len(set(ids))==11 and mapping is not None and set(ids)==set(mapping)and mapping==position_map and all(role in ROLES for role in mapping.values()))
            guards=sorted(n for n,role in mapping.items()if role=='G')if eleven else[]
            valid=aligned and side_proven and eleven and len(guards)==2
            if any(not re.fullmatch(r'00-\d{7}',n)for n in guards)or not set(guards)<=set(identity_universe):raise ValueError('Complete global native guard identity universe required')
            receipts={n:identities[n]for n in guards}if valid else{}
            if valid:
                for native,identity in receipts.items():
                    if identity['status']!='unique_native_alias':requests.append(dict(game_id=gid,team=team,source_player_id=native,position='G',reason=identity['status'],alias_evidence=deepcopy(identity['original_alias_evidence'])))
            unit=dict(game_id=gid,season=season,week=item['week'],team=team,game_date=item['game_date'],source_proven_guard_pair=valid,
                native_guard_ids=guards if valid else None,independent_proof=dict(beginning_and_firstsnap=aligned,native_firstsnap_side=side_proven,eleven_aligned_positions=eleven,source_G_count=len(guards),
                    first_physical_play_id=play,original_first_snap_positions=deepcopy(mapping),original_center_proven_flag=item['source_proven_center']),
                identity_statuses={n:identity['status']for n,identity in receipts.items()},canonical_guard_ids=[receipts[n]['player_master_id']for n in guards]if valid and all(v['player_master_id']is not None for v in receipts.values())else None)
            unit_index[key]=unit;teams[team].append(unit);all_units.append(unit)
        counts={key:_counter()for key in unit_index};seen=set();native_sides={(x['game_id'],x['offense'])for x in r['team_game_rows']}
        for key in counts:
            if key not in native_sides:counts[key]['missing_source_games']=1
        for event in r['event_basis']:
            gid=event['game_id'];key=(gid,event['play_id'])
            if key in seen:raise ValueError('Duplicate native rushing event')
            seen.add(key);inside=_interior(event);elig=event['eligible'];pair={u['team']for u in source['units']if u['game_id']==gid}
            if len(pair)!=2:raise ValueError('Native rush game missing two expected sides')
            off=event['offense'];defense=event['defense']
            if any(t is not None and t not in pair for t in(off,defense))or off is not None and off==defense:raise ValueError('Native rushing sides conflict')
            if elig is False or inside is False:continue
            for team in({off}if off is not None and defense is not None else pair):
                c=counts[(gid,team)]
                if elig is not True or inside is not True or off is None or defense is None:c['unknown_interior_membership']+=1
                else:
                    c['known_interior_rushes']+=1
                    for field,summed,known,unknown in(('rushing_yards','rushing_yards_sum','known_yards_exposures','unknown_yards'),('epa','EPA_sum','known_EPA_exposures','unknown_EPA')):
                        if event[field]is None:c[unknown]+=1
                        else:c[known]+=1;c[summed]+=event[field]
            basis.append(dict(game_id=gid,play_id=event['play_id'],offense=off,defense=defense,eligible=elig,interior_membership=inside,original_run_location=event['original_run_location'],original_run_gap=event['original_run_gap'],rushing_yards=event['rushing_yards'],epa=event['epa']))
        for team,games in sorted(teams.items()):
            if any(not g['game_date']for g in games)or len({g['game_date']for g in games})!=len(games):raise ValueError('Unique native scheduled dates required')
            games.sort(key=lambda g:g['game_date']);team_rows=[]
            for i,current in enumerate(games):
                previous=games[i-1]if i else None;overlap=None;group=None;qualified=None
                if previous and previous['source_proven_guard_pair']and current['source_proven_guard_pair']:
                    if not any(v=='canonical_native_conflict'for u in(previous,current)for v in u['identity_statuses'].values()):
                        overlap=len(set(previous['native_guard_ids'])&set(current['native_guard_ids']));group='same'if overlap==2 else'changed';qualified=all(u['canonical_guard_ids']is not None for u in(previous,current))
                row=dict(game_id=current['game_id'],season=season,week=current['week'],team=team,previous_scheduled_game_id=previous['game_id']if previous else None,
                    comparison_applicable=previous is not None,guard_overlap=overlap,continuity_index=overlap/2 if overlap is not None else None,guard_class=group,canonical_qualified=qualified,
                    interior_response=_finish(counts[(current['game_id'],team)]))
                prior=team_rows[max(0,len(team_rows)-8):]
                if any(x['week']>=current['week']for x in prior):raise ValueError('Strictly prior scheduled response windows required')
                windows.append(dict(game_id=current['game_id'],season=season,team=team,contributing_game_ids=[x['game_id']for x in prior],max_contributing_period=max((season*100+x['week']for x in prior),default=None),target_period=season*100+current['week'],**_summarize(prior)))
                team_rows.append(row);rows.append(row)
            profiles.append(dict(season=season,team=team,observed_game_ids=[g['game_id']for g in games],**_summarize(team_rows)))
    core=dict(version=VERSION,catalog_id='X04-M03',starting_guard_units=all_units,game_rows=rows,profiles=profiles,prior_windows=windows,event_basis=basis,native_identity_receipts=identities,identity_review_requests=requests,future_alias_evidence_excluded=future,
        definitions=dict(continuity='Unordered exact2sourceG members current/previous scheduled same-team-season overlap/2; no LG/RG assignment, missing prior not skipped',
            interior='Tri-state native run_location=middle OR native run_gap=guard; left/right guard is interior; raw axes remain separate, no invented contradictions',
            response='Matched official nonkneel interior rush credited signed yards and provider EPA per eligible rush; all native rushers/scrambles, unknowns masked',
            cohorts='Pair unchanged vs changed observed whole-game response, pooled counts before rates; first game structural N/A, unknown classes mask applicable exact cells',
            timing='Historical observed source units, not pregame expected starters; prior windows at most8scheduledgames strictly before target'))
    return dict(**core,semantic_sha256=digest(core),evidence_use='historical_postseason_revised_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None)


def persist_guard_identity_requests(connection,features,*,source_refs):
    """Append-only evidence incidents; no aliases/canonical/resolved mutation."""
    from sqlalchemy import text
    import json,hashlib
    if features.get('version')!=VERSION or features.get('pregame_serving_eligible')is not False:raise ValueError('Exact offline guard feature required')
    requests=defaultdict(list)
    for row in features['identity_review_requests']:requests[(row['source_player_id'],row['reason'])].append(row)
    output=[]
    for (native,reason),incidents in sorted(requests.items()):
        evidence=[{k:r[k]for k in('alias_id','source_key','player_master_id','created_at')}for q in incidents for r in q['alias_evidence']]
        evidence=sorted({digest(r):r for r in evidence}.values(),key=lambda r:(str(r['alias_id']),r['source_key']))
        key='nflreadpy-gsis:'+native if reason=='unresolved_native_key'else'line-alias-conflict:'+native+':'+digest(evidence)
        qid='guard-native:'+hashlib.sha256(key.encode()).hexdigest()[:32];first=min(incidents,key=lambda r:r['game_id']);parts=first['game_id'].split('_');table='player_alias'if reason=='canonical_native_conflict'else'source_snapshot'
        connection.execute(text("""INSERT INTO target.identity_quarantine
        (identity_quarantine_id,entity_type,source_schema,source_table,source_record_key,source_system,season,week,slate,
         source_player_key,display_name,team_id,position,reason_code,candidate_player_ids,status,first_seen_at,updated_at)
        VALUES (:qid,'player','public',:table,:key,'nflreadpy',:season,:week,'FEATURE_INVENTORY',:native,NULL,:team,'G',:reason,CAST(:candidates AS jsonb),'open',now(),now())
        ON CONFLICT (source_schema,source_table,source_record_key) DO NOTHING"""),dict(qid=qid,table=table,key=key,native=native,season=int(parts[0]),week=int(parts[1]),team=first['team'],reason='guard_'+reason,candidates=json.dumps(sorted({r['player_master_id']for r in evidence}))))
        output.append(dict(source_table=table,source_record_key=key,intended_identity_quarantine_id=qid,source_player_key=native,reason=reason,all_native_game_ids=sorted({r['game_id']for r in incidents}),original_alias_evidence=evidence))
    return dict(records=output,requests=len(output),source_refs=deepcopy(source_refs),policy='Append only; DO NOTHING preserves existing resolved review cases; no aliases or canonical changes/name joins')
