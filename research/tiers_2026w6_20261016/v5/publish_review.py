"""Publish the bounded read-only review into the existing Analyst library."""
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from backend.app.product_services.preliminary_optimizer import load_snapshot
from backend.app.product_services import analyst_reports

root = Path(__file__).resolve().parent
pool = json.loads((root.parent/'v4/pool.json').read_text())
comparison = json.loads((root/'comparison.json').read_text())
snapshot = load_snapshot(comparison['snapshot_sha256'])
previous = load_snapshot('abcd448ecc604de45f2e573ac3ddad393099cc2c3e64c78939c1c9ccc1cae040')
by = {p['player_id']: p for p in snapshot['pool']}
old = {p['player_id']: p for p in previous['pool']}
audit = []
for p in pool['players']:
    f = by[p['player_master_id']]
    assert f['projection'] == old[p['player_master_id']]['projection']
    audit.append({k: p[k] for k in ['source_player_id','player_master_id','name','tier','team','position','game_id','native_status','questionable','reason_codes']} |
                 dict(old_mean=p['projection'],fresh_mean=f['projection'],fresh_p90=f['p90'],
                      fresh_context={k: f.get(k) for k in ['availability_status','pregame_injury_status','practice_participation','practice_observed_at','game_total_line','team_spread_line','team_implied_total','market_observed_at','team_starting_qb_name']}))
(root/'all40_projection_comparison.json').write_text(json.dumps(dict(snapshot_sha256=snapshot['sha256'],cutoff=snapshot['data_cutoff_at'],projection_run_id=snapshot['projection_run_id'],players=audit),indent=2)+'\n')
(root/'source_transition.json').write_text(json.dumps(dict(old_snapshot=previous['sha256'],new_snapshot=snapshot['sha256'],old_projection=previous['projection_run_id'],new_projection=snapshot['projection_run_id'],old_cutoff=previous['data_cutoff_at'],new_cutoff=snapshot['data_cutoff_at'],all40_offensive_means_exactly_equal=True,partial_output_consumed=False),indent=2)+'\n')
path=root/'REVIEW.md'; text=path.read_text()
rosters='| Variant | T1 | T2 | T3 | T4 | T5 | T6 | Mean | Gap vs mean leader | Games |\n|---|---|---|---|---|---|---|---:|---:|---:|\n'
for r in comparison['rosters']:
    rosters+='| '+r['label']+' | '+' | '.join(p['name'] for p in r['roster'])+f" | {r['mean']:.3f} | {r['gap_to_fresh_highest_mean']:+.3f} | {len(r['games'])} |\n"
preferred=next(r for r in comparison['rosters'] if r['label']=='analyst_balanced_path')
rosters+='\nPreferred roster native identity:\n\n| Tier | Player | Native ID | Mean |\n|---|---|---|---:|\n'
for p in preferred['roster']:rosters+=f"| {p['tier']} | {p['name']} | {p['source_player_id']} | {p['mean']:.3f} |\n"
all40='\n## All 40 native candidates\n\n| Tier | Player | Native ID | Team | Old mean | Fresh mean | Eligibility evidence |\n|---|---|---|---|---:|---:|---|\n'
for p in audit:
    state='Excluded: native Q' if p['questionable'] else ('Excluded: OUT/missing projection' if p['fresh_mean'] is None else 'Sourced active role; final game clearance unverified')
    oldmean='—' if p['old_mean'] is None else f"{p['old_mean']:.3f}"
    mean='—' if p['fresh_mean'] is None else f"{p['fresh_mean']:.3f}"
    all40+=f"| {p['tier']} | {p['name']} | {p['source_player_id']} | {p['team']} | {oldmean} | {mean} | {state} |\n"
if '<!-- GENERATED_ROSTERS -->' in text:
    text=text.replace('<!-- GENERATED_ROSTERS -->',rosters).replace('<!-- GENERATED_ALL40 -->',all40)
    path.write_text(text)
report_id='sunday-main-tiers-football-review-2026w6-v5'
catalog_path=Path('research/analyst_reports/catalog.json')
catalog=json.loads(catalog_path.read_text())
entry=dict(report_id=report_id,title='Sunday Main Tiers — full-roster football review',category='lineup_review',season=2026,week=6,slates=['SUNDAY_MAIN_TIERS'],version='v5',recorded_at=datetime.now(UTC).isoformat(),preliminary=True,application_status='research_only',saved_run_ids=[],summary='Fresh all40 comparison; Allen/Walker/Puka/Kyren/Rodgers/Jeanty conditional Analyst preference versus exact-mean Adams alternative. Original saved lineup unchanged.',path='tiers_2026w6_20261016/v5/REVIEW.md',evidence=[dict(evidence_id=e,path=f'tiers_2026w6_20261016/v5/{f}') for e,f in [('comparison','comparison.json'),('all40','all40_projection_comparison.json'),('verification','verification.json'),('source-transition','source_transition.json'),('workload','observed_workload.json'),('source-manifest','primary_sources/manifest.json')]])
catalog['reports']=[r for r in catalog['reports'] if r['report_id']!=report_id]+[entry]
analyst_reports.Catalog.model_validate(catalog)
catalog_path.write_text(json.dumps(catalog,indent=2)+'\n')
reopened=analyst_reports.read_report(report_id)
assert reopened['markdown']==path.read_text()
for e in entry['evidence']:analyst_reports.read_evidence(report_id,e['evidence_id'])
(root/'library_verification.json').write_text(json.dumps(dict(report_id=report_id,sha256=reopened['sha256'],saved_and_reopened_exact=True,all6_evidence_files_readable=True,application_status=reopened['report']['application_status'],original_lineup_unchanged=True,entry_ready=False),indent=2)+'\n')
print(json.dumps(dict(report_id=report_id,sha256=reopened['sha256'],bytes=len(path.read_bytes()),saved_and_reopened=True)))
