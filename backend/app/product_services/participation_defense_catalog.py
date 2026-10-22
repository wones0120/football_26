"""Native historical coverage rates; pressure field retains taxonomy limits."""
from collections import Counter,defaultdict
from copy import deepcopy
from decimal import Decimal
from .evaluation_record import digest
from .market_snapshots import canonical_team
from .fumble_event_components import _flag,_eligibility
from .participation_source_components import VERSION as SOURCE_VERSION,_int

VERSION='participation_defense_catalog_v1'
CATEGORIES={'MAN':'man','MAN_COVERAGE':'man','ZONE':'zone','ZONE_COVERAGE':'zone','MIXED':'mixed','OTHER':'other'}


def _and(a,b):return False if a is False or b is False else True if a is True and b is True else None

def _or(*values):return True if any(v is True for v in values)else False if all(v is False for v in values)else None


def _counter():return dict(known_eligible_dropbacks=0,unknown_eligible_dropbacks=0,known_pressure_outcomes=0,source_pressure_count=0,unknown_pressure_outcomes=0,
    sack_pressure_conflicts=0,classified_dropbacks=0,man_dropbacks=0,zone_dropbacks=0,mixed_dropbacks=0,other_dropbacks=0,
    unclassified_dropbacks=0,unknown_classified_membership=0,missing_participation_rows=0,source_join_conflicts=0)


def _finish(c):
    n=c['known_eligible_dropbacks'];classified=c['classified_dropbacks'];unknown_class=c['unknown_classified_membership']
    p=c['source_pressure_count']/n if n and not(c['unknown_eligible_dropbacks']or c['unknown_pressure_outcomes'])else None
    metrics={}
    for mid,category in (('G14-M04','man'),('G14-M05','zone')):
        value=c[category+'_dropbacks']/classified if classified and not unknown_class else None
        full=c[category+'_dropbacks']/n if n and not(c['unknown_eligible_dropbacks']or c['unclassified_dropbacks']or unknown_class)else None
        metrics[mid]=dict(value=value,unit='fraction_of_classified_nonspike_dropbacks',numerator=c[category+'_dropbacks'],classified_denominator=classified,
            known_classified_sample_fraction=c[category+'_dropbacks']/classified if classified else None,unknown_classified_membership=unknown_class,
            full_eligible_dropback_fraction=full,full_eligible_denominator=n,unclassified_residual=c['unclassified_dropbacks'],
            mixed_classified_residual=c['mixed_dropbacks'],other_classified_residual=c['other_dropbacks'])
    return dict(**c,metrics=metrics,native_pressure_variant=dict(value=p,known_outcome_sample_fraction=c['source_pressure_count']/c['known_pressure_outcomes']if c['known_pressure_outcomes']else None,
        unit='native_provider_pressure_bool_per_nonspike_dropback',catalog_id='G14-M01',catalog_value=None,
        catalog_definition_status='pending_provider_event_taxonomy_HHS_evidence; native boolean alone is a measured variant',
        numerator=c['source_pressure_count'],denominator=n,unknown_outcomes=c['unknown_pressure_outcomes'],unknown_eligibility=c['unknown_eligible_dropbacks']))


