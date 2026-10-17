from pathlib import Path
import json,csv
from collections import Counter
P=Path(__file__).resolve().parent
load=lambda n:json.loads((P/(n+'.json')).read_text())
s=load('saved_run');inc=load('incumbent_counterfactual_local_run');ref=load('fresh_highest_baseline_reference_local_run');old=json.loads(Path('research/sunday_hurts_refresh_20261015/v1/saved_run.json').read_text())
def lineup(rs):
 ordered=[];remaining=list(rs)
 for pos,n in [('QB',1),('RB',2),('WR',3),('TE',1)]:
  selected=sorted([r for r in remaining if r['position']==pos],key=lambda r:-r['projection'])[:n]
  for r in selected:ordered.append((pos,r));remaining.remove(r)
 ordered.extend([('FLEX',r) for r in remaining if r['position']!='DST']);ordered.extend([('DST',r) for r in remaining if r['position']=='DST'])
 return ordered
def table(rs):
 out=['| Slot | Player | Team | Salary | Baseline mean |','|---|---|---|---:|---:|']
 out += [f"| {slot} | {r['name']} | {r['player_team']} | ${r['salary']:,} | {r['projection']:.3f} |" for slot,r in lineup(rs)]
 return '\n'.join(out)
text='''# Sunday Main: accepted defense refresh, 2026 Week 6

Saved run **bebc581f-cda1-4db9-b0a1-352eeba6efea** contains five legal Analyst Mixed research lineups. The actual saved report reopened in Chrome at localhost5173. No contest entry was submitted. **ENTRY READY: NO; contest export remains disabled.**

Normal preparation failed on current evidence for Max Klare, CJ Daniels, Joshua Palmer and DJ Moore. The authorized preliminary workflow conservatively excludes those four; it does not assume health or full workload. The later snapshot displays READY for the remaining assessed pool, which must not be confused with clearance of the original complete normal pool. Final game-day designations remain separate. Main's normal active projection pointer remains unchanged.

## Frozen inputs and controls

Accepted projection **c8869a96-440c-4c36-aead-3614d6ef4d97**, model run **3dd3819a-b880-4696-a734-eb689c96bde9**, cutoff **2026-10-16 14:58:29.446687 UTC**. 285 forecasts (265 offense,20 DST) within a native frozen salary pool of513 rows. Snapshot **6d662321caa3a513bb7720d68f836aca4cad96581314757c5e35d7d794ae207a**. Checked Analyst packet **693befcad20dd476c265112431ef39cf0d756795561ea3a10d2603737f23aeca**.

Actual saved controls preserved: five lineups,80% exposure,team cap3,game cap4,maximum overlap5,Q exclusion,DEN-opponent exclusion,QB/RB minimum$4,500,all offensive season-average rank filters top50%,singleTE,no player locks,no required favored positions. Analyst Mixed/AUTO. Existing AUTO discovery/challenger/teammate helpers are enabled; **new joint-opportunity prototype remains false**. Mixed includes alternative scenario paths; it is not a five-lineup highest-baseline ranking. No settings changed to the old one-lineup preset.

The checked Analyst decision originated October15 13:49:14UTC and was revalidated against the fresh snapshot (560 changes,needs_review). Revalidation is not a new outcome-blind research packet. Conditional tail scores and summed marginal P90s are heuristics, not a calibrated joint quantile or win probability.

## Saved full rosters

FLEX placement below is a legal presentation reconstructed from natural position; equivalent Classic RB/WR ordering is not a separate canonical roster.
'''
for i,rs in enumerate(s['results'],1):
 text+=f"\n### Lineup {i}: ${sum(r['salary'] for r in rs):,}; baseline mean {sum(r['projection'] for r in rs):.3f}\n\n"+table(rs)+'\n'
text+='''
## Football paths and shared risks

1. Young/Hubbard need productive Carolina offense with both passing and rushing contributions; they can coexist without both reaching their P90. Puka/Kyren need enough LAR production across receiving/rushing. Henry benefits from BAL control. Cheap Jets DST releases salary for that offensive combination; it is not the highest projected defense.
2. Shough/Vele is an explicit NO passing path, plus Cook/Hubbard rushing opportunity and Puka/Kyren. Passing concentration and Shough efficiency are shared risks; the roster does not require every isolated ceiling.
3. Brissett/Wilson with Puka/Kyren uses four ARI–LAR players: sustained LAR production and Arizona passing response can support it. A poor game environment threatens four roster spots; the game cap is reached.
4. Stafford/Kyren can contribute through separate LAR scoring channels. Taylor supports IND control while Tate/Wan'Dale may receive TEN trailing volume. Two TEN WR remain optional optimizer choices, not locks. Both share Ward's passing-volume/efficiency downside and compete for targets. Current evidence does not justify a blanket teammate penalty or an assertion that both need P90; precise joint success probability is unknown.
5. Mahomes/Worthy expresses KC passing success; Puka/Higbee concentrates another passing game. Henry/Jeanty need sufficient independent rushing roles. This is a distinct scenario roster with lower baseline expectation, not proof of a superior chance to win.

Puka,Kyren,Odunze and Otton each appear4/5 (80%). **Every lineup contains at least two LAR players**: QB diversity therefore does not remove shared LAR game risk. Odunze's four appearances also share Chicago QB uncertainty. The portfolio respects the user's caps, but those caps alone do not establish good diversification or optimal full-lineup success likelihood. No calibrated portfolio win probability is available.

## Defense-only matched generation comparison

The offline ensemble replay reproduces all five saved canonical rosters **in order**. The counterfactual holds the frozen pool,all non-DST cells,eligibility,controls,checked packet and seed fixed, substituting only same-fitted-model incumbent DST means/quantiles/calibration fields. It performs no fits,configuration changes or database writes. This is a **matched generation experiment**, not a fixed-candidate selector test; candidate generation can change under the DST intervention.

| Entry | Incumbent mean | Ensemble mean | Roster change |
|---|---:|---:|---|
'''
for i,(a,b) in enumerate(zip(inc['results'],s['results']),1):
 aid={r['player_id']:r for r in a};bid={r['player_id']:r for r in b};out=', '.join(r['name'] for k,r in aid.items() if k not in bid) or 'none';inn=', '.join(r['name'] for k,r in bid.items() if k not in aid) or 'none'
 text+=f"| {i} | {sum(r['projection'] for r in a):.3f} | {sum(r['projection'] for r in b):.3f} | Out: {out}; in: {inn} |\n"
