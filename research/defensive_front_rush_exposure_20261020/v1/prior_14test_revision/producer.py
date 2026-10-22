"""Observed directional rush exposure by native defensive personnel counts."""
from collections import Counter,defaultdict
import math
from .evaluation_record import digest
from .market_snapshots import canonical_team
from .fumble_event_components import _flag,_eligibility
from .participation_source_components import VERSION as SOURCE_VERSION,_int

VERSION='defensive_front_rush_exposure_v1'
ROLE_FAMILIES={'DE':'DL','DT':'DL','NT':'DL','LB':'LB','ILB':'LB','OLB':'LB','MLB':'LB','CB':'DB','S':'DB','FS':'DB','SS':'DB'}
DIRECTIONS=('left','middle','right')


def _and(a,b):return False if a is False or b is False else True if a is True and b is True else None


def _number(value):
    return float(value)if type(value)in(int,float)and math.isfinite(value)else None


def _personnel(source,offense):
    if offense is None:return None,'Unknown native offense/opponent membership'
    if source is None:return None,'Missing participation'
    if source.get('native_phase')not in(None,'REG')or source.get('possession_team')!=offense:return None,'Unknown or conflicting source possession/phase'
    scope=source['participant_scopes']['defense'];positions=scope.get('position_by_native_id');ids=scope.get('native_player_ids')
    if scope.get('status')!='aligned_native_position_list'or not isinstance(positions,dict)or ids is None or len(ids)!=11 or len(set(ids))!=11 or set(positions)!=set(ids):return None,'Eleven unique aligned native defensive participants not proven'
    if any(not isinstance(position,str)or not position or position in {'UNKNOWN','UNK','UNSPECIFIED','NA','N/A'} for position in positions.values()):return None,'Unknown native position'
    counts=Counter(ROLE_FAMILIES.get(position,'OTHER')for position in positions.values())
    return tuple(counts[k]for k in('DL','LB','DB','OTHER')),None


def _summary(events):
    events=sorted(events,key=lambda e:(e['game_id'],int(e['play_id'])))
    unknown=sum(e['eligible']is None or e['offense']is None or e['personnel']is None or e['direction']is None for e in events)
    cells=[]
    for personnel in sorted({tuple(e['personnel'])for e in events if e['eligible']is True and e['personnel']is not None}):
        for direction in DIRECTIONS:
            sample=[e for e in events if e['eligible']is True and e['offense']is not None and e['personnel']==personnel and e['direction']==direction]
            measures={}
            for field,unit in(('rushing_yards','yards'),('epa','provider_expected_points')):
                values=[e[field]for e in sample if e[field]is not None];missing=len(sample)-len(values)
                known_sum=sum(values)
                exact=not(unknown or missing)
                measures[field]=dict(exact_sum=known_sum if exact else None,exact_mean=known_sum/len(sample)if exact and sample else None,
                    known_outcome_sum=known_sum,known_outcome_mean=known_sum/len(values)if values else None,known_outcome_exposures=len(values),unknown_outcome_exposures=missing,unit=unit)
            cells.append(dict(personnel_counts=dict(zip(('DL','LB','DB','OTHER'),personnel)),direction=direction,
                exact_exposure_count=len(sample)if not unknown else None,known_exposure_lower_bound=len(sample),outcomes=measures))
    return dict(observed_event_rows=len(events),known_eligible_rushes=sum(e['eligible']is True and e['offense']is not None for e in events),
        unknown_eligibility=sum(e['eligible']is None for e in events),unknown_offense_membership=sum(e['offense']is None for e in events),unknown_condition_membership=unknown,
        known_classified_rushes=sum(e['eligible']is True and e['offense']is not None and e['personnel']is not None and e['direction']is not None for e in events),cells=cells)


