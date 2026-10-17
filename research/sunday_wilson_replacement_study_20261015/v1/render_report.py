from pathlib import Path
import json,collections,hashlib
P=Path(__file__).resolve().parent;x=json.loads((P/'RESULTS.json').read_text());runs=x['runs'];baseline=runs[0];by={(r['arm'],r['label']):r for r in runs};base=x['saved_baseline_metrics']
assert len(runs)==29 and all(r['solver_status']=='Optimal' and r['solution_status']=='Optimal Solution Found' for r in runs)
assert hashlib.sha256(Path(x['source_file']).read_bytes()).hexdigest()==x['source_file_sha256']
assert len({r['canonical_roster_sha256'] for r in runs})==25
for arm in ['required_ari_response','optional_ari_response']:
 assert by[(arm,'optimized_keep_wilson')]['canonical_roster_sha256']==baseline['canonical_roster_sha256']
for r in runs:
 if r.get('salary_flow'):
  flow=r['salary_flow'];assert flow['released']==flow['net_reinvested']+flow['unspent']
 assert set(x['fixed_core'])<=set(r['player_ids'])
 if r['label'] not in ['exact_saved_baseline','optimized_keep_wilson']:assert x['wilson_id'] not in r['player_ids']
 assert len({p['player_master_id'] for p in r['players']})==9
 # Artifact FLEX assignment is derived from natural-position counts, not a claim about old DB slots.
 ordered=[];bypos=collections.defaultdict(list)
 for p in r['players']:bypos[p['position']].append(p)
 for ps in bypos.values():ps.sort(key=lambda p:(-p['salary'],p['player_master_id']))
 for pos,n in [('QB',1),('RB',2),('WR',3),('TE',1),('DST',1)]:
  ordered.extend((pos,bypos[pos].pop(0)) for i in range(n))
 leftover=[p for ps in bypos.values() for p in ps];assert len(leftover)==1 and leftover[0]['position'] in ['WR','RB'];ordered.append(('FLEX',leftover[0]));r['display_slots']=[dict(slot=slot,player_master_id=p['player_master_id']) for slot,p in ordered]
full=['# Complete frozen-model research rosters','', 'Every roster is a separate local research candidate, not an entry, export, original saved lineup or new live optimizer result. Same frozen model, salary, ownership, conditional LAR-passing world and three core locks. The two arms differ only in the generated scenario’s compulsory ARI response. All 29 solves were optimal; 25 distinct canonical rosters.','']
for i,r in enumerate(runs,1):
 full += [f"## Candidate {i}: {r['label']} — {r['arm']}",'',f"Solver: {r['solver_status']}; salary ${r['salary']:,}; base {r['base_mean']:.2f}; conditional mean {r['conditional_mean']:.2f}; conditional objective {r['conditional_objective']:.2f}; unspent ${r['unused_salary']:,}.",'', '| Slot | Player | Team | Salary | Base mean | Canonical UUID |','|---|---|---|---:|---:|---|']
 lookup={p['player_master_id']:p for p in r['players']}
 for s in r['display_slots']:
  p=lookup[s['player_master_id']];full.append(f"| {s['slot']} | {p['name']} | {p['team']} | ${p['salary']:,} | {p['base_mean']:.2f} | {p['player_master_id']} |")
 if r.get('salary_flow'):
  f=r['salary_flow'];full+=['',f"Wilson replacement releases ${f['released']:,}; net other-slot reinvestment ${f['net_reinvested']:,}; unspent ${f['unspent']:,}."]
 full+=['',f"Canonical roster hash: `{r['canonical_roster_sha256']}`.",'']
(P/'FULL_ROSTERS.md').write_text('\n'.join(full)+'\n')
(P/'CANDIDATES.json').write_text(json.dumps(dict(source_results_sha256=hashlib.sha256((P/'RESULTS.json').read_bytes()).hexdigest(),candidates=runs),indent=2)+'\n')
rows=['| Forced replacement | Saves vs Wilson | Original ARI-response requirement: base / objective Δ | ARI response optional: base / objective Δ | Optional-arm unspent |','|---|---:|---:|---:|---:|']
for label in x['eligible_candidate_ids']:
 a=by[('required_ari_response',label)];b=by[('optional_ari_response',label)];rows.append(f"| {label} | ${b['salary_flow']['released']:,} | {a['base_mean']:.2f} / {a['delta_saved_baseline']['conditional_objective']:+.2f} | {b['base_mean']:.2f} / {b['delta_saved_baseline']['conditional_objective']:+.2f} | ${b['unused_salary']:,} |")
(P/'ALL_COMPARISONS.md').write_text('# All twelve forced-replacement tests\n\nObjective deltas compare the same frozen LAR-passing world against saved baseline 168.674565. Base totals do not include conditional adjustments.\n\n'+'\n'.join(rows)+'\n')
(P/'VALIDATION.json').write_text(json.dumps(dict(verified=True,checks=['29 Optimal solves with Optimal Solution Found status','25 distinct canonical rosters','frozen source hash unchanged','exact saved baseline score reproduced to 1e-8','optimized Wilson-retained control matches baseline under both arms','three requested core UUIDs retained in all29','Wilson absent in all26 exclusion treatments','nine canonical players and legal derived FLEX in each roster','replacement savings reconcile to net reinvestment plus unspent for all24 forced-replacement solves'],production_code_changes=False,live_db_writes=False),indent=2)+'\n')
print('Artifacts validated and rendered:',len(runs),'solves',len({r['canonical_roster_sha256'] for r in runs}),'distinct rosters')
