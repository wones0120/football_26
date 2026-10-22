"""Provider HHS pressure counts on a separately declared physical dropback basis.

Rounded provider percentages are compatibility checks, never denominators.
"""
from collections import defaultdict
from copy import deepcopy
import re
from .contact_cohort_reconciliation import _number,resolve_contact_identity
from .fumble_event_components import _flag,_eligibility
from .market_snapshots import canonical_team
from .participation_source_components import _int
from .evaluation_record import digest

VERSION='pfr_pressure_cohort_v1'
PCT_ROUNDING_TOLERANCE=0.0005000001


def nonspike_dropback(raw):
    live,basis=_eligibility(raw)
    if live is False:return False,basis
    passing,rush,sack,scramble,spike=(_flag(raw.get(k))for k in ('pass_attempt','rush_attempt','sack','qb_scramble','qb_spike'))
    if passing is False and sack is False and scramble is False and _flag(raw.get('qb_dropback'))is not True:return False,'known_non_dropback'
    if live is not True:return None,basis
    if spike is True:
        return (False,'known_spike')if passing is True and rush is False and sack is False and scramble is False else(None,'contradictory_spike')
    if spike is not False:return None,'unknown_spike'
    valid=(passing is True and rush is False and sack is False and scramble is False)or(sack is True and passing in (True,False) and rush is False and scramble is False)or(scramble is True and rush is True and passing is False and sack is False)
    if not valid:return None,'unknown_or_conflicting_physical_union'
    if scramble is True and raw.get('passer_player_id')and raw.get('rusher_player_id')and raw['passer_player_id']!=raw['rusher_player_id']:return None,'contradictory_scrambler_identity'
    return True,'official_nonspike_pass_or_sack_or_official_scramble_once'


def build_pressure_dropbacks(records,*,before_period):
    if type(before_period)is not int or not 1<=before_period%100<=18:raise ValueError('Explicit prior REG boundary required')
    groups={};seen=set();events=[]
    for raw in records:
        if raw.get('season_type')!='REG':continue
        season=_int(raw['season']);week=_int(raw['week']);gid=raw['game_id'];parts=gid.split('_');play=str(_int(raw['play_id']))
        if len(parts)!=4 or parts[:2]!=[str(season),f'{week:02d}']or not 1<=week<=18:raise ValueError('Native game/period required')
        if season*100+week>=before_period:continue
        if (gid,play)in seen:raise ValueError('Duplicate native play')
        seen.add((gid,play));pair={canonical_team(t)for t in parts[2:]}
        if len(pair)!=2:raise ValueError('Two native sides required')
        for team in pair:groups.setdefault((gid,team),dict(game_id=gid,season=season,week=week,offense=team,defense=next(t for t in pair if t!=team),source_offense_rows=0,known_dropbacks=0,known_sacks=0,unknown_dropback_events=0,unattributed_dropbacks=0,actors={}))
        off=canonical_team(raw['posteam'])if raw.get('posteam')else None;defense=canonical_team(raw['defteam'])if raw.get('defteam')else None
        if any(t is not None and t not in pair for t in(off,defense))or off is not None and off==defense:raise ValueError('Native sides contradict game')
        if off is not None and defense is not None:groups[(gid,off)]['source_offense_rows']+=1
        eligible,basis=nonspike_dropback(raw)
        if eligible is False:continue
        scramble=_flag(raw.get('qb_scramble'));native=raw.get('rusher_player_id')if scramble is True else raw.get('passer_player_id');valid=isinstance(native,str)and re.fullmatch(r'00-\d{7}',native)is not None
        sack=_flag(raw.get('sack'));events.append(dict(game_id=gid,play_id=play,offense=off,defense=defense,eligible=eligible,eligibility_basis=basis,native_passer=native,native_passer_valid=valid,sack=sack))
        for team in {off}if off is not None and defense is not None else pair:
            g=groups[(gid,team)]
            if eligible is None or off is None or defense is None:g['unknown_dropback_events']+=1;continue
            g['known_dropbacks']+=1;g['known_sacks']+=int(sack is True)
            if not valid:g['unattributed_dropbacks']+=1;continue
            a=g['actors'].setdefault(native,dict(native_GSIS=native,dropbacks=0,sacks=0));a['dropbacks']+=1;a['sacks']+=int(sack is True)
    return dict(version=VERSION,before_period=before_period,game_rows=[g for _,g in sorted(groups.items())],event_basis=events)


def _count(value):
    n=_number(value)
    return int(n)if n is not None and n>=0 and n.is_integer()else None


