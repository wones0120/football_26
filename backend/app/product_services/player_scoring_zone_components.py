"""Prior observed official opportunities in disjoint preplay field-position zones.

No summed passer+receiver opportunity or invented goal-to-go probability.
Caller must authenticate the immutable source/event parent before consumption.
"""
from copy import deepcopy
import hashlib
from pathlib import Path
from .opportunity_events import validate_event_evidence
from .player_opportunity_components import build_player_opportunity_components
from .defense_context_evidence import _hash

VERSION='player_scoring_zone_components_v1'
CHANNELS={'rush_attempts':('rusher','rusher_player_id','official_rush_attempts'),
          'targets':('receiver','receiver_player_id','targets'),
          'pass_attempts':('passer','passer_player_id','official_pass_attempts')}
ZONES=('outside20','six_to_twenty','inside5')
DEFINITIONS={}
for start,channel in ((1,'rush_attempts'),(4,'targets'),(7,'pass_attempts')):
 for offset,zone in enumerate(ZONES):
  DEFINITIONS[f'G11-M{start+offset:02}']=dict(channel=channel,zone=zone,unit='official_observed_events',
   definition='Official channel eligibility; preplay yardline_100 >20, >5 through20, or0 through5; rush includes kneels, pass includes spikes')
DEFINITIONS['G11-M10']=dict(unit='channel_specific_player_fraction_of_team_GTG_events',
 definition='Separate official rush/pass/target shares on source goal_to_go=True; no cross-channel sum',
 catalog_scope='Declared channel-specific variant; no unique composite opportunity denominator is asserted')


def _counter():return dict(counted_lower_bound=0,unknown_eligibility_events=0,unattributed_eligible_events=0)


def _add(counter,eligible,*,unattributed=False):
 if eligible is None:counter['unknown_eligibility_events']+=1
 elif eligible:
  counter['counted_lower_bound']+=1
  if unattributed:counter['unattributed_eligible_events']+=1


def _and(a,b):return False if a is False or b is False else None if a is None or b is None else True


def _finish(counter,*,actor=False,team=None):
 value=deepcopy(counter)
 unknown=counter['unknown_eligibility_events']
 missing_native=(team or counter)['unattributed_eligible_events'] if actor else 0
 value['exact_within_log_count']=None if unknown or missing_native else counter['counted_lower_bound']
 value['exactness_scope']='Observed source log only; full-game completion not certified'
 if actor:value['inherited_unattributed_eligible_events']=missing_native
 return value


