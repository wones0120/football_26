"""Run the normal application optimizer with a pinned fresh Sunday projection.

--replay verifies the saved frame and selection offline without a new source
fetch or optimizer write. The normal API request remains saved and reviewable.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import uuid

import requests

from backend.app.product_services.classic_candidate_completeness import compact_candidate, load_context
from backend.app.product_services.classic_prospective import digest_payload
from scripts.reconcile_classic_discovery_selection import (
    resolve_effective_policy, selected_caps, violations, solve, summary,
)
from scripts.rerun_saved_optimizer_for_full_candidates import DERIVED_PARAM_KEYS


def saved_report(response):
    return response['results'][0][0]['classic_small_field_report']


def replay(directory: Path):
    inputs=json.loads((directory/'preview_inputs.json').read_text())
    ctx=load_context(inputs);report=inputs['report']
    candidates=[{**compact_candidate(row['player_ids'],ctx),'rank':row['rank']} for row in report['all_candidates']]
    for fresh,old in zip(candidates,report['all_candidates']):
        assert abs(fresh['objective_score']-old['objective_score'])<1e-9
    policy=resolve_effective_policy(inputs);caps=selected_caps(inputs)
    selected=[r for r in candidates if r['rank'] in report['selected_ranks']]
    assert not violations(selected,policy,caps,ctx['elevated'])
    proven=solve(candidates,policy,caps,ctx['elevated'],incumbent=selected)
    result=summary(proven,ctx['source'],ctx['risk'])
    assert result['status']=='optimal'
    assert abs(result['selector_sum']-sum(r['objective_score'] for r in selected))<1e-8
    return {'input_sha256':digest_payload(inputs),'candidate_sha256':digest_payload(report['all_candidates']),
            'saved_roster_hashes':[r['roster_sha256'] for r in selected],
            'proven_optimal':True,'same_objective':True,
            'exact_rosters_reselected':set(result['roster_hashes'])=={r['roster_sha256'] for r in selected},
            'policy':policy.__dict__,'selector_sum':result['selector_sum'],
            'normalization':{'mean':max(p.projection+p.optimizer_context_adjustment for p in ctx['players']),
                             'p90':max(p.ceiling+p.optimizer_context_adjustment for p in ctx['players'])}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path);parser.add_argument('--control',type=Path)
    parser.add_argument('--replay',action='store_true');parser.add_argument('--verify-output',type=Path)
    args=parser.parse_args();directory=args.directory
    if args.replay:
        result=replay(directory)
        if args.verify_output:
            with args.verify_output.open('x') as f:json.dump(result,f,sort_keys=True,indent=2)
        print(json.dumps(result,indent=2));return
    if not args.control:raise ValueError('--control is required to create a preview')
    if (directory/'preview.json').exists():raise ValueError('Saved preview exists; use --replay')
    control=json.loads(args.control.read_text());fresh=json.loads((directory/'refresh_lineage.json').read_text())
    params={k:v for k,v in control['params'].items() if k not in DERIVED_PARAM_KEYS|{'decision_snapshot','projection_scenario_evidence'}}
    params['diagnostic_source_optimizer_run_id']=control['run']['optimizer_run_id']
    params['reconciliation_preview_policy_id']='current_production_205_conservative_sunday_preview_v1'
    request_path=directory/'application_request.json'
    if request_path.exists():body=json.loads(request_path.read_text())
    else:
        body={'season':2026,'week':4,'slate':'SUNDAY_MAIN','strategy':'classic_small_field_gpp',
              'contest_format':'classic','objective':'gpp','projection_run_id':fresh['projection_run_id'],
              'data_cutoff_at':fresh['data_cutoff_at'],'params':params,'optimizer_run_id':str(uuid.uuid4())}
        with request_path.open('x') as f:json.dump(body,f,indent=2,sort_keys=True)
    # This is the same endpoint used by the normal optimizer button.
    response=requests.post('http://127.0.0.1:8000/api/optimizer/run',json=body,timeout=1200)
    response.raise_for_status();payload=response.json()
    with (directory/'preview.json').open('x') as f:json.dump(payload,f,indent=2,sort_keys=True)
    if payload['status']!='completed':raise ValueError(payload['message'])
    report=saved_report(payload)
    inputs={'report':report,'params':body['params'],'run':{'optimizer_run_id':payload['job_id'],
                'projection_run_id':payload['projection_run_id'],'data_cutoff_at':payload['data_cutoff_at']}}
    with (directory/'preview_inputs.json').open('x') as f:json.dump(inputs,f,indent=2,sort_keys=True)
    persisted=requests.get('http://127.0.0.1:8000/api/optimizer/results/'+payload['job_id'],timeout=30)
    persisted.raise_for_status()
    with (directory/'application_readback.json').open('x') as f:json.dump(persisted.json(),f,indent=2,sort_keys=True)
    other=saved_report(persisted.json())
    assert report['frozen_solver_snapshot']['sha256']==other['frozen_solver_snapshot']['sha256']
    assert digest_payload(report['all_candidates'])==digest_payload(other['all_candidates'])
    assert report['selected_ranks']==other['selected_ranks']
    verified=replay(directory)
    verified.update(application_endpoint='/api/optimizer/run',readback_endpoint='/api/optimizer/results/'+payload['job_id'],
        run_id=payload['job_id'],policy_name=params['reconciliation_preview_policy_id'],
        selected_ranks=report['selected_ranks'],candidate_count=len(report['all_candidates']),
        captured_at=datetime.now(UTC).isoformat(),request_sha256=sha256(request_path.read_bytes()).hexdigest())
    with (directory/'execution_verification.json').open('x') as f:json.dump(verified,f,sort_keys=True,indent=2)
    print(json.dumps(verified,indent=2))


if __name__=='__main__':main()
