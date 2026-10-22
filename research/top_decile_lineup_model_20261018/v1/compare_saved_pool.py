"""Matched frozen candidate pool; research utilities never overwrite projections."""
from collections import Counter
from copy import deepcopy
import hashlib,json,pathlib
from backend.app.product_services.lineup_top_decile_research import lineup_features,predict_artifact
from backend.app.product_services.scenario_breadth import select_pool,signature
from backend.app.product_services.scenario_breadth_replay import game_dependencies
P=pathlib.Path(__file__).resolve().parent
replay=json.loads(pathlib.Path('research/scenario_candidate_breadth_20261018/v1/comparison.json').read_text())
saved=json.load(open('/private/tmp/sunday_actual_review_20261018/main_saved.json'));source=next(r for r in json.load(open('/private/tmp/sunday_actual_review_20261018/stored_run_configs.json'))if r['optimizer_run_id']==replay['source_optimizer_run_id'])
config=source['constraint_config_json'];report=config['strategy_runtime']['football_analyst'];snapshot=report['input_snapshot'];rows=snapshot['players'];pool=replay['candidates'];ids={i['idea_id']for i in report['scenario_allocation_plan']['ideas']};worlds=[w for w in report['scenario_definitions']if w['scenario_id']in ids]
pred={p['player_id']:p for p in json.load(open('/private/tmp/season_accuracy_20261018/projections.json'))if p['projection_run_id']==saved['projection_run_id']}
features={(f['projection_run_id'],f['player_id'],f['game_id']):f for f in json.loads((P/'historical_features_v2.json').read_text())}
actuals={r['player_id']:r['actual_points']for r in json.load(open('/private/tmp/season_accuracy_20261018/actuals.json'))if r['contest_id']=='196653899'}
context=next(c for c in json.loads((P/'dataset_inventory_v2.json').read_text())if c.get('contest_id')=='196653899');cutoff=context['points_cutoff']
lookup={r['player_master_id']:r for r in rows}
def score_actual(c):
 ps=[p['player_master_id']for p in c['roster']]
 return round(sum(actuals[pid]for pid in ps),2)if all(pid in actuals for pid in ps)else None
def summary(cs):
 counts=Counter(p['player_master_id']for c in cs for p in c['roster']);out=[]
 for c in cs:out.append({**c,'actual_points_retrospective_only':score_actual(c),'observed_field_top10_label':int(score_actual(c)>=cutoff)if score_actual(c)is not None else None})
 return dict(selected=out,achieved=len(cs),summed_baseline_mean=sum(c['baseline_mean']for c in cs),max_player_appearances=max(counts.values(),default=0),dependencies=game_dependencies(cs,rows),observed_top10_hits=sum(score_actual(c)>=cutoff for c in cs if score_actual(c)is not None))
result=dict(contract_id='top_decile_model_matched_pool_comparison_v1',source_replay_id=replay['replay_id'],source_optimizer_run_id=replay['source_optimizer_run_id'],source_projection_run_id=saved['projection_run_id'],settings_sha256=replay['settings_sha256'],candidate_variants=len(pool),distinct_canonical_rosters=len({signature(c)for c in pool}),models={},original=summary(replay['original_selected']),highest_mean_control=summary(replay['highest_baseline_mean_control']),observed_top10_cutoff=cutoff,retrospective=True,probabilities_calibrated=False,live_promoted=False,disclosure='Model fits trainW1–5; Week6 outcomes previously inspected. Features use exact original raw projection run, original pregame feature snapshot and frozen salary/team/position. Prepared baseline means retained separately; no projection edits. Actuals only appended after utility selection.')
for rich in [False,True]:
 name='classic_'+('rich'if rich else'core')+'_train_before_w6';model=json.loads((P/'models'/(name+'.json')).read_text());utilities=[]
 assert max(model['train_weeks'])<6
 for c in pool:
  ps=[]
  for p in c['roster']:
   pid=p['player_master_id'];raw=pred[pid];r=lookup[pid];f=features[(saved['projection_run_id'],pid,raw['game_id'])]
   ps.append(dict(player_id=pid,role='SELECTED',position=r['position'],team=r.get('player_team',r.get('team')),game_id=raw['game_id'],salary=float(r['salary']),mean=float(raw['mean']),p90=float(raw['p90']),features=f))
  values=lineup_features(ps,'classic',rich=rich);utilities.append(predict_artifact(model,values))
 selected,selection=select_pool(deepcopy(pool),worlds,rows,{**config,'data_cutoff_at':snapshot['decision_at']},5,report['scenario_allocation_plan'],objective='EXTERNAL_LINEUP_SCORE',candidate_utilities=utilities)
 by_id={c['candidate_id']:u for c,u in zip(pool,utilities)}
 for c in selected:c['research_lineup_model_score']=by_id[c['candidate_id']]
 result['models'][name]={**summary(selected),'selection':selection,'score_basis':'uncalibrated complete-lineup top-decile propensity research utility, not paid-finish/win probability','candidate_scores':by_id,'model_sha256':hashlib.sha256((P/'models'/(name+'.json')).read_bytes()).hexdigest()}
result['candidate_coverage_upper_bound']={'scoreable_distinct_rosters':len({signature(c)for c in pool if score_actual(c)is not None}),'distinct_top10_rosters':len({signature(c)for c in pool if score_actual(c)is not None and score_actual(c)>=cutoff}),'maximum_top10_hits_for_five_ignoring_portfolio_conflicts':min(5,len({signature(c)for c in pool if score_actual(c)is not None and score_actual(c)>=cutoff}))}
(P/'saved_pool_comparison.json').write_text(json.dumps(result,indent=2))
print('upperbound',result['candidate_coverage_upper_bound'])
for name,x in result['models'].items():
 print(name,'hits',x['observed_top10_hits'],'mean',x['summed_baseline_mean'],'Rams',x['dependencies']['offense_game_appearance_counts'].get('2026_06_ARI_LA'))
 for c in x['selected']:print(c['salary'],round(c['baseline_mean'],3),round(c['research_lineup_model_score'],3),c['actual_points_retrospective_only'],[p['name']for p in c['roster']])
