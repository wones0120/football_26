"""Prior-period source-selected NGS measurements; no inferred full-team exposure."""
from copy import deepcopy
from datetime import datetime,UTC
from pathlib import Path
import hashlib
from .nextgen_source_components import load_nextgen_snapshot,KINDS,VERSION as SOURCE_VERSION
from .factual_designation import clock
from .defense_context_evidence import _hash
VERSION='nextgen_tracking_features_v1'
DEFINITIONS={
 'G04-M02':dict(family='passing',field='completion_percentage_above_expectation',exposure='attempts',unit='percentage_points',definition='Provider actual completion percentage minus provider expected completion percentage for its selected native weekly passing sample; provider expectation model vintage unknown'),
 'G07-M10':dict(family='rushing',field='rush_yards_over_expected',exposure='rush_attempts',unit='yards',definition='Provider rushing yards minus provider tracking-derived expected rushing yards for its selected native weekly rushing sample; provider expectation model vintage unknown')}
SUPPLEMENTAL={
 'passing':{'avg_time_to_throw':'seconds_snap_to_throw_excludes_sacks','avg_intended_air_yards':'yards_per_provider_intended_target','expected_completion_percentage':'percent_vendor_expected','aggressiveness':'percent_tight_window_attempts'},
 'rushing':{'percent_attempts_gte_eight_defenders':'percent_rush_attempts_with_at_least_eight_defenders_in_box','avg_time_to_los':'seconds_snap_to_line_of_scrimmage','rush_yards_over_expected_per_att':'yards_per_provider_rush_attempt','rush_pct_over_expected':'provider_native_percentage_scale_unverified'},
 'receiving':{'avg_separation':'yards_at_catch_or_incompletion','avg_cushion':'yards_pre_snap_defender_distance','avg_yac':'yards_after_catch_per_provider_reception','avg_expected_yac':'yards_after_catch_vendor_expectation_per_reception','avg_yac_above_expectation':'yards_after_catch_above_vendor_expectation_per_reception'}}

def build_nextgen_features(blocks,*,before_period,actual_derived_at):
 if type(before_period) is not int or not 201601<=before_period or not 1<=before_period%100<=18:raise ValueError('Explicit REG before_period required')
 if clock(actual_derived_at) is None:raise ValueError('Actual derivation clock required')
 rows=[];sources=[];requests=[];seen=set();excluded={'season_aggregate':0,'POST':0,'current_or_future_period':0,'missing_native_scope':0}
 for kind,block in blocks.items():
  if kind not in KINDS or block.get('version')!=SOURCE_VERSION:raise ValueError('NGS source family/version mismatch')
  source=block.get('source',{})
  if not source.get('snapshot_id') or not source.get('content_sha256'):raise ValueError('Indexed source lineage required')
  if clock(source.get('captured_at'))>clock(actual_derived_at) or clock(source.get('observed_at'))>clock(actual_derived_at):raise ValueError('Source unavailable at actual derivation')
  sources.append(dict(stat_type=kind,**deepcopy(source)));requests.extend(deepcopy(block['identity_review_requests']))
  for r in block['rows']:
   if r['stat_type']!=kind:raise ValueError('NGS row family mismatch')
   if r['grain']=='season_aggregate':excluded['season_aggregate']+=1;continue
   if r['season_type']!='REG':excluded['POST']+=1;continue
   if r['season']*100+r['week']>=before_period:excluded['current_or_future_period']+=1;continue
   if not r['weekly_feature_eligible']:excluded['missing_native_scope']+=1;continue
   key=(kind,r['season'],r['week'],r['source_player_id'],r['team'])
   if key in seen:raise ValueError('Duplicate NGS feature native grain')
   seen.add(key);metrics={}
   for mid,d in DEFINITIONS.items():
    if d['family']!=kind:continue
    v=r['values'][d['field']];exposure=r['values'][d['exposure']]
    # A reported average/difference with no positive sample is not verified exposure.
    role_known=mid!='G04-M02' or r['source_position']=='QB'
    known=v is not None and exposure is not None and exposure>0 and role_known
    metrics[mid]=dict(value=v if known else None,reported_value=v,known_exposure=exposure,unit=d['unit'],status='provider_selected_weekly_measurement' if known else 'unknown_measurement_positive_exposure_or_native_QB_scope',source_field=d['field'],source_model_vintage='unknown')
   supplemental={f:dict(value=r['values'][f],unit=u,source_field=f,catalog_id=None) for f,u in SUPPLEMENTAL[kind].items()}
   rows.append(dict(stat_type=kind,season=r['season'],week=r['week'],season_type='REG',source_player_id=r['source_player_id'],player_master_id=r['player_master_id'],team=r['team'],source_position=r['source_position'],identity_status='canonical_native_alias' if r['player_master_id'] else 'native_unresolved_or_ambiguous',metrics=metrics,supplemental=supplemental,source_quality=deepcopy(r['source_quality']),source_snapshot_id=source['snapshot_id']))
 rows.sort(key=lambda r:(r['season'],r['week'],r['stat_type'],r['source_player_id'],r['team']))
 # Opaque IDs and execution clocks are lineage, not extra votes or measurements.
 semantic_rows=[{k:v for k,v in r.items() if k!='source_snapshot_id'} for r in rows]
 basis=dict(version=VERSION,before_period=before_period,definitions=DEFINITIONS,supplemental_definitions=SUPPLEMENTAL,rows=semantic_rows,excluded=excluded,selection='Provider minimum-attempt selected cohort; numeric thresholds unknown; absent players unknown')
 return dict(**(basis | {'rows':rows}),semantic_sha256=_hash(basis),provenance=dict(sources=sources,actual_derived_at=clock(actual_derived_at).isoformat(),producer_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),identity_review_requests=requests),evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,limitations=['Revised historical original decision availability unknown','Vendor expectation model vintage and exact selection thresholds unknown','No full-team denominator, routes, pressure, causal effects or probability inferred','Weekly rows remain team-specific; no invented native game ID','Supplemental provider rush_pct_over_expected native scale unverified; no probability interpretation'])

def derive_nextgen_features(snapshots,*,before_period,cutoff,canonical_ids=None):
 """Authenticate actual indexed immutable sources before constructing measurements."""
 blocks={kind:load_nextgen_snapshot(s,stat_type=kind,cutoff=cutoff,canonical_ids=canonical_ids) for kind,s in snapshots.items()}
 return build_nextgen_features(blocks,before_period=before_period,actual_derived_at=cutoff)

def require_feature_use(value,*,purpose):
 if purpose not in {'offline_descriptive','offline_retrospective_features'}:raise ValueError('NGS retrospective features cannot be registered as pregame/current serving evidence')
 if value.get('evidence_use')!='postlock_descriptive_not_pregame_or_serving' or value.get('pregame_serving_eligible') is not False:raise ValueError('Explicit nonserving boundary required')
 return value
