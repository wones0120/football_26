"""Frozen counts-only role-relative-shock test. No fits or lineup solves."""
from pathlib import Path
from collections import defaultdict
import json, math, statistics, hashlib
from backend.app.product_services.relative_role_transport import allocate
from backend.app.product_services.role_transport_support import scale_vectors
P=Path(__file__).resolve().parent
lib=json.load(open(P/'historical_templates_v3.json'))['games']
raw=json.load(open(P.parents[1]/'joint_portfolio_selection_20261018/v1/historical_stats.json'))
by_team=defaultdict(lambda:defaultdict(list)); by_game=defaultdict(list)
for r in raw:
    by_team['LAR' if r['team']=='LA' else r['team']][r['game_id']].append(r)
    by_game[(r['game_id'],'LAR' if r['team']=='LA' else r['team'])].append(r)

def prior(team,week):
    games=sorted([(max(r['week'] for r in rows),g,rows) for g,rows in by_team[team].items() if max(r['week'] for r in rows)<week],reverse=True)[:3]
    if len(games)!=3:return None
    players={}
    for _,_,rows in games:
        for r in rows:
            p=players.setdefault(r['player_id'],dict(id=r['player_id'],position=r['position'],targets=0.,carries=0.))
            for channel in ('targets','carries'):p[channel]+=r['raw_row_json'][channel]/3
    return list(players.values())

def observed(game,side,channel):
    return {r['player_id']:r['raw_row_json'][channel] for r in by_game[(game['game_id'],side['team'])]}

def leader(rows,pos):
    ps=[r for r in rows if r['position']==pos and r['targets' if pos!='RB' else 'carries']>0]
    return min(ps,key=lambda r:(-(r['targets']+r['carries'] if pos=='RB' else r['targets']),r['id'])) if ps else None

def quantile(v,w,q):
    so=sorted(zip(v,w)); cut=sum(w)*q; acc=0
    for a,b in so:
        acc+=b
        if acc>=cut:return a
    return so[-1][0]

def summary(rows):
    return dict(rows=len(rows),games=len({r['game_id']for r in rows}),mae=statistics.mean(abs(r['mean']-r['actual'])for r in rows),bias=statistics.mean(r['mean']-r['actual']for r in rows),p90_exceedance=statistics.mean(r['actual']>r['p90']for r in rows),central80_coverage=statistics.mean(r['p10']<=r['actual']<=r['p90']for r in rows))
ctx=lambda g:[g['total_line'],g['home_margin_line'],*[s['qb_prior_carries']for s in g['sides']]]
previous={r['game_id']for r in json.load(open(P/'transport_temporal_validation.json'))['rows']}
targets=sorted([g for g in lib if g['week']>=10 and g['game_id']not in previous],key=lambda g:(g['week'],g['game_id']))
assert len(targets)==36
rows=[];audit=[];skipped=[]
for target in targets:
    past=[g for g in lib if g['week']<target['week']]
    scales=scale_vectors([ctx(g)for g in past])
    distance=lambda g:sum(((s-t)/scale)**2 for s,t,scale in zip(ctx(g),ctx(target),scales))
    nearest=sorted(past,key=lambda g:(distance(g),g['game_id']))[:40]
    ds=[distance(g)for g in nearest];weights=[math.exp(-.5*(d-min(ds)))for d in ds]
    for si,side in enumerate(target['sides']):
        current=prior(side['team'],target['week'])
        if current is None:raise ValueError('Missing current prior games')
        for pos,channel in [('TE','targets'),('WR','targets'),('RB','carries')]:
            cp=leader(current,pos)
            if cp is None:skipped.append([target['game_id'],si,pos,'no_positive_prior_role']);continue
            # Active-zero rows are explicitly present in accepted templates.
            active={p['source_player_id']:p for p in side['players']}
            if cp['id'] not in active:skipped.append([target['game_id'],si,pos,'no_observed_active_stat_evidence']);continue
            actual=active[cp['id']]['stats'][channel]
            values={'absolute_rank':[],'relative_shock':[]};ws=[]
            for src,w in zip(nearest,weights):
                ss=src['sides'][si];sp=prior(ss['team'],src['week'])
                if sp is None:continue
                actual_src=observed(src,ss,channel)
                allocation=allocate(current,sp,actual_src,channel)
                srole=leader(sp,pos)
                if srole is None:continue
                # Complete source team stat universe contains every credited
                # opportunity; absent prior-role actors add zero credited count.
                values['absolute_rank'].append(actual_src.get(srole['id'],0))
                values['relative_shock'].append(allocation['counts'].get(cp['id'],0))
                ws.append(w)
                error=abs(sum(allocation['counts'].values())+allocation['residual']-allocation['budget'])
                assert error<1e-8
                audit.append(dict(target=target['game_id'],source=src['game_id'],side=si,channel=channel,residual_share=allocation['residual']/allocation['budget']if allocation['budget']else 0,conservation_error=error))
            for treatment,vs in values.items():
                rows.append(dict(game_id=target['game_id'],week=target['week'],side=si,position=pos,player_native_id=cp['id'],treatment=treatment,actual=actual,mean=sum(v*w for v,w in zip(vs,ws))/sum(ws),p10=quantile(vs,ws,.1),p90=quantile(vs,ws,.9),source_game_ids=[g['game_id']for g in nearest]))
            rows.append(dict(game_id=target['game_id'],week=target['week'],side=si,position=pos,player_native_id=cp['id'],treatment='lagged_three',actual=actual,mean=cp[channel],p10=None,p90=None))
summaries={}
for pos in ['TE','WR','RB']:
    summaries[pos]={}
    for treatment in ['absolute_rank','relative_shock','lagged_three']:
        rs=[r for r in rows if r['position']==pos and r['treatment']==treatment]
        if treatment=='lagged_three':
            summaries[pos][treatment]=dict(rows=len(rs),games=len({r['game_id']for r in rs}),mae=statistics.mean(abs(r['mean']-r['actual'])for r in rs),bias=statistics.mean(r['mean']-r['actual']for r in rs))
        else:summaries[pos][treatment]=summary(rs)
out=dict(protocol_sha256=hashlib.sha256((P/'WORKLOAD_MATCHING_V2_PROTOCOL.md').read_bytes()).hexdigest(),retrospective=True,revised_historical_sources=True,full_fantasy_scoring=False,target_games=len(targets),skipped=skipped,summary=summaries,rows=rows,conservation=dict(checks=len(audit),max_error=max(a['conservation_error']for a in audit),mean_residual_share=statistics.mean(a['residual_share']for a in audit)),audit=audit)
with(P/'relative_transport_validation.json').open('x')as f:json.dump(out,f,indent=2)
print(json.dumps({k:v for k,v in out.items()if k in ['target_games','summary','skipped','conservation']},indent=2))
