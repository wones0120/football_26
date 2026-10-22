"""Historical deep passing conditioned on direct native COVER-family labels.

Coverage labels are observed play classifications, not inferred safety depth,
individual assignments or a forecast of the opponent's next call.
"""
from collections import defaultdict
from copy import deepcopy
import math
from .evaluation_record import digest
from .coverage_receiver_performance import VERSION as PARENT_VERSION
from .participation_source_components import VERSION as SOURCE_VERSION, _int
from .market_snapshots import canonical_team

VERSION='deep_coverage_response_v1'
FAMILIES=('COVER_0','COVER_1','COVER_2','2_MAN','COVER_3','COVER_4','COVER_6','COVER_9','COMBO','BLOWN')


def _depth(value):
    if value in (None,'') or type(value)is bool:return None
    try:n=float(value)
    except (TypeError,ValueError):return None
    return n if math.isfinite(n) else None


def _counter():
    return dict(known_official_attempts=0,known_depth_exposures=0,unknown_attempt_membership=0,known_deep_attempts=0,unknown_deep_membership=0,
        known_completion_exposures=0,completions=0,unknown_completions=0,known_EPA_exposures=0,EPA_sum=0.,unknown_EPA=0,missing_source_games=0)


def _finish(c):
    n=c['known_deep_attempts'];a=c['known_official_attempts'];u=c['unknown_deep_membership'] or c['missing_source_games']
    return dict(**c,exact_official_attempts=a if not(c['unknown_attempt_membership'] or c['missing_source_games']) else None,
        exact_deep_attempts=n if not u else None,
        deep_opportunity_fraction=n/a if a and not(u or c['unknown_attempt_membership']) else None,
        completion_rate=c['completions']/n if n and not(u or c['unknown_completions']) else None,
        EPA_per_deep_attempt=c['EPA_sum']/n if n and not(u or c['unknown_EPA']) else None,
        known_depth_sample_opportunity_fraction=n/c['known_depth_exposures'] if c['known_depth_exposures'] else None,
        known_outcome_sample_completion=c['completions']/c['known_completion_exposures'] if c['known_completion_exposures'] else None,
        known_outcome_sample_EPA=c['EPA_sum']/c['known_EPA_exposures'] if c['known_EPA_exposures'] else None)


def _pool(cells):return {k:sum(c[k] for c in cells) for k in _counter()}


def _summary(cells,unknown):
    # Missing category may belong to this family OR its complement. Apply its
    # uncertainty once to each side, never once per other-family voting cell.
    result={}
    for family in FAMILIES:
        selected=_finish(_pool([cells[family],unknown]))
        other=_finish(_pool([c for name,c in cells.items() if name!=family]+[unknown]))
        def diff(key):
            a,b=selected[key],other[key]
            return a-b if a is not None and b is not None else None
        result[family]=dict(reported_family=selected,other_explicit_classified_families=other,
            family_minus_other_deep_completion=diff('completion_rate'),family_minus_other_deep_EPA=diff('EPA_per_deep_attempt'),
            known_sample_completion_difference=diff('known_outcome_sample_completion'),known_sample_EPA_difference=diff('known_outcome_sample_EPA'))
    return result


def _add(c,eligible,deep,completion,epa,side_known,category_known):
    if eligible is True and side_known and category_known:c['known_official_attempts']+=1
    else:c['unknown_attempt_membership']+=1
    if eligible is True and side_known and category_known and deep is not None:c['known_depth_exposures']+=1
    if deep is False:return
    if eligible is not True or deep is None or not side_known or not category_known:
        c['unknown_deep_membership']+=1;return
    c['known_deep_attempts']+=1
    if completion is None:c['unknown_completions']+=1
    else:c['known_completion_exposures']+=1;c['completions']+=int(completion)
    if epa is None:c['unknown_EPA']+=1
    else:c['known_EPA_exposures']+=1;c['EPA_sum']+=epa


