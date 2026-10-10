"""Current-slate explanation parity and opportunity evidence checks; no outcomes."""
import json
from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.product_services.model_artifacts import deserialize_artifact, explain_player
from backend.app.product_services.predictions import apply_opportunity_point_adjustment

SOURCE = ROOT / 'artifacts/classic_opportunity_repair'
OUT = ROOT / 'artifacts/classic_projection_validation'


def main():
    run = next(r for r in json.loads((SOURCE / 'inventory.json').read_text()) if r['week'] == 5)
    payload = deserialize_artifact((SOURCE / (run['projection_run_id'] + '.joblib')).read_bytes(), run['artifact_sha256'])
    stored = pd.DataFrame(json.loads((SOURCE / 'original_projections.json').read_text()))
    stored = stored.loc[stored.projection_run_id.eq(run['projection_run_id'])].set_index('player_id')
    errors = []
    target = payload['target']
    representatives = target.groupby('position').head(1).player_id.astype(str).tolist()
    if 'market_team_point_adjustment' in target:
        representatives += target.loc[target.market_team_point_adjustment.abs().sort_values(ascending=False).head(5).index].player_id.astype(str).tolist()
    representatives = list(dict.fromkeys(representatives))
    for player_id in representatives:
        explanation = explain_player(payload, player_id)
        errors.append(abs(explanation['reloaded_model_mean'] - float(stored.loc[player_id, 'mean'])))
    repaired = pd.read_pickle(SOURCE / (run['projection_run_id'] + '_corrected_features.pkl'))
    _, details = apply_opportunity_point_adjustment([0.] * len(repaired), payload['train'], repaired)
    evidence = repaired[['player_id', 'player_display_name', 'position', 'recent_team']].copy()
    for col in ('pregame_opportunity_point_reason', 'pregame_opportunity_evidence_status', 'pregame_opportunity_review_required'):
        evidence[col] = details[col].to_numpy()
    evidence.to_csv(OUT / 'current_slate_opportunity_review.csv', index=False)
    summary = {'projection_run_id': run['projection_run_id'], 'cutoff': run['data_cutoff_at'],
               'players_checked': len(errors), 'full_opportunity_pool_reviewed': len(repaired), 'maximum_saved_mean_error': max(errors),
               'opportunity_evidence_counts': details.pregame_opportunity_evidence_status.value_counts().to_dict(),
               'review_required_players': int(details.pregame_opportunity_review_required.sum()),
               'outcomes_used': False, 'production_default_changed': False}
    (OUT / 'current_slate_explanation_parity.json').write_text(json.dumps(summary, indent=2) + '\n')
    assert max(errors) < 1e-7, summary
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
