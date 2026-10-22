"""Observed TE on-field attempt/target response by reported coverage and personnel."""
from collections import Counter,defaultdict
from copy import deepcopy
import math,re
from uuid import UUID
from .participation_position_components import VERSION as POSITION_VERSION,UNKNOWN_POSITIONS
from .coverage_receiver_performance import VERSION as TARGET_VERSION
from .participation_defense_catalog import CATEGORIES
from .defensive_front_rush_exposure import ROLE_FAMILIES
from .evaluation_record import digest

VERSION='te_coverage_package_v1'
COVERS=('man','zone');PACKAGES=('DB_count_le5','DB_count_ge6')
FAMILIES={**ROLE_FAMILIES,'DB':'DB','DL':'DL'}


def _cell():return dict(known_onfield_attempts=0,unknown_onfield_attempts=0,known_TE_targets=0,unknown_TE_targets=0,completions=0,unknown_completions=0,known_EPA_sum=0.,unknown_EPA=0)


def _finish(c):
    n=c['known_onfield_attempts'];t=c['known_TE_targets'];u=c['unknown_onfield_attempts'];ut=c['unknown_TE_targets']
    return dict(**c,exact_onfield_attempts=n if not u else None,exact_TE_targets=t if not(u or ut)else None,target_rate=t/n if n and not(u or ut)else None,completion_rate=c['completions']/t if t and not(u or ut or c['unknown_completions'])else None,provider_EPA_per_TE_target=c['known_EPA_sum']/t if t and not(u or ut or c['unknown_EPA'])else None,known_sample_target_rate=t/(n-ut)if n>ut else None,known_sample_completion_rate=c['completions']/(t-c['unknown_completions'])if t>c['unknown_completions']else None,known_sample_EPA_per_target=c['known_EPA_sum']/(t-c['unknown_EPA'])if t>c['unknown_EPA']else None)


def _package(p):
    scope=p['participant_scopes']['defense']
    if not scope['exact_eleven_positions_proven']or scope['status']!='aligned_native_position_list':return None,None
    mapping=scope['position_by_native_id'];ids=scope['native_player_ids']
    if not isinstance(mapping,dict)or not isinstance(ids,list)or len(ids)!=11 or len(set(ids))!=11 or set(ids)!=set(mapping):return None,None
    counts=Counter(FAMILIES.get(v,'OTHER')for v in mapping.values());tuple_={k:counts[k]for k in('DL','LB','DB','OTHER')}
    if counts['OTHER']:return None,tuple_
    return 'DB_count_ge6'if counts['DB']>=6 else'DB_count_le5',tuple_


def _presence(p,native,conflict):
    scope=p['participant_scopes']['offense'];mapping=scope['position_by_native_id']
    if scope['status']!='aligned_native_position_list'or not scope['exact_eleven_native_proven']or mapping is None:return None
    ids=scope['native_player_ids']
    if not isinstance(ids,list)or len(ids)!=11 or len(set(ids))!=11 or set(ids)!=set(mapping):return None
    if conflict:return None
    role=mapping.get(native)
    if role is None:return False
    if role in UNKNOWN_POSITIONS:return None
    return role=='TE'


def _qualified_global_identities(identities):
    edges={n:{a['player_master_id']for a in p.get('original_alias_evidence',[])}|({p['player_master_id']}if p.get('player_master_id')is not None else set())for n,p in identities.items()}
    reverse=defaultdict(set)
    for native,values in edges.items():
        if not isinstance(native,str)or not re.fullmatch(r'00-\d{7}',native)or any(str(UUID(str(pid)))!=pid for pid in values):raise ValueError('Native GSIS and canonical UUID spelling required')
        for pid in values:reverse[pid].add(native)
    conflict={n for natives in reverse.values()if len(natives)>1 for n in natives}|{n for n,v in edges.items()if len(v)>1}
    qualified={n:p['player_master_id']if p['status']=='unique_native_alias'and p.get('player_master_id')is not None and edges[n]=={p['player_master_id']}and n not in conflict else None for n,p in identities.items()}
    novel=[n for n,p in identities.items()if p['status']=='unique_native_alias'and qualified[n]is None]
    return qualified,sorted(conflict),sorted(novel)


