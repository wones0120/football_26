"""Freeze prefit tensors from approved caches. This script never fits a model."""
from pathlib import Path
from datetime import datetime, UTC
from collections import Counter
from io import BytesIO
import hashlib,json,time
import numpy as np
from backend.app.product_services import joint_target_pass_conditional_means as model
from backend.app.product_services.scheduled_workload_efficiency_model_inputs import _pool,TEAM_ADDED,PLAYER_ADDED
from backend.app.product_services.model_weekly_workload_components import CHANNEL_FIELDS

R=Path(__file__).resolve().parent
started=datetime.now(UTC);timer=time.monotonic();refs={}
def load(name,ref,cap):
    if ref['bytes']>cap:raise ValueError('Bounded cache cap')
    b=Path(ref['path']).read_bytes()
    assert len(b)==ref['bytes'] and hashlib.sha256(b).hexdigest()==ref['sha256']
    refs[name]=ref
    return json.loads(b)
def save(value,kind,suffix='.json'):
    b=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode() if suffix=='.json' else value
    sha=hashlib.sha256(b).hexdigest();p=Path('artifacts',kind,sha+suffix);p.parent.mkdir(exist_ok=True)
    if p.exists():assert p.read_bytes()==b
    else:
        with p.open('xb')as f:f.write(b)
        p.chmod(0o444)
    return dict(path=str(p.resolve()),sha256=sha,bytes=len(b))
def file_ref(p):
    p=Path(p);b=p.read_bytes();return dict(path=str(p.resolve()),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))

weekly_receipt=json.loads(Path('research/joint_candidate_label_coverage_20261020/v1/ACTUAL_RECEIPT.json').read_text())
zero_receipt=json.loads(Path('research/cached_event_zero_proof_20261020/v1/ACTUAL_RECEIPT.json').read_text())
source=load('source_component',weekly_receipt['source_refs']['source_component'],80*1024*1024)
contexts=load('prior_contexts',weekly_receipt['source_refs']['reviewed_prior_contexts'],6*1024*1024)
original=load('candidate_groups',weekly_receipt['full_ref'],48*1024*1024)
proofs=load('zero_proof',zero_receipt['full_ref'],24*1024*1024)
source_actor={};source_team={}
for row in source['actor_rows']:
    if row['source_player_id'] is None:continue
    k=row['game_id'],row['team'],row['source_player_id']
    assert k not in source_actor;source_actor[k]=row
for row in source['team_game_rows']:
    k=row['game_id'],row['team'];assert k not in source_team;source_team[k]=row
ctxmap={(r['game_id'],r['team']):r for r in contexts['team_contexts']}
origmap={(r['game_id'],r['team']):r for r in original['groups']}
admission_path=Path('research/target_budget_census_feasibility_20261020/v1/HIGH_ADMISSION.json')
admission=json.loads(admission_path.read_text());admitted_keys={tuple(k)for k in admission['qualified_fixed_keys']}
assert len(admitted_keys)==279
columns=[*TEAM_ADDED,*PLAYER_ADDED,'is_known_outside_rest','prior_candidate_count','is_source_pass_minus_target_remainder']
assert len(columns)==70 and len(set(columns))==70

def candidate_features(g,sid,ctx):
    team=g['team'];ids=g['prior_games'];rs=[source_actor.get((gid,team,sid))for gid in ids]
    pooled=_pool(rs,actor=True)
    fields={'scheduled3_'+k:v for k,v in pooled.items()if k not in('known_source_games','unknown_source_games')}
    fields['scheduled3_known_actor_rows']=sum(r is not None for r in rs)
    fields['scheduled3_unknown_actor_rows']=3-fields['scheduled3_known_actor_rows']
    for c,field in CHANNEL_FIELDS.items():
        nums=[r['counts'][c]if r else None for r in rs]
        dens=[source_team[(gid,team)]['values'][field]for gid in ids]
        valid=all(v is not None for v in nums+dens)
        n,d=(sum(nums),sum(dens))if valid else(None,None)
        if valid:assert n<=d
        fields[f'scheduled3_{c}_pooled_share']=n/d if valid and d>0 else None
    latest=rs[-1]['source_position']if rs[-1]else None
    fields.update({'latest_prior_role_'+r:None if latest is None else int(latest==r if r!='other' else latest not in{'QB','RB','WR','TE','FB'})for r in('QB','RB','WR','TE','FB','other')})
    roles=[r['source_position']if r else None for r in rs]
    fields['scheduled3_role_consistent']=int(len(set(roles))==1)if all(r is not None for r in roles)else None
    assert set(fields)==set(PLAYER_ADDED)
    return {**ctx['features'],**fields,'is_known_outside_rest':0,'prior_candidate_count':g['candidate_count'],'is_source_pass_minus_target_remainder':0}

