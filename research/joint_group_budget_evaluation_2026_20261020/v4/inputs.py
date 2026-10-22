"""Reconstructed 2026 evaluation inputs only; no fit or inference API."""
import numpy as np
from backend.app.product_services.scheduled_workload_efficiency_model_inputs import _pool,TEAM_ADDED,PLAYER_ADDED
from backend.app.product_services.model_weekly_workload_components import CHANNEL_FIELDS
from backend.app.product_services.joint_group_budget_allocation import transform_group_inputs


def prior_features(proof, native, context, actors, teams, *, channel):
    ids=proof['prior_games'];team=proof['team'];period=202600+proof['week']
    if len(ids)!=3 or ids!=context['windows']['own']['game_ids'] or any(int(g[:4])!=2026 or int(g.split('_')[1])>=proof['week'] for g in ids):
        raise ValueError('Exact immediate scheduled same-season prior3 required')
    if context['period']!=period or set(context['features'])!=set(TEAM_ADDED):raise ValueError('Same native context required')
    for window in context['windows'].values():
        if len(window['game_ids'])!=3 or any(p//100!=2026 or p>=period for p in window['periods']):raise ValueError('Both context axes must be strictly prior3')
    rows=[actors.get((g,team,native))for g in ids];pooled=_pool(rows,actor=True)
    fields={'scheduled3_'+k:v for k,v in pooled.items()if k not in('known_source_games','unknown_source_games')}
    fields.update(scheduled3_known_actor_rows=sum(r is not None for r in rows),scheduled3_unknown_actor_rows=sum(r is None for r in rows))
    for ch,field in CHANNEL_FIELDS.items():
        nums=[r['counts'][ch]if r else None for r in rows];dens=[teams[(g,team)]['values'][field]for g in ids]
        valid=all(v is not None for v in nums+dens);n,d=(sum(nums),sum(dens))if valid else(None,None)
        if valid and n>d:raise ValueError('Prior actor count exceeds source budget')
        fields[f'scheduled3_{ch}_pooled_share']=n/d if valid and d>0 else None
    latest=rows[-1]['source_position']if rows[-1]else None
    fields.update({'latest_prior_role_'+r:None if latest is None else int(latest==r if r!='other'else latest not in{'QB','RB','WR','TE','FB'})for r in('QB','RB','WR','TE','FB','other')})
    roles=[r['source_position']if r else None for r in rows]
    fields['scheduled3_role_consistent']=int(len(set(roles))==1)if all(r is not None for r in roles)else None
    if set(fields)!=set(PLAYER_ADDED):raise ValueError('Exact historical actor fields required')
    out={**context['features'],**fields,'is_known_outside_rest':0,'prior_candidate_count':proof['channels']['rush_attempts']['candidate_count']}
    if channel=='target':out['is_source_pass_minus_target_remainder']=0
    return out


def construct_group(proof, context, actors, teams, columns, *, channel):
    if not proof['completed_status_verified']or not proof['prior3_achieved']or proof['week']not in(4,5):raise ValueError('Approved completed evaluation weeks only')
    ch=proof['channels']['rush_attempts'if channel=='rush'else'targets']
    if not ch['canonical_group_complete']or channel=='target'and not proof['target_joint_canonical_group']:raise ValueError('Canonical complete source group required')
    candidates=ch['candidate_labels'];natives=[c['native']for c in candidates];pids=[c['player_master_id']for c in candidates]
    prior={n for g in proof['prior_games']for gg,t,n in actors if gg==g and t==proof['team']}
    if set(natives)!=prior or len(natives)!=len(set(natives))or None in pids or len(pids)!=len(set(pids)):raise ValueError('Unchanged all-role native/canonical candidate universe required')
    cells=[]
    for c in candidates:
        f=prior_features(proof,c['native'],context,actors,teams,channel=channel)
        cells.append(dict(kind='candidate',source_player_id=c['native'],player_master_id=c['player_master_id'],label=c['count'],label_basis=c['basis'],features={k:f[k]for k in columns}))
    f={**context['features'],**dict.fromkeys(PLAYER_ADDED),'is_known_outside_rest':1,'prior_candidate_count':len(candidates)}
    if channel=='target':f['is_source_pass_minus_target_remainder']=0
    cells.append(dict(kind='outside_rest'if channel=='rush'else'outside_target_rest',source_player_id=None,player_master_id=None,label=ch['outside_rest'],features={k:f[k]for k in columns}))
    g=dict(game_id=proof['game_id'],team=proof['team'],period=202600+proof['week'],prior_games=proof['prior_games'],cells=cells,independent_NFL_census='UNKNOWN',input_vintage='LATEST_RECONSTRUCTED_NOT_ORIGINAL_PREGAME')
    if channel=='rush':g['budget_label']=ch['source_budget']
    else:
        P=proof['channels']['pass_attempts']['source_budget'];T=ch['source_budget']
        if P is None or T is None or P<T:raise ValueError('Known same-source P>=T required')
        f=dict(f,is_known_outside_rest=0,is_source_pass_minus_target_remainder=1)
        cells.append(dict(kind='source_pass_minus_target_remainder',source_player_id=None,player_master_id=None,label=P-T,features={k:f[k]for k in columns}))
        g.update(target_budget_label=T,pass_budget_label=P)
    return g


def transform_evaluation(groups, cell_prep, group_prep, *, channel):
    """Same numerical transform as frozen training; explicit 2026-only label gate."""
    if not groups or len({(g['game_id'],g['team'])for g in groups})!=len(groups):raise ValueError('Nonempty unique groups required')
    columns=cell_prep['columns']
    for g in groups:
        if g['period']//100!=2026 or g['period']%100 not in(4,5):raise ValueError('No historical-period relabeling or unsupported week')
        cells=g['cells'];kinds=[c['kind']for c in cells]
        tail=['outside_rest']if channel=='rush'else['outside_target_rest','source_pass_minus_target_remainder']
        if kinds[-len(tail):]!=tail or any(k!='candidate'for k in kinds[:-len(tail)]):raise ValueError('Disjoint cells required')
        cs=cells[:-len(tail)]
        for key in('source_player_id','player_master_id'):
            ids=[c[key]for c in cs]
            if not ids or None in ids or len(set(ids))!=len(ids):raise ValueError('Unique canonical/native candidates required')
        labels=np.asarray([c['label']for c in cells],float)
        if not np.isfinite(labels).all()or(labels<0).any()or not np.equal(labels,np.floor(labels)).all():raise ValueError('Known observed labels required')
        if channel=='rush':valid=labels.sum()==g['budget_label']
        else:valid=labels[:-1].sum()==g['target_budget_label']and labels.sum()==g['pass_budget_label']
        if not valid:raise ValueError('Exact source-observed budgets required')
        for c in cells:
            if list(c['features'])!=columns or any(v is not None and(type(v)not in(int,float)or not np.isfinite(v))for v in c['features'].values()):raise ValueError('Exact finite/unknown predictor order required')
    raw=np.asarray([[np.nan if c['features'][k]is None else c['features'][k]for k in columns]for g in groups for c in g['cells']],float)
    frozen=raw.copy()
    for k in cell_prep['entirely_missing_train_columns']:frozen[:,columns.index(k)]=np.nan
    missing=np.isnan(frozen);filled=np.where(missing,cell_prep['medians'],frozen)
    X=np.concatenate(((filled-cell_prep['centers'])/cell_prep['scales'],missing.astype(float)),axis=1)
    if not np.isfinite(X).all():raise ValueError('Nonfinite prepared input')
    out=dict(raw_inputs=raw,X=X,G=transform_group_inputs(groups,group_prep),labels=np.asarray([c['label']for g in groups for c in g['cells']],float),offsets=np.cumsum([0]+[len(g['cells'])for g in groups]),budgets=np.asarray([g['budget_label'if channel=='rush'else'pass_budget_label']for g in groups],float))
    if channel=='target':out['target_budgets']=np.asarray([g['target_budget_label']for g in groups],float)
    return out
