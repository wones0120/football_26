"""Leakage, independence, paired-cohort and tuning guard regressions."""
import unittest
import pandas as pd
from scripts.classic_projection_validation import (
    validate_windows, error_metrics, paired_metrics, calibration_metrics, select_anchor_weights,
    refit_forecast_pair,
)


def window():
    return {'season': 2026, 'week': 4, 'slate': 'SUNDAY_MAIN',
            'cutoff': '2026-10-04T16:00:00Z', 'earliest_kickoff': '2026-10-04T17:00:00Z',
            'historical_features_as_of_each_game': True,
            'receipts': [{'kind': kind, 'hash_verified': True, 'sha256': 'f'*64,
                          'received_at': '2026-10-04T15:00:00Z', 'observed_at': '2026-10-04T15:00:00Z'}
                         for kind in ('weekly_stats', 'identity', 'roster', 'features', 'context')]}


class ValidationTests(unittest.TestCase):
    def test_duplicates_are_not_independent(self):
        with self.assertRaisesRegex(ValueError, 'not independent'):
            validate_windows([window(), window()])

    def test_late_alias_receipt_rejected(self):
        w = window()
        w['receipts'][1]['received_at'] = '2026-10-04T19:25:00Z'
        with self.assertRaisesRegex(ValueError, 'after cutoff'):
            validate_windows([w])

    def test_missing_training_provenance_rejected(self):
        w = window()
        w['historical_features_as_of_each_game'] = False
        with self.assertRaisesRegex(ValueError, 'per-game'):
            validate_windows([w])

    def test_postlock_and_unverified_receipts_rejected(self):
        w = window()
        w['cutoff'] = w['earliest_kickoff']
        with self.assertRaises(ValueError):
            validate_windows([w])
        w = window()
        w['receipts'][0]['hash_verified'] = False
        with self.assertRaises(ValueError):
            validate_windows([w])

    def test_valid_window(self):
        validate_windows([window()])

    def test_unknown_forecast_is_not_zero(self):
        metrics = error_metrics([float('nan'), 3], [5, 1])
        self.assertEqual(metrics['n'], 1)
        self.assertEqual(metrics['missing_forecast_n'], 1)
        self.assertEqual(metrics['bias'], 2)

    def test_single_week_has_no_uncertainty_claim(self):
        rows = pd.DataFrame({'season': [2026, 2026], 'week': [4, 4], 'actual_points': [10, 10],
                             'legacy_v1_mean': [8, 8], 'team_window_v2_mean': [9, float('nan')]})
        m = paired_metrics(rows, 'actual_points', 'mean')
        self.assertEqual(m['paired_n'], 1)
        self.assertEqual(m['equal_week_delta']['mae'], -1)
        self.assertIsNone(m['week_cluster_95_ci'])

    def test_week_weighting_does_not_weight_larger_slates(self):
        rows = pd.DataFrame({'season': [2026]*4, 'week': [1, 1, 1, 2], 'actual_points': [0]*4,
                             'legacy_v1_mean': [2]*4, 'team_window_v2_mean': [1, 1, 1, 5]})
        m = paired_metrics(rows, 'actual_points', 'mean')
        self.assertEqual(m['equal_week_delta']['mae'], 1)
        self.assertIsNotNone(m['week_cluster_95_ci'])

    def test_calibration_counts_boundaries_consistently(self):
        rows = pd.DataFrame({'actual_points': [0, 5, 10, 15], 'legacy_v1_p10': [0]*4, 'legacy_v1_p90': [10]*4})
        m = calibration_metrics(rows, 'legacy_v1')
        self.assertEqual(m['coverage'], .75)
        self.assertEqual(m['above_p90'], .25)
        rows.loc[0, 'legacy_v1_p10'] = 11
        with self.assertRaises(ValueError):
            calibration_metrics(rows, 'legacy_v1')

    def test_weights_need_independent_prior_folds(self):
        rows = pd.DataFrame({'season': [2026]*3, 'week': [1, 2, 3], 'base': [0.]*3, 'anchor': [10.]*3,
                             'actual_points': [5.5]*3, 'player_games_history': [4]*3, 'anchor_active': [True]*3,
                             'prior_only_fit': [True]*3, 'training_through': [202522, 202601, 202602]})
        selected, _ = select_anchor_weights(rows, test_start=202604)
        self.assertEqual(selected['veteran'], .55)
        with self.assertRaises(ValueError):
            select_anchor_weights(rows, test_start=202603)
        rows.loc[0, 'training_through'] = 202601
        with self.assertRaises(ValueError):
            select_anchor_weights(rows, test_start=202604)

    def test_independent_refit_and_prior_calibration_smoke(self):
        from backend.app.product_services.predictions import TARGET_COL
        train = pd.DataFrame({'season': [2026]*420, 'week': [1]*210 + [2]*210,
                              'player_master_id': [str(i) for i in range(420)], 'position': ['RB']*420,
                              'signal': [i % 20 for i in range(420)], TARGET_COL: [i % 20 for i in range(420)]})
        target = pd.DataFrame({'season': [2026], 'week': [4], 'player_master_id': ['x'],
                               'recent_team': ['DET'], 'position': ['RB'], 'signal': [10]})
        predictions = refit_forecast_pair({p: train for p in ('legacy_v1', 'team_window_v2')},
                                         {p: target for p in ('legacy_v1', 'team_window_v2')},
                                         target_period=202604, feature_columns=['signal'], windows=[window()])
        pd.testing.assert_frame_equal(predictions['legacy_v1'], predictions['team_window_v2'])
        self.assertLessEqual(predictions['legacy_v1'].p10.iloc[0], predictions['legacy_v1'].p90.iloc[0])

    def test_test_labels_cannot_enter_forecasting(self):
        from backend.app.product_services.predictions import TARGET_COL
        train = pd.DataFrame({'season': [2026], 'week': [1], 'player_master_id': ['a'], 'position': ['RB']})
        target = pd.DataFrame({TARGET_COL: [10.], 'season': [2026], 'week': [4], 'player_master_id': ['a'], 'position': ['RB']})
        with self.assertRaisesRegex(ValueError, 'labels'):
            refit_forecast_pair({'legacy_v1': train, 'team_window_v2': train}, {'legacy_v1': target, 'team_window_v2': target}, target_period=202604, feature_columns=[], windows=[window()])


if __name__ == '__main__':
    unittest.main()
