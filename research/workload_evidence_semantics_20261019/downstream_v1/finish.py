from pathlib import Path
import json,datetime,hashlib
P=Path(__file__).parent;d=json.load(open(P/'comparison.json'));s=json.load(open(P/'summary.json'));c=next(x['constraint_config_json']for x in json.load(open('/private/tmp/sunday_actual_review_20261018/stored_run_configs.json'))if x['optimizer_run_id'].startswith('398efe88'));look={r['player_id']:r for r in c['strategy_runtime']['player_pool']['rows']};a=d['v1']['role_transport'];b=d['v2']['role_transport'];changes=[]
for key in sorted(set(a['roles'])|set(b['roles'])):
 l=a['roles'].get(key,[]);r=b['roles'].get(key,[])
 if [x['player_id']for x in l]!=[x['player_id']for x in r]:changes.append({'team_position':key,'before':l,'after':r})
s.update(pool_role_order_changes=changes,changed_role_groups=len(changes),unknown_before=len(a['audit']['unknown_role']),unknown_after=len(b['audit']['unknown_role']),unavailable_ids_equal=a['audit']['unavailable']==b['audit']['unavailable'])
rosters=[]
for idx,x in enumerate(c['strategy_runtime']['football_analyst']['candidates'],1):
 rr=[{'player_master_id':v['player_master_id'],'name':look[v['player_master_id']]['player_name'],'position':look[v['player_master_id']]['position'],'team':look[v['player_master_id']]['team'],'salary':look[v['player_master_id']]['salary'],'projection':look[v['player_master_id']]['projection']}for v in x['roster']];rosters.append({'source_order':idx,'roster':rr,'salary':sum(v['salary']for v in rr),'baseline_mean':sum(v['projection']for v in rr)})
