"""Official weekly statistical ratios, preserving native source and unknowns."""
from copy import deepcopy
from pathlib import Path
from uuid import UUID
import hashlib,math,re
from .factual_designation import clock
from .market_snapshots import canonical_team
from .defense_context_evidence import _hash
VERSION='weekly_effectiveness_catalog_features_v1'
DEFINITIONS={
 'G04-M01':('completions','attempts','completions_per_official_pass_attempt','QB'),
 'G04-M03':('passing_yards','attempts','signed_passing_yards_per_official_attempt','QB'),
 'G04-M05':('passing_yards','completions','signed_passing_yards_per_completion','QB'),
 'G04-M08':('interceptions','attempts','interceptions_per_official_attempt','QB'),
 'G04-M10':('passing_tds','attempts','passing_TD_per_official_attempt','QB'),
 'G07-M01':('rushing_yards','carries','signed_yards_per_official_carry_including_kneels_and_scrambles','all_source_rushers'),
 'G09-M01':('receptions','targets','receptions_per_official_target','all_source_receivers'),
 'G09-M03':('receiving_yards','targets','signed_receiving_yards_per_official_target','all_source_receivers'),
 'G09-M04':('receiving_yards','receptions','signed_receiving_yards_per_reception','all_source_receivers')}
ALIASES={'attempts':('attempts','passing_attempts'),'carries':('carries','rushing_attempts'),'interceptions':('interceptions','passing_interceptions'),'passing_tds':('passing_tds','passing_touchdowns')}
COUNTS={'attempts','carries','completions','interceptions','passing_tds','receptions','targets'}
SOURCE_FIELDS=tuple(sorted({'season_type','season','game_season','week','game_week','player_id','gsis_id','id','position','pos','team','recent_team','game_id','gameid','old_game_id'} | {alias for d in DEFINITIONS.values() for field in d[:2] for alias in ALIASES.get(field,(field,))}))
def _values(raw):
 values={};quality={}
 for field in sorted({x for d in DEFINITIONS.values() for x in d[:2]}):
  known=[];bad=[]
  for key in ALIASES.get(field,(field,)):
   v=raw.get(key)
   if v in (None,''):continue
   try:n=float(v)
   except (TypeError,ValueError):bad.append(dict(field=key,original=str(v),reason='unparseable'));continue
   if isinstance(v,bool) or not math.isfinite(n) or (field in COUNTS and (n<0 or n!=int(n))):bad.append(dict(field=key,original=str(v),reason='invalid_nonfinite_or_count'));continue
   known.append(n)
  values[field]=known[0] if known and len(set(known))==1 and not bad else None
  if bad or len(set(known))>1:quality[field]=dict(invalid_source_values=bad,conflicting_known_alias_values=known if len(set(known))>1 else [])
 for smaller,larger in [('completions','attempts'),('interceptions','attempts'),('passing_tds','completions'),('receptions','targets')]:
  if values[smaller] is not None and values[larger] is not None and values[smaller]>values[larger]:
   quality[smaller]=dict(reason='source_count_exceeds_compatible_exposure',value=values[smaller],exposure=values[larger]);values[smaller]=None
 return values,quality

