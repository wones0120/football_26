"""Targeted correctness tests for the offline standings analysis."""
import numpy as np
import hashlib
import json
import math
from pathlib import Path
import pytest

from scripts.analyze_showdown_qb_construction import (
    ET, build_resolver, comparison, entry_groups, identify_starters,
    missing_bounds, parse_lineup, prior_qb_stats, tie_payout, timestamp,
    top_counts, weighted_median,
)


def player(identity, position='QB', team='A', salary=10000):
    return {'id':identity,'position':position,'team':team,'flex_salary':salary,'name':identity}


def test_showdown_parser_rejects_classic_and_incomplete():
    assert parse_lineup('QB A RB B RB C WR D WR E WR F TE G FLEX H DST I') is None
    assert parse_lineup('CPT A FLEX B FLEX C FLEX D FLEX E') is None
    assert parse_lineup('prefix CPT A FLEX B FLEX C FLEX D FLEX E FLEX F') is None
    assert parse_lineup('CPT A FLEX B FLEX C FLEX D FLEX E FLEX F') == [('CPT','A'),('FLEX','B'),('FLEX','C'),('FLEX','D'),('FLEX','E'),('FLEX','F')]


def test_tie_boundary_and_fractional_sensitivity():
    counts,fractional=top_counts({'rank':10,'n':4},100,{10:4})
    assert counts['top10']==4
    assert fractional['top10']==1
    assert counts['top01'] is None
    assert top_counts({'rank':11,'n':1},100,{11:1})[0]['top10']==0
    assert top_counts({'rank':1,'n':2},24,{1:2})[0]['top1'] is None


def test_medians_even_and_odd_entry_weighting():
    assert weighted_median([(20,1),(50,1)])==35
    assert weighted_median([(20,2),(50,1)])==20
    assert weighted_median([(20,1)])==20
    assert weighted_median([]) is None


def test_backup_is_never_second_starting_qb():
    a,b,backup=player('a'),player('b',team='B'),player('backup',team='B')
    other=[player(str(i),'WR') for i in range(4)]
    groups,flag=entry_groups(a,[a,backup]+other,[a,b])
    assert 'QB Captain' in groups and flag
    assert 'Both QBs' not in groups and 'Exactly one QB' not in groups
    groups,flag=entry_groups(a,[a,b]+other,[a,b])
    assert 'Both QBs' in groups and 'QB Captain + both QBs' in groups and not flag
    assert 'Both QBs' not in entry_groups(a,[a,b]+other,[a])[0]


def test_missing_identity_never_overrides_conflict_with_alias():
    rows=[{'player_name':'Same','player_master_id':identity,'source_player_key':identity,
           'team':tm,'position':'WR','roster_position':'FLEX','salary':8000}
          for identity,tm in [('one','A'),('two','B')]]
    resolve=build_resolver((2026,1,'s',('A','B')),rows,[])
    assert resolve('FLEX','Same') is None


def test_native_source_id_coalesces_recovered_and_curated():
    base={'player_name':'A','team':'A','position':'QB','salary':10000,'source_player_key':'native','roster_position':'FLEX'}
    resolve=build_resolver((2026,1,'s',('A','B')),[dict(base,player_master_id='canonical'),dict(base,player_master_id=None)],[])
    assert resolve('FLEX','A')['id']=='canonical'


def test_two_slot_native_ids_without_master_use_flex_identity():
    base={'player_name':'A','team':'A','position':'QB','player_master_id':None}
    rows=[dict(base,salary=10000,source_player_key='flex-id',roster_position='FLEX'),
          dict(base,salary=15000,source_player_key='cpt-id',roster_position='CPT')]
    resolve=build_resolver((2026,1,'s',('A','B')),rows,[])
    assert resolve('CPT','A')['id']==resolve('FLEX','A')['id']=='dk:flex-id'


def test_alias_fallback_constrained_to_game_and_season():
    aliases=[{'alias_name':'A','team':'Z','first_seen_season':2025,'player_master_id':'wrong','position':'QB'},
             {'alias_name':'A','team':'A','first_seen_season':2027,'player_master_id':'future','position':'QB'}]
    assert build_resolver((2026,1,'s',('A','B')),[],aliases)('CPT','A') is None


