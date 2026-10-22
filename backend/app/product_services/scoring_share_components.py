"""Prior observed offensive TD shares and declared official-attempt TD rates."""
from copy import deepcopy
from pathlib import Path
import hashlib
from .opportunity_events import validate_event_evidence,_flag
from .player_opportunity_components import build_player_opportunity_components
from .environment_context_evidence import _and
from .market_snapshots import canonical_team
from .defense_context_evidence import _hash
VERSION='scoring_share_components_v1'
DEFINITIONS={
 'G12-M02':'Team rushing TD / all official team rush attempts including kneels; declared attempt-denominator variant, not share of all TDs',
 'G12-M03':'Team passing TD / all official team pass attempts including spikes; declared attempt-denominator variant; receiving TD is same physical passing TD, never added again',
 'G12-M04':'Player rushing TD / full-team rushing TD over identical native observed games, all rushers including QB/nonQB',
 'G12-M05':'Player receiving TD / full-team receiving TD over identical native observed games, all receivers'}
def _counter():return dict(known_count=0,unknown_events=0,unattributed_known_events=0,unattributed_unknown_events=0)
def _add(c,predicate,native=True):
 if predicate is None:
  c['unknown_events']+=1
  if not native:c['unattributed_unknown_events']+=1
 elif predicate:
  c['known_count']+=1
  if not native:c['unattributed_known_events']+=1
def _finish(c,*,inherited=0):return dict(**c,inherited_possible_actor_events=inherited,exact_within_log_count=None if c['unknown_events'] or inherited else c['known_count'])
def _ratio(n,d,*,inherited=0):
 n=_finish(n,inherited=inherited);d=_finish(d);a=n['exact_within_log_count'];b=d['exact_within_log_count']
 return dict(numerator=n,full_team_denominator=d,exact_within_log_value=a/b if a is not None and b is not None and b>0 else None)
