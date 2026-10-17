import json
from pathlib import Path
import unittest
from validator import validate

class PacketTests(unittest.TestCase):
    def setUp(self):
        self.packet = json.loads((Path(__file__).parent/'packet.json').read_text())
    def rejected(self, fragment):
        self.assertTrue(any(fragment in error for error in validate(self.packet)), validate(self.packet))
    def test_malformed_array(self):
        self.packet['sources'] = None
        self.rejected('expected array of objects')
    def test_invalid_kickoff_clock_rejected_without_crash(self):
        self.packet['games'][0]['kickoff_at'] = 'invalid'
        self.rejected('missing timezone clock')
    def test_numeric_uncertainty(self):
        self.packet['hypotheses'][0]['uncertainty'] = 0.8
        self.rejected('unquantified text')
    def test_valid_pregame_packet(self):
        self.assertEqual(validate(self.packet), [])
    def test_unknown_identity(self):
        self.packet['hypotheses'][0]['player_master_ids'] = ['unresolved']
        self.rejected('hypothesis player')
    def test_malformed_canonical_id(self):
        self.packet['players'][0]['player_master_id'] = 'name-only'
        self.rejected('canonical player identity')
    def test_missing_native_identity(self):
        self.packet['players'][0]['source_native_key'] = None
        self.rejected('native identity key')
    def test_missing_clock(self):
        self.packet['sources'][0]['available_at'] = None
        self.rejected('missing timezone clock')
    def test_naive_clock(self):
        self.packet['sources'][0]['available_at'] = '2026-10-13T12:00:00'
        self.rejected('missing timezone clock')
    def test_future_source(self):
        self.packet['sources'][0]['available_at'] = '2026-10-15T12:00:00Z'
        self.rejected('available after decision')
    def test_postgame_decision(self):
        self.packet['decision_at'] = self.packet['frozen_at'] = '2026-10-16T02:00:00Z'
        self.rejected('not pregame')
    def test_unknown_scope(self):
        self.packet['hypotheses'][0]['game_id'] = 'UNKNOWN'
        self.rejected('game scope')
    def test_thursday_not_sunday_main(self):
        self.packet['hypotheses'][0]['formats'] = ['CLASSIC']
        self.rejected('format not in game scope')
    def test_both_format_contract_with_confirmed_classic_scope(self):
        self.packet['games'][0]['format_membership']['CLASSIC'] = 'confirmed_in_scope'
        self.packet['hypotheses'][0]['formats'] = ['CLASSIC', 'SHOWDOWN']
        self.assertEqual(validate(self.packet), [])
    def test_numeric_adjustment(self):
        self.packet['hypotheses'][0]['numeric_effect_proposal'] = {'targets':2}
        self.rejected('numeric workload')
    def test_arbitrary_probability(self):
        self.packet['hypotheses'][0]['probability'] = 0.7
        self.rejected('numeric hypothesis')
    def test_conditional_in_baseline(self):
        self.packet['baseline_facts'][0]['kind'] = 'conditional_assumption'
        self.rejected('conditional assumption in baseline')
    def test_missing_contrary_evidence(self):
        self.packet['hypotheses'][0]['contrary_evidence'] = []
        self.rejected('contrary_evidence')
    def test_unsupported_action(self):
        self.packet['hypotheses'][1]['action'] = 'increase_projection'
        self.rejected('abstain from action')
    def test_unavailable_source_cannot_support_actionable_monitor(self):
        self.packet['sources'][0]['coverage'] = 'unavailable'
        self.rejected('source coverage unavailable')
    def test_baseline_unchanged(self):
        self.packet['baseline_mutation'] = True
        self.rejected('baseline mutation')
    def test_filled_zero_is_not_measurement(self):
        self.packet['players'][0]['workload_evidence']['historical'] = {'targets_mean_3':{'value':0,'stored_value':0,'status':'observed','available':False}}
        self.rejected('measurement flag')
        self.rejected('measured zero')
    def test_expired_hypothesis(self):
        self.packet['hypotheses'][0]['expires_at'] = '2026-10-12T12:00:00Z'
        self.rejected('expired')
    def test_missing_evidence(self):
        self.packet['hypotheses'][0]['source_ids'] = []
        self.rejected('missing source references')
    def test_unknown_source(self):
        self.packet['hypotheses'][0]['source_ids'] = ['UNKNOWN']
        self.rejected('unknown source')

if __name__ == '__main__':
    unittest.main()
