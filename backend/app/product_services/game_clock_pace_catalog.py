"""Audited elapsed game-clock pace, distinct from wall-clock play cadence."""
from copy import deepcopy
from collections import defaultdict
import math
from datetime import datetime,UTC
from .environment_context_evidence import DEFINITIONS as ENV_DEFINITIONS
from .defense_context_evidence import _number
from .evaluation_record import digest
from .market_snapshots import canonical_team
VERSION='game_clock_pace_catalog_v1'
IDS=('G01-M04','G01-M05','G01-M07','G01-M08','G01-M09','G01-M10')

def native_order_proof(records,*,before_period,max_rows=100000):
 games=defaultdict(list)
 for index,row in enumerate(records):
  if index>=max_rows:raise ValueError('Native timeline row bound exceeded')
  if row.get('season_type')!='REG':continue
  season=_number(row.get('season'));week=_number(row.get('week'))
  if season is None or week is None or season!=int(season) or week!=int(week) or not 1<=week<=18:raise ValueError('Explicit native timeline period required')
  if season*100+week>=before_period:continue
  gid=row['game_id'];parts=gid.split('_')
  if len(parts)!=4 or parts[:2]!=[str(int(season)),f'{int(week):02d}']:raise ValueError('Native timeline game scope differs')
  play=_number(row.get('play_id'));sequence=_number(row.get('order_sequence'))
  games[gid].append(dict(play_id=play if play is not None and int(play)==play else None,order_sequence=sequence))
 proofs=[]
 for gid,events in sorted(games.items()):
  missing_play=sum(e['play_id'] is None for e in events);missing_sequence=sum(e['order_sequence'] is None for e in events)
  duplicate_play=len(events)-len({e['play_id'] for e in events});duplicate_sequence=len(events)-len({e['order_sequence'] for e in events})
  ordered=sorted(events,key=lambda e:e['play_id'] if e['play_id'] is not None else -1)
  inversions=sum(a['order_sequence']>=b['order_sequence'] for a,b in zip(ordered,ordered[1:]) if a['order_sequence'] is not None and b['order_sequence'] is not None)
  proofs.append(dict(game_id=gid,native_timeline_rows=len(events),missing_play_ids=missing_play,missing_order_sequences=missing_sequence,duplicate_play_ids=duplicate_play,duplicate_order_sequences=duplicate_sequence,nonincreasing_sequences_by_play_id=inversions,play_id_order_matches_native_order=not(missing_play or missing_sequence or duplicate_play or duplicate_sequence or inversions),native_order_semantic_sha256=digest(sorted(events,key=lambda e:(str(e['play_id']),str(e['order_sequence']))))))
 return dict(before_period=before_period,game_proofs=proofs,native_order_semantic_sha256=digest(proofs))

def _metric(raw,order_verified):
 m=deepcopy(raw)
 for field in ('eligible_events','known_outcome_events','unknown_outcome_events','unknown_eligibility_events'):
  n=m[field]
  if type(n) not in {int,float} or not math.isfinite(n) or n<0 or int(n)!=n:raise ValueError('Nonnegative pace exposure required')
 if m['known_outcome_events']+m['unknown_outcome_events']!=m['eligible_events']:raise ValueError('Pace exposure partition differs')
 total=m['observed_outcome_sum'];known=m['known_outcome_events']
 if total is not None and (type(total) not in {int,float} or not math.isfinite(total) or total<0):raise ValueError('Nonnegative elapsed game-clock seconds required')
 exact=total/known if total is not None and known and not(m['unknown_outcome_events'] or m['unknown_eligibility_events']) else None
 if exact!=m['all_eligible_mean']:raise ValueError('Source game-clock interval mean differs')
 m.update(value=exact if order_verified else None,unit='elapsed_eligible_game_clock_seconds_between_play_starts',native_order_verified=order_verified,known_ordered_sample_mean=total/known if order_verified and total is not None and known else None)
 if not order_verified:m['legacy_play_id_sorted_mean']=m['observed_known_mean']
 return m

