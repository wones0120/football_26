from pathlib import Path
from copy import deepcopy
from collections import Counter
from itertools import combinations
import json
P=Path(__file__).resolve().parent
job=json.loads((P/'refreshed_scenarios_saved_run.json').read_text());old=json.loads(Path('research/sunday_accepted_defense_refresh_20261016/v2/saved_run.json').read_text());rosters=deepcopy(job['results']);r=rosters[3]
def unique(rs,team,pos):
 found=[x for x in rs if x['player_team']==team and x['position']==pos];assert len(found)==1;return found[0]
outs=[unique(r,'CAR','RB'),unique(r,'LV','TE'),unique(r,'CAR','DST')];ins=[unique(old['results'][4],'LV','RB'),unique(job['results'][4],'LAR','TE'),unique(job['results'][2],'NYJ','DST')]
assert all(x['player_id'] not in {y['player_id'] for y in r} for x in ins)
alt=[x for x in r if x['player_id'] not in {x['player_id'] for x in outs}]+deepcopy(ins);rosters[3]=alt
ids=lambda rs:frozenset(x['player_id'] for x in rs)
req=json.loads((P/'refreshed_scenarios_request.json').read_text());snap=json.loads((Path('artifacts/preliminary_optimizer_snapshots')/(req['snapshot_sha256']+'.json')).read_text());excluded=set(snap['assumption_manifest']['exclude_player_ids']);rank=job['params']['strategy_runtime']['season_ppg_rank_preference']['eligible_ids']
for rs in rosters:
 assert len(rs)==len(ids(rs))==9 and not ids(rs)&excluded
 assert sum(x['salary'] for x in rs)<=50000
 assert max(Counter(x['player_team'] for x in rs).values())<=3
 assert max(Counter(x['canonical_game_id'] for x in rs).values())<=4
 c=Counter(x['position'] for x in rs);assert c['QB']==c['TE']==c['DST']==1 and c['RB']>=2 and c['WR']>=3 and c['RB']+c['WR']==6
 dst=next(x for x in rs if x['position']=='DST');assert all(x['player_team']!=dst['opponent_team'] for x in rs if x['position']!='DST')
 assert all(x['opponent_team']!='DEN' and not x['entry_ready'] for x in rs)
 assert all(x['player_id'] in rank[x['position']] for x in rs if x['position']!='DST')
assert max(Counter(x['player_id'] for rs in rosters for x in rs).values())<=4
assert max(len(ids(a)&ids(b)) for a,b in combinations(rosters,2))<=5
out=dict(kind='manual_football_review_alternative_not_optimizer_selected_or_new_saved_optimizer_run',saved_parent_run=job['job_id'],replace_entry=4,projection_run_id=job['projection_run_id'],entry_ready=False,validation='PASS_all_saved_portfolio_rules_including80percent_and_overlap5',out_ids=[x['player_id'] for x in outs],in_ids=[x['player_id'] for x in ins],out_names=[x['name'] for x in outs],in_names=[x['name'] for x in ins],alternative=alt,salary=sum(x['salary'] for x in alt),baseline_mean=sum(x['projection'] for x in alt),baseline_mean_delta=sum(x['projection'] for x in alt)-sum(x['projection'] for x in r),full_preferred_review_portfolio=rosters,reason='Prefer an observed primary Jeanty role as LV response to Allen/Shakir rather than relying on secondary Mayer behind cleared Bowers. Higbee+Puka/Kyren use LAR production,with healthy TE competition retained; Jets release300salary at1.691DSTmean cost. No claim of calibrated superiority; no user constraint changed.')
(P/'preferred_review_alternative.json').write_text(json.dumps(out,indent=2)+'\n');print({k:v for k,v in out.items() if k not in ['alternative','full_preferred_review_portfolio']})
