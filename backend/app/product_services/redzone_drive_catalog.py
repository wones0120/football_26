"""Observed entered-drive passing TD conversion with explicit terminal unknowns."""
from copy import deepcopy
import math
from .evaluation_record import digest
from .defense_context_extensions import DEFINITIONS
from .defensive_catalog_features import _rate
from .market_snapshots import canonical_team
VERSION='redzone_drive_catalog_v1'
KNOWN_BASES={'observed_passing_touchdown','observed_rushing_touchdown','provider_field_goal_terminal','provider_missed_field_goal_terminal','provider_punt_terminal','provider_interception_terminal','provider_fumble_lost_terminal','provider_turnover_on_downs_terminal'}
def build_redzone_drive_catalog(source,*,before_period):
 if (source.get('version')!='native_order_redzone_drives_v1' or source.get('chronology_basis')!='native_order_sequence') or source.get('before_period')!=before_period or source.get('pregame_serving_eligible') is not False or source.get('evidence_use')!='postlock_descriptive_not_pregame_or_serving' or source['definitions']['G14-M10']!=DEFINITIONS['G14-M10']:raise ValueError('Matched nonserving entered-drive source required')
 rows=[];seen=set()
 for src in source['game_rows']:
  gid=src['game_id'];parts=gid.split('_');defense=canonical_team(src['defense_team']);offense=canonical_team(src['offense_team'])
  if len(parts)!=4 or not 1<=int(parts[1])<=18 or int(parts[0])*100+int(parts[1])>=before_period or {defense,offense}!={canonical_team(t) for t in parts[2:]} or defense==offense:raise ValueError('Prior native drive game/team scope required')
  key=(gid,defense)
  if key in seen:raise ValueError('Duplicate native defense game')
  seen.add(key);quality=deepcopy(src['drive_quality']);m=_rate(src['metrics']['G14-M10'],'G14-M10');entered=quality['observed_redzone_drive_ids'];outcomes=quality['drive_outcomes']
  if len(set(entered))!=len(entered) or len(entered)!=m['eligible_events'] or len(outcomes)!=len(entered) or {r['drive_id'] for r in outcomes}!=set(entered):raise ValueError('Observed drive entry/outcome grain differs')
  known=[r for r in outcomes if r['outcome_known']]
  if len(known)!=m['known_outcome_events'] or len(outcomes)-len(known)!=m['unknown_outcome_events']:raise ValueError('Drive terminal coverage differs')
  for outcome in known:
   first=outcome.get('first_entry_order');terms=outcome.get('terminal_native_orders',[])
   if type(first) not in {int,float} or not math.isfinite(first) or {t['play_id'] for t in terms}!=set(outcome['terminal_play_ids']) or any(type(t.get('order')) not in {int,float} or not math.isfinite(t['order']) or t['order']<first for t in terms):raise ValueError('Native terminal chronology before entry or unavailable')
  if any(r.get('native_order_verified') is not True for r in known):raise ValueError('Known drive outcome lacks native order chronology proof')
  if any(r['completion_basis'] not in KNOWN_BASES or not r['terminal_play_ids'] for r in known):raise ValueError('Known drive outcome lacks explicit sourced terminal evidence')
  passing=sum(r['completion_basis']=='observed_passing_touchdown' for r in known)
  if passing!=(m['observed_outcome_sum'] or 0):raise ValueError('Passing TD numerator differs from native terminal evidence')
  missing=quality['redzone_events_missing_drive_id']
  if type(missing)is not int or missing<0:raise ValueError('Explicit unknown native drive exposure required')
  m.update(observed_entered_drives=len(entered),unknown_trip_count_due_missing_native_drive=missing,known_passing_TD_drives=passing,unit='passing_TD_per_observed_entered_drive')
  if missing:m['value']=None
  rows.append(dict(game_id=gid,defense_team=defense,offense_team=offense,metrics={'G14-M10':m},drive_quality=quality))
 rows.sort(key=lambda r:(r['game_id'],r['defense_team']));basis=dict(version=VERSION,before_period=before_period,definition='Passing TD after a proven preplay inside20 entry on the same native drive / observed entered drives; terminal-free or conflicting outcomes unknown',game_rows=rows)
 return dict(**basis,semantic_sha256=digest(basis),source_semantic_sha256=source['semantic_measurements_sha256'],provenance=deepcopy(source['provenance']),evidence_use=source['evidence_use'],pregame_serving_eligible=False,forecast=None,limitations=['Known-terminal sample rate is separate from all-eligible entered-drive conversion','Observed native entries/drives are not independently verified complete game possession coverage','Long pass TD after a drive backed out of RZ still counts; drives never observed entering RZ do not','No final-source-row or zero-TD flag implies a completed drive; missing native drive keys mask exact rate'],consumer_status='Features-only; models/optimizer pending')
