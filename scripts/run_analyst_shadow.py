"""Generate offline Analyst shadow candidates from a frozen packet/model pair."""
import argparse
import json
from pathlib import Path

from backend.app.product_services.analyst_shadow import generate_shadow, digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet', type=Path, required=True)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--requested-per-thesis', type=int, default=2)
    parser.add_argument('--baseline-count', type=int, default=2)
    parser.add_argument('--seed', type=int, default=7)
    parser.add_argument('--disabled', action='store_true')
    args = parser.parse_args()
    packet = json.loads(args.packet.read_text()); snapshot = json.loads(args.snapshot.read_text())
    result = generate_shadow(packet, snapshot, requested_per_thesis=args.requested_per_thesis,
                             baseline_count=args.baseline_count, seed=args.seed, enabled=not args.disabled)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'result.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    manifest = dict(contract_id='analyst_shadow_manifest_v1', packet_path=str(args.packet),
                    snapshot_path=str(args.snapshot), packet_sha256=digest(packet), snapshot_sha256=snapshot['sha256'],
                    result_sha256=digest(result), source_sha256={str(p): __import__('hashlib').sha256(p.read_bytes()).hexdigest()
                    for p in (Path(__file__), Path('backend/app/product_services/analyst_shadow.py'))})
    (args.output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    lines = ['# Analyst shadow discovery', '', '**RESEARCH_SHADOW; no final portfolio selected.**', '',
             '| Analyst thought | Generated construction | Screen / eligibility outcome |', '|---|---|---|']
    by_id = {r['candidate_id']:r for r in result['shadow']}
    for t in result['theses']:
        outcomes = ', '.join(by_id[c]['eligibility_outcome'] for c in t.get('candidate_ids', [])) or ', '.join(t['reasons'])
        lines.append('| '+str(t['analyst_thought']).replace('|','/')+' | '+str(t['construction']['type'])+'; '+str(t['achieved'])+'/'+str(t['requested'])+' | '+outcomes+' |')
    lines += ['', 'Packet errors: '+json.dumps(result['packet_errors']), '', 'Counts: '+json.dumps(result['comparison']), '',
              'Baseline objective, legal constraints, eligibility, locks, Captain shortlist and remaining exposure gates are frozen. Candidate counts are discovery budgets, not portfolio exposures. No global portfolio optimality or production recommendation is claimed.']
    names = {p['player_master_id']:p for p in snapshot['players']}
    baseline_ids = {r['candidate_id'] for r in result['baseline']}
    lines += ['', '## Candidate rosters', '', '| Candidate | Captain | FLEX / Classic roster | Salary | Mean | Baseline objective | Origin |', '|---|---|---|---:|---:|---:|---|']
    for i,r in enumerate(result['shadow'],1):
        captain = next((names[p['player_master_id']].get('name',p['player_master_id']) for p in r['roster'] if p['role']=='CPT'),'N/A')
        rest = ', '.join(names[p['player_master_id']].get('name',p['player_master_id']) for p in r['roster'] if p['role']!='CPT')
        lines.append('| '+str(i)+' | '+captain+' | '+rest+' | '+str(round(r['salary']))+' | '+str(round(r['projected_mean'],2))+' | '+str(round(r['baseline_objective'],4))+' | '+('Also baseline' if r['candidate_id'] in baseline_ids else 'New Analyst construction')+' |')
    lines += ['', 'Only the typed anchors are forced. Remaining FLEX players follow the frozen baseline objective; branch assumptions are not observed clearance or quantified forecasts.',
              'Quality screens: '+('separately evaluated as listed in result.json' if snapshot['quality_screens'] else '**Not separately evaluated. An empty screen list is not a pass of a 95% screen.**'),
              'Football coherence: an opposing DST may accompany offensive anchors when the original avoid_dst_opponents setting permits it. This is a coherence concern to inspect, not an additional Analyst exclusion.',
              'Verified game identity comes from packet schedule/canonical team linkage. A reversed source display matchup is retained as a display limitation, not treated as verified venue evidence.']
    (args.output/'REPORT.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(result['comparison'], indent=2))


if __name__ == '__main__': main()
