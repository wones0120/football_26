"""One bounded TRAIN-only conditioning pass. No optimizers or holdout metrics."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
from pathlib import Path
from datetime import datetime,UTC
from io import BytesIO
import json,hashlib,time
import numpy as np
from backend.app.product_services import joint_rush_conditional_means as rush,joint_target_pass_conditional_means as target
R=Path(__file__).resolve().parent
start=datetime.now(UTC);wall=time.perf_counter();refs={}
def read(name,ref):
 b=Path(ref['path']).read_bytes();assert len(b)==ref['bytes']and hashlib.sha256(b).hexdigest()==ref['sha256'];refs[name]=ref;return b
def ref(path):
 path=Path(path);b=path.read_bytes();return dict(path=str(path.resolve()),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def full_gn_diagonal(theta,data,prep,channel):
 """Diagonal J'WJ for ALL declared squared losses plus original weight L2."""
 X=data['X'];mu,H,z=rush.forward(theta,X);W,b,v,a=rush._unpack(theta,X.shape[1],8)
 s=np.exp(-np.logaddexp(0.,-z));dh=s[:,None]*v*(1-H**2);dv=s[:,None]*H
 offsets=data['offsets'];ng=len(offsets)-1;cellweight=np.empty(len(X))
 for lo,hi in zip(offsets[:-1],offsets[1:]):cellweight[lo:hi]=2/(ng*(hi-lo)*prep['cell_label_scale']**2)
 dW=(X**2).T@(dh**2*cellweight[:,None]);db=np.sum(dh**2*cellweight[:,None],axis=0);dV=np.sum(dv**2*cellweight[:,None],axis=0);da=float(np.sum(s**2*cellweight))
 for lo,hi in zip(offsets[:-1],offsets[1:]):
  terms=[(hi,prep['budget_label_scale'])]
  if channel=='target':terms.append((hi-1,prep['target_budget_label_scale']))
  for end,scale in terms:
   factor=2/(ng*scale**2);dW+=factor*(X[lo:end].T@dh[lo:end])**2;db+=factor*dh[lo:end].sum(axis=0)**2;dV+=factor*dv[lo:end].sum(axis=0)**2;da+=factor*float(s[lo:end].sum())**2
 return np.r_[dW.ravel()+.001,db,dV+.001,da]
def hvp_rayleigh(theta,directions,module,data,prep):
 output=[]
 for name,direction in directions:
  # The perturbation has fixed Euclidean theta norm1e-4; the returned curvature
  # is with respect to the provided coordinate direction, which may be D*v.
  norm=float(np.linalg.norm(direction));step=1e-4/max(1.,norm)
  gp=module.objective(theta+step*direction,data,prep)[1];gm=module.objective(theta-step*direction,data,prep)[1]
  hv=(gp-gm)/(2*step);output.append(dict(direction=name,theta_direction_norm=norm,coordinate_rayleigh=float(direction@hv)))
 return output