def build_deep_coverage_response(parent,participation,measurements):
    if parent.get('version')!=PARENT_VERSION or parent.get('pregame_serving_eligible')is not False or participation.get('version')!=SOURCE_VERSION or participation.get('pregame_serving_eligible')is not False:raise ValueError('Reviewed nonserving native parents required')
    season=parent['season']
    if participation['season']!=season:raise ValueError('Exact same participation season required')
    expected={g['game_id']:g for g in parent['expected_games']}
    if len(expected)!=len(parent['expected_games']):raise ValueError('Duplicate expected native games')
    source={};depths={};groups={};basis=[];seen=set()
    for p in participation['rows']:
        key=(p['game_id'],str(p['play_id']))
        if key in source:raise ValueError('Duplicate participation native key')
        source[key]=p
    for raw in measurements:
        if raw.get('season_type')!='REG':continue
        year=_int(raw['season']);week=_int(raw['week']);gid=raw['game_id'];play=str(_int(raw['play_id']));parts=gid.split('_')
        if len(parts)!=4 or parts[:2]!=[str(year),f'{week:02d}'] or not 1<=week<=18:raise ValueError('Native measurement game/period required')
        if year*100+week>=parent['before_period']:continue
        if year!=season:raise ValueError('Native measurement season differs')
        key=(gid,play)
        if key in depths:raise ValueError('Duplicate PBP depth native key')
        depths[key]=raw
    for gid,g in expected.items():
        if g['season']!=season or len(set(g['sides']))!=2 or not 1<=g['week']<=18 or season*100+g['week']>=parent['before_period']:raise ValueError('Prior REG game and two expected native sides required')
        for team in g['sides']:
            groups[(gid,team)]=dict(game_id=gid,season=season,week=g['week'],team=team,opponent=next(t for t in g['sides'] if t!=team),
                offense={f:_counter() for f in FAMILIES},defense={f:_counter() for f in FAMILIES},offense_unknown=_counter(),defense_unknown=_counter())
            if gid in parent['missing_PBP_game_ids']:
                groups[(gid,team)]['offense_unknown']['missing_source_games']=1
                groups[(gid,team)]['defense_unknown']['missing_source_games']=1
    for e in parent['event_basis']:
        gid=e['game_id'];key=(gid,str(e['play_id']));g=expected.get(gid);raw=depths.get(key)
        if key in seen or g is None or raw is None:raise ValueError('Unique expected native event/depth key required')
        seen.add(key);eligible=e['eligible_target_attempt'];off=e['offense'];defense=e['defense'];sides=set(g['sides'])
        if eligible is not None and type(eligible)is not bool:raise ValueError('Explicit tri-state official attempt eligibility required')
        for field,side in (('posteam',off),('defteam',defense)):
            value=canonical_team(raw[field]) if raw.get(field) else None
            if value!=side:raise ValueError('PBP depth/native attempt side differs')
        if any(t is not None and t not in sides for t in(off,defense)) or off is not None and off==defense:raise ValueError('Native response sides differ')
        p=source.get(key);conflict=False
        if p:
            # Legacy participation may omit phase; the authenticated same-key
            # PBP row explicitly supplies REG, rather than guessing from absence.
            conflict=(p['season'],p['week'])!=(season,g['week']) or p.get('native_phase') not in (None,'REG') or p['possession_team']!=off or e['source_join_conflict']
        label=p['measurements'].get('defense_coverage_type') if p else None
        family=label if not conflict and label in FAMILIES else None
        air=_depth(raw.get('air_yards'));deep=None if air is None else air>=20
        if eligible is False:continue
        completion=e['complete_pass'];epa=e['target_play_EPA']
        if completion is not None and type(completion)is not bool:raise ValueError('Tri-state native completion required')
        if epa is not None and (type(epa)not in (int,float) or not math.isfinite(epa)):raise ValueError('Finite signed provider EPA required')
        side_known=off is not None and defense is not None
        for role,team in (('offense',off),('defense',defense)):
            for candidate in ({team} if team is not None else sides):
                row=groups[(gid,candidate)];c=row[role][family] if family is not None else row[role+'_unknown']
                _add(c,eligible,deep,completion,epa,side_known,family is not None)
        basis.append(dict(game_id=gid,play_id=key[1],offense=off,defense=defense,official_nonspike_attempt=eligible,
            original_air_yards=air,deep_at_least20=deep,raw_defense_coverage_type=label,reported_family=family,
            source_participation_present=p is not None,source_join_conflict=conflict,original_participation_phase=p.get('native_phase') if p else None,
            phase_basis='authenticated_same_native_PBP_REG',complete_pass=completion,target_play_EPA=epa))
    if set(depths)!=seen:raise ValueError('Complete same-source REG native event/depth universe required')
    game_rows=[]
    for _,row in sorted(groups.items()):
        game_rows.append({k:row[k] for k in ('game_id','season','week','team','opponent')}|dict(
            offense=_summary(row['offense'],row['offense_unknown']),defense=_summary(row['defense'],row['defense_unknown']),
            counters={k:deepcopy(row[k]) for k in ('offense','defense','offense_unknown','defense_unknown')}))
    profiles=[]
    for team in sorted({team for gid,team in groups}):
        rs=[r for (gid,t),r in groups.items() if t==team]
        profile=dict(season=season,team=team,observed_game_ids=sorted(r['game_id'] for r in rs))
        for role in ('offense','defense'):
            cells={f:_pool([r[role][f] for r in rs]) for f in FAMILIES};unknown=_pool([r[role+'_unknown'] for r in rs])
            profile[role]=_summary(cells,unknown)
        profiles.append(profile)
    core=dict(version=VERSION,catalog_id='G16-M05',season=season,before_period=parent['before_period'],deep_threshold_air_yards=20,
        native_coverage_families=list(FAMILIES),game_rows=game_rows,profiles=profiles,event_basis=basis,
        definitions=dict(opportunity='Official nonspike air_yards>=20 attempts / all official nonspike attempts within direct native coverage family',
            response='Same-event source completion and provider target-play EPA per deep attempt; reported family vs all other explicit classified families',
            coverage='Literal published defense_coverage_type only, including COMBO/BLOWN; not inferred safety count/depth or assigned defender',
            baseline='Pooled other explicit classified families within same game or observed same-season/team profile, matched counts before rates'),
        evidence_use='historical_postseason_revised_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None,
        limitations=['Coverage observed on past play, not future coverage selection or causal advantage',
            'Postseason FTN2023–25 source, original historical pregame availability unknown; no current2026 fallback',
            'Missing depth/category/eligibility/side/outcome retains relevant full-cell uncertainty; samples are not full populations',
            'Team-grain all native passers and receivers; no identity/role filter, no extra opportunities',
            'Observed logs do not establish full-game completeness or fitted/calibrated probability'])
    return dict(**core,semantic_sha256=digest(core),provenance=dict(native_attempt_semantic_sha256=parent['semantic_sha256'],participation_semantic_sha256=participation['semantic_sha256']))


