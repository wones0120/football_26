"""TRAIN/2024 saved-artifact mechanism diagnosis; no fitting or2025evaluation."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
from pathlib import Path
from io import BytesIO
from datetime import datetime,UTC
import json,hashlib,time
import numpy as np
from scipy.special import expit
from backend.app.product_services import joint_rush_conditional_means as rush,joint_target_pass_conditional_means as target,joint_mean_exact_residual_solver as solver
R=Path(__file__).resolve().parent;start=datetime.now(UTC);timer=time.perf_counter();refs={}
def ref(path):
 path=Path(path);b=path.read_bytes();return dict(path=str(path.resolve()),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def read(name,r):
 b=Path(r['path']).read_bytes();assert len(b)==r['bytes']and hashlib.sha256(b).hexdigest()==r['sha256'];refs[name]=r;return b
def metric(y,p):
 y=np.asarray(y);p=np.asarray(p);e=p-y;return dict(n=len(y),mae=float(abs(e).mean()),rmse=float(np.sqrt(np.mean(e*e))),bias=float(e.mean()),observed_sum=float(y.sum()),predicted_sum=float(p.sum()))
rp=Path('research/joint_conditional_mean_fits_20261020/v3/rush.json');r=json.loads(rp.read_text());refs['rush_receipt']=ref(rp);model=json.loads(read('rush_model',r['model_ref']));mp=Path(r['manifest_path']);m=json.loads(mp.read_text());refs['rush_manifest']=ref(mp);z=np.load(BytesIO(read('rush_tensors',m['tensor_ref'])),allow_pickle=False)
ng=int(np.sum(z['group_years']<=2024));off=z['offsets'][:ng+1];nc=int(off[-1]);X=z['X'][:nc];raw=z['raw_inputs'][:nc];y=z['labels'][:nc];B=z['budgets'][:ng];years=z['group_years'][:ng];mu,H,logit=rush.forward(np.array(model['parameters']),X);p=model['preprocessing'];cols=m['feature_columns'];matched=json.loads(read('rush_baseline_matches',m['saved_baseline_matches_ref']));out={}
for year in(2023,2024):
 ids=np.flatnonzero(years==year);cellids=np.concatenate([np.arange(off[j],off[j+1])for j in ids]);candidate=np.ones(nc,dtype=bool);candidate[off[1:]-1]=False;cis=cellids[candidate[cellids]];rest=off[ids+1]-1;ghat=np.asarray([mu[off[j]:off[j+1]].sum()for j in ids]);oracle=mu.copy();budgetSSE=allocationSSE=cross=0.;role= {};exposure={}
 for j,bhat in zip(ids,ghat):
  lo,hi=off[j:j+2];s=mu[lo:hi]/bhat;budgetpart=s*(bhat-B[j]);allocpart=B[j]*s-y[lo:hi];assert np.allclose(budgetpart+allocpart,mu[lo:hi]-y[lo:hi]);budgetSSE+=float(budgetpart@budgetpart);allocationSSE+=float(allocpart@allocpart);cross+=float(2*budgetpart@allocpart);oracle[lo:hi]=B[j]*s
 assert np.isclose(budgetSSE+allocationSSE+cross,np.sum((mu[cellids]-y[cellids])**2))
 roleids={}
 for name in('QB','RB','WR','TE','FB','other'):
  mask=raw[cis,cols.index('latest_prior_role_'+name)]==1;roleids[name]=cis[mask]
 unknown=np.ones(len(cis),dtype=bool)
 for cells in roleids.values():unknown&=~np.isin(cis,cells)
 roleids['UNKNOWN_PRIOR_ROLE']=cis[unknown]
 for name,cells in roleids.items():
  stats=metric(y[cells],mu[cells]);stats['budget_bias_per_group']=float(np.sum(mu[cells]-y[cells])/len(ids));role[name]=stats
 for name,mask in [('unknown',~np.isfinite(raw[cis,cols.index('scheduled3_carries_exposure')])),('known_zero',raw[cis,cols.index('scheduled3_carries_exposure')]==0),('known_positive',raw[cis,cols.index('scheduled3_carries_exposure')]>0)]:
  cells=cis[mask];stats=metric(y[cells],mu[cells]);stats['positive_current_labels']=int(np.sum(y[cells]>0));exposure[name]=stats
 cellloss=np.mean([np.mean((mu[off[j]:off[j+1]]-y[off[j]:off[j+1]])**2)/p['cell_label_scale']**2 for j in ids]);bloss=float(np.mean((ghat-B[ids])**2)/p['budget_label_scale']**2)
 ratios=1+np.diff(off)[ids]**2*p['cell_label_scale']**2/p['budget_label_scale']**2
 selected={}
 for name,rows in matched.items():
  rows=[v for v in rows if v['group_index']in set(ids)];index=np.array([off[v['group_index']]+v['cell_index']for v in rows]);labels=np.array([v['actual']for v in rows]);saved=np.array([v['saved_prediction']for v in rows]);assert np.array_equal(labels,y[index]);selected[name]=dict(new=metric(labels,mu[index]),saved=metric(labels,saved),oracle_realized_budget_allocation_only=metric(labels,oracle[index]))
 # A derivative of the DATA objective along a hypothetical new role-logit
 # offset measures a missing representational direction, not an applied update.
 dmu=np.zeros(nc)
 for j in ids:
  lo,hi=off[j:j+2];dmu[lo:hi]=(2*(mu[lo:hi]-y[lo:hi])/((hi-lo)*p['cell_label_scale']**2)+2*(mu[lo:hi].sum()-B[j])/p['budget_label_scale']**2)/len(ids)
 offsets={name:float(np.sum(dmu[cells]*expit(logit[cells])))for name,cells in roleids.items()}
 out[str(year)]=dict(groups=len(ids),candidate=metric(y[cis],mu[cis]),budget=metric(B[ids],ghat),outside_rest=metric(y[rest],mu[rest]),role=role,prior_exposure=exposure,loss_components=dict(mean_standardized_cell_loss=float(cellloss),mean_standardized_budget_loss=bloss),mu_space_loss_common_vs_allocation_contrast_curvature=dict(min=float(ratios.min()),median=float(np.median(ratios)),max=float(ratios.max()),meaning='1+m²*TRAINcellvariance/TRAINbudgetvariance; analyticlossgeometry,notparameterHessianconditionnumber'),cell_squared_error_decomposition=dict(budget_component=budgetSSE,allocation_at_realized_budget_component=allocationSSE,cross_term=cross,total=budgetSSE+allocationSSE+cross,scope='Oracle realizedbudget counterfactual diagnostic ONLY; notdeployable,notcausal attribution,never a corrected prediction'),matched=selected,data_loss_derivative_new_role_logit_offset=offsets,scope='TRAIN/2024validation only; oraclecounterfactual and rolepositive/zero strata diagnostic,neverstructuralzero')
# Failed target: TRAIN-only loss-part gradient decomposition; no predict API.
tp=Path('research/joint_conditional_mean_fits_20261020/v3/target.json');tr=json.loads(tp.read_text());refs['target_receipt']=ref(tp);tm=json.loads(read('target_model',tr['model_ref']));mt=json.loads(Path(tr['manifest_path']).read_text());zt=np.load(BytesIO(read('target_tensors',mt['tensor_ref'])),allow_pickle=False);nt=int(np.sum(zt['group_years']==2023));ot=zt['offsets'][:nt+1];ct=int(ot[-1]);dt=dict(X=zt['X'][:ct],labels=zt['labels'][:ct],budgets=zt['budgets'][:nt],target_budgets=zt['target_budgets'][:nt],offsets=ot.tolist());theta=np.array(tm['parameters']);F,g=target.objective(theta,dt,tm['preprocessing']);res,J=solver.residual_system(theta,dt,tm['preprocessing'],channel='target');parts={};summed=np.zeros_like(g)
for name,a,b in [('cell',0,ct),('pass_budget',ct,ct+nt),('target_budget',ct+nt,ct+2*nt),('original_ridge',ct+2*nt,len(res))]:
 u=np.zeros_like(res);u[a:b]=res[a:b];gradient=J.rmatvec(u);summed+=gradient;parts[name]=dict(objective=float(.5*(res[a:b]@res[a:b])),gradient_inf=float(abs(gradient).max()),gradient_l2=float(np.linalg.norm(gradient)))
assert np.max(abs(summed-g))<1e-12
W,b,v,a=rush._unpack(theta,dt['X'].shape[1],8);bounds=[('input_weights',0,W.size),('hidden_bias',W.size,W.size+8),('output_weights',W.size+8,W.size+16),('output_bias',len(theta)-1,len(theta))];blocks={name:dict(gradient_inf=float(abs(g[lo:hi]).max()),gradient_l2=float(np.linalg.norm(g[lo:hi])))for name,lo,hi in bounds}
cp=tm['preprocessing'];Hmu=[]
for lo,hi in zip(ot[:-1],ot[1:]):
 size=hi-lo;h=np.eye(size)*2/(nt*size*cp['cell_label_scale']**2);ones=np.ones(size);targets=ones.copy();targets[-1]=0;h+=2/(nt*cp['budget_label_scale']**2)*np.outer(ones,ones)+2/(nt*cp['target_budget_label_scale']**2)*np.outer(targets,targets);eig=np.linalg.eigvalsh(h);Hmu.append(float(eig[-1]/eig[0]))
targetout=dict(status=tm['status'],nfev=tm['nfev'],njev=tm['njev'],native_reason=tm['solver_message'],original_gradient_inf=float(abs(g).max()),threshold=1e-5,gradient_parts=parts,gradient_blocks=blocks,gradient_cancellation_ratio=sum(v['gradient_l2']for v in parts.values())/float(np.linalg.norm(g)),mean_space_loss_common_vs_contrast_curvature=dict(min=min(Hmu),median=float(np.median(Hmu)),max=max(Hmu),scope='Exactmean-space squaredloss spectrum,NOTfullparameterHessian'),inner_operator_calls=tm['solver_counters'],caution='No recorded innerLSMR stop codes: counterscannotproveinnermaxiter/conlimcausedfailure. NoanalyticJacobianbugfound; nonstationaryweakallocationdirections/coupledobjective arehypotheses,notuniquecause.',target_inference_api_calls=0)
result=dict(version='joint_mean_generalization_diagnosis_v1',started_at=start.isoformat(),completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.perf_counter()-timer,source_refs=refs,rush=out,target_train_only=targetout,optimizer_calls=0,parameter_updates=0,new_2025_evaluations=0,activation=False)
(R/'DIAGNOSIS.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
print(json.dumps(dict(elapsed_seconds=result['elapsed_seconds'],rush={y:dict(budget=v['budget'],tree_matched=v['matched']['pressure_count_model_fits_20261020_tree'],mean_space_curvature=v['mu_space_loss_common_vs_allocation_contrast_curvature'],newroleoffset=v['data_loss_derivative_new_role_logit_offset'])for y,v in out.items()},target=targetout),indent=2))
