"""Source-measured player effectiveness; no routes/contact proxies or FP bonus.

Caller authenticates immutable event/source bytes. Means over known attributed
samples remain distinct from complete within-log rates and full-game coverage.
"""
from copy import deepcopy
import hashlib
from pathlib import Path

from .opportunity_events import validate_event_evidence,_flag
from .defense_context_evidence import _eligibility,_number,_metric,_finish,_hash
from .environment_context_evidence import _and
from .player_opportunity_components import build_player_opportunity_components

VERSION='player_effectiveness_components_v1'
DEFINITIONS={
 'G04-M01':dict(role='passer',variant='official_completion_fraction_including_spikes',unit='completions_per_official_attempt'),
 'G04-M02':dict(role='passer',variant='provider_cpoe_nonspike_official_attempt',unit='provider_percentage_points'),
 'G04-M03':dict(role='passer',variant='source_passing_yards_per_official_attempt',unit='passing_yards_per_attempt'),
 'G04-M04':dict(role='passer',variant='source_air_yards_per_nonspike_official_attempt',unit='signed_air_yards_per_attempt'),
 'G04-M05':dict(role='passer',variant='source_passing_yards_per_proven_completion',unit='passing_yards_per_completion'),
 'G04-M06':dict(role='passer',variant='source_epa_per_nonspike_reported_dropback_including_sacks_scrambles',unit='provider_expected_points_per_dropback'),
 'G04-M07':dict(role='passer',variant='source_epa_positive_per_nonspike_reported_dropback',unit='observed_success_fraction'),
 'G04-M08':dict(role='passer',variant='interception_per_official_attempt',unit='observed_interception_fraction'),
 'G04-M09':dict(role='passer',variant='sack_per_nonspike_reported_dropback',unit='observed_sack_fraction'),
 'G04-M10':dict(role='passer',variant='passing_touchdown_per_official_attempt',unit='observed_passing_td_fraction'),
 'G07-M01':dict(role='rusher',variant='source_rushing_yards_per_nonkneel_official_rush',unit='rushing_yards_per_rush'),
 'G07-M02':dict(role='rusher',variant='source_epa_per_nonkneel_official_rush',unit='provider_expected_points_per_rush'),
 'G07-M03':dict(role='rusher',variant='source_epa_positive_per_nonkneel_official_rush',unit='observed_success_fraction'),
 'G07-M04':dict(role='rusher',variant='source_play_net10_per_nonkneel_official_rush',unit='observed_explosive_run_fraction'),
 'G07-M05':dict(role='rusher',variant='source_play_net_le0_per_nonkneel_official_rush',unit='observed_stuffed_run_fraction'),
 'G07-M06':dict(role='rusher',variant='first_down_rush_or_rush_td_per_nonkneel_official_rush',unit='observed_first_down_conversion_fraction'),
 'G09-M01':dict(role='receiver',variant='completion_per_official_attributed_target',unit='observed_catch_fraction'),
 'G09-M02':dict(role='receiver',variant='provider_completion_oe_per_attributed_nonspike_target',unit='provider_percentage_points',catalog_status='partial_completion_expectation_variant_not_independent_catchability'),
 'G09-M03':dict(role='receiver',variant='source_receiving_yards_per_official_attributed_target',unit='receiving_yards_per_target'),
 'G09-M04':dict(role='receiver',variant='source_receiving_yards_per_proven_completion',unit='receiving_yards_per_reception'),
 'G09-M06':dict(role='receiver',variant='source_play_epa_per_official_attributed_target',unit='provider_expected_points_per_target'),
 'G09-M07':dict(role='receiver',variant='source_play_epa_positive_per_official_attributed_target',unit='observed_success_fraction'),
 'G09-M08':dict(role='receiver',variant='source_yac_per_proven_completion',unit='signed_yards_after_catch_per_reception'),
 'G09-M10':dict(role='receiver',variant='source_receiving_net20_per_proven_completion',unit='observed_explosive_reception_fraction'),
}
SOURCE_GAPS={'G07-M07':'yards before contact unavailable','G07-M08':'yards after contact unavailable','G07-M09':'missed tackles forced unavailable','G07-M10':'rushing yards over expectation unavailable',
 'G09-M05':'routes unavailable; no yards/route substitute','G09-M09':'drops/catchable-target denominator unavailable'}


def _binary(value):
 flag=_flag(value)
 return None if flag is None else float(flag)