s['original_rosters_unchanged']=rosters;(P/'summary.json').write_text(json.dumps(s,indent=2)+'\n')
text='''# Downstream workload semantic acceptance

The correction is useful for evidence integrity and operative in the full-game research role mapper. It has **not established a better selector or generated new lineups**. No fit, solver, operational run, reload, projection change or default activation occurred. Original Sunday Main run398efe88-a871-47fa-a4f1-4d3e9924a825 remains unchanged.

## Consumer boundary and source parity

The actual checked Analyst packet8b08666d… already uses separately derived, rounded raw current-team observations. The pool audit uses allocated counts under v1 historical labels;452 selected channel values differ between these two original evidence sources. The initial source-equality guard stopped before comparison. Replacing that packet with recovered feature evidence would change source/window/precision as well as labels, so the subsequent comparison is explicitly a **source-changing sensitivity**, not pure semantic A/B. No historical stories were reconstructed.

The existing public scenario-breadth replay takes saved idea/world moments and never rebuilds measurement evidence. Its original rosters/worlds therefore do not change automatically when this code lands. Repeating that optimization would not test this correction. Generic scenario construction reads packet measurements; scenario-first build_ideas reads role measurements for eligibility, ordinal priority and opponent responders; conditional_world uses them for conserved100-unit sensitivity and RB touch mix. full_game_breadth.role_universe directly reads the pool measurements for within-position rank and QB-style context, so that is the operative isolated mapping consumer tested here. Selection consumes moments/candidate scores rather than original workload fields. No new forecasts or joint probabilities are inferred from raw observations.

## Matched downstream results

All513source actors,137eligible players and376excluded actors retain IDs, model assessment, original eligibility/reasons and preferences. Missing data is not reassigned to included players.

|Check|Result|
|---|---:|
|Accepted/rejected stories, packet vs feature sensitivity|18/4 in both|
|Stories added/removed|0/0|
|Planned5stories|Same set; BUF passing and IND run-control swap order|
|Largest player conditional-mean difference|0.001768 FP|
|Direct pool A/B changed team-position rank/membership groups|10|
|Unknown/zero-role actors rejected by existing mapper, before/after|37/34|
|Fixed seed7 stress states|38|
|Same historical paired source-game plans|Yes|
|States with some changed eligible score|38|
|Changed unchanged-roster score cells|30/190|
|Whole-ledger DK point difference, including residuals|0|
|Missing-feature skill actors remaining unmapped|228/228|

The manifest-bound library actually used contains85reconciled paired games, not the older208-template inventory mentioned in the initial protocol wording. Its existing hash was checked before reuse; no library was expanded or tuned. Within each fixed state the same physical game and scoring events are retained; only assignment by workload rank changes. Ten groups change, including Cleveland WR leading order and several backup ranks. Three formerly zero/unknown roles become mapped from retained original positive history; exclusion remains exclusion. This can change which eligible actor receives a historical analog score without creating extra team production. It does not validate the cross-season rank transport, assign likelihoods to stress states, or prove that carrying forward an observed workload is a valid future forecast.

## Focused audit correction

The audit found a real remaining v2 gap: build_ideas retained a legacy proxy-only fallback, which could admit a story with no observed role at a low allowed credibility setting. A synthetic reproducer demonstrated it. The fallback now abstains for v2 unsupported construction roles with an explicit reason, while v1 behavior is preserved. This does not alter any supported story in this frozen source comparison. Captain qualification and settings remain unchanged. Full-game rank transport still has its previously disclosed historical-role and current-QB uncertainty; it is not promoted.

## Original full-roster controls

These are the unchanged five original candidates, not newly selected/saved results. Every listed salary and mean remains fixed in both comparisons.

|Original order|Complete roster|Salary|Baseline mean|
|---|---|---:|---:|
'''
for r in rosters:text+=f"|{r['source_order']}|"+', '.join(x['name']for x in r['roster'])+f"|${r['salary']:,.0f}|{r['baseline_mean']:.3f}|\n"
text+='''
The first control combines Stafford/Puka/Kyren with Michael Wilson: its path needs productive Rams passing plus Kyren production and enough Arizona response for Wilson, with cheap Otton/Tate supporting the salary allocation. A Rams drive-efficiency failure still hurts several shared players. Controls2–4 change QB or primary scenario, but retain Puka/Kyren; changing evidence labels cannot manufacture independent success paths. Control5 removes that pair and uses Taylor/Henry with Stafford/Higbee; it trades baseline mean for a different RB/secondary-receiver path, but still depends on Rams passing and uncertain cheaper receiving production. These football tradeoffs already existed; no source-sensitive ordinal swap is proof that one wins more often.

## Validation, state and next gate

22focused workload-semantic/scenario-allocation/full-game tests pass. No broad tests or unrelated stale CSV-message assertion changes. Code audit scoped semantic changes against existing broader edits: dual-version validation, unknown versus measured zero, attributed producer precedence, consumer evidence tracing and immutable legacy values remain intact. Existing historical packets are not rewritten. comparison.json retains per-world moments/role groups; analog_mapping.json retains per-state whole-ledger checks and unchanged-roster scores. No target-week actual outcomes loaded or scored.

Next gate: validate role transport against original supported current-team role/source chronology before new generation, and bind any prospective scenario rebuild to the same typed original receipt. A clean v1/v2 source-matched scenario test needs a common original source representation rather than substituting the separately derived Analyst packet. Do not optimize on new raw counts as forecasts or claim selector improvement from this mapping audit. Current backend changes are not claimed loaded in an existing worker.

UI-WEEK-002 remains partial: spacing rule edited and1616px expanded-sidebar proof retained; narrow/collapsed checks and TODO completion remain unfinished. Maintenance window ended; no additional UI maintenance performed here. Prior six isotonic anchor refits in the earlier allocation diagnostic remain disclosed; this task invoked no fitting helper.
'''
(P/'REVIEW.md').write_text(text)
v={'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'tests':{'focused_backend_passed':22,'seconds':2.57},'fits':0,'solves':0,'target_outcomes_loaded':False,'runtime_reloaded':False,'operational_generation':False,'source_parity_initial_guard':'failed as intended; separate source-changing sensitivity disclosed','schema_consumer_bug_fixed':'v2 unsupported-role proxy fallback now abstains; archivedv1 preserved','unfinished_ui':'UI-WEEK-002 partial; no maintenance performed'};(P/'validation.json').write_text(json.dumps(v,indent=2)+'\n')
manifest={'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':{x.name:hashlib.sha256(x.read_bytes()).hexdigest()for x in sorted(P.iterdir())if x.is_file()and x.name!='manifest.json'}};(P/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
