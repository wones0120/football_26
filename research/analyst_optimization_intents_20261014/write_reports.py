import json
from pathlib import Path
root=Path(__file__).resolve().parent
s=json.loads((root/'FINAL_COMPARISON.json').read_text());runs=s['runs'];expected=runs['EXPECTED_GAME'];contrarian=runs['CONTRARIAN']
fmt=lambda amount:f'${amount:,.0f}'
def cell(lineup):
 captain=next(p for p in lineup['players'] if p['roster_position']=='CPT')
 flex=[p for p in lineup['players'] if p['roster_position']=='FLEX']
 return '**CPT '+captain['name']+' '+fmt(captain['salary'])+'**<br>FLEX '+', '.join(p['name']+' '+fmt(p['salary']) for p in flex)+'<br>**Total '+fmt(lineup['salary'])+'**'
lines=['# Thursday: Expected Game vs Contrarian','',
 '**Both passed: 4/4 saved, reopened and verified in Chrome.** One Prepare supplies identical salary, projection, ownership and source inputs. Only the intent changes; all 30 asserted user-control values match the prior authorized Thursday run, including 4 lineups, 100% player cap, 25% Captain cap, $1,700 base salary minimum, WR/RB Captains, non-QB leader required, Q exclusion and DEN opponent exclusion OFF.','',
 '**Expected Game:** competitive lower-total game, SEA modestly favored (market SEA -2.5, total 40.5). It uses current role-based upside plus a modest SEA drive-success envelope, with conditional mean + 0.35 P90 spread in candidate generation. It is not a mean-only/safe lineup mode. No explicit Denver 40-point what-if or Captain-team constraint enters this intent.','',
 '**Contrarian:** previously authorized DEN passing breakout above its market-implied 19.0 points. Roughly 40 points remains a narrative tail target, not a fitted forecast or probability. This intent uses only that conditional world and requires a DEN QB plus at least two DEN WR/TE across Captain and FLEX. The Captain team remains unrestricted. The 1.3 passing / 0.7 rushing factors and elasticity 0.6 are declared uncalibrated sensitivities.','',
 '| Saved lineup | Expected Game | Contrarian |','|---|---|---|']
for a,b in zip(expected['lineups'],contrarian['lineups']):lines.append(f"| {a['lineup']} | {cell(a)} | {cell(b)} |")
lines+=['','Numbers are each saved run’s lineup order, not matched pairs or evidence of an independent ranking. Captain identity is part of the Showdown roster. Expected Game has four role-distinct rosters but three unique six-player sets because the Waddle/Harvey Captain variants share the same players. Contrarian has four role-distinct rosters and four unique six-player sets.','',
 '## What actually changed','',
 '| Captain / comparison | Scenario-driven change |','|---|---|',
 '| Dobbins in both | Contrarian replaces SEA Kupp FLEX with DEN Engram, moving from 3–3 to 4 DEN / 2 SEA and supplying the second DEN receiver alongside Waddle. Salary rises $49,200 → $50,000. |',
 '| Waddle in both | Contrarian replaces Harvey and Barner with Sutton and Engram: more correlated DEN receiving exposure, 4 DEN / 2 SEA, salary $48,500 → $49,900. |',
 '| Sutton in both | Exactly the same $49,600 roster. It already contains Nix + Sutton/Waddle and satisfies both primary-context upside and the alternate passing construction. No artificial novelty is forced. |',
 '| Fourth Captain | Expected uses Harvey ($47,200); Contrarian uses SEA Kupp ($46,200) with Darnold plus DEN Nix/Sutton/Waddle. Kupp is an opponent receiving-response construction, not a promotion or a prediction that SEA wins. |','',
 'Both portfolios have Nix, Darnold, Myers and Waddle in all four. The expected and alternate labels therefore do not make these independent portfolios. One of four format-relevant rosters is identical across intents; three differ. All Captains appear once (25%).','',
 '| Player | Expected roster exposure | Contrarian roster exposure | Expected CPT | Contrarian CPT |','|---|---:|---:|---:|---:|']
for pid,name in sorted(s['player_names'].items(),key=lambda item:item[1]):
 e=expected['player_exposure'].get(pid,0);c=contrarian['player_exposure'].get(pid,0)
 if e or c:lines.append(f"| {name} | {25*e}% | {25*c}% | {25*expected['captain_exposure'].get(pid,0)}% | {25*contrarian['captain_exposure'].get(pid,0)}% |")
