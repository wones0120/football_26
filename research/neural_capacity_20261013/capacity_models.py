"""Focused neural training; all preprocessing and priors fit on gradient rows only."""
from __future__ import annotations
from copy import deepcopy
import time,warnings
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.neural_network import MLPClassifier,MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder,StandardScaler

SEED=261013
SETTINGS=[dict(hidden_layer_sizes=(16,8),alpha=.05,batch_size=128),dict(hidden_layer_sizes=(32,16),alpha=.2,batch_size=256)]


def preprocess(columns):
 return ColumnTransformer([('numeric',make_pipeline(SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True),StandardScaler()),columns),('position',OneHotEncoder(handle_unknown='ignore',sparse_output=False),['position'])])
def mae(y,p):return float(np.mean(np.abs(p-y)))
def brier(y,p):return float(np.mean((p-y)**2))
def baseline(f,target,priors):
 return f[target+'_mean3'].fillna(f.position.map(priors)).fillna(float(np.mean(list(priors.values())))).to_numpy()
def floor(p,target):return np.maximum(0,p) if target!='fantasy_points_ppr' else p

def observed_labels(frame,target):
 if frame[target].isna().any():raise ValueError('Absent labels must be excluded explicitly, never converted to zero')
 if target!='fantasy_points_ppr' and (frame[target]<0).any():raise ValueError('Observed workloads must be nonnegative')

def epoch_fit(X,y,Z,z,settings,*,classifier=False,stop_metric=None,fixed_epochs=None):
 """partial_fit retains Adam state; no random internal validation split."""
 params={k:v for k,v in settings.items() if k not in ['name','epoch_cap']}|dict(batch_size=min(settings['batch_size'],len(y)),random_state=SEED,shuffle=True,early_stopping=False,max_iter=1)
 params.setdefault('learning_rate_init',.001)
 estimator=MLPClassifier(**params) if classifier else MLPRegressor(**params)
 curves=[];best=None;best_metric=float('inf');stale=0;best_epoch=0;start=time.perf_counter();cap=int(fixed_epochs) if fixed_epochs is not None else settings.get('epoch_cap',300)
 with warnings.catch_warnings(record=True) as caught:
  warnings.simplefilter('always')
  for epoch in range(1,max(1,cap)+1):
   if time.perf_counter()-start>120:raise TimeoutError('120-second network head limit')
   if classifier:estimator.partial_fit(X,y,classes=np.array([0,1]))
   else:estimator.partial_fit(X,y)
   pred=estimator.predict_proba(Z)[:,1] if classifier else estimator.predict(Z)
   trainp=estimator.predict_proba(X)[:,1] if classifier else estimator.predict(X)
   score=stop_metric(z,pred) if stop_metric is not None else brier(z,pred) if classifier else float(np.sqrt(np.mean((z-pred)**2)))
   train_score=brier(y,trainp) if classifier else float(np.sqrt(np.mean((y-trainp)**2)))
   curves.append({'epoch':epoch,'training_loss':float(estimator.loss_),'training_metric':train_score,'stopping_metric':score})
   tolerance=.0001 if classifier else .0002 if stop_metric is None else .002
   if score<best_metric-tolerance:
    best_metric=score;best=deepcopy(estimator);best_epoch=epoch;stale=0
   else:stale+=1
   if fixed_epochs is None and epoch>=10 and stale>=25:break
 if fixed_epochs is not None:best=estimator;best_epoch=cap
 return best,{'best_epoch':int(best_epoch),'epochs_run':len(curves),'stopping_best':float(best_metric),'last_stopping_metric':float(curves[-1]['stopping_metric']),'training_metric_at_best':float(curves[best_epoch-1]['training_metric']),'seconds':time.perf_counter()-start,'warnings':[str(w.message) for w in caught],'curve':curves,'parameter_count':int(sum(a.size for a in best.coefs_)+sum(a.size for a in best.intercepts_)),'epoch_cap':cap,'cap_reached':len(curves)==cap,'early_stopped':fixed_epochs is None and len(curves)<cap}


class ResidualNetwork:
 def __init__(self,columns,settings):self.columns=columns;self.settings=settings
 def fit(self,f,target,stop,*,fixed_epochs=None):
  observed_labels(f,target);observed_labels(stop,target)
  self.target=target;self.priors=f.groupby('position')[target].mean().to_dict();self.pre=preprocess(self.columns)
  X=self.pre.fit_transform(f[self.columns+['position']]);Z=self.pre.transform(stop[self.columns+['position']]);history=baseline(f,target,self.priors);sh=baseline(stop,target,self.priors)
  self.scale=StandardScaler();y=self.scale.fit_transform((f[target].to_numpy()-history).reshape(-1,1)).ravel();z=self.scale.transform((stop[target].to_numpy()-sh).reshape(-1,1)).ravel()
  def stop_score(_,p):return mae(stop[target].to_numpy(),floor(sh+self.scale.inverse_transform(p.reshape(-1,1)).ravel(),target))
  self.model,self.metadata=epoch_fit(X,y,Z,z,self.settings,stop_metric=stop_score,fixed_epochs=fixed_epochs)
  self.metadata['training_actual_mae']=mae(f[target].to_numpy(),self.predict(f));self.metadata['stopping_actual_mae']=mae(stop[target].to_numpy(),self.predict(stop));self.metadata['head']='residual';return self
 def predict(self,f):
  p=self.model.predict(self.pre.transform(f[self.columns+['position']]));return floor(baseline(f,self.target,self.priors)+self.scale.inverse_transform(p.reshape(-1,1)).ravel(),self.target)


