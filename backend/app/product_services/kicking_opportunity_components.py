"""Official source-flagged kicker opportunities and distance outcomes."""
from copy import deepcopy
from pathlib import Path
from uuid import UUID
import hashlib,re
from .opportunity_events import validate_event_evidence,_flag
from .defense_context_evidence import _number,_hash
from .environment_context_evidence import _and
VERSION='kicking_opportunity_components_v1'
DEFINITIONS={
 'G23-M01':'Official field_goal_attempt count; no_play and two_point_attempt excluded',
 'G23-M02':'Official FG attempt distance distribution in yards:0–19/20–29/30–39/40–49/50–59/60+ and unknown distance; full attempt denominator retained',
 'G23-M03':'Official FG made / all official FG attempts per distance bucket; blocked and missed are known failures, unknown result remains unknown',
 'G23-M04':'Official extra_point_attempt count; two-point attempts excluded'}
NATIVE_CLASS_CONTRACT=dict(id='nflverse_exclusive_native_kick_classes_v1',dictionary='https://nflfastr.com/reference/fast_scraper.html',producer='https://github.com/nflverse/nflfastR/blob/master/R/helper_add_nflscrapr_mutations.R',meaning='Only absent no_play key may use agreeing field_goal/FIELD_GOAL or extra_point/XP_KICK source classes; explicit null remains unknown')
BUCKETS=('0-19','20-29','30-39','40-49','50-59','60+','unknown')
def _counter():return dict(attempts=0,unknown_eligibility=0,unattributed_attempts=0,known_made=0,known_failed=0,unknown_result=0)
def _add(c,eligible,result,native=True):
 if eligible is None:c['unknown_eligibility']+=1
 elif eligible:
  c['attempts']+=1
  if not native:c['unattributed_attempts']+=1
  if result=='made':c['known_made']+=1
  elif result in {'missed','blocked'}:c['known_failed']+=1
  else:c['unknown_result']+=1
def _finish(c,*,inherited=0):
 return dict(**c,inherited_possible_native_actor_exposures=inherited,exact_attempts=None if c['unknown_eligibility'] or inherited else c['attempts'],known_result_accuracy=c['known_made']/(c['known_made']+c['known_failed']) if c['known_made']+c['known_failed'] else None,exact_within_log_accuracy=c['known_made']/c['attempts'] if c['attempts'] and not(c['unknown_result'] or c['unknown_eligibility'] or inherited) else None)
def _bucket(value):
 n=_number(value)
 if n is None:return 'unknown'
 if n<0 or n>120 or n!=int(n):raise ValueError('Invalid physical source kick distance')
 if n<20:return '0-19'
 if n<60:return f'{int(n)//10*10}-{int(n)//10*10+9}'
 return '60+'
