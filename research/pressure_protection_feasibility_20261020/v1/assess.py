"""Coverage diagnostic only: no catalog feature or aggregate-protection proxy."""
from collections import defaultdict
from itertools import product
from backend.app.product_services.opponent_strength_workload import _quantile
BINS=('low','middle','high');PERSONNEL=('unchanged_five','changed_native_CGT_members')


def _pool(rows):
    if not rows or any(r is None or not r['full_observed_cohort_proven']for r in rows):return None
    den=sum(r['known_dropbacks']for r in rows)
    return sum(r['known_source_pressure_sum']for r in rows)/den if den else None


def _bin(value,cutpoints,ready):
    lo,hi=cutpoints
    if not ready or value is None or lo is None or hi is None or lo>=hi:return None
    return 'low'if value<=lo else'high'if value>=hi else'middle'


def _compatible(condition,cell):return all(v is None or v==c for v,c in zip(condition,cell))


def _contrast_count(rows):
    cells={c:dict(num=0,den=0,unknown=0)for c in product(PERSONNEL,BINS,BINS)}
    for r in rows:
        for cell,c in cells.items():
            if not _compatible(r['condition'],cell):continue
            if None in r['condition']or not r['response_known']:c['unknown']+=1
            else:c['num']+=r['pressure_sum'];c['den']+=r['dropbacks']
    count=0
    for personnel,own in product(PERSONNEL,BINS):
        low,high=cells[(personnel,own,'low')],cells[(personnel,own,'high')]
        count+=int(all(c['den']>0 and c['unknown']==0 for c in(low,high)))
    return count


def assess(pressure,lines,schedule):
    index={(g['game_id'],g['offense']):g for g in pressure['game_rows']};ol={(g['game_id'],g['team']):g for line in lines for g in line['continuity_rows']}
    if len(index)!=len(pressure['game_rows'])or len(ol)!=sum(len(l['continuity_rows'])for l in lines):raise ValueError('Unique source game/team rows required')
    groups=defaultdict(list)
    for g in schedule:
        if g['season']not in {2023,2024,2025}or g['game_type']!='REG':continue
        for team in(g['home_team'],g['away_team']):groups[(g['season'],team)].append(g)
    for key,gs in groups.items():
        if any(not g.get('game_date')for g in gs)or len({g['game_date']for g in gs})!=len(gs):raise ValueError('Exact unique native scheduled dates required')
        gs.sort(key=lambda g:g['game_date'])
        for g in gs:
            row=index.get((g['game_id'],key[1]));other=g['away_team']if key[1]==g['home_team']else g['home_team']
            if row and(row['season'],row['week'],row['defense'])!=(g['season'],g['week'],other):raise ValueError('Pressure/schedule native side or period conflict')
    refs={};contexts={}
    reference_dates={s:max((g['game_date']for (year,team),gs in groups.items()if year==s for g in gs if g['week']<4),default=None)for s in (2023,2024,2025)}
    for season in (2023,2024,2025):
        for role in('own_allowed','opponent_generated'):
            values=[]
            for(s,team),gs in groups.items():
                if s!=season:continue
                rs=[index.get((g['game_id'],team if role=='own_allowed'else(g['away_team']if team==g['home_team']else g['home_team'])))for g in gs if g['week']<4]
                v=_pool(rs)
                if v is not None:values.append(v)
            refs[(season,role)]=(_quantile(values,1/3),_quantile(values,2/3))if len(values)>=2 else(None,None)
    for(s,team),gs in groups.items():
        for i,g in enumerate(gs):
            prior=gs[max(0,i-8):i]
            if any(old['season']*100+old['week']>=s*100+g['week']for old in prior):raise ValueError('Prior scheduled games must precede target period')
            for role in('own_allowed','opponent_generated'):
                rows=[index.get((old['game_id'],team if role=='own_allowed'else(old['away_team']if team==old['home_team']else old['home_team'])))for old in prior]
                value=_pool(rows);contexts[(g['game_id'],team,role)]=dict(value=value,group=_bin(value,refs[(s,role)],g['week']>=4 and reference_dates[s]is not None and reference_dates[s]<g['game_date']),contributing_game_ids=[old['game_id']for old in prior])
    output=[];rows=[]
    for(s,team),gs in sorted(groups.items()):
        evaluations=[];prior_counts=[]
        for g in gs:
            opp=g['away_team']if team==g['home_team']else g['home_team'];own=contexts[(g['game_id'],team,'own_allowed')];opposing=contexts[(g['game_id'],opp,'opponent_generated')]
            l=ol.get((g['game_id'],team));value=l.get('canonical_qualified_value')if l else None
            if value is not None and (type(value)not in(int,float)or not 0<=value<=1 or abs(value*5-round(value*5))>1e-8):raise ValueError('Five-source-member continuity fraction required')
            previous=gs[gs.index(g)-1]['game_id']if gs.index(g)>0 else None
            if l and l['previous_same_season_game_id']!=previous:raise ValueError('No skip to another known OL unit')
            personnel=None if value is None else'unchanged_five'if value==1 else'changed_native_CGT_members'
            p=index.get((g['game_id'],team));r=dict(game_id=g['game_id'],season=s,team=team,week=g['week'],condition=(personnel,own['group'],opposing['group']),response_known=bool(p and p['full_observed_cohort_proven']),pressure_sum=p['known_source_pressure_sum']if p else None,dropbacks=p['known_dropbacks']if p else None)
            rows.append(r)
            if g['week']<4:continue
            prior_counts.append(_contrast_count(evaluations[-8:]));evaluations.append(r)
        output.append(dict(season=s,team=team,evaluation_games=len(evaluations),known_three_axis_response_games=sum(None not in r['condition']and r['response_known']for r in evaluations),whole_profile_exact_contrasts=_contrast_count(evaluations),strict_prior_window_exact_contrasts=sum(prior_counts)))
    return dict(diagnostic_only=True,catalog_ids_completed=[],reference_cutpoints={f'{k[0]}:{k[1]}':v for k,v in refs.items()},profiles=output,game_contexts=rows)
