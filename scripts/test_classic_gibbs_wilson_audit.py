"""Evidence acceptance tests for the frozen research audit; no database access."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/classic_gibbs_wilson_audit'
class FrozenAuditTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.r=json.loads((OUT/'results.json').read_text())
 def test_source_and_snapshot_integrity(self):
  for key,h in self.r['input_hashes'].items():self.assertEqual(sha256((OUT/(key+'_run.json')).read_bytes()).hexdigest(),h)
  for name,h in self.r['source_files'].items():self.assertEqual(sha256((OUT/'source'/name).read_bytes()).hexdigest(),h)
  self.assertEqual(sha256((OUT/'projection_lineage.json').read_bytes()).hexdigest(),self.r['projection_lineage_hash'])
  self.assertTrue(self.r['identical_ordered_players'])
 def test_all_ten_historical_models_and_rosters_reproduce(self):
  for steps in self.r['sequential'].values():
   self.assertEqual(len(steps),5)
   for step in steps:
    p=step['parity'];self.assertTrue(p['feasible_region_sha256']);self.assertTrue(p['objective_sha256']);self.assertTrue(p['roster_set']);self.assertAlmostEqual(p['objective_delta'],0,places=9)
 def test_all_returned_lineups_have_dk_rosters_and_reconciled_scores(self):
  for label,a in self.r['solves'].items():
   if not a['player_ids']:continue
   self.assertEqual(len(a['player_ids']),9,label);self.assertEqual(len(set(a['player_ids'])),9)
   self.assertLessEqual(a['salary'],50000)
   pos=Counter(p['position'] for p in a['players']);self.assertEqual(pos['QB'],1);self.assertEqual(pos['DST'],1)
   self.assertGreaterEqual(pos['RB'],2);self.assertGreaterEqual(pos['WR'],3);self.assertGreaterEqual(pos['TE'],1)
   self.assertAlmostEqual(a['objective_components']['total'],a['objective_score'],places=7)
   if 'dst_allowed' not in label:
    dst=next(p for p in a['players'] if p['position']=='DST')
    self.assertFalse(any(p['team']==dst['opponent'] for p in a['players'] if p['position']!='DST'))
 def test_forcing_players_and_cap_relaxation_monotonicity(self):
  names={p['name']:p['player_id'] for p in self.r['player_diagnostics']};g=names['Jahmyr Gibbs'];w=names['Garrett Wilson']
  for prefix in ['', 'broad_']:
   for suffix,required in [('B',{g}),('C',{w}),('D',{g,w})]:
    a=self.r['solves'][prefix+suffix];self.assertTrue(required<=set(a['player_ids']))
    self.assertLessEqual(a['objective_score'],self.r['solves'][prefix+'A']['objective_score']+1e-7)
  for variant in ['team_cap4','game_cap5']:
   for s in 'ABC':self.assertGreaterEqual(self.r['solves'][variant+'_'+s]['objective_score']+1e-7,self.r['solves'][s]['objective_score'])
  self.assertEqual(self.r['solves']['tight_Goff_Gibbs']['solver_status'],'Infeasible')
  self.assertTrue(self.r['solves']['team4_Goff_Gibbs']['proven_optimal'])
 def test_all_feasible_solves_have_cbc_optimality_proof(self):
  for name,a in self.r['solves'].items():
   log=(OUT/'solver_logs'/(name+'.log')).read_text()
   if a['player_ids']:
    self.assertTrue(a['proven_optimal']);self.assertIn('Result - Optimal solution found',log)
    self.assertNotIn('Stopped on time',log)
 def test_original_score_reconstruction(self):
  for label,a in self.r['solves'].items():
   if a['player_ids'] and not any(x in label for x in ['no_context','no_correlation']):self.assertAlmostEqual(a['original_objective_rescore'],a['objective_score'],places=7)
 def test_upstream_blend_and_stale_cross_team_evidence(self):
  for name,e in self.r['upstream_evidence'].items():
   f=e['features'];v=(1-f['pregame_opportunity_point_weight'])*f['pregame_point_mean_before_opportunity']+f['pregame_opportunity_point_weight']*f['pregame_opportunity_point_anchor']
   self.assertAlmostEqual(v,f['pregame_point_mean_after_opportunity'],places=7,msg=name)
  history=json.loads((OUT/'opportunity_history.json').read_text())['rows'];p=[x for x in history if x['player_master_id']=='2f86ed70-9abf-429d-bd07-49a0bf22b5ff']
  self.assertEqual({x['team'] for x in p},{'KC'});self.assertEqual({x['season'] for x in p},{2025})
  f=self.r['upstream_evidence']['Jahmyr Gibbs']['features'];self.assertLess(f['carry_share_mean_3'],f['pregame_base_carry_share_mean_3'])
 def test_zero_leverage_and_missing_role_signals_are_actual_inputs(self):
  self.assertTrue(all(p['optimal_lineup_probability'] is None and p['leverage']==0 for p in self.r['player_diagnostics']))
  self.assertTrue(all(p['optimizer_receiving_role_strength']==0 and p['optimizer_rushing_role_strength']==0 for p in self.r['player_diagnostics']))
if __name__=='__main__':unittest.main()
