"""One bounded explicit fixture audit, no sampling or operational consumers."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import time

from .assignment import assign
from .fixtures import cases

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
CAP=10


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    started=time.monotonic()
    with (HERE/'RUN_STARTED.json').open('x') as f:json.dump(dict(cap_seconds=CAP,automatic_retry=False),f);f.write('\n')
    records=[];summary=[]
    for case in cases():
        if time.monotonic()-started>=CAP:raise TimeoutError('Shared-event fixture cap exceeded')
        result=assign(case['events'],case['roster'],evidence_kind=case['evidence_kind'])
        seen=set()
        for event in result['events']:
            for credit in event['credits']:
                key=(event['game_id'],event['event_id'],credit['channel'])
                if key in seen:raise ValueError('Duplicate shared event-channel credit')
                seen.add(key)
        for team in result['teams']:
            for channel,c in team['channels'].items():
                assigned=sum(p['assigned_counts_lower_bound'][channel] for p in result['players'] if p['team']==team['team'])
                if assigned!=c['assigned_count'] or assigned+c['residual_count']!=c['known_eligible_count']:
                    raise ValueError('Shared event opportunity accounting conflict')
        records.append(dict(case=case,result=result))
        summary.append(dict(case_id=case['case_id'],events=len(result['events']),
            residual_assignments=len(result['unresolved_assignments']),teams=result['teams']))
    baseline=json.loads((HERE/'PRESERVATION_BASELINE.json').read_text())
    changed=[p for p,sha in baseline.items() if digest(ROOT/p)!=sha]
    if changed:raise ValueError(f'Preserved artifact/service changed: {changed}')
    elapsed=time.monotonic()-started
    if elapsed>=CAP:raise TimeoutError('Preservation audit cap exceeded')
    def save(name,value):
        with (HERE/name).open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')
    save('ASSIGNMENTS.json',records);save('SUMMARY.json',summary)
    refs=[HERE/n for n in ('assignment.py','fixtures.py','build.py','RECIPE.md','PRESERVATION_BASELINE.json','ASSIGNMENTS.json','SUMMARY.json')]
    refs += [ROOT/'backend/app/tests/product/test_shared_event_assignment.py',ROOT/'backend/app/product_services/opportunity_events.py']
    save('MANIFEST.json',dict(status='SYNTHETIC_SHARED_EVENT_ACCOUNTING_ONLY',recorded_at=datetime.now(timezone.utc).isoformat(),
        cases=len(records),fixture_event_records=sum(len(r['result']['events']) for r in records),
        elapsed_seconds=elapsed,cap_seconds=CAP,preservation_files=len(baseline),changed_preserved_files=changed,
        probability_draws=0,network_requests=0,fits=0,simulations=0,activation=False,live_settings_changes=0,
        files=[dict(path=str(p.relative_to(ROOT)),sha256=digest(p)) for p in refs]))
    print(json.dumps(dict(cases=len(records),elapsed_seconds=elapsed,preserved_files=len(baseline),summary=summary)))


if __name__=='__main__':main()
