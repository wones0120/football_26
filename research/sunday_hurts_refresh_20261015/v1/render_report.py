from pathlib import Path
from collections import defaultdict
import json
P=Path(__file__).resolve().parent;e=json.load(open(P/'EVIDENCE.json'));arms=json.load(open(P/'matched_comparisons.json'));saved=json.load(open(P/'saved_run.json'));base=e['fresh_unlocked_mean'];model=saved['params']['strategy_runtime']['highest_projection']['input_snapshot'];pool={r['player_id']:r for r in model['players']};obj={r['name']:r['value'] for r in model['model']['objective']['coefficients']};variables=model['variable_players'];assert all(obj.get(var,0)==pool[pid]['projection'] for var,pid in variables.items());assert set(obj)<=set(variables)
fixed=[c for c in model['model']['constraints'] if c['sense']==0 and len(c['coefficients'])==1 and c['coefficients'][0]['name'] in variables and abs(c['constant'])==1];assert fixed==[]
def slots(rows):
 g=defaultdict(list)
 for r in rows:g[r['position']].append(r)
 for a in g.values():a.sort(key=lambda p:(-p['projection'],p['player_id']))
 o=[]
 for pos,n in [('QB',1),('RB',2),('WR',3),('TE',1),('DST',1)]:o.extend((pos,g[pos].pop(0)) for _ in range(n))
 left=[p for a in g.values() for p in a];assert len(left)==1;o.append(('FLEX',left[0]));return o
full=['# Frozen fresh full rosters','','All six comparison arms use the same 201-player legal input frame and exact sum of baseline means. Only the primary unlocked lineup is saved in the app. Other arms are isolated generation experiments with explicit diagnostic locks; both running backs remain allowed in each single-RB arm. No app preferences were changed.','']
for name,arm in arms.items():
 a=arm['audit'];full += [f'## {name}','',f"Optimal; ${a['salary']:,.0f}; {a['base_mean']:.6f} projected points; gap {a['base_mean']-base:+.6f}. Canonical locks: {a['locked_player_ids'] or 'none'}.",'','| Slot | Player | Team | Salary | Mean | Canonical UUID | DK ID |','|---|---|---|---:|---:|---|---|']
 for slot,r in slots(arm['lineups'][0]):full.append(f"| {slot} | {r['name']} | {r['player_team']} | ${r['salary']:,} | {r['projection']:.4f} | {r['player_id']} | {r['dk_player_id']} |")
 full.append('')
