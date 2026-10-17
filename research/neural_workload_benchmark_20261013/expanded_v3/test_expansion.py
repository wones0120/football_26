import sys
from copy import deepcopy
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import data as d
import train as t


def row(pid='a',week=1,targets=0,carries=8):
 r={k:np.nan for k in d.TARGETS+d.v2.PRODUCTION+d.DETAIL_RAW+['receiving_first_downs','rushing_first_downs','passing_first_downs','lost_fumbles','touches']}
 r.update(player_master_id=pid,source_player_id='native-'+pid,raw_source_id=week*10+(1 if pid=='a' else 2),source_imported_at='2026-10-13',season=2026,week=week,team='ATL',opponent='NO',position='RB',game_id='game-'+str(week),name=pid,targets=targets,carries=carries,fantasy_points_ppr=4,source_refs=['weekly:'+pid+':'+str(week)])
 return r

def sources(rows):
 stats={(r['player_master_id'],2026,r['week']):r for r in rows};snaps={};tp={};pp={};games={}
 for r in rows:
  k=(r['player_master_id'],2026,r['week']);snaps[k]={'offense_pct':.6,'offense_snaps':35,'source_refs':['snaps:'+r['game_id']]}
  date=pd.Timestamp('2026-09-13T17:00:00Z')+pd.Timedelta(days=7*(r['week']-1));games[r['game_id']]={'completed_at':date+pd.Timedelta(hours=8),'cutoff_at':date-pd.Timedelta(hours=1),'kickoff_at':date,'sunday_main':True}
  pc={'game_id':r['game_id'],'season':2026,'week':r['week'],'source_refs':['pbp:'+r['game_id']]}
  pp[k]=pc|dict(redzone_targets=0,redzone_carries=1,inside5_carries=1,deep_targets=0)
  tp[(2026,r['week'],'ATL')]=pc|dict(plays=60,neutral_passes=20,neutral_plays=40,no_huddles=3,shotguns=30,redzone_passes=3,redzone_plays=10,source_ids=[])
 return stats,snaps,pp,tp,games


def test_expanded_features_never_use_same_week_or_future_results():
 rows=[row(week=1),row(week=2),row(pid='b',week=2,targets=20),row(week=3)]
 original=sources(rows);f,_,_=d.expanded_matrix(*deepcopy(original))
 changed=deepcopy(original);changed[0][('a',2026,2)]['targets']=999;changed[0][('b',2026,2)]['targets']=999
 changed[1][('a',2026,2)]['offense_pct']=.99;changed[2][('a',2026,2)]['redzone_targets']=999;changed[3][(2026,2,'ATL')]['plays']=999
 g,_,_=d.expanded_matrix(*changed)
 pd.testing.assert_frame_equal(f[f.week==2][d.VARIANTS['F3_role_pbp']],g[g.week==2][d.VARIANTS['F3_role_pbp']])
 assert f[f.week==2].max_expanded_source_period.max()==202601


def test_missing_stats_and_observed_zero_are_distinct_and_snap_role_lagged():
 original=sources([row(week=1,targets=np.nan),row(week=2,targets=0),row(week=4)])
 f,_,_=d.expanded_matrix(*original)
 assert np.isnan(f.iloc[1].targets_mean3)
 assert f.iloc[2].targets_mean3==0
 assert f.iloc[2].weeks_since_last==2
 assert f.iloc[1].offense_pct_mean3==.6
 assert f.iloc[1].redzone_targets_mean3==0


def test_completion_after_decision_is_rejected():
 original=sources([row(week=1),row(week=2)])
 original[-1]['game-1']['completed_at']=original[-1]['game-2']['cutoff_at']+pd.Timedelta(hours=1)
 with pytest.raises(ValueError,match='completion clock'):d.expanded_matrix(*original)


def test_gsis_pfr_bridge_rejects_ambiguity_without_name_matching(monkeypatch):
 monkeypatch.setattr(d,'read',lambda _: [{'source_system':'nflreadpy','source_key':'gsis-a','player_master_id':'canonical-a'},{'source_system':'nflreadpy','source_key':'gsis-b','player_master_id':'canonical-b'}])
 monkeypatch.setattr(pd,'read_parquet',lambda _:pd.DataFrame([{'pfr_id':'pfr-a','gsis_id':'gsis-a'},{'pfr_id':'pfr-b','gsis_id':'gsis-a'},{'pfr_id':'pfr-b','gsis_id':'gsis-b'}]))
 native,bridge,audit=d.canonical_maps();assert bridge=={'pfr-a':'gsis-a'};assert native['gsis-a']=='canonical-a';assert audit['ambiguous_pfr_keys']==1
 assert d.team('LA')==d.team('LAR')


def test_equal_features_budget_deterministic_models_and_train_only_scaling():
 rng=np.random.default_rng(261013);columns=d.VARIANTS['F3_role_pbp'];f=pd.DataFrame(rng.normal(size=(160,len(columns))),columns=columns);f['position']='RB';y=np.maximum(0,f.targets_mean3+4)
 assert len(t.CONFIGS['tree'])==len(t.CONFIGS['neural'])==2
 for family,cols in d.VARIANTS.items():
  tree=t.make_model('tree',cols,t.CONFIGS['tree'][0]);nn=t.make_model('neural',cols,t.CONFIGS['neural'][0]);assert tree[0].transformers[0][2]==nn[0].transformers[0][2]==cols
 models=[t.make_model('neural',columns,t.CONFIGS['neural'][0]).fit(f,y) for _ in range(2)]
 assert np.array_equal(models[0].predict(f),models[1].predict(f))
 scaler=models[0][0].named_transformers_['numeric'][1];before=scaler.mean_.copy();probe=f.copy();probe[columns]=1000;models[0].predict(probe);assert np.array_equal(before,scaler.mean_)


def test_test_weeks_never_enter_tuning_or_final_fit():
 f,manifest=t.load();train=f[f.split=='tuning_train'];val=f[f.split=='validation'];final=f[f.final_train];test=f[f.split=='test']
 assert max(train.season*100+train.week)<min(val.season*100+val.week)
 assert max(final.season*100+final.week)==202603
 assert set(zip(test.season,test.week))=={(2026,4),(2026,5)}
 assert set(zip(final.season,final.week)).isdisjoint(set(zip(test.season,test.week)))
 assert all(f.loc[f.max_expanded_source_period.notna(),'max_expanded_source_period']<(f.season*100+f.week)[f.max_expanded_source_period.notna()])
 assert all(pd.to_datetime(f.loc[f.max_expanded_completed_at.notna(),'max_expanded_completed_at'],utc=True)<pd.to_datetime(f.loc[f.max_expanded_completed_at.notna(),'decision_cutoff_at'],utc=True))
 assert len(manifest['games'])==23
 assert not f.duplicated(['player_master_id','season','week']).any()
