"""Native-play FTN charting features with full-source PBP denominators."""
from copy import deepcopy
from pathlib import Path
import hashlib
from .opportunity_events import validate_event_evidence,_flag
from .player_opportunity_components import build_player_opportunity_components
from .official_workload_components import _or
from .environment_context_evidence import _and
from .defense_context_extensions import _positions
from .defense_context_evidence import _hash
from .factual_designation import clock
from .market_snapshots import canonical_team
VERSION='charted_football_features_v1'
DEFINITIONS={
 'G03-M05':'Source-charted throwaways on official-inclusive physical QB dropbacks; count',
 'G03-M09':'Source-charted play-action dropbacks / official-inclusive physical QB dropbacks',
 'G08-M06':'Player first-read targets / all first-read full-team targets; FTN primary code0 defined only2023+',
 'G08-M10':'Player source-charted catchable targets / all official attributed player targets',
 'G09-M09':'Player source-charted drops / source-charted catchable player targets; contradictory drop/catchable flags unknown',
 'G10-M06':'Player source-charted screen targets / all official attributed player targets',
 'G10-M10':'Player source-charted contested targets / all official attributed player targets',
 'G14-M02':'Opponent dropbacks with FTN n_blitzers>0 / official-inclusive physical opponent dropbacks; not pressure or five-rusher inference'}

def _counter():return dict(eligible=0,known=0,unknown=0,unknown_eligibility=0,sum=0.,unattributed=0)
def _add(c,eligible,value,native=True):
 if eligible is None:c['unknown_eligibility']+=1
 elif eligible:
  c['eligible']+=1
  if not native:c['unattributed']+=1
  if value is None:c['unknown']+=1
  else:c['known']+=1;c['sum']+=float(value)
def _finish(c,*,inherited=0):
 exact=None if c['unknown'] or c['unknown_eligibility'] or inherited else c['sum']
 return dict(**c,exact_within_log_sum=exact,known_sample_mean=c['sum']/c['known'] if c['known'] else None,exact_within_log_mean=exact/c['eligible'] if exact is not None and c['eligible'] else None,inherited_unknown_actor_exposures=inherited)
def _ratio(n,d,*,inherited=0):
 a=_finish(n,inherited=inherited);b=_finish(d,inherited=inherited)
 return dict(numerator=a,denominator=b,exact_within_log_value=a['exact_within_log_sum']/b['exact_within_log_sum'] if a['exact_within_log_sum'] is not None and b['exact_within_log_sum'] is not None and b['exact_within_log_sum']>0 else None)

