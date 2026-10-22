"""Official signed rushing YPC for source-proven native weekly quarterbacks."""
from copy import deepcopy
from uuid import UUID
import math
from .weekly_effectiveness_catalog_features import VERSION as WEEKLY_VERSION
from .evaluation_record import digest
VERSION='quarterback_official_efficiency_v1'
DEFINITION='Signed official weekly rushing yards / official weekly carries, including kneel-downs and scrambles; source-proven QB only'
def build_quarterback_official_efficiency(source,*,before_period):
 if source.get('version')!=WEEKLY_VERSION or source.get('before_period')!=before_period or source.get('pregame_serving_eligible') is not False or source.get('evidence_use')!='postlock_descriptive_not_pregame_or_serving':raise ValueError('Matched nonserving weekly source required')
 rows=[];seen=set()
 for src in source['rows']:
  if not src['QB_scope_source_proven']:continue
  season,week=src['season'],src['week'];native=src['source_player_id'];pid=src['player_master_id']
  if type(season)is not int or type(week)is not int or not 1<=week<=18 or season*100+week>=before_period or src['season_type']!='REG' or src['source_position']!='QB':raise ValueError('Strict prior native QB weekly proof required')
  if pid is not None and str(UUID(str(pid)))!=pid:raise ValueError('Canonical QB UUID spelling required')
  key=(season,week,native,src['team'])
  if key in seen:raise ValueError('Duplicate native QB week/team')
  seen.add(key);m=src['metrics']['G07-M01'];n,d=m['numerator'],m['denominator']
  if n is not None and (type(n) not in {int,float} or not math.isfinite(n)):raise ValueError('Finite signed native yards required')
  if d is not None and (type(d) not in {int,float} or not math.isfinite(d) or d<0 or d!=int(d)):raise ValueError('Nonnegative official carry count required')
  value=n/d if n is not None and d is not None and d>0 else None
  if value!=m['value']:raise ValueError('Official source ratio differs')
  rows.append({k:deepcopy(src[k]) for k in ('season','week','season_type','grain','source_player_id','player_master_id','team','native_game_id','source_position','source_quality')}|dict(metrics={'G05-M05':dict(value=value,numerator=n,denominator=d,unit='signed_rushing_yards_per_official_carry',status=m['status'])},source_ref=deepcopy(src['source_ref'])))
 rows.sort(key=lambda r:(r['season'],r['week'],r['source_player_id'],str(r['team'])))
 basis=dict(version=VERSION,before_period=before_period,definition=DEFINITION,rows=[{k:v for k,v in r.items() if k!='source_ref'} for r in rows])
 return dict(**(basis|{'rows':rows}),semantic_sha256=digest(basis),source_semantic_sha256=source['semantic_sha256'],provenance=deepcopy(source['provenance']),identity_review_requests=deepcopy(source['identity_review_requests']),evidence_use=source['evidence_use'],pregame_serving_eligible=False,forecast=None,limitations=['Native player-week/team grain is retained, not a fabricated game ID','Official-inclusive denominator differs from the preserved nonkneel-only variant','Source-proven QB evidence only; no all-position passing-count inference','Unknown and zero carry exposure are undefined, not zero efficiency; retrospective/nonserving'],consumer_status='Features only; models/optimizer pending')
