"""Focused offline checks. These never access the database or select by outcomes."""
from copy import deepcopy
import ast
import json
import unittest

from .experiment import (OUT, signature, deduplicate, reconstruct, solve,
                         validate_portfolio, actuals, quantized, budgets)

def candidate(captain='a',score=10,rank=1,scenario='baseline'):
    return dict(players=[dict(player_id=p,slot='CPT' if p==captain else 'FLEX',team='A' if p in 'abc' else 'B') for p in 'abcdef'],
                selector=score,rank=rank,scenario_id=scenario,mean=6.5,p90=13,salary=30000,
                captain_objective_multiplier=1,correlation=0)

class FixedPoolChecks(unittest.TestCase):
    def test_captain_identity_is_part_of_signature(self):
        self.assertNotEqual(signature(candidate('a')),signature(candidate('b')))
        self.assertEqual(len(deduplicate([candidate('a'),candidate('b',rank=2)])),2)

    def test_variant_resolution_is_outcome_independent(self):
        rows=[candidate(score=12,rank=3,scenario='win'),candidate(score=10),candidate(score=12,rank=2)]
        self.assertEqual(deduplicate(rows)[0]['rank'],2)
        self.assertEqual(deduplicate(list(reversed(rows)))[0]['rank'],2)

    def test_conflicting_variant_forecasts_fail_closed(self):
        row=candidate(rank=2);row['mean']=7
        with self.assertRaises(ValueError):
            deduplicate([candidate(),row])

    def test_invalid_duplicate_player_rejected(self):
        row=candidate();row['players'][-1]['player_id']='a'
        with self.assertRaises(ValueError):
            signature(row)

    def test_current_objective_role_multiplier_once(self):
        row=candidate()
        players={p:dict(player_id=p,projection=1,p90=2,optimizer_context_adjustment=0,position='WR',team='A',included=True) for p in 'abcdef'}
        score=reconstruct(row,players)
        self.assertEqual(score['current_score'],8)
        self.assertEqual(score['mean_score'],6.5)
        self.assertEqual(score['p90_score'],13)

    def test_source_objective_matches_reconstructed_formula(self):
        path=OUT/'inputs/code/backend/app/product_services/optimizer.py'
        tree=ast.parse(path.read_text())
        expressions=[ast.unparse(n.value) for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='objective_expression' for t in n.targets)]
        self.assertTrue(any('showdown_captain_p90' in e and 'showdown_flex_mean' in e and '1.5' in e for e in expressions))

    def test_constraints_and_explicit_infeasibility(self):
        rows=deduplicate([candidate('a'),candidate('b',rank=2)])
        limits={p:1 for p in 'abcdef'}
        self.assertEqual(solve(rows,limits,1,5)['count'],1)
        self.assertIsNone(solve(rows,limits,1,5,score='selector',size=2))
        with self.assertRaises(AssertionError):
            validate_portfolio(rows,limits,1,2)

    def test_request_denominator_not_realized_size(self):
        source=json.loads((OUT/'inputs/3a41af88-a28c-41b1-888c-462ddcd7d74d.json').read_text())
        config=source['run']['constraint_config_json']
        limits,captain,requested=budgets(config,config['strategy_runtime'])
        self.assertEqual(requested,5)
        self.assertEqual(captain,3)
        self.assertEqual(limits['1f90d290-afb4-48ae-8052-fa99040b8ddb'],4)

    def test_original_replays_and_objective_reconstruction(self):
        verification=json.loads((OUT/'verification.json').read_text())
        for r in verification['runs']:
            self.assertTrue(r['historical_physical_match'])
            self.assertAlmostEqual(r['historical_objective'],r['replay_objective'],places=6)
            self.assertLess(r['historical_additive_reconstruction']['max_abs_corrected_residual'],1e-7)
        self.assertEqual(verification['runs'][0]['common_size'],4)
        self.assertEqual([r['common_size'] for r in verification['runs'][1:5]],[5]*4)
        self.assertEqual(verification['runs'][-1]['chronology']['status'],'unverified')

    def test_quantization_and_tied_portfolio_stability(self):
        rows=deduplicate([candidate('b',rank=2),candidate('a')])
        limits={p:1 for p in 'abcdef'}
        left=solve(rows,limits,1,5,score='selector',size=1,stable=True)
        right=solve(rows,limits,1,5,score='selector',size=1,stable=True)
        self.assertEqual(left['rows'],right['rows'])
        self.assertEqual(quantized(1.0000005),1000000)

    def test_repeated_contests_and_cpt_actuals(self):
        rows=[dict(player_id='a',actual_points=15,roster_position='CPT',resolution_status='resolved'),
              dict(player_id='a',actual_points=10,roster_position='FLEX',resolution_status='resolved')]
        self.assertEqual(actuals(rows*3),({'a':10.0},[]))
        rows.append(dict(player_id='a',actual_points=11,roster_position='FLEX',resolution_status='resolved'))
        self.assertEqual(actuals(rows),({},['a']))

if __name__=='__main__':
    unittest.main()