def test_prior_stats_exclude_current_future_and_repeated_imports():
    stats=[{'season':s,'week':w,'player_master_id':'a','raw_row_json':{'attempts':att,'carries':2}}
           for s,w,att in [(2026,4,100),(2026,3,30),(2026,3,40),(2026,5,200),(2026,2,20)]]
    prior=prior_qb_stats(stats,'a',2026,4)
    assert prior['attempts']==25 and prior['games']==2 and prior['last_prior_game']==[2026,3]


def test_after_lock_starter_needs_independent_prior_inference():
    rows=[{'position':'QB','player_name':'a'},{'position':'QB','player_name':'b'}]
    qb={'a':player('a'), 'b':player('b',team='B')}
    resolver=lambda slot,name:qb[name]
    evidence=[{'season':2026,'week':1,'slate':'s','team':'A','status':'available','created_at':'2026-09-10 21:00:00',
               'updated_at':'2026-09-10 21:00:00','evidence_json':{'observed_at':'2026-09-10T10:00:00-04:00'},
               'player_master_id':'a','player_name':'a','evidence_tier':'confirmed','source':'manual'}]
    result,rejected=identify_starters((2026,1,'s',('A','B')),rows,resolver,
        {'lock':timestamp('2026-09-10T20:15:00-04:00')},{'starters':evidence},[])
    assert result==[] and any('after lock' in r['reason'] for r in rejected)


def test_cash_ties_split_occupied_prize_positions():
    assert tie_payout(1,2,{1:200,2:100})==150
    assert tie_payout(2,3,{1:200,2:100,3:50})==50


def test_missing_roster_success_bounds_use_success_and_failure_separately():
    c={'contest_id':'c','game_key':'g','season':2026,'loaded_entries':100,'starters':[]}
    rows=[{'n':90,'groups':['QB Captain'],'counts':{'top10':9,'top1':1,'winner':1}}]
    unknown=[{'n':10,'counts':{'top10':1,'top1':0,'winner':0}}]
    r=missing_bounds(c,rows,unknown,'QB Captain')
    assert r['all_entry_usage_lower']==.9 and r['all_entry_usage_upper']==1
    assert r['top10_rate_lower']==9/99 and r['top10_rate_upper']==10/91
    assert missing_bounds(c,rows,unknown,'Both QBs') is None


def test_cluster_comparison_ignores_unpaired_games():
    rows=[{'group':group,'contest_id':cid,'game_key':game,'entries':100,'top10_count':success,
           'top10_rate':success/100} for cid,game,group,success in
          [('c1','g1','QB Captain',20),('c1','g1','Non-QB Captain',10),
           ('c2','g2','QB Captain',30),('c2','g2','Non-QB Captain',20)]]
    draws=np.array([['g1','unpaired'],['g2','unpaired']])
    r=comparison(rows,'QB Captain','Non-QB Captain','top10',draws)
    assert r['paired_games']==2 and r['game_sign_flip_p']==.5
    assert all(np.isfinite(v) for v in r['absolute_difference_game_bootstrap_95'])


def test_saved_research_partitions_and_input_integrity():
    out=Path(__file__).resolve().parents[1]/'artifacts/showdown_qb_construction'
    if not (out/'analysis.json').exists():pytest.skip('Research snapshot not present')
    d=json.loads((out/'analysis.json').read_text())
    summary={r['group']:r for r in d['entry_weighted'] if r['season']=='pooled'}
    assert sum(summary[g]['entries'] for g in ['QB Captain','Non-QB Captain'])==d['inventory']['resolved_entries']
    assert sum(summary[g]['entries'] for g in ['Both QBs','Exactly one QB','Zero QB'])==d['inventory']['starter_eligible_entries']
    combos=['QB Captain + both QBs','QB Captain + one QB','Non-QB Captain + both QBs','Non-QB Captain + one QB','Non-QB Captain + zero QB']
    assert sum(summary[g]['entries'] for g in combos)==d['inventory']['starter_eligible_entries']
    assert sum(summary['CPT '+p]['entries'] for p in ['QB','RB','WR','TE','DST','K'])==d['inventory']['resolved_entries']
    assert sum(summary[g]['winner_count'] for g in ['QB Captain','Non-QB Captain'])==sum(r['first_place_tie_size'] for r in d['contest_audits'])
    for name,expected in d['analysis_input_hashes'].items():
        assert hashlib.sha256((out/'inputs'/name).read_bytes()).hexdigest()==expected
    def finite(value):
        if isinstance(value,float):assert math.isfinite(value)
        elif isinstance(value,dict):
            for v in value.values():finite(v)
        elif isinstance(value,list):
            for v in value:finite(v)
    finite(d)