def reconcile_pressure_cohorts(cohort,pfr_rows,GSIS_proofs,PFR_proofs):
    if cohort.get('version')!=VERSION:raise ValueError('Exact dropback contract required')
    for system,proofs in (('nflreadpy',GSIS_proofs),('pfr',PFR_proofs)):
        if not proofs:continue
        cutoffs={p.get('actual_alias_cutoff_at')for p in proofs.values()}
        if len(cutoffs)!=1:raise ValueError('One actual native alias cutoff required')
        aliases=[]
        for native,p in proofs.items():
            if p.get('source_key')!=native or p.get('source_system')!=system:raise ValueError('Native identity scope differs')
            aliases.extend(deepcopy(p.get('original_alias_evidence',[])))
        expected_proofs,_=resolve_contact_identity(set(proofs),aliases,source_system=system,cutoff=next(iter(cutoffs)))
        if any((p.get('player_master_id'),p.get('status'))!=(expected_proofs[n]['player_master_id'],expected_proofs[n]['status'])for n,p in proofs.items()):raise ValueError('Native identity candidate-edge proof differs')
    bygame=defaultdict(list);seen=set();expected={(g['game_id'],g['offense'])for g in cohort['game_rows']};rows=[]
    for r in pfr_rows:
        key=(r['game_id'],r['team']);native=r['pfr_player_id']
        if (*key,native)in seen or key not in expected:raise ValueError('Native PFR actor/game cardinality differs')
        seen.add((*key,native));bygame[key].append(r)
    for g in cohort['game_rows']:
        source=bygame[(g['game_id'],g['offense'])];issues=[];pbp={};pfr={};links=[];known_pressure=0
        if not g['source_offense_rows']:issues.append('missing_opposing_offense_source_log')
        if g['unknown_dropback_events']or g['unattributed_dropbacks']:issues.append('unknown_or_unattributed_dropback_cohort')
        for native,a in g['actors'].items():
            pid=GSIS_proofs.get(native,{}).get('player_master_id')
            if pid is None:issues.append('unresolved_or_conflicted_GSIS')
            elif pid in pbp:raise ValueError('Conflicting GSIS canonical actor')
            else:pbp[pid]=a
        for r in source:
            native=r['pfr_player_id'];pid=PFR_proofs.get(native,{}).get('player_master_id');fields={k:_count(r.get(k))for k in ('times_hurried','times_hit','times_sacked','times_pressured')}
            if fields['times_pressured']is not None:known_pressure+=fields['times_pressured']
            if any(v is None for v in fields.values()):issues.append('unknown_PFR_HHS_component')
            elif fields['times_hurried']+fields['times_hit']+fields['times_sacked']!=fields['times_pressured']:issues.append('PFR_HHS_partition_conflict')
            if pid is None:issues.append('unresolved_or_conflicted_PFR')
            elif pid in pfr:raise ValueError('Conflicting PFR canonical actor')
            else:pfr[pid]=(r,fields)
        if set(pbp)!=set(pfr):issues.append('missing_or_extra_native_passer')
        for pid in sorted(set(pbp)&set(pfr)):
            a=pbp[pid];r,f=pfr[pid];pressure=f['times_pressured'];pct=_number(r.get('times_pressured_pct'));den=a['dropbacks']
            sacks_match=f['times_sacked']==a['sacks'];bounds=pressure is not None and 0<=pressure<=den
            pct_match=pct is not None and 0<=pct<=1 and den>0 and pressure is not None and abs(pct-pressure/den)<=PCT_ROUNDING_TOLERANCE
            if not sacks_match:issues.append('per_passer_sack_count_conflict')
            if not bounds:issues.append('pressure_outside_declared_dropback_bounds')
            if not pct_match:issues.append('published_fraction_vs_declared_exposure_semantic_gap')
            links.append(dict(native_GSIS=a['native_GSIS'],native_PFR=r['pfr_player_id'],player_master_id=pid,dropbacks=den,PBP_sacks=a['sacks'],PFR_HHS=f,published_fraction=pct,sacks_match=sacks_match,pressure_bounds=bounds,rounded_fraction_compatible=pct_match))
        rate=known_pressure/g['known_dropbacks']if not issues and g['known_dropbacks']else None
        rows.append(dict(game_id=g['game_id'],season=g['season'],week=g['week'],offense=g['offense'],defense=g['defense'],source_offense_rows=g['source_offense_rows'],known_dropbacks=g['known_dropbacks'],known_pressure_lower_bound=known_pressure,full_observed_cohort_proven=not issues,unknown_or_incompatible_reasons=sorted(set(issues)),matched_native_passers=links,pressure_rate=rate))
    core=dict(version=VERSION,game_rows=rows,definition='Native PFR passer HHS pressures / compatible all-passer official nonspike physical dropbacks, one exposure per play',catalog_ids=['G13-M03','G14-M01'],native_GSIS_identity_proofs=deepcopy(GSIS_proofs),native_PFR_identity_proofs=deepcopy(PFR_proofs),evidence_use='historical_revised_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None)
    return dict(**core,semantic_sha256=digest(core))
