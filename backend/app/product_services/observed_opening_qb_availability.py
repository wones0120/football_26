"""Measured opening QB participation, separate from pregame availability/health."""
from copy import deepcopy
from collections import defaultdict
import re
from .center_sack_response import UNIT_VERSION,ROLES
from .personnel_package_continuity import globally_qualified_identity
from .turnover_drive_start_context import _order
from .original_drive_field_context import _integer
from .market_snapshots import canonical_team
from .evaluation_record import digest

VERSION='observed_opening_qb_availability_v1'
NATIVE=re.compile(r'00-\d{7}')


def build_observed_opening_qb_availability(components,games,identity_receipts,position_rows):
    source_positions={}
    for r in position_rows:
        play=_integer(r.get('play_id'));key=(r.get('game_id'),play)
        if play is None or key in source_positions:raise ValueError('Unique native first-snap position source keys required')
        source_positions[key]=r
    scopes={};units={};qualified,withheld=globally_qualified_identity(identity_receipts)
    for c in components:
        season=c['season']
        if c.get('version')!=UNIT_VERSION or c.get('pregame_serving_eligible')is not False or season in scopes:raise ValueError('Unique reviewed first-snap source season required')
        scopes[season]=c['before_period']
        for u in c['units']:
            key=(u['game_id'],u['team'])
            if key in units or u['season']!=season:raise ValueError('Unique same-season first-snap side required')
            units[key]=u
    rows=[];seen=set();unknown_identities=set();expected=set()
    for g in sorted(games,key=lambda r:r['game_id']):
        year,week=g['season'],g['week']
        if g['game_type']!='REG'or year not in scopes or year*100+week>=scopes[year]:continue
        gid=g['game_id'];parts=gid.split('_');home,away=canonical_team(g['home_team']),canonical_team(g['away_team'])
        if gid in seen or len(parts)!=4 or parts[:2]!=[str(year),f'{week:02d}']or home!=canonical_team(parts[3])or away!=canonical_team(parts[2])or home==away:raise ValueError('Unique native reported-starter schedule game required')
        seen.add(gid)
        for side,team in(('home',home),('away',away)):
            expected.add((gid,team));u=units.get((gid,team));proof=u['proof']if u else{};reasons=[]
            if u is None:reasons.append('missing_first_snap_source_side')
            elif (u['season'],u['week'],u['game_date'])!=(year,week,g['game_date']):raise ValueError('Native first-snap/schedule period/date differs')
            if proof.get('unique_quiet_native_GAME_START')is not True:reasons.append('complete_native_game_beginning_unproven')
            if proof.get('no_earlier_possible_offense')is not True or proof.get('earlier_possible_play_ids'):reasons.append('earlier_possible_offense_not_excluded')
            beginning,first=(_integer(proof.get(k))for k in('native_beginning_play_id','first_physical_play_id'))
            order=_order(proof.get('first_physical_native_order'))
            if beginning is None or first is None or beginning==first or order is None:reasons.append('positive_first_physical_snap_identity_order_unproven')
            pos=proof.get('original_first_snap_position_by_native_id')
            rolemap=bool(proof.get('eleven_unique_aligned_positions')is True and isinstance(pos,dict)and len(pos)==11 and all(isinstance(n,str)and NATIVE.fullmatch(n)and isinstance(p,str)and p in ROLES for n,p in pos.items()))
            if not rolemap:reasons.append('eleven_unique_known_native_position_roles_unproven')
            source=source_positions.get((gid,first));scope=source.get('participant_scopes',{}).get('offense',{})if source else{}
            source_bound=bool(source and (source.get('season'),source.get('week'),source.get('possession_team'))==(year,week,team)
                and source.get('native_phase')in(None,'REG')and scope.get('status')=='aligned_native_position_list'
                and scope.get('exact_eleven_native_proven')is True and scope.get('exact_eleven_positions_proven')is True
                and scope.get('position_by_native_id')==pos and rolemap)
            if not source_bound:reasons.append('same_native_first_snap_team_phase_and_position_source_unproven')
            candidates=sorted(n for n,p in pos.items()if p=='QB')if rolemap else[]
            native=candidates[0]if len(candidates)==1 else None
            if native is None:reasons.append('sole_source_position_QB_unproven')
            reported=g.get(side+'_qb_id');reported=reported if isinstance(reported,str)and NATIVE.fullmatch(reported)else None
            if reported is None:reasons.append('same_game_reported_starter_GSIS_unknown')
            elif native is not None and native!=reported:reasons.append('reported_starter_and_opening_native_QB_conflict')
            native_present=True if not reasons else None
            receipt=qualified.get(native,{})if native else{};pid=receipt.get('player_master_id')if receipt.get('status')=='unique_native_alias'else None
            if native_present and pid is None:unknown_identities.add(native)
            canonical_reasons=reasons+(['unique_frozen_global_QB_UUID_unproven']if native_present and pid is None else[])
            rows.append(dict(native_game_id=gid,team=team,season=year,week=week,game_date=g['game_date'],source_reported_starter_GSIS=reported,source_opening_QB_candidates=candidates,source_opening_QB_GSIS=native,
                canonical_opening_QB_id=pid if native_present else None,native_observed_opening_presence=native_present,observed_opening_available=True if native_present and pid is not None else None,
                opening_status='observed_present_at_opening'if native_present and pid is not None else'unknown',unknown_reasons=canonical_reasons,first_snap_proof=deepcopy(proof),participation_source_binding=deepcopy(source),participation_phase_basis='Same native first-snap REG PBP/schedule proof; source phase may be absent'if source_bound else None,
                positive_participation_meaning='Source QB-position player is in the source-proven first physical offensive eleven; reported starter native ID corroborates identity, not scheduled-name inference alone',
                pregame_confirmed_available=None,health_status=None,upcoming_starting_role_confirmed=None))
    if set(units)-expected:raise ValueError('First-snap source has unmatched scheduled native sides')
    grouped=defaultdict(list)
    for r in rows:grouped[(r['season'],r['team'])].append(r)
    profiles=[dict(season=s,team=t,scheduled_game_slots=len(rs),known_observed_opening_present=sum(r['observed_opening_available']is True for r in rs),unknown_opening_states=sum(r['observed_opening_available']is None for r in rs),availability_interpretation='Observed opening participation only; unknown is never unavailableFalse')for(s,t),rs in sorted(grouped.items())]
    core=dict(version=VERSION,candidate_ids=['G18-M01'],game_rows=rows,profiles=profiles,affected_identity_native_ids=sorted(unknown_identities),global_identity_withheld_native_ids=withheld,
        definition='Historical MEASURED-game canonical reported starting QB corroborated by complete native beginning/first physical snap/exact11 source positions/sole QB and actual opening participation; not pregame, health or future availability')
    return dict(**core,semantic_sha256=digest(core),model_consumed=False,optimizer_consumed=False,pregame_serving_eligible=False,evidence_use='observed_measured_game_opening_presence_not_pregame_or_future_availability')