def build_te_coverage_package(positions,targets,identities):
    if positions.get('version')!=POSITION_VERSION or targets.get('version')!=TARGET_VERSION or positions.get('pregame_serving_eligible')is not False or targets.get('pregame_serving_eligible')is not False or positions['season']!=targets['season']:raise ValueError('Matched reviewed nonserving native parents required')
    if not set(targets.get('native_identity_universe',[]))<=set(identities):raise ValueError('Complete frozen global identity universe required')
    qualified_ids,global_conflicts,novel_identity_conflicts=_qualified_global_identities(identities)
    source={}
    for p in positions['rows']:
        key=(p['game_id'],str(p['play_id']))
        if key in source:raise ValueError('Unique native position row required')
        source[key]=p
    expected={g['game_id']:g for g in targets['expected_games']};events=defaultdict(list);seen=set();basis=[];unassigned=[]
    for e in targets['event_basis']:
        key=(e['game_id'],str(e['play_id']))
        if key in seen:raise ValueError('Unique native target event required')
        seen.add(key)
        if any(e[k]is not None and type(e[k])is not bool for k in('eligible_target_attempt','complete_pass')):raise ValueError('Tri-state native target/completion flags required')
        if e['target_play_EPA']is not None and(type(e['target_play_EPA'])is bool or not isinstance(e['target_play_EPA'],(int,float))or not math.isfinite(e['target_play_EPA'])):raise ValueError('Finite native provider EPA required')
        if e['game_id']not in expected:raise ValueError('Native target game absent from schedule')
        p=source.get(key);off=e['offense'];defense=e['defense'];valid=bool(p and off is not None and defense is not None and off!=defense and {off,defense}==set(expected[e['game_id']]['sides'])and p['possession_team']==off and p['native_phase']in(None,'REG'))
        cover=CATEGORIES.get(p['measurements']['defense_man_zone_type'])if valid else None
        package,tuple_=_package(p)if valid else(None,None)
        item={**deepcopy(e),'position_source_proven':valid,'reported_coverage':cover,'reported_personnel_package':package,'reported_personnel_tuple':tuple_,'raw_coverage_labels':deepcopy(p['measurements'])if p else None,'position_source_row_ordinal':p['source_row_ordinal']if p else None};basis.append(item);events[e['game_id']].append((item,p))
        if not valid or cover is None or package is None or e['eligible_target_attempt']is None or e['attributed_receiver_id']is None:unassigned.append(dict(game_id=e['game_id'],play_id=e['play_id'],offense=off,reported_native_receiver=e['native_receiver_id'],unknown_other_TE_candidates=True,reason='Unknown TE/condition/recipient membership retained; source roles do not bound all missing native actors'))
    cohort={(r['game_id'],r['team'],r['source_player_id'])for r in targets['game_rows']if'TE'in r['source_roles']};rows=[]
    if not {n for g,t,n in cohort}<=set(identities):raise ValueError('Complete frozen native TE identity receipts required')
    for gid,team,native in sorted(cohort):
        if gid not in expected or team not in expected[gid]['sides']:raise ValueError('Native TE game/team scope differs')
        cells={(c,p):_cell()for c in COVERS for p in PACKAGES};owned=0;excluded=0
        for e,p in events[gid]:
            if e['offense']is not None and e['offense']!=team:continue
            if e['offense']==team:owned+=1
            eligible=e['eligible_target_attempt']
            if eligible is False:continue
            cover=e['reported_coverage'];package=e['reported_personnel_package']
            if cover in('mixed','other'):excluded+=1;continue
            presence=_presence(p,native,e['attribution_conflict'])if e['position_source_proven']else None
            if presence is False:continue
            conditions=[(c,k)for c in COVERS for k in PACKAGES if(cover is None or cover==c)and(package is None or package==k)]
            for key in conditions:
                c=cells[key]
                if presence is not True or eligible is not True or cover is None or package is None:
                    c['unknown_onfield_attempts']+=1;continue
                c['known_onfield_attempts']+=1;recipient=e['attributed_receiver_id']
                if recipient is None:c['unknown_TE_targets']+=1;continue
                if recipient!=native:continue
                c['known_TE_targets']+=1
                if e['complete_pass']is None:c['unknown_completions']+=1
                else:c['completions']+=int(e['complete_pass'])
                if e['target_play_EPA']is None:c['unknown_EPA']+=1
                else:c['known_EPA_sum']+=e['target_play_EPA']
        if not owned:
            for c in cells.values():c['unknown_onfield_attempts']+=1
        finished={cover:{pack:_finish(cells[(cover,pack)])for pack in PACKAGES}for cover in COVERS};proof=identities[native];qualified=qualified_ids[native]is not None;contrasts={}
        for cover in COVERS:
            high=finished[cover]['DB_count_ge6'];low=finished[cover]['DB_count_le5'];contrasts[cover]={field:high[field]-low[field]if high[field]is not None and low[field]is not None and qualified else None for field in('target_rate','completion_rate','provider_EPA_per_TE_target')}
        rows.append(dict(game_id=gid,season=targets['season'],week=expected[gid]['week'],team=team,native_GSIS=native,player_master_id=qualified_ids[native],canonical_qualified=qualified,identity_status='unique_native_alias'if qualified else'canonical_native_conflict'if native in global_conflicts else proof['status'],inherited_identity_status=proof['status'],source_owned_attempt_rows=owned,reported_mixed_other_excluded=excluded,cells=finished,DB_ge6_minus_le5=contrasts))
    core=dict(version=VERSION,catalog_id='G16-M03',season=targets['season'],before_period=targets['before_period'],actor_game_rows=rows,event_basis=basis,unassigned_TE_candidate_residual=unassigned,global_identity_scope=dict(native_keys=len(identities),conflicted_native_keys=global_conflicts,novel_conflicts_requiring_UI_incident=novel_identity_conflicts),source_semantic_sha256=dict(positions=positions['semantic_sha256'],native_target_events=targets['semantic_sha256']),definitions=dict(scope='Observed sourceTEonfield officialnonspike attempt/target/completion/providerEPA conditional on directreportedMANZONE AND native defensive personnel package',package='Exact11known native defensive positions; fixed DL/LB/DBfamily tuple, OLB remainsLB; DB>=6versus<=5, unsupportedposition residual unknown',exposure='One matched officialnonspike attempt for each source-proven TEonfield; multipleTEplayer-exposures are not additional physical team attempts',TE_role='Same-play source TE position+exact11 native offense membership, never inferred from name/volume/route; roster/list contradiction unknown',condition='MAN andZONE separate; reported MIXED/OTHER explicitly excluded; unclassified/missing coverage remains unknown, no complement or family-to-MAN inference',interpretation='Reported onfield personnel composition, not actual covering actor/slot/safetydepth/blocking/route/forecast/causality',comparator='Within same TEgame/reportedcoverage, DB_count_ge6 minusDB_count_le5 with exactmatched denominators and unknowns'),pregame_serving_eligible=False,forecast=None)
    return dict(**core,semantic_sha256=digest(core))
