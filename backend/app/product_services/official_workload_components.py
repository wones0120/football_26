"""Official-inclusive workloads: preserve spikes/kneels and physical play union."""
from copy import deepcopy
from pathlib import Path
import hashlib
from .opportunity_events import validate_event_evidence,_flag
from .player_opportunity_components import build_player_opportunity_components,_condition
from .defense_context_extensions import _positions
from .defense_context_evidence import _metric,_finish,_hash
from .player_effectiveness_components import _record
from .environment_context_evidence import _and

VERSION='official_workload_components_v1'
RB_SPLITS=('G06-M03','G06-M04','G06-M05','G06-M06','G06-M07','G06-M08','G06-M09','G06-M10')
DEFINITIONS={
 'G03-M01':'Official dropback union: official pass attempt including spike OR sack OR official rush with scramble; each play once',
 'G03-M07':'Official QB scramble count / official-inclusive QB dropbacks',
 'G03-M10':'QB official-inclusive dropbacks / all team official-inclusive dropbacks, including native actors without canonical identity',
 'G06-M02':'RB official carries including kneels / all full-source team official carries including QB kneels',
 'G06-M03':'Official carries including kneels on first/second preplay down',
 'G06-M04':'Official carries including kneels on third preplay down',
 'G06-M05':'Official carries including kneels with preplay ydstogo<=2',
 'G06-M06':'Official carries including kneels in Q2/Q4 with half_seconds_remaining<=120',
 'G06-M07':'Official carries including kneels in Q1/Q2',
 'G06-M08':'Official carries including kneels in Q4',
 'G06-M09':'Official carries including kneels with preplay score differential>0',
 'G06-M10':'Official carries including kneels with preplay score differential<0'}


def _or(*values):return True if True in values else None if None in values else False


def _counter():return {**_metric(),'unattributed_eligible_events':0,'unattributed_unknown_eligibility_events':0}


def _add(counter,eligible,native):
 _record(counter,eligible,1.)
 if eligible is True and not native:counter['unattributed_eligible_events']+=1
 if eligible is None and not native:counter['unattributed_unknown_eligibility_events']+=1


def _result(counter,team=None):
 finished=_finish(counter);unknown=team['unattributed_unknown_eligibility_events'] if team is not None else counter['unknown_eligibility_events'];unattributed=(team or counter)['unattributed_eligible_events'] if team is not None else 0
 finished['counted_lower_bound']=counter['observed_outcome_sum']
 finished['exact_within_log_count']=None if counter['unknown_eligibility_events'] or unknown or unattributed else counter['observed_outcome_sum']
 finished['inherited_team_unknown_eligibility']=unknown;finished['inherited_unattributed_eligible_events']=unattributed
 return finished


