"""New residual/Jacobian equivalence only, on already-approved TRAIN arrays."""
from pathlib import Path
from io import BytesIO
import hashlib,json,time
import numpy as np
from backend.app.product_services import joint_mean_exact_residual_solver as new
R=Path(__file__).resolve().parent;timer=time.monotonic();out={};refs={}
def checked(ref):
 b=Path(ref['path']).read_bytes();assert len(b)==ref['bytes']and hashlib.sha256(b).hexdigest()==ref['sha256'];return b
for channel,package in [('rush','joint_rush_conditional_means_20261020'),('target','joint_target_pass_conditional_means_20261020')]:
 manifest=json.loads(Path('research',package,'v1/MANIFEST.json').read_text());z=np.load(BytesIO(checked(manifest['tensor_ref'])),allow_pickle=False);prep=manifest['preprocessing'];ng=int(sum(z['group_years']==2023));nc=int(z['offsets'][ng]);d=dict(X=z['X'][:nc],labels=z['labels'][:nc],budgets=z['budgets'][:ng],offsets=z['offsets'][:ng+1].tolist());refs[channel+'_tensors']=manifest['tensor_ref']
 if channel=='target':d['target_budgets']=z['target_budgets'][:ng]
 module=new.rush if channel=='rush'else new.target;points={'fresh_initial':new.rush.initial_parameters(d['X'].shape[1])}
 for version in('v1','v2'):
  rec=json.loads(Path('research/joint_conditional_mean_fits_20261020',version,channel+'.json').read_text());points[version+'_failed']=np.asarray(json.loads(checked(rec['model_ref']))['parameters']);refs[channel+'_'+version+'_failed_model']=rec['model_ref']
 checks={}
 for name,theta in points.items():
  r,J=new.residual_system(theta,d,prep,channel=channel);F,g=module.objective(theta,d,prep);rng=np.random.default_rng(17);q=rng.normal(size=len(theta));q/=np.linalg.norm(q);u=rng.normal(size=len(r));u/=np.linalg.norm(u)
  Ferror=abs(.5*(r@r)-F);gerror=float(np.max(abs(J.rmatvec(r)-g)));adj=abs(float(J.matvec(q)@u-q@J.rmatvec(u)))
  fd=(new.residual_system(theta+1e-5*q,d,prep,channel=channel)[0]-new.residual_system(theta-1e-5*q,d,prep,channel=channel)[0])/2e-5
  fderr=float(np.max(abs(J.matvec(q)-fd)))
  assert Ferror<1e-12 and gerror<1e-12 and adj<1e-12 and fderr<1e-8
  checks[name]=dict(objective_error=Ferror,gradient_error=gerror,adjoint_error=adj,jvp_finite_difference_max_error=fderr,residuals=len(r),parameters=len(theta))
 out[channel]=checks
result=dict(status='PASS',checks=out,source_refs=refs,elapsed_seconds=time.monotonic()-timer,optimizer_calls=0,holdout_evaluations=0)
(R/'TRAIN_IDENTITY_CHECK.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
