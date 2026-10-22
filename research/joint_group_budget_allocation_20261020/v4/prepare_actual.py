"""New group-only preprocessing from frozen prior cell arrays; no source/fit."""
from pathlib import Path
from datetime import datetime,UTC
from io import BytesIO
import hashlib,json,time
import numpy as np
from backend.app.product_services import joint_group_budget_allocation as m
R=Path(__file__).resolve().parent;started=datetime.now(UTC);timer=time.monotonic();channels={}
def file_ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p.resolve()),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))
def read(ref):
 b=Path(ref['path']).read_bytes();assert len(b)==ref['bytes']and hashlib.sha256(b).hexdigest()==ref['sha256'];return b
def save(b,kind,suffix):
 sha=hashlib.sha256(b).hexdigest();p=Path('artifacts',kind,sha+suffix);p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==b
 else:
  with p.open('xb')as f:f.write(b)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(b))
for channel,folder in [('rush','joint_rush_conditional_means_20261020'),('target','joint_target_pass_conditional_means_20261020')]:
 p=Path('research',folder,'v1/MANIFEST.json');old=json.loads(p.read_text());z=np.load(BytesIO(read(old['tensor_ref'])),allow_pickle=False);meta=json.loads(read(old['group_metadata_ref']));raw=z['raw_inputs'];offsets=z['offsets'];years=z['group_years']
 assert old['feature_columns'][:38]==list(m.TEAM_ADDED)
 rows=[];groups=[]
 for g,lo,hi in zip(meta,offsets[:-1],offsets[1:]):
  x=raw[lo,:38]
  assert all(np.array_equal(row,x,equal_nan=True)for row in raw[lo:hi,:38])
  rows.append(x.copy());groups.append(dict(period=g['period'],cells=[dict(features={k:None if np.isnan(v)else float(v)for k,v in zip(m.TEAM_ADDED,x)})]))
 group_prep=m.fit_group_preprocessing(groups);G=m.transform_group_inputs(groups,group_prep);ng=int(sum(years==2023));nc=int(offsets[ng]);data=dict(X=z['X'][:nc],G=G[:ng],labels=z['labels'][:nc],budgets=z['budgets'][:ng],offsets=offsets[:ng+1].tolist())
 if channel=='target':data['target_budgets']=z['target_budgets'][:ng]
 theta,means=m.initial_parameters(data,channel=channel);checks={};rng=np.random.default_rng(17)
 for name,t in [('fresh_initial',theta),('fixed_small_perturbation',theta+rng.normal(0,.01,len(theta)))]:
  F,grad=m.objective(t,data,old['preprocessing'],channel=channel);r,J=m.residual_system(t,data,old['preprocessing'],channel=channel);q=rng.normal(size=len(t));q/=np.linalg.norm(q);u=rng.normal(size=len(r));u/=np.linalg.norm(u)
  fd=(m.residual_system(t+1e-5*q,data,old['preprocessing'],channel=channel)[0]-m.residual_system(t-1e-5*q,data,old['preprocessing'],channel=channel)[0])/2e-5
  fe=abs(F-.5*(r@r));ge=float(np.max(abs(J.rmatvec(r)-grad)));ad=abs(float(J.matvec(q)@u-q@J.rmatvec(u)));de=float(np.max(abs(J.matvec(q)-fd)))
  assert fe<1e-10 and ge<1e-12 and ad<1e-10 and de<1e-7
  prefix=data['X'].shape[1]*8+16
  for head in range(1 if channel=='rush'else 2):
   pure=np.zeros(len(r));lo=nc+head*ng;pure[lo:lo+ng]=1.;assert np.array_equal(J.rmatvec(pure)[:prefix],np.zeros(prefix))
  checks[name]=dict(objective_error=fe,gradient_error=ge,adjoint_error=ad,jvp_finite_difference_error=de,budget_only_score_gradient_exact_zero=True)
 # Independent TRAIN-once/group statistics; later rows/labels never inform prep.
 groupraw=np.asarray(rows);tr=groupraw[years==2023];med=np.asarray([np.nanmedian(tr[:,j])if np.isfinite(tr[:,j]).any()else 0. for j in range(38)])
 filled=np.where(np.isnan(tr),med,tr);center=filled.mean(0);scale=filled.std(0);scale[scale==0]=1.
 assert np.array_equal(med,group_prep['medians'])and np.array_equal(center,group_prep['centers'])and np.array_equal(scale,group_prep['scales'])
 state=m.forward(theta,data,channel=channel);assert np.allclose(state['heads'],means,rtol=1e-12,atol=1e-12)
 buf=BytesIO();np.savez_compressed(buf,raw_group_inputs=groupraw,G=G,group_years=years,offsets=offsets)
 channels[channel]=dict(parent_manifest_ref=file_ref(p),parent_prefit_gate_ref=file_ref(p.with_name('HIGH_REVIEW.json')),original_tensor_ref=old['tensor_ref'],original_group_metadata_ref=old['group_metadata_ref'],original_baseline_matches_ref=old['saved_baseline_matches_ref'],original_feature_columns=old['feature_columns'],group_counts=old['group_counts'],group_feature_columns=list(m.TEAM_ADDED),group_preprocessing=group_prep,group_tensor_ref=save(buf.getvalue(),'joint_group_budget_inputs','.npz'),initial_parameter_ref=save(json.dumps(theta.tolist(),separators=(',',':')).encode(),'joint_group_budget_initial_parameters','.json'),train_group_head_mean_initialization=means.tolist(),parameters=len(theta),score_parameters_without_common_bias=data['X'].shape[1]*8+16,group_parameters=G.shape[1]*len(means)+len(means),group_array_shape=list(G.shape),checks=checks)
manifest=dict(version=m.VERSION,status='PREFIT_REVIEW_ONLY_NO_OPTIMIZER',started_at=started.isoformat(),completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-timer,channels=channels,contract_ref=file_ref('research/joint_mean_generalization_diagnosis_20261020/v1/REPAIR_CONTRACT.json'),solver_options=m.SOLVER_OPTIONS,hard_cap_seconds=300,architecture='Jointaffinegroupsoftplusmeans+8tanhnormalizedmeanallocations;groupinputonce/group excludescandidatearity/identity/currentfacts',raw_loss='Originalequalgroupcell+budget(+targetbudget)rawSSE/TRAINscales;L2.001alltrainableweightsnotbiases;nooutcome-selectedweights',original_source_cohorts_fields_labels_and_allocation_preprocessing_unchanged=True,group_preprocessor_train_unit='one2023TRAINgroup',optimizer_calls=0,holdout_model_evaluations=0,activation=False,year2026='NOTTRAINED/NO_CURRENT_APPROVED_JOINT_COHORT; separateallweekstatusmanifestandBsourceauditmustgatefutureeval;nocoldstartskipsorimputedlabels')
(R/'MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps({c:{k:v[k]for k in('group_counts','parameters','group_array_shape','train_group_head_mean_initialization','checks')}for c,v in channels.items()},indent=2))