def build_official_workload_components(event_receipt,*,before_period,cutoff,position_evidence=()):
 proofs=deepcopy(list(position_evidence));positions,_=_positions(proofs,cutoff)
 evidence=validate_event_evidence(event_receipt['event_evidence'],before_period=before_period,cutoff=cutoff)
 base=build_player_opportunity_components(event_receipt,before_period=before_period,cutoff=cutoff,position_evidence=proofs)
 identities={(r['game_id'],r['team'],r['source_player_id']):r for r in base['actor_game_rows']};actors={};teams={};basis=[];missing=[]
 def actor_for(key):
  proof=positions.get((key[0],key[2],key[1]));original=identities.get(key)
  if not proof or proof['position'] not in {'QB','RB'}:return None
  if key not in actors:
   canonical=original['player_master_id'] if original else proof['player_master_id']
   actors[key]=dict(game_id=key[0],team=key[1],source_player_id=key[2],player_master_id=canonical,position=proof['position'],position_status='scoped_source_proven',counts={})
  return actors[key]
 for key in identities:actor_for(key)
 for event in sorted(evidence['events'],key=lambda e:(e['game_id'],int(e['play_id']))):
  raw=event['raw_flags'];key=(event['game_id'],event['team']);tm=teams.setdefault(key,{})
  channels={o['channel'] for o in event['opportunities']}
  official_pass=True if 'pass_attempts' in channels else None if 'pass_attempts' in event['unknown_channels'] else False
  official_rush=True if 'rush_attempts' in channels else None if 'rush_attempts' in event['unknown_channels'] else False
  scramble=_and(official_rush,_flag(raw.get('qb_scramble')))
  sack=_flag(raw.get('sack'))
  if event['status'] in {'excluded','not_applicable'}:dropback=False;scramble=False
  elif event['status']=='unknown':dropback=None;scramble=None
  else:dropback=_or(official_pass,sack,scramble)
  if event['status'] not in {'excluded','not_applicable'} and _flag(raw.get('qb_scramble')) is True and raw.get('passer_player_id') and raw.get('rusher_player_id') and str(raw['passer_player_id'])!=str(raw['rusher_player_id']):raise ValueError('Scramble has contradictory native passer/rusher identity')
  passer=raw.get('passer_player_id') or (raw.get('rusher_player_id') if _flag(raw.get('qb_scramble')) is True else None)
  rusher=raw.get('rusher_player_id')
  down=raw.get('down');qtr=raw.get('qtr');score=raw.get('score_differential')
  predicates=[_condition(down,lambda n:n in {1,2},lambda n:n in {1,2,3,4}),_condition(down,lambda n:n==3,lambda n:n in {1,2,3,4}),
   _condition(raw.get('ydstogo'),lambda n:n<=2,lambda n:n>=0),
   _and(_condition(qtr,lambda n:n in {2,4},lambda n:n in {1,2,3,4,5}),_condition(raw.get('half_seconds_remaining'),lambda n:n<=120,lambda n:0<=n<=1800)),
   _condition(qtr,lambda n:n in {1,2},lambda n:n in {1,2,3,4,5}),_condition(qtr,lambda n:n==4,lambda n:n in {1,2,3,4,5}),
   _condition(score,lambda n:n>0),_condition(score,lambda n:n<0)]
  outcomes={'dropbacks':(dropback,passer),'scrambles':(scramble,passer),'official_carries':(official_rush,rusher),
   **{m:(_and(official_rush,p),rusher) for m,p in zip(RB_SPLITS,predicates)}}
  for name,(eligible,native) in outcomes.items():
   _add(tm.setdefault(name,_counter()),eligible,native)
   if eligible is False:continue
   if not native:
    missing.append(dict(game_id=key[0],team=key[1],play_id=event['play_id'],measurement=name,eligibility=eligible,reason='Native actor unavailable; full-team opportunity retained'));continue
   a=actor_for((*key,str(native)))
   if a and ((a['position']=='QB' and name in {'dropbacks','scrambles'}) or (a['position']=='RB' and name not in {'dropbacks','scrambles'})):_add(a['counts'].setdefault(name,_counter()),eligible,native)
  basis.append(dict(game_id=key[0],team=key[1],play_id=event['play_id'],outcomes=outcomes))
 rows=[]
 for key,a in sorted(actors.items()):
  tm=teams[key[:2]];metrics={}
  if a['position']=='QB':
   db=_result(a['counts'].get('dropbacks',_counter()),tm['dropbacks']);sc=_result(a['counts'].get('scrambles',_counter()),tm['scrambles']);team_db=_result(tm['dropbacks'])
   metrics['G03-M01']=db
   for name,numerator,denominator in [('G03-M07',sc,db),('G03-M10',db,team_db)]:
    n=numerator['exact_within_log_count'];d=denominator['exact_within_log_count'];metrics[name]=dict(numerator=numerator,denominator=denominator,exact_within_log_value=n/d if n is not None and d is not None and d>0 else None)
  else:
   carries=_result(a['counts'].get('official_carries',_counter()),tm['official_carries']);team_carries=_result(tm['official_carries']);n=carries['exact_within_log_count'];d=team_carries['exact_within_log_count']
   metrics['G06-M02']=dict(numerator=carries,full_team_denominator=team_carries,exact_within_log_value=n/d if n is not None and d is not None and d>0 else None)
   for name in RB_SPLITS:metrics[name]=_result(a['counts'].get(name,_counter()),tm[name])
  rows.append({k:deepcopy(v) for k,v in a.items() if k!='counts'}|dict(metrics=metrics))
 result=dict(version=VERSION,before_period=before_period,definitions=deepcopy(DEFINITIONS),actor_game_rows=rows,
  full_team_denominators=[dict(game_id=g,team=t,measurements={m:_result(v) for m,v in values.items()}) for (g,t),values in sorted(teams.items())],
  unattributed_events=missing,identity_review_requests=[dict(game_id=r['game_id'],team=r['team'],source_player_id=r['source_player_id'],reason='Persist unresolved native identity; never name-join') for r in rows if r['player_master_id'] is None],
  source_quality=deepcopy(base['source_quality']),limitations=['Official-inclusive baselines coexist with separately retained nonspike/nonkneel variants',
   'Source-proven historical QB/RB scope; canonical taxonomy maps nativeFB toRB, original proof retained',
   'Physical official dropback union counts each play once, not pass+sack+scramble arithmetic votes','Full-source budgets include unknown canonical actors and unknown native residuals',
   'Observed log exactness is not full-game completeness or original pregame availability','No workload forecast or fantasy-point bonus; caller authenticates source/parent'],forecast=None)
 result['semantic_measurements_sha256']=_hash(dict(result=result,event_basis=basis,identity_component_semantic_sha256=base['semantic_measurements_sha256']))
 result['provenance']=dict(source=deepcopy(evidence['source']),event_receipt_sha256=evidence['sha256'],original_position_evidence=proofs,producer_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),measurement_cutoff_at=str(cutoff))
 return result


def derive_retrospective_official_workload(parent_ref,snapshot,*,position_evidence=(),actual_read_at=None,directory=None):
 from datetime import UTC,datetime
 from .factual_designation import clock
 from .opportunity_source_capture import load_event_artifact
 from .player_opportunity_components import RETROSPECTIVE_USE
 read_at=clock(actual_read_at or datetime.now(UTC));original=clock(parent_ref.get('decision_cutoff_at'));lock=clock(snapshot.slate_lock_at)
 if original is None or lock is None or not original<lock<=read_at<=datetime.now(UTC):raise ValueError('Retrospective reader requires original prelock boundary and actual nonfuture postlock read')
 parent=load_event_artifact(parent_ref,snapshot,before_period=parent_ref['before_period'],cutoff=original,directory=directory)
 result=build_official_workload_components(parent,before_period=parent_ref['before_period'],cutoff=read_at,position_evidence=position_evidence)
 result['underlying_measurements_sha256']=result.pop('semantic_measurements_sha256');result.update(evidence_use=RETROSPECTIVE_USE,pregame_serving_eligible=False)
 result['semantic_measurements_sha256']=_hash(dict(underlying_measurements_sha256=result['underlying_measurements_sha256'],evidence_use=RETROSPECTIVE_USE,pregame_serving_eligible=False))
 result['provenance'].pop('measurement_cutoff_at');result['provenance']['retrospective_read']=dict(original_evidence_boundary_at=original.isoformat(),source_lock_at=lock.isoformat(),actual_read_at=read_at.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),parent_artifact_ref=deepcopy(parent_ref),meaning='Frozen historical byte validation; no new pregame intake/current serving')
 return result
