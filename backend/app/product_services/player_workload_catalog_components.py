"""Catalog views of authenticated observed workloads; no forecast or role guess."""
from copy import deepcopy
from pathlib import Path
import hashlib
from .defense_context_evidence import _hash
from .player_opportunity_components import VERSION as OPPORTUNITY_VERSION
from .player_effectiveness_components import VERSION as EFFECTIVENESS_VERSION
from .quarterback_rushing_components import _index

VERSION='player_workload_catalog_components_v1'
QB_COUNTS={'G03-M01':'nonspike_dropbacks','G03-M02':'official_pass_attempts','G03-M03':'completions','G03-M04':'sacks','G03-M06':'spikes'}
RB_COUNTS={'G06-M01':'official_rush_attempts','G06-M03':'early_down_carries','G06-M04':'third_down_carries','G06-M05':'short_yard_carries','G06-M06':'two_minute_carries','G06-M07':'first_half_carries','G06-M08':'fourth_quarter_carries','G06-M09':'leading_carries','G06-M10':'trailing_carries'}
DEFINITIONS={k:dict(source_measure=v,unit='observed_events') for k,v in {**QB_COUNTS,**RB_COUNTS,'G08-M01':'targets','G08-M07':'air_yards'}.items()}
DEFINITIONS['G08-M07']['unit']='signed_air_yards'
DEFINITIONS.update({'G03-M07':dict(definition='Native QB scrambles / source-reported nonspike dropbacks',unit='observed_fraction'),
 'G03-M10':dict(definition='QB source-reported nonspike dropbacks / all team native nonspike dropbacks',unit='observed_fraction'),
 'G06-M02':dict(definition='RB nonkneel carries / full-source team nonkneel carries including QB rushes',unit='observed_fraction'),
 'G08-M02':dict(definition='Native receiver targets / all full-source team official targets',unit='observed_fraction'),
 'G08-M08':dict(definition='Native receiver signed air yards / full-source team signed air yards; may be negative or exceed1',unit='signed_yard_ratio'),
 'G08-M09':dict(definition='Native receiver signed air yards / all official player targets',unit='signed_yards_per_target')})
SOURCE_GAPS={'G03-M05':'Exact throwaway tag not supplied; absent receiver is not proof of throwaway',
 'G03-M08':'Exact designed rollout not supplied','G03-M09':'Exact play-action tag not supplied',
 'G08-M03':'Routes not supplied','G08-M04':'Route participation denominator not supplied','G08-M05':'Routes not supplied',
 'G08-M06':'First-read tag not supplied','G08-M10':'Catchability tag/denominator not supplied'}


def _ratio(n,d):return n/d if n is not None and d is not None and d!=0 else None


def _count(actor,name,channel,role):
 value=actor['metrics'].get(name);unknown=actor['inherited_team_unknown_eligibility'].get(channel,0) or actor['unknown_native_attribution_exposures'].get(role,0)
 return dict(counted_lower_bound=(value['observed_outcome_sum'] or 0) if value else 0,
  exact_within_log_sum=value['exact_within_log_sum'] if value else None if unknown else 0,
  unknown_measurement_events=value['unknown_eligibility_events']+value['unknown_outcome_events'] if value else 0,
  inherited_team_unknown_eligibility=actor['inherited_team_unknown_eligibility'].get(channel,0),
  unknown_native_attribution_exposures=actor['unknown_native_attribution_exposures'].get(role,0))


