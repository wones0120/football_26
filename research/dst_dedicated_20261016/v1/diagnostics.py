"""Component-conditioned total error and per-week rank evidence; no extra fitting."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
P=Path(__file__).resolve().parent
rows=pd.DataFrame(json.loads((P/'heldout_predictions.json').read_text()))
events=pd.DataFrame(json.loads(Path('research/dst_scoring_repair_20261015/v1/scored_games.json').read_text()))
events['season']=events.game_id.str.split('_').str[0].astype(int)
events['week']=events.game_id.str.split('_').str[1].astype(int)
events['td']=events.components.map(lambda x:x['defensive_touchdowns']+x['special_teams_touchdowns'])
events['sacks']=events.components.map(lambda x:x['sacks'])
events['takeaways']=events.components.map(lambda x:x['interceptions']+x['fumble_recoveries'])
rows=rows.merge(events[['season','week','player_master_id','td','sacks','takeaways']],on=['season','week','player_master_id'],validate='many_to_one')
strata={}
for name,mask in [('negative_actual',rows.actual<0),('verified_zero',rows.actual==0),('actual_15_plus',rows.actual>=15),
                  ('defensive_or_ST_TD',rows.td>0),('no_defensive_or_ST_TD',rows.td==0),('three_plus_sacks',rows.sacks>=3),
                  ('two_plus_takeaways',rows.takeaways>=2)]:
    strata[name]={}
    for arm,group in rows[mask].groupby('arm'):
        err=group.prediction-group.actual
        strata[name][arm]=dict(n=len(group),mae=float(abs(err).mean()),rmse=float(np.sqrt((err**2).mean())),bias=float(err.mean()))
weeks=[]
for (season,week),group in rows.groupby(['season','week']):
    record=dict(season=int(season),week=int(week))
    for arm,values in group.groupby('arm'):
        record[arm]=dict(n=len(values),mae=float(abs(values.prediction-values.actual).mean()),
            spearman=float(spearmanr(values.prediction,values.actual).statistic) if values.prediction.nunique()>1 and values.actual.nunique()>1 else 0.)
    weeks.append(record)
(P/'diagnostics.json').write_text(json.dumps(dict(total_score_error_strata=strata,weekly_rank_and_error=weeks,
    note='No component heads are trained; these are total-point errors conditioned on observed components. Future median shadow ties all20DST, not a new rank signal.'),indent=2)+'\n')
print(json.dumps(strata,indent=2))
