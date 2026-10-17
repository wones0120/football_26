"""Fitted team outlooks and explicit conditional opportunity evidence.

Separate from player projection truth. Paired empirical game residuals estimate
probabilities, without promising forward calibration or fantasy lineup tails.
"""
from copy import deepcopy
import hashlib
import json
import math
import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from Database.dst import normalize_team

CONTRACT='team_game_outlook_v1'
TARGETS=['points','plays','drives','target_fraction','carry_fraction']
HISTORY=['points','points_against','plays','drives','epa','success','target_fraction','carry_fraction']
FEATURES=['home','rest_days','history_count','opponent_history_count']+[side+'_'+field+'_mean5' for side in ('own','opponent') for field in HISTORY]
SEED=261013


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def feasible(values):
    values=np.asarray(values,dtype=float).copy()
    if not np.isfinite(values).all(): raise ValueError('nonfinite team estimates')
    values[:,0]=np.maximum(0,values[:,0])
    values[:,1]=np.maximum(1,values[:,1])
    values[:,2]=np.clip(values[:,2],1,values[:,1])
    fractions=np.maximum(0,values[:,3:5]); scale=np.maximum(1,fractions.sum(axis=1))
    values[:,3:5]=fractions/scale[:,None]
    return values


def budgets(values):
    values=feasible(values)
    return np.column_stack([values[:,:3],values[:,1]*values[:,3],values[:,1]*values[:,4]])


class TeamGameModel:
    def __init__(self,alpha=100):
        self.alpha=alpha
        self.pipeline=make_pipeline(SimpleImputer(strategy='median',keep_empty_features=True),StandardScaler(),Ridge(alpha=alpha))

    def fit(self,frame):
        if frame[TARGETS].isna().any().any(): raise ValueError('missing target cannot become observed zero')
        if frame[['game_id','team']].duplicated().any(): raise ValueError('duplicate team/game identity')
        self.pipeline.fit(frame[FEATURES],frame[TARGETS]); return self

    def predict(self,frame): return feasible(self.pipeline.predict(frame[FEATURES]))

    def calibrate(self,frame):
        if frame[TARGETS].isna().any().any(): raise ValueError('calibration labels unavailable')
        residual=frame[TARGETS].to_numpy()-self.predict(frame)
        pairs=[]
        for _,indices in frame.reset_index(drop=True).groupby('game_id').groups.items():
            indices=list(indices)
            if len(indices)!=2 or set(frame.iloc[indices]['home'])!={0,1}: raise ValueError('incomplete paired calibration game')
            order=sorted(indices,key=lambda i:-frame.iloc[i]['home']);pairs.append(residual[order])
        self.residual_pairs=np.asarray(pairs)
        if len(pairs)<20: raise ValueError('at least20 calibration games required')
        return self

    def game(self,frame,*,draws=4096,seed=SEED):
        if len(frame)!=2 or frame.game_id.nunique()!=1 or set(frame.home)!={0,1}: raise ValueError('one complete home/away game required')
        frame=frame.sort_values('home',ascending=False);pred=self.predict(frame)
        sampled=self.residual_pairs[np.random.default_rng(seed).integers(len(self.residual_pairs),size=draws)]
        simulations=np.stack([budgets(pred[i]+sampled[:,i,:]) for i in range(2)],axis=1)
        simulations[:,:,0]=np.rint(simulations[:,:,0])
        score=simulations[:,:,0];margin=score[:,0]-score[:,1]
        central=budgets(pred)
        teams={}
        for side,row in enumerate(frame.to_dict('records')):
            own=simulations[:,side];other=simulations[:,1-side];diff=own[:,0]-other[:,0]
            competitive=(own[:,0]>=20)&(other[:,0]>=20)&(np.abs(diff)<=14)
            productive=(diff < -7)&(own[:,0]>=14)&(own[:,3]>=30)
            stall=(own[:,0]<14)&(own[:,0]/own[:,2]<1.4)
            masks={'competitive_scoring':competitive,'trailing_productive_passing':~competitive&productive,'drive_stall_runout':~competitive&~productive&stall,'other':~competitive&~productive&~stall}
            branches={key:dict(probability=float(mask.mean()),sample_count=int(mask.sum()),opponent_budget=dict(zip(['points','plays','drives','targets','carries'],map(float,other[mask].mean(axis=0)))) if mask.sum()>=30 else None,budget=dict(zip(['points','plays','drives','targets','carries'],map(float,own[mask].mean(axis=0)))) if mask.sum()>=30 else None) for key,mask in masks.items()}
            interval=np.quantile(own[:,0],[.1,.9])
            teams[row['team']]=dict(opponent=row['opponent'],home=bool(row['home']),central=dict(zip(['points','plays','drives','targets','carries'],map(float,central[side]))),
                win_probability=float((diff>0).mean()),tie_probability=float((diff==0).mean()),loss_probability=float((diff<0).mean()),win_half_tie_probability=float((diff>0).mean()+.5*(diff==0).mean()),
                score_interval_80=list(map(float,interval)),script_probabilities={'leading_by_more_than7':float((diff>7).mean()),'competitive_within7':float((np.abs(diff)<=7).mean()),'trailing_by_more_than7':float((diff < -7).mean())},
                capability_branches=branches,history_count=int(row['history_count']),last_history_completed_at=row.get('last_history_completed_at'))
        return dict(game_id=frame.game_id.iloc[0],season=int(frame.season.iloc[0]),week=int(frame.week.iloc[0]),kickoff_at=frame.kickoff_at.iloc[0],teams=teams,total_points=float(central[:,0].sum()),home_margin=float(central[0,0]-central[1,0]),seed=seed,draws=draws,
            probability_status='empirical_paired_residual_estimate; retrospective calibration measured, forward calibration unproven',tie_convention='ties separate; win_half_tie=win+0.5*tie',
            scenario_definition='mutually exclusive precedence: competitive_scoring, trailing_productive_passing, drive_stall_runout, other')