def build_charted_features(event_receipt,charting_block,*,before_period,cutoff,position_evidence=()):
 evidence=validate_event_evidence(event_receipt['event_evidence'],before_period=before_period,cutoff=cutoff)
 source=charting_block.get('source',{})
 if not source.get('snapshot_id') or not source.get('content_sha256') or source.get('source_uri','').split('/')[-1] not in {f'ftn_charting_{r["season"]}.parquet' for r in evidence['events']}:raise ValueError('FTN indexed native source lineage required')
 if clock(source.get('captured_at'))>clock(cutoff) or clock(source.get('observed_at'))>clock(cutoff):raise ValueError('Charting source unavailable at actual cutoff')
 charts={}
 for r in charting_block['rows']:
  key=(r['game_id'],r['play_id'])
  if key in charts:raise ValueError('Duplicate native charting game/play')
  charts[key]=r
 proofs=deepcopy(list(position_evidence));positions,position_facts=_positions(proofs,cutoff)
 base=build_player_opportunity_components(event_receipt,before_period=before_period,cutoff=cutoff,position_evidence=proofs)
 identity={(r['game_id'],r['team'],r['source_player_id']):r for r in base['actor_game_rows']}
 actors={};teams={};defenses={};basis=[];matched=0;unmatched=[]
 for event in sorted(evidence['events'],key=lambda e:(e['game_id'],int(e['play_id']))):
  raw=event['raw_flags'];gid=event['game_id'];team=event['team'];tm=teams.setdefault((gid,team),{})
  chart=charts.get((gid,event['play_id']));flags=chart['flags'] if chart else {};matched+=chart is not None
  if chart and (chart['season'],chart['week'])!=(event['season'],event['week']):raise ValueError('FTN native period conflict')
  channels={x['channel'] for x in event['opportunities']}
  attempt=True if 'pass_attempts' in channels else None if 'pass_attempts' in event['unknown_channels'] else False
  rush=True if 'rush_attempts' in channels else None if 'rush_attempts' in event['unknown_channels'] else False
  target=True if 'targets' in channels else None if 'targets' in event['unknown_channels'] else False
  scramble=_and(rush,_flag(raw.get('qb_scramble')))
  db=False if event['status'] in {'excluded','not_applicable'} else None if event['status']=='unknown' else _or(attempt,_flag(raw.get('sack')),scramble)
  passer=raw.get('passer_player_id') or (raw.get('rusher_player_id') if scramble is True else None);receiver=raw.get('receiver_player_id')
  if scramble is True and raw.get('passer_player_id') and raw.get('rusher_player_id') and raw['passer_player_id']!=raw['rusher_player_id']:raise ValueError('Conflicting native scramble athlete')
  conflict=bool(chart and chart['drop_catchability_conflict']);catchable=None if conflict else flags.get('is_catchable_ball');drop=None if conflict else flags.get('is_drop')
  primary=chart['primary_read'] if chart else None
  outcomes={'targets':(target,1.),'first_read':(_and(target,primary),1.),'catchable':(target,catchable),'screen':(target,flags.get('is_screen_pass')),'contested':(target,flags.get('is_contested_ball')),'drops':(_and(target,catchable),drop),'catchable_count':(_and(target,catchable),1.),'dropbacks':(db,1.),'throwaways':(db,flags.get('is_throw_away')),'play_action':(db,flags.get('is_play_action'))}
  for name,(eligible,value) in outcomes.items():
   native=passer if name in {'dropbacks','throwaways','play_action'} else receiver
   _add(tm.setdefault(name,_counter()),eligible,value,native)
   if not native or eligible is False:continue
   key=(gid,team,str(native));original=identity.get(key)
   if original is None:continue
   if name in {'dropbacks','throwaways','play_action'}:
    proof=positions.get((gid,str(native),team))
    if proof is None or proof['position']!='QB':continue
   actor=actors.setdefault(key,dict(game_id=gid,team=team,source_player_id=str(native),player_master_id=original['player_master_id'],measurements={}))
   _add(actor['measurements'].setdefault(name,_counter()),eligible,value)
  pair={canonical_team(t) for t in gid.split('_')[2:]}
  if team not in pair or len(pair)!=2:raise ValueError('Native defensive team pair conflict')
  defense=next(iter(pair-{team}))
  if raw.get('defteam') not in (None,defense):raise ValueError('Native defense contradicts PBP')
  dc=defenses.setdefault((gid,defense),_counter());blitz=None if not chart or chart['counts']['n_blitzers'] is None else chart['counts']['n_blitzers']>0
  _add(dc,db,blitz)
  if not chart and (db is not False or target is not False):unmatched.append(dict(game_id=gid,play_id=event['play_id'],dropback=db,target=target))
  basis.append(dict(game_id=gid,play_id=event['play_id'],team=team,passer=passer,receiver=receiver,outcomes=outcomes,blitz=blitz,drop_conflict=conflict))
 rows=[]
 for key,a in sorted(actors.items()):
  raw=a.pop('measurements');tm=teams[key[:2]];metrics={}
  def c(name):return raw.get(name,_counter())
  target_unknown=tm['targets']['unattributed']+tm['targets']['unknown_eligibility']
  db_unknown=tm['dropbacks']['unattributed']+tm['dropbacks']['unknown_eligibility']
  if 'dropbacks' in raw:
   metrics['G03-M05']=_finish(c('throwaways'),inherited=db_unknown)
   metrics['G03-M09']=_ratio(c('play_action'),c('dropbacks'),inherited=db_unknown)
  if 'targets' in raw:
   metrics['G08-M06']=dict(numerator=_finish(c('first_read'),inherited=target_unknown),full_team_denominator=_finish(tm['first_read']),exact_within_log_value=None)
   n=metrics['G08-M06']['numerator']['exact_within_log_sum'];d=metrics['G08-M06']['full_team_denominator']['exact_within_log_sum']
   if n is not None and d is not None and d>0:metrics['G08-M06']['exact_within_log_value']=n/d
   for mid,name in [('G08-M10','catchable'),('G10-M06','screen'),('G10-M10','contested')]:metrics[mid]=_ratio(c(name),c('targets'),inherited=target_unknown)
   metrics['G09-M09']=_ratio(c('drops'),c('catchable_count'),inherited=target_unknown)
  rows.append(dict(**a,metrics=metrics))
 team_rows=[dict(game_id=g,team=t,measurements={m:_finish(c) for m,c in counters.items()}) for (g,t),counters in sorted(teams.items())]
 defense_rows=[dict(game_id=g,team=t,metrics={'G14-M02':_finish(c)}) for (g,t),c in sorted(defenses.items())]
 semantic=dict(version=VERSION,before_period=before_period,definitions=DEFINITIONS,actor_game_rows=rows,team_game_denominators=team_rows,defense_game_rows=defense_rows,event_basis=basis,position_facts=position_facts,coverage=dict(PBP_events=len(evidence['events']),matched_charting_events=matched,unmatched_relevant_PBP=unmatched))
 return dict(**semantic,semantic_sha256=_hash(semantic),provenance=dict(charting_source=deepcopy(source),event_source=deepcopy(evidence.get('source',{})),original_position_evidence=proofs,actual_derived_at=clock(cutoff).isoformat(),producer_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,limitations=['Observed source log only; full-game finalness unknown','FTN date_pulled is API retrieval, not original publication','Full-team native/unmapped actors retained; absent charting is unknown, never false','n_blitzers is explicit charted blitz count, not pressure','No rollout, alignment, actor motion, routes or probability inferred'])

def derive_retrospective_charted_features(parent_ref,pbp_snapshot,charting_snapshot,*,actual_read_at=None,position_evidence=(),directory=None):
 from datetime import datetime,UTC
 from .opportunity_source_capture import load_event_artifact
 from .charting_source_components import load_charting_snapshot
 read_at=clock(actual_read_at or datetime.now(UTC));original=clock(parent_ref.get('decision_cutoff_at'));lock=clock(pbp_snapshot.slate_lock_at)
 if original is None or lock is None or not original<lock<=read_at<=datetime.now(UTC):raise ValueError('Explicit retrospective original boundary and actual postlock read required')
 parent=load_event_artifact(parent_ref,pbp_snapshot,before_period=parent_ref['before_period'],cutoff=original,directory=directory)
 charting=load_charting_snapshot(charting_snapshot,cutoff=read_at)
 result=build_charted_features(parent,charting,before_period=parent_ref['before_period'],cutoff=read_at,position_evidence=position_evidence)
 result['provenance']['retrospective_read']=dict(original_evidence_boundary_at=original.isoformat(),source_lock_at=lock.isoformat(),actual_read_at=read_at.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),parent_artifact_ref=deepcopy(parent_ref),meaning='Frozen parent authentication at original boundary; new charting captured postlock, never pregame evidence')
 return result

def require_feature_use(value,*,purpose):
 if purpose!='offline_descriptive':raise ValueError('Postlock charted features cannot be registered as current/pregame serving evidence')
 if value.get('evidence_use')!='postlock_descriptive_not_pregame_or_serving':raise ValueError('Explicit evidence use required')
 return value
