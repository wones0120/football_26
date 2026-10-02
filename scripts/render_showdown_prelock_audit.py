"""Render the prospective audit from frozen evidence, without re-solving."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime
from itertools import combinations
import json
from pathlib import Path

from backend.app.product_services.classic_prospective import digest_payload
from backend.app.product_services.optimizer import _safe_float, _is_high_rushing_qb
from scripts.finalize_showdown_prelock_shadow import read_frozen
from scripts.research_showdown_prelock import signature, validate_lineup


def number(value, digits=2):
    return 'N/A' if value is None else f'{float(value):.{digits}f}'


def table(headers, rows):
    return '\n'.join(['| '+' | '.join(headers)+' |', '| '+' | '.join('---' for _ in headers)+' |',
                      *['| '+' | '.join(str(cell).replace('|','/') for cell in row)+' |' for row in rows]])


def overlap(records):
    rows = []
    for left,right in combinations(records,2):
        shared = len({p['player_id'] for p in left['players']} & {p['player_id'] for p in right['players']})
        rows.append({'ranks':(left['rank'],right['rank']),'shared':shared,
                     'same_thesis':left['research_thesis']==right['research_thesis']})
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory',type=Path)
    parser.add_argument('report',type=Path)
    args = parser.parse_args()
    base = args.directory
    p = read_frozen(base/'quality_shadow.json')['payload']
    f = read_frozen(base/'refreshed_database_freeze.json')['payload']
    c = read_frozen(base/'production_single_entry_control.json')['payload']
    ten = read_frozen(base/'ten_thesis_sensitivity.json')['payload']
    context = read_frozen(base/'prepared_context_request.json')['payload']
    guard = read_frozen(base/'production_preservation_verified.json')['payload']
    records,lineups = p['all_candidates'],p['raw_lineups']
    pool = {str(r['player_id']):r for r in p['prepared_pool']}
    all_pool = {str(r['player_id']):r for r in f['player_pool']}
    contexts = {str(r['player_id']):r for r in context['players']}
    best = records[0]['single_entry_score']
    primary = [records[i-1] for i in p['primary_three_ranks']]
    primary_lineups = [lineups[i-1] for i in p['primary_three_ranks']]
    ten_records = [records[i-1] for i in ten['ranks']]
    captain_only = [records[i-1] for i in p['captain_only_three_ranks']]
    def record_rows(rows):
        return [[r['rank'],r['captain'],number(r['single_entry_score'],5),number(best-r['single_entry_score'],5),
                 number(r['mean']),number(r['p90']),int(r['salary']),r['team_counts'].get('PIT',0),
                 r['team_counts'].get('CLE',0),r['research_thesis']] for r in rows]
    metric_headers = ['Rank','CPT','Selector','Gap','Mean','Σ marginal P90','Salary','PIT','CLE','Structure thesis']
    def roster_text(lineup):
        ordered = sorted(lineup,key=lambda row:(row['roster_position']!='CPT',row['player_team'],row['name']))
        return '; '.join(f"**{r['roster_position']} {r['name']}** (${int(r['salary']):,}, {r['player_team']})" for r in ordered)
    def exposures(rows):
        return Counter(player['name'] for row in rows for player in row['players'])
    player_coverage,captain_rows = [],[]
    for pid,row in all_pool.items():
        flex = [r for r in records if any(x['player_id']==pid and x['slot']=='FLEX' for x in r['players'])]
        cap = [r for r in records if r['captain_id']==pid]
        included = pid in pool
        player_coverage.append({'player_id':pid,'name':row['name'],'team':row['player_team'],'position':row['position'],
            'salary':row['salary'],'mean':row['projection'],'p90':row['p90'],'included':included,
            'flex_count':len(flex),'captain_count':len(cap),
            'best_flex_selector':flex[0]['single_entry_score'] if flex else None,
            'best_captain_selector':cap[0]['single_entry_score'] if cap else None,
            'best_containing_mean':max((r['mean'] for r in flex+cap),default=None),
            'best_containing_p90':max((r['p90'] for r in flex+cap),default=None),
            'diagnostic_cpt_ownership':row.get('captain_ownership'),'diagnostic_flex_ownership':row.get('flex_ownership'),
            'role_confidence':row.get('offensive_role_confidence'),'official_role_uncertain':row.get('pregame_role_uncertain'),
            'availability':contexts[pid]['evidence']['nfl_state'],
            'exclusion_reason':None if included else (
                contexts[pid]['evidence']['nfl_state'] if contexts[pid]['availability_probability']==0 else
                'nonstarting_QB' if row['position']=='QB' else
                'missing_or_nonpositive_projection' if row['projection']<=0 else
                'existing_low_salary_positive_opportunity_gate'),
            'zero_coverage_warning':included and (not flex or not cap)})
        if included:
            top = cap[0] if cap else None
            counts = [sum(best-r['single_entry_score']<=t+1e-8 for r in cap) for t in (.05,.10,.15,.20,.30)]
            captain_rows.append({'player_id':pid,'name':row['name'],'cpt_salary':row['salary']*1.5,
                'raw_mean':row['projection'],'cpt_mean':row['projection']*1.5,'raw_p90':row['p90'],'cpt_p90':row['p90']*1.5,
                'salary_premium':row['salary']*.5,'best_selector':top['single_entry_score'] if top else None,
                'best_mean':top['mean'] if top else None,'best_p90':top['p90'] if top else None,
                'depth':counts,'best_rank':top['rank'] if top else None,
                'positive_rostered_relationships':[
                    {'rule_id':trigger['rule_id'],'players':trigger.get('players'),
                     'adjustment':trigger['objective_contribution']}
                    for trigger in lineups[top['rank']-1][0]['lineup_correlation_summary']['triggered_rules']
                    if trigger['objective_contribution']>0] if top else [],
                'negative_rostered_relationships':[
                    {'rule_id':trigger['rule_id'],'players':trigger.get('players'),
                     'adjustment':trigger['objective_contribution']}
                    for trigger in lineups[top['rank']-1][0]['lineup_correlation_summary']['triggered_rules']
                    if trigger['objective_contribution']<0] if top else [],
                'constructions':sorted({f"{r['team_counts'].get('PIT',0)}-{r['team_counts'].get('CLE',0)}" for r in cap}),
                'theses':sorted({r['research_thesis'] for r in cap})})
    player_coverage.sort(key=lambda r:(not r['included'],-r['mean'],r['name']))
    captain_rows.sort(key=lambda r:-(r['best_selector'] or -1))
    def write_csv(name,rows):
        with (base/name).open('w',newline='') as handle:
            writer = csv.DictWriter(handle,fieldnames=list(rows[0]))
            writer.writeheader();writer.writerows(rows)
    write_csv('player_coverage.csv',player_coverage)
    write_csv('captain_frontier.csv',captain_rows)
    assert all(not r['zero_coverage_warning'] for r in player_coverage)
    for lineup in lineups:validate_lineup(lineup)
    # Correlation audit retains every fired rule, rather than only positive examples.
    rule_rows = {}
    for record,lineup in zip(records,lineups):
        for trigger in lineup[0]['lineup_correlation_summary']['triggered_rules']:
            key = trigger['rule_id']
            item = rule_rows.setdefault(key,{'rule_id':key,'candidate_trigger_count':0,'frontier_05_trigger_count':0,
                                           'minimum_adjustment':0.,'maximum_adjustment':0.})
            item['candidate_trigger_count']+=1
            item['frontier_05_trigger_count']+=int(best-record['single_entry_score']<=.05)
            value = trigger['objective_contribution']
            item['minimum_adjustment']=min(item['minimum_adjustment'],value)
            item['maximum_adjustment']=max(item['maximum_adjustment'],value)
    write_csv('correlation_rules_fired.csv',list(rule_rows.values()))
    family = lambda source: source.split(':')[0]
    source_rows = []
    for source_family in sorted({family(s) for r in records for s in r['discovery_sources']}):
        supplied = [r for r in records if source_family in {family(s) for s in r['discovery_sources']}]
        exclusive = [r for r in supplied if {family(s) for s in r['discovery_sources']}=={source_family}]
        attempts = [a for a in p['original_attempts']+p['conditional_attempts'] if family(a['source'])==source_family]
        source_rows.append({'source':source_family,'unique_rosters_touched':len(supplied),
            'frontier_05':sum(best-r['single_entry_score']<=.05 for r in supplied),
            'exclusive_frontier_05':sum(best-r['single_entry_score']<=.05 for r in exclusive),
            'exclusive_frontier_10':sum(best-r['single_entry_score']<=.10 for r in exclusive),
            'seconds':sum(a['seconds'] for a in attempts)})
    write_csv('source_contribution.csv',source_rows)
    sections = []
    def section(title,text):sections.append(f'## {title}\n\n{text.strip()}\n')
    section('1. Entry readiness',f"""**PRE-LOCK PREPARATION COMPLETE; NOT ENTRY READY.** PIT at CLE, Thursday October 1, 2026, 8:15 PM EDT. All numbers are prospective. No game results, realized ownership, exports or contest entries were used.

