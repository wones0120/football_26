from pathlib import Path
from datetime import datetime,UTC
import json
from sqlalchemy.orm import Session
from backend.app.product_services.optimizer import OptimizerService
from backend.app.services.source_capture import SourceCaptureService
P=Path(__file__).resolve().parent;v=json.load(open(P/'corrected_all_matrix_rows.json'));prior=json.load(open(P/'persistence_receipt.json'));s=OptimizerService()
with Session(s.engine) as session:
 r=SourceCaptureService(session).capture_file(P/'corrected_all_matrix_rows.json',source_system='football26_research',dataset='dst_label_correction_all_rows',season=2026,week=5,slate='DST_SCORING_RESEARCH',source_uri='football26://research/dst_scoring_repair_20261015/v1/corrected_all_matrix_rows.json',source_license='Versioned research labels; original matrix and live projections preserved',effective_at=datetime.now(UTC),observation_basis='versioned_research_correction',media_type='application/json',row_count=len(v['rows']),metadata={'research_only':True,'logical_dataset_sha256':v['sha256'],'original_source_sha256':v['original_source_sha256'],'source_snapshot_ids':[a['snapshot_id'] for a in prior['records']],'live_activation':False,'deduplicated_experiment_rows':804})
 result=dict(snapshot_id=str(r.snapshot.snapshot_id),content_sha256=r.snapshot.content_sha256,artifact_path=r.snapshot.artifact_path,logical_dataset_sha256=v['sha256'],row_versions=len(v['rows']),live_activation=False)
(P/'full_matrix_version_receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
