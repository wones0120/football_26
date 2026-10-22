"""Historical player target performance versus directly charted coverage.

Observed initial-recipient target EPA/completions, not assigned-defender or
future-coverage forecasts. Exact statistics retain unknown membership.
"""
from collections import defaultdict
from copy import deepcopy
import math,re
from .evaluation_record import digest
from .market_snapshots import canonical_team
from .participation_source_components import VERSION as SOURCE_VERSION,_int
from .schedule_context_features import VERSION as SCHEDULE_VERSION
from .participation_defense_catalog import CATEGORIES
from .fumble_event_components import _flag,_eligibility
from .offensive_line_participation import resolve_line_identity

VERSION='coverage_receiver_performance_v1'
RECEIVING_ROLES={'WR','TE','RB','FB'}
CATEGORIES_USED=('man','zone')


def _num(value):
    try:n=float(value)
    except (ValueError,TypeError):return None
    return n if math.isfinite(n)else None


def _target_eligible(row):
    live,basis=_eligibility(row)
    if live is False:return False,basis
    p,r,s,sc,sp=(_flag(row.get(k))for k in('pass_attempt','rush_attempt','sack','qb_scramble','qb_spike'))
    if (p is True and r is True)or(r is True and s is True)or(sc is True and r is False):return None,'conflicting_official_flags'
    if live is None:return None,basis
    if p is False or s is True:return False,'not_official_target_attempt'
    if sp is True:return (None,'spike_receiver_conflict')if row.get('receiver_player_id')else(False,'known_spike')
    if p is True and r is False and s is False and sc is False and sp is False:return True,'official_nonspike_pass_attempt'
    return None,'missing_official_target_flags'


def _cell():return dict(known_targets=0,unknown_target_membership=0,known_completion_outcomes=0,completions=0,unknown_completions=0,known_EPA_outcomes=0,EPA_sum=0.,unknown_EPA=0)


def _finish(c):
    unknown=c['unknown_target_membership'];n=c['known_targets']
    return dict(**c,exact_targets=n if not unknown else None,
        completion_rate=c['completions']/n if n and not(unknown or c['unknown_completions'])else None,
        target_EPA_per_target=c['EPA_sum']/n if n and not(unknown or c['unknown_EPA'])else None,
        known_outcome_sample_completion_rate=c['completions']/c['known_completion_outcomes']if c['known_completion_outcomes']else None,
        known_outcome_sample_target_EPA=c['EPA_sum']/c['known_EPA_outcomes']if c['known_EPA_outcomes']else None)


def _summary(cells):
    cells={k:_finish(v)for k,v in cells.items()};m,z=cells['man'],cells['zone']
    return dict(cells=cells,
        man_minus_zone_completion_rate=m['completion_rate']-z['completion_rate']if m['completion_rate']is not None and z['completion_rate']is not None else None,
        man_minus_zone_target_EPA=m['target_EPA_per_target']-z['target_EPA_per_target']if m['target_EPA_per_target']is not None and z['target_EPA_per_target']is not None else None)


