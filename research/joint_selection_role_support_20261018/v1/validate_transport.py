"""Fixed context-only versus pregame role-context analog comparison. No fitting/search."""
from pathlib import Path
from collections import defaultdict
import json,math,statistics
from backend.app.product_services.role_transport_support import historical_vector,scale_vectors,role_distance
P=Path(__file__).resolve().parent;lib=json.load(open(P/'historical_templates_v3.json'));games=lib['games']
ctx=lambda g:[g['total_line'],g['home_margin_line'],*[s['qb_prior_carries']for s in g['sides']]]
roles=lambda g:sum([historical_vector(s)for s in g['sides']],[])
def percentile(values,weights,q):
 threshold=sum(weights)*q;total=0
 for v,w in sorted(zip(values,weights)):
  total+=w
  if total>=threshold:return v
 return max(values)
def holder(side,pos):
 ps=[p for p in side['players']if p['position']==pos]
 return max(ps,key=lambda p:(p['prior']['targets']+p['prior']['carries']if pos=='RB'else p['prior']['targets'],p['source_player_id']))if ps else None
predictions=[];attempts=[]
for week in range(10,19):
 targets=sorted([g for g in games if g['week']==week],key=lambda g:g['game_id'])[:2];past=[g for g in games if g['week']<week]
 if len(past)<20:
  attempts.append({'week':week,'status':'insufficient_prior_analog_games','available':len(past)});continue
 cs=scale_vectors([ctx(g)for g in past]);rs=scale_vectors([roles(g)for g in past])
 for target in targets:
  cv=ctx(target);rv=roles(target)
  for treatment in ['context_only','context_and_role']:
   def distance(g):
    base=sum(((s-t)/scale)**2 for s,t,scale in zip(ctx(g),cv,cs))
    return base+(role_distance(roles(g),rv,rs)if treatment=='context_and_role'else 0)
   nearest=sorted(past,key=lambda g:(distance(g),g['game_id']))[:40];dist=[distance(g)for g in nearest];weights=[math.exp(-.5*(d-min(dist)))for d in dist]
   for side_index in [0,1]:
    for pos,channel in [('TE','targets'),('WR','targets'),('RB','carries')]:
     actual_holder=holder(target['sides'][side_index],pos)
     if not actual_holder:continue
     values=[];ws=[]
     for g,w in zip(nearest,weights):
      p=holder(g['sides'][side_index],pos)
      if p is not None:values.append(p['stats'][channel]);ws.append(w)
     actual=actual_holder['stats'][channel];mean=sum(v*w for v,w in zip(values,ws))/sum(ws);p10=percentile(values,ws,.1);p90=percentile(values,ws,.9)
     predictions.append({'game_id':target['game_id'],'week':week,'side':side_index,'position':pos,'treatment':treatment,'actual':actual,'mean':mean,'p10':p10,'p90':p90,'prior_games':len(past),'source_game_ids':[g['game_id']for g in nearest], 'feature_chronology':'Only earlier target-week games in source library, role inputs from preceding three team games'})
def summarize(rows):
 return {'rows':len(rows),'games':len({r['game_id']for r in rows}),'mae':statistics.mean(abs(r['mean']-r['actual'])for r in rows),'bias':statistics.mean(r['mean']-r['actual']for r in rows),'p90_exceedance':statistics.mean(r['actual']>r['p90']for r in rows),'central80_coverage':statistics.mean(r['p10']<=r['actual']<=r['p90']for r in rows)}
out={'predeclared_protocol':'PROTOCOL.md','new_model_fit':False,'retrospective':True,'healthy_role_conditioned':True,'attempts':attempts,'rows':predictions,'summary':{p:{t:summarize([r for r in predictions if r['position']==p and r['treatment']==t])for t in ['context_only','context_and_role']}for p in ['TE','WR','RB']}}
with (P/'transport_temporal_validation.json').open('x')as f:json.dump(out,f,indent=2)
for p,s in out['summary'].items():print(p,s)