def build_player_scoring_zone_components(event_receipt,*,before_period,cutoff,position_evidence=()):
 evidence=validate_event_evidence(event_receipt['event_evidence'],before_period=before_period,cutoff=cutoff)
 base=build_player_opportunity_components(event_receipt,before_period=before_period,cutoff=cutoff,position_evidence=position_evidence)
 identities={(r['game_id'],r['team'],r['source_player_id']):r for r in base['actor_game_rows']}
 teams={};actors={};basis=[]
 for event in sorted(evidence['events'],key=lambda e:(e['game_id'],int(e['play_id']))):
  teamkey=(event['game_id'],event['team']);tm=teams.setdefault(teamkey,{})
  opportunities={o['channel']:o for o in event['opportunities']}
  for channel,(role,native_field,_) in CHANNELS.items():
   eligibility=True if channel in opportunities else None if channel in event['unknown_channels'] else False
   if eligibility is False:continue
   native=(opportunities.get(channel) or {}).get('source_player_id') or event['raw_flags'].get(native_field)
   native=str(native) if native else None
   outcomes={zone:_and(eligibility,None if event['zone']=='unknown' else event['zone']==zone) for zone in ZONES}
   outcomes['goal_to_go']=_and(eligibility,event['goal_to_go'])
   outcomes['all_official']=eligibility
   outcomes['unknown_zone']=_and(eligibility,event['zone']=='unknown')
   for zone,eligible in outcomes.items():_add(tm.setdefault((channel,zone),_counter()),eligible,unattributed=native is None)
   if native:
    actor_key=(*teamkey,native)
    if actor_key not in identities:raise ValueError('Native zone actor absent from validated identity universe')
    am=actors.setdefault(actor_key,{})
    for zone,eligible in outcomes.items():_add(am.setdefault((channel,zone),_counter()),eligible)
   basis.append(dict(game_id=teamkey[0],play_id=event['play_id'],team=teamkey[1],channel=channel,source_player_id=native,outcomes=outcomes))
 team_rows=[]
 for (game,team),metrics in sorted(teams.items()):
  channels={c:{z:_finish(metrics.get((c,z),_counter())) for z in (*ZONES,'goal_to_go','all_official','unknown_zone')} for c in CHANNELS}
  # Channels with no recorded exposure are known zero only within this observed log.
  team_rows.append(dict(game_id=game,team=team,channels=channels))
 actor_rows=[]
 for key,metrics in sorted(actors.items()):
  original=identities[key];row={k:deepcopy(original[k]) for k in ('game_id','team','source_player_id','player_master_id','position','position_status')}
  row['metrics']={};row['goal_to_go_channel_shares']={};row['channel_coverage']={}
  for channel in CHANNELS:
   if not any(c==channel for c,_ in metrics):continue
   row['channel_coverage'][channel]={}
   for category in ('all_official','unknown_zone'):
    summary=deepcopy(metrics.get((channel,category),_counter()));team_summary=teams[key[:2]].get((channel,category),_counter())
    summary['unknown_eligibility_events']=max(summary['unknown_eligibility_events'],team_summary['unknown_eligibility_events'])
    row['channel_coverage'][channel][category]=_finish(summary,actor=True,team=team_summary)
   for metric,definition in DEFINITIONS.items():
    if definition.get('channel')!=channel:continue
    zone=definition['zone'];counter=deepcopy(metrics.get((channel,zone),_counter()));team_counter=teams[key[:2]].get((channel,zone),_counter())
    # Unknown channel/zone eligibility may belong to this actor even when its native ID is absent.
    counter['unknown_eligibility_events']=max(counter['unknown_eligibility_events'],team_counter['unknown_eligibility_events'])
    row['metrics'][metric]=_finish(counter,actor=True,team=team_counter)
   counter=deepcopy(metrics.get((channel,'goal_to_go'),_counter()));team_counter=teams[key[:2]].get((channel,'goal_to_go'),_counter())
   counter['unknown_eligibility_events']=max(counter['unknown_eligibility_events'],team_counter['unknown_eligibility_events'])
   numerator=_finish(counter,actor=True,team=team_counter);denominator=_finish(team_counter)
   n=numerator['exact_within_log_count'];d=denominator['exact_within_log_count']
   row['goal_to_go_channel_shares'][channel]=dict(numerator=numerator,full_team_denominator=denominator,
    exact_within_log_share=n/d if n is not None and d is not None and d>0 else None,zero_denominator=d==0)
  actor_rows.append(row)
 result=dict(version=VERSION,before_period=before_period,definitions=deepcopy(DEFINITIONS),actor_game_rows=actor_rows,
  full_team_denominators=team_rows,identity_review_requests=deepcopy(base['identity_review_requests']),
  unattributed_events=deepcopy(base['unattributed_events']),source_quality=deepcopy(base['source_quality']),
  limitations=['Official rush includes kneels and official pass includes spikes; nonkneel variants live separately',
   'Zone is preplay line of scrimmage, not target catch location','Known zero requires observed eligibility; unknown native actors remain in full team denominator',
   'G11-M10 channel-specific shares only: pass and receiver target can describe the same physical play and must not be summed',
   'Prior observed log is not certified complete game; checksum alone does not authenticate source intake'],forecast=None)
 result['semantic_measurements_sha256']=_hash(dict(result=result,event_basis=basis,identity_component_semantic_sha256=base['semantic_measurements_sha256']))
 result['provenance']=dict(source=deepcopy(evidence['source']),event_receipt_sha256=evidence['sha256'],producer_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),measurement_cutoff_at=str(cutoff))
 return result


def derive_retrospective_player_scoring_zones(parent_ref,snapshot,*,actual_read_at=None,directory=None):
 """Revalidate frozen historical bytes, preserving actual postlock publication."""
 from datetime import UTC,datetime
 from .factual_designation import clock
 from .opportunity_source_capture import load_event_artifact
 from .player_opportunity_components import RETROSPECTIVE_USE
 read_at=clock(actual_read_at or datetime.now(UTC));original=clock(parent_ref.get('decision_cutoff_at'));lock=clock(snapshot.slate_lock_at)
 if original is None or lock is None or not original<lock<=read_at<=datetime.now(UTC):raise ValueError('Retrospective reader requires original prelock boundary and actual nonfuture postlock read')
 parent=load_event_artifact(parent_ref,snapshot,before_period=parent_ref['before_period'],cutoff=original,directory=directory)
 result=build_player_scoring_zone_components(parent,before_period=parent_ref['before_period'],cutoff=read_at)
 result['underlying_measurements_sha256']=result.pop('semantic_measurements_sha256')
 result.update(evidence_use=RETROSPECTIVE_USE,pregame_serving_eligible=False)
 result['semantic_measurements_sha256']=_hash(dict(underlying_measurements_sha256=result['underlying_measurements_sha256'],evidence_use=RETROSPECTIVE_USE,pregame_serving_eligible=False))
 result['provenance'].pop('measurement_cutoff_at')
 result['provenance']['retrospective_read']=dict(original_evidence_boundary_at=original.isoformat(),source_lock_at=lock.isoformat(),actual_read_at=read_at.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),parent_artifact_ref=deepcopy(parent_ref),meaning='Frozen historical byte validation; no new pregame intake/current serving')
 return result