def build_player_workload_catalog_components(opportunity,effectiveness,*,before_period):
 if opportunity.get('version')!=OPPORTUNITY_VERSION or effectiveness.get('version')!=EFFECTIVENESS_VERSION:raise ValueError('Component version mismatch')
 if opportunity.get('before_period')!=before_period or effectiveness.get('before_period')!=before_period:raise ValueError('Component target period mismatch')
 for field in ('snapshot_id','content_sha256','event_receipt_sha256'):
  a=opportunity.get('provenance',{});b=effectiveness.get('provenance',{})
  if field!='event_receipt_sha256':a=a.get('source',{});b=b.get('source',{})
  if not a.get(field) or a[field]!=b.get(field):raise ValueError('Frozen source/event scope mismatch')
 if opportunity.get('evidence_use')!=effectiveness.get('evidence_use') or opportunity.get('pregame_serving_eligible')!=effectiveness.get('pregame_serving_eligible'):raise ValueError('Evidence use mismatch')
 actors=_index(opportunity['actor_game_rows']);effect=_index(effectiveness['actor_game_rows']);team_dropbacks={};unknown_passers={(r['game_id'],r['team']) for r in opportunity['unattributed_events'] if r['role']=='passer'}
 for key,actor in actors.items():
  parts=key[0].split('_')
  if len(parts)!=4 or int(parts[0])*100+int(parts[1])>=before_period:raise ValueError('Nonprior native game')
  if key in effect and actor.get('player_master_id')!=effect[key].get('player_master_id'):raise ValueError('Native/canonical components contradict')
  metric=actor['metrics'].get('nonspike_dropbacks')
  if metric is not None:team_dropbacks.setdefault(key[:2],[]).append(metric['exact_within_log_sum'])
 denominators={key:None if key in unknown_passers or any(v is None for v in values) else sum(values) for key,values in team_dropbacks.items()}
 rows=[]
 for key,actor in sorted(actors.items()):
  e=effect.get(key);position=e.get('position') if e and e.get('position_status')=='scoped_source_proven' else None
  row={k:deepcopy(actor[k]) for k in ('game_id','team','source_player_id','player_master_id')};row.update(position=position,position_status='scoped_source_proven' if position else 'unknown',metrics={})
  if position=='QB':
   for metric,name in QB_COUNTS.items():row['metrics'][metric]=_count(actor,name,'pass_attempts','passer')
   scramble=_count(actor,'scrambles_per_dropback','pass_attempts','passer');dropback=_count(actor,'nonspike_dropbacks','pass_attempts','passer')
   row['metrics']['G03-M07']=dict(numerator=scramble,denominator=dropback,exact_within_log_value=_ratio(scramble['exact_within_log_sum'],dropback['exact_within_log_sum']))
   row['metrics']['G03-M10']=dict(numerator=dropback,full_team_denominator=denominators.get(key[:2]),exact_within_log_value=_ratio(dropback['exact_within_log_sum'],denominators.get(key[:2])))
  if position=='RB':
   for metric,name in RB_COUNTS.items():row['metrics'][metric]=_count(actor,name,'rush_attempts','rusher')
   row['metrics']['G06-M02']=dict(exact_within_log_value=actor['shares']['nonkneel_carry_share'],denominator_scope='All team nonkneel official rushes, including QB and unresolved canonical actors')
  if 'targets' in actor['metrics']:
   for metric,name in [('G08-M01','targets'),('G08-M07','air_yards')]:row['metrics'][metric]=_count(actor,name,'targets','receiver')
   for metric,name in [('G08-M02','target_share'),('G08-M08','signed_air_yard_share'),('G08-M09','average_target_depth')]:row['metrics'][metric]=dict(exact_within_log_value=actor['shares'][name])
  if row['metrics']:rows.append(row)
 result=dict(version=VERSION,before_period=before_period,definitions=deepcopy(DEFINITIONS),source_gaps=deepcopy(SOURCE_GAPS),actor_game_rows=rows,
  full_team_denominators=deepcopy(opportunity['team_denominators']),full_team_nonspike_dropbacks=[dict(game_id=g,team=t,exact_within_log_count=n) for (g,t),n in sorted(denominators.items())],
  identity_review_requests=deepcopy(opportunity['identity_review_requests']),source_quality=deepcopy(opportunity['source_quality']),
  evidence_use=opportunity.get('evidence_use'),pregame_serving_eligible=False,forecast=None,
  limitations=['Historical source-proven QB/RB scope only; canonical taxonomy maps sourceFB toRB, original position proof retained',
   'Source-reported dropbacks exclude spikes; scramble is included once, not added to dropback total',
   'RB official carries include kneels; carryshare and contextual splits explicitly nonkneel',
   'Two-minute carries mean native Q2/Q4 halfclock<=120; lead/trail uses preplay score differential',
   'Signed air ratios may be negative or exceed1; never interpreted as probabilities',
   'Observed logs only, no complete-game or original pregame availability claim; caller authenticates both immutable inputs'])
 result['semantic_measurements_sha256']=_hash(dict(result=result,opportunity_semantics=opportunity['semantic_measurements_sha256'],effectiveness_semantics=effectiveness['semantic_measurements_sha256']))
 result['provenance']=dict(source=deepcopy(opportunity['provenance']['source']),original_opportunity_provenance=deepcopy(opportunity['provenance']),original_effectiveness_provenance=deepcopy(effectiveness['provenance']),producer_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
 return result
