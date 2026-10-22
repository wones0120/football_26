"""Observed receiver target-depth partitions, without route/alignment proxies."""
from copy import deepcopy
import hashlib
from pathlib import Path
from .opportunity_events import validate_event_evidence
from .player_opportunity_components import build_player_opportunity_components
from .defense_context_evidence import _number,_hash

VERSION='receiving_depth_components_v1'
BUCKETS=('behind_LOS','short','intermediate','deep','unknown_depth')
DEFINITIONS={
 'G10-M07':dict(bucket='short',definition='0<=native air_yards<10 / all official player targets',unit='target_fraction'),
 'G10-M08':dict(bucket='intermediate',definition='10<=native air_yards<20 / all official player targets',unit='target_fraction'),
 'G10-M09':dict(bucket='deep',definition='native air_yards>=20 / all official player targets',unit='target_fraction')}


def _empty():return dict(known_targets=0,unknown_target_eligibility=0,buckets=dict.fromkeys(BUCKETS,0))


def _add(counter,eligible,depth):
 if eligible is None:counter['unknown_target_eligibility']+=1
 elif eligible:
  counter['known_targets']+=1
  bucket='unknown_depth' if depth is None else 'behind_LOS' if depth<0 else 'short' if depth<10 else 'intermediate' if depth<20 else 'deep'
  counter['buckets'][bucket]+=1


def build_receiving_depth_components(event_receipt,*,before_period,cutoff):
 evidence=validate_event_evidence(event_receipt['event_evidence'],before_period=before_period,cutoff=cutoff)
 base=build_player_opportunity_components(event_receipt,before_period=before_period,cutoff=cutoff)
 identities={(r['game_id'],r['team'],r['source_player_id']):r for r in base['actor_game_rows']}
 teams={};actors={};basis=[]
 for event in sorted(evidence['events'],key=lambda e:(e['game_id'],int(e['play_id']))):
  target=next((o for o in event['opportunities'] if o['channel']=='targets'),None)
  eligible=True if target else None if 'targets' in event['unknown_channels'] else False
  if eligible is False:continue
  key=(event['game_id'],event['team']);depth=_number(event['raw_flags'].get('air_yards'));native=(target or {}).get('source_player_id') or event['raw_flags'].get('receiver_player_id')
  _add(teams.setdefault(key,_empty()),eligible,depth)
  if native:
   native=str(native);actor_key=(*key,native)
   if actor_key not in identities:raise ValueError('Receiver absent from validated native/canonical identity universe')
   _add(actors.setdefault(actor_key,_empty()),eligible,depth)
  basis.append(dict(game_id=key[0],play_id=event['play_id'],team=key[1],native_receiver=native,eligible=eligible,source_air_yards=depth))
 rows=[]
 for key,counts in sorted(actors.items()):
  original=identities[key];row={k:deepcopy(original[k]) for k in ('game_id','team','source_player_id','player_master_id')}
  denominator=original['metrics']['targets']['exact_within_log_sum'];unknown=counts['buckets']['unknown_depth']
  row.update(observed_partition=deepcopy(counts),exact_within_log_target_count=denominator,
   inherited_team_unknown_target_eligibility=original['inherited_team_unknown_eligibility'].get('targets',0),
   unknown_native_receiver_exposures=original['unknown_native_attribution_exposures'].get('receiver',0),metrics={})
  for metric,definition in DEFINITIONS.items():
   n=counts['buckets'][definition['bucket']];exact=denominator is not None and not unknown
   row['metrics'][metric]=dict(known_attributed_bucket_count=n,exact_within_log_bucket_count=n if exact else None,
    full_player_target_denominator=denominator,unknown_depth_targets=unknown,
    exact_within_log_share=n/denominator if exact and denominator>0 else None,
    known_depth_attributed_sample_share=n/(counts['known_targets']-unknown) if counts['known_targets']>unknown else None,
    unit='target_fraction')
  rows.append(row)
 result=dict(version=VERSION,before_period=before_period,definitions=deepcopy(DEFINITIONS),actor_game_rows=rows,
  full_team_denominators=[dict(game_id=g,team=t,**v) for (g,t),v in sorted(teams.items())],
  identity_review_requests=deepcopy(base['identity_review_requests']),unattributed_events=deepcopy(base['unattributed_events']),source_quality=deepcopy(base['source_quality']),
  limitations=['Depth is source signed air yards, not route/alignment/catchability/screen/contested-target classification',
   'Behind-LOS is its own partition, never silently reassigned to short or screen',
   'Shares use all official player targets; known-depth sample shares are separate and cannot stand in for exact shares',
   'Missing target eligibility/native identity/depth preserves unknown exactness and full-team universe',
   'Observed log completeness and original pregame availability remain unverified; caller authenticates immutable parent'],forecast=None)
 result['semantic_measurements_sha256']=_hash(dict(result=result,event_basis=basis,identity_component_semantic_sha256=base['semantic_measurements_sha256']))
 result['provenance']=dict(source=deepcopy(evidence['source']),event_receipt_sha256=evidence['sha256'],producer_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),measurement_cutoff_at=str(cutoff))
 return result


def derive_retrospective_receiving_depth(parent_ref,snapshot,*,actual_read_at=None,directory=None):
 from datetime import UTC,datetime
 from .factual_designation import clock
 from .opportunity_source_capture import load_event_artifact
 from .player_opportunity_components import RETROSPECTIVE_USE
 read_at=clock(actual_read_at or datetime.now(UTC));original=clock(parent_ref.get('decision_cutoff_at'));lock=clock(snapshot.slate_lock_at)
 if original is None or lock is None or not original<lock<=read_at<=datetime.now(UTC):raise ValueError('Retrospective reader requires original prelock boundary and actual nonfuture postlock read')
 parent=load_event_artifact(parent_ref,snapshot,before_period=parent_ref['before_period'],cutoff=original,directory=directory)
 result=build_receiving_depth_components(parent,before_period=parent_ref['before_period'],cutoff=read_at)
 result['underlying_measurements_sha256']=result.pop('semantic_measurements_sha256');result.update(evidence_use=RETROSPECTIVE_USE,pregame_serving_eligible=False)
 result['semantic_measurements_sha256']=_hash(dict(underlying_measurements_sha256=result['underlying_measurements_sha256'],evidence_use=RETROSPECTIVE_USE,pregame_serving_eligible=False))
 result['provenance'].pop('measurement_cutoff_at');result['provenance']['retrospective_read']=dict(original_evidence_boundary_at=original.isoformat(),source_lock_at=lock.isoformat(),actual_read_at=read_at.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),parent_artifact_ref=deepcopy(parent_ref),meaning='Frozen historical byte validation; no new pregame intake/current serving')
 return result
