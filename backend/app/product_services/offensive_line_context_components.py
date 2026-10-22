"""Measured team outcomes associated with protection/run context, not line blame."""
from copy import deepcopy
from pathlib import Path
from collections import defaultdict
import hashlib
from .opportunity_events import validate_event_evidence,_flag
from .defense_context_evidence import _eligibility,_number,_metric,_finish,_hash
from .player_effectiveness_components import _record
from .environment_context_evidence import _and

VERSION='offensive_line_context_components_v1'
DEFINITIONS={
 'G13-M04':dict(definition='Source sacks / (official pass attempts including spikes + source sacks); scrambles excluded',unit='observed_sack_fraction'),
 'G13-M08':dict(definition='First_down_rush OR rush_TD / nonkneel rushes with preplay ydstogo<=2',unit='observed_short_yard_conversion_fraction'),
 'G13-M09':dict(definition='Source play net yards<0 / all nonkneel official rushes',unit='observed_behind_LOS_fraction'),
 'G13-M10':dict(definition='Provider EPA>0 / nonkneel official rush, split by native run_location left/middle/right; unknown direction separate',unit='observed_rush_success_fraction')}
SOURCE_GAPS={'G13-M01':'Historical source-proven starting-line continuity not supplied by this PBP',
 'G13-M02':'Historical missing-starting-linemen source proof not supplied by this PBP',
 'G13-M03':'Pressure allowed unavailable in verified PBP fields','G13-M05':'Time to pressure unavailable in verified PBP fields',
 'G13-M06':'Vendor pass-block win rate unavailable in verified PBP fields','G13-M07':'Vendor run-block win rate unavailable in verified PBP fields'}
DIRECTIONS=('left','middle','right','unknown')


def _or(a,b):return True if a is True or b is True else None if a is None or b is None else False


def _direction(raw):
 value=raw.get('run_location')
 return str(value).strip().lower() if str(value).strip().lower() in DIRECTIONS[:-1] else 'unknown'


