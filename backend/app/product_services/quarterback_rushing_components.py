"""Scoped QB rushing catalog view over authenticated measured components.

Pure composition, no source fetch, new fit, role inference or count donation.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
from .defense_context_evidence import _hash
from .player_opportunity_components import VERSION as OPPORTUNITY_VERSION
from .player_effectiveness_components import VERSION as EFFECTIVENESS_VERSION

VERSION='quarterback_rushing_components_v1'
COUNTS={'G05-M02':'scrambles','G05-M03':'kneels','G05-M07':'rush_first_downs',
 'G05-M08':'redzone_carries','G05-M09':'inside5_carries','G05-M10':'rush_touchdowns'}
DEFINITIONS={k:dict(source_measure=v,unit='observed_events',scope='Source-proven QB; nonkneel rushing except explicit kneels') for k,v in COUNTS.items()}
DEFINITIONS.update({'G05-M05':dict(source_measure='G07-M01',unit='source_rushing_yards_per_nonkneel_rush',catalog_scope='Explicit nonkneel rate variant'),
 'G05-M06':dict(source_measure='G07-M03',unit='provider_EPA_positive_per_nonkneel_rush',catalog_scope='Explicit provider-EPA success/nonkneel rate variant')})
SOURCE_GAPS={'G05-M01':'Exact designed QB play calls unavailable; nonscramble/other rush is not proof of designed call',
 'G05-M04':'Pressure state unavailable; no scramble-under-pressure denominator can be measured'}


def _key(row):return row['game_id'],row['team'],row['source_player_id']


def _index(rows):
 indexed={}
 for row in rows:
  key=_key(row)
  if key in indexed:raise ValueError('Duplicate native actor-game component')
  indexed[key]=row
 return indexed


def build_quarterback_rushing_components(opportunity,effectiveness,*,before_period):
 if opportunity.get('version')!=OPPORTUNITY_VERSION or effectiveness.get('version')!=EFFECTIVENESS_VERSION:raise ValueError('Measured component version mismatch')
 if opportunity.get('before_period')!=before_period or effectiveness.get('before_period')!=before_period:raise ValueError('Component target period mismatch')
 for field in ('snapshot_id','content_sha256'):
  a=opportunity.get('provenance',{}).get('source',{}).get(field);b=effectiveness.get('provenance',{}).get('source',{}).get(field)
  if not a or a!=b:raise ValueError('Measured components must share authenticated frozen source')
 event_sha=opportunity.get('provenance',{}).get('event_receipt_sha256')
 if not event_sha or event_sha!=effectiveness.get('provenance',{}).get('event_receipt_sha256'):raise ValueError('Measured components must share exact event receipt/scope')
 use=opportunity.get('evidence_use');other_use=effectiveness.get('evidence_use')
 if use!=other_use or opportunity.get('pregame_serving_eligible')!=effectiveness.get('pregame_serving_eligible'):raise ValueError('Component evidence-use mismatch')
 actors=_index(opportunity['actor_game_rows']);effect=_index(effectiveness['actor_game_rows']);rows=[];excluded=[]
 for key,e in sorted(effect.items()):
  parts=key[0].split('_')
  if len(parts)!=4 or int(parts[0])*100+int(parts[1])>=before_period:raise ValueError('Nonprior native game in QB component')
  if e.get('position')!='QB' or e.get('position_status')!='scoped_source_proven':
   excluded.append(dict(game_id=key[0],team=key[1],source_player_id=key[2],reason='Scoped historical QB position unproven or non-QB'));continue
  a=actors.get(key)
  if a is None or a.get('player_master_id')!=e.get('player_master_id'):raise ValueError('QB native/canonical components contradict')
  row={k:deepcopy(e[k]) for k in ('game_id','team','source_player_id','player_master_id','position','position_status')};row['metrics']={}
  unknown=a['unknown_native_attribution_exposures'].get('rusher',0) or a['inherited_team_unknown_eligibility'].get('rush_attempts',0)
  for metric,name in COUNTS.items():
   m=a['metrics'].get(name)
   row['metrics'][metric]=dict(counted_lower_bound=m['observed_outcome_sum'] if m else 0,
    exact_within_log_count=m['exact_within_log_sum'] if m else None if unknown else 0,
    unknown_native_rusher_exposures=a['unknown_native_attribution_exposures'].get('rusher',0),
    unknown_official_rush_eligibility=a['inherited_team_unknown_eligibility'].get('rush_attempts',0),
    unknown_measurement_events=(m['unknown_eligibility_events']+m['unknown_outcome_events']) if m else 0,unit='observed_events')
  for metric,source in [('G05-M05','G07-M01'),('G05-M06','G07-M03')]:
   m=e['metrics'].get(source)
   row['metrics'][metric]=dict(known_attributed_sample_mean=m['known_attributed_sample_mean'] if m else None,
    exact_within_log_mean=m['exact_within_log_mean'] if m else None,
    known_events=m['known_outcome_events'] if m else 0,unit=DEFINITIONS[metric]['unit'])
  support=a['metrics'].get('designed_or_other_nonkneel_rushes')
  row['nonscramble_or_other_support']=dict(exact_within_log_count=support['exact_within_log_sum'] if support else None if unknown else 0,
   meaning='Explicit nonscramble-or-other variant; not exact designed-QB-call catalog metric')
  rows.append(row)
 result=dict(version=VERSION,before_period=before_period,definitions=deepcopy(DEFINITIONS),source_gaps=deepcopy(SOURCE_GAPS),actor_game_rows=rows,
  excluded_unproven_or_nonQB=excluded,full_team_denominators=deepcopy(opportunity['team_denominators']),
  identity_review_requests=deepcopy(opportunity['identity_review_requests']),source_quality=deepcopy(opportunity['source_quality']),
  limitations=['Native game/team/period source-proven historical QB position only; no present workload or availability claim',
   'Observed log count/rate; full-game completeness unproven; unobserved players are not inactive zeros',
   'Designed call and pressure fields remain exact source gaps; no proxy substitution',
   'QB rushing and passing are same player ancestry, not independent fantasy-point bonuses'],forecast=None,
  evidence_use=use,pregame_serving_eligible=False)
 result['semantic_measurements_sha256']=_hash(dict(result=result,opportunity_semantics=opportunity['semantic_measurements_sha256'],effectiveness_semantics=effectiveness['semantic_measurements_sha256']))
 result['provenance']=dict(source=deepcopy(opportunity['provenance']['source']),
  original_opportunity_provenance=deepcopy(opportunity['provenance']),original_effectiveness_provenance=deepcopy(effectiveness['provenance']),
  producer_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),source_authentication='Caller must authenticate both immutable component artifacts and original parent; pure marker is not authentication')
 return result