def build_participation_defense_catalog(participation,pbp_rows,*,before_period):
    if participation.get('version')!=SOURCE_VERSION or participation.get('pregame_serving_eligible')is not False:raise ValueError('Reviewed nonserving native participation required')
    if type(before_period)is not int or not 200001<=before_period or not 1<=before_period%100<=19:raise ValueError('Strict prior REG boundary required')
    source={};season=participation['season'];seen=set();totals={};basis=[]
    for r in participation['rows']:
        key=(r['game_id'],r['play_id'])
        if key in source:raise ValueError('Duplicate native participation game/play')
        source[key]=r
    for r in pbp_rows:
        gid=r['game_id'];parts=gid.split('_');year=_int(r['season']);week=_int(r['week']);play=str(_int(r['play_id']))
        if len(parts)!=4 or parts[:2]!=[str(year),f'{week:02d}']or year!=season or not 1<=week<=22:raise ValueError('Native PBP season/game/week required')
        key=(gid,play)
        if key in seen:raise ValueError('Duplicate native PBP play')
        seen.add(key)
        if r.get('season_type')!='REG'or year*100+week>=before_period:continue
        pair={canonical_team(t)for t in parts[2:]}
        if len(pair)!=2:raise ValueError('Two native game sides required')
        for team in pair:totals.setdefault((gid,team),_counter())
        off=r.get('posteam')or None;defense=r.get('defteam')or None
        if off is not None:off=canonical_team(off)
        if defense is not None:defense=canonical_team(defense)
        if any(t is not None and t not in pair for t in (off,defense))or off is not None and off==defense:raise ValueError('PBP native sides contradict game')
        passing=_flag(r.get('pass_attempt'));sack=_flag(r.get('sack'));rushing=_flag(r.get('rush_attempt'));scramble=_flag(r.get('qb_scramble'));spike=_flag(r.get('qb_spike'))
        physical=_or(passing,sack,_and(rushing,scramble))
        if scramble is True and rushing is False:physical=None
        eligible=_and(_eligibility(r)[0],_and(physical,None if spike is None else not spike))
        if eligible is False:continue
        s=source.get(key);conflict=bool(s is not None and (s.get('native_phase')not in (None,'REG')or s.get('possession_team')is not None and off is not None and s['possession_team']!=off))
        pressure=s['measurements'].get('was_pressure')if s is not None and not conflict else None
        if type(pressure)is not bool:pressure=None
        text=s['measurements'].get('defense_man_zone_type')if s is not None and not conflict else None
        category=CATEGORIES.get(text)if isinstance(text,str)else None
        explicit_unclassified=s is not None and not conflict and text in (None,'','UNKNOWN','UNCLASSIFIED')
        original_pressure=pressure
        contradiction=sack is True and pressure is False
        if contradiction:pressure=None
        targets={defense}if defense is not None else pair
        for team in targets:
            c=totals[(gid,team)]
            if eligible is None or defense is None:
                c['unknown_eligible_dropbacks']+=1
                if not explicit_unclassified:c['unknown_classified_membership']+=1
            else:
                c['known_eligible_dropbacks']+=1
                if pressure is None:c['unknown_pressure_outcomes']+=1
                else:c['known_pressure_outcomes']+=1;c['source_pressure_count']+=int(pressure)
                if category is not None:c['classified_dropbacks']+=1;c[category+'_dropbacks']+=1
                else:
                    c['unclassified_dropbacks']+=1
                    if not explicit_unclassified:c['unknown_classified_membership']+=1
            c['missing_participation_rows']+=int(s is None);c['source_join_conflicts']+=int(conflict);c['sack_pressure_conflicts']+=int(contradiction)
        basis.append(dict(game_id=gid,play_id=play,offense=off,defense=defense,eligible_nonspike_dropback=eligible,
            source_participation_present=s is not None,source_join_conflict=conflict,original_native_pressure=original_pressure,native_pressure=pressure,source_sack=sack,pressure_sack_conflict=contradiction,
            native_man_zone=text,classified_category=category,explicit_source_unclassified=explicit_unclassified))
    rows=[];grouped=defaultdict(list)
    for (gid,team),counter in sorted(totals.items()):
        row=dict(game_id=gid,team=team,**_finish(counter));rows.append(row);grouped[team].append(row)
    profiles=[dict(season=season,team=team,observed_games=[r['game_id']for r in games],**_finish({k:sum(r[k]for r in games)for k in _counter()}))for team,games in sorted(grouped.items())]
    core=dict(version=VERSION,before_period=before_period,season=season,definitions=dict(eligible_dropback='Official pass OR sack OR official rush&scramble, once; nonspike, non2PT, nonnullified native physical play',
        man_zone='Direct native publisher man/zone category, divided by classified eligible dropbacks; mixed/other/unclassified separate, not complements',
        pressure='Native provider was_pressure bool only; no transplanted vendor HHS taxonomy and no summing defender votes'),source_category_mapping=CATEGORIES,
        team_game_rows=rows,team_season_rows=profiles,event_basis=sorted(basis,key=lambda r:(r['game_id'],int(r['play_id']))))
    return dict(**core,semantic_sha256=digest(core),provenance=dict(participation_semantic_sha256=participation['semantic_sha256'],participation_source=deepcopy(participation.get('provenance'))),
        evidence_use='historical_postseason_revised_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None,
        limitations=['Historical postseason source never current2026 fallback or original contemporaneous input proof','Missing eligible PBP joins/flags/source values remain unknown; all opposing passers retained at native team grain','Pressure provider taxonomy gap remains separate from man/zone classification evidence','No rate inferred from COVER_x strings, no forced man-plus-zone complement, no model or matchup probability'])
