"""TRAIN-only fixed-point numerical diagnosis; no optimizer or holdout outputs."""
from pathlib import Path
from datetime import datetime,UTC
from io import BytesIO
import hashlib,json,time
import numpy as np
from backend.app.product_services import joint_rush_conditional_means as rush
from backend.app.product_services import joint_target_pass_conditional_means as target

R=Path(__file__).resolve().parent;started=datetime.now(UTC);timer=time.monotonic();refs={}
def read(name,ref):
 b=Path(ref['path']).read_bytes();assert len(b)==ref['bytes']and hashlib.sha256(b).hexdigest()==ref['sha256'];refs[name]=ref;return b
def file_ref(p):
 b=p.read_bytes();return dict(path=str(p.resolve()),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))
out={}
for channel,module,folder in(('rush',rush,'joint_rush_conditional_means_20261020'),('target',target,'joint_target_pass_conditional_means_20261020')):
 receipt_path=Path('research/joint_conditional_mean_fits_20261020/v1')/(channel+'.json');receipt=json.loads(receipt_path.read_text());refs[channel+'_fit_receipt']=file_ref(receipt_path)
 manifest_path=Path('research',folder,'v1/MANIFEST.json');manifest=json.loads(manifest_path.read_text());refs[channel+'_manifest']=file_ref(manifest_path)
 model=json.loads(read(channel+'_failed_model',receipt['model_ref']));assert model['status']=='fit_failed'and model['iterations']==500
 archive=np.load(BytesIO(read(channel+'_tensor',manifest['tensor_ref'])),allow_pickle=False)
 years=archive['group_years'];offsets=archive['offsets'];train_group_indices=np.flatnonzero(years==2023)
 # Only TRAIN slices are materialized into numerical diagnostics. The shared
 # archive also stores other years, which are never evaluated or summarized.
 assert np.array_equal(train_group_indices,np.arange(len(train_group_indices)))
 last=int(offsets[len(train_group_indices)]);X=archive['X'][:last];labels=archive['labels'][:last];budgets=archive['budgets'][train_group_indices]
 data=dict(X=X,labels=labels,budgets=budgets,offsets=offsets[:len(train_group_indices)+1].tolist())
 if channel=='target':data['target_budgets']=archive['target_budgets'][train_group_indices]
 theta=np.asarray(model['parameters']);prep=model['preprocessing'];loss,grad=module.objective(theta,data,prep)
 initial=rush.initial_parameters(X.shape[1]);initial_loss,initial_grad=module.objective(initial,data,prep)
 assert np.isfinite(theta).all()and np.isfinite(grad).all()and abs(loss-model['objective'])<1e-10
 hidden=model['recipe']['hidden_units'];W,b,v,a=rush._unpack(theta,X.shape[1],hidden)
 mu,H,z=rush.forward(theta,X,hidden)
 # Fixed tiny symmetric directional derivative checks are not optimizer steps.
 direction=-grad/max(1.,float(np.linalg.norm(grad)))
 epsilon=1e-4
 fplus=module.objective(theta+epsilon*direction,data,prep)[0]
 fminus=module.objective(theta-epsilon*direction,data,prep)[0]
 directional=float(grad@direction);numeric=(fplus-fminus)/(2*epsilon)
 block=dict(input_weights=grad[:W.size],hidden_bias=grad[W.size:W.size+hidden],output_weights=grad[W.size+hidden:-1],output_bias=grad[-1:])
 # Diagonal Gauss-Newton cell curvature proxy, computed without a dense Hessian.
 # This diagnoses scale variation; it is NOT an independently estimated full
 # condition number and does not choose hyperparameters from validation/test.
 dmu=np.exp(-np.logaddexp(0.,-z));dh=dmu[:,None]*v*(1-H**2)
 diagW=(X**2).T@(dh**2)/len(X)+model['recipe']['l2']
 diagv=np.mean((dmu[:,None]*H)**2,axis=0)+model['recipe']['l2']
 diag=np.r_[diagW.ravel(),np.mean(dh**2,axis=0),diagv,np.mean(dmu**2)]
 positive=diag[diag>0]
 feature_norm=np.linalg.norm(grad[:W.size].reshape(W.shape),axis=1);names=manifest['transformed_columns']
 top=np.argsort(-feature_norm,kind='stable')[:10]
 cell=0.;P=0.;T=0.
 for j,(lo,hi)in enumerate(zip(data['offsets'][:-1],data['offsets'][1:])):
  cell+=float(np.mean((mu[lo:hi]-labels[lo:hi])**2))/prep['cell_label_scale']**2/len(budgets)
  P+=float((mu[lo:hi].sum()-budgets[j])**2)/prep['budget_label_scale']**2/len(budgets)
  if channel=='target':T+=float((mu[lo:hi-1].sum()-data['target_budgets'][j])**2)/prep['target_budget_label_scale']**2/len(budgets)
 ridge=model['recipe']['l2']*(float(np.sum(W**2))+float(np.sum(v**2)))/2
 assert abs(cell+P+T+ridge-loss)<1e-10
 out[channel]=dict(train_groups=len(train_group_indices),train_cells=last,parameters=len(theta),iterations=receipt['optimizer_iterations'],stop=receipt['optimizer_message'],
  objective=loss,saved_objective=model['objective'],initial_objective=initial_loss,initial_gradient_inf=float(np.max(abs(initial_grad))),
  final_gradient_inf=float(np.max(abs(grad))),final_gradient_l2=float(np.linalg.norm(grad)),gtol=model['recipe']['gtol'],ftol=model['recipe']['ftol'],
  gradient_gtol_multiple=float(np.max(abs(grad)))/model['recipe']['gtol'],
  loss_components=dict(cell=cell,pass_or_rush_budget=P,target_budget=T,ridge=ridge),
  finite=True,input_abs_max=float(np.max(abs(X))),zero_variance_transformed_columns=int(np.sum(X.std(0)==0)),
  hidden_tanh_abs_gt_0999_fraction=float(np.mean(abs(H)>.999)),softplus_logit_abs_gt_20_fraction=float(np.mean(abs(z)>20)),
  softplus_logit_min=float(z.min()),softplus_logit_max=float(z.max()),parameter_abs_max=float(np.max(abs(theta))),
  gradient_blocks={k:dict(l2=float(np.linalg.norm(values)),inf=float(np.max(abs(values))))for k,values in block.items()},
  top_input_gradient_columns=[dict(column=names[i],gradient_l2=float(feature_norm[i]))for i in top],
  diagonal_cell_curvature_proxy=dict(min_positive=float(positive.min()),max=float(positive.max()),ratio=float(positive.max()/positive.min()),scope='Unweighted cell-Jacobian diagonal plus fixedweightL2;not fullHessian/conditionnumber'),
  fixed_directional_check=dict(epsilon=epsilon,analytic=directional,numeric=numeric,absolute_error=abs(numeric-directional),objective_minus=fminus,objective_plus=fplus,optimizer_invocations=0),
  inference_or_holdout_metrics_produced=False)
result=dict(version='joint_mean_train_stopping_diagnosis_v1',started_at=started.isoformat(),completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-timer,
 source_refs=refs,channels=out,optimizer_invocations=0,fits=0,holdout_objective_or_prediction_evaluations=0,activation=False)
(R/'DIAGNOSIS.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');print(json.dumps(out,indent=2))