def validate_outlook(block,*,games,decision_at):
    from .analyst_packets import clock
    errors=[]
    if not isinstance(block,dict) or block.get('contract_id')!=CONTRACT:return ['unknown team outlook contract']
    if block.get('sha256')!=digest({k:v for k,v in block.items() if k!='sha256'}):errors.append('team outlook snapshot hash mismatch')
    try:
        decision=clock(decision_at)
        if clock(block['generated_at'])>decision or clock(block['source_available_at'])>decision:errors.append('future team outlook source')
    except (KeyError,TypeError,ValueError):return errors+['invalid team outlook clocks']
    if clock(block['source_available_at'])>clock(block['generated_at']):errors.append('source received after outlook generated')
    if not block.get('model_metadata') or not block.get('source_hashes'):errors.append('team outlook requires model/source lineage')
    for field in ['max_training_completed_at','max_calibration_completed_at']:
        try:
            if block['model_metadata'].get(field) and clock(block['model_metadata'][field])>=decision:errors.append('future model '+field)
        except (TypeError,ValueError):errors.append('invalid model fit clock')
    lookup={g['game_id']:g for g in games};seen=set()
    for g in block.get('games',[]):
        gid=g.get('game_id');scope=lookup.get(gid)
        if gid in seen or not scope:errors.append('duplicate/out-of-scope team outlook game');continue
        seen.add(gid)
        if set(g.get('teams',{}))!={normalize_team(t) for t in scope['teams']}:errors.append('team outlook canonical team mismatch')
        try:
            if clock(g['kickoff_at'])!=clock(scope['kickoff_at']) or clock(g['kickoff_at'])<=decision:errors.append('team outlook kickoff mismatch/not pregame')
        except (KeyError,TypeError,ValueError):errors.append('invalid team outlook kickoff')
        for team,t in g.get('teams',{}).items():
            try:
                if t.get('last_history_completed_at') and clock(t['last_history_completed_at'])>=decision:errors.append('future/same-game history')
            except (TypeError,ValueError):errors.append('invalid history clock')
            if t.get('opponent') not in g['teams'] or t.get('opponent')==team:errors.append('team outlook opponent mismatch')
            for budget in [t.get('central'),*[b.get(field) for b in t.get('capability_branches',{}).values() for field in ['budget','opponent_budget'] if b.get(field)]]:
                if not isinstance(budget,dict) or not all(type(budget.get(k)) in (float,int) and math.isfinite(budget[k]) and budget[k]>=0 for k in ['points','plays','drives','targets','carries']):errors.append('invalid team budget');continue
                if budget['targets']+budget['carries']>budget['plays']+1e-8 or budget['drives']>budget['plays']+1e-8:errors.append('impossible team budget')
            for names,values in [('win',[t.get(k) for k in ['win_probability','tie_probability','loss_probability']]),('script',list(t.get('script_probabilities',{}).values())),('capability',[b.get('probability') for b in t.get('capability_branches',{}).values()])]:
                if not values or not all(type(v) in (float,int) and math.isfinite(v) and 0<=v<=1 for v in values) or abs(sum(values)-1)>1e-6:errors.append('invalid '+names+' probabilities')
    return errors