def build_game_clock_pace_catalog(context,proof,*,before_period,last_n=8):
 if context.get('version') not in {'environment_context_evidence_v1','native_game_clock_intervals_v1'} or context.get('before_period')!=before_period or proof.get('before_period')!=before_period:raise ValueError('Matched native game-clock source/order scope required')
 if type(before_period)is not int or not 200001<=before_period or not 1<=before_period%100<=18 or type(last_n)is not int or not 1<=last_n<=32:raise ValueError('Explicit prior REG scope/window required')
 for mid in IDS:
  if context['definitions'][mid]!=ENV_DEFINITIONS[mid]:raise ValueError('Reviewed eligible game-clock definition differs')
 bygame={r['game_id']:r for r in proof['game_proofs']}
 if len(bygame)!=len(proof['game_proofs']):raise ValueError('Duplicate native timeline proof')
 rows=[];seen=set();groups=defaultdict(list)
 for src in context['game_rows']:
  gid=src['game_id'];parts=gid.split('_');team=canonical_team(src['team']);p=bygame.get(gid)
  if len(parts)!=4 or parts[:2]!=[str(src['season']),f"{src['week']:02d}"] or src['season']*100+src['week']>=before_period or team not in {canonical_team(t) for t in parts[2:]} or p is None:raise ValueError('Prior native timeline/team identity proof required')
  key=(gid,team)
  if key in seen:raise ValueError('Duplicate native game/team')
  seen.add(key);native=context.get('version')=='native_game_clock_intervals_v1'
  if native and (context.get('timeline_order')!='native_order_sequence' or src.get('native_timeline_rows')!=p['native_timeline_rows']):raise ValueError('Native ordered timeline coverage differs')
  ordered=not(p['missing_play_ids'] or p['missing_order_sequences'] or p['duplicate_play_ids'] or p['duplicate_order_sequences']) if native else p['play_id_order_matches_native_order'];row=dict(game_id=gid,season=src['season'],week=src['week'],team=team,metrics={mid:_metric(src['metrics'][mid],ordered) for mid in IDS},native_timeline_order=deepcopy(p),interval_rejections=deepcopy(src['interval_rejections']));rows.append(row)
  if src['season']==before_period//100:groups[team].append(row)
 windows=[]
 for team,group in sorted(groups.items()):
  group=sorted(group,key=lambda r:(r['week'],r['game_id']))[-last_n:]
  if len({r['week'] for r in group})!=len(group):raise ValueError('Ambiguous native team period')
  metrics={};ordered=all(r['metrics']['G01-M04']['native_order_verified'] for r in group)
  for mid in IDS:
   sums={k:sum(r['metrics'][mid][k] for r in group) for k in ('eligible_events','known_outcome_events','unknown_outcome_events','unknown_eligibility_events')};total=sum(r['metrics'][mid]['observed_outcome_sum'] or 0 for r in group);known=sums['known_outcome_events'];sums.update(observed_outcome_sum=total if known else None,observed_known_mean=total/known if known else None,all_eligible_mean=total/known if known and not(sums['unknown_eligibility_events'] or sums['unknown_outcome_events']) else None);metrics[mid]=_metric(sums,ordered)
  windows.append(dict(team=team,observed_game_ids=[r['game_id'] for r in group],metrics=metrics))
 basis=dict(version=VERSION,before_period=before_period,last_n_same_season_observed_games=last_n,definitions={mid:context['definitions'][mid] for mid in IDS},game_rows=sorted(rows,key=lambda r:(r['game_id'],r['team'])),team_windows=windows,native_order_semantic_sha256=proof['native_order_semantic_sha256'])
 return dict(**basis,semantic_sha256=digest(basis),source_context_semantic_sha256=context['semantic_measurements_sha256'],evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None,provenance=deepcopy(context['provenance']),limitations=['Elapsed game clock between eligible same-offense/drive/quarter play starts, NOT wall-clock UTC cadence or time between play ends','Full native controls break adjacency; unknown/invalid clocks and subset states remain in exposure coverage','Clock-stopped zero differences are retained as observed game-clock intervals; missing values never become zero','Known native order disagreement masks exact game/window rates; full-game coverage remains unverified'],consumer_status='Features-only; models/optimizer pending')

NATIVE_CONTEXT_VERSION='native_game_clock_intervals_v1'