groups=[];counts=Counter();zero_labels=Counter();gate_keys=[]
for p in sorted(proofs['groups'],key=lambda g:(g['period'],g['game_id'],g['team'])):
    ch=p['channels']['targets']
    if (p['game_id'],p['team'])not in admitted_keys:continue
    assert ch['canonical_group_known_credit_and_budget_compatible']
    assert ch['known_weekly_native_credit_compatibility']['unknown_recipient_or_eligibility_membership_retained']is False
    assert ch['known_weekly_native_credit_compatibility']['known_weekly_candidate_exact_event_credit_unassessed']==0
    key=p['game_id'],p['team'];g=origmap[key];ctx=ctxmap[key]
    assert p['period']//100 in(2023,2024,2025) and g['history_achieved']
    assert len(g['prior_games'])==3 and g['prior_games']==ctx['windows']['own']['game_ids']
    assert all(int(gid[:4])==g['period']//100 and int(gid[:4])*100+int(gid.split('_')[1])<g['period']for gid in g['prior_games'])
    assert set(ctx['features'])==set(TEAM_ADDED)
    prior_native={sid for gid in g['prior_games']for gg,t,sid in source_actor if gg==gid and t==g['team']}
    assert prior_native=={c['source_player_id']for c in g['candidate_native_labels']}
    z={(c['source_player_id'],c['channel']):c for c in p['missing_candidate_proofs']}
    cells=[]
    for c in g['candidate_native_labels']:
        sid=c['source_player_id'];label=c['counts']['targets'];reason='KNOWN_CURRENT_SOURCE_ROW'
        if label is None:
            q=z[sid,'targets'];assert q['zero'] and q['canonical_prior_attachment']==c['canonical_prior_attachment']
            label=0.;reason=q['reason'];zero_labels[str(g['period']//100)]+=1
        else:assert c['canonical_same_native_label_qualified']
        assert c['canonical_prior_attachment'] and not c['canonical_prior_attachment_conflict']
        fields=candidate_features(g,sid,ctx)
        cells.append(dict(kind='candidate',source_player_id=sid,player_master_id=c['canonical_prior_attachment'],label=label,
                          features={k:fields[k]for k in columns},label_basis=reason,prior_roles=c['prior_roles'],
                          prior_source_ids=c['prior_source_ids'],target_source_id=c['target_source_id']))
    fields={**ctx['features'],**dict.fromkeys(PLAYER_ADDED),'is_known_outside_rest':1,'prior_candidate_count':g['candidate_count'],'is_source_pass_minus_target_remainder':0}
    cells.append(dict(kind='outside_target_rest',source_player_id=None,player_master_id=None,label=ch['numeric_disjoint_outside_rest'],
                      features={k:fields[k]for k in columns},label_basis='DISJOINT_KNOWN_SOURCE_OUTSIDE_CANDIDATES',
                      outside_unresolved_observed_count=ch['known_outside_unresolved_sum']))
    P=g['channels']['pass_attempts']['source_observed_budget'];T=ch['source_observed_budget']
    assert P is not None and T is not None and 0<=T<=P
    remainder_fields={**fields,'is_known_outside_rest':0,'is_source_pass_minus_target_remainder':1}
    cells.append(dict(kind='source_pass_minus_target_remainder',source_player_id=None,player_master_id=None,label=P-T,
                      features={k:remainder_fields[k]for k in columns},label_basis='SOURCE_PASS_MINUS_SOURCE_TARGET_NOT_IDENTIFIED_THROWAWAY'))
    groups.append(dict(game_id=g['game_id'],team=g['team'],period=g['period'],prior_games=g['prior_games'],
                       prior_windows=ctx['windows'],cells=cells,target_budget_label=T,pass_budget_label=P,
                       independent_NFL_census='UNKNOWN',current_proof_metadata_not_predictors=True))
    counts[str(g['period']//100)]+=1;gate_keys.append(list(key))
assert counts=={'2023':88,'2024':102,'2025':89}
assert {tuple(k)for k in gate_keys}==admitted_keys
model.validate_groups(groups,columns)
prep=model.fit_preprocessing(groups,columns);data=model.transform_groups(groups,prep)
raw=np.asarray([[c['features'][k]if c['features'][k]is not None else np.nan for k in columns]for g in groups for c in g['cells']],dtype=float)
assert data['X'].shape==(len(raw),140) and np.isfinite(data['X']).all()
arrays=BytesIO();np.savez_compressed(arrays,raw_inputs=raw,X=data['X'],labels=data['labels'],budgets=data['budgets'],target_budgets=data['target_budgets'],
                                    offsets=np.asarray(data['offsets']),group_years=np.asarray([g['period']//100 for g in groups]))
metadata=[{**{k:v for k,v in g.items()if k!='cells'},'cells':[{k:v for k,v in c.items()if k!='features'}for c in g['cells']]}for g in groups]
metadata_ref=save(metadata,'joint_target_pass_prefit_keys');array_ref=save(arrays.getvalue(),'joint_target_pass_prefit_tensors','.npz')

# Match saved predictions only where UUID AND observed target label agree. No absent
# baseline is zero-filled, assigned to rest, or allowed to change the new cohort.
comparisons={};matched_rows={}
for experiment in('pressure_count_model_fits_20261020','workload_direct_count_fits_20261020'):
    for family in('tree','neural'):
        job=Path('research',experiment,'v1','player_'+family+'.json');receipt=json.loads(job.read_text())
        rows=load(experiment+'_'+family,receipt['prediction_ref'],8*1024*1024)
        if isinstance(rows,dict):rows=rows['rows']
        lookup={(r['game_id'],r['team'],r['player_master_id']):r for r in rows}
        assert len(lookup)==len(rows)
        stats={};matches=[]
        for year in(2023,2024,2025):
            n=0;missing=0;conflict=0;full=0
            for i,g in enumerate(groups):
                if g['period']//100!=year:continue
                complete=True
                for j,c in enumerate(g['cells'][:-2]):
                    old=lookup.get((g['game_id'],g['team'],c['player_master_id']))
                    if old is None:missing+=1;complete=False;continue
                    if old['actual']['targets']!=c['label']:conflict+=1;complete=False;continue
                    assert old['predicted']['targets']is not None
                    n+=1;matches.append(dict(group_index=i,cell_index=j,actual=c['label'],saved_prediction=old['predicted']['targets']))
                full+=int(complete)
            stats[str(year)]=dict(matched_candidate_rows=n,missing_saved_prediction_rows=missing,
                                 changed_or_unknown_saved_label_rows=conflict,all_candidate_saved_prediction_groups=full)
        name=experiment+'_'+family;comparisons[name]=stats;matched_rows[name]=matches
baseline_ref=save(matched_rows,'joint_target_pass_prefit_baseline_matches')
manifest=dict(version=model.VERSION,status='PREFIT_ONLY_PENDING_HIGH',started_at=started.isoformat(),completed_at=datetime.now(UTC).isoformat(),
              elapsed_seconds=time.monotonic()-timer,source_refs=refs,target_admission_ref=file_ref(admission_path),excluded_unknown_counts=admission['excluded_unknown_counts'],group_metadata_ref=metadata_ref,tensor_ref=array_ref,
              saved_baseline_matches_ref=baseline_ref,feature_columns=columns,transformed_columns=columns+['missing__'+k for k in columns],
              preprocessing=prep,recipe=model.RECIPE,group_counts=dict(counts),source_zero_label_cells=dict(zero_labels),
              cells=len(raw),shapes={k:list(v.shape)for k,v in data.items()if isinstance(v,np.ndarray)},
              baseline_coverage=comparisons,gate_key_sha256=hashlib.sha256(json.dumps(gate_keys,separators=(',',':')).encode()).hexdigest(),
              contract_ref=file_ref('research/cached_event_zero_proof_20261020/v1/HIGH_NEXT_MODEL_CONTRACT.json'),
              feature_helper_refs=[file_ref('backend/app/product_services/scheduled_workload_efficiency_model_inputs.py')],
              fit_count=0,activation=False,new_sources=0,raw_source_rereads=0,identity_queries=0,
              scope='SOURCE_OBSERVED target candidate+knownoutside means and source P-T remainder; fixed selected compatible historical population, not unconditional NFL roster',
              prior_only='Exactly3immediate scheduled same-season games; prior role/knownness only; current labels/proofs and current source rows NEVER predictors',
              loss='Equal TRAIN group weight: mean ALLcell rawMSE/TRAINcellstd^2 + PbudgetMSE/TRAINPstd^2 + TbudgetMSE/TRAINTstd^2;stdsfloored1;fixedL2.001weightsnotbias. Shared reviewed rush core derivatives.',
              availability='Retrospective revised captures/aliases/provider metrics; original pregame vintages unproved; 2025 previously inspected',
              comparison='Matched saved known candidate rows only; absent baseline predictions UNKNOWN, rest separate; changed cohort/features/loss confound attribution',
              target_and_pass='279retainedsourcecensusgroupsONLY;28unknownexcluded;muT=candidate+knownoutside;muP=muT+sourceP-Tmean;no per-QBallocation/fullNFLcensus' )
(R/'MANIFEST.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
print(json.dumps({k:manifest[k]for k in('group_counts','cells','shapes','elapsed_seconds','source_zero_label_cells','baseline_coverage','tensor_ref','group_metadata_ref')},indent=2))