(P/'FULL_ROSTERS.md').write_text('\n'.join(full)+'\n')
comparison=['| Slot | Fresh unlocked / Henry required | Hubbard required |','|---|---|---|'];a=dict(slots(arms['unlocked_replay']['lineups'][0]));b=dict(slots(arms['hubbard_required']['lineups'][0]))
for slot in ['QB','RB','WR','TE','DST','FLEX']:pass
# Use a stable natural-position display; duplicate RB/WR rows remain separate.
for (sa,pa),(sb,pb) in zip(slots(arms['unlocked_replay']['lineups'][0]),slots(arms['hubbard_required']['lineups'][0])):comparison.append(f"| {sa} | {pa['name']} ${pa['salary']:,} | {pb['name']} ${pb['salary']:,} |")
comparison.append('| Total | **$49,800 / 133.14** | **$50,000 / 132.80** |')
report=f'''# Sunday refresh after Hurts OUT — October 15, 2026

**The refreshed highest-projected lineup keeps Henry, Panthers DST and Odunze; Stafford still wins without a lock.** Saved and API/browser reopened run `{e['saved_run_id']}` is **Optimal, 133.1430 points, $49,800**. This is highest among the **201 eligible players under the retained user rules**, not all NFL players. Stacks/bringbacks remain optional, all player locks are empty, and the objective is the exact sum of unchanged baseline means.

{chr(10).join(comparison)}

**Hubbard versus Henry is close at whole-roster level: 0.3412 points.** Henry's fresh mean is 18.8087 at $8,200; Hubbard is 14.5746 at $6,300. Requiring Hubbard does not require removing Henry, but the optimizer voluntarily replaces **Henry + Tate ($13,200)** with **Hubbard + Flowers ($13,400)**, spending the winner's unused $200. Henry→Hubbard releases $1,900 and loses 4.2341 individual points; Tate→Flowers spends $2,100 and recovers 3.89296. Henry-required reproduces the winner. Requiring both backs scores 131.8165 at $49,600 and introduces **Ted Hurst III $3,000** while dropping Tate/Wan'Dale; that extra punt risk is not a compelling improvement. All are separate exact Optimal solves, not one-player arithmetic substitutions. [Six full legal rosters and canonical IDs](FULL_ROSTERS.md).

Hubbard's last three observed games show 12/19/20 carries, 17 per game, 2.67 targets, and 84% snaps in both latest appearances; Carolina had a Week 5 bye. His last game was 20/122/2 rushing. Henry has 26/23/24 recent carries, 24.33 per game, 1.67 targets, and 67%/62%/55% offensive snaps; Hill/Mitchell still handle work. Henry's established carry load supports the higher mean, while Hubbard buys a stronger receiver elsewhere. Neither has an injury designation on the captured Wednesday club table; that is not final clearance. Carolina has Freeling DNP/Lewis LP; Moton's return window still requires activation. Baltimore has Lamar DNP and multiple OL limited, so Henry's team efficiency and script remain uncertain rather than automatically benefiting from a backup QB. Cleveland has several defensive linemen DNP, which is a conditional blocking advantage, not confirmed absences. All workload joins use canonical UUID and source-native aliases, retained raw row/ingest IDs, and observed games only. [Usage evidence](usage_summary.json).

**Panthers DST is a more attractive football matchup after Hurts OUT, but its model mean did not rise: 4.6123 → 4.6123.** The refreshed market at **19:16:01 UTC** has CAR -3.5, total38.5 (CAR21/PHI17.5 implied), versus the prior CAR -1.5/40.5 total. Hurts' absence removes his designed-rushing/escape threat; McKee behind Philadelphia's disrupted line offers a plausible sack/drive-stall route. This is an analyst interpretation, not a measured pressure-rate edge or a guaranteed turnover increase. Carolina's own Horn and Mike Jackson remain on IR, Cam Jackson joined IR, and Phillips was limited; McKee can still exploit weakened coverage. [Official Hurts statement](https://www.philadelphiaeagles.com/news/statement-from-the-philadelphia-eagles-on-qb-jalen-hurts), [CAR corners](https://www.panthers.com/news/panthers-place-jaycee-horn-and-mike-jackson-on-injured-reserve), [CAR front/returns](https://www.panthers.com/news/panthers-placed-defensive-tackle-cam-jackson-on-ir-among-other-moves-taylor-moton-turk-wharton-trevor-etienne).

Saints at $2,600 project4.4182. Requiring them preserves the other eight players, spends $100 of the unused $200 and scores132.9489, **0.1941 below Panthers**. Giants tackle DNPs/Winston turnover and sack opportunities remain a credible alternative; Saints defensive injuries remain counterevidence. Other eligible DSTs competed freely in the main solve. No verified pressure metric or new turnover probability was invented.

**Odunze's QB is unresolved.** The latest captured [official Bears report](https://www.chicagobears.com/news/caleb-williams-takes-another-step-toward-return-from-hamstring-injury), published Oct14 17:35 club time, says Williams would have been FULL in Wednesday's walkthrough, but the starter remains unknown among Williams/Bagent/Keenum. The current club table also shows Wednesday FP, with Thursday/Friday blank. The canonical depth-based Williams starter row remains **provisional**, not confirmed; no new starter announcement was found. Odunze retains his 11.5285 mean and strong observed 6→7→9 targets/99% latest snaps, but those recent targets came with backups, so a Williams return can change distribution. Burden/Loveland remain competition. No backup upgrade or full-health assumption was applied.

## What the refresh actually changed

Captured Hurts statement **19:14:51 UTC** (published Oct15 13:00 Eastern), immutable source snapshot `0bac0466-b9de-5a5e-b8be-6f2753b81279`; canonical PHI QB `83d7ba4e-3f9b-4769-a9d4-37ad680ef63b`; appended context `b696df30-e0c5-4559-934c-ba1c747b8ba2`. OUT supersedes the older Wednesday FP. McKee canonical `783b00df-c32b-4054-bff3-906ea6fbc4a7` is the sourced **provisional** expected replacement based on the next rank in the current club depth chart, not a fabricated confirmed announcement. Hurts is absent from the eligible optimizer pool. McKee's $4,000 salary also fails the unchanged $4,500 QB minimum.

The app refreshed markets, weekly roster/history, canonical context, projection and ownership together. Preparation `67bd6a71-f9db-42dc-86a2-05aee5cbdddf`; projection `{e['projection_run_id']}`; ownership `{e['ownership_run_id']}`; frozen research snapshot `{e['snapshot_sha256']}`; cutoff `{e['cutoff']}`. [Source/model evidence](EVIDENCE.json), [actual immutable feature proof](fresh_projection_proof.json), [submitted request](submitted_request.json), [reopened saved API result](reopened_api.json).

The current model consumes QB availability/start role, teammate opportunity allocation and current market features. **It has no direct opponent-starting-QB quality feature** for DST, nor a QB-specific efficiency adjustment to PHI receivers/RBs. Starter identity is lineage/start-probability evidence, not a learned quality coefficient. Its team/game outlook uses lagged team history and home/rest, not the current starter; no new fitted outlook was claimed. Thus this rerun does **not** claim that excluding Hurts fully models McKee's effect on the matchup. The direct QB-quality feature gap is being addressed separately in shadow research; it has not altered this saved lineup or its official model values.

Old unlocked mean133.1786→fresh133.1430 is a **data refresh comparison**, not a policy experiment. Same roster; Henry's -0.03557 accounts for its total change. Hubbard changed -0.03749; Odunze/Panthers/Saints unchanged. No hand-applied Hurts bonus. Other rules retained: Q excluded, QB/RBminimum4500, singleTE, favored-teamRB/DST, team4/game5caps, nooffensevsDST, DEN-opponent exclusion,100%maxexposure, request-only unrestricted season-average ranks as before. Stored rank preferences/count and Thursday settings remain untouched.

The saved result remains **entry_ready=false**: official report identity `/players/david-sills` still needs review; four conservative unknown/questionable exclusions remain explicit. This is not final Sunday injury clearance. No exports or contest entries. **65 targeted backend tests passed** (highest objective, shared Sunday injuries, canonical input context). No application code changed for this refresh. Objective coefficients exactly match each baseline mean; no auxiliary objective terms or single-player forced equalities; all six matched solves Optimal.

![Reopened fresh app result](ui_reopened.jpg)
'''
(P/'REVIEW.md').write_text(report)
(P/'VALIDATION.json').write_text(json.dumps(dict(saved_run_id=e['saved_run_id'],reopened_api=True,solver_status='Optimal',exact_objective=True,auxiliary_objective_coefficients=0,forced_player_equalities=fixed,same_pool_all_six_arms=True,eligible_players=201,entry_ready=False,tests_passed=65,policy_changed=False,code_changed=False),indent=2)+'\n')
print('report and full rosters written')