def build_weekly_effectiveness(records,*,before_period,cutoff,max_rows=100000):
 if type(before_period)is not int or not 200001<=before_period or not 1<=before_period%100<=18:raise ValueError('Explicit prior REG period required')
 rows=[];quarantine=[];requests=[];seen=set();source_refs=[]
 for index,original in enumerate(records):
  if index>=max_rows:raise ValueError('Weekly source row bound exceeded')
  r=dict(original);raw={k:deepcopy(v) for k,v in (r.get('raw_row_json') or {}).items() if k in SOURCE_FIELDS};native=r.get('source_player_id');season=r.get('season');week=r.get('week')
  if type(season)is not int or type(week)is not int or not 2000<=season or not 1<=week<=18 or season*100+week>=before_period:raise ValueError('Weekly source is not strictly prior REG period')
  if raw.get('season_type')!='REG':raise ValueError('Explicit REG raw-source phase required; no season summaries')
  for field,expected in [('season',season),('game_season',season),('week',week),('game_week',week)]:
   if raw.get(field) is not None and str(raw[field]) not in {str(expected),str(float(expected))}:raise ValueError('Native metadata/raw period contradiction')
  if r.get('source_id') is None or not r.get('ingest_run_id') or not r.get('imported_at') or clock(r['imported_at'])>clock(cutoff):raise ValueError('Original raw source/ingest clock missing or future')
  if not isinstance(native,str) or not re.fullmatch(r'00-\d{7}',native):
   quarantine.append(dict(source_id=r['source_id'],native_player_id=native,reason='Missing/malformed GSIS; no name join',source_row_sha256=_hash(raw)));requests.append(quarantine[-1]);continue
  for native_field in ('player_id','gsis_id'):
   if raw.get(native_field) not in (None,native):raise ValueError('Raw native player differs from indexed native ID')
  native_teams={k:v for k,v in [('indexed_team',r.get('team')),('raw_team',raw.get('team')),('raw_recent_team',raw.get('recent_team'))] if v not in (None,'')}
  team_values=set();team_errors={}
  for label,value in native_teams.items():
   try:team_values.add(canonical_team(str(value)))
   except ValueError:team_errors[label]=str(value)
  team=next(iter(team_values)) if len(team_values)==1 and not team_errors else None
  pid=r.get('player_master_id')
  aliases=r.get('native_alias_evidence',[]);alias_ids=set()
  for alias in aliases:
   if alias.get('source_key')!=native or alias.get('source_system')!='nflreadpy' or not alias.get('alias_id') or not alias.get('created_at') or clock(alias['created_at'])>clock(cutoff):raise ValueError('Native alias evidence missing, mismatched or future')
   alias_ids.add(str(UUID(str(alias['player_master_id']))))
  if pid is not None and alias_ids!={pid}:raise ValueError('Canonical attachment lacks unique cutoff-bounded native alias proof')
  if pid is not None and str(UUID(str(pid)))!=pid:raise ValueError('Canonical weekly UUID spelling invalid')
  key=(season,week,native,team)
  if key in seen:raise ValueError('Duplicate native weekly player/team grain')
  seen.add(key);position=r.get('position');raw_position=raw.get('position') if raw.get('position') is not None else raw.get('pos');role_known=position=='QB' and raw_position in (None,'QB')
  values,quality=_values(raw);metrics={}
  if team_errors or len(team_values)>1:quality['team_scope']=dict(reason='Unknown/conflicting native team; team attachment withheld',native_teams=native_teams)
  if position=='QB' and raw_position not in (None,'QB'):quality['QB_role']=dict(reason='Indexed/raw native position conflict; no QB metric inferred')
  for mid,(num,den,unit,scope) in DEFINITIONS.items():
   if scope=='QB' and not role_known:continue
   n=values[num];d=values[den];value=n/d if n is not None and d is not None and d>0 else None
   metrics[mid]=dict(value=value,numerator=n,denominator=d,status='measured_weekly_ratio' if value is not None else 'undefined_zero_exposure' if d==0 else 'unknown_source_measurement')
  source_ref=dict(source_id=r['source_id'],ingest_run_id=r['ingest_run_id'],imported_at=r['imported_at'],projected_source_row_sha256=_hash(raw),native_team_evidence=native_teams,native_alias_evidence=deepcopy(aliases));source_refs.append(source_ref)
  rows.append(dict(season=season,week=week,season_type='REG',grain='native_player_week_team',source_player_id=native,player_master_id=pid,team=team,native_game_id=r.get('game_id'),source_position=position,QB_scope_source_proven=role_known,metrics=metrics,source_quality=quality,source_ref=source_ref))
 # Cross-native aliases cannot silently attach two source actors to one UUID/period.
 bycanonical={}
 for r in rows:
  if r['player_master_id'] is not None:bycanonical.setdefault((r['season'],r['week'],r['player_master_id']),[]).append(r)
 implicated=set()
 for group in bycanonical.values():
  if len({r['source_player_id'] for r in group})>1:implicated.update(r['source_player_id'] for r in group)
 for r in rows:
  if r['source_player_id'] in implicated:
   r['source_quality']['canonical_identity']=dict(reason='Native actor implicated in canonical UUID collision; attachment withheld across entire extract',original_player_master_id=r['player_master_id']);r['player_master_id']=None
 for r in rows:
  if r['player_master_id'] is None:requests.append(dict(season=r['season'],week=r['week'],team=r['team'],source_player_id=r['source_player_id'],reason='Unresolved or contradictory native alias; persist existing identity review'))
 rows.sort(key=lambda r:(r['season'],r['week'],r['source_player_id'],str(r['team'])))
 semantic_rows=[{k:v for k,v in r.items() if k!='source_ref'} for r in rows]
 basis=dict(version=VERSION,before_period=before_period,definitions=DEFINITIONS,source_field_aliases=ALIASES,source_projection_fields=SOURCE_FIELDS,rows=semantic_rows,quarantined_source_rows=sorted([{k:v for k,v in r.items() if k!='source_id'} for r in quarantine],key=lambda r:(str(r['native_player_id']),r['source_row_sha256'])))
 return dict(**(basis|{'rows':rows}),semantic_sha256=_hash(basis),identity_review_requests=requests,provenance=dict(valid_source_row_refs_count=len(source_refs),actual_derived_at=clock(cutoff).isoformat(),producer_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),original_availability='Revised raw weekly source imported later; original historical pregame chronology unknown'),evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,limitations=['Official weekly source scope, not fabricated native game ID or current availability proof','No minimum-outcome/salary/user-preference cohort filter; zero exposures remain undefined','Yards per carry includes official kneels/scrambles; separate nonkneel variants are preserved elsewhere','No EPA, route/contact, calibrated scoring probabilities or forecasts inferred'])

