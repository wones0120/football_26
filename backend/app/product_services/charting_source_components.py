"""FTN charting via public nflverse native game/play joins, never name/proxy joins."""
from copy import deepcopy
from datetime import UTC,datetime
from decimal import Decimal,InvalidOperation
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import csv,hashlib,re
from .factual_designation import clock
from .defense_context_evidence import _hash,_metric,_finish
from .player_effectiveness_components import _record
from .player_opportunity_components import build_player_opportunity_components
from .opportunity_events import validate_event_evidence,_flag
from .environment_context_evidence import _and
from .market_snapshots import canonical_team
from backend.app.services.source_capture import verify_snapshot_artifact,DEFAULT_NFLREADPY_LICENSE

VERSION='ftn_charting_components_v1'
DATASET='ftn_charting'
PROVIDER_URL='https://github.com/nflverse/nflverse-data/releases/download/ftn_charting/ftn_charting_{season}.parquet'
DICTIONARY=dict(contract='nflreadr_ftn_dictionary_observed_20261020_v1',url='https://nflreadr.nflverse.com/articles/dictionary_ftn_charting.html',
 first_read='read_thrown=0 means primary read only from2023; 2022 missing primary codes stay unknown',
 out_of_pocket='Not a designed rollout tag',blitz='n_blitzers is not pressure',motion='Play-level motion does not identify moving player')
BOOL_FIELDS=('is_play_action','is_screen_pass','is_motion','is_qb_out_of_pocket','is_throw_away','is_catchable_ball','is_contested_ball','is_drop','is_qb_sneak')
NATIVE_FIELDS=('nflverse_game_id','nflverse_play_id','season','week')


def _integer(value,field):
 if isinstance(value,bool) or value is None:raise ValueError(f'{field} requires integral native value')
 try:n=Decimal(str(value))
 except InvalidOperation as e:raise ValueError(f'Invalid {field}') from e
 if not n.is_finite() or n!=n.to_integral_value():raise ValueError(f'Nonintegral {field}')
 return int(n)


def _boolean(value):
 if value is None or value=='':return None
 if value is True or value in (1,'1','1.0','true','TRUE','True'):return True
 if value is False or value in (0,'0','0.0','false','FALSE','False'):return False
 raise ValueError('Unrecognized charting boolean; never truth-test string values')


def _pulled(value,cutoff):
 if value in (None,''):return dict(raw=value,aware_at=None,status='unknown')
 try:d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
 except ValueError:return dict(raw=value,aware_at=None,status='unparseable_original_provider_clock')
 if d.tzinfo is None:return dict(raw=value,aware_at=None,status='provider_timezone_unknown')
 d=d.astimezone(UTC)
 if d>clock(cutoff):raise ValueError('FTN API retrieval clock after evidence cutoff')
 return dict(raw=value,aware_at=d.isoformat(),status='provider_API_retrieval_not_original_publication')


def normalize_charting_rows(rows,*,source_season,cutoff,max_rows=200000):
 if type(source_season) is not int or source_season<2022 or source_season>clock(cutoff).year:raise ValueError('FTN source season outside declared scope')
 if type(max_rows) is not int or max_rows<1:raise ValueError('Invalid charting row bound')
 result=[];seen=set()
 for index,original in enumerate(rows):
  if index>=max_rows:raise ValueError('FTN row bound exceeded')
  row=deepcopy(original);gid=str(row.get('nflverse_game_id') or '');match=re.fullmatch(r'(\d{4})_(\d{2})_([A-Z]{2,3})_([A-Z]{2,3})',gid)
  season=_integer(row.get('season'),'season');week=_integer(row.get('week'),'week');play=_integer(row.get('nflverse_play_id'),'nflverse_play_id')
  if not match or season!=source_season or (int(match[1]),int(match[2]))!=(season,week) or not 1<=week<=22 or not 0<=play<=1000000000:raise ValueError('FTN native game/play/season/week conflict')
  if len({canonical_team(match[3]),canonical_team(match[4])})!=2:raise ValueError('FTN native game team pair invalid')
  key=(gid,play)
  if key in seen:raise ValueError('Duplicate normalized FTN native game/play')
  seen.add(key);flags={name:_boolean(row.get(name)) for name in BOOL_FIELDS};counts={};invalid_counts={};raw_counts={}
  for name in ('n_blitzers','n_pass_rushers'):
   value=row.get(name);raw_counts[name]=value
   if value in (None,''):counts[name]=None
   else:
    try:
     measured=_integer(value,name)
     if not 0<=measured<=11:raise ValueError('Outside physical0..11defender range')
     counts[name]=measured
    except ValueError:
     counts[name]=None;invalid_counts[name]=dict(original=value,status='inconsistent_source_count_unknown_not_clipped')
  read=row.get('read_thrown');read=None if read in (None,'') else str(read).upper()
  if read in ('0.0','1.0','2.0'):read=read[:-2]
  read_known=read in {'0','1','2','CHK','DES','SD'} and not (season<2023 and read=='0')
  result.append(dict(game_id=gid,play_id=str(play),season=season,week=week,flags=flags,counts=counts,raw_counts=raw_counts,inconsistent_count_fields=invalid_counts,
   primary_read=read=='0' if read_known else None,read_thrown=read,read_status='known_dictionary_code' if read_known else 'unknown_or_not_defined_for_source_season',
   date_pulled=_pulled(row.get('date_pulled'),cutoff),native_ftn_game_id=row.get('ftn_game_id'),native_ftn_play_id=row.get('ftn_play_id'),
   drop_catchability_conflict=flags['is_drop'] is True and flags['is_catchable_ball'] is False))
 return sorted(result,key=lambda r:(r['game_id'],int(r['play_id'])))


