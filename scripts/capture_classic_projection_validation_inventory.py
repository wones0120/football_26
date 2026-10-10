"""Read-only metadata audit. Never reads Week 5 results or changes database rows."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sqlalchemy import create_engine, text
from Database.config import get_connection_string

QUERIES = {
    'projection_runs': """select pr.season,pr.week,count(*) n,min(pr.data_cutoff_at) earliest,
        max(pr.data_cutoff_at) latest,count(a.model_run_id) fitted
        from target.projection_run pr left join target.model_artifact a using(model_run_id)
        where upper(pr.slate_id)='SUNDAY_MAIN' group by 1,2 order by 1,2""",
    'weekly_source_receipts': """select season,week,count(*) n,min(created_at) earliest,
        max(created_at) latest from public.raw_nfl_weekly_stat
        where season>=2024 and (season<2026 or week<=4) group by 1,2 order by 1,2""",
    'source_snapshots': """select snapshot_id,dataset,season,week,slate,observed_at,captured_at,observation_basis,content_sha256,artifact_path,manifest_path from public.source_snapshot where dataset in ('weekly_stats','weekly_rosters') and season>=2024 and (season<2026 or week<=5) order by observed_at""",
    'stats_ingest_runs': """select ingest_run_id,season,week,source_path,source_checksum,started_at,completed_at,rows_raw,status from public.ingest_run where source_table='weekly_stats' and season>=2024 order by started_at""",
    'lineage_columns': """select table_schema,table_name,column_name from information_schema.columns
        where (table_schema='public' and table_name in ('player_alias','raw_nfl_weekly_stat'))
        or (table_schema='target' and table_name='player_game_feature_matrix')
        order by table_name,ordinal_position""",
}

if __name__ == '__main__':
    with create_engine(get_connection_string()).connect() as connection:
        connection.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
        result = {name: [dict(r) for r in connection.execute(text(query)).mappings()]
                  for name, query in QUERIES.items()}
    output = ROOT / 'artifacts/classic_projection_validation/database_inventory.json'
    output.write_text(json.dumps(result, default=str, indent=2) + '\n')
    print('Saved read-only inventory:', output)