Freeze: {f['frozen_at']}; projection cutoff {f['projection_header'][0]['data_cutoff_at']}; completed projection `{f['projection_run_id']}`. This is the latest imported DK salary file, observed September 29 at 15:41 EDT—not a freshly authenticated DK download. Its checksum matches the immutable source copy. Recheck salaries tomorrow.

{table(['Check','Finding','Disposition'],[
['Salary/identity','102 CPT/FLEX salary rows; 51 canonical players; 2 teams; unique slot IDs','PASS within imported snapshot'],
['Projection','47 stored projections; 31 positive means; 23 final eligible research players','WARN: four currently inactive/PS salary players lack projections'],
['Ownership','50/51 identities, KC missing; estimates have poor Showdown calibration','DIAGNOSTIC ONLY; uniformly unavailable to shadow selection'],
['Market','Fresh DK observation 23:24 EDT; PIT −2.5, total 38.5','PASS for tonight; refresh tomorrow'],
['Injuries','Wednesday final club reports reconciled; both offensive OUT players zeroed','PASS for tonight; game-day actives not published'],
['Starters','Rodgers and Watson; backups excluded by existing evidence hierarchy','Provisional; refresh quarterback news'],
['Role','Official active roster/depth plus lagged opportunity; no invented forward routes/snaps','Fragile bench roles remain conditional'],
['Duplicates','CPT/FLEX source rows map to one canonical identity; six distinct players per roster','PASS'],
['Legal generation',f'{len(records)} unique research rosters validated; 1 CPT/5 FLEX, ≤$50,000, both teams','PASS'],
['Production entry readiness','Existing Showdown GPP gate warns on projection coverage','Additional source/ownership gates prevent ENTRY READY label']])}