def read_native_attempt_parent(ref,*,actual_read_at,published_at,directory=None):
    """File-only native attempt authority with frozen publication/producer proof."""
    from datetime import datetime,UTC
    from pathlib import Path
    import hashlib,json
    from .factual_designation import clock
    read=clock(actual_read_at);published=clock(published_at)
    if read is None or published is None or not published<=read<=datetime.now(UTC):raise ValueError('Actual publication/read chronology required')
    path=Path(ref['path']);base=Path(directory or 'artifacts/coverage_receiver_performance')
    if path.resolve().parent!=base.resolve() or ref['bytes']>32*1024*1024:raise ValueError('Managed native parent path/byte bound differs')
    raw=path.read_bytes()
    if len(raw)!=ref['bytes'] or hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('Immutable native parent bytes differ')
    parent=json.loads(raw)
    if parent.get('version')!=PARENT_VERSION or parent.get('pregame_serving_eligible')is not False:raise ValueError('Reviewed nonserving attempt parent required')
    core={k:v for k,v in parent.items() if k not in ('semantic_sha256','provenance','evidence_use','pregame_serving_eligible','forecast')}
    if digest(core)!=parent['semantic_sha256']:raise ValueError('Native parent semantic core differs')
    provenance=parent['provenance']
    for field in ('actual_read_at','actual_derived_at'):
        at=clock(provenance.get(field))
        if at is None or at>published:raise ValueError('Native parent creation clock differs')
    required={'backend/app/product_services/'+p+'.py' for p in ('coverage_receiver_performance','participation_source_components','fumble_event_components')}
    hashes=provenance.get('producer_code_hashes',{})
    if not required<=set(hashes):raise ValueError('Native parent producer ancestry missing')
    for name,value in hashes.items():
        p=Path(name)
        if p.resolve().parent!=Path('backend/app/product_services').resolve() or hashlib.sha256(p.read_bytes()).hexdigest()!=value:raise ValueError('Native parent producer ancestry differs')
    return parent
