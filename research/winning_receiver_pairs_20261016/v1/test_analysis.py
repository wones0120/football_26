import importlib.util
from pathlib import Path
from collections import Counter
import pytest
spec=importlib.util.spec_from_file_location('winner_study',Path(__file__).with_name('analyze.py'));a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
def roster(wrs=('TEN','TEN','LAR'),qb='LAR',te='BUF',flexpos='RB',flexteam='CAR'):
 return [dict(id=str(i),position=p,team=t,salary=4000,canonical=True) for i,(p,t) in enumerate([('QB',qb),('RB','BUF'),('RB','LAR'),*[('WR',t) for t in wrs],('TE',te),(flexpos,flexteam),('DST','IND')])]
def test_two_receivers_means_natural_wr_including_flex():
 flags,wr,qb=a.classify(roster());assert flags['two_wr'] and flags['exactly_two_wr_max'] and flags['two_wr_without_own_qb']
 flags,_,_=a.classify(roster(wrs=('TEN','LAR','BUF'),flexpos='WR',flexteam='TEN'));assert flags['two_wr']
def test_wr_te_separate_and_own_qb_partition():
 flags,_,_=a.classify(roster(wrs=('TEN','LAR','BUF'),qb='TEN',te='TEN'));assert not flags['two_wr'];assert flags['wr_te'] and flags['two_passcatchers']
 flags,_,_=a.classify(roster(qb='TEN'));assert flags['two_wr_with_own_qb'] and not flags['two_wr_without_own_qb']
def test_exactly_two_and_three_plus_not_conflated():
 flags,_,_=a.classify(roster(wrs=('TEN','TEN','TEN')));assert flags['two_wr'] and flags['three_plus_wr'];assert not flags['exactly_two_wr_max']
def test_invalid_showdown_or_duplicate_identity_rejected():
 assert a.parse('CPT A FLEX B',lambda s,n:None)[1]=='not_legal_classic_slots'
 line='QB A RB B RB C WR D WR E WR F TE G FLEX H DST I'
 assert a.parse(line,lambda s,n:dict(id='same',canonical=True,salary=4000))[1]=='duplicate_canonical_player'
 assert a.parse(line,lambda s,n:dict(id=n,canonical=False,salary=4000))[1]=='canonical_identity_unresolved'
def test_scoped_resolver_keeps_effective_team_and_rejects_ambiguous_native():
 from scripts.analyze_classic_historical_study import build_players
 s=dict(player_name="Wan'Dale Robinson",position='WR',team='TEN',opponent='IND',source_player_key='2026-native',player_master_id='uuid',salary=4500)
 resolve,_=build_players([s],[],{});assert resolve('FLEX',"Wan'Dale Robinson")['team']=='TEN'
 resolve,_=build_players([s,{**s,'player_master_id':'other','team':'NYG','source_player_key':'old-native'}],[],{});assert resolve('WR',"Wan'Dale Robinson") is None
def test_actual_frozen_cohorts_keep_ties_unknowns_and_qb_partition():
 import json,math
 r=json.loads(Path(__file__).with_name('results.json').read_text());cs=[c for c in r['contests'] if c['contest']['season']==2026]
 assert sum(c['cohorts']['winner']['raw_entries'] for c in cs)==15
 assert sum(c['cohorts']['winner']['unique_rosters'] for c in cs)==13
 assert sum(c['cohorts']['top_1']['raw_entries']-c['cohorts']['top_1']['valid_entries'] for c in cs)==1
 for c in cs:
  assert c['cohorts']['field']['raw_entries']==c['contest']['field_size']
  assert c['cohorts']['top_1']['raw_entries']>=math.ceil(c['contest']['field_size']*.01)
  for pop in a.POPS:
   v=c['cohorts'][pop]['entry'];assert v.get('two_wr',0)==v.get('two_wr_with_own_qb',0)+v.get('two_wr_without_own_qb',0)
  assert len(c['actual_qbs'])==2*c['pool_games']