def _native_timeline(parent,*,before_period,cutoff):
 from .opportunity_events import validate_event_evidence
 evidence=validate_event_evidence(parent['event_evidence'],before_period=before_period,cutoff=cutoff);timeline=[];seen=set()
 for event in evidence['events']:
  key=(event['game_id'],int(event['play_id']))
  if key in seen:raise ValueError('Duplicate native timeline event')
  seen.add(key);timeline.append(dict(game_id=event['game_id'],play_id=key[1],order=_number(event['raw_flags'].get('order_sequence')),event=event))
 for field in ('unscoped_nonoffensive_rows','scoped_administrative_rows'):
  for raw in parent.get(field,[]):
   gid=raw['game_id'];play=_number(raw.get('play_id'));season=_number(raw.get('season'));week=_number(raw.get('week'))
   if play is None or play!=int(play) or season is None or week is None or raw.get('season_type')!='REG' or season*100+week>=before_period or gid.split('_')[:2]!=[str(int(season)),f'{int(week):02d}']:raise ValueError('Prior native control scope required')
   key=(gid,int(play))
   if key in seen:raise ValueError('Duplicate native timeline control')
   seen.add(key);timeline.append(dict(game_id=gid,play_id=int(play),order=_number(raw.get('order_sequence')),control=field))
 bygame=defaultdict(list)
 for row in timeline:bygame[row['game_id']].append(row)
 uncertain={gid for gid,group in bygame.items() if any(r['order'] is None for r in group) or len({r['order'] for r in group})!=len(group)}
 return evidence,sorted(timeline,key=lambda r:(r['game_id'],r['order'] if r['order'] is not None else -1,r['play_id'])),uncertain

