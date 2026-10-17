import json
from pathlib import Path
root=Path(__file__).resolve().parent
s=json.loads((root/'FINAL_ACCEPTANCE.json').read_text())
j=json.loads((root/'final_optimizer_job.json').read_text())
first=json.loads((root/'first_fresh_optimizer_job.json').read_text())
r=j['params']['strategy_runtime']['football_analyst'];old=first['params']['strategy_runtime']['football_analyst']
assert r['input_snapshot']['model']==old['input_snapshot']['model']
assert r['input_snapshot']['players']==old['input_snapshot']['players']
stories=[
 'Dobbins rushing payoff with both QBs; DEN leader Waddle is the receiving anchor. This roster was generated under the reference and SEA run-control worlds.',
 'DEN passing upside through Waddle Captain and Nix, with Darnold/Barner on SEA. It was generated under the reference and DEN breakout worlds.',
 'DEN passing-upside alternative through Sutton Captain plus Nix/Waddle; Darnold/Barner provide SEA receiving linkage. Generated in the DEN breakout world.',
 'Harvey Captain supplies the fourth legal exposure choice, with Nix/Waddle and Darnold/Barner. Added under the current reference world; his backup role makes this a more speculative Captain branch, not an asserted promotion.'
]
lines=['# Thursday research lineups — saved and reopened','',
 f"**PASS: 4/4 saved and reopened in Chrome**, run `{s['run_id']}`. Only the DEN opponent exclusion was turned off. The 25% Captain cap, 4 lineups, 100% player cap, $1,700 base salary minimum, WR/RB Captains, non-QB leader requirement and other settings remain unchanged.",'',
 'Each Captain appears once. Every roster is 3 DEN / 3 SEA, under $50,000, and includes Jaylen Waddle as the qualifying season-average DEN leader (10.34 DK PPG over five prior games). Both WR Captains are paired with Bo Nix. No Q player is selected. Final entry readiness remains false.','',
 '| Lineup | Captain | Total salary | Model mean | Scenario generation lineage |','|---|---|---:|---:|---|']
for item in s['lineups']:
 lines.append(f"| {item['lineup']} | {item['captain']} | ${item['salary']:,.0f} | {item['base_projection']:.2f} | {', '.join(item['scenario_ids'])} |")
lines+=['','The model mean is the saved base projection sum including the Captain multiplier. Scenario generation lineage identifies which conditional world produced a candidate; it is not a calibrated probability or proof that the story will happen.','']
for item,story in zip(s['lineups'],stories):
 lines += [f"## Lineup {item['lineup']} — {item['captain']} Captain",'',story,'', '| Slot | Player | Salary |','|---|---|---:|',f"| CPT | {item['captain']} | ${item['captain_salary']:,.0f} |"]
 lines += [f"| FLEX | {x['name']} | ${x['salary']:,.0f} |" for x in item['flex']]
 lines += [f"| **Total** | | **${item['salary']:,.0f}** |",'']
lines += ['## Portfolio review','',
 'Bo Nix, Sam Darnold, Jason Myers and Jaylen Waddle appear in all four. Captain exposure is diversified, but the portfolio still shares a four-player core and every Captain is DEN. These four legal rosters therefore do not represent four independent game outcomes. The research packet includes SEA run-control, but this small selected portfolio does not directly express that branch with a SEA RB Captain. The current model favors the selected combinations under the declared constraints; this is not evidence that Denver is likely to score 40.','',
 'Dobbins is the app’s provisional recommendation because it has the highest saved model mean among these four. Waddle/Sutton are the clearest DEN passing what-if constructions. Harvey is the weaker role-based Captain expression: he remains an expected backup in source evidence, and the extra candidate is an exposure-feasibility alternative, not new football evidence.','',
 'Ownership fields are modeled estimates; paid-finish probability, duplication-adjusted value, expected return and the scenario likelihoods are not validated here. Final injury/active checks and entry clearance remain separate. No contest entry or export was performed.','',
 '## Automatic lineage','',f"- Prepared run: `{s['preparation_run_id']}`",f"- Projection: `{s['projection_run_id']}`",f"- Authored packet: `{s['source_packet_sha256']}`",f"- Checked packet: `{s['checked_packet_sha256']}`",f"- Compatibility: `{s['compatibility_sha256']}`",f"- Prepared source hash: `{s['source_sha256']}`",'',
 'The saved job parameters, runtime prepared-research receipt, checked packet, compatibility artifact and selected lineup tags match. Chrome Reopen results loaded this same saved run. Full machine assertions are in `verify_final.py` and `FINAL_ACCEPTANCE.json`.']
