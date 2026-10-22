"""Catalog-specific receiving rates over exact source-measured exposures."""
from copy import deepcopy
from uuid import UUID
import math
from .evaluation_record import digest
from .market_snapshots import canonical_team

VERSION='receiving_effectiveness_catalog_v1'
DEFINITIONS={'G09-M06':('source_play_epa_per_official_attributed_target','provider_expected_points_per_target'),
 'G09-M07':('source_play_epa_positive_per_official_attributed_target','observed_success_fraction'),
 'G09-M08':('source_yac_per_proven_completion','signed_yards_after_catch_per_reception'),
 'G09-M10':('source_receiving_net20_per_proven_completion','observed_explosive_reception_fraction')}

def build_receiving_effectiveness_catalog(source,*,before_period):
 if source.get('version')!='player_effectiveness_components_v1' or source.get('before_period')!=before_period or source.get('pregame_serving_eligible') is not False or source.get('evidence_use')!='postlock_descriptive_not_pregame_or_serving':raise ValueError('Exact nonserving measured source scope required')
 if type(before_period)is not int or not 200001<=before_period or not 1<=before_period%100<=18:raise ValueError('Explicit REG period required')
 for mid,(variant,unit) in DEFINITIONS.items():
  if source['definitions'][mid]['variant']!=variant or source['definitions'][mid]['unit']!=unit:raise ValueError('Source measured definition differs')
 rows=[];seen=set();canonical={}
 for src in source['actor_game_rows']:
  if not any(mid in src['metrics'] for mid in DEFINITIONS):continue
  gid=src['game_id'];parts=gid.split('_');team=canonical_team(src['team']);native=src['source_player_id'];pid=src['player_master_id']
  if len(parts)!=4 or not parts[0].isdigit() or not parts[1].isdigit() or not 1<=int(parts[1])<=18 or int(parts[0])*100+int(parts[1])>=before_period or team not in {canonical_team(t) for t in parts[2:]} or not isinstance(native,str) or not native:raise ValueError('Prior native receiver scope required')
  key=(gid,team,native)
  if key in seen:raise ValueError('Duplicate native actor/game')
  seen.add(key)
  if pid is not None:
   if str(UUID(str(pid)))!=pid:raise ValueError('Canonical UUID spelling required')
   ck=(gid,pid)
   if ck in canonical and canonical[ck]!=key:raise ValueError('Canonical native actor collision')
   canonical[ck]=key
  native_unknown=src['unknown_native_attribution_exposures'].get('receiver',0);elig_unknown=src['inherited_team_unknown_eligibility'].get('targets',0);metrics={}
  for mid in DEFINITIONS:
   m=src['metrics'].get(mid)
   if m is None:continue
   m=deepcopy(m)
   for field in ('eligible_events','known_outcome_events','unknown_outcome_events','unknown_eligibility_events'):
    v=m[field]
    if type(v) not in {int,float} or not math.isfinite(v) or v<0 or int(v)!=v:raise ValueError('Nonnegative native count required')
   if m['known_outcome_events']+m['unknown_outcome_events']!=m['eligible_events']:raise ValueError('Known/unknown receiver exposure mismatch')
   total=m['observed_outcome_sum'];known=m['known_outcome_events'];den=m['eligible_events']
   if total is not None and (type(total) not in {int,float} or not math.isfinite(total)):raise ValueError('Nonfinite measured outcome')
   if mid in {'G09-M07','G09-M10'} and total is not None and not 0<=total<=known:raise ValueError('Binary outcome exceeds known exposure')
   exact=total/den if total is not None and den and not(native_unknown or elig_unknown or m['unknown_outcome_events'] or m['unknown_eligibility_events']) else None
   if exact!=m['exact_within_log_mean']:raise ValueError('Source exactness/missingness differs')
   m.update(value=exact,unknown_native_receiver_exposures=native_unknown,inherited_unknown_target_eligibility=elig_unknown);metrics[mid]=m
  rows.append(dict(game_id=gid,team=team,source_player_id=native,player_master_id=pid,metrics=metrics))
 rows.sort(key=lambda r:(r['game_id'],r['team'],r['source_player_id']))
 basis=dict(version=VERSION,before_period=before_period,definitions=DEFINITIONS,actor_game_rows=rows,team_denominators=deepcopy(source['team_denominators']),unattributed_events=deepcopy(source['unattributed_events']))
 return dict(**basis,semantic_sha256=digest(basis),source_component_semantic_sha256=source['semantic_measurements_sha256'],identity_review_requests=deepcopy(source['identity_review_requests']),evidence_use=source['evidence_use'],pregame_serving_eligible=False,forecast=None,provenance=deepcopy(source['provenance']),limitations=['Provider EPA is a derived source measurement; vendor model/training chronology unknown','Full-game coverage unknown; exactness refers only to observed source log','Official target exposures and proven completion exposures remain distinct; no routes or catchability proxy','Missing receiver identity or eligibility masks exact rate; known attributed samples remain separate'],consumer_status='Features only; model/optimizer integration pending')
