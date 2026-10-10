from unittest import TestCase
from unittest.mock import MagicMock, patch

import pandas as pd

from backend.app.product_services.kicker_roles import assign_kicker_roles
from backend.app.product_services.predictions import kicker_point_estimates

CUTOFF = '2026-10-05T19:34:45+00:00'
AT = '2026-10-02T14:37:33+00:00'


def roster(pid, status='ACT', depth='K'):
    return dict(player_id=pid, team='NO', roster_status=status,
                depth_chart_position=depth, created_at=AT, evidence_id=pid)


def pool():
    return pd.DataFrame([dict(player_id=pid, player_team='NO', position='K',
                             player_display_name=pid, salary=salary,
                             projection=10.93, p90=16.58,
                             player_games_history=10, player_roll3_mean=12,
                             player_roll8_mean=9.3333333333)
                         for pid, salary in [('starter', 1000), ('backup', 6000)]])


def context(pid, role='primary_kicker', duties=None):
    facts = {} if duties is None else {'expected_kicking_duties': duties}
    return dict(player_master_id=pid, team='NO', position='K', role_label=role,
                source='official_team', source_uri='https://example.com/depth',
                observed_at=AT, received_at=AT, availability_probability=1,
                evidence_json=facts)


class KickerRoleTests(TestCase):
    def test_salary_rows_without_projection_cutoff_do_not_hide_role_evidence(self):
        from backend.app.product_services.optimizer import OptimizerService
        engine = MagicMock()
        engine.dialect.name = "postgresql"
        inspector = MagicMock()
        inspector.has_table.side_effect = lambda name, **kwargs: name in {
            "curated_salary", "player_projection", "dim_player"}
        inspector.get_columns.return_value = []
        frame = pool()
        frame['name'] = frame.player_display_name
        frame['opponent_team'] = 'ATL'
        for column in ('predicted_p50', 'predicted_p10', 'predicted_p90'):
            frame[column] = None
        frame['data_cutoff_at'] = [CUTOFF, None]
        evidence = dict(cutoff=CUTOFF, rosters=[roster('starter'), roster('backup', 'DEV')])
        service = OptimizerService.__new__(OptimizerService)
        service.engine = engine
        with patch('backend.app.product_services.optimizer.inspect', return_value=inspector), \
             patch('backend.app.product_services.optimizer.pd.read_sql', return_value=frame), \
             patch('backend.app.product_services.kicker_roles.load_kicker_evidence', return_value=evidence) as loader:
            loaded = service._load_target_player_pool(2026, 4, 'MONDAY_NIGHT', projection_run_id='run')
        self.assertEqual(loader.call_args.kwargs['cutoff'].isoformat(), CUTOFF)
        assigned, _ = assign_kicker_roles(loaded)
        self.assertEqual(assigned.kicker_role_eligible.tolist(), [True, False])

    def test_active_roster_beats_backup_historical_production_and_salary(self):
        original = pool()
        rows, report = assign_kicker_roles(original, dict(cutoff=CUTOFF,
            rosters=[roster('starter'), roster('backup', 'DEV')]))
        self.assertEqual(rows.kicker_role_eligible.tolist(), [True, False])
        self.assertEqual(report['teams'][0]['primary_player_id'], 'starter')
        self.assertEqual(rows.projection.tolist(), original.projection.tolist())
        self.assertEqual(kicker_point_estimates(rows)[0].iloc[1], 0)
        # Role selection never depends on which kicker is cheaper.
        original['salary'] = [10000, 200]
        swapped, _ = assign_kicker_roles(original, dict(cutoff=CUTOFF,
            rosters=[roster('starter'), roster('backup', 'DEV')]))
        self.assertEqual(swapped.kicker_role_eligible.tolist(), [True, False])

    def test_unranked_k_label_and_prior_ability_do_not_establish_primary(self):
        rows, report = assign_kicker_roles(pool(), dict(cutoff=CUTOFF,
            rosters=[roster('starter'), roster('backup')]))
        self.assertFalse(rows.kicker_role_eligible.any())
        self.assertIn('uncertain', report['warnings'][0])

    def test_missing_or_future_evidence_fails_closed(self):
        for evidence in [{}, dict(cutoff=CUTOFF, rosters=[dict(roster('starter'), created_at='2026-10-06T00:00:00Z')])]:
            rows, report = assign_kicker_roles(pool(), evidence)
            self.assertFalse(rows.kicker_role_eligible.any())
            self.assertTrue(report['warnings'])

    def test_evidence_after_kickoff_is_not_pregame_even_with_later_cutoff(self):
        frame = pool()
        frame['game_id'] = 'ATL@NO 10/05/2026 08:15PM ET'
        late = dict(roster('starter'), created_at='2026-10-06T00:30:00Z')
        rows, report = assign_kicker_roles(frame, dict(cutoff='2026-10-06T01:00:00Z', rosters=[late]))
        self.assertFalse(rows.kicker_role_eligible.any())
        self.assertTrue(report['warnings'])

    def test_primary_outside_salary_pool_does_not_promote_backup(self):
        rows, _ = assign_kicker_roles(pool().iloc[[1]], dict(cutoff=CUTOFF,
            rosters=[roster('starter'), roster('backup', 'DEV')]))
        self.assertFalse(rows.kicker_role_eligible.any())

    def test_explicit_sourced_replacement_overrides_development_roster(self):
        rows, _ = assign_kicker_roles(pool(), dict(cutoff=CUTOFF,
            rosters=[roster('starter'), roster('backup', 'DEV')],
            context=[context('backup')]))
        self.assertEqual(rows.kicker_role_eligible.tolist(), [False, True])

    def test_multiple_kickers_require_explicit_shared_duties(self):
        rows, _ = assign_kicker_roles(pool(), dict(cutoff=CUTOFF,
            rosters=[roster('starter'), roster('backup', 'DEV')],
            context=[context('backup', role='BACKUP', duties=True)]))
        self.assertEqual(rows.kicker_role_eligible.tolist(), [True, True])

    def test_unsourced_backup_duties_cannot_override_roster(self):
        fact = context('backup', duties=True)
        fact['source_uri'] = None
        rows, _ = assign_kicker_roles(pool(), dict(cutoff=CUTOFF,
            rosters=[roster('starter'), roster('backup', 'DEV')], context=[fact]))
        self.assertEqual(rows.kicker_role_eligible.tolist(), [True, False])

    def test_shared_duties_without_history_cannot_borrow_primary_projection(self):
        rows = pool()
        rows['kicker_role_eligible'] = [True, True]
        rows['kicker_role'] = ['primary', 'explicit_duties']
        rows.loc[1, ['player_games_history', 'player_roll3_mean', 'player_roll8_mean']] = [0, None, None]
        with self.assertRaisesRegex(ValueError, 'cannot be copied'):
            kicker_point_estimates(rows)

    def test_conflicting_primary_evidence_excludes_both(self):
        rows, report = assign_kicker_roles(pool(), dict(cutoff=CUTOFF,
            context=[context('starter'), context('backup')]))
        self.assertFalse(rows.kicker_role_eligible.any())
        self.assertTrue(report['warnings'])

    def test_recent_usage_can_resolve_two_active_kickers_with_warning(self):
        rows, report = assign_kicker_roles(pool(), dict(cutoff=CUTOFF,
            rosters=[roster('starter'), roster('backup')],
            usage=[dict(player_id='starter', team='NO', week=3, attempts=4, created_at=AT)]))
        self.assertEqual(rows.kicker_role_eligible.tolist(), [True, False])
        self.assertIn('confirm current', report['warnings'][0])

    def test_zero_attempt_game_does_not_prove_kicking_duties(self):
        rows, _ = assign_kicker_roles(pool(), dict(cutoff=CUTOFF,
            usage=[dict(player_id='backup', team='NO', week=3, attempts=0, created_at=AT)]))
        self.assertFalse(rows.kicker_role_eligible.any())

    def test_no_peer_history_is_lent_to_backup_without_history(self):
        rows = pool()
        rows['kicker_role_eligible'] = [True, False]
        rows.loc[1, ['player_games_history', 'player_roll3_mean', 'player_roll8_mean']] = [0, None, None]
        values, metrics = kicker_point_estimates(rows)
        self.assertEqual(values.iloc[1], 0)
        self.assertEqual(metrics['fallback_player_count'], 0)
