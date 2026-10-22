"""Single bounded fixture audit, exclusive outputs and preserved prior bytes."""
import hashlib
import json
import math
from pathlib import Path
import time

from .allocation import allocate
from .fixtures import cases

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CAP_SECONDS = 10


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    started = time.monotonic()
    # Claim the one allowed run before calculating or writing any results.
    with (HERE / 'RUN_STARTED.json').open('x') as handle:
        json.dump(dict(cap_seconds=CAP_SECONDS, automatic_retry=False), handle)
        handle.write('\n')
    baseline = json.loads((HERE / 'PRESERVATION_BASELINE.json').read_text())
    rows = []
    for name, case in cases():
        if time.monotonic() - started >= CAP_SECONDS:
            raise TimeoutError('Fixture audit cap reached')
        result = allocate(**case)
        for channel in result['accounting'].values():
            if channel['team_budget'] is not None:
                if not math.isclose(channel['assigned_known_mean'] + channel['residual_mean'],
                                    channel['team_budget'], abs_tol=1e-10):
                    raise ValueError('Opportunity budget not conserved')
        rows.append(dict(case_id=name, inputs=case, result=result))
    changed = [name for name, sha in baseline.items() if digest(ROOT / name) != sha]
    if changed:
        raise ValueError(f'Prior artifact or product service changed: {changed}')
    elapsed = time.monotonic() - started
    if elapsed >= CAP_SECONDS:
        raise TimeoutError('Preservation verification exceeded cap')
    with (HERE / 'ALLOCATIONS.jsonl').open('x') as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, allow_nan=False) + '\n')
    refs = [HERE / name for name in ('allocation.py', 'fixtures.py', 'build.py', 'RECIPE.md',
            'TIMING_DEFERRED.json', 'PRESERVATION_BASELINE.json', 'ALLOCATIONS.jsonl')]
    refs.append(ROOT / 'backend/app/tests/product/test_player_opportunity_accounting.py')
    manifest = dict(status='SYNTHETIC_ACCOUNTING_ONLY', fixture_cases=len(rows),
        elapsed_seconds=elapsed, cap_seconds=CAP_SECONDS, preservation_files=len(baseline),
        changed_preserved_files=changed, simulation_runs=0, fits=0, network_requests=0,
        activation=False, live_settings_changes=0,
        files=[dict(path=str(p.relative_to(ROOT)), sha256=digest(p)) for p in refs])
    with (HERE / 'MANIFEST.json').open('x') as handle:
        json.dump(manifest, handle, indent=2); handle.write('\n')
    print(json.dumps({k: v for k, v in manifest.items() if k != 'files'}))


if __name__ == '__main__':
    main()