def build_defensive_front_rush_exposure(participation,pbp_rows,*,before_period):
    if participation.get('version')!=SOURCE_VERSION or participation.get('pregame_serving_eligible')is not False:raise ValueError('Reviewed historical participation required')
    if type(before_period)is not int or not 200001<=before_period or not 1<=before_period%100<=19:raise ValueError('Strict prior REG period required')
    season=participation['season'];source={};seen=set();events=[];groups=defaultdict(list);expected=set()
    for r in participation['rows']:
        key=(r['game_id'],r['play_id'])
        if key in source:raise ValueError('Duplicate native participation game/play')
        source[key]=r
    for raw in pbp_rows:
        gid=raw['game_id'];parts=gid.split('_');year=_int(raw['season']);week=_int(raw['week']);play=str(_int(raw['play_id']))
        if len(parts)!=4 or parts[:2]!=[str(year),f'{week:02d}']or year!=season or not 1<=week<=22:raise ValueError('Native PBP game/season/week required')
        key=(gid,play)
        if key in seen:raise ValueError('Duplicate native PBP game/play')
        seen.add(key)
        if raw.get('season_type')!='REG'or year*100+week>=before_period:continue
        sides={canonical_team(t)for t in parts[2:]}
        if len(sides)!=2:raise ValueError('Two distinct native game teams required')
        for team in sides:expected.add((gid,team))
        off=canonical_team(raw['posteam'])if raw.get('posteam')else None;defense=canonical_team(raw['defteam'])if raw.get('defteam')else None
        if any(t is not None and t not in sides for t in(off,defense))or off is not None and off==defense:raise ValueError('Native PBP sides contradict game')
        rushing=_flag(raw.get('rush_attempt'));kneel=_flag(raw.get('qb_kneel'))
        eligible=_and(_eligibility(raw)[0],_and(rushing,None if kneel is None else not kneel))
        if eligible is False:continue
        # Defense side must be explicit rather than inferred from an unknown offense.
        if defense is None:off_for_join=None
        else:off_for_join=off
        personnel,reason=_personnel(source.get(key),off_for_join)
        location=raw.get('run_location');direction=location if location in DIRECTIONS else None
        event=dict(game_id=gid,play_id=play,original_offense=off,original_defense=defense,offense=off if defense is not None else None,defense=defense,eligible=eligible,
            personnel=personnel,direction=direction,original_run_location=location,original_run_gap=raw.get('run_gap'),
            personnel_unknown_reason=reason,rushing_yards=_number(raw.get('rushing_yards')),epa=_number(raw.get('epa')))
        events.append(event)
        for team in {off}if off is not None and defense is not None else sides:groups[(gid,team)].append(event)
    game_rows=[dict(game_id=gid,offense=team,defense=next(t for t in{canonical_team(p)for p in gid.split('_')[2:]}if t!=team),**_summary(groups[(gid,team)]))for gid,team in sorted(expected)]
    profiles=[]
    for team in sorted({team for _,team in expected}):
        matches=[e for(g,t),items in groups.items()if t==team for e in items]
        profiles.append(dict(season=season,offense=team,observed_games=sorted(g for g,t in expected if t==team),**_summary(matches)))
    core=dict(version=VERSION,candidate_ids=['X04-M06'],before_period=before_period,season=season,team_game_rows=game_rows,profiles=profiles,event_basis=sorted(events,key=lambda e:(e['game_id'],int(e['play_id']))),
        definition=dict(exposure='Official nonkneel non2PT nonnullified rush, including scramble once; all native rushers',personnel='Exactly11 unique source-reported defenders; DL=DE/DT/NT,LB=LB/ILB/OLB/MLB,DB=CB/S/FS/SS; all other explicit roles separate OTHER',
            direction='Native run_location left/middle/right, raw gap retained without inferred alignment',unknown='Unknown eligibility/side/personnel/direction masks all exact cells in affected game/profile; known samples separately labeled',
            units='Rush exposure counts; signed rushing yards and provider-derived EPA sums/means with matched known outcome denominators'),
        evidence_use='historical_postseason_revised_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None,
        source_gaps=['Reported positions do not prove alignment, box count, scheme/front technique or blocking assignment','No current2026 participation fallback or original historical pregame availability','No pressure, fitted response, causal effect or future probability'])
    return dict(**core,semantic_sha256=digest(core),provenance=dict(participation_semantic_sha256=participation['semantic_sha256']))
