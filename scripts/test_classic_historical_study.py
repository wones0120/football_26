"""Targeted offline checks for research classification, joins, and time safety."""
import unittest
from copy import deepcopy

from scripts.analyze_classic_historical_study import analyze_contest, build_players, classify, lagged_usage, market_frame


def player(i, pos, tm, opp):
    return {'id':str(i),'position':pos,'team':tm,'opponent':opp,'game':'|'.join(sorted((tm,opp))),
            'salary':5000,'ownership':10,'points':10,'projection':None,'canonical':True,'source_keys':[str(i)]}


class StudyTests(unittest.TestCase):
    def setUp(self):
        self.players=[player(1,'QB','A','B'),player(2,'RB','A','B'),player(3,'WR','A','B'),
            player(4,'WR','A','B'),player(5,'WR','B','A'),player(6,'RB','C','D'),
            player(7,'TE','D','C'),player(8,'RB','E','F'),player(9,'DST','E','F')]

    def test_rb_additive_stack_and_concentration(self):
        f=classify(self.players,{},set())
        self.assertEqual(f['qb_family'],'QB+2PC+1RB')
        self.assertTrue(f['qb_rb_added_to_pc'])
        self.assertEqual(f['qb_team_offense_including_qb'],4)
        self.assertTrue(f['qb_2pc_1bring'])
        self.assertEqual(f['qb_game_all_players'],5)
        self.assertEqual(f['unrelated_oneoffs'],1)
        self.assertEqual(f['true_unrelated_oneoffs'],0)
        self.assertEqual(f['oneoff_dst_same_team_count'],1)
        self.assertTrue(f['secondary_rb_opposing_pc'])
        self.assertTrue(f['two_correlated_environments'])
        self.assertTrue(f['rb_dst_same_team'])
        self.assertEqual(f['flex_position'],'RB')
        self.assertIsNone(f['qb_highest_total'])

    def test_dst_count_separate_and_same_team_pair_not_opposing_mini(self):
        ps=deepcopy(self.players)
        ps[6]=player(7,'TE','C','D')
        ps[8]=player(9,'DST','A','B')
        f=classify(ps,{},set())
        self.assertEqual(f['max_team_all'],5)
        self.assertEqual(f['max_team_offense'],4)
        self.assertFalse(f['secondary_opposing_mini'])
        self.assertEqual(f['secondary_two_player_games'],1)

    def test_slot_constrained_identity_and_ambiguity(self):
        row={'position':'WR','player_name':'John Smith','player_master_id':'a','source_player_key':'1','team':'A','opponent':'B','salary':5000}
        resolve,_=build_players([row],[],{})
        self.assertIsNone(resolve('QB','John Smith'))
        self.assertEqual(resolve('FLEX','John Smith')['id'],'a')
        other={**row,'player_master_id':'b','source_player_key':'2','team':'C','opponent':'D'}
        resolve,_=build_players([row,other],[],{})
        self.assertIsNone(resolve('WR','John Smith'))

    def test_postlock_market_rejected_and_home_spread_sign(self):
        salaries=[{'team':'A','opponent':'B','game_info':'A@B 09/20/2026 01:00PM ET'}]
        row={'season':'2026','week':'2','away_team':'A','home_team':'B','total_line':'50','spread_line':'6'}
        def src(time):
            return {'hash_matches':True,'metadata':{'observed_at':time,'captured_at':time,'snapshot_id':'x'},'rows':[row]}
        markets,info=market_frame(salaries,2026,2,{'market_sources':[src('2026-09-20T14:00:00-04:00')]})
        self.assertFalse(markets)
        markets,info=market_frame(salaries,2026,2,{'market_sources':[src('2026-09-20T12:00:00-04:00')]})
        self.assertEqual(markets['A|B']['team_totals']['B'],28)
        self.assertEqual(markets['A|B']['team_totals']['A'],22)
        self.assertTrue(info['relative_ranks_available'])

    def test_duplicate_entries_unique_rosters_and_ties(self):
        positions=['QB','RB','RB','WR','WR','WR','TE','RB','DST']
        slots=['QB','RB','RB','WR','WR','WR','TE','FLEX','DST']
        salaries=[]
        for i,(pos,slot) in enumerate(zip(positions,slots)):
            salaries.append({'season':2026,'week':2,'slate':'SUNDAY_MAIN','player_name':'P'+str(i),
                'position':pos,'team':'A' if i<4 else 'C','opponent':'B' if i<4 else 'D',
                'source_player_key':str(i),'player_master_id':str(i),'salary':5000,
                'game_info':'A@B 09/20/2026 01:00PM ET'})
        lineup=' '.join(s+' P'+str(i) for i,s in enumerate(slots))
        entry={'lineup_text':lineup,'n':3,'winner':2,'top_01':2,'top_1':2,'top_10':3,'min_points':90,'max_points':90}
        alternate={**entry,'lineup_text':' '.join(reversed([s+' P'+str(i) for i,s in enumerate(slots)])),'n':1,'winner':1,'top_01':1,'top_1':1,'top_10':1}
        payload={'contest':{'season':2026,'week':2,'slate_id':'SUNDAY_NIGHT'},'entries':[entry,alternate],'observations':[],'reviewed':[]}
        result=analyze_contest(payload,{'salaries':salaries},{'projections':{},'market_sources':[]})
        self.assertEqual(result['valid_population_entries']['winner'],3)
        self.assertEqual(result['unique_population_rosters']['winner'],1)
        self.assertEqual(result['unique_population_rosters']['field'],1)
        self.assertTrue(result['scope_corrected'])
        self.assertIn('top 10%',result['success_definition'])

    def test_lagged_usage_excludes_current_and_future_weeks(self):
        rows=[{'season':2025,'week':w,'player_master_id':'p','carries':6 if w<6 else 90,
               'rushing_yards':25,'targets':0} for w in range(1,9)]
        usage=lagged_usage(rows,2025,6)
        self.assertEqual(usage['p']['games'],5)
        self.assertEqual(usage['p']['carries'],6)
        self.assertFalse(lagged_usage(rows,2025,4))


if __name__=='__main__':
    unittest.main()
