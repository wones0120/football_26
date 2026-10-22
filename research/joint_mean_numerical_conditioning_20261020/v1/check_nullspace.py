"""Small TRAIN-only nullspace/penalty equivalence check; no fitting."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
from pathlib import Path
from io import BytesIO
import json,time
import numpy as np
from backend.app.product_services import joint_rush_conditional_means as rush,joint_target_pass_conditional_means as target
R=Path(__file__).resolve().parent;timer=time.perf_counter();d=json.loads((R/'DIAGNOSIS.json').read_text());out={}
for channel,module in [('rush',rush),('target',target)]:
 rr=json.loads(Path(d['source_refs'][channel+'_receipt']['path']).read_text());model=json.loads(Path(rr['model_ref']['path']).read_text());archive=np.load(BytesIO(Path(d['source_refs'][channel+'_tensors']['path']).read_bytes()),allow_pickle=False)
 n=sum(archive['group_years']==2023);off=archive['offsets'][:n+1];X=archive['X'][:off[-1]];data=dict(X=X,labels=archive['labels'][:off[-1]],budgets=archive['budgets'][:n],offsets=off.tolist())
 if channel=='target':data['target_budgets']=archive['target_budgets'][:n]
 mean=X.mean(0);C=X-mean;u,s,vt=np.linalg.svd(C,full_matrices=False);threshold=np.finfo(float).eps*max(C.shape)*s[0];rank=sum(s>threshold);V=vt[:rank].T
 theta=np.array(model['parameters']);W,b,v,a=rush._unpack(theta,X.shape[1],8);projection=V@(V.T@W);null=W-projection;newb=b+mean@null;newtheta=np.r_[projection.ravel(),newb,v,a];F,g=module.objective(theta,data,model['preprocessing']);Fn,gn=module.objective(newtheta,data,model['preprocessing']);removed_penalty=.001*np.sum(null**2)/2
 before=np.tanh(X@W+b);after=np.tanh(X@projection+newb)
 GW,gb,gv,ga=rush._unpack(g,X.shape[1],8);effectiveGW=GW-mean[:,None]*gb;nullgrad=effectiveGW-V@(V.T@effectiveGW)
 out[channel]=dict(centered_design_rank=int(rank),features=X.shape[1],removed_input_parameters=int((X.shape[1]-rank)*8),W_norm=float(np.linalg.norm(W)),null_W_norm=float(np.linalg.norm(null)),null_W_fraction=float(np.linalg.norm(null)/np.linalg.norm(W)),objective_before=F,objective_after_null_removed=Fn,removed_null_weight_penalty=float(removed_penalty),exact_penalty_identity_error=float(abs(F-Fn-removed_penalty)),max_training_hidden_error=float(abs(before-after).max()),effective_input_gradient_norm=float(np.linalg.norm(effectiveGW)),null_gradient_norm=float(np.linalg.norm(nullgrad)),null_gradient_fraction=float(np.linalg.norm(nullgrad)/np.linalg.norm(effectiveGW)),null_gradient_equals_L2_error=float(abs(nullgrad-.001*null).max()),rank_scope='Machineprecision numerical rank,not a modeling columnselection rule')
result=dict(elapsed_seconds=time.perf_counter()-timer,channels=out,optimizer_calls=0,holdout_evaluations=0,parameter_updates_applied=0,scope='Analytical nullspace objective check only; no estimator created or fitted')
(R/'NULLSPACE_CHECK.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