def load_weekly_effectiveness_sources(engine,*,before_period,cutoff,start_season=2023,max_rows=100000):
 """Bounded read-only current raw row/ingest IDs; caller freezes actual extract, unique exact GSIS aliases."""
 from sqlalchemy import text
 season,week=divmod(before_period,100)
 with engine.connect() as connection:
  result=connection.execute(text('''WITH aliases AS (
 SELECT source_key,CASE WHEN COUNT(DISTINCT player_master_id)=1 THEN MIN(player_master_id::text) END AS player_master_id,
 jsonb_agg(jsonb_build_object('alias_id',alias_id,'source_system',source_system,'source_key',source_key,'player_master_id',player_master_id,'created_at',created_at)) AS native_alias_evidence
 FROM public.player_alias WHERE source_system='nflreadpy' AND created_at AT TIME ZONE 'UTC'<=:cutoff GROUP BY source_key), latest AS (
 SELECT DISTINCT ON(COALESCE(r.player_id,'__missing:'||r.raw_nfl_weekly_stat_id::text),r.season,r.week,r.team) r.*,a.player_master_id,a.native_alias_evidence
 FROM public.raw_nfl_weekly_stat r LEFT JOIN aliases a ON a.source_key=r.player_id
 WHERE r.source_system='nflreadpy' AND r.season BETWEEN :start AND :season AND r.week BETWEEN 1 AND 18
 AND (r.season<:season OR r.week<:week) AND r.created_at AT TIME ZONE 'UTC'<=:cutoff AND r.raw_row_json->>'season_type'='REG'
 ORDER BY COALESCE(r.player_id,'__missing:'||r.raw_nfl_weekly_stat_id::text),r.season,r.week,r.team,r.created_at DESC,r.raw_nfl_weekly_stat_id DESC)
 SELECT player_master_id,COALESCE(native_alias_evidence,'[]'::jsonb) AS native_alias_evidence,player_id AS source_player_id,season,week,team,position,game_id,(SELECT COALESCE(jsonb_object_agg(f.key,f.value),'{}'::jsonb) FROM jsonb_each(latest.raw_row_json::jsonb) f WHERE f.key=ANY(CAST(:source_fields AS text[]))) AS raw_row_json,
 raw_nfl_weekly_stat_id AS source_id,ingest_run_id,created_at AS imported_at FROM latest LIMIT :row_limit'''),dict(start=start_season,season=season,week=week,cutoff=clock(cutoff),row_limit=max_rows+1,source_fields=list(SOURCE_FIELDS))).mappings().all()
 if len(result)>max_rows:raise ValueError('Weekly source row bound exceeded')
 return [dict(r,player_master_id=str(r['player_master_id']) if r['player_master_id'] is not None else None,imported_at=r['imported_at'].isoformat()) for r in result]