def capture_charting_source(service,*,season,week,slate,slate_lock_at,nfl_module=None,max_rows=200000,max_bytes=64*1024*1024):
 """One installed public provider season; caller owns existing service transaction."""
 if type(season) is not int or not 2022<=season<=datetime.now(UTC).year or type(week) is not int or not 1<=week<=18:raise ValueError('Invalid source capture season/week')
 if not slate or clock(slate_lock_at) is None:raise ValueError('Explicit capture slate/lock required')
 if nfl_module is None:import nflreadpy as nfl_module
 frame=nfl_module.load_ftn_charting(seasons=[season])
 if not hasattr(frame,'columns') or not 0<len(frame)<=max_rows:raise ValueError('FTN provider empty, unsupported, or exceeds row bound')
 if not set(NATIVE_FIELDS).issubset(frame.columns):raise ValueError('FTN provider missing native game/play scope fields')
 if hasattr(frame,'write_csv'):payload=frame.write_csv().encode('utf-8')
 elif hasattr(frame,'to_csv'):payload=frame.to_csv(index=False,lineterminator='\n').encode('utf-8')
 else:raise ValueError('FTN provider must return supported dataframe')
 if len(payload)>max_bytes:raise ValueError('FTN provider byte bound exceeded')
 # Store the provider serialization exactly; avoid a new pyarrow dependency or ID conversion.
 with TemporaryDirectory(prefix='football_ftn_capture_') as tmp:
  path=Path(tmp)/f'ftn_charting_{season}.csv';path.write_bytes(payload)
  capture=service.capture_file(path,source_system='nflreadpy',dataset=DATASET,season=season,week=week,slate=slate,
   source_license=DEFAULT_NFLREADPY_LICENSE,source_uri=PROVIDER_URL.format(season=season),slate_lock_at=clock(slate_lock_at),observation_basis='capture_clock',media_type='text/csv',row_count=len(frame),
   metadata=dict(contract_id=VERSION,loader='load_ftn_charting',nflreadpy_version=str(getattr(nfl_module,'__version__','unknown')),dictionary=deepcopy(DICTIONARY),provider_rows=len(frame),provider_columns=list(frame.columns),raw_representation='Installed provider dataframe native CSV serialization; remote parquet bytes not exposed by loader',provider_expected_url=PROVIDER_URL.format(season=season),provider_csv_sha256=hashlib.sha256(payload).hexdigest(),
    original_historical_pregame_availability='unverified_revised_retrospective_capture',remote_freshness='unknown: installed provider may return cache; capture is not verified remote publication',data_access='Public nflverse provider, not direct paid FTN API'))
 verify_snapshot_artifact(capture.snapshot)
 if capture.snapshot.content_sha256!=hashlib.sha256(payload).hexdigest():raise ValueError('FTN capture differs from provider serialization')
 return capture


def load_charting_snapshot(snapshot,*,cutoff,max_rows=200000,max_bytes=64*1024*1024):
 if snapshot.source_system!='nflreadpy' or snapshot.dataset!=DATASET or snapshot.media_type!='text/csv' or snapshot.source_uri!=PROVIDER_URL.format(season=snapshot.season):raise ValueError('Wrong indexed charting provider/dataset/media/native URI')
 verify_snapshot_artifact(snapshot)
 if not 0<snapshot.byte_count<=max_bytes:raise ValueError('FTN byte bound exceeded')
 if clock(snapshot.captured_at)>clock(cutoff) or clock(snapshot.observed_at)>clock(cutoff):raise ValueError('FTN snapshot not available at actual cutoff')
 with Path(snapshot.artifact_path).open(newline='') as stream:
  reader=csv.DictReader(stream)
  if not set(NATIVE_FIELDS).issubset(reader.fieldnames or []):raise ValueError('FTN source missing native columns')
  fields=list(reader.fieldnames);rows=normalize_charting_rows(reader,source_season=snapshot.season,cutoff=min(clock(cutoff),clock(snapshot.captured_at)),max_rows=max_rows)
 if snapshot.row_count!=len(rows):raise ValueError('Indexed FTN row count mismatch')
 return dict(rows=rows,source=dict(snapshot_id=str(snapshot.snapshot_id),content_sha256=snapshot.content_sha256,source_uri=snapshot.source_uri,
  captured_at=clock(snapshot.captured_at).isoformat(),observed_at=clock(snapshot.observed_at).isoformat(),field_availability={k:k in fields for k in (*BOOL_FIELDS,'read_thrown','n_blitzers','n_pass_rushers','date_pulled')},dictionary=deepcopy(DICTIONARY),
  original_historical_pregame_availability='unverified',revision_status='revised_retrospective_provider_capture',remote_freshness='unknown; provider may be cached'))