text+='''
Four of five canonical rosters change; entry2 remains identical and gains1.880019 solely from CAR's forecast. CAR same-input incumbent4.720434 →ensemble6.600452 ($2,500),rank10→3. LAR5.848996→6.329840,rank1→7; KC5.813295→6.765604,rank3→1. Eighteen of20 DST ranks change. These are forecasts; ranking advantage is unproven and was explicitly accepted with rollback.

Corrected serving contract **verified_dst_serving_component_v1**,policyensemble; selection SHA **c2a5aee81621a1403f6e6b04cc2fab717ae179bc30044c732f5fb5a340b07a89**; combined fitted artifact **c55178561a04c8b4d078697ad21c726bf39467289ec6b8c01c5b6bd12a4cc28a**. The deployment verifier checked20 DST means,five quantiles,corrected source/Gold cells,and exact265-offense pre-overlay parity. Calibration uses88 prior residuals; that is not proof of superior rankings.

A first preliminary run b13daaf6 used an unmanaged stale worker and is retained as **legacy evidence only**. It was not optimized as corrected. The competing worker was stopped; this accepted run's durable worker97957 and persisted component both verified. Rollback remains documented in artifacts/dst_deployments/20261016/v1/rollback.py with before.json; no rollback performed here.

## Old baseline and current highest-mean reference

Original f84e75db-b286-48f4-8740-c03d11323889: Stafford/Kyren/Henry/Puka/Odunze/Tate/Higbee/Wan'Dale/CAR,$49,800,mean133.143044. It used one highest-baseline lineup,team4/game5 and different rank/favored controls. The new five Analyst Mixed lineups therefore cannot attribute every old-to-new change to defense.

Fresh highest-baseline **local reference only**, preserving current player eligibility/team3/game4/singleTE preferences but requesting one lineup and baseline objective (no UI changes):

'''+table(ref['results'][0])+f"\n\n${sum(r['salary'] for r in ref['results'][0]):,},mean{sum(r['projection'] for r in ref['results'][0]):.6f}. This reference is not the saved Mixed portfolio recommendation. It retains two TEN WR; it substitutes Walker for Henry and Otton for Higbee relative to the old roster. Old CAR4.612312→fresh6.600452 comprises roughly0.10812 base-fit/source change plus1.880019 ensemble-only change; do not confuse the older global-pointer CAR score with f84's score.\n"
text+='''
## Current injury and QB evidence

Fresh preparation captures current NFL/club/native evidence rather than treating old salary flags or blank final columns as clearance. Hurts remains OUT on the Eagles' October15 statement. Official Eagles reporting confirms Tanner McKee starting (captured October16 14:12:41UTC,source snapshot b06e415d-011e-550e-adbc-cf8572f42929). Caleb Williams practiced FULL, but the official Bears report still described uncertain game status; Odunze's projection does not erase that dependency. TEN's October12 club depth chart lists Cam Ward first and Tate/Wan'Dale as starting WR; depth order alone does not establish passing efficiency or a current game-day guarantee. Source packet: ../../sunday_normal_refresh_20261016/v1/qb_refresh.json. No fabricated starter probability or healthy workload override was added.

## Verification and artifacts

[Validation JSON](validation.json) confirms five distinct legal nine-player canonical rosters,salary/team/game/exposure/overlap constraints,DEN/Q exclusion,entry_ready=false,new prototype=false and exact replay. [Saved API response](saved_api_response.json),[saved full records](saved_run.json),[matched manifest](counterfactual_manifest.json),[counterfactual full records](incumbent_counterfactual_local_run.json),[local reference](fresh_highest_baseline_reference_local_run.json). Reproduce with verify_results.py; offline generation uses counterfactual.py and read-only SQL engine. These are retrospective construction comparisons, not new backtests.

[Reopened app screenshot](saved_portfolio_browser.png) shows saved run bebc581f,completed5lineups and ENTRY READY:NO. No application code was changed for this comparison. Existing deployment tests/lineage proof belong to the defense activation task; this task adds deterministic saved-output checks,not a new broad test run.
'''
(P/'REVIEW.md').write_text(text)
print(P/'REVIEW.md')
