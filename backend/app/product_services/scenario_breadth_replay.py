"""Immutable public frozen-input research replay. Never writes optimizer lineups."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from uuid import UUID

from sqlalchemy import text

from .analyst_shadow import digest, validate_snapshot
from .scenario_allocation import AllocationControls, dependence_audit
from .scenario_breadth import CONTRACT, generate_pool, select_pool, signature

ROOT = Path(__file__).resolve().parents[3] / 'artifacts' / 'scenario_breadth_replays'


def implementation_hash():
    root = Path(__file__).parent
    return digest({name: (root / name).read_text() for name in ['scenario_breadth.py', 'scenario_breadth_replay.py', 'analyst_scenarios.py', 'scenario_allocation.py']})


def read_replay(replay_id, *, directory=None):
    if not re.fullmatch(r'[a-f0-9]{64}', replay_id):
        raise ValueError('Invalid research replay ID')
    path = (Path(directory) if directory else ROOT) / (replay_id + '.json')
    if not path.exists():
        raise LookupError('Research replay not found')
    result = json.loads(path.read_text())
    if result.get('replay_id') != replay_id or digest(result['input_identity']) != replay_id or digest({k:v for k,v in result.items() if k != 'artifact_sha256'}) != result.get('artifact_sha256'):
        raise ValueError('Research replay integrity mismatch')
    return result


def list_replays(*, directory=None):
    root = Path(directory) if directory else ROOT
    rows = []
    for path in sorted(root.glob('*.json'), reverse=True)[:100]:
        result = read_replay(path.stem, directory=root)
        rows.append({k:result[k] for k in ['replay_id', 'source_optimizer_run_id', 'scope', 'created_at', 'status']})
    return {'rows': rows}


def decorate(candidates, rows):
    lookup = {str(r['player_id']):r for r in rows}
    result = []
    for c in candidates:
        roster = [{**p, 'name':lookup[p['player_master_id']].get('name', lookup[p['player_master_id']].get('player_name', lookup[p['player_master_id']].get('full_name', p['player_master_id']))),
                   'position':lookup[p['player_master_id']]['position'],
                   'team':lookup[p['player_master_id']].get('player_team', lookup[p['player_master_id']].get('team')),
                   'game_id':lookup[p['player_master_id']]['game_id'],
                   'salary':float(lookup[p['player_master_id']]['salary']),
                   'projection':float(lookup[p['player_master_id']]['projection'])} for p in c['roster']]
        result.append({**c, 'roster':roster, 'baseline_mean':sum(p['projection'] for p in roster), 'salary':sum(p['salary'] for p in roster)})
    return result


def game_dependencies(candidates, rows):
    from collections import Counter
    from itertools import combinations
    lookup = {str(r['player_id']):r for r in rows}
    games, pairs = Counter(), Counter()
    for c in candidates:
        ids = sorted(p['player_master_id'] for p in c['roster'])
        games.update({lookup[pid]['game_id'] for pid in ids if lookup[pid]['position'] != 'DST'})
        pairs.update(combinations(ids, 2))
    return {'offense_game_appearance_counts':dict(games),
        'repeated_two_player_dependencies':[{'player_master_ids':list(ids), 'count':count} for ids,count in pairs.most_common() if count>1],
        'meaning':'Game presence and shared canonical pairs are failure-dependency diagnostics, not calibrated correlation or arbitrary caps.'}


def build_from_config(run_id, config, *, directory=None, code_hash=None):
    UUID(run_id)
    report = (config.get('strategy_runtime') or {}).get('football_analyst') or {}
    if report.get('portfolio_mode') != 'SCENARIO_FIRST':
        raise ValueError('Replay requires a saved SCENARIO_FIRST report')
    snapshot = report.get('input_snapshot') or {}
    validate_snapshot(snapshot)
    if snapshot['scope']['format'] != 'CLASSIC':
        raise ValueError('This research replay supports Classic only')
    plan = deepcopy(report.get('scenario_allocation_plan') or {})
    if not plan.get('ideas') or not report.get('scenario_definitions'):
        raise ValueError('Saved supported ideas/worlds are unavailable; no historical reconstruction')
    requested = int(config.get('num_lineups', 0))
    identity = dict(contract=CONTRACT, source_optimizer_run_id=run_id, source_config_sha256=digest(config),
        original_snapshot_sha256=snapshot['sha256'], original_packet_sha256=report.get('packet_sha256'),
        settings_sha256=digest({k:v for k,v in config.items() if k != 'strategy_runtime'}), implementation_sha256=code_hash or implementation_hash(), seed=7)
    replay_id = digest(identity)
    root = Path(directory) if directory else ROOT
    if (root / (replay_id + '.json')).exists():
        return read_replay(replay_id, directory=root)
    rows = deepcopy(snapshot['players'])
    for row in rows:
        row['player_id'] = row['player_master_id']
    # Complete original user settings preserved; frozen legal model is unchanged.
    params = {**config, 'data_cutoff_at':snapshot['decision_at']}
    controls = AllocationControls.model_validate(plan['controls'])
    worlds = [w for w in report['scenario_definitions'] if w['scenario_id'] in {i['idea_id'] for i in plan['ideas']}]
    if len(worlds) != len(plan['ideas']):
        raise ValueError('Saved idea/world lineage is incomplete')
    pool, generation = generate_pool(snapshot, rows, plan['ideas'], worlds, params, requested, controls)
    original = deepcopy(report['candidates'])
    # Include original selected candidates as explicit controls, never relabel them as newly generated.
    for index,c in enumerate(original):
        c['candidate_id'] = 'original_saved_control:' + str(index+1)
        c['origin'] = 'original_saved_selected_roster_not_reconstructed_generation'
    combined = pool + original
    selected, selection = select_pool(deepcopy(combined), worlds, rows, params, requested, plan)
    baseline, baseline_selection = select_pool(deepcopy(combined), worlds, rows, params, requested, plan, objective='BASELINE_MEAN')
    result = dict(replay_id=replay_id, input_identity=identity, contract_id=CONTRACT,
        source_optimizer_run_id=run_id, scope=snapshot['scope'], created_at=datetime.now(timezone.utc).isoformat(),
        status='completed' if len(selected)==requested else 'underfilled', research_only=True, entry_clearance=False,
        production_defaults_changed=False, projection_mutation=False, outcomes_used=False,
        historical_outcomes_previously_inspected=True, source_data_cutoff=snapshot['decision_at'],
        chronology_status='Frozen stored inputs, not independently verified original source/code chronology; retrospective research only',
        requested=requested, settings_sha256=identity['settings_sha256'], generation=generation,
        candidate_variant_count=len(combined), distinct_canonical_roster_count=len({signature(c) for c in combined}),
        original_selected=decorate(original,rows), candidates=decorate(combined,rows),
        selected=decorate(selected,rows), selection=selection,
        highest_baseline_mean_control=decorate(baseline,rows), baseline_selection=baseline_selection,
        original_dependencies={**dependence_audit(original,rows,requested),**game_dependencies(original,rows)},
        selected_dependencies={**dependence_audit(selected,rows,requested),**game_dependencies(selected,rows)},
        ideas=plan['ideas'], worlds=[{k:v for k,v in w.items() if k!='moments'} for w in worlds],
        assumptions=['Existing conserved opportunity sensitivity and .7 elasticity, not fitted game simulation',
          'Candidate objective uses summed marginal P90 spreads, not actual joint lineup upside',
          'Existing ordinal source/capability priorities are not event probabilities',
          'No actual points, ranks, winnings or winner player identities used by generation or selection',
          'Generation and selection both changed: not a selector-only controlled experiment',
          'Original saved generator and lineups remain unchanged; experimental policy not live default'])
    result['artifact_sha256'] = digest(result)
    root.mkdir(parents=True, exist_ok=True)
    path = root / (replay_id + '.json')
    try:
        with path.open('x') as handle:
            handle.write(json.dumps(result, indent=2, allow_nan=False)+'\n')
    except FileExistsError:
        return read_replay(replay_id, directory=root)
    return result


def build_replay(session, run_id):
    UUID(run_id)
    row = session.execute(text('SELECT constraint_config_json FROM target.optimizer_run WHERE optimizer_run_id = :id'), {'id':run_id}).mappings().first()
    if not row:
        raise LookupError('Saved optimizer run not found')
    return build_from_config(run_id, row['constraint_config_json'])
