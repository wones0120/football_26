"""Isolated generation experiment; production entry gate is deliberately bypassed only here."""
import json,math
from copy import deepcopy
from pathlib import Path
from contextlib import redirect_stdout
import pandas as pd
from backend.app.db import engine
from backend.app.product_services.optimizer import OptimizerService,_json_safe
from backend.app.product_services.classic_season_rank_preferences import preference
from backend.app.product_services.analyst_scenarios import run_merged
from backend.app.product_services.classic_highest_projection import solve as exact_mean
from backend.app.product_services.analyst_shadow import digest

out=Path(__file__).parent
source=json.loads(Path('artifacts/preliminary_optimizer_snapshots/d4cf2f619a6856bef8d48bd988509a2a6952cc1be181886dddd74210773181e8.json').read_text());packet=json.loads(Path('research/sunday_refresh_20261015/v2/packet.json').read_text());raw=source['pool'];original_hash=digest(raw)
params=dict(num_lineups=5,max_exposure=.8,max_players_per_team=3,max_players_per_game=4,minimum_qb_salary=4500,minimum_rb_salary=4500,exclude_questionable=True,enforce_single_te=True,avoid_dst_opponents=True,analyst_strategy='MERGED_SCENARIOS',analyst_portfolio_mode='SCENARIO_FIRST',analyst_optimization_intent='MIXED',analyst_candidates_per_thesis=2,excluded_opponents=['DEN'],**{'season_ppg_top_pct_'+pos:50 for pos in ['qb','rb','wr','te']})
rank=preference(engine,params,season=2026,week=6);rankids={pos:set(ids) for pos,ids in rank['eligible_ids'].items()};excluded=set(source['assumption_manifest']['exclude_player_ids']);pool=[];exclusions=[]
for r in raw:
 reasons=[];p=r['position'];pid=str(r['player_id'])
 if pid in excluded:reasons.append('frozen_unknown_or_Q_assumption')
 if any(type(r.get(k)) not in (int,float) or not math.isfinite(r[k]) for k in ['projection','p90']):reasons.append('missing_moments')
 if p in rankids and pid not in rankids[p]:reasons.append('user_top50_prior_week_rank')
 if p in ['QB','RB'] and float(r.get('salary') or 0)<4500:reasons.append('user_salary_minimum')
 if r.get('opponent_team')=='DEN':reasons.append('user_opponent_exclusion')
 if str(r.get('availability_status')).upper() in ['Q','QUESTIONABLE','OUT','IR','D','DOUBTFUL','INACTIVE']:reasons.append('frozen_availability')
 if r.get('role_optimizer_eligible') is False or r.get('salary_status_eligible') is False:reasons.append('source_role_or_salary_ineligible')
 if reasons:exclusions.append(dict(player_master_id=pid,reasons=reasons))
 else:pool.append(r)
service=OptimizerService.__new__(OptimizerService)
kwargs=dict(score_col='p90',contest_type='tournament',stack_params=dict(enabled=False,correlation_bonus=0,single_lineup_user_controls={'max_players_per_team':3,'max_players_per_game':4},single_lineup_cutoff=source['data_cutoff_at']),locked_player_ids=set(),enforce_single_te=True,avoid_dst_opponents=True,rule_profile=None,quality_floor=None,include_control_comparison=False)
results={}
for arm,enabled in [('control',False),('opportunity_supported',True)]:
 with (out/(arm+'.log')).open('w') as log,redirect_stdout(log):
  lineups,report=run_merged(service,pd.DataFrame(deepcopy(pool)),params={**params,'analyst_joint_opportunity_enabled':enabled},packet=deepcopy(packet),fmt='CLASSIC',season=2026,week=6,slate='SUNDAY_MAIN',requested=5,solve_kwargs=deepcopy(kwargs),source_pool_rows=deepcopy(raw),research_only_joint_opportunity=enabled)
 result=_json_safe(dict(lineups=lineups,report=report));(out/(arm+'.json')).write_text(json.dumps(result,indent=2,allow_nan=False));results[arm]=result
with (out/'exact_mean.log').open('w') as log,redirect_stdout(log):exact,audit=exact_mean(service,pd.DataFrame(deepcopy(pool)),params=params,cutoff=source['data_cutoff_at'])
(out/'exact_mean.json').write_text(json.dumps(_json_safe(dict(lineups=exact,audit=audit)),indent=2))
assert digest(raw)==original_hash
manifest=dict(classification='INACTIVE_ISOLATED_PRELIMINARY_GENERATION_EXPERIMENT',production_activation=False,normal_readiness=source['normal_readiness']['status'],source_snapshot_sha256=source['sha256'],projection_run_id=source['projection_run_id'],projection_cutoff=source['data_cutoff_at'],source_pool_sha256=original_hash,eligible_pool_sha256=digest(pool),packet_sha256=digest(packet),params=params,rank_eligibility=_json_safe(rank),eligible_count=len(pool),exclusions=exclusions,seed=7,comparison_type='generation experiment; scenario solves use same frozen inputs/constraints/seed, candidate pools can differ because declared objective treatment differs',original_saved_baseline_separate='f84e75db-b286-48f4-8740-c03d11323889 uses different old one-lineup controls, not a matched control',requested=5,achieved={arm:len(v['lineups']) for arm,v in results.items()},constraints_relaxed=False,live_persistence=False)
(out/'manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False));print(json.dumps({k:dict(count=len(v['lineups']),rosters=[dict(names=[p['name'] for p in line],mean=sum(p['projection'] for p in line),salary=sum(p['salary'] for p in line)) for line in v['lineups']]) for k,v in results.items()}))