def build_kicking_components(event_receipt,*,before_period,cutoff,canonical_ids=None):
 evidence=validate_event_evidence(event_receipt['event_evidence'],before_period=before_period,cutoff=cutoff);ids=canonical_ids or {};actors={};teams={};basis=[];requests=[];canonical_native={}
 def start():return dict(FG=_counter(),XP=_counter(),distances={b:_counter() for b in BUCKETS})
 for event in sorted(evidence['events'],key=lambda e:(e['game_id'],int(e['play_id']))):
  raw=event['raw_flags'];fg=_flag(raw.get('field_goal_attempt'));xp=_flag(raw.get('extra_point_attempt'))
  # A known other native play type independently proves non-kicking eligibility.
  kind=raw.get('play_type')
  if fg is None and kind not in (None,'field_goal'):fg=False
  if xp is None and kind not in (None,'extra_point'):xp=False
  no_play=_flag(raw.get('no_play'));two=_flag(raw.get('two_point_attempt'));derived_no_play=no_play
  nullification_basis='explicit_no_play_field' if 'no_play' in raw else 'unknown_absent_no_play_field'
  known_source=evidence['source'].get('source_uri')==f'nflreadpy://pbp/{event["season"]}' and evidence['source'].get('verification')=='snapshot_artifact_sha256_verified'
  if 'no_play' not in raw and known_source and (kind,raw.get('play_type_nfl')) in {('field_goal','FIELD_GOAL'),('extra_point','XP_KICK')}:
   derived_no_play=False;nullification_basis='verified_source_exclusive_native_kick_classes'
  if kind=='no_play' or derived_no_play is True or two is True:fg=False;xp=False
  elif two is None and (fg is not False or xp is not False):
   # Explicit kick types plus attempt flags prove this is not a two-point play.
   if kind not in {'field_goal','extra_point'}:fg=_and(fg,None);xp=_and(xp,None)
  if derived_no_play is None:fg=_and(fg,None);xp=_and(xp,None)
  if fg is True and xp is True:raise ValueError('Same physical play cannot be FG and XP attempt')
  if fg is False and xp is False:continue
  native=raw.get('kicker_player_id')
  if native is not None and (not isinstance(native,str) or not re.fullmatch(r'00-\d{7}',native)):raise ValueError('Kicker native GSIS required; no display-name join')
  pid=ids.get(native)
  if pid is not None and str(UUID(str(pid)))!=pid:raise ValueError('Kicker canonical UUID spelling invalid')
  key=(event['game_id'],event['team']);team=teams.setdefault(key,start());actor=None
  if pid is not None:
   ckey=(key[0],pid)
   if ckey in canonical_native and canonical_native[ckey]!=(key[1],native):raise ValueError('Canonical kicker has contradictory native/team scope')
   canonical_native[ckey]=(key[1],native)
  if native:
   akey=(*key,native);actor=actors.setdefault(akey,dict(game_id=key[0],team=key[1],source_player_id=native,player_master_id=pid,source_role='native_kicker_on_flagged_kick_not_permanent_position',measurements=start()))['measurements']
  distance=_bucket(raw.get('kick_distance')) if fg is not False else 'unknown'
  for channel,eligible,result in [('FG',fg,raw.get('field_goal_result')),('XP',xp,{'good':'made','failed':'missed'}.get(raw.get('extra_point_result'),raw.get('extra_point_result')))]:
   _add(team[channel],eligible,result,native)
   if actor:_add(actor[channel],eligible,result)
  if fg is True or fg is None:
   _add(team['distances'][distance],fg,raw.get('field_goal_result'),native)
   if actor:_add(actor['distances'][distance],fg,raw.get('field_goal_result'))
  basis.append(dict(game_id=key[0],team=key[1],play_id=event['play_id'],source_player_id=native,no_play=no_play,no_play_key_present='no_play' in raw,derived_no_play=derived_no_play,nullification_basis=nullification_basis,two_point_attempt=two,FG=fg,XP=xp,distance=distance,FG_result=raw.get('field_goal_result'),XP_result=raw.get('extra_point_result')))
 rows=[]
 for key,a in sorted(actors.items()):
  counters=a.pop('measurements');team=teams[key[:2]];fg_unknown=team['FG']['unknown_eligibility']+team['FG']['unattributed_attempts'];xp_unknown=team['XP']['unknown_eligibility']+team['XP']['unattributed_attempts'];fg=_finish(counters['FG'],inherited=fg_unknown)
  buckets={b:_finish(counters['distances'][b],inherited=fg_unknown) for b in BUCKETS}
  # Missing distance could belong to any known bucket; do not report exact bucket rates.
  unknown_distance=counters['distances']['unknown']['attempts']
  for b in BUCKETS:
   if b!='unknown' and unknown_distance:
    buckets[b]['exact_attempts']=None;buckets[b]['exact_within_log_accuracy']=None
   buckets[b]['inherited_unknown_distance_attempts']=unknown_distance if b!='unknown' else 0
  metrics={'G23-M01':fg,'G23-M02':dict(full_attempt_denominator=fg,distance_buckets=buckets),'G23-M03':dict(distance_buckets=deepcopy(buckets),full_attempt_denominator=fg),'G23-M04':_finish(counters['XP'],inherited=xp_unknown)}
  rows.append(dict(**a,metrics=metrics))
  if a['player_master_id'] is None:requests.append(dict(game_id=a['game_id'],team=a['team'],source_player_id=a['source_player_id'],reason='Unresolved native kicker; persist through identity review, never name-join'))
 team_rows=[]
 for (g,t),c in sorted(teams.items()):
  buckets={b:_finish(c['distances'][b],inherited=c['FG']['unknown_eligibility']) for b in BUCKETS};missing=c['distances']['unknown']['attempts']
  for b in BUCKETS:
   if b!='unknown' and missing:buckets[b]['exact_attempts']=None;buckets[b]['exact_within_log_accuracy']=None
   buckets[b]['inherited_unknown_distance_attempts']=missing if b!='unknown' else 0
  team_rows.append(dict(game_id=g,team=t,FG=_finish(c['FG']),XP=_finish(c['XP']),distance_buckets=buckets))
 basis=dict(version=VERSION,before_period=before_period,definitions=DEFINITIONS,native_nullification_contract=NATIVE_CLASS_CONTRACT,actor_game_rows=rows,team_game_rows=team_rows,event_basis=basis,identity_review_requests=requests)
 return dict(**basis,semantic_sha256=_hash(basis),provenance=dict(source=deepcopy(evidence['source']),event_receipt_sha256=evidence['sha256'],actual_derived_at=str(cutoff),producer_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,limitations=['Observed official source log, not full-game completion proof','No expected kick accuracy or scoring projection inferred','Unknown outcome and distance retained; unknown kicker exposure masks exact actor counts','Historical original source publication availability unknown; no pregame/current registration'])

def derive_retrospective_kicking_components(parent_ref,snapshot,*,actual_read_at=None,canonical_ids=None,directory=None):
 from datetime import datetime,UTC
 from .factual_designation import clock
 from .opportunity_source_capture import load_event_artifact
 read_at=clock(actual_read_at or datetime.now(UTC));original=clock(parent_ref.get('decision_cutoff_at'));lock=clock(snapshot.slate_lock_at)
 if original is None or lock is None or not original<lock<=read_at<=datetime.now(UTC):raise ValueError('Original frozen boundary and actual postlock read required')
 parent=load_event_artifact(parent_ref,snapshot,before_period=parent_ref['before_period'],cutoff=original,directory=directory)
 value=build_kicking_components(parent,before_period=parent_ref['before_period'],cutoff=read_at,canonical_ids=canonical_ids)
 value['provenance']['retrospective_read']=dict(original_evidence_boundary_at=original.isoformat(),source_lock_at=lock.isoformat(),actual_read_at=read_at.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),parent_artifact_ref=deepcopy(parent_ref))
 return value

def require_feature_use(value,*,purpose):
 if purpose!='offline_descriptive':raise ValueError('Retrospective kicker measurements cannot be used as current/pregame serving evidence')
 if value.get('evidence_use')!='postlock_descriptive_not_pregame_or_serving':raise ValueError('Explicit nonserving boundary required')
 return value
