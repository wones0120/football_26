import unittest

import pandas as pd

from backend.app.product_services.contest_ownership_identity import resolve_observations
from backend.app.product_services.ownership import OwnershipService


class ContestOwnershipIdentityTests(unittest.TestCase):
    def salary(self, **changes):
        return dict(curated_salary_id=1, ingest_run_id='run', source_player_key='dk1',
                    player_master_id='canonical1', player_name='Player A', team='SEA',
                    opponent='NE', position='WR', roster_position='FLEX', **changes)

    def rows(self):
        return pd.DataFrame([dict(season=2026, week=1, slate='NIGHT', contest_id='c1',
                                  source_file_id='s1', entry_id='e1', player_display_name='Player A',
                                  roster_position=slot, pct_drafted=pct)
                             for slot, pct in [('CPT', 5), ('FLEX', 30)]])

    def test_native_salary_evidence_resolves_separate_captain_and_flex(self):
        salaries=pd.DataFrame([self.salary(), {**self.salary(), 'source_player_key':'dk2', 'roster_position':'CPT'}])
        resolved=resolve_observations(self.rows(), salaries)
        self.assertEqual(resolved.resolution_status.tolist(), ['resolved', 'resolved'])
        built=OwnershipService(connection_string='sqlite:///:memory:')._build_ownership(resolved)
        self.assertEqual(dict(zip(built.roster_position,built.actual_ownership)), {'CPT':5,'FLEX':30})
        self.assertTrue(built.projected_ownership.isna().all())

    def test_missing_canonical_stays_in_review(self):
        salary={**self.salary(),'player_master_id':None}
        result=resolve_observations(self.rows(),pd.DataFrame([salary]))
        self.assertTrue(result.player_id.isna().all())
        self.assertEqual(result.resolution_status.tolist(), ['unresolved','unresolved'])
        self.assertEqual(result.iloc[1].identity_evidence['salary_candidates'][0]['source_player_key'],'dk1')

    def test_name_collision_does_not_choose_a_team(self):
        salary2={**self.salary(),'player_master_id':'canonical2','team':'NE','opponent':'SEA'}
        result=resolve_observations(self.rows(),pd.DataFrame([self.salary(),salary2]))
        self.assertEqual(result.iloc[1].resolution_status,'ambiguous')
        self.assertIsNone(result.iloc[1].player_id)

    def test_conflicting_percentage_is_rejected(self):
        rows=self.rows().iloc[[1,1]].copy()
        rows['player_id']='p1'; rows['player_master_id']='p1'
        rows['pct_drafted']=[20,30]
        with self.assertRaisesRegex(ValueError,'Conflicting ownership'):
            OwnershipService(connection_string='sqlite:///:memory:')._build_ownership(rows)

    def test_classic_flex_does_not_resolve_quarterback(self):
        salary={**self.salary(),'position':'QB','roster_position':'QB'}
        result=resolve_observations(self.rows(),pd.DataFrame([salary]))
        self.assertTrue(result.player_id.isna().all())