(root/'LINEUP_REVIEW.md').write_text('\n'.join(lines)+'\n')
report=f'''# Final Thursday Prepare → Optimize acceptance

**PASS: actual Chrome Prepare → Optimize AUTO → Reopen results, 4/4 saved.** Run `{s['run_id']}` uses the requested research settings with only DEN opponent exclusion off. Full readable rosters, salaries and qualified story review: `LINEUP_REVIEW.md`.

Prepare did not previously fetch missing historical participation. It now checks every prior regular-season week and automatically captures/ingests missing stats or snaps before rebuilding. The actual first Chrome Prepare captured 1,400 available nflverse Week 5 snaps (all 30 scheduled teams), with immutable snapshot/ingest linkage. Existing Week 5 stats (1,057 rows) were preserved. The strict canonical leader check now succeeds through Week 5; unresolved/conflicting identities stay explicit. The subsequent Prepare required no history fetch because coverage was complete.

Expired Thursday injury hypotheses were preserved. A separate research decision was authored from the fresh prepared pool, captured current ESPN/DraftKings quote and corrected history, with current reference, user-authorized DEN passing-breakout what-if and conditional SEA run-control worlds. It claims no fresh injury/coverage edge or fitted 40-point prediction. Original source clocks are retained; this is not an expiry extension. See `FRESH_RESEARCH.md` and the immutable new packet/receipt.

The first AUTO optimization (`1786c871…`) correctly underfilled 3/4: six initial scenario solves produced four distinct rosters but only three distinct Captains. The 25% cap therefore could not select four. The focused fix expands an underfilled Showdown candidate pool with a bounded search for unseen Captains against the identical legal model and authored scenario worlds. It retains locks, eligibility, focus/story and all exposure constraints. The second run added one candidate (RJ Harvey Captain) and reached four without relaxation. The initial and final captured legal model dictionaries and player snapshots are byte-equivalent as parsed structures; their distinct run/decision clocks and candidate sets are retained, so this is a generation repair, not a controlled selector experiment.

Chrome saved and reopened four canonical role-distinct rosters with Captains Dobbins, Waddle, Sutton and Harvey once each. Salaries: $49,200 / $48,500 / $49,600 / $47,200. All are 3–3, have base salaries >=$1,700, include the strict Waddle leader, exclude Qs and respect WR/RB Captain and QB pairing rules. Saved AUTO packet/compatibility/projection/source lineage matches preparation and selected lineup tags. Entry readiness stays false; no contest action or export occurred.

Validation: 175 history/readiness/preparation/rank tests plus 50 focused scenario/focus/Captain/automatic-lineage tests passed. The two pre-existing synthetic forced-leader cases remain separately documented/deselected. UI TypeScript/Vite build, Python compilation and diff whitespace checks passed. Idle managed local services were restarted to load the two focused backend repairs; no active job was interrupted and no duplicate run was queued.

Evidence: `FINAL_ACCEPTANCE.json`, `final_optimizer_job.json`, `fresh_analyst_preparation.json`, `final_reopened_dom.txt`, `final_lineup_view.jpg`, `LINEUP_REVIEW.md`, `source_capture_and_ingest.json`, `history_validation.json`, `leader_validation.json`. Earlier `REPORT.md` records the now-resolved expiry blocker and is preserved as historical evidence. Sunday’s previously saved/reopened preliminary run remains `5158eba0-395b-47bf-882a-5159a676a2ad` (5/5, entry readiness false); it was not regenerated in this Thursday repair.
'''
(root/'FINAL_REPORT.md').write_text(report)
print('reports saved; original/final mathematical model and player snapshot equal')
