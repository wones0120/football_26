"""Bounded retained PBP→player components for revised retrospective training.

Original receipt clocks/manifest bytes are retained; this never fabricates an
operational historical Snapshot or contemporaneous pregame availability.
"""
from copy import deepcopy
from datetime import UTC,datetime
from decimal import Decimal
import hashlib
import math
from pathlib import Path
import re

from .market_snapshots import canonical_team,utc_time
from .team_opportunity_matrix import RAW_FIELDS,_native
from .opportunity_events import build_event_evidence
from .player_opportunity_components import build_player_opportunity_components
from .defense_context_evidence import _hash

VERSION='retrospective_player_opportunity_history_v1'
ADDITIONAL_FIELDS=('complete_pass','air_yards','first_down_rush','half_seconds_remaining','ydstogo')
INDICATORS=('pass_attempt','rush_attempt','sack','qb_dropback','qb_spike','qb_kneel','qb_scramble','two_point_attempt')


def load_retrospective_player_components(descriptor,*,cutoff,canonical_ids=None,position_evidence=(),max_bytes=128*1024*1024,max_rows=200000):
    """Read original verified Parquet once; no fetch, fit, name join or write."""
    if type(max_bytes) is not int or max_bytes<=0 or type(max_rows) is not int or max_rows<=0:raise ValueError('Invalid historical bounds')
    decision=utc_time(cutoff);entry=descriptor['manifest'];path=Path(descriptor['path'])
    match=re.fullmatch(r'https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_(\d{4})\.parquet',entry.get('url',''))
    if not match:raise ValueError('Unsupported original PBP source URI')
    expected_season=int(match[1]);received=utc_time(entry['received_at'])
    if received>decision:raise ValueError('Historical source acquired after cutoff')
    if path.stat().st_size!=entry['bytes'] or path.stat().st_size>max_bytes:raise ValueError('Historical source byte bound/size mismatch')
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    if h.hexdigest()!=entry['sha256']:raise ValueError('Historical source hash mismatch')
    import pyarrow.parquet as pq
    file=pq.ParquetFile(path);available=set(file.schema_arrow.names)
    if file.metadata.num_rows>max_rows:raise ValueError('Historical row bound exceeded')
    if set(RAW_FIELDS)-available:raise ValueError('Historical source missing required native/event fields')
    optional=(*ADDITIONAL_FIELDS,'no_play','goal_to_go','quarter_end','desc')
    columns=list(RAW_FIELDS)+[k for k in optional if k in available and k not in RAW_FIELDS]
    events=[];controls=[];seen=set();excluded=0
    for row in file.read(columns=columns).to_pylist():
        row={k:None if isinstance(v,float) and not math.isfinite(v) else v for k,v in row.items()}
        for field in ADDITIONAL_FIELDS:row.setdefault(field,None)
        if row['season_type']!='REG':excluded+=1;continue
        if row['season']!=expected_season:raise ValueError('Historical season contradicts source URI')
        pair=_native(row['game_id'],row['season'],row['week'])
        play=Decimal(str(row['play_id']))
        if not play.is_finite() or play!=play.to_integral_value():raise ValueError('Nonintegral native play ID')
        row['play_id']=str(int(play));key=(row['game_id'],row['play_id'])
        if key in seen:raise ValueError('Duplicate native historical event')
        seen.add(key)
        for field in ('passer_player_id','rusher_player_id','receiver_player_id'):
            native=row.get(field)
            if native is not None and (not isinstance(native,str) or not re.fullmatch(r'00-\d{7}',native)):
                raise ValueError('Historical actor requires native GSIS ID, not name')
        for field in ('posteam','defteam'):
            if row[field] is not None:
                row['native_'+field]=row[field]
                row[field]=canonical_team(row[field])
                if row[field] not in pair:raise ValueError('Historical team contradicts native game')
        if row['posteam'] is not None and row['posteam']==row['defteam']:raise ValueError('Historical offense/defense conflict')
        suspension=row['posteam'] is None and (row.get('desc')=='The game has been suspended. Lightning in the area.' or bool(re.fullmatch(r'The game has resumed\. Total delay time of \d+ hours? and \d+ minutes?\.',str(row.get('desc') or ''))))
        administrative=row['play_type'] is None and (row.get('quarter_end')==1 or row.get('desc') in {'GAME','END GAME'} or suspension) and all(row.get(k) in (None,0,False) for k in INDICATORS)
        if row['posteam'] is None:
            if row['play_type'] not in {'kickoff','extra_point','field_goal','punt','no_play'} and not administrative:raise ValueError('Unscoped historical offense')
            controls.append(row)
        elif administrative:controls.append(row)
        else:events.append(row)
    source=dict(snapshot_id='retained_manifest:'+h.hexdigest(),content_sha256=h.hexdigest(),captured_at=received.isoformat(),received_at=received.isoformat(),
        source_uri=entry['url'],verification='snapshot_artifact_sha256_verified',
        verification_basis='Original retained Parquet manifest bytes independently hashed; NOT a historical operational SourceSnapshot',
        original_material_type='retained_parquet_manifest',full_game_coverage='unverified',game_completion='unverified',historical_availability='revised later capture; original pregame availability unknown')
    receipt=dict(event_evidence=build_event_evidence(events,canonical_ids=canonical_ids or {},source_receipt=source,cutoff=decision))
    block=build_player_opportunity_components(receipt,before_period=expected_season*100+19,cutoff=decision,position_evidence=position_evidence)
    block['underlying_measurements_sha256']=block.pop('semantic_measurements_sha256')
    block['field_availability']={k:k in available for k in ADDITIONAL_FIELDS}
    block.update(evidence_use='revised_retrospective_training_not_original_pregame',pregame_serving_eligible=False)
    block['semantic_measurements_sha256']=_hash(dict(underlying_measurements_sha256=block['underlying_measurements_sha256'],field_availability=block['field_availability'],evidence_use=block['evidence_use'],pregame_serving_eligible=False))
    block['provenance'].update(history_loader_version=VERSION,original_source_descriptor=deepcopy(descriptor),actual_source_received_at=received.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),
        team_key_transform='Existing canonical_team normalizer; original native_posteam/native_defteam and raw artifact retained',loader_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),source_rows=file.metadata.num_rows,scoped_event_rows=len(events),retained_control_rows=len(controls),
        excluded_not_explicit_REG_rows=excluded,missing_optional_measurement_fields=sorted(set(ADDITIONAL_FIELDS)-available),
        control_rows_sha256=hashlib.sha256(__import__('json').dumps(controls,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest(),
        original_pregame_availability='unknown; later revised historical source, not restored by a target-period cutoff')
    return block