def build_offensive_line_context_components(event_receipt,*,before_period,cutoff,last_n_games=8):
 if isinstance(last_n_games,bool) or not isinstance(last_n_games,int) or not 1<=last_n_games<=32:raise ValueError('Observed window must be integer1..32')
 evidence=validate_event_evidence(event_receipt['event_evidence'],before_period=before_period,cutoff=cutoff)
 games={};basis=[]
 for event in sorted(evidence['events'],key=lambda e:(e['game_id'],int(e['play_id']))):
  key=(event['game_id'],event['team']);game=games.setdefault(key,dict(game_id=key[0],offense_team=key[1],season=int(key[0][:4]),week=int(key[0].split('_')[1]),metrics={m:_metric() for m in DEFINITIONS if m!='G13-M10'},direction_success={d:_metric() for d in DIRECTIONS}))
  raw=event['raw_flags'];_,dropback,rushing=_eligibility(event);sack=_flag(raw.get('sack'));channels={o['channel'] for o in event['opportunities']}
  official=True if 'pass_attempts' in channels else None if 'pass_attempts' in event['unknown_channels'] else False
  sack_eligible=_and(dropback,sack);pass_or_sack=_or(official,sack_eligible)
  togo=_number(raw.get('ydstogo'));short=_and(rushing,None if togo is None or togo<0 else togo<=2)
  first=_flag(raw.get('first_down_rush'));td=_flag(raw.get('rush_touchdown'));converted=_or(first,td)
  yards=_number(raw.get('yards_gained'));epa=_number(raw.get('epa'));direction=_direction(raw)
  outcomes={'G13-M04':(pass_or_sack,None if sack is None else float(sack)),
   'G13-M08':(short,None if converted is None else float(converted)),
   'G13-M09':(rushing,None if yards is None else float(yards<0))}
  for metric,(eligible,outcome) in outcomes.items():_record(game['metrics'][metric],eligible,outcome)
  # Unknown direction is not imputed to a known direction; it masks complete directional rates.
  success=None if epa is None else float(epa>0)
  for d in DIRECTIONS:
   eligible=rushing if d==direction else _and(rushing,None if direction=='unknown' and d!='unknown' else False)
   _record(game['direction_success'][d],eligible,success)
  basis.append(dict(game_id=key[0],play_id=event['play_id'],team=key[1],outcomes=outcomes,rushing=rushing,direction=direction,success=success,native_run_location=raw.get('run_location'),native_run_gap=raw.get('run_gap')))
 grouped=defaultdict(list)
 for game in games.values():grouped[game['offense_team']].append(game)
 windows=[]
 for team,rows in sorted(grouped.items()):
  rows.sort(key=lambda r:(r['season'],r['week'],r['game_id']))
  if len({(r['season'],r['week']) for r in rows})!=len(rows):raise ValueError('Multiple offense games in one period')
  selected=rows[-last_n_games:];totals={m:_metric() for m in DEFINITIONS if m!='G13-M10'};directions={d:_metric() for d in DIRECTIONS}
  for game in selected:
   for target,source in ((totals,game['metrics']),(directions,game['direction_success'])):
    for m,counts in source.items():
     for k,v in counts.items():target[m][k]+=v
  windows.append(dict(offense_team=team,observed_games=len(selected),source_periods=[r['season']*100+r['week'] for r in selected],metrics={k:_finish(v) for k,v in totals.items()},direction_success={k:_finish(v) for k,v in directions.items()}))
 finished=[{**r,'metrics':{k:_finish(v) for k,v in r['metrics'].items()},'direction_success':{k:_finish(v) for k,v in r['direction_success'].items()}} for _,r in sorted(games.items())]
 result=dict(version=VERSION,before_period=before_period,last_n_observed_games=last_n_games,definitions=deepcopy(DEFINITIONS),source_gaps=deepcopy(SOURCE_GAPS),team_game_rows=finished,team_windows=windows,
  source_quality={k:deepcopy(evidence['source'].get(k)) for k in ('game_completion','full_game_coverage')},
  limitations=['Team outcomes do not isolate offensive-line causal contribution, protection assignment or individual blocker ability',
   'Native run direction is not defensive front or gap assignment; run_gap preserved only as source lineage',
   'Provider EPA is derived measurement, not raw physical outcome or forecast','Window pools known exposures over lastN observed logs, not average game rates or certified complete games',
   'Unknown source direction/eligibility/outcome masks all-eligible rates; known samples remain explicit','Caller must authenticate immutable parent/source; marker alone does not verify intake'],forecast=None)
 result['semantic_measurements_sha256']=_hash(dict(result=result,event_basis=basis))
 result['provenance']=dict(source=deepcopy(evidence['source']),event_receipt_sha256=evidence['sha256'],producer_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),measurement_cutoff_at=str(cutoff))
 return result


def derive_retrospective_offensive_line_context(parent_ref,snapshot,*,actual_read_at=None,directory=None,last_n_games=8):
 from datetime import UTC,datetime
 from .factual_designation import clock
 from .opportunity_source_capture import load_event_artifact
 from .player_opportunity_components import RETROSPECTIVE_USE
 read_at=clock(actual_read_at or datetime.now(UTC));original=clock(parent_ref.get('decision_cutoff_at'));lock=clock(snapshot.slate_lock_at)
 if original is None or lock is None or not original<lock<=read_at<=datetime.now(UTC):raise ValueError('Retrospective reader requires original prelock boundary and actual nonfuture postlock read')
 parent=load_event_artifact(parent_ref,snapshot,before_period=parent_ref['before_period'],cutoff=original,directory=directory)
 result=build_offensive_line_context_components(parent,before_period=parent_ref['before_period'],cutoff=read_at,last_n_games=last_n_games)
 result['underlying_measurements_sha256']=result.pop('semantic_measurements_sha256');result.update(evidence_use=RETROSPECTIVE_USE,pregame_serving_eligible=False)
 result['semantic_measurements_sha256']=_hash(dict(underlying_measurements_sha256=result['underlying_measurements_sha256'],evidence_use=RETROSPECTIVE_USE,pregame_serving_eligible=False))
 result['provenance'].pop('measurement_cutoff_at');result['provenance']['retrospective_read']=dict(original_evidence_boundary_at=original.isoformat(),source_lock_at=lock.isoformat(),actual_read_at=read_at.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),parent_artifact_ref=deepcopy(parent_ref),meaning='Frozen historical byte validation; no new pregame intake/current serving')
 return result
