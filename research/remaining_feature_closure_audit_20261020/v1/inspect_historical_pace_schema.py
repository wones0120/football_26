"""Footer-only feasibility inspection; no Parquet row/column values decoded."""
from pathlib import Path
from datetime import datetime,UTC
import json,time
import pyarrow.parquet as pq

root=Path('research/remaining_feature_closure_audit_20261020/v1');start=datetime.now(UTC);tick=time.monotonic()
receipt=json.loads(Path('research/historical_team_interaction_context_20261020/v1/actual_receipt.json').read_text());output=[]
fields=('game_id','play_id','order_sequence','season','season_type','week','posteam','defteam','drive','fixed_drive','qtr','game_seconds_remaining','quarter_seconds_remaining','time','play_type','no_play','pass_attempt','rush_attempt','sack','qb_dropback','qb_scramble','qb_spike','qb_kneel','two_point_attempt','quarter_end')
for entry in receipt['outputs']:
    source=entry['source_provenance']['original_source_descriptor'];path=Path(source['path']);assert path.stat().st_size==source['manifest']['bytes']
    file=pq.ParquetFile(path);names=set(file.schema_arrow.names)
    output.append(dict(season=entry['season'],source_descriptor=source,source_hash_verification='Already approved immutable source lineage reused; this footer-only job checks size, does not claim new full-byte hash verification',source_rows=file.metadata.num_rows,row_groups=file.metadata.num_row_groups,schema_columns=len(names),field_availability={f:f in names for f in fields},native_order_candidate_fields=sorted(n for n in names if any(s in n.lower()for s in('order','sequence','index','sort'))),row_value_reads=0,actual_native_order_proven=False,actual_nonnulls_unknown=True,missingness_and_conditional_coverage='Unknown; schema presence does not prove values or native chronology'))
r=dict(actual_started_at=start.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-tick,outputs=output,parquet_value_rows_decoded=0,models=0,database_queries=0,new_sources=0)
(root/'historical_pace_schema.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