def attach_context(packet,scenarios,*,decision_at,rows=None):
    """Attach saved shared game context without multiplying base player means."""
    block=packet.get('team_game_outlook')
    if block is None:return scenarios
    errors=validate_outlook(block,games=packet['games'],decision_at=decision_at)
    if errors:raise ValueError('; '.join(errors))
    lookup={g['game_id']:g for g in block['games']}
    for s in scenarios:
        gids={a['game_id'] for a in s['assumptions']}
        s['team_game_outlook']={'sha256':block['sha256'],'model_metadata':deepcopy(block['model_metadata']),'games':[deepcopy(lookup[g]) for g in sorted(gids) if g in lookup], 'baseline_mutation':False,'portfolio_weights':'existing uncalibrated design weights; game-event probabilities are not lineup probabilities'}
        if rows is not None:
            s['team_budget_allocation_audit']=[]
            for gid in sorted(gids):
                if gid not in lookup:continue
                for team,item in lookup[gid]['teams'].items():
                    branch=item['capability_branches'].get(s.get('team_game_branch'))
                    budget=(branch or {}).get('budget') or item['central']
                    audit=allocate_budget(packet,rows,gid,team,budget,decision_at=decision_at)
                    if branch and branch.get('budget'):audit['audit_basis']='conditional model team budget; separate from player fantasy elasticity'
                    s['team_budget_allocation_audit'].append(audit)
    return scenarios


def conditional_factors(packet,game_id,team,branch,*,conditioned_on_team=None):
    """Ratios to central budgets; no additive market or player projection changes."""
    block=packet.get('team_game_outlook')
    if not block:return None
    game=next((g for g in block['games'] if g['game_id']==game_id),None)
    if not game:return None
    item=game['teams'].get(normalize_team(team));condition=game['teams'].get(normalize_team(conditioned_on_team or team));conditional=condition['capability_branches'].get(branch) if condition else None
    if not conditional or not conditional.get('budget'):return None
    baseline=item['central'];budget=conditional['budget'] if not conditioned_on_team or normalize_team(conditioned_on_team)==normalize_team(team) else conditional.get('opponent_budget')
    if not budget:return None
    if baseline['targets']<=0 or baseline['carries']<=0:return None
    factors=(budget['targets']/baseline['targets'],budget['carries']/baseline['carries'])
    # Current Analyst contract bounds factors; don't clip and pretend exact budget.
    if not all(.5<=v<=1.5 for v in factors):return None
    return factors


def bind_outlook(block,games):
    """Bind native schedule IDs to packet IDs using period+canonical teams+kickoff."""
    from .analyst_packets import clock
    bound=deepcopy(block);bound.pop('sha256',None);bound['source_snapshot_sha256']=block['sha256'];bound['games']=[]
    for scope in games:
        matches=[g for g in block['games'] if g['season']==scope.get('season') and g['week']==scope.get('week') and set(g['teams'])=={normalize_team(t) for t in scope['teams']} and clock(g['kickoff_at'])==clock(scope['kickoff_at'])]
        if len(matches)!=1:raise ValueError('ambiguous/unavailable canonical team game binding')
        game=deepcopy(matches[0]);game['source_native_game_id']=game['game_id'];game['game_id']=scope['game_id'];bound['games'].append(game)
    bound['sha256']=digest(bound);return bound


def allocate_budget(packet,rows,game_id,team,budget,*,decision_at):
    """Conserve full-team opportunities; absent/missing roles stay unallocated.

    Canonical packet skill participants are the universe. If any channel's
    measurement is unavailable, do not fabricate share estimates. This audit
    does not change fantasy means or infer routes/availability.
    """
    from .analyst_scenarios import _measurement
    from .analyst_packets import clock
    team=normalize_team(team);pool={str(r.get('player_id',r.get('player_master_id'))) for r in rows}
    members=[p for p in packet['players'] if p['game_id']==game_id and normalize_team(p['team'])==team and p['position'] in {'QB','RB','WR','TE'}]
    channels={}
    for channel in ['targets','carries']:
        observed={p['player_master_id']:_measurement(p,channel,clock(decision_at))[0] for p in members if channel!='targets' or p['position']!='QB'}
        if not observed or any(v is None for v in observed.values()) or sum(observed.values())<=0:
            channels[channel]={'status':'unavailable_complete_role_shares','allocated':{},'unallocated':float(budget[channel]),'budget':float(budget[channel]),'missing_player_master_ids':[p for p,v in observed.items() if v is None]};continue
        total=sum(observed.values());allocated={pid:float(budget[channel])*value/total for pid,value in observed.items() if pid in pool}
        channels[channel]={'status':'normalized_historical_role_shares_conditional_assumption','allocated':allocated,'unallocated':max(0,float(budget[channel])-sum(allocated.values())),'budget':float(budget[channel]),'observed_zero_player_master_ids':[pid for pid,value in observed.items() if value==0]}
    return {'game_id':game_id,'team':team,'audit_basis':'central model team budget; separate from declared player fantasy elasticity','plays':budget['plays'],'channels':channels,'unassigned_play_budget':float(budget['plays']-budget['targets']-budget['carries']),'baseline_mutation':False,'limitation':'Conditional allocation audit, not injury redistribution or projected route measurement'}