lines+=['','## Why Expected Game still has DEN Captains','',
 'The old mixed run evaluated candidates across every shared world, including the DEN breakout, then added a fourth distinct Captain to satisfy the 25% cap. Its all-DEN result was a combination of the blended objective, candidate coverage and the unchanged source/user constraints—not a hidden DEN Captain rule.','',
 'The separated Expected Game run now contains only its two primary-context worlds, yet selects the same four DEN Captain identities. JSN retains a strong model assessment but is excluded by the native DraftKings Q preference. That makes Waddle the available qualifying season-average leader for every roster. Given his salary, the remaining prices and the upside objective, DEN Captain combinations remain preferable under these settings. A small SEA market advantage does not imply that a SEA Captain must be selected. No player bans, Q overrides, role promotions or Captain-team forcing were introduced to manufacture a difference.','',
 'Each intent initially generated two distinct candidates. The existing bounded search added two legal unseen-Captain alternatives to satisfy four distinct Captains at 25%; it did not weaken the cap. Both final candidate pools contain four candidates and all four were selected. These are **matched-input generation experiments with different scenario/story candidate pools**, not a controlled selector comparison over one frozen pool.','',
 '## Saved evidence','',f"- Expected Game: `{expected['run_id']}`",f"- Contrarian: `{contrarian['run_id']}`",f"- Shared preparation: `{s['prepared_run_id']}`",f"- Shared projection: `{s['projection_run_id']}`",f"- Shared ownership: `{s['ownership_run_id']}`",'',
 'Both immutable checked packets and compatibility receipts are distinct and match their prepared intent, saved runtime and lineup tags. The complete base legal model, prepared player rows and all asserted user controls match. `FINAL_COMPARISON.json` contains hashes and machine-checked assertions; `verify_compare.py` reproduces those assertions. Chrome Reopen results verified both; a browser reload also preserved the intent choice, Thursday DEN exclusion OFF and both saved comparison columns.','',
 '**Research only:** entry readiness remains false. Final injury/role clearance, scenario likelihoods, duplication-adjusted value, expected return and paid-finish probability are not established. No contest entry or export occurred.']
(root/'SIDE_BY_SIDE_REVIEW.md').write_text('\n'.join(lines)+'\n')
report=f'''# Expected Game / Contrarian implementation and Chrome acceptance

**Complete: both actual Chrome intent flows save and reopen 4/4 from one matched Prepare.**

- Expected Game: `{expected['run_id']}`; only `expected_competitive_reference` / `expected_sea_drive_upside`.
- Contrarian: `{contrarian['run_id']}`; only `contrarian_den_breakout`, with typed DEN QB + two WR/TE requirements and no Captain-team forcing.
- One shared Prepare: `{s['prepared_run_id']}`. Projection `{s['projection_run_id']}`, ownership `{s['ownership_run_id']}`, source SHA `{s['source_sha256']}`.

The app now separates these intents, freezes automatic scoped packets and compatibility receipts during Prepare, persists intent/scenario lineage in saved runs/results, labels recent runs and provides a persistent side-by-side roster/salary/scenario/exposure comparison. Missing authored classification or mismatched intent/packet/scenario receipts block without mixed/baseline fallback. Expected Game explicitly excludes user what-ifs. A new source-backed primary/alternate research decision preserves predecessor packets and original source clocks; no expiry was merely extended. Source/model truth and user settings are unchanged.

All 30 asserted user-control values match the prior authorized Thursday research request (DEN opponent exclusion OFF, all other controls retained). The opponent exclusion edit is now scoped/persisted for the active context so an app refresh cannot silently restore DEN for this comparison or change another slate's setting. Final entry readiness stays false.

Exact validation: selected intent receipt equals prepared receipt in frozen optimizer evidence, runtime expanded compatibility and applied handoff; checked/scoped/authoring hashes trace immutably; lineup tags and generation worlds contain only the chosen intent. Shared salary/source/projection/ownership, base legal model and prepared player rows match. Distinct candidate pools are disclosed as generation experiments. Each intent achieved four unique Captains at 25% without constraint relaxation, with canonical leader, salary, QB pairing, team-count and Q-exclusion assertions. One role-relevant roster overlaps between portfolios; three differ. Full player-level comparison and honest story limitations are in `SIDE_BY_SIDE_REVIEW.md`.

Verification found an initial audit-report link still pointed to the parent mixed receipt although the correct scoped packet drove generation. The evidence return path was repaired to carry the selected intent receipt; the final saved runs above pass full receipt equality checks. Earlier first-pass records `d5e9a158…` / `29e16a8e…` remain intact as historical evidence and are not the final acceptance runs.

Validation: 87 affected backend tests and 8 UI tests passed; the audit-return correction also passed the 30 affected preparation/intent tests. TypeScript/Vite build, Python compilation and diff whitespace checks passed. Desktop Chrome visual checks confirmed readable two-column rosters and persistent comparison after reload. Idle managed API/worker restarts loaded the feature and audit fix without interrupting active jobs. No dependency/config/schema/default projection changes or contest actions were made. Existing dirty work and all old artifacts were preserved.

Implementation: `analyst_intents.py` and focused tests; extensions to packet validation, preparation, binding, scenario generation, request validation and saved history; `analystIntent.ts`, `AnalystIntentComparison.tsx/.css`, App selection/wiring, recent-run labels and API types; README, RELEASE_NOTES, and product intent/preparation docs.

Evidence: `FINAL_COMPARISON.json`, `expected_final_job.json`, `contrarian_final_job.json`, `preparation.json`, `packet.json` / `packet_receipt.json`, final reopened/reloaded DOM captures, `final_comparison_text.txt`, `comparison_view.jpg`, `comparison_lineups_view.jpg`. The full user review is `SIDE_BY_SIDE_REVIEW.md`.
'''
(root/'FINAL_REPORT.md').write_text(report)
print('side-by-side review and final evidence report saved')
