"""Bounded schema/nonnull evidence only; field semantics are not invented."""
import csv,json,hashlib
from pathlib import Path
from collections import Counter
from datetime import datetime,UTC
source=Path('artifacts/source_snapshots/nflreadpy/play_by_play/season=2026/week=06/slate=monday_night/79230705-26c3-5cbd-af43-b26c9bb4e1bb/nflreadpy_pbp_2026.csv');sha=hashlib.sha256(source.read_bytes()).hexdigest();assert sha=='56e4d82e49e381a07b40ad9f10f5947a7133cbbf27708f1644d17a0c56809912'
fields=['time_of_day','order_sequence','end_clock_time','was_pressure','route','defense_man_zone_type','defense_coverage_type','time_to_throw','defenders_in_box','number_of_pass_rushers','offense_personnel','defense_personnel','offense_players','defense_players']
counts=Counter();values={f:Counter() for f in fields};examples={}
with source.open() as file:
 reader=csv.DictReader(file);present={f:f in reader.fieldnames for f in fields}
 for r in reader:
  if r['season_type']!='REG' or int(float(r['season']))*100+int(float(r['week']))>=202606:continue
  counts['prior_rows']+=1
  for f in fields:
   v=r.get(f)
   if v in (None,''):continue
   counts[f]+=1
   if len(values[f])<20 or v in values[f]:values[f][v]+=1
   examples.setdefault(f,dict(game_id=r['game_id'],play_id=r['play_id'],original=v))
receipt=dict(actual_read_at=datetime.now(UTC).isoformat(),source_sha256=sha,before_period=202606,prior_rows=counts['prior_rows'],fields={f:dict(column_present=present[f],nonnull_rows=counts[f],bounded_value_counts=dict(values[f]),first_native_example=examples.get(f)) for f in fields},evidence_use='postlock_descriptive_not_pregame_or_serving',meaning='Schema/value coverage only; no source semantic interpretation or catalog verification claim',source_fetches=0,models=0)
Path('research/native_enrichment_coverage_20261020/v1/receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({f:dict(column_present=present[f],nonnull_rows=counts[f],sample=examples.get(f)) for f in fields}))
