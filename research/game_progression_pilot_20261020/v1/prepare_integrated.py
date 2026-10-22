"""One bounded, SHA-bound cached transformation; never runs a simulation."""
from pathlib import Path
from datetime import datetime, UTC
from collections import Counter
import gzip, hashlib, json, math, signal, time
from backend.app.product_services.game_progression_source_adapter import adapt_library, prior_contexts
from backend.app.product_services.game_progression_policy import compile_policy
from backend.app.product_services.market_snapshots import canonical_team

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]

def ref(path):
    path = Path(path); raw = path.read_bytes()
    return dict(path=str(path.resolve()), sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))

def load(reference):
    raw = Path(reference['path']).read_bytes()
    if len(raw) != reference['bytes'] or hashlib.sha256(raw).hexdigest() != reference['sha256']:
        raise ValueError('Immutable input binding differs')
    decoded = gzip.decompress(raw) if reference.get('encoding') == 'gzip_json_v1' else raw
    if len(decoded) != reference.get('uncompressed_bytes', len(decoded)):
        raise ValueError('Uncompressed byte binding differs')
    return json.loads(decoded)

def target_context(row):
    """Same exact-three formula as TRAIN, retaining explicit coldstart missingness."""
    out = dict(game_id=row['game_id'], team=row['team'], season=2026)
    for axis in ('own', 'opponent'):
        window = row['windows'][axis]; periods = window['periods']
        if any(p // 100 != 2026 or p >= row['period'] for p in periods):
            raise ValueError('Target context leaks target/year')
        if len(set(window['game_ids'])) != len(window['game_ids']):
            raise ValueError('Duplicate scheduled prior game')
        p = row['features']['weekly3_' + axis + '_pass_attempts_mean']
        r = row['features']['weekly3_' + axis + '_rush_attempts_mean']
        known = len(periods) == len(window['game_ids']) == 3 and all(type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in (p, r))
        out[axis + '_pass_share'] = p / (p + r) if known and p + r > 0 else None
    return out

def publish(value, name):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    compressed = gzip.compress(raw, mtime=0); digest = hashlib.sha256(compressed).hexdigest()
    folder = ROOT / 'artifacts' / 'game_progression_integrated'; folder.mkdir(parents=True, exist_ok=True)
    path = folder / (digest + '.json.gz')
    if path.exists() and path.read_bytes() != compressed: raise ValueError('Artifact collision')
    if not path.exists(): path.write_bytes(compressed)
    return dict(**ref(path), encoding='gzip_json_v1', uncompressed_bytes=len(raw), kind=name)

def main():
    target = OUT / 'INTEGRATED_MANIFEST.json'
    if target.exists(): raise ValueError('No automatic overwrite/retry of integrated measurement')
    started = time.monotonic(); stamp = datetime.now(UTC).isoformat()
    def cap(*_): raise TimeoutError('60 second cached preparation cap')
    signal.signal(signal.SIGALRM, cap); signal.setitimer(signal.ITIMER_REAL, 60)
    receipt_path = ROOT / 'research/game_state_reconstruction_20261020/v1/CACHED_RECOMPOSE_RECEIPT.json'
    receipt = json.loads(receipt_path.read_text()); outputs = {o['season']: o for o in receipt['outputs']}
    source = outputs[2023]
    context_receipt = json.loads((ROOT / 'research/joint_candidate_label_coverage_20261020/v1/ACTUAL_RECEIPT.json').read_text())
    context_ref = context_receipt['source_refs']['reviewed_prior_contexts']
    context_data = load(context_ref)['team_contexts']; train_context = prior_contexts(context_data)
    index = load(source['reconstruction_ref']); blocks = load(source['blocks_ref']); openings = load(source['openings_ref'])
    adapted = adapt_library(blocks, openings['rows'], train_context, train_quarantine_rows=index['quarantine'])
    policy = compile_policy(adapted['blocks'], train_context, unscopable_threats=adapted['unscopable_threats'])
    policy_ref = publish(policy, 'TRAIN_POLICY'); openings_ref = publish(adapted['openings'], 'TRAIN_OPENINGS')
    normalization_ref = publish({k:v for k,v in adapted.items() if k not in ('blocks','openings','contexts')}, 'NORMALIZATION_LEDGER')
    selected = json.loads((OUT / 'SMOKE_GAME_SELECTION.json').read_text())
    coverage = json.loads((OUT / 'SCENARIO_COVERAGE_PLAN.json').read_text())
    assert len(coverage['rows']) == 214 and len(selected['selected']) == 5
    context_lookup = {(c['game_id'],c['team']): c for c in context_data if c['period'] // 100 == 2026}
    # Target openings are evidence-status only; never a rollout input.
    target_openings = load(outputs[2026]['openings_ref'])['rows']; opening_status = {}
    for o in target_openings: opening_status.setdefault(o['game_id'], []).append(dict(half=o['source_half'],certified=o['certified'],barriers=o['barriers']))
    games = []; statuses = []
    for selected_game in selected['selected']:
        gid = selected_game['game_id']; pieces = gid.split('_'); sides = [canonical_team(pieces[3]), canonical_team(pieces[2])]
        contexts = [target_context(context_lookup[(gid, team)]) for team in sides]
        games.append(dict(game_id=gid, sides=sides, context_by_side=contexts))
        statuses.append(dict(**selected_game, source_present=gid in opening_status, opening_evidence=opening_status.get(gid, []), regulation_truth='UNKNOWN_NOT_ADMITTED', generation_uses_target_observed_state=False))
    games_ref = publish(games, 'FIXED_PREGAME_INPUTS')
    result = dict(version='integrated_regulation_progression_v1', started_at=stamp, completed_at=datetime.now(UTC).isoformat(), elapsed_seconds=time.monotonic()-started,
        source_receipt_ref=ref(receipt_path), input_refs=dict(TRAIN_index=source['reconstruction_ref'],TRAIN_blocks=source['blocks_ref'],TRAIN_openings=source['openings_ref'],target_opening_status_only=outputs[2026]['openings_ref'],prior_contexts=context_ref),
        policy_ref=policy_ref,openings_ref=openings_ref,normalization_ref=normalization_ref,games_ref=games_ref,
        selection_ref=ref(OUT/'SMOKE_GAME_SELECTION.json'),coverage_ref=ref(OUT/'SCENARIO_COVERAGE_PLAN.json'),selected_game_statuses=statuses,
        support=dict(TRAIN_openings=len(adapted['openings']),certified_openings=sum(o['certified'] for o in adapted['openings']),normalized_blocks=len(adapted['blocks']),policy_physical_blocks=len(policy['blocks']),certified_policy_blocks=sum(b['certified'] for b in policy['blocks']),potential_unscopable_threats=len(policy['unscopable_threats']),deterministic_exclusions=len(adapted['deterministic_exclusion_ledger']),normalization_status_counts=dict(Counter(c['status'] for c in adapted['normalization_coverage']))),
        scope=dict(schedule_rows=214,planned_paths=320,paths_per_arm_game=32,seed=17,whole_job_seconds=120,smoke_only=True,regulation_truth='UNKNOWN_NOT_ADMITTED',canonical_player_forecasts=False,replacement_result_cases=0,availability='LATEST_RECONSTRUCTED_NOT_ORIGINAL_PREGAME',unsupported_mass='RETAINED_NOT_RENORMALIZED'),
        implementation_refs=[ref(ROOT/p) for p in ('backend/app/product_services/game_progression_runtime.py','backend/app/product_services/game_progression_policy.py','backend/app/product_services/game_progression_source_adapter.py')],
        runner_ref=ref(__file__),fits=0,simulated_paths=0,activation=False)
    signal.setitimer(signal.ITIMER_REAL,0)
    target.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(status='INTEGRATED_PREPARED_NOT_RUN',support=result['support'],selected_game_statuses=statuses,elapsed_seconds=result['elapsed_seconds'])))

if __name__ == '__main__': main()
