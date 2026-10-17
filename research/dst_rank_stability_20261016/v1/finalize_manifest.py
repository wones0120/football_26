"""Attach diagnostic evidence and reviewed source hashes without refitting."""
from pathlib import Path
import hashlib
import json
import joblib
P=Path(__file__).resolve().parent
bundle=joblib.load(P/'ranking_candidate.joblib');m=bundle['metadata'];m.pop('artifact_sha256',None)
m['diagnostic_fits_executed']=4
m['total_fits_executed']=37
m['diagnostic_fit_note']='33 planned main fits plus two identical diagnostic prefix fits repeated after an output-assembly error; no alternative/parameter/selection changes.'
m['model_parameters']={name:str(model.get_params()) for name,model in bundle['policies'].models.items()}
m['supporting_code_sha256']={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in [P/'diagnostics.py',P/'selection_diagnostics.py',P/'finalize_manifest.py']}
m['evidence_sha256']={name:hashlib.sha256((P/name).read_bytes()).hexdigest() for name in ['validation.json','weekly_metrics.json','row_predictions.json','selection_audits.json','selection_diagnosis.json','inner_loss_diagnostics.json','inner_row_predictions.json','point_uncertainty_and_strata.json','artifact_scoring_parity.json','sunday_defense_rankings.csv','matched_lineups.json']}
joblib.dump(bundle,P/'ranking_candidate.joblib',compress=3)
m['artifact_sha256']=hashlib.sha256((P/'ranking_candidate.joblib').read_bytes()).hexdigest()
(P/'candidate_manifest.json').write_text(json.dumps(m,indent=2)+'\n')
