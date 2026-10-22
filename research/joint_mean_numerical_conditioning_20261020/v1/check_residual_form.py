"""Verify exact least-squares residual/JVP/adjoint identity on TRAIN only."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
from pathlib import Path
from io import BytesIO
import json,time
import numpy as np
from backend.app.product_services import joint_rush_conditional_means as rush,joint_target_pass_conditional_means as target
R=Path(__file__).resolve().parent;timer=time.perf_counter();d=json.loads((R/'DIAGNOSIS.json').read_text());out={}
for channel,module in [('rush',rush),('target',target)]:
 receipt=json.loads(Path(d['source_refs'][channel+'_receipt']['path']).read_text());model=json.loads(Path(receipt['model_ref']['path']).read_text());z=np.load(BytesIO(Path(d['source_refs'][channel+'_tensors']['path']).read_bytes()),allow_pickle=False)
 ng=sum(z['group_years']==2023);off=z['offsets'][:ng+1];nc=int(off[-1]);X=z['X'][:nc];y=z['labels'][:nc];B=z['budgets'][:ng];p=model['preprocessing'];theta=np.array(model['parameters']);data=dict(X=X,labels=y,budgets=B,offsets=off.tolist())
 if channel=='target':data['target_budgets']=z['target_budgets'][:ng]
 mu,H,zz=rush.forward(theta,X);W,b,v,a=rush._unpack(theta,X.shape[1],8);s=np.exp(-np.logaddexp(0.,-zz));mask=np.r_[np.ones(W.size,dtype=bool),np.zeros(8,dtype=bool),np.ones(8,dtype=bool),False];ri=np.flatnonzero(mask)
 cellscale=np.repeat(np.sqrt(2/(ng*np.diff(off)))/p['cell_label_scale'],np.diff(off));Pscale=np.sqrt(2/ng)/p['budget_label_scale'];Tscale=np.sqrt(2/ng)/p['target_budget_label_scale']if channel=='target'else None
 def grouped(values,target_only=False):return np.asarray([values[lo:(hi-1 if target_only else hi)].sum()for lo,hi in zip(off[:-1],off[1:])])
 residual=np.r_[cellscale*(mu-y),Pscale*(grouped(mu)-B),*( [Tscale*(grouped(mu,True)-data['target_budgets'])]if channel=='target'else[]),np.sqrt(.001)*theta[ri]]
 def JVP(q):
  qW,qb,qv,qa=rush._unpack(q,X.shape[1],8);delta=s*(((1-H**2)*(X@qW+qb))@v+H@qv+qa)
  return np.r_[cellscale*delta,Pscale*grouped(delta),*([Tscale*grouped(delta,True)]if channel=='target'else[]),np.sqrt(.001)*q[ri]]
 def adjoint(q):
  qm=cellscale*q[:nc]+np.repeat(Pscale*q[nc:nc+ng],np.diff(off));position=nc+ng
  if channel=='target':
   for j,(lo,hi)in enumerate(zip(off[:-1],off[1:])):qm[lo:hi-1]+=Tscale*q[position+j]
   position+=ng
  dz=qm*s;dh=dz[:,None]*v*(1-H**2);answer=np.r_[(X.T@dh).ravel(),dh.sum(0),H.T@dz,dz.sum()];answer[ri]+=np.sqrt(.001)*q[position:];return answer
 F,g=module.objective(theta,data,p);g2=adjoint(residual);rng=np.random.default_rng(17);q=rng.normal(size=len(theta));q/=np.linalg.norm(q);u=rng.normal(size=len(residual));u/=np.linalg.norm(u);left=float(JVP(q)@u);right=float(q@adjoint(u))
 errF=float(abs(.5*(residual@residual)-F));errG=float(abs(g-g2).max());adjerr=abs(left-right);assert errF<1e-13 and errG<1e-13 and adjerr<1e-13
 out[channel]=dict(residuals=len(residual),parameters=len(theta),half_squared_residual_objective_error=errF,JTresidual_gradient_max_error=errG,random_JVP_adjoint_dot_error=adjerr,regularization='OriginalsqrtL2 weights rows, biases excluded',scope='Exact same objective/parameters/no fitted updates')
result=dict(elapsed_seconds=time.perf_counter()-timer,channels=out,optimizer_calls=0,holdout_evaluations=0,parameter_updates=0)
(R/'RESIDUAL_CHECK.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