out={}
for channel,module,folder in [('rush',rush,'joint_rush_conditional_means_20261020'),('target',target,'joint_target_pass_conditional_means_20261020')]:
 receipt_path=Path('research/joint_conditional_mean_fits_20261020/v2')/(channel+'.json');receipt=json.loads(receipt_path.read_text());refs[channel+'_receipt']=ref(receipt_path)
 manifest_path=Path('research',folder,'v1/MANIFEST.json');manifest=json.loads(manifest_path.read_text());refs[channel+'_manifest']=ref(manifest_path)
 model=json.loads(read(channel+'_failedmodel',receipt['model_ref']));z=np.load(BytesIO(read(channel+'_tensors',manifest['tensor_ref'])),allow_pickle=False)
 n=int(np.sum(z['group_years']==2023));off=z['offsets'][:n+1];assert np.array_equal(np.flatnonzero(z['group_years']==2023),np.arange(n));last=int(off[-1]);X=z['X'][:last]
 data=dict(X=X,labels=z['labels'][:last],budgets=z['budgets'][:n],offsets=off.tolist())
 if channel=='target':data['target_budgets']=z['target_budgets'][:n]
 theta=np.asarray(model['parameters']);prep=model['preprocessing'];f,g=module.objective(theta,data,prep);assert f==model['objective']
 sv=np.linalg.svd(X,compute_uv=False);threshold=np.finfo(float).eps*max(X.shape)*sv[0];rank=int(np.sum(sv>threshold));zero=np.flatnonzero(np.max(abs(X),axis=0)==0).tolist()
 # Exact affine relations can differ by ordinary standardization roundoff.
 duplicates=[]
 for i in range(X.shape[1]):
  if i in zero:continue
  for j in range(i):
   if j in zero:continue
   error=float(np.max(abs(X[:,i]-X[:,j])))
   if error<=1e-12:duplicates.append(dict(left=manifest['transformed_columns'][j],right=manifest['transformed_columns'][i],max_absolute_difference=error));break
 initial=rush.initial_parameters(X.shape[1]);initial_diag=full_gn_diagonal(initial,data,prep,channel);final_diag=full_gn_diagonal(theta,data,prep,channel)
 assert np.isfinite(initial_diag).all()and(initial_diag>0).all();D=1/np.sqrt(initial_diag)
 Wsize=X.shape[1]*8;blocks={'W':(0,Wsize),'hidden_bias':(Wsize,Wsize+8),'output_weights':(Wsize+8,Wsize+16),'output_bias':(len(theta)-1,len(theta))}
 derivatives=[];directions=[]
 for name,(lo,hi)in blocks.items():
  index=lo+int(np.argmax(abs(g[lo:hi])));eps=1e-5;unit=np.zeros_like(theta);unit[index]=1
  plus=module.objective(theta+eps*unit,data,prep)[0];minus=module.objective(theta-eps*unit,data,prep)[0];numeric=(plus-minus)/(2*eps)
  derivatives.append(dict(block=name,index=index,analytic=float(g[index]),numeric=float(numeric),absolute_error=float(abs(numeric-g[index]))));directions.append((name+'_coordinate',unit))
 rng=np.random.default_rng(17)
 for i in range(4):
  direction=rng.normal(size=len(theta));direction/=np.linalg.norm(direction);directions.append((f'fixed_random_{i}',direction))
 raw_hvp=hvp_rayleigh(theta,directions,module,data,prep);scaled_hvp=hvp_rayleigh(theta,[(name,D*v)for name,v in directions],module,data,prep)
 # Exact, reversible coordinate transform; F(theta0+D*phi) keeps original L2 on
 # theta, not phi. No parameter update or optimizer is performed here.
 phi=(theta-initial)/D;roundtrip=initial+D*phi;round_loss,round_grad=module.objective(roundtrip,data,prep)
 test=rng.normal(size=len(theta));test/=np.linalg.norm(test);eps=1e-5
 fp=module.objective(initial+D*(phi+eps*test),data,prep)[0];fm=module.objective(initial+D*(phi-eps*test),data,prep)[0]
 transformed_analytic=float((D*round_grad)@test);transformed_numeric=float((fp-fm)/(2*eps))
 assert np.max(abs(roundtrip-theta))<2e-15 and abs(round_loss-f)<1e-13
 def spread(values):
  positive=[v['coordinate_rayleigh']for v in values if v['coordinate_rayleigh']>0];return dict(min_positive=min(positive),max_positive=max(positive),positive_ratio=max(positive)/min(positive),negative=sum(v['coordinate_rayleigh']<0 for v in values),scope='Fixed8directionRayleighprobe,NOTeigenconditionnumber')
 out[channel]=dict(train_groups=n,train_cells=last,features=X.shape[1],parameters=len(theta),design_rank=rank,rank_threshold=float(threshold),zero_columns=len(zero),affine_duplicate_columns=duplicates,nonzero_design_singular_ratio=float(sv[0]/sv[rank-1]),design_min_retained_singular=float(sv[rank-1]),input_abs_max=float(abs(X).max()),final_objective=f,gradient_inf=float(abs(g).max()),block_derivatives=derivatives,original_coordinate_rayleigh=raw_hvp,scaled_coordinate_rayleigh=scaled_hvp,raw_fixed_direction_spread=spread(raw_hvp),scaled_fixed_direction_spread=spread(scaled_hvp),initial_full_objective_GN_diagonal=dict(min=float(initial_diag.min()),max=float(initial_diag.max()),ratio=float(initial_diag.max()/initial_diag.min())),final_full_objective_GN_diagonal=dict(min=float(final_diag.min()),max=float(final_diag.max()),ratio=float(final_diag.max()/final_diag.min())),fixed_initial_TRAIN_coordinate_scale=dict(min=float(D.min()),max=float(D.max()),sha256=hashlib.sha256(D.astype('<f8').tobytes()).hexdigest(),construction='1/sqrt(fullinitialTRAINcell+budgetGaussNewtondiagonal+originalweightL2);noreselectedfloor/clipping'),coordinate_equivalence=dict(theta_roundtrip_max_error=float(abs(roundtrip-theta).max()),objective_error=float(abs(round_loss-f)),transformed_direction_analytic=transformed_analytic,transformed_direction_numeric=float(transformed_numeric),transformed_direction_error=float(abs(transformed_analytic-transformed_numeric))),optimizer_calls=0,holdout_evaluations=0)
result=dict(version='joint_mean_train_conditioning_diagnosis_v1',started_at=start.isoformat(),completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.perf_counter()-wall,source_refs=refs,producer_ref=ref(__file__),channels=out,optimizer_calls=0,parameter_updates=0,model_prediction_api_calls=0,holdout_evaluations=0,activation=False)
(R/'DIAGNOSIS.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
print(json.dumps(dict(elapsed_seconds=result['elapsed_seconds'],channels={c:{k:r[k]for k in('design_rank','features','zero_columns','raw_fixed_direction_spread','scaled_fixed_direction_spread','initial_full_objective_GN_diagonal','final_full_objective_GN_diagonal','coordinate_equivalence')}for c,r in out.items()}),indent=2))