def build_native_game_clock_context(parent,*,before_period,cutoff):
 """Re-derive intervals in provider order; do not relabel old play-ID intervals."""
 from .environment_context_evidence import _snap,_conditions,_and,_add
 from .defense_context_evidence import _metric,_finish
 from .factual_designation import clock
 from pathlib import Path
 import hashlib
 evidence,timeline,uncertain=_native_timeline(parent,before_period=before_period,cutoff=cutoff);games={};previous={};basis=[];row_counts=defaultdict(int)
 for item in timeline:row_counts[item['game_id']]+=1
 for entry in timeline:
  gid=entry['game_id']
  if 'control' in entry:
   previous[gid]=dict(control=True);basis.append(dict(game_id=gid,play_id=entry['play_id'],order=entry['order'],control=entry['control']));continue
  event=entry['event'];raw=event['raw_flags'];key=(gid,event['team']);snap=_snap(event);conditions=_conditions(raw)
  game=games.setdefault(key,dict(game_id=gid,team=event['team'],season=event['season'],week=event['week'],metrics={mid:_metric() for mid in IDS},interval_rejections=defaultdict(int),native_timeline_rows=row_counts[gid]))
  drive=_number(raw.get('fixed_drive'));drive=int(drive) if drive is not None and drive>=0 and drive==int(drive) else None
  current=dict(team=event['team'],snap=snap,drive=drive,qtr=_number(raw.get('qtr')),clock=_number(raw.get('game_seconds_remaining')),conditions=conditions)
  prev=previous.get(gid);previous[gid]=current;eligibility=True;elapsed=None;reason=None
  if gid in uncertain:eligibility=None;reason='native_order_unknown_or_duplicate'
  elif prev is None:eligibility=False;reason='first_native_row'
  elif prev.get('control'):eligibility=False;reason='source_control_break'
  elif prev['team']!=current['team']:eligibility=False;reason='offense_change'
  elif prev['snap'] is False or snap is False:eligibility=False;reason='known_nonoffensive_break'
  elif prev['snap'] is None or snap is None:eligibility=None;reason='unknown_snap_eligibility'
  elif prev['drive'] is None or drive is None:eligibility=None;reason='native_drive_unknown'
  elif prev['drive']!=drive:eligibility=False;reason='native_drive_change'
  elif prev['qtr'] is None or current['qtr'] is None:eligibility=None;reason='quarter_unknown'
  elif prev['qtr']!=current['qtr']:eligibility=False;reason='quarter_change'
  elif prev['clock'] is None or current['clock'] is None:eligibility=None;reason='game_clock_unknown'
  elif not 0<=prev['clock']<=3600 or not 0<=current['clock']<=3600:eligibility=None;reason='game_clock_out_of_range'
  elif prev['clock']<current['clock']:eligibility=None;reason='nonmonotonic_game_clock'
  else:elapsed=prev['clock']-current['clock']
  if reason:game['interval_rejections'][reason]+=1
  if snap is not False:
   subsets={'G01-M04':True,'G01-M05':conditions['neutral'],'G01-M07':conditions['firsthalf'],'G01-M08':conditions['secondhalf'],'G01-M09':conditions['trailing'],'G01-M10':conditions['leading']}
   names={'G01-M05':'neutral','G01-M07':'firsthalf','G01-M08':'secondhalf','G01-M09':'trailing','G01-M10':'leading'}
   for mid,condition in subsets.items():
    prior=True if mid=='G01-M04' else prev.get('conditions',{}).get(names[mid]) if prev else None
    _add(game['metrics'][mid],_and(eligibility,_and(condition,prior)),elapsed)
  basis.append(dict(game_id=gid,play_id=entry['play_id'],order=entry['order'],snap=snap,conditions=conditions,drive=drive,qtr=current['qtr'],game_clock=current['clock']))
 rows=[dict(row,interval_rejections=dict(row['interval_rejections']),metrics={mid:_finish(value) for mid,value in row['metrics'].items()}) for _,row in sorted(games.items())]
 result=dict(version=NATIVE_CONTEXT_VERSION,before_period=before_period,timeline_order='native_order_sequence',definitions={mid:ENV_DEFINITIONS[mid] for mid in IDS},game_rows=rows,source_order_unknown_games=sorted(uncertain),forecast=None)
 result['semantic_measurements_sha256']=digest(dict(result=result,native_basis=basis));result['provenance']=dict(source=deepcopy(evidence['source']),event_receipt_sha256=evidence['sha256'],actual_derived_at=datetime.now(UTC).isoformat(),producer_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
 return result

NATIVE_DRIVE_VERSION='native_order_redzone_drives_v1'

def build_native_redzone_drives(parent,*,before_period,cutoff):
 from .environment_context_evidence import _snap,_and
 from .defense_context_evidence import _eligibility,_metric,_finish
 from .defense_context_extensions import _no_pass_terminal,DEFINITIONS as DRIVE_DEFINITIONS
 from .opportunity_events import _flag
 from .factual_designation import clock
 from pathlib import Path
 import hashlib
 evidence,timeline,uncertain=_native_timeline(parent,before_period=before_period,cutoff=cutoff);games={};drives={};unbound=[]
 for entry in timeline:
  if 'event' not in entry:continue
  event=entry['event'];raw=event['raw_flags'];gid=event['game_id']
  try:defense=canonical_team(str(raw.get('defteam') or ''))
  except ValueError:defense=None
  if not defense:
   unbound.append(dict(game_id=gid,play_id=entry['play_id'],reason='Unknown native defense; no allocation'));continue
  offense=event['team'];key=(gid,defense)
  if {defense,offense}!={canonical_team(t) for t in gid.split('_')[2:]}:raise ValueError('Native defense/opponent scope contradiction')
  game=games.setdefault(key,dict(game_id=gid,defense_team=defense,offense_team=offense,season=event['season'],week=event['week'],metrics={'G14-M10':_metric()},drive_quality=dict(observed_redzone_drive_ids=[],uncertain_redzone_drive_ids=[],redzone_events_missing_drive_id=0,conflicting_td_drive_ids=[],drive_outcomes=[])))
  yard=_number(raw.get('yardline_100'));zone=None if yard is None or not 0<=yard<=100 else yard<=20;eligible_entry=_and(_snap(event),zone);drive=_number(raw.get('fixed_drive'));drive=str(int(drive)) if drive is not None and drive>=0 and drive==int(drive) else None
  if drive is None:
   if eligible_entry is not False:game['drive_quality']['redzone_events_missing_drive_id']+=1
   continue
  item=drives.setdefault((gid,defense,drive),dict(game_key=key,drive_id=drive,entries=[],uncertain_entry=False,events=[]))
  if eligible_entry is True:item['entries'].append(dict(play_id=entry['play_id'],order=entry['order']))
  elif eligible_entry is None:item['uncertain_entry']=True
  passing,_,rushing=_eligibility(event)
  item['events'].append(dict(play_id=entry['play_id'],order=entry['order'],pass_td=passing is True and _flag(raw.get('pass_touchdown')) is True,rush_td=rushing is True and _flag(raw.get('rush_touchdown')) is True,other_terminal=_no_pass_terminal(event)))
 for (gid,defense,did),drive in sorted(drives.items()):
  game=games[drive['game_key']];quality=game['drive_quality'];m=game['metrics']['G14-M10']
  if not drive['entries']:
   if drive['uncertain_entry']:quality['uncertain_redzone_drive_ids'].append(did);m['unknown_eligibility_events']+=1
   continue
  quality['observed_redzone_drive_ids'].append(did);m['eligible_events']+=1
  touchdowns=[r for r in drive['events'] if r['pass_td']];rushing=[r for r in drive['events'] if r['rush_td']];others=[r for r in drive['events'] if r['other_terminal']];terminals=touchdowns+rushing+others
  order_known=gid not in uncertain and all(r['order'] is not None for r in drive['entries']+terminals)
  first=min(drive['entries'],key=lambda r:r['order']) if order_known else None
  before=bool(order_known and any(r['order']<first['order'] for r in terminals))
  conflict=len({r['play_id'] for r in terminals})>1 or before or bool(touchdowns and (rushing or others))
  known=order_known and not conflict and bool(terminals)
  basis='native_order_unknown' if not order_known else 'conflicting_touchdown_evidence' if conflict else 'observed_passing_touchdown' if touchdowns else 'observed_rushing_touchdown' if rushing else others[0]['other_terminal'] if others else 'unknown_no_terminal_evidence'
  quality['drive_outcomes'].append(dict(drive_id=did,completion_basis=basis,outcome_known=known,terminal_play_ids=sorted(r['play_id'] for r in terminals),native_order_verified=order_known,first_entry_play_id=first['play_id'] if first else None,first_entry_order=first['order'] if first else None,terminal_native_orders=[dict(play_id=r['play_id'],order=r['order']) for r in sorted(terminals,key=lambda r:r['play_id'])],terminal_precedes_entry=before))
  if conflict:quality['conflicting_td_drive_ids'].append(did)
  if known:m['known_outcome_events']+=1;m['observed_outcome_sum']+=float(bool(touchdowns))
  else:m['unknown_outcome_events']+=1
 rows=[dict(r,metrics={'G14-M10':_finish(r['metrics']['G14-M10'])}) for _,r in sorted(games.items())]
 result=dict(version=NATIVE_DRIVE_VERSION,before_period=before_period,chronology_basis='native_order_sequence',definitions={'G14-M10':deepcopy(DRIVE_DEFINITIONS['G14-M10'])},game_rows=rows,unbound_native_defense_events=unbound,source_order_unknown_games=sorted(uncertain),evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None)
 result['semantic_measurements_sha256']=digest(result);result['provenance']=dict(source=deepcopy(evidence['source']),event_receipt_sha256=evidence['sha256'],actual_derived_at=datetime.now(UTC).isoformat(),producer_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
 return result

def validated_native_order_map(parent,*,before_period,cutoff):
 """Exact native key→provider order receipt, including controls and unknown games."""
 evidence,timeline,uncertain=_native_timeline(parent,before_period=before_period,cutoff=cutoff)
 rows=[dict(game_id=r['game_id'],play_id=r['play_id'],order_sequence=r['order'],is_control='control' in r,native_order_verified=r['game_id'] not in uncertain) for r in timeline]
 basis=dict(version='validated_native_order_map_v1',before_period=before_period,rows=rows,unknown_order_games=sorted(uncertain))
 return dict(**basis,semantic_sha256=digest(basis),source_snapshot_id=evidence['source']['snapshot_id'],source_byte_sha256=evidence['source']['content_sha256'],event_receipt_sha256=evidence['sha256'])
