"""Threshold-selected NFL NGS measurements, separate weekly/season grains."""
from copy import deepcopy
from datetime import datetime,UTC
from decimal import Decimal,InvalidOperation
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID
import csv,hashlib,re,math
from .factual_designation import clock
from .market_snapshots import canonical_team
from .defense_context_evidence import _hash
from backend.app.services.source_capture import verify_snapshot_artifact,DEFAULT_NFLREADPY_LICENSE

VERSION='nextgen_source_components_v1'
KINDS=('passing','rushing','receiving')
URL='https://github.com/nflverse/nflverse-data/releases/download/nextgen_stats/ngs_{kind}.parquet'
DICTIONARY='https://nflreadr.nflverse.com/articles/dictionary_nextgen_stats.html'
DOCUMENTATION='https://nflreadr.nflverse.com/reference/load_nextgen_stats.html'
FIELDS={
 'passing':('avg_time_to_throw','avg_completed_air_yards','avg_intended_air_yards','avg_air_yards_differential','aggressiveness','max_completed_air_distance','avg_air_yards_to_sticks','attempts','pass_yards','pass_touchdowns','interceptions','passer_rating','completions','completion_percentage','expected_completion_percentage','completion_percentage_above_expectation'),
 'rushing':('efficiency','percent_attempts_gte_eight_defenders','avg_time_to_los','rush_attempts','rush_yards','avg_rush_yards','rush_touchdowns','expected_rush_yards','rush_yards_over_expected','rush_yards_over_expected_per_att','rush_pct_over_expected'),
 'receiving':('avg_cushion','avg_separation','avg_air_distance','avg_intended_air_yards','max_air_distance','percent_share_of_intended_air_yards','receptions','targets','catch_percentage','yards','rec_touchdowns','avg_yac','avg_expected_yac','avg_yac_above_expectation')}
COUNTS={'attempts','pass_touchdowns','interceptions','completions','rush_attempts','rush_touchdowns','receptions','targets','rec_touchdowns'}
PERCENTAGES={'completion_percentage','expected_completion_percentage','catch_percentage','aggressiveness','percent_attempts_gte_eight_defenders'}
NONNEGATIVE={'avg_time_to_throw','avg_time_to_los','avg_cushion','avg_separation','max_air_distance','max_completed_air_distance'}


def _integer(value):
 if value is None or isinstance(value,bool):raise ValueError('Native period requires integer')
 try:n=Decimal(str(value))
 except InvalidOperation as exc:raise ValueError('Native period invalid') from exc
 if not n.is_finite() or n!=n.to_integral_value():raise ValueError('Native period nonintegral')
 return int(n)


def _number(value,name):
 if value in (None,''):return None,None
 try:n=float(value)
 except (TypeError,ValueError):return None,'unparseable_source_measurement'
 if isinstance(value,bool) or not math.isfinite(n):return None,'nonfinite_or_boolean_source_measurement'
 if name in COUNTS and (n<0 or n!=int(n)):return None,'invalid_source_count'
 if name in PERCENTAGES and not 0<=n<=100:return None,'invalid_source_percentage'
 if name=='completion_percentage_above_expectation' and not -100<=n<=100:return None,'invalid_source_percentage_point_difference'
 if name in NONNEGATIVE and n<0:return None,'invalid_negative_source_time_or_distance'
 return n,None


def normalize_nextgen_rows(rows,*,stat_type,cutoff,canonical_ids=None,max_rows=200000):
 if stat_type not in KINDS:raise ValueError('NGS stat family invalid')
 ids=canonical_ids or {};seen=set();result=[];requests=[]
 for index,original in enumerate(rows):
  if index>=max_rows:raise ValueError('NGS row bound exceeded')
  raw=deepcopy(original);season=_integer(raw.get('season'));week=_integer(raw.get('week'));phase=raw.get('season_type')
  if not 2016<=season<=clock(cutoff).year or not 0<=week<=25 or phase not in {'REG','POST'}:raise ValueError('NGS explicit native season/phase/week invalid')
  native=str(raw.get('player_gsis_id') or '')
  if not re.fullmatch(r'00-\d{7}',native):
   requests.append(dict(source_row_index=index,native_player_id=raw.get('player_gsis_id'),season=season,week=week,phase=phase,reason='Missing/malformed native GSIS; no name join'))
   native=None
  team_raw=raw.get('team_abbr');team=None if team_raw in (None,'','TOT','2TM','3TM') else canonical_team(str(team_raw))
  grain='season_aggregate' if week==0 else 'weekly'
  key=(season,phase,week,native,team)
  if native and key in seen:raise ValueError('Duplicate NGS native player/phase/period/team grain')
  if native:seen.add(key)
  pid=ids.get(native) if native else None
  if pid is not None:
   try:pid=str(UUID(str(pid)))
   except (ValueError,AttributeError) as exc:raise ValueError('Canonical NGS player must be UUID') from exc
  if native and pid is None:requests.append(dict(native_player_id=native,season=season,week=week,phase=phase,team=team,reason='Native GSIS unresolved/ambiguous; preserve source-selected row'))
  values={};quality={}
  for field in FIELDS[stat_type]:
   values[field],error=_number(raw.get(field),field)
   if error:quality[field]=dict(original=raw.get(field),reason=error)
  result.append(dict(stat_type=stat_type,season=season,season_type=phase,week=week,grain=grain,source_player_id=native,player_master_id=pid,
   team=team,source_native_team=team_raw,source_position=raw.get('player_position'),source_row_index=index,values=values,source_quality=quality,
   weekly_feature_eligible=grain=='weekly' and phase=='REG' and native is not None and team is not None))
 result.sort(key=lambda r:(r['season'],r['season_type'],r['week'],str(r['source_player_id']),str(r['team']),r['source_row_index']))
 return dict(version=VERSION,rows=result,identity_review_requests=requests,
  source_selection='Provider minimum-attempt selection; numeric thresholds not specified in source reference; absent players unknown, not zero',
  original_historical_availability='Unknown revised-provider capture; source expectation model vintages unknown',
  limitations=['Week0 season summaries are never weekly observations or prior-week features','No game ID is invented from native player/week alone',
   'No team denominator reconstructed from threshold-selected players','Tracking averages are vendor measurements, not calibrated probabilities or own forecasts'])