def _sum(counters):return {k:sum(c[k] for c in counters) for k in ('known_count','unknown_events','unattributed_known_events','unattributed_unknown_events')}
def build_scoring_shares(event_receipt,*,before_period,cutoff,window_sizes=(3,8)):
 if not window_sizes or any(type(n)is not int or not 1<=n<=32 for n in window_sizes):raise ValueError('Observed-game window sizes invalid')
 evidence=validate_event_evidence(event_receipt['event_evidence'],before_period=before_period,cutoff=cutoff)
 base=build_player_opportunity_components(event_receipt,before_period=before_period,cutoff=cutoff)
 actors={(r['game_id'],r['team'],r['source_player_id']):dict(game_id=r['game_id'],team=r['team'],source_player_id=r['source_player_id'],player_master_id=r['player_master_id'],rushing_TD=_counter(),receiving_TD=_counter()) for r in base['actor_game_rows']};teams={};basis=[]
 for e in sorted(evidence['events'],key=lambda r:(r['game_id'],int(r['play_id']))):
  raw=e['raw_flags'];channels={x['channel'] for x in e['opportunities']};tm=teams.setdefault((e['game_id'],e['team']),{k:_counter() for k in ('rush_attempts','pass_attempts','rushing_TD','passing_TD')})
  rush=True if 'rush_attempts'in channels else None if 'rush_attempts'in e['unknown_channels'] else False
  passing=True if 'pass_attempts'in channels else None if 'pass_attempts'in e['unknown_channels'] else False
  rushTD=_and(rush,_flag(raw.get('rush_touchdown')));passTD=_and(passing,_flag(raw.get('pass_touchdown')))
  if rushTD is True and passTD is True:raise ValueError('Same offensive play cannot be both rushing and passing TD')
  original_rusher=raw.get('rusher_player_id');original_receiver=raw.get('receiver_player_id');scorer=raw.get('td_player_id')
  if (rushTD is True or passTD is True) and raw.get('td_team') not in (None,'') and canonical_team(str(raw['td_team']))!=e['team']:raise ValueError('Offensive TD team contradicts native scoring event')
  rusher=scorer if scorer is not None else original_rusher if _flag(raw.get('lateral_rush')) is False else None
  receiver=scorer if scorer is not None else original_receiver if _flag(raw.get('lateral_reception')) is False else None
  for native,predicate in ((rusher,rushTD),(receiver,passTD)):
   if native is not None and predicate is not False:
    key=(e['game_id'],e['team'],str(native))
    if key not in actors:actors[key]=dict(game_id=key[0],team=key[1],source_player_id=key[2],player_master_id=None,rushing_TD=_counter(),receiving_TD=_counter())
  _add(tm['rush_attempts'],rush);_add(tm['pass_attempts'],passing);_add(tm['rushing_TD'],rushTD,rusher);_add(tm['passing_TD'],passTD,receiver)
  for role,native,predicate in [('rushing_TD',rusher,rushTD),('receiving_TD',receiver,passTD)]:
   if native:
    actor=actors.get((e['game_id'],e['team'],str(native)))
    if actor:_add(actor[role],predicate)
  basis.append(dict(game_id=e['game_id'],play_id=e['play_id'],team=e['team'],rush=rush,official_pass=passing,rush_TD=rushTD,passing_and_receiving_same_TD=passTD,rusher=rusher,receiver=receiver,original_rusher=original_rusher,original_receiver=original_receiver,native_td_player_id=scorer,lateral_rush=_flag(raw.get('lateral_rush')),lateral_reception=_flag(raw.get('lateral_reception'))))
 def actor_row(a,tm,games):
  return {k:deepcopy(v) for k,v in a.items() if k not in {'rushing_TD','receiving_TD'}}|dict(observed_games=games,metrics={
   'G12-M04':_ratio(a['rushing_TD'],tm['rushing_TD'],inherited=tm['rushing_TD']['unattributed_known_events']+tm['rushing_TD']['unattributed_unknown_events']),
   'G12-M05':_ratio(a['receiving_TD'],tm['passing_TD'],inherited=tm['passing_TD']['unattributed_known_events']+tm['passing_TD']['unattributed_unknown_events'])})
 rows=[actor_row(a,teams[key[:2]],[a['game_id']]) for key,a in sorted(actors.items())]
 teamrows=[dict(game_id=g,team=t,counts=deepcopy(v),metrics={'G12-M02':_ratio(v['rushing_TD'],v['rush_attempts']),'G12-M03':_ratio(v['passing_TD'],v['pass_attempts'])}) for (g,t),v in sorted(teams.items())]
 grouped={}
 native_identity={}
 for key,a in sorted(actors.items()):
  native=(a['team'],a['source_player_id']);pid=a['player_master_id']
  if pid is not None and native in native_identity and native_identity[native]!=pid:raise ValueError('Native actor canonical identity changes across games')
  if pid is not None:native_identity[native]=pid
  group_identity=pid if pid is not None else 'native:'+a['source_player_id']
  grouped.setdefault((a['team'],group_identity),[]).append(a)
 windows=[]
 for (team,identity_key),observed in sorted(grouped.items()):
  observed.sort(key=lambda r:r['game_id'])
  for n in sorted(set(window_sizes)):
   chosen=observed[-n:];games=[r['game_id'] for r in chosen];canonical={r['player_master_id'] for r in chosen}
   if len(canonical)>1:raise ValueError('Native actor canonical identity changes across selected observed games')
   aggregate=dict(team=team,source_player_id=chosen[-1]['source_player_id'],source_player_ids=sorted({r['source_player_id'] for r in chosen}),player_master_id=chosen[-1]['player_master_id'],rushing_TD=_sum([r['rushing_TD'] for r in chosen]),receiving_TD=_sum([r['receiving_TD'] for r in chosen]))
   fullteam={k:_sum([teams[(g,team)][k] for g in games]) for k in ('rushing_TD','passing_TD')}
   windows.append(actor_row(aggregate,fullteam,games)|dict(requested_observed_games=n,observed_games_count=len(games),window_kind='last_actor_native_appearances_same_team_not_complete_games'))
 result=dict(version=VERSION,before_period=before_period,definitions=DEFINITIONS,actor_game_rows=rows,team_game_rows=teamrows,actor_windows=windows,identity_review_requests=[dict(game_id=a['game_id'],team=a['team'],source_player_id=a['source_player_id'],reason='Unresolved native scoring actor; retain through existing identity queue, never name join') for a in actors.values() if a['player_master_id'] is None],event_basis=basis,source_quality=deepcopy(base['source_quality']))
 result['semantic_sha256']=_hash(result);result['provenance']=dict(source=deepcopy(evidence['source']),event_receipt_sha256=evidence['sha256'],actual_derived_at=str(cutoff),producer_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest());result.update(evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,limitations=['Observed source log only; full-game completion and original pregame availability unknown','Window denominator uses exactly the selected actor games; no absent-player zero-fill or cross-team transfer','Passing TD and receiving TD are one physical team scoring event','G12-M02/M03 are explicitly attempt-denominator variants; not a fitted TD probability','No end-zone target, expected scoring opportunity or drive-conversion proxy'])
 return result

def derive_retrospective_scoring_shares(parent_ref,snapshot,*,actual_read_at=None,directory=None):
 from datetime import datetime,UTC
 from .factual_designation import clock
 from .opportunity_source_capture import load_event_artifact
 read_at=clock(actual_read_at or datetime.now(UTC));original=clock(parent_ref.get('decision_cutoff_at'));lock=clock(snapshot.slate_lock_at)
 if original is None or lock is None or not original<lock<=read_at<=datetime.now(UTC):raise ValueError('Original prelock validation boundary and actual postlock read required')
 parent=load_event_artifact(parent_ref,snapshot,before_period=parent_ref['before_period'],cutoff=original,directory=directory)
 value=build_scoring_shares(parent,before_period=parent_ref['before_period'],cutoff=read_at)
 value['provenance']['retrospective_read']=dict(original_evidence_boundary_at=original.isoformat(),source_lock_at=lock.isoformat(),actual_read_at=read_at.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),parent_artifact_ref=deepcopy(parent_ref))
 return value

def require_feature_use(value,*,purpose):
 if purpose!='offline_descriptive':raise ValueError('Postlock scoring-share measurements cannot be used as current/pregame serving evidence')
 if value.get('pregame_serving_eligible') is not False:raise ValueError('Explicit nonserving use required')
 return value
