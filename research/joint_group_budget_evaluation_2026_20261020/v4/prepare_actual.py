"""Build exact approved reconstructed evaluation arrays; never fit or predict."""
from pathlib import Path
from datetime import datetime,UTC
from io import BytesIO
import argparse,hashlib,json,time
import numpy as np
from inputs import construct_group,transform_evaluation

R=Path(__file__).resolve().parent

def ref(path):
    p=Path(path);b=p.read_bytes();return dict(path=str(p.resolve()),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))

def read(r,cap):
    if r['bytes']>cap:raise ValueError('Bounded immutable cache cap')
    b=Path(r['path']).read_bytes()
    if len(b)!=r['bytes']or hashlib.sha256(b).hexdigest()!=r['sha256']:raise ValueError('Immutable source binding mismatch')
    return json.loads(b)

def save(b,kind,suffix):
    sha=hashlib.sha256(b).hexdigest();p=Path('artifacts',kind,sha+suffix);p.parent.mkdir(exist_ok=True)
    if p.exists():assert p.read_bytes()==b
    else:
        with p.open('xb')as f:f.write(b)
        p.chmod(0o444)
    return dict(path=str(p.resolve()),sha256=sha,bytes=len(b))

def main():
    cli=argparse.ArgumentParser();cli.add_argument('--source-gate',required=True);args=cli.parse_args()
    if(R/'MANIFEST.json').exists():raise ValueError('Preserve existing preparation; no automatic repeat')
    gate=json.loads(Path(args.source_gate).read_text())
    if not gate['status'].startswith('FINAL_PASS'):raise ValueError('Final source guard review required')
    started=datetime.now(UTC);timer=time.monotonic()
    A=Path('research/verification_2026_20261020/v1');admission=json.loads((A/'HIGH_ADMISSION.json').read_text());receipt=json.loads((A/'ACTUAL_RECEIPT.json').read_text())
    # Completed original measurement is immutable; current guard provenance is separate.
    proof=read(receipt['full_ref'],20*1024*1024)
    for pin in json.loads((A/'EVIDENCE.json').read_text())['pins']:
        p=ref(pin['path']);assert p==pin
    old=json.loads(Path('research/joint_candidate_label_coverage_20261020/v1/ACTUAL_RECEIPT.json').read_text())
    source=read(old['source_refs']['source_component'],80*1024*1024);contexts=read(old['source_refs']['reviewed_prior_contexts'],6*1024*1024)
    actors={(r['game_id'],r['team'],r['source_player_id']):r for r in source['actor_rows']if r['source_player_id']is not None and r['season']==2026}
    teams={(r['game_id'],r['team']):r for r in source['team_game_rows']if r['season']==2026};ctx={(r['game_id'],r['team']):r for r in contexts['team_contexts']}
    allproof={(g['game_id'],g['team']):g for g in proof['groups']};channels={}
    arch=json.loads(Path('research/joint_group_budget_allocation_20261020/v4/MANIFEST.json').read_text())
    baseline_lookup={};baseline_refs={}
    for experiment in('pressure_count_model_fits_20261020','workload_direct_count_fits_20261020'):
        for family in('tree','neural'):
            for grain in('player','team'):
                p=Path('research',experiment,'v1',grain+'_'+family+'.json');oldfit=json.loads(p.read_text());rr=oldfit['prediction_ref'];rows=read(rr,9*1024*1024)
                if isinstance(rows,dict):rows=rows['rows']
                name=experiment+'_'+family+'_'+grain
                keys=[(r['game_id'],r['team'],r['player_master_id'])if grain=='player'else(r['game_id'],r['team'])for r in rows]
                if len(set(keys))!=len(keys):raise ValueError('Duplicate saved baseline key')
                baseline_lookup[name]=dict(zip(keys,rows));baseline_refs[name]=rr
    for channel,folder,keyfield in [('rush','joint_rush_conditional_means_20261020','provisional_completed_rush_keys'),('target','joint_target_pass_conditional_means_20261020','provisional_completed_target_pass_keys')]:
        oldmanifest=Path('research',folder,'v1/MANIFEST.json');historical=json.loads(oldmanifest.read_text());prep=historical['preprocessing'];gp=arch['channels'][channel]['group_preprocessing'];keys=admission[keyfield]
        assert len(keys)==(11 if channel=='rush'else 2)
        groups=[construct_group(allproof[tuple(k)],ctx[tuple(k)],actors,teams,historical['feature_columns'],channel=channel)for k in keys]
        d=transform_evaluation(groups,prep,gp,channel=channel)
        assert [list((g['game_id'],g['team']))for g in groups]==keys
        arrays=BytesIO();np.savez_compressed(arrays,**d)
        encoded=json.dumps(groups,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
        fitpath=Path('research/joint_conditional_mean_fits_20261020/v4',channel+'.json');fit=json.loads(fitpath.read_text())
        assert fit['status']=='completed'and fit['native_status']==1 and fit['original_gradient_inf']<=1e-5
        matches={};coverage={}
        for name,lookup in baseline_lookup.items():
            player=name.endswith('_player');head=('rush_attempts'if channel=='rush'else'targets')if player else('rush_attempts'if channel=='rush'else'pass_attempts')
            rows=[];missing=changed=0
            for gi,g in enumerate(groups):
                for ci,c in enumerate(g['cells']if player else[{}]):
                    if player and c['kind']!='candidate':continue
                    k=(g['game_id'],g['team'],c['player_master_id'])if player else(g['game_id'],g['team']);previous=lookup.get(k)
                    y=c['label']if player else g['budget_label'if channel=='rush'else'pass_budget_label']
                    if previous is None or previous['predicted'].get(head)is None:missing+=1;continue
                    if previous['actual'].get(head)!=y:changed+=1;continue
                    rows.append(dict(group_index=gi,cell_index=ci if player else None,actual=y,saved_prediction=previous['predicted'][head]))
            matches[name]=rows;coverage[name]=dict(matched_rows=len(rows),missing_saved_prediction_rows=missing,changed_or_unknown_saved_label_rows=changed)
        channels[channel]=dict(keys=keys,groups=len(groups),candidate_cells=sum(c['kind']=='candidate'for g in groups for c in g['cells']),zero_labels=int((d['labels']==0).sum()),group_ref=save(encoded,'joint_group_evaluation_2026_groups','.json'),tensor_ref=save(arrays.getvalue(),'joint_group_evaluation_2026_tensors','.npz'),shapes={k:list(v.shape)for k,v in d.items()},historical_manifest_ref=ref(oldmanifest),cell_preprocessing=prep,group_preprocessing=gp,converged_model_ref=fit['model_ref'],fit_receipt_ref=ref(fitpath),baseline_coverage=coverage,saved_baseline_matches_ref=save(json.dumps(matches,sort_keys=True,separators=(',',':')).encode(),'joint_group_evaluation_2026_baseline_matches','.json'))
    manifest=dict(version='joint_group_budget_reconstructed2026_evaluation_inputs_v4',status='ARRAY_REVIEW_REQUIRED_NO_INFERENCE',started_at=started.isoformat(),completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-timer,source_guard_gate_ref=ref(args.source_gate),source_admission_ref=ref(A/'HIGH_ADMISSION.json'),source_measurement_ref=receipt['full_ref'],source_component_ref=old['source_refs']['source_component'],prior_context_ref=old['source_refs']['reviewed_prior_contexts'],baseline_prediction_refs=baseline_refs,architecture_manifest_ref=ref('research/joint_group_budget_allocation_20261020/v4/MANIFEST.json'),all214_schedule_status_ref=ref('research/joint_group_budget_allocation_20261020/v4/2026_EVALUATION_STATUS_PLAN.json'),channels=channels,models_loaded=False,optimizer_calls=0,prediction_calls=0,train_year=2023,preprocessing_refit=False,availability='LATEST_RECONSTRUCTED_SOURCE_ONLY; original predictor and identity availability before kickoff unproved',scope='Only exact approved11rush/2target/P finalizedW4–5 sides. All96W1–3 coldstarts,W6completionunknown,W7unfinalized remain explicit. No wholeNFL/full2026 or replacement-result claim.',activation=False)
    (R/'MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps({c:{k:v[k]for k in('groups','candidate_cells','zero_labels','shapes')}for c,v in channels.items()},indent=2))

if __name__=='__main__':main()