def capture_nextgen_source(service,*,stat_type,season,week,slate,slate_lock_at,nfl_module=None,max_rows=200000,max_bytes=64*1024*1024):
 if stat_type not in KINDS or type(season) is not int or not 2016<=season<=datetime.now(UTC).year or type(week) is not int or not 1<=week<=18:raise ValueError('Invalid NGS capture scope')
 if not slate or clock(slate_lock_at) is None:raise ValueError('Explicit capture scope/lock required')
 if nfl_module is None:import nflreadpy as nfl_module
 # Installed provider downloads one all-history file per type. Call once, not per year.
 frame=nfl_module.load_nextgen_stats(seasons=True,stat_type=stat_type)
 if not hasattr(frame,'columns') or not 0<len(frame)<=max_rows:raise ValueError('NGS provider empty, unsupported or row bound exceeded')
 if not {'season','season_type','week','player_gsis_id','team_abbr'}.issubset(frame.columns):raise ValueError('NGS native grain columns missing')
 if hasattr(frame,'write_csv'):payload=frame.write_csv().encode('utf-8')
 elif hasattr(frame,'to_csv'):payload=frame.to_csv(index=False,lineterminator='\n').encode('utf-8')
 else:raise ValueError('NGS provider unsupported dataframe')
 if len(payload)>max_bytes:raise ValueError('NGS byte bound exceeded')
 with TemporaryDirectory(prefix='football_ngs_capture_') as tmp:
  path=Path(tmp)/f'ngs_{stat_type}_all_returned_seasons.csv';path.write_bytes(payload)
  capture=service.capture_file(path,source_system='nflreadpy',dataset=f'ngs_{stat_type}',season=season,week=week,slate=slate,source_license=DEFAULT_NFLREADPY_LICENSE,
   source_uri=URL.format(kind=stat_type),slate_lock_at=clock(slate_lock_at),observation_basis='capture_clock',media_type='text/csv',row_count=len(frame),
   metadata=dict(contract_id=VERSION,loader='load_nextgen_stats',stat_type=stat_type,loader_seasons=True,nflreadpy_version=str(getattr(nfl_module,'__version__','unknown')),
    provider_rows=len(frame),provider_columns=list(frame.columns),source_scope='Full installed-provider return2016onward; indexed season/week is capture context, not a row filter',
    raw_representation='Provider native CSV serialization; original remote parquet bytes not exposed by loader',provider_csv_sha256=hashlib.sha256(payload).hexdigest(),
    dictionary=DICTIONARY,source_reference=DOCUMENTATION,source_selection='Minimum attempts selected by provider; numeric thresholds unspecified',
    original_historical_availability='Unknown revised-retrospective capture',remote_freshness='Unverified; installed provider may return cache'))
 verify_snapshot_artifact(capture.snapshot)
 if capture.snapshot.content_sha256!=hashlib.sha256(payload).hexdigest():raise ValueError('NGS raw capture differs from provider serialization')
 return capture


def load_nextgen_snapshot(snapshot,*,stat_type,cutoff,canonical_ids=None,max_rows=200000,max_bytes=64*1024*1024):
 if stat_type not in KINDS or snapshot.source_system!='nflreadpy' or snapshot.dataset!=f'ngs_{stat_type}' or snapshot.source_uri!=URL.format(kind=stat_type) or snapshot.media_type!='text/csv':raise ValueError('NGS indexed source provider/family/media mismatch')
 verify_snapshot_artifact(snapshot)
 if not 0<snapshot.byte_count<=max_bytes:raise ValueError('NGS byte bound exceeded')
 if clock(snapshot.observed_at)>clock(cutoff) or clock(snapshot.captured_at)>clock(cutoff):raise ValueError('NGS source not available at actual cutoff')
 with Path(snapshot.artifact_path).open(newline='') as stream:
  reader=csv.DictReader(stream);fields=list(reader.fieldnames or [])
  if not {'season','season_type','week','player_gsis_id','team_abbr'}.issubset(fields):raise ValueError('NGS native source columns missing')
  block=normalize_nextgen_rows(reader,stat_type=stat_type,cutoff=cutoff,canonical_ids=canonical_ids,max_rows=max_rows)
 if snapshot.row_count!=len(block['rows']):raise ValueError('NGS indexed row count mismatch')
 block['source']=dict(snapshot_id=str(snapshot.snapshot_id),content_sha256=snapshot.content_sha256,source_uri=snapshot.source_uri,captured_at=clock(snapshot.captured_at).isoformat(),observed_at=clock(snapshot.observed_at).isoformat(),field_availability={k:k in fields for k in FIELDS[stat_type]},source_columns=fields)
 block['evidence_use']='postlock_descriptive_not_pregame_or_serving';block['pregame_serving_eligible']=False
 block['producer_code_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
 return block