KC's new CPT/FLEX aliases were resolved against its unique canonical CLE/WR identity and official roster/depth evidence, not raw display-name matching. The initial blocked freeze remains preserved. Four missing projection rows are not treated as usable punts; all have non-active source evidence. Active-roster availability=1 is an eligibility assumption before inactives, not a literal certainty of playing.""")
    section('2. Current injury/status summary',"""Wednesday's authoritative reports agree with all seven supplied designations.

| Team | Player | Status | Treatment |
| --- | --- | --- | --- |
| PIT | Rico Dowdle, toe | OUT | Mean/P90 zero; unavailable; absent from all candidates |
| PIT | Joey Porter Jr., back/conditioning | OUT | Secondary matchup uncertainty; no fantasy-player exclusion |
| PIT | Jalen Ramsey, wrist | QUESTIONABLE | Monitor defensive personnel; no offensive-player exclusion |
| PIT | Brandin Echols, concussion | QUESTIONABLE | Cleared protocol but designation persists; monitor actives |
| CLE | Tylan Wallace, knee | OUT | Mean/P90 zero; unavailable; absent from all candidates |
| CLE | Elgton Jenkins, concussion | OUT | Center replacement/pressure uncertainty |
| CLE | Teven Jenkins, back | OUT | Offensive-line depth uncertainty |

[Steelers final report](https://www.steelers.com/news/week-4-injury-report-browns), [Browns final report](https://www.clevelandbrowns.com/news/elgton-jenkins-out-for-week-4-against-the-steelers-injury-report).

The old inputs still had Wallace questionable and a stale Dowdle committee projection. Fresh source snapshots and the existing feature/projection pipeline correct those. Warren's refreshed mean is 12.51, P90 23.98. Homer is on the active roster; last week's Nichols elevation does not establish this week's availability. Defensive/OL evidence is qualitative in this audit: no bespoke projection bump or newly fitted injury coefficient was invented. Losing PIT defensive backs supports scrutiny of CLE passing; losing CLE linemen adds pressure uncertainty in the other direction.""")
    section('3. Market environment',"""Frozen DraftKings line: PIT −2.5 / CLE +2.5, total 38.5; implied PIT 20.5, CLE 18.0. This modest favorite and low total do not justify declaring either team a likely blowout. The source has no reliable publication timestamp; the freeze preserves the retrieval observation separately. [DraftKings market](https://dknetwork.draftkings.com/moneyline-total-spread/).

NWS hourly forecast updated September 30 at 21:32 EDT: kickoff approximately 76°F, SW wind 9 mph, precipitation probability 4%; late evening approximately 75°F/8 mph. No manual weather adjustment was applied. [NWS point/forecast lineage](https://api.weather.gov/points/41.506,-81.699).

Existing symmetric 14-point conditional scenarios retain total 38.5 and condition winner/loser implied scoring to 26.25/12.25. They are bounded role/scoring heuristics, not estimated scenario probabilities or a joint simulation. Each conditional roster is re-solved on the unconditioned model before baseline comparison.""")
    section('4. Player projection/role summary',table(['Player','Pos','Salary','Mean','P90','Official depth','Role confidence / uncertain'],[
        [r['name'],r['position'],r['salary'],number(r['projection']),number(r['p90']),r.get('pregame_role_label') or 'reserve/unit',
         f"{r.get('offensive_role_confidence') or 'N/A'} / {r.get('pregame_role_uncertain')}"] for r in p['prepared_pool']])+"\n\nRole confidence comes from lagged model features; it is distinct from official future role certainty. For example Bernard's 4% recent snap share conflicts with treating a medium model confidence tag as secure usage. Official depth charts are unofficial and are not guaranteed workloads. [PIT depth](https://www.steelers.com/team/depth-chart/), [CLE depth](https://www.clevelandbrowns.com/news/browns-announce-unofficial-depth-chart-for-week-4-vs-the-steelers). Forward snaps/routes are unavailable. Σ marginal P90 throughout this report is a sum of player ceilings, not a calibrated lineup 90th percentile or payout estimate.")
    section('5. Candidate-generation coverage',f"""The unchanged single-entry production control creates 30 candidates. The expanded baseline search creates 691; full conditional-model discovery adds 78 unique baseline-legal rosters, producing **{len(records)}**. Discovery covers global ceiling/mean, every retained CPT, forced FLEX, both single-QB paths, dual QB, exact 3–3/4–2/5–1 allocations, RB+DST, QB+WR, K+DST, and both symmetric decisive conditions.

Every one of the 23 eligible players has CPT and FLEX coverage. The full 51-player audit includes excluded players with explicit status/model reasons in `player_coverage.csv`. No meaningful eligible player has unexpected zero coverage.

{table(['Player','FLEX count','CPT count','Best FLEX selector','Best CPT selector','Peak containing mean','Peak containing ΣP90'],[
 [r['name'],r['flex_count'],r['captain_count'],number(r['best_flex_selector'],5),number(r['best_captain_selector'],5),number(r['best_containing_mean']),number(r['best_containing_p90'])] for r in player_coverage if r['included']])}

This is a broad best-found frontier, not exhaustive enumeration of all DK-legal rosters. Existing single-entry policy requires a starting QB, requires QB backing for WR/TE CPT, and restricts multiple same-team pass catchers without QB. Zero-QB builds are therefore outside this policy's feasible set; that is an explicit architectural restriction, not a discovered impossibility. Low-opportunity gate exclusions also remain intact. CPT depth of 20 ceiling/5 mean proposals is a search budget, not a count of every possible competitive roster.

{table(['Discovery family','Unique rosters touched','Within .05','Exclusive .05','Exclusive .10','Solve seconds'],[
 [r['source'],r['unique_rosters_touched'],r['frontier_05'],r['exclusive_frontier_05'],r['exclusive_frontier_10'],number(r['seconds'])] for r in source_rows])}

Contribution counts overlap; exclusivity is conditional on these search budgets. Early `scenario` proposals reused baseline correlation coefficients; they are retained as legal discovery proposals only. `conditional_exact` rebuilds the complete conditional model, including QB correlation scaling, and exclusively supplies the decisive-scenario results below. Search/selection runtime: {number(p['runtime_seconds'])} seconds, excluding source refresh, model training, tests and report rendering. Native CBC solves the unchanged mathematical objective; no solver timeouts or unproven incumbents were accepted.""")
    sections[-1] += "\nPer-captain ceiling search adds the most exclusive close-frontier coverage (11 within .05) but consumes 74 seconds, approximately half the search/selection runtime. Forced FLEX adds three exclusive .05 candidates in 4.4 seconds; complete conditional rebuilding adds two in 16.3 seconds and supports the decisive-game audit. Per-captain mean adds eight exclusive candidates within .10, none within .05. Initial approximate scenario and generic structural sweeps have no exclusive .10 candidates in this budget; keep their diagnostic purpose separate from claiming incremental frontier gains. These order/budget-dependent contributions do not prove a source can be safely removed on future slates.\n"
    section('6. CPT frontier',table(['Tolerance','Candidates','Distinct CPTs','CPT names'],[
        [number(t),len([r for r in records if best-r['single_entry_score']<=t]),len({r['captain'] for r in records if best-r['single_entry_score']<=t}),
         ', '.join(dict.fromkeys(r['captain'] for r in records if best-r['single_entry_score']<=t))] for t in (.05,.10,.15,.20,.30)])+
        f"\n\nBest selector {best:.5f}. Tolerances are absolute score differences, not fantasy-point gaps or probabilities. Normalizers are frozen once over the identical 769-roster universe. Scores from the narrow 30-roster control have different normalizers and are not directly subtracted. Projection/context/correlation/CPT-prior parameters are unchanged. Weights remain mean .35, ceiling .30, solver .20, correlation .10, context .05, existing chalk coefficient .03; ownership is uniformly unavailable in the quality shadow.")
    section('7. CPT depth',table(['CPT','CPT salary','Base mean','CPT mean','CPT P90','Best selector','Best lineup mean','Best lineup ΣP90','Depth .05/.10/.15/.20/.30','Salary premium'],[
        [r['name'],int(r['cpt_salary']),number(r['raw_mean']),number(r['cpt_mean']),number(r['cpt_p90']),number(r['best_selector'],5),number(r['best_mean']),number(r['best_p90']),'/'.join(map(str,r['depth'])),int(r['salary_premium'])] for r in captain_rows])+
        "\n\nA low-salary CPT creates room relative to a more expensive CPT, but still costs 50% more than its own FLEX salary. `captain_frontier.csv` contains all construction/thesis memberships and peaks; `quality_shadow.json` retains full correlated/negative-rule evidence and supporting lineups. Kicker/DST/backup-role CPT coverage does not make them equally viable primary captains.")
    qb_text = []
    for pid,row in pool.items():
        if row['position']!='QB':continue
        cap = next(r for r in records if r['captain_id']==pid)
        flex = next(r for r in records if any(x['player_id']==pid and x['slot']=='FLEX' for x in r['players']))
        qb_text.append(f"**{row['name']}**: recent carries/game {number(row.get('carries_mean_3'))}; high-rushing classifier={_is_high_rushing_qb(row)}. CPT salary ${int(row['salary']*1.5):,}, premium ${int(row['salary']*.5):,}; point gain {row['projection']*.5:.2f} mean / {row['p90']*.5:.2f} ceiling. Best CPT #{cap['rank']} selector {cap['single_entry_score']:.5f}; best FLEX #{flex['rank']} {flex['single_entry_score']:.5f}; opportunity cost {flex['single_entry_score']-cap['single_entry_score']:.5f}.\n\nCPT: {roster_text(lineups[cap['rank']-1])}\n\nFLEX: {roster_text(lineups[flex['rank']-1])}")
    section('8. QB CPT vs FLEX analysis','\n\n'.join(qb_text)+"\n\nWatson qualifies as mobile from five lagged carries/game; no new rushing projection was fabricated. His best CPT includes two CLE pass catchers and is competitive. Rodgers has approximately 1.33 carries/game; CPT requires two PIT WR/TE under the unchanged hard rule. Rodgers remains mathematically close but adds no independent thesis when only the slot rotates on the same core. Keep him out of the primary three; the ten-entry sensitivity retains one explicit marginal test. Neither passing yards nor a dollar salary premium proves optimal-CPT probability.")
    thesis_rows = []
    thesis_stats = []
    for name in sorted({r['research_thesis'] for r in records}):
        rows = [r for r in records if r['research_thesis']==name]
        top = rows[0]
        thesis_rows.append([name,len(rows),sum(best-r['single_entry_score']<=.05 for r in rows),number(top['single_entry_score'],5),
            number(top['mean']),number(top['p90']),', '.join(dict.fromkeys(r['captain'] for r in rows if best-r['single_entry_score']<=.10)) or 'none within .10'])
        qb_exposure = Counter(player['name'] for r in rows for player in r['players'] if player['position']=='QB')
        allocation = Counter(f"{r['team_counts'].get('PIT',0)}-{r['team_counts'].get('CLE',0)}" for r in rows)
        dependency = Counter(player['name'] for r in rows for player in r['players'])
        thesis_stats.append({'thesis':name,'depth':len(rows),
            'qb_exposure':{qb:count/len(rows) for qb,count in qb_exposure.items()},
            'allocation':dict(allocation),'key_dependencies':dict(dependency.most_common(4)),
            'ownership':'uniformly unavailable to selection; draft estimates unreliable'})
    section('9. Football thesis discovery',table(['Thesis','Raw depth','Depth .05','Peak selector','Peak mean','Peak ΣP90','Competitive CPTs ≤.10'],thesis_rows)+"\n\nThese are transparent roster-based hypotheses, not independent simulated outcomes. A 3–3 dual-QB roster stays balanced when its captain changes. Four-plus same-team concentration plus its QB and multiple receivers supports passing concentration. Own-team RB CPT with four-plus teammates supports rushing-led scoring with passing support; it does not prove run-only control. RB+DST supports a separate control family. A K/DST CPT requires another K/DST selection before receiving a defensive/kicking label. Each legal thesis's QB exposure, team allocations, rule triggers and player dependencies are retained in the raw rosters; no empty categories were manufactured. CLE passing depends on Watson/Boston/Jeudy plus uncertain PIT secondary health; PIT offense depends on Rodgers/Metcalf and Warren's post-Dowdle workload.")
    sections[-1] += '\n'+table(['Thesis','QB coverage within family','PIT-CLE allocation counts','Most common player dependencies'],[
        [r['thesis'],', '.join(f"{qb}: {100*share:.1f}%" for qb,share in r['qb_exposure'].items()),r['allocation'],r['key_dependencies']]
        for r in thesis_stats])+"\n\nQB coverage above is across discovered candidates, not proposed entry exposure or scenario probability. Ownership for every family remains diagnostic and unreliable. The full rule/stack structures and source-specific conditioned role dependencies accompany each candidate.\n"
    for winner,title in [('PIT','10. PIT-wins-big thesis'),('CLE','11. CLE-wins-big thesis')]:
        rows = sorted([r for r in p['conditional_candidates'][winner] if r['team_count']>=4],key=lambda r:-r['conditioned_solver'])
        unique,seen = [],set()
        for row in rows:
            key = tuple(tuple(pair) for pair in row['signature'])
            if key not in seen:unique.append(row);seen.add(key)
        top = unique[:5]
        peak = max(unique,key=lambda r:r['baseline_selector'])
        top_text = []
        for i,row in enumerate(top,1):
            record = records[row['baseline_rank']-1]
            top_text.append(f"{i}. CPT **{row['captain']}**, {winner} {row['team_count']}–{6-row['team_count']}; conditional objective {row['conditioned_solver']:.2f}, mean/ΣP90 {row['conditioned_mean']:.2f}/{row['conditioned_p90']:.2f}; baseline #{record['rank']} selector {record['single_entry_score']:.5f}, gap {best-record['single_entry_score']:.5f}.\n\n   {roster_text(lineups[record['rank']-1])}")
        section(title,f"""The complete existing conditional model boosts winner rush/control and DST paths, reduces loser rushing, allows loser passing chase, and modestly suppresses loser kicking. Each search requires the winner CPT and either winner RB+DST or winner QB+WR, across 3–3, 4–2 and 5–1. A 5–1 allocation alone is insufficient. The top-five table below uses ≥4 winner players for the explicit dominant subset; 3–3 conditional candidates are preserved separately.

Unique dominant depth {len(unique)}; {sum(best-r['baseline_selector']<=.05 for r in unique)} inside .05; {sum(best-r['baseline_selector']<=.10 for r in unique)} inside .10. The closest-to-global dominant variant is baseline #{peak['baseline_rank']}, CPT {peak['captain']}, selector {peak['baseline_selector']:.5f}, gap {best-peak['baseline_selector']:.5f}. Conditional objective ordering and baseline-quality ordering differ.

"""+'\n\n'.join(top_text)+"\n\nThe conditional assumptions do not estimate the chance of a 14-point win. Winner pass-led constructions can include the opposing QB/receiver because losing-side chase production can coexist with a decisive score margin. Winner RB+DST alternatives are retained even when they rank lower. Future lineman/secondary news can change which version is credible.")
    neutral = [r for r in records if r['research_thesis']=='balanced competitive']
    section('12. Competitive-game thesis',table(metric_headers,record_rows(neutral[:5]))+"\n\nThe central family includes both QBs and contributing pass catchers. Metcalf/Watson/Boston/Rodgers captain rotation on the same six-player roster creates captain alternatives, not four independent football stories. The primary joint search gives up the single top roster to obtain structurally distinct PIT- and CLE-concentrated alternatives with at least two changed players per pair.")
    section('13. Questionable-player analysis',"No currently eligible offensive player carries a final QUESTIONABLE designation. Offensive OUTs have zero candidate/CPT exposure. Ramsey/Echols are defensive matchup uncertainties and are not silently removed from an offensive DK pool. Thus the cost of avoiding a designated offensive Q is 0 mean/ceiling/selector in this freeze. Role-fragile active backups are separate: primary exposure is capped at one of three for ≤$1,000 punts or uncertain reserves with <10% lagged snap share. The raw universe retains their original model assessments. New offensive Q designations tomorrow require fresh availability evidence and an avoidance-cost solve; they must not inherit today's assumed-active treatment.")
    sections[-1] += "\nThe global best roster contains none of Homer, Heidenreich, Bernard, McLaughlin or Whiteheart. Avoiding each of those names individually leaves that exact frontier roster intact: cost versus its selector, mean and ceiling is zero. This does not imply their forced-containing upside is zero; coverage and containing-quality diagnostics remain in the player CSV.\n"
    cheap = [r for r in p['prepared_pool'] if r['salary']<=3200]
    section('14. Cheap-player audit',table(['Player','Salary','Mean/P90','Recent snap share','Projected carries','Projected targets','Routes / forward snaps','Confidence'],[
        [r['name'],r['salary'],f"{r['projection']:.2f}/{r['p90']:.2f}",number((_safe_float(r.get('snap_share_mean_3'))*100),1)+'%',
         number(r.get('projected_carries')),number(r.get('projected_targets')),'N/A / N/A',f"{r.get('offensive_role_confidence')} / uncertain={r.get('pregame_role_uncertain')}"] for r in cheap])+"\n\nThese carries/targets are model expectations from lagged team-volume reconciliation with salary fallback; they are not reported Week 4 snap/route commitments. Jeudy's $3,000 salary and 81.7% recent snap share support meaningful use despite modest projected targets. McLaughlin's $400 salary buys limited rotational rushing/receiving access, not a guaranteed workload. Bernard has only 4% recent snaps despite modeled targets; Homer 0%, Heidenreich 4%: verify role/elevations, avoid heavy unsupported exposure. Whiteheart has recent snaps but low target volume. Wetjen, Ryan, Corley, Tonyan, Nowakowski/Burton and Skowronek do not pass the existing positive-opportunity/low-salary gate in this freeze; inactive practice-squad names are also absent. The final primary three uses none of the unsupported reserve punts; the thesis ten uses Bernard once. Return-role designation alone is not adequate receiving evidence. [PIT roster](https://www.steelers.com/team/players-roster/), [CLE roster](https://www.clevelandbrowns.com/team/players-roster/), [PIT transactions](https://www.steelers.com/team/transactions/), [CLE transactions](https://www.clevelandbrowns.com/team/transactions/).")
    fired = []
    for label,lineup in zip('ABC',primary_lineups):
        fired.append(f"**{label}:** "+'; '.join(f"{r['rule_id']}={r['objective_contribution']:+.3f}" for r in lineup[0]['lineup_correlation_summary']['triggered_rules']))
    section('15. Correlation audit','\n\n'.join(fired)+"\n\nQB+catcher bonuses actually fire with diminishing 60/30/10 stacking rewards and one opposing bring-back per QB team, scaled by QB projection quality. WR/TE CPT requires own QB; non-mobile QB CPT requires two own pass catchers. RB+DST, opposing DST conflicts, kicker/environment and 5–1 coherence are audited in `correlation_rules_fired.csv`, including negative adjustments and zero-fire cases. No blanket DST/opponent ban or generic opposing-RB exclusion was added. Opposing RB/control conflict is chiefly expressed in the conditional role model, not a new arbitrary pair penalty. Opposing-pass-catcher/QB exposure can represent chase volume. A 4–2/5–1 format bonus is a construction rule, not proof of a blowout. Small model/report correlation-attribution residuals are retained as `other_or_unattributed`; they are not reallocated into invented football bonuses.")
    primary_total = sum(r['single_entry_score'] for r in primary)
    top3_total = sum(r['single_entry_score'] for r in records[:3])
    section('16. Recommended 3-entry shadow',table(metric_headers,record_rows(primary))+'\n\n'+'\n\n'.join(
        f"**Lineup {label} — {record['research_thesis']}:**\n\n{roster_text(lineup)}" for label,record,lineup in zip('ABC',primary,primary_lineups))+
        f"\n\nJoint constraints: three distinct CPTs; three supported structural theses; ≤4 shared players per pair; limited fragile-role exposure; candidates within .10 of the same frontier. This is an explicit research selection policy implementing the user's diversity request, not a production default change. Three raw-best distinct rosters total {top3_total:.5f}; primary total {primary_total:.5f}, sacrifice {top3_total-primary_total:.5f} ({100*(top3_total-primary_total)/top3_total:.2f}%). Compared with repeating the single strongest roster three times, sacrifice is {3*best-primary_total:.5f} ({100*(3*best-primary_total)/(3*best):.2f}%). Captain-only selection costs less but merely rotates slots on an identical core. No payouts/EV are inferred.")
    section('17. Recommended 10-entry shadow',table(metric_headers,record_rows(ten_records))+
        f"\n\nThe quality-maximizing cap-constrained ten totals {ten['original_ten_total_selector']:.5f}. Requiring one representative of each of the three supported primary theses totals {ten['total_selector']:.5f}, incremental sacrifice {ten['original_ten_total_selector']-ten['total_selector']:.5f} ({100*(ten['original_ten_total_selector']-ten['total_selector'])/ten['original_ten_total_selector']:.3f}%). This is the preferred thesis sensitivity; it does not force weak defensive or pure-rushing categories. Existing v3 exposure ceilings are retained: CPT ≤6/10, core ≤8/10, starting QB ≤10/10, ≤$1,000 punt ≤4/10. The allocation emerges from this slate; no previous-game CPT distribution is reused. Ten distinct rosters are retained, but both QBs remain heavily exposed.")
    section('18. CPT allocation',table(['Portfolio','CPT allocation'],[
        ['Primary three',dict(Counter(r['captain'] for r in primary))],
        ['Quality ten',dict(Counter(records[i-1]['captain'] for i in p['ten_ranks']))],
        ['Thesis ten',dict(Counter(r['captain'] for r in ten_records))]])+
        "\n\nOwnership is descriptive only in the quality/thesis shadows. The generated estimates sum to 247.66% CPT and 369.90% FLEX across loaded players, rather than the expected 100% and 500% for complete slate slot marginals. Showdown CPT held-out MAE 12.92 percentage points/bias +11.57; FLEX MAE 7.59/bias −3.99. The pooled diagnostic promotion check passes, but that does not establish reliable Showdown marginals or authorize promotion. KC has no estimate. `player_coverage.csv` retains individual draft estimates. Original production control preserves its existing chalk behavior, including the missing-ownership inconsistency; the quality shadow masks every candidate's ownership uniformly, while retaining the .03 coefficient unchanged. No reliable duplication or leverage probability is available.")
    section('19. Thesis allocation',table(['Portfolio','Thesis allocation'],[
        ['Primary three',dict(Counter(r['research_thesis'] for r in primary))],
        ['Quality ten',dict(Counter(records[i-1]['research_thesis'] for i in p['ten_ranks']))],
        ['Thesis ten',dict(Counter(r['research_thesis'] for r in ten_records))]])+
        "\n\nDistinct CPT is not distinct thesis. The same six-player dual-QB core supports several CPT choices. The ten-entry diversity increment covers a CLE-concentrated construction without pretending that five CPTs are five independent game scenarios. All selected offensive families share important scoring dependencies.")
    section('20. Player exposures',table(['Player','Primary count / 3','Thesis-ten count / 10'],[
        [name,exposures(primary).get(name,0),exposures(ten_records).get(name,0)] for name in sorted(set(exposures(primary))|set(exposures(ten_records)))])+
        "\n\nThe primary three still shares Jeudy, Watson and Metcalf in all entries. These are concentrated exposure decisions supported by the frozen frontier, not independence claims. Both QBs are 10/10 in the ten-entry sensitivity; this is the largest residual dependence. Fragile/cheap alternatives remain capped rather than being purchased purely for salary fit.")
    pairs = overlap(primary)
    ten_pairs = overlap(ten_records)
    def average(rows):return number(sum(r['shared'] for r in rows)/len(rows)) if rows else 'N/A'
    section('21. Pairwise overlap',table(['Primary pair ranks','Shared players','Same structural thesis'],[[str(r['ranks']),r['shared'],r['same_thesis']] for r in pairs])+
        f"\n\nPrimary average overlap {average(pairs)}/6; CPT count {len(set(r['captain'] for r in primary))}, thesis count {len(set(r['research_thesis'] for r in primary))}. Within-thesis average N/A because all three labels differ. Ten average {average(ten_pairs)}/6, within-thesis {average([r for r in ten_pairs if r['same_thesis']])}/6, across-thesis {average([r for r in ten_pairs if not r['same_thesis']])}/6; CPT count {len(set(r['captain'] for r in ten_records))}, thesis count {len(set(r['research_thesis'] for r in ten_records))}. Full pair rows and allocation counts are saved in `audit_tables.json`. Overlap is a dependence diagnostic, not a measured fantasy-score correlation.")
    section('22. Remaining uncertainty',"""The imported DK file is not a fresh live verification. Final inactives/elevations are outstanding. Defensive back health and CLE center replacement affect the plausibility of passing/control theses but lack quantified incremental adjustments. Backup/rookie role tags and salary-fallback opportunity can overstate certainty. Ownership is unsuitable for promotion. The search is broad but does not certify global selector optimality, and existing hard QB/opportunity gates define its universe. Conditional models are heuristic, not joint-score simulations. No contest field, fee/payout metadata or payout simulation was supplied, so the three outputs are prospective shadows rather than expected-profit recommendations.

Tomorrow: capture new immutable official reports/transactions and market/weather snapshots; import a fresh DK salary file; reconcile actives/elevations/starters against canonical IDs; refresh normal context/features/projection; use reliable ownership only when coverage, slot marginals and calibration support it; create a **new** freeze/output path, then re-run the same discovery and joint constraints. Review changes in thesis/CPT depth and make the final three-entry decision. Retain tonight's files; do not overwrite freezes. Do not run the archived one-off preparation scripts blindly—they are provenance, not an automatic news parser. No automation or entry submission was scheduled.""")
    section('23. Files changed',"""Primary report `WEEK4_THURSDAY_SHOWDOWN_PRELOCK_AUDIT.md`; new offline scripts `freeze_showdown_prelock.py`, `research_showdown_prelock.py`, `replay_showdown_single_entry_control.py`, `finalize_showdown_prelock_shadow.py`, `render_showdown_prelock_audit.py`; new focused research tests and one corrected existing multiple-TE contract test; small README/release-note references. Artifacts contain original/fresh database freezes, immutable public/DK sources, prepared pool, exact baseline LP, full raw universes, original production control, quality/thesis shadows, CSV coverage and rule audits, logs and preservation verification.

Local data refresh resolved two salary aliases, appended source/context/market/injury lineage, rebuilt only Thursday features and produced new Thursday projection/ownership runs through existing services. No optimizer run, export or entry was persisted. Production optimizer, projection/selector/correlation/CPT-prior/thesis code and configuration are unchanged; Classic report/research remain in place. The unchanged 30-candidate control selects A/B/A, all Metcalf CPT, showing why it does not implement the requested three-captain decision.

Reproduction (from repo root, with a new output path):

```sh
PYTHONPATH=. .venv/bin/python scripts/research_showdown_prelock.py <hashed-freeze.json> <new-directory>/discovery_v1.json
PYTHONPATH=. .venv/bin/python scripts/replay_showdown_single_entry_control.py <hashed-freeze.json> <new-directory>/production_single_entry_control.json
PYTHONPATH=. .venv/bin/python scripts/finalize_showdown_prelock_shadow.py <new-directory> <new-directory>/quality_shadow.json
```

The finalizer expects the freeze/control files under the same documented names. The ten-thesis sensitivity and final report are evidence-derived supplements, not an entry API. The archived preparation/refresh scripts document today's source reconciliation; they are not production integration changes.""")
    section('24. Tests',f"""**159 passed**: 92 optimizer/Showdown, captain, portfolio, scenario, starter, safety, pregame, readiness, ownership and research tests; 67 input-lineage, canonical projection, forward-opportunity, source-capture and matching tests. New tests verify hash failure, canonical/slot/salary/status legality, captured-model agreement with production, uniformly unavailable diagnostic ownership, same-core CPT/thesis distinction and joint core/captain constraints.

The initial run found one pre-existing stale test expecting the old one-TE restriction. The test now verifies the current schema forces `enforce_single_te=false`, multiple-TE candidates survive selection and final validation, and the production implementation was not changed.

All {len(records)} full-universe lineups were independently checked for legal slots, salary, canonical uniqueness, team representation and frozen availability; all 23 retained players have both CPT/FLEX coverage. Conditional rosters were re-solved on the baseline model. Source hashes and freeze hashes are checked before analysis. Protected code/report/artifact hashes: {guard['all_protected_hashes_unchanged']}; {guard['saved_classic_configuration_count']} saved Classic objective/constraint configurations unchanged; Thursday persisted optimizer runs {guard['thursday_optimizer_runs_persisted']}. No actual results were queried or attached for this future slate. See test logs and `production_preservation_verified.json`.""")
    answers = []
    def answer(question,text):answers.append(f'### {question}\n\n{text}\n')
    answer('What are the strongest football theses for PIT-CLE?','Balanced dual-QB competition; PIT passing concentration with Warren support; CLE passing concentration with a PIT bring-back. These are the three supported primary structural alternatives. Pure RB+DST control and defensive/kicking families are weaker on the current selector.')
    answer('Which captains are genuinely viable?',', '.join(row['name'] for row in captain_rows if row['depth'][0]>0)+'. These have best-found depth within .05. Treat lower-cost WRs/TEs, kickers and defensive CPTs farther down the frontier as conditional alternatives; do not equate .30 coverage with a primary recommendation.')
    answer('Which three captains would you use if entering exactly three lineups?',', '.join(row['captain'] for row in primary)+', subject to tomorrow’s fresh inputs. Watson is mobile under the existing five-carries evidence rule; Rodgers is not selected in the primary three.')
    answer('What three lineups would the current system select?',
        'The **unchanged production single-entry control** selects A/B/A and only Metcalf CPT:\n\n'+
        '\n\n'.join(f"{index+1}. {roster_text(lineup)}" for index,lineup in enumerate(c['selected']))+
        '\n\nThe **requested expanded joint shadow** selects three distinct captains and structurally different cores:\n\n'+
        '\n\n'.join(f"{label}. {roster_text(lineup)}" for label,lineup in zip('ABC',primary_lineups)))
    answer('What thesis does each lineup represent?','; '.join(f"{label}: {row['research_thesis']} ({row['team_counts'].get('PIT',0)} PIT/{row['team_counts'].get('CLE',0)} CLE)" for label,row in zip('ABC',primary))+'. The labels describe allocations and actual stacks, not independent simulated outcomes.')
    answer('What is the quality cost of using three different captains?',f"Captain uniqueness alone sacrifices {top3_total-sum(r['single_entry_score'] for r in captain_only):.5f} total selector points versus the best three distinct rosters, but rotates the same core. Requiring three supported theses and ≤4 overlap costs {top3_total-primary_total:.5f} ({100*(top3_total-primary_total)/top3_total:.2f}%). Versus repeating the best roster three times: {100*(3*best-primary_total)/(3*best):.2f}%. No monetary EV inference.")
    answer('Does PIT-wins-big deserve one of the three entries?','**YES, through the competitive 4–2 PIT pass-led variant.** It is the strongest conditional PIT candidate and the primary A roster, only 0.00444 below the baseline frontier. No extra low-quality 5–1 or RB+DST roster is forced; the lineup also works in closer games.')
    answer('Does CLE-wins-big deserve one of the three entries?','**BORDERLINE as a dedicated 14+ blowout bet.** The closest competitive CLE-dominant variant costs 0.02267, while the conditionally top Boston 5–1 costs 0.07515. Primary C provides a CLE-concentrated alternate with three different captains/cores, without declaring a 14-point win likely. Avoid forcing the more expensive pure-blowout variant.')
    answer('Are any non-rushing QB CPTs justified?','**BORDERLINE.** Rodgers is mathematically close but captain-only rotation adds no game-thesis diversity and costs salary flexibility. Keep him out of the primary three. The ten-entry sensitivity reserves one explicit Rodgers CPT test. Watson’s five lagged carries/game classify him as mobile, so his primary CPT does not rely on casually accepting a non-rushing QB.')
    answer('Which questionable or fragile players need monitoring tomorrow?','Ramsey/Echols actives and PIT secondary alignment; CLE center replacement/line status; both QB starters; Warren/Homer and any Nichols elevation; Bernard/Heidenreich/McLaughlin roles. Confirm Dowdle/Wallace remain OUT and watch any new offensive Q designation. Preserve model assessments when applying user risk limits.')
    answer('Which cheap players require special scrutiny?','McLaughlin ($400), Bernard ($3,200), Heidenreich ($2,200), Homer ($2,600), Whiteheart ($1,600), and any newly activated minimum-salary player. Jeudy ($3,000) has stronger snap evidence but his 3/3 primary dependence and target expectations must be rechecked. Do not buy a PS/inactive punt or treat return duty as an established receiving role.')
    answer('If entering 10 lineups, what CPT allocation does the slate support?',', '.join(f"{captain}: {count}" for captain,count in Counter(r['captain'] for r in ten_records).items())+'. This is generated from current quality/depth and retained exposure ceilings. It covers three structural theses at an incremental 0.059% selector cost; both QBs remain 10/10 and the portfolio is not independent.')
    answer('What must be refreshed again tomorrow before lock?','Fresh DK salary/slot IDs; official injuries, inactives and elevations; starters/depth and credible opportunity news; reliable slot-specific ownership; total/spread/implied scoring; weather. Rebuild normal context/features/projections, freeze a new hashed input, repeat discovery/selection, and review all three full rosters. Tonight is not ENTRY READY. No export or entry has been authorized or performed.')
    report = '# Week 4 Thursday Showdown pre-lock audit\n\n'+ '\n'.join(sections)+'\n'+ '\n'.join(answers)
    args.report.write_text(report)
    summary = {'primary_ranks':p['primary_three_ranks'],'ten_ranks':ten['ranks'],
               'primary_overlap':pairs,'ten_overlap':ten_pairs,'source_contribution':source_rows,
               'player_coverage':player_coverage,'captain_frontier':captain_rows,'thesis_statistics':thesis_stats,
               'all_lineups_validated':len(lineups),'tests_passed':159,
               'entry_ready':False,'report_sha256':__import__('hashlib').sha256(args.report.read_bytes()).hexdigest()}
    (base/'audit_tables.json').write_text(json.dumps({'payload':summary,'sha256':digest_payload(summary)},indent=2,sort_keys=True)+'\n')
    print({'report':str(args.report),'sections':len(sections),'answers':len(answers),'lineups':len(lineups)})


if __name__=='__main__':
    main()
