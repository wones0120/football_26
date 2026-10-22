"""Read and validate stored J8 comparisons. No optimizer, DB, or source capture."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import time
from backend.app.product_services import frozen_salary_opportunity_cost as f

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
TIMINGS = ROOT / 'research/feature_platform_implementation_20261019/v1/PACKAGE_TIMINGS.jsonl'


def clock():
    return datetime.now(timezone.utc).isoformat()


def event(stage, evidence):
    row = dict(package='frozen_salary_opportunity_cost_20261020/v1', agent='B', stage=stage, timestamp=clock(), evidence=evidence)
    fd = os.open(TIMINGS, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, (json.dumps(row, sort_keys=True) + '\n').encode())
    finally:
        os.close(fd)


def read(path):
    raw = path.read_bytes()
    return json.loads(raw), dict(path=str(path.relative_to(ROOT)), sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))


def write_new(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    with path.open('xb') as handle:
        handle.write(raw)
    return dict(path=str(path.relative_to(ROOT)), sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))


def main():
    started = clock(); tick = time.monotonic()
    event('source_start', 'frozen J8 manifest/packet/report/Showdown snapshot only; no solver/DB')
    base = ROOT / 'research/defense_kicker_analysts_20261014/v2'
    manifest, manifest_ref = read(base / 'manifest.json')
    packet, packet_ref = read(base / 'packet.json')
    report, report_ref = read(base / 'report.json')
    snapshot_path = 'research/analyst_shadow_lineups_20261013/real_capture_v4/snapshot.json'
    snapshot, snapshot_ref = read(ROOT / snapshot_path)
    assert manifest['validation_errors'] == [] and manifest['live_mutations'] is False
    assert f.digest(packet) == manifest['packet_sha256'] == report['packet_sha256']
    assert snapshot_ref['sha256'] == manifest['files'][snapshot_path]
    assert report['entry_ready'] is False and report['live_mutations'] is False
    assert f._time(report['generated_at']) >= f._time(snapshot['decision_at'])
    comparisons = report['paired_comparisons']
    assert len(comparisons) == 8
    result = [f.validate_comparison(snapshot, c) for c in comparisons]
    keys = [(r['captain_id'], r['specialist_id']) for r in result]
    assert len(set(keys)) == 8
    captains = {c for c, _ in keys}; specialists = {s for _, s in keys}
    assert len(captains) == 2 and len(specialists) == 4 and set(keys) == {(c,s) for c in captains for s in specialists}
    player_evidence = [dict(player_master_id=p['player_master_id'], source_player_id=p.get('player_id'), identity_resolved=p.get('identity_resolved'), salary=p['salary'], projection=p['projection'], evidence={k:v for k,v in p.items() if any(s in k for s in ('source','observed','cutoff','run_id','model_version','created'))}) for p in snapshot['players']]
    artifact = dict(version=f.VERSION, feature_id='G24-M07', comparisons=result, frozen_player_evidence=player_evidence, source_refs=dict(manifest=manifest_ref, packet=packet_ref, report=report_ref, snapshot=snapshot_ref), source_comparison_generated_at=report['generated_at'], source_clocks=report['source_clocks'], scoring_definition='frozen_projection_sum_cpt_1p5_v1', objective_definition='exact captured linear objective coefficients; separately retained from projection sum', limits=['Eight retrospective frozen Showdown alternatives; not broad slate coverage.', 'Recorded Optimal solver status retained; arithmetic feasibility is independently checked, optimality is not independently proved.', 'No new forecast, optimizer execution, lineup save, or activation.', 'Original model-source availability remains as frozen; later analyst comparison is not a contemporaneous replay at projection cutoff.'])
    ref = write_new(ROOT / 'artifacts/frozen_salary_opportunity_cost' / (f.digest(artifact) + '.json'), artifact)
    ended = clock()
    receipt = dict(status='awaiting_High_review', version=f.VERSION, feature_ids=['G24-M07'], source_start=started, source_end=ended, elapsed_seconds=time.monotonic()-tick, source_refs=artifact['source_refs'], full_ref=ref, counts=dict(comparisons=8, complete_rosters=16, captains=2, specialists=4, distinct_frozen_players=len(snapshot['players']), constraints_per_roster=len(snapshot['model']['constraints'])), new_solver_executions=0, DB_reads=0, DB_writes=0, source_captures=0, model_runs=0)
    write_new(OUT / 'actual_receipt.json', receipt)
    event('source_end', ref['path'])
    print(json.dumps(receipt, sort_keys=True))


if __name__ == '__main__':
    (ROOT / 'artifacts/frozen_salary_opportunity_cost').mkdir(parents=True, exist_ok=True)
    try:
        main()
    except Exception as exc:
        event('source_failed', type(exc).__name__ + ': ' + str(exc))
        raise
