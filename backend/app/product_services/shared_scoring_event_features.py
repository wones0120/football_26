"""Observed QB/receiver shared TD events, not independent scoring opportunities."""
from collections import defaultdict
from copy import deepcopy
import re
from uuid import UUID
from .evaluation_record import digest
from .market_snapshots import canonical_team

VERSION='shared_scoring_event_features_v1'
DEFINITION='One physical official passing TD jointly credits its source-proven QB passer and actual native TD scorer; receiving TD is not a second physical TD'
_NATIVE=re.compile(r'00-\d{7}\Z')


def _native(value):
    if value in (None,''):return None
    if not isinstance(value,str)or not _NATIVE.fullmatch(value):raise ValueError('Native GSIS identity required; no names')
    return value


def _scope(gid,team,before_period):
    parts=gid.split('_')
    if len(parts)!=4 or not parts[0].isdigit()or not parts[1].isdigit()or not 1<=int(parts[1])<=18 or int(parts[0])*100+int(parts[1])>=before_period or team!=canonical_team(team)or team not in {canonical_team(t)for t in parts[2:]}:raise ValueError('Explicit prior native game/team required')


def build_shared_scoring_events(scoring,effectiveness,passer_rows,*,before_period):
    """Pure composition; caller authenticates source bytes and all managed inputs."""
    if type(before_period)is not int or not 200001<=before_period or not 1<=before_period%100<=18:raise ValueError('Explicit REG target period required')
    for block,version in ((scoring,'scoring_share_components_v1'),(effectiveness,'player_effectiveness_components_v1')):
        if block.get('version')!=version or block.get('before_period')!=before_period or block.get('evidence_use')!='postlock_descriptive_not_pregame_or_serving'or block.get('pregame_serving_eligible')is not False:raise ValueError('Matching reviewed retrospective components required')
    a=scoring['provenance'];b=effectiveness['provenance']
    for field in ('snapshot_id','content_sha256'):
        if not a['source'].get(field)or a['source'][field]!=b['source'].get(field):raise ValueError('Shared scoring source differs')
    if not a.get('event_receipt_sha256')or a['event_receipt_sha256']!=b.get('event_receipt_sha256'):raise ValueError('Frozen event scope differs')
    actors={};canonical={};positions={}
    for row in scoring['actor_game_rows']:
        gid,team,native=row['game_id'],row['team'],_native(row['source_player_id']);_scope(gid,team,before_period)
        key=(gid,team,native)
        if key in actors:raise ValueError('Duplicate native scoring actor')
        pid=row.get('player_master_id')
        if pid is not None:
            if str(UUID(pid))!=pid:raise ValueError('Canonical UUID spelling required')
            ck=(gid,pid)
            if ck in canonical and canonical[ck]!=key:raise ValueError('Canonical native scoring conflict')
            canonical[ck]=key
        actors[key]=pid
    for row in effectiveness['actor_game_rows']:
        key=(row['game_id'],row['team'],_native(row['source_player_id']));_scope(key[0],key[1],before_period)
        if key in positions:raise ValueError('Duplicate scoped position actor')
        if key not in actors or actors[key]!=row.get('player_master_id'):raise ValueError('Position/scoring canonical attachment differs')
        positions[key]=row['position']if row.get('position_status')=='scoped_source_proven'else None
    passers={}
    for row in passer_rows:
        gid,team=row['game_id'],row['team'];_scope(gid,team,before_period);play=str(row['play_id'])
        if not play.isdigit()or str(int(play))!=play:raise ValueError('Canonical native play key required')
        key=(gid,play)
        if key in passers:raise ValueError('Duplicate native passer play')
        passers[key]=dict(team=team,source_passer_id=_native(row.get('passer_player_id')))
    events=[];pairs=defaultdict(list);games={};seen=set();requests=[]
    for e in scoring['event_basis']:
        gid,team,play=e['game_id'],e['team'],str(e['play_id']);_scope(gid,team,before_period)
        key=(gid,play)
        if key in seen:raise ValueError('Duplicate scoring event key')
        seen.add(key)
        value=e['passing_and_receiving_same_TD']
        if value is not None and type(value)is not bool:raise ValueError('Explicit tri-state passing-TD predicate required')
        game=games.setdefault((gid,team),dict(game_id=gid,team=team,known_physical_passing_TDs=0,unknown_TD_events=0,known_nonQB_passing_TDs=0,unknown_QB_pair_membership=0,known_shared_QB_receiver_TDs=0))
        if value is False:continue
        p=passers.get(key)
        if p is None or p['team']!=team:raise ValueError('Every possible passing TD requires same-source native passer row')
        passer=p['source_passer_id'];scorer=_native(e.get('receiver'));initial=_native(e.get('original_receiver'))
        position=positions.get((gid,team,passer))if passer else None
        status='unknown'
        if value is None:game['unknown_TD_events']+=1
        else:
            game['known_physical_passing_TDs']+=1
            if position is not None and position!='QB':
                status='known_nonQB_passer';game['known_nonQB_passing_TDs']+=1
            elif position=='QB'and scorer is not None:
                status='known_shared_QB_receiver';game['known_shared_QB_receiver_TDs']+=1
                pairs[(gid,team,passer,scorer)].append(play)
        if status=='unknown':game['unknown_QB_pair_membership']+=1
        pid=actors.get((gid,team,passer));rid=actors.get((gid,team,scorer))
        if value is True and status!='known_nonQB_passer':
            for native,canonical_id,role in ((passer,pid,'passer'),(scorer,rid,'TD_scorer')):
                if native is not None and canonical_id is None:requests.append(dict(game_id=gid,team=team,source_player_id=native,role=role,reason='Frozen shared-scoring canonical attachment unavailable; no current alias substitution'))
        events.append(dict(game_id=gid,play_id=play,team=team,physical_passing_TD=value,source_passer_id=passer,source_TD_scorer_id=scorer,source_initial_receiver_id=initial,
            passer_player_master_id=pid,TD_scorer_player_master_id=rid,source_proven_passer_position=position,pair_status=status,
            same_actor_event=passer==scorer if passer and scorer else None,
            shared_QB_passing_and_receiver_TD_credit=1 if status=='known_shared_QB_receiver'else None,
            physical_team_TD_count=1 if value is True else None,
            lateral_TD_scorer_differs_from_initial_receiver=scorer!=initial if scorer and initial else None))
    rows=[]
    for (gid,team,passer,scorer),plays in sorted(pairs.items()):
        game=games[(gid,team)]
        rows.append(dict(game_id=gid,team=team,source_passer_id=passer,source_TD_scorer_id=scorer,
            passer_player_master_id=actors.get((gid,team,passer)),TD_scorer_player_master_id=actors.get((gid,team,scorer)),
            native_play_ids=sorted(plays,key=int),known_shared_physical_TDs=len(plays),unknown_pair_membership_events=game['unknown_QB_pair_membership'],
            exact_within_log_shared_TDs=None if game['unknown_QB_pair_membership']else len(plays)))
    for game in games.values():
        game['exact_within_log_physical_passing_TDs']=None if game['unknown_TD_events']else game['known_physical_passing_TDs']
        game['exact_within_log_shared_QB_receiver_TDs']=None if game['unknown_QB_pair_membership']else game['known_shared_QB_receiver_TDs']
        if game['known_shared_QB_receiver_TDs']+game['known_nonQB_passing_TDs']>game['known_physical_passing_TDs']:raise ValueError('Physical scoring conservation violated')
    basis=dict(version=VERSION,before_period=before_period,catalog_id='G24-M01',definition=DEFINITION,
        event_rows=sorted(events,key=lambda r:(r['game_id'],int(r['play_id']))),pair_game_rows=rows,team_game_rows=[r for _,r in sorted(games.items())],
        identity_review_requests=sorted({digest(r):r for r in requests}.values(),key=lambda r:(r['game_id'],r['team'],r['source_player_id'],r['role'])))
    return dict(**basis,semantic_sha256=digest(basis),evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None,
        provenance=dict(source=deepcopy(a['source']),event_receipt_sha256=a['event_receipt_sha256'],scoring_semantic_sha256=scoring['semantic_sha256'],effectiveness_semantic_sha256=effectiveness['semantic_measurements_sha256']),
        limitations=['Shared source TD is one physical event with two linked credits, not two independent team TDs','Only observed native QB/scorer pairs are represented; absent pair is not a proven zero','Unknown passing-TD status, passer, scorer or QB position masks possible pair totals','Full-game completeness and original historical availability unverified; no calibrated joint ceiling probability or fixed FP bonus','Caller must authenticate immutable source/component/proof lineage; marker alone is not authentication'])
