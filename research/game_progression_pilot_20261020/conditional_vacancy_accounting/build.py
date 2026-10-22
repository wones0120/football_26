"""Single bounded six-case accounting audit with immutable parent verification."""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time

from .accounting import account
from .cases import cases

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
CAP=10


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def parent(folder,name):
    path=HERE.parent/folder/name
    manifest_path=path.parent/'MANIFEST.json'
    manifest=json.loads(manifest_path.read_text())
    expected=next(r['sha256'] for r in manifest['files'] if r['path']==str(path.relative_to(ROOT)))
    if digest(path)!=expected:raise ValueError('Retained parent bytes differ')
    return json.loads(path.read_text()),[path,manifest_path]


def main():
    started=time.monotonic()
    with (HERE/'RUN_STARTED.json').open('x') as f:json.dump(dict(cap_seconds=CAP,automatic_retry=False),f);f.write('\n')
    workload,refs=parent('prior_workload_reference','REFERENCE.json')
    roles,role_refs=parent('player_role_evidence','EVIDENCE.json');refs+=role_refs
    records=[];summary=[]
    for case in cases(roles):
        if time.monotonic()-started>=CAP:raise TimeoutError('Conditional accounting cap exceeded')
        result=account(workload,roles,case['assumptions'])
        world=result['conditional_world']
        for team,budget in world['teams'].items():
            for channel,reconciliation in budget['reconciliation'].items():
                if (reconciliation['unallocated']<0 or not math.isclose(reconciliation['allocated_known']+reconciliation['unallocated'],budget[channel],abs_tol=1e-9)):
                    raise ValueError('Conditional team budget not conserved')
        transitions=world['availability_conditions']['conditional_allocations']
        records.append(dict(case=case,result=result))
        summary.append(dict(case_id=case['case_id'],numeric_transfers=sum(t['transferred'] is not None for t in transitions),
            missing_reference_transfers=sum(t['transferred'] is None for t in transitions),
            explicit_abstentions=len(result['abstentions']),
            WAS_reconciliation=world['teams']['WAS']['reconciliation']))
    baseline=json.loads((HERE/'PRESERVATION_BASELINE.json').read_text())
    changed=[p for p,sha in baseline.items() if digest(ROOT/p)!=sha]
    if changed:raise ValueError(f'Prior/runtime files changed: {changed}')
    elapsed=time.monotonic()-started
    if elapsed>=CAP:raise TimeoutError('Preservation verification exceeded cap')
    def save(name,value):
        with (HERE/name).open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')
    save('ACCOUNTING.json',records);save('SUMMARY.json',summary)
    refs += [HERE/n for n in ('accounting.py','cases.py','build.py','RECIPE.md','PRESERVATION_BASELINE.json','ACCOUNTING.json','SUMMARY.json')]
    refs += [ROOT/'backend/app/tests/product/test_conditional_vacancy_accounting.py',ROOT/'backend/app/product_services/opportunity_role_allocation.py']
    save('MANIFEST.json',dict(status='RETROSPECTIVE_CONDITIONAL_ACCOUNTING_ONLY',recorded_at=datetime.now(timezone.utc).isoformat(),
        cases=len(records),elapsed_seconds=elapsed,cap_seconds=CAP,preservation_files=len(baseline),changed_preserved_files=changed,
        network_requests=0,fits=0,simulations=0,activation=False,live_settings_changes=0,
        files=[dict(path=str(p.relative_to(ROOT)),sha256=digest(p)) for p in refs]))
    print(json.dumps(dict(cases=len(records),elapsed_seconds=elapsed,preserved_files=len(baseline),summary=summary)))


if __name__=='__main__':main()