def _yards(raw,field):
 value=_number(raw.get(field));completed=_flag(raw.get('complete_pass'))
 if completed is False:
  if value not in (None,0.):raise ValueError('Incomplete pass conflicts with nonzero source passing/receiving yards')
  return 0.
 return value


def _success(value):return None if value is None else float(value>0)


def _record(metric,eligible,value):
 if eligible is None:metric['unknown_eligibility_events']+=1
 elif eligible:
  metric['eligible_events']+=1
  if value is None:metric['unknown_outcome_events']+=1
  else:metric['known_outcome_events']+=1;metric['observed_outcome_sum']+=value


def build_player_effectiveness_components(event_receipt,*,before_period,cutoff,position_evidence=()):
 position_evidence=deepcopy(list(position_evidence))
 evidence=validate_event_evidence(event_receipt['event_evidence'],before_period=before_period,cutoff=cutoff)
 base=build_player_opportunity_components(event_receipt,before_period=before_period,cutoff=cutoff,position_evidence=position_evidence)
 actors={(a['game_id'],a['team'],a['source_player_id']):{k:deepcopy(v) for k,v in a.items() if k not in {'metrics','shares'}} for a in base['actor_game_rows']}
 for actor in actors.values():actor['metrics']={}
 basis=[]
 for event in sorted(evidence['events'],key=lambda e:(e['game_id'],int(e['play_id']))):
  raw=event['raw_flags'];channels={o['channel'] for o in event['opportunities']}
  passing,dropback,rushing=_eligibility(event)
  official=True if 'pass_attempts' in channels else None if 'pass_attempts' in event['unknown_channels'] else False
  target=True if 'targets' in channels else None if 'targets' in event['unknown_channels'] else False
  completion=_flag(raw.get('complete_pass'));pass_complete=_and(official,completion);reception=_and(target,completion)
  epa=_number(raw.get('epa'));cpoe=_number(raw.get('cpoe'))
  if cpoe is not None and not -100<=cpoe<=100:raise ValueError('Source CPOE outside physical percentage-point range')
  py=_yards(raw,'passing_yards') if official is not False else None
  ry=_yards(raw,'receiving_yards') if target is not False else None
  rushing_yards=_number(raw.get('rushing_yards'));net=_number(raw.get('yards_gained'))
  first=_flag(raw.get('first_down_rush'));td=_flag(raw.get('rush_touchdown'))
  converted=True if first is True or td is True else False if first is False and td is False else None
  passer=raw.get('passer_player_id') or (raw.get('rusher_player_id') if _flag(raw.get('qb_scramble')) is True else None)
  groups=[('passer',passer,{
   'G04-M01':(official,_binary(raw.get('complete_pass'))),'G04-M02':(passing,cpoe),'G04-M03':(official,py),
   'G04-M04':(passing,_number(raw.get('air_yards'))),'G04-M05':(pass_complete,py),'G04-M06':(dropback,epa),
   'G04-M07':(dropback,_success(epa)),'G04-M08':(official,_binary(raw.get('interception'))),
   'G04-M09':(dropback,_binary(raw.get('sack'))),'G04-M10':(official,_binary(raw.get('pass_touchdown')))}),
   ('rusher',raw.get('rusher_player_id'),{
   'G07-M01':(rushing,rushing_yards),'G07-M02':(rushing,epa),'G07-M03':(rushing,_success(epa)),
   'G07-M04':(rushing,None if net is None else float(net>=10)),'G07-M05':(rushing,None if net is None else float(net<=0)),
   'G07-M06':(rushing,None if converted is None else float(converted))}),
   ('receiver',raw.get('receiver_player_id'),{
   'G09-M01':(target,_binary(raw.get('complete_pass'))),'G09-M02':(_and(target,passing),cpoe),'G09-M03':(target,ry),
   'G09-M04':(reception,ry),'G09-M06':(target,epa),'G09-M07':(target,_success(epa)),
   'G09-M08':(reception,_number(raw.get('yards_after_catch'))),'G09-M10':(reception,None if ry is None else float(ry>=20))})]
  for role,native,outcomes in groups:
   if not native:continue
   key=(event['game_id'],event['team'],str(native));actor=actors.get(key)
   if actor is None:continue
   for metric,(eligible,value) in outcomes.items():
    if eligible is False:continue
    _record(actor['metrics'].setdefault(metric,_metric()),eligible,value)
   basis.append(dict(game_id=event['game_id'],play_id=event['play_id'],team=event['team'],source_player_id=str(native),role=role,outcomes=outcomes))
 rows=[]
 for _,actor in sorted(actors.items()):
  finished={}
  for metric,value in actor['metrics'].items():
   measured=_finish(value);role=DEFINITIONS[metric]['role'];channel={'passer':'pass_attempts','rusher':'rush_attempts','receiver':'targets'}[role]
   unknown=(actor['unknown_native_attribution_exposures'].get(role) or actor['inherited_team_unknown_eligibility'].get(channel))
   measured['known_attributed_sample_mean']=measured['observed_known_mean']
   measured['exact_within_log_mean']=measured['all_eligible_mean'] if not unknown else None
   measured['unit']=DEFINITIONS[metric]['unit']
   measured['catalog_scope_status']=('source_proven_QB' if actor['position']=='QB' else 'unknown_QB_scope_generic_passer_support' if actor['position'] is None else 'non_QB_generic_passer_support') if metric.startswith('G04-') else 'source_measured_actor_role'
   finished[metric]=measured
  actor['metrics']=finished
  if finished:rows.append(actor)
 result=dict(version=VERSION,before_period=before_period,definitions=deepcopy(DEFINITIONS),actor_game_rows=rows,
  team_denominators=deepcopy(base['team_denominators']),identity_review_requests=deepcopy(base['identity_review_requests']),
  unattributed_events=deepcopy(base['unattributed_events']),source_quality=deepcopy(base['source_quality']),official_reconciliation=deepcopy(base['official_reconciliation']),source_gaps=deepcopy(SOURCE_GAPS),
  limitations=['Verified immutable parent/source intake required; checksum alone is not source authentication','Observed logs, full-game coverage/original pregame availability unproven',
   'G04 QB interpretation requires scoped QB position proof; generic passer identity alone is not QB proof','Receiver CPOE is same-event vendor completion expectation, not independent catchability or a second scoring effect',
   'Passing/rushing/receiving EPA share physical play ancestry; no additive fantasy-point bonus or probability','No route/contact/pressure/drop/RYOE proxy substitution'],forecast=None)
 result['semantic_measurements_sha256']=_hash(dict(result=result,event_basis=basis))
 result['provenance']=dict(source=deepcopy(evidence['source']),event_receipt_sha256=evidence['sha256'],original_position_evidence=deepcopy(list(position_evidence)),
  measurement_cutoff_at=str(cutoff),identity_component_semantic_sha256=base['semantic_measurements_sha256'],producer_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
 return result



def derive_retrospective_player_effectiveness(parent_ref,snapshot,*,actual_read_at=None,directory=None,position_evidence=()):
 """Offline frozen-parent revalidation; actual postlock clocks remain actual."""
 from datetime import UTC,datetime
 from .factual_designation import clock
 from .opportunity_source_capture import load_event_artifact
 from .player_opportunity_components import RETROSPECTIVE_USE
 read_at=clock(actual_read_at or datetime.now(UTC));original=clock(parent_ref.get('decision_cutoff_at'));lock=clock(snapshot.slate_lock_at)
 if original is None or lock is None or not original<lock<=read_at<=datetime.now(UTC):raise ValueError('Retrospective reader requires original prelock boundary and actual nonfuture postlock read')
 parent=load_event_artifact(parent_ref,snapshot,before_period=parent_ref['before_period'],cutoff=original,directory=directory)
 result=build_player_effectiveness_components(parent,before_period=parent_ref['before_period'],cutoff=read_at,position_evidence=position_evidence)
 result['underlying_measurements_sha256']=result.pop('semantic_measurements_sha256')
 result.update(evidence_use=RETROSPECTIVE_USE,pregame_serving_eligible=False)
 result['semantic_measurements_sha256']=_hash(dict(underlying_measurements_sha256=result['underlying_measurements_sha256'],evidence_use=RETROSPECTIVE_USE,pregame_serving_eligible=False))
 result['provenance'].pop('measurement_cutoff_at')
 result['provenance']['retrospective_read']=dict(original_evidence_boundary_at=original.isoformat(),source_lock_at=lock.isoformat(),actual_read_at=read_at.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),parent_artifact_ref=deepcopy(parent_ref),meaning='Frozen historical byte validation only; no new pregame intake or current-serving eligibility')
 return result