def build_native_coverage_performance(participation,pbp_rows,schedule,*,before_period,event_source_sha256):
    if participation.get('version')!=SOURCE_VERSION or schedule.get('version')!=SCHEDULE_VERSION or any(x.get('pregame_serving_eligible')is not False for x in(participation,schedule)):raise ValueError('Reviewed nonserving native sources required')
    if not re.fullmatch(r'[0-9a-f]{64}',event_source_sha256):raise ValueError('Original PBP SHA required')
    if type(before_period)is not int or not 1<=before_period%100<=18:raise ValueError('Strict prior REG boundary required')
    year=participation['season'];expected={};part_index={};events=[];seen=set();cohort=defaultdict(dict);universe=set()
    for g in schedule['game_rows']:
        if g['season']!=year or g['game_type']!='REG'or year*100+g['week']>=before_period:continue
        gid=g['game_id'];pair={canonical_team(g['home_team']),canonical_team(g['away_team'])}
        if len(pair)!=2 or gid.split('_')[:2]!=[str(year),f"{g['week']:02d}"]or {canonical_team(t)for t in gid.split('_')[2:]}!=pair or gid in expected:raise ValueError('Unique native schedule sides/period required')
        expected[gid]=dict(game_id=gid,season=year,week=g['week'],game_date=g.get('game_date'),sides=pair)
    for p in participation['rows']:
        key=(p['game_id'],p['play_id'])
        if key in part_index:raise ValueError('Duplicate participation native key')
        part_index[key]=p
    for raw in pbp_rows:
        if raw.get('season_type')!='REG':continue
        season=_int(raw['season']);week=_int(raw['week']);gid=raw['game_id'];play=_int(raw['play_id'])
        if season!=year or play is None or week is None or gid.split('_')[:2]!=[str(year),f'{week:02d}']:raise ValueError('Native event period/play required')
        if season*100+week>=before_period:continue
        if gid not in expected:raise ValueError('Native PBP game absent from expected schedule')
        key=(gid,str(play))
        if key in seen:raise ValueError('Duplicate native PBP key')
        seen.add(key);pair=expected[gid]['sides'];off=canonical_team(raw['posteam'])if raw.get('posteam')else None;defense=canonical_team(raw['defteam'])if raw.get('defteam')else None
        if any(t is not None and t not in pair for t in(off,defense))or off is not None and off==defense:raise ValueError('Native event sides conflict')
        p=part_index.get(key);scope=p['participant_scopes']['offense']if p else None
        source_conflict=bool(p and(p.get('native_phase')not in(None,'REG')or p.get('possession_team')!=off or off is None))
        mapping=scope.get('position_by_native_id')if scope else None;ids=scope.get('native_player_ids')if scope else None
        aligned=bool(p and not source_conflict and scope.get('status')=='aligned_native_position_list'and ids is not None and len(ids)==len(set(ids))==11 and mapping is not None and set(mapping)==set(ids))
        if aligned:
            universe.update(ids)
            for native,role in mapping.items():
                if role in RECEIVING_ROLES:cohort[(gid,off)].setdefault(native,set()).add(role)
        receiver=raw.get('receiver_player_id')or None
        if receiver is not None and(not isinstance(receiver,str)or not re.fullmatch(r'00-\d{7}',receiver)):raise ValueError('Native GSIS recipient required, no names')
        eligible,basis=_target_eligible(raw)
        if receiver and eligible is not False:
            universe.add(receiver)
            for team in({off}if off else pair):cohort[(gid,team)].setdefault(receiver,set()).add('explicit_native_target_actor')
        if eligible is False:continue
        attribution_conflict=bool(receiver and aligned and receiver not in ids)
        if attribution_conflict:receiver_proven=None
        else:receiver_proven=receiver
        text=p['measurements'].get('defense_man_zone_type')if p and not source_conflict else None
        category=CATEGORIES.get(text)if isinstance(text,str)else None
        explicit_unclassified=bool(p and not source_conflict and text in(None,'','UNKNOWN','UNCLASSIFIED'))
        events.append(dict(game_id=gid,play_id=str(play),offense=off,defense=defense,eligible_target_attempt=eligible,eligibility_basis=basis,
            native_receiver_id=receiver,attributed_receiver_id=receiver_proven,attribution_conflict=attribution_conflict,
            source_participation_present=p is not None,source_join_conflict=source_conflict,verified_offensive_eleven=aligned,
            native_offensive_players=sorted(ids)if aligned else None,native_man_zone=text,classified_category=category,
            explicit_source_unclassified=explicit_unclassified,complete_pass=_flag(raw.get('complete_pass')),target_play_EPA=_num(raw.get('epa'))))
    # Missing native-source games are kept as explicit unknown coverage, never zero.
    observed={gid for gid,play in seen};game_rows=[];residual=[]
    by_game=defaultdict(list)
    for e in events:by_game[e['game_id']].append(e)
    for (gid,team),natives in sorted(cohort.items()):
        game=expected[gid]
        for native,roles in sorted(natives.items()):
            cells={k:_cell()for k in CATEGORIES_USED};excluded_by_eleven=0
            for e in by_game[gid]:
                if e['offense']is not None and e['offense']!=team:continue
                category=e['classified_category'];eligible=e['eligible_target_attempt'];recipient=e['attributed_receiver_id']
                if category is not None and category not in CATEGORIES_USED:continue
                if e['explicit_source_unclassified']:continue
                target_categories=(category,)if category in CATEGORIES_USED else CATEGORIES_USED
                if eligible is True and recipient is not None and e['offense']is not None:
                    if recipient!=native:continue
                    if category not in CATEGORIES_USED:
                        for name in target_categories:cells[name]['unknown_target_membership']+=1
                        continue
                    c=cells[category];c['known_targets']+=1
                    if e['complete_pass']is None:c['unknown_completions']+=1
                    else:c['known_completion_outcomes']+=1;c['completions']+=int(e['complete_pass'])
                    if e['target_play_EPA']is None:c['unknown_EPA']+=1
                    else:c['known_EPA_outcomes']+=1;c['EPA_sum']+=e['target_play_EPA']
                elif e['verified_offensive_eleven']and native not in e['native_offensive_players']and not e['attribution_conflict']:
                    excluded_by_eleven+=1
                else:
                    for name in target_categories:cells[name]['unknown_target_membership']+=1
            game_rows.append(dict(game_id=gid,season=year,week=game['week'],team=team,source_player_id=native,source_roles=sorted(roles),
                unknown_recipient_events_excluded_by_verified_off_field=excluded_by_eleven,**_summary(cells)))
    for e in events:
        if e['attributed_receiver_id']is None or e['eligible_target_attempt']is not True or e['offense']is None or e['classified_category']is None:
            residual.append(dict(game_id=e['game_id'],play_id=e['play_id'],offense=e['offense'],category=e['classified_category'],
                reason='Unassigned target eligibility/recipient/category remains unknown; possible actors outside declared role cohort retained',
                potential_native_players=e['native_offensive_players'],unknown_other_candidates=e['native_offensive_players']is None))
    core=dict(version=VERSION,catalog_id='G16-M10',before_period=before_period,season=year,game_rows=game_rows,event_basis=events,unassigned_residual=residual,
        expected_games=[{**r,'sides':sorted(r['sides'])}for r in sorted(expected.values(),key=lambda x:x['game_id'])],
        missing_PBP_game_ids=sorted(set(expected)-observed),native_identity_universe=sorted(universe),
        definitions=dict(response='Initial-recipient source complete_pass and full target-play provider EPA per matched official nonspike target',
            coverage='Direct publisher MAN/ZONE only; mixed/other/explicit unclassified excluded from conditional channels, unknown category membership masks both',
            cohort='Observed verified WR/TE/RB/FB participants plus any explicit native target actor, including QB/OL; no route/assignment inference',
            off_field='Only same native game/play/offense/phase exact11 unique aligned GSIS proves actor not on play; no role-based target ineligibility',
            completeness='Observed log only; missing actor-game participation/unknown recipient/eligibility/outcome never absent-zero'))
    return dict(**core,semantic_sha256=digest(core),provenance=dict(participation_semantic_sha256=participation['semantic_sha256'],original_PBP_sha256=event_source_sha256),
        evidence_use='historical_postseason_revised_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None)


def attach_and_window_performance(blocks,alias_rows,*,cutoff,identity_universe):
    if not blocks or any(b.get('version')!=VERSION or b.get('pregame_serving_eligible')is not False for b in blocks):raise ValueError('Exact nonserving native blocks required')
    universe=set(identity_universe);needed={n for b in blocks for n in b['native_identity_universe']}
    if not needed<=universe:raise ValueError('Global native identity universe must include all source actors')
    identities,future=resolve_line_identity(universe,alias_rows,cutoff=cutoff);rows=[];requests=[];seen=set();profiles=[];windows=[]
    for block in blocks:
        expected=block['expected_games'];source_index={(r['game_id'],r['team'],r['source_player_id']):r for r in block['game_rows']}
        team_schedules=defaultdict(list)
        for g in expected:
            for team in g['sides']:team_schedules[team].append(g)
        for team,games in team_schedules.items():
            if any(not g.get('game_date')for g in games)or len({g['game_date']for g in games})!=len(games):raise ValueError('Unique native scheduled dates required')
            games.sort(key=lambda g:g['game_date'])
            natives=sorted({r['source_player_id']for r in block['game_rows']if r['team']==team})
            for native in natives:
                proof=identities[native];actor_rows=[]
                for i,g in enumerate(games):
                    row=source_index.get((g['game_id'],team,native))
                    if row is None:continue
                    key=(g['game_id'],team,native)
                    if key in seen:raise ValueError('Duplicate native actor-game across sources')
                    seen.add(key);row=deepcopy(row);row.update(player_master_id=proof['player_master_id'],identity_status=proof['status'])
                    if proof['status']!='unique_native_alias':requests.append(dict(game_id=g['game_id'],team=team,source_player_id=native,position='/'.join(row['source_roles']),reason=proof['status'],alias_evidence=deepcopy(proof['original_alias_evidence'])))
                    rows.append(row);actor_rows.append(row)
                    prior=games[max(0,i-8):i]
                    if any(old['season']*100+old['week']>=g['season']*100+g['week']for old in prior):raise ValueError('Every contributing scheduled game must be strictly prior period')
                    cells={k:_cell()for k in CATEGORIES_USED};missing=[]
                    for old in prior:
                        previous=source_index.get((old['game_id'],team,native))
                        if previous is None:missing.append(old['game_id']);continue
                        for name in CATEGORIES_USED:
                            for field in _cell():cells[name][field]+=previous['cells'][name][field]
                    summary=_summary(cells);known_sample=deepcopy(summary)
                    if missing:
                        for cell in summary['cells'].values():
                            for field in('exact_targets','completion_rate','target_EPA_per_target'):cell[field]=None
                        summary['man_minus_zone_completion_rate']=None;summary['man_minus_zone_target_EPA']=None
                    windows.append(dict(game_id=g['game_id'],season=block['season'],team=team,source_player_id=native,player_master_id=proof['player_master_id'],
                        target_period=block['season']*100+g['week'],contributing_game_ids=[old['game_id']for old in prior],
                        max_contributing_period=max((block['season']*100+old['week']for old in prior),default=None),missing_actor_game_ids=missing,
                        known_observed_game_sample=known_sample,**summary))
                pooled={k:_cell()for k in CATEGORIES_USED}
                for row in actor_rows:
                    for name in CATEGORIES_USED:
                        for field in _cell():pooled[name][field]+=row['cells'][name][field]
                profiles.append(dict(season=block['season'],team=team,source_player_id=native,player_master_id=proof['player_master_id'],observed_game_ids=[r['game_id']for r in actor_rows],
                    scope='Only observed actor games; not full-season participation proof',**_summary(pooled)))
    core=dict(version=VERSION,catalog_id='G16-M10',source_components=[dict(season=b['season'],semantic_sha256=b['semantic_sha256'])for b in blocks],game_rows=rows,profiles=profiles,prior_windows=windows,
        native_identity_receipts=identities,identity_review_requests=requests,future_alias_evidence_excluded=future,
        definitions=blocks[0]['definitions'],units=dict(completion_rate='completions/known official recipient targets',target_EPA_per_target='provider expected points/recipient target',contrast='MAN minus ZONE in same units'))
    return dict(**core,semantic_sha256=digest(core),evidence_use='historical_postseason_revised_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None)


def persist_coverage_identity_requests(connection,features,*,source_refs):
    """Existing append-only identity UI; retain canonical conflicts across all periods."""
    from sqlalchemy import text
    import hashlib,json
    requests=defaultdict(list)
    for block in features:
        if block.get('version')!=VERSION or block.get('pregame_serving_eligible')is not False:raise ValueError('Exact nonserving coverage source required')
        for row in block['identity_review_requests']:requests[(row['source_player_id'],row['reason'])].append(row)
    output=[]
    for (native,reason),incidents in sorted(requests.items()):
        evidence=[{k:r[k]for k in('alias_id','source_key','player_master_id','created_at')}for q in incidents for r in q['alias_evidence']]
        evidence=sorted({digest(r):r for r in evidence}.values(),key=lambda r:(str(r['alias_id']),r['source_key']))
        key='nflreadpy-gsis:'+native if reason=='unresolved_native_key'else'line-alias-conflict:'+native+':'+digest(evidence)
        qid='coverage-native:'+hashlib.sha256(key.encode()).hexdigest()[:32];first=min(incidents,key=lambda r:r['game_id']);parts=first['game_id'].split('_')
        table='player_alias'if reason=='canonical_native_conflict'else'source_snapshot'
        connection.execute(text("""INSERT INTO target.identity_quarantine
        (identity_quarantine_id,entity_type,source_schema,source_table,source_record_key,source_system,season,week,slate,
         source_player_key,display_name,team_id,position,reason_code,candidate_player_ids,status,first_seen_at,updated_at)
        VALUES (:qid,'player','public',:table,:key,'nflreadpy',:season,:week,'FEATURE_INVENTORY',:native,NULL,:team,NULL,:reason,CAST(:candidates AS jsonb),'open',now(),now())
        ON CONFLICT (source_schema,source_table,source_record_key) DO NOTHING"""),dict(qid=qid,table=table,key=key,native=native,season=int(parts[0]),week=int(parts[1]),team=first['team'],reason='coverage_'+reason,candidates=json.dumps(sorted({r['player_master_id']for r in evidence}))))
        output.append(dict(source_table=table,source_record_key=key,intended_identity_quarantine_id=qid,source_player_key=native,reason=reason,
            all_native_game_ids=sorted({r['game_id']for r in incidents}),original_alias_evidence=evidence))
    return dict(records=output,requests=len(output),source_refs=deepcopy(source_refs),policy='Append only; conflict preserves existing/resolved cases; no canonical or alias changes/name joins')
