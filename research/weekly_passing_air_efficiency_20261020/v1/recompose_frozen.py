"""Guard correction on exact prior frozen air projection, no database reread."""
from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from backend.app.product_services.weekly_passing_air_efficiency import load_reviewed_weekly_input,build_weekly_passing_air_efficiency
from research.weekly_passing_air_efficiency_20261020.v1.derive_actual import save

start=time.monotonic();actual=datetime.now(UTC).isoformat();directory=Path('research/weekly_passing_air_efficiency_20261020/v1')
prior=json.loads((directory/'prior_24test_revision/actual_receipt.json').read_text());ref=prior['weekly_input_ref'];source=prior['air_projection_ref'];path=Path(source['path']).resolve()
assert path.parent==Path('artifacts/weekly_passing_air_sources').resolve() and path.name==source['sha256']+'.json'
raw=path.read_bytes();assert len(raw)==source['bytes'] and hashlib.sha256(raw).hexdigest()==source['sha256'];extract=json.loads(raw)
weekly=load_reviewed_weekly_input(ref,cutoff=actual);result=build_weekly_passing_air_efficiency(weekly,extract,cutoff=actual)
old_raw=Path(prior['full_ref']['path']).read_bytes();assert hashlib.sha256(old_raw).hexdigest()==prior['full_ref']['sha256'];old=json.loads(old_raw)
def values(block):return [(r['season'],r['week'],r['team'],r['source_player_id'],r['source_reported_passing_air_yards'],r['official_attempts'],r['value'],r['source_revision_issue']) for r in block['rows']]
changes=sum(a!=b for a,b in zip(values(old),values(result)));assert len(old['rows'])==len(result['rows'])
result['provenance']=dict(weekly_input_ref=ref,air_projection_ref=source,original_weekly_provenance=weekly['provenance'],original_air_projection_read_at=extract['actual_read_at'],actual_read_at=actual,actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),prior_feature_ref=prior['full_ref'],producer_sha256=hashlib.sha256(Path('backend/app/product_services/weekly_passing_air_efficiency.py').read_bytes()).hexdigest())
full=save(result,'weekly_passing_air_efficiency');selected={**result,'rows':[r for r in result['rows'] if r['team'] in {'SF','WAS'}]};selected.pop('semantic_sha256');selected['selected_from_full_ref']=full;sel=save(selected,'weekly_passing_air_efficiency')
coverage=dict(expected_source_QB_rows=extract['expected_reviewed_QB_rows'],observed_raw_projection_rows=len(extract['rows']),rows=len(result['rows']),canonical_rows=sum(r['player_master_id'] is not None for r in result['rows']),known_ratios=sum(r['value'] is not None for r in result['rows']),missing_air_field=sum(not r['source_field_present'] for r in result['rows']),missing_or_conflicting_revision=sum(r['source_revision_issue'] is not None for r in result['rows']),selected_rows=len(selected['rows']))
receipt=dict(full_ref=full,selected_ref=sel,weekly_input_ref=ref,air_projection_ref=source,coverage=coverage,actual_read_at=actual,actual_publication_at=result['provenance']['actual_publication_at'],prior_feature_ref=prior['full_ref'],numeric_or_issue_row_changes=changes,game_binding_counts={basis:sum(r['native_game_binding_basis']==basis for r in result['rows']) for basis in sorted({r['native_game_binding_basis'] for r in result['rows']})},elapsed_seconds=time.monotonic()-start,source_fetches=0,database_reads=0,database_writes=0,parent_inflations=0,models=0,review_status='pending High corrected guard review')
(directory/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
