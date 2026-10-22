"""No download: independently revalidate immutable captures and exact PBP keys."""
from pathlib import Path
from datetime import datetime,UTC
from collections import Counter
import json,runpy,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.charting_source_components import load_charting_snapshot,BOOL_FIELDS,DICTIONARY

ROOT=Path('research/charting_source_components_20261020/v1')
pbp_keys=runpy.run_path(str(ROOT/'capture_actual.py'))['pbp_keys']
start=time.monotonic();outputs=[]
for season in (2022,2023,2024,2025,2026):
 captured=json.loads((ROOT/f'capture_{season}.json').read_text());result={k:v for k,v in captured.items() if k not in {'validation_status','validation_error','validation_error_type','native_join','field_missingness','field_availability','inconsistent_count_fields','source_quality_conflicts'}}
 result['actual_validation_at']=datetime.now(UTC).isoformat()
 try:
  with Session(engine) as session:
   snapshot=session.get(SourceSnapshot,captured['snapshot_id']);assert snapshot is not None
   loaded=load_charting_snapshot(snapshot,cutoff=datetime.now(UTC));rows=loaded['rows'];keys={(r['game_id'],r['play_id']) for r in rows}
   assert len(rows)==len(keys)==captured['rows']
   result.update(validation_status='verified_native_schema_unique_keys_actual_clock_and_snapshot_bytes',field_availability=loaded['source']['field_availability'],field_missingness={k:sum(r['flags'][k] is None for r in rows) for k in BOOL_FIELDS},count_missingness={k:sum(r['counts'][k] is None for r in rows) for k in ('n_blitzers','n_pass_rushers')},inconsistent_count_fields=dict(Counter(k for r in rows for k in r['inconsistent_count_fields'])),inconsistent_count_original_values={k:dict(Counter(str(r['raw_counts'][k]) for r in rows if k in r['inconsistent_count_fields'])) for k in ('n_blitzers','n_pass_rushers')},read_code_counts=dict(Counter(str(r['read_thrown']) for r in rows)),primary_read_known=sum(r['primary_read'] is not None for r in rows),date_pulled_status=dict(Counter(r['date_pulled']['status'] for r in rows)),date_pulled_aware_min=min((r['date_pulled']['aware_at'] for r in rows if r['date_pulled']['aware_at']),default=None),date_pulled_aware_max=max((r['date_pulled']['aware_at'] for r in rows if r['date_pulled']['aware_at']),default=None),drop_catchability_conflicts=sum(r['drop_catchability_conflict'] for r in rows))
   try:
    raw,regular,offense,source=pbp_keys(season,session)
    result['native_join']=dict(status='verified_exact_game_play_join',PBP_source=source,FTN_keys=len(keys),PBP_raw_keys=len(raw),FTN_matched_raw_PBP=len(keys&raw),FTN_unmatched_raw_PBP=len(keys-raw),FTN_matched_prior_REG=len(keys&regular),PBP_prior_REG=len(regular),PBP_prior_offensive_play_types=len(offense),FTN_matched_prior_offensive_play_types=len(keys&offense),unmatched_examples=[dict(game_id=g,play_id=p) for g,p in sorted(keys-raw)[:10]],meaning='Exact normalized native game/play equality only; missing charting never becomes false/zero')
   except StopIteration:result['native_join']=dict(status='unknown_no_retained_2022_PBP_descriptor',FTN_keys=len(keys),PBP_raw_keys=None,FTN_matched_raw_PBP=None,meaning='FTN native source verified; no PBP join coverage asserted for missing PBP source')
 except Exception as exc:result.update(validation_status='validation_failed_source_preserved',validation_error_type=type(exc).__name__,validation_error=str(exc))
 outputs.append(result);(ROOT/f'validated_{season}.json').write_text(json.dumps(result,indent=2)+'\n');print(season,result['validation_status'],result.get('native_join',{}).get('status'),flush=True)
receipt=dict(status='Actual source captures and independent no-redownload validation; High review pending',actual_completed_at=datetime.now(UTC).isoformat(),validation_elapsed_seconds=time.monotonic()-start,seasons=outputs,dictionary=DICTIONARY,source_representation='Immutable installed-provider native CSV; original remote parquet bytes not exposed by loader',original_historical_pregame_availability='Unknown; actual source capture and upstream date_pulled clocks retained; no backdating',evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,feature_catalog_verified_claims=0,models=0,redownloads=0)
(ROOT/'actual_validated_capture_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