def load_reviewed_first_snap_component(ref,*,cutoff):
    from pathlib import Path
    from datetime import datetime,UTC
    import json,hashlib
    from . import center_sack_response,offensive_line_participation,participation_source_components
    from .factual_designation import clock
    p=Path(ref['path']).resolve();actual=clock(cutoff)
    if p.parent!=Path('artifacts/center_sack_response').resolve()or p.name!=ref['sha256']+'.json'or not 0<ref['bytes']<=4*1024*1024:raise ValueError('Managed bounded reviewed first-snap component required')
    b=p.read_bytes()
    if len(b)!=ref['bytes']or hashlib.sha256(b).hexdigest()!=ref['sha256']:raise ValueError('First-snap bytes differ')
    x=json.loads(b);pr=x['provenance'];published=clock(pr.get('actual_publication_at'))
    if actual is None or actual>datetime.now(UTC)or published is None or published>actual:raise ValueError('First-snap publication unavailable')
    for key,module in(('producer_code_sha256',center_sack_response),('firstsnap_helper_sha256',offensive_line_participation),('source_adapter_sha256',participation_source_components)):
        if pr.get(key)!=hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest():raise ValueError('Reviewed first-snap measurement/helper producer differs')
    core={k:x[k]for k in('version','season','before_period','units','evidence_use','pregame_serving_eligible')}
    if x.get('version')!=UNIT_VERSION or x.get('pregame_serving_eligible')is not False or digest(core)!=x['semantic_sha256']:raise ValueError('First-snap semantic/scope contract differs')
    return x
