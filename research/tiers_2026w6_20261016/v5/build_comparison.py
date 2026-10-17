"""Read-only, canonical Tiers comparison. Does not import data or run an optimizer."""
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from backend.app.product_services.preliminary_optimizer import load_snapshot

ROOT = Path(__file__).resolve().parent
POOL = ROOT.parent / 'v4/pool.json'
KEY = '6d662321caa3a513bb7720d68f836aca4cad96581314757c5e35d7d794ae207a'
snapshot = load_snapshot(KEY)
pool = json.loads(POOL.read_text())
assert snapshot['scope']['season'] == pool['season'] == 2026
assert snapshot['scope']['week'] == pool['week'] == 6
assert snapshot['scope']['slate'] == 'SUNDAY_MAIN'
fresh = {r['player_id']: r for r in snapshot['pool']}
players = {r['name']: r for r in pool['players']}
assert len(players) == 40
assert len({r['player_master_id'] for r in players.values()}) == 40
assert all(r['player_master_id'] in fresh for r in players.values())

base = ['Josh Allen', 'Derrick Henry', 'Puka Nacua', 'Kyren Williams', 'Kirk Cousins', 'Ashton Jeanty']
def changed(names, **swaps):
    return [swaps.get(f'T{i}', n) for i, n in enumerate(names, 1)]

mean_best = changed(base, T2='Kenneth Walker III', T5='Aaron Rodgers', T6='Davante Adams')
preferred = changed(mean_best, T6='Ashton Jeanty')
specs = [
    ('original_roster_fresh_means', base),
    ('fresh_exact_highest_mean', mean_best),
    ('analyst_balanced_path', preferred),
    ('retain_vegas_trio', changed(preferred, T5='Kirk Cousins')),
    ('young_four_game_alternative', changed(preferred, T5='Bryce Young')),
    ('irving_opponent_response', changed(preferred, T6='Bucky Irving')),
    ('wilson_rams_bringback', changed(preferred, T6='Michael Wilson')),
    ('stafford_rams_passing', changed(preferred, T1='Matthew Stafford')),
    ('mahomes_different_game', changed(preferred, T1='Patrick Mahomes')),
    ('maye_different_game', changed(preferred, T1='Drake Maye')),
    ('henry_workload_alternative', changed(preferred, T2='Derrick Henry')),
]
rows = []
for label, names in specs:
    roster = []
    for i, name in enumerate(names, 1):
        p = players[name]
        f = fresh[p['player_master_id']]
        assert p['tier'] == f'T{i}'
        assert not p['questionable'] and not p['reason_codes']
        assert f['availability_status'] not in {'OUT', 'IR', 'DOUBTFUL'}
        assert f['projection'] is not None
        assert p['source_player_id'].isascii() and p['source_player_id'].isdigit()
        roster.append({k: p[k] for k in ['tier', 'name', 'player_master_id', 'source_player_id', 'team', 'game_id']} |
                      {'old_mean': p['projection'], 'mean': f['projection'], 'salary': None})
    assert len({p['player_master_id'] for p in roster}) == 6
    games = sorted({p['game_id'] for p in roster})
    assert len(games) >= 2
    rows.append(dict(label=label, roster=roster, games=games, mean=sum(p['mean'] for p in roster),
                     old_mean=sum(p['old_mean'] for p in roster), valid=True))
best = next(r['mean'] for r in rows if r['label'] == 'fresh_exact_highest_mean')
for r in rows:
    r['gap_to_fresh_highest_mean'] = r['mean'] - best
eligible = [p for p in players.values() if not p['questionable'] and not p['reason_codes'] and fresh[p['player_master_id']]['projection'] is not None]
assert abs(best - sum(max(fresh[p['player_master_id']]['projection'] for p in eligible if p['tier'] == tier) for tier in pool['tier_labels'])) < 1e-9
result = dict(contract='tiers_full_roster_review_v1', created_at=datetime.now(UTC).isoformat(),
              application_status='research_only', entry_ready=False, optimizer_executed=False,
              original_report_sha256='1bc9d189a2e88e0cec4748dd3d5883218723fcbbf7ea23b1b32eea90fe9394e1',
              original_pool_sha256=pool['sha256'], snapshot_sha256=KEY,
              projection_run_id=snapshot['projection_run_id'], data_cutoff_at=snapshot['data_cutoff_at'],
              source_sha256=snapshot['source_sha256'], projection_lineage_sha256=snapshot['projection_lineage_sha256'],
              native_draft_group_id=pool['native_draft_group_id'], rules=pool['rules'],
              unchanged_preferences={'exclude_questionable': True, 'no_added_team_caps': True},
              uncertainty='No calibrated joint outcomes; means unchanged; scenarios conditional, unweighted.', rosters=rows)
(ROOT / 'comparison.json').write_text(json.dumps(result, indent=2) + '\n')
verification = dict(checked_at=datetime.now(UTC).isoformat(), all40_canonical_coverage=True,
                    snapshot_hash_contract_verified=True, all11_rosters_native_tier_legal=True,
                    minimum_games_satisfied=True, canonical_distinct=True,
                    questionable_and_known_unavailable_absent=True, mean_objective_exact=True,
                    baseline_report_file_sha256=hashlib.sha256((ROOT.parent/'v4/report.json').read_bytes()).hexdigest(),
                    comparison_sha256=hashlib.sha256((ROOT/'comparison.json').read_bytes()).hexdigest(),
                    live_mutations=False, new_optimizer_run=False, new_csv=False)
(ROOT / 'verification.json').write_text(json.dumps(verification, indent=2) + '\n')
for r in rows:
    print(r['label'], round(r['mean'], 6), round(r['gap_to_fresh_highest_mean'], 6), len(r['games']))