class PositionNetwork:
 def __init__(self,columns,settings):self.columns=columns;self.settings=settings
 def fit(self,f,target,stop,*,epoch_template=None):
  observed_labels(f,target);observed_labels(stop,target)
  self.target=target;self.heads={};self.metadata={};self.priors=f.groupby('position')[target].mean().to_dict()
  self.fallback=ResidualNetwork(self.columns,self.settings).fit(f,target,stop,fixed_epochs=(epoch_template or {}).get('shared/residual'))
  self.metadata['shared/residual']=self.fallback.metadata
  for pos in ['QB','RB','WR','TE']:
   train=f[f.position==pos];validation=stop[stop.position==pos];template=epoch_template or {}
   if len(train)<100 or len(validation)<20:
    self.heads[pos]={'kind':'shared_fallback'};self.metadata[pos+'/fallback']={'reason':'<100fit or <20stopping labels','fit_rows':len(train),'stop_rows':len(validation)};continue
   if target=='fantasy_points_ppr':
    head=ResidualNetwork(self.columns,self.settings).fit(train,target,validation,fixed_epochs=template.get(pos+'/residual'));self.heads[pos]={'kind':'residual','model':head};self.metadata[pos+'/residual']=head.metadata;continue
   pre=preprocess(self.columns);X=pre.fit_transform(train[self.columns+['position']]);Z=pre.transform(validation[self.columns+['position']]);y=(train[target].to_numpy()>0).astype(int);z=(validation[target].to_numpy()>0).astype(int)
   head={'kind':'hurdle','pre':pre,'positive_fraction':float(y.mean())}
   if len(np.unique(y))<2:
    head['classifier']=None;self.metadata[pos+'/classifier']={'constant_probability':float(y.mean()),'reason':'single train class'}
   else:
    classifier,metadata=epoch_fit(X,y,Z,z,self.settings,classifier=True,fixed_epochs=template.get(pos+'/classifier'));head['classifier']=classifier;self.metadata[pos+'/classifier']=metadata
   positive=y>0;stoppositive=z>0
   if positive.sum()<60 or stoppositive.sum()<10:
    head['amount']=None;head['constant_amount']=float(train.loc[positive,target].mean()) if positive.any() else 0.;self.metadata[pos+'/amount']={'constant_positive_mean':head['constant_amount'],'fit_positives':int(positive.sum()),'stop_positives':int(stoppositive.sum()),'reason':'<60fit or <10stop positives'}
   else:
    scale=StandardScaler();logs=np.log1p(train.loc[positive,target].to_numpy());logs_stop=np.log1p(validation.loc[stoppositive,target].to_numpy());scaled=scale.fit_transform(logs.reshape(-1,1)).ravel();stopscaled=scale.transform(logs_stop.reshape(-1,1)).ravel()
    amount,metadata=epoch_fit(X[positive],scaled,Z[stoppositive],stopscaled,self.settings,fixed_epochs=template.get(pos+'/amount'))
    # Training-only smearing; approximate mean correction, not distribution calibration.
    trainlog=scale.inverse_transform(amount.predict(X[positive]).reshape(-1,1)).ravel();smear=float(np.mean(np.exp(np.clip(logs-trainlog,-10,10))))
    head.update(amount=amount,scale=scale,smear=smear);self.metadata[pos+'/amount']=metadata|{'training_smearing_factor':smear,'fit_positives':int(positive.sum()),'stop_positives':int(stoppositive.sum())}
   self.heads[pos]=head
  return self
 def predict_with_probability(self,f):
  p=self.fallback.predict(f);probability=np.full(len(f),np.nan)
  for pos,head in self.heads.items():
   mask=(f.position==pos).to_numpy();part=f.loc[mask]
   if not mask.any() or head['kind']=='shared_fallback':continue
   if head['kind']=='residual':p[mask]=head['model'].predict(part);continue
   X=head['pre'].transform(part[self.columns+['position']]);q=head['classifier'].predict_proba(X)[:,1] if head['classifier'] is not None else np.full(len(part),head['positive_fraction']);probability[mask]=q
   if head['amount'] is None:amount=np.full(len(part),head['constant_amount'])
   else:
    logs=head['scale'].inverse_transform(head['amount'].predict(X).reshape(-1,1)).ravel();amount=np.maximum(0,np.exp(np.clip(logs,-10,10))*head['smear']-1)
   p[mask]=q*amount
  return floor(p,self.target),probability
 def predict(self,f):return self.predict_with_probability(f)[0]