def require_feature_use(value,*,purpose):
 if purpose!='offline_descriptive':raise ValueError('Retrospective weekly measurements cannot be registered as current/pregame serving evidence')
 if value.get('pregame_serving_eligible') is not False:raise ValueError('Explicit nonserving boundary required')
 return value

def persist_weekly_identity_requests(connection,features,*,source_ref,source_root=None):
 """Append existing UI quarantine records; never mutate aliases or reopen resolved issues."""
 import json
 from sqlalchemy import text
 root=Path(source_root or 'artifacts/weekly_effectiveness_sources').resolve();path=Path(source_ref['path']).resolve()
 if path.parent!=root or path.name!=source_ref['sha256']+'.json':raise ValueError('Managed immutable weekly extract required')
 if path.stat().st_size!=source_ref['bytes'] or path.stat().st_size>128*1024*1024:raise ValueError('Weekly extract size mismatch')
 raw=path.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=source_ref['sha256']:raise ValueError('Weekly extract hash mismatch')
 source=json.loads(raw)
 if source.get('source_kind')!='actual_database_raw_weekly_revision_extract' or source.get('before_period')!=features.get('before_period') or features.get('version')!=VERSION:raise ValueError('Weekly extract scope/version mismatch')
 records={r['source_id']:(i,r) for i,r in enumerate(source['rows'])};rows={(r['season'],r['week'],r['source_player_id'],r['team']):r for r in features['rows']};pending={}
 for item in features['identity_review_requests']:
  candidates=[]
  if 'source_id' in item:
   index,r=records[item['source_id']]
   projected={k:v for k,v in r['raw_row_json'].items() if k in SOURCE_FIELDS}
   if _hash(projected)!=item['source_row_sha256']:raise ValueError('Quarantine row differs from immutable extract')
   key=f"weekly-extract:{source_ref['sha256']}:{index}";native=r.get('source_player_id');reason='weekly_native_gsis_missing_or_malformed'
  else:
   row=rows[(item['season'],item['week'],item['source_player_id'],item['team'])];native=row['source_player_id'];r=row
   conflict=row['source_quality'].get('canonical_identity')
   candidates=[conflict['original_player_master_id']] if conflict else []
   key='nflreadpy-gsis:'+native;reason='weekly_native_gsis_alias_missing'
   if conflict:
    key='weekly-alias-conflict:'+_hash(dict(native=native,period=row['season']*100+row['week'],candidate=candidates,source_sha256=source_ref['sha256']));reason='weekly_native_alias_canonical_collision'
  pending.setdefault(key,dict(key=key,native=native,season=r['season'],week=r['week'],team=r.get('team'),position=r.get('position') or r.get('source_position'),reason=reason,candidates=candidates))
 for key,r in sorted(pending.items()):
  connection.execute(text('''INSERT INTO target.identity_quarantine
  (identity_quarantine_id,entity_type,source_schema,source_table,source_record_key,source_system,season,week,slate,source_player_key,display_name,team_id,position,reason_code,candidate_player_ids,status,first_seen_at,updated_at)
  VALUES (:qid,'player','public','raw_nfl_weekly_stat',:key,'nflreadpy',:season,:week,'FEATURE_INVENTORY',:native,NULL,:team,:position,:reason,CAST(:candidates AS jsonb),'open',now(),now())
  ON CONFLICT (source_schema,source_table,source_record_key) DO NOTHING'''),dict(r,qid='weekly-native:'+hashlib.sha256(key.encode()).hexdigest()[:32],candidates=json.dumps(r['candidates'])))
 return dict(source_incidents=len(features['identity_review_requests']),distinct_queue_keys=len(pending),source_extract_ref=source_ref,records=list(pending.values()),policy='Append only; existing resolved records unchanged; no alias/canonical mutation')
