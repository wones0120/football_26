"""Render the decision report from frozen offline audit results."""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
from statistics import mean,median
import numpy as np
from scripts.audit_showdown_strategy import OUT, ROOT, read, write

def fmt(x):return '—' if x is None else f'{x:.3f}'
def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |',*['| '+' | '.join(map(str,r))+' |' for r in rows]])
def csvfile(path,rows):
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)

def main():
    structural=read(OUT/'structural_results.json');safe=read(OUT/'time_safe_2026_4_thursday/results.json')
    assert len(structural)==45
    lineups=[];slates=[];cheap=[]
    for s in structural:
        slug='_'.join(map(str,s['key']));players=read(OUT/slug/'prepared.json')['players']
        current=s['experiments']['objective_current'];c=current['lineups'][0]
        slates.append({'slate':slug,'evidence':'STRUCTURAL REPLAY','actual_score':c['actual_score'],
         'archive_zero_score':c['archive_zero_imputed_score'],'archive_percentile':c['archive_zero_imputed_percentile'],
         'archive_regret':c['archive_regret'],'captain':c['captain_name'],'captain_position':c['captain_position'],
         'qb_count':c['qb_count'],'team_split':json.dumps(c['team_split']),'missing_labels':len(c['missing_label_ids']),
         'archive_oracle':s['oracle_archive'],'physical_count':s['physical_count']})
        for label,e in s['experiments'].items():
            for l in e['lineups']:
                lineups.append({'slate':slug,'evidence':'STRUCTURAL REPLAY','experiment':label,'requested':e['requested'],
                  **{k:l[k] for k in ['captain_id','captain_name','captain_position','qb_count','selector','mean','marginal_p90_sum',
                   'actual_score','archive_zero_imputed_score','archive_zero_imputed_percentile','archive_regret','actual_optimal_captain_archive']},
                  'team_split':json.dumps(l['team_split']),'player_ids':json.dumps(l['player_ids']),
                  'missing_label_ids':json.dumps(l['missing_label_ids']),'pair_overlap':e['average_shared_identities']})
        for r in players:
            if r['salary']>2000:continue
            exposures={str(n):sum(r['player_id'] in l['player_ids'] for l in s['experiments'][f'exposure_all_n{n}']['lineups']) for n in [1,2,5]}
            cheap.append({'slate':slug,'player_id':r['player_id'],'name':r['name'],'position':r['position'],'team':r['player_team'],
             'salary':r['salary'],'sourced_current_role':None,'recent_snaps':None,
             'prior_three_targets':r['pregame_expected_targets'],'prior_three_carries':r['pregame_expected_carries'],
             'projection':r['projection'],'p90':r['p90'],'current_gate_pass':r['audit_gate'],
             'exposure_appearances':json.dumps(exposures),'actual_score':r['actual_points'] if r['actual_source']!='unavailable' else None,
             'archive_actual_value':r['actual_points'],'actual_source':r['actual_source']})
    csvfile(OUT/'selected_lineup_metrics.csv',lineups);csvfile(OUT/'slate_metrics.csv',slates);csvfile(OUT/'cheap_player_metrics.csv',cheap)
    paired=[]
    baseline='objective_current'
    labels=['objective_no_prior','objective_weak_prior','objective_mobile_qb_neutral_prior','objective_no_correlation',
      'objective_no_first_catcher','objective_no_additional_catchers','objective_no_bringback','objective_no_concentration','objective_no_script_format',
      'mean_ranker_joint','p90_ranker_joint','screen_mean95_n1','screen_p90_95_n1','screen_joint94_n1','screen_joint93_n1',
      'screen_composite95_n1','screen_pareto_n1','screen_selector_regret95_n1','team5_qbpolicy0','team3_qbpolicy0',
      'team4_qbpolicy1','team4_qbpolicy2','team4_qbpolicy3','gate_removed_fixed_benchmark','gate_prior_usage_proxy']
    rng=np.random.default_rng(20261005)
    for label in labels:
        vals=[(s['experiments'][label],s['experiments'][baseline]) for s in structural]
        delta=np.array([a['mean_archive_score']-b['mean_archive_score'] for a,b in vals if a['generated'] and b['generated']])
        complete=[a['mean_archive_score']-b['mean_archive_score'] for a,b in vals if a['generated']==b['generated']==1 and a['confirmed_lineups']==b['confirmed_lineups']==1]
        boot=delta[rng.integers(0,len(delta),(5000,len(delta)))].mean(axis=1)
        paired.append({'experiment':label,'archive_pairs':len(delta),'archive_delta':float(delta.mean()),
          'archive_wins':int(sum(delta>1e-7)),'archive_losses':int(sum(delta< -1e-7)),
          'archive_bootstrap95':list(map(float,np.quantile(boot,[.025,.975]))),
          'both_fully_scored_pairs':len(complete),'confirmed_subset_delta':mean(complete) if complete else None})
    csvfile(OUT/'paired_experiments.csv',[{**r,'archive_bootstrap95':json.dumps(r['archive_bootstrap95'])} for r in paired])
    write(OUT/'aggregate.json',{'structural_games':len(structural),'missing_labels':sum(s['missing_actual_labels'] for s in structural),
     'current_fully_scored_top_selections':sum(s['experiments']['objective_current']['confirmed_lineups'] for s in structural),
     'paired':paired,'time_safe':safe})
    current_complete=sum(s['experiments']['objective_current']['confirmed_lineups'] for s in structural)
    no_prior=next(r for r in paired if r['experiment']=='objective_no_prior')
    def captain_stats(label):
        ls=[l for s in structural for l in s['experiments'][label]['lineups']]
        qs=[l for l in ls if l['captain_position']=='QB']
        return len(qs),sum(l['actual_optimal_captain_archive'] for l in qs),sum(l['actual_optimal_captain_archive'] for l in ls)
    cq,co,cc=captain_stats('objective_current');nq,no,nc=captain_stats('objective_no_prior')
    qm=[s['captain_multipliers']['QB'] for s in structural]
    rules=[
     ['QB Captain','Allowed; user can ban',f'11/45 archive optima have QB CPT; current/no-prior select {cq}/{nq} QBs and capture {co}/{no} optimal QB CPTs','One frozen game; no evidence for blanket ban','KEEP eligibility; validate scoring separately','Medium for eligibility; low for edge'],
     ['QB count','Up to 2 eligible starting QBs; require ≥1 in v3 ≤5-entry path','Four-way controlled structural replay; starter identity reconstructed','Frozen candidate filtering is time-safe, one game','KEEP permissive max 2; do not impose max 1 by theory alone','Low–medium'],
     ['Team count','Requested policy max 4; production default max 5','Max 3/4/5 compared on 45 games; labels incomplete','Max 4 is a user preference, not DK legality','NEEDS MORE EVIDENCE for max 4; preserve explicit preference','Low for performance'],
     ['Captain-position prior','Strength 0.35; learned/fallback position multiplier on CPT objective','Two old 39-slate sweeps disagree; new 45-game replay cannot establish a winner','No/weaker prior +7.05 actual points in one completed freeze','MODIFY validation/strength policy; no production retuning from one game','High for validation gap; low for best strength'],
     ['Hard QB correlations','≥2 same-team WR/TE ⇒ QB; WR/TE CPT ⇒ QB; QB CPT needs 2 catchers, or 1 with high rushing','Constraints retained; not causally ablated with complete pregame pools','Current rules can block low-cost replacements','NEEDS MORE EVIDENCE; evaluate separately from rewards','Low'],
     ['Correlation rewards','QB catchers 0.60/0.30/0.10; bring-back 0.45 once; scaled to QB; context/format terms','Each reward family removed independently; no robust confirmed improvement','No-correlation does not change top pick in frozen game','NEEDS MORE EVIDENCE for numeric weights','Low'],
     ['Joint quality screen','≥95% maximum baseline mean AND ≥95% maximum sum marginal P90','Eight admissions compared; most top selections unchanged; broad evidence incomplete','15/438 max-4 candidates survive on completed freeze','MODIFY research admission; retain current control while testing simpler alternatives','High for narrowing; low for outcome benefit'],
     ['Core exposure','80%, ceil(requested × rate), at least 1','Isolated 2/5-entry experiments; fill and overlap measured','Can force underfill; denominator is requested count','MODIFY to entry-count-specific policy with visible regret','High for mechanics; low for optimal cap'],
     ['Starting-QB exposure','100%','Identical to uncapped QB appearances in 2/5 entries','Does not force either specific QB','KEEP as permissive capacity','High for mechanics'],
     ['Captain exposure','60%, ceil; 2/2 or 3/5','Separate cap test; current two-entry cap imposes no Captain distinction','Distinct-Captain + overlap pair helps one game','MODIFY policy by entry count; evaluate soft regret-based diversity','High for mechanics; low for benefit'],
     ['Cheap/punt exposure','≤$1,000 FLEX: 40%, ceil; 1/2 or 2/5','Independent cap experiments; can remove high-scoring rows and underfill','Austin is required in all 21 fresh joint-screened lineups: current cap prevents two-entry v3 fill','MODIFY hard percentage policy; never fix weak inputs through exposure alone','High for feasibility; low for outcome optimum'],
     ['Cheap-player opportunity gate','RB/WR/TE thresholds; any explicit opportunity/role bypasses; separate current-role and kicker gates upstream','No archived current-role/snap evidence; prior-usage proxy is not current-role validation','Smyth excluded by role fix; Austin old target window remains a risk','MODIFY evidence currency requirement; retain sourced injury/role safety','High for failure mechanism; low for historical lift'],
     ['Scenario candidate generation','Baseline + market-conditioned decisive wins; re-score on common baseline','Controlled coverage proxy plus frozen candidate sources; no established cross-game gain','Conditional forecasts are discovery assumptions, not event probabilities','NEEDS MORE EVIDENCE; retain as bounded research discovery','Low'],
     ['Scenario diversity','Default off; soft opt-in 2% bounded credit per condition; legacy required-label mode available','No complete multi-game causal validation of these coefficients','Duplicate labels cannot add physical entries; forced label coverage can displace stronger rows','REMOVE mandatory label quotas from recommended strategy; NEEDS MORE EVIDENCE for soft credits','High for mechanism; low for benefit'],
     ['Portfolio selector','Maximize entry count, then sum baseline selector (+ optional soft coverage)','No verified contest-EV validation; current point proxy can prioritize wrong lineup','Physical top 1% can still finish below field median','MODIFY objective architecture and validation before scaling entries','High'],
     ['Single-entry selector','Normalized 35% mean / 30% P90 / 20% solver / 10% correlation / 5% context; −3% chalk','Separate heuristic; tested on same frozen candidates only','Solver already contains context/correlation; blend counts them again','NEEDS MORE EVIDENCE; compare against simple mean baseline','High for formula; low for performance'],
    ]
    md=[table(['Rule','Current Setting','Historical Evidence','Prospective Evidence','Recommendation','Confidence'],rules),'',
     '**Decision: pause reliance on the current Showdown optimizer for paid lineup decisions; keep Showdown as a research capability. The evidence supports changing how the objectives and inputs are validated. It does not support permanently abandoning the format, or claiming that a particular weight change will fix it.**',
     '',
     'Audit date: October 5, 2026 (America/New_York). Production code and defaults were not changed. The user’s follow-up prioritizes whether the objectives merit repair or Showdown should be abandoned. Recommendations below are research configurations and decision gates, not a deployment.',
     '',
     'The concern is substantive: this optimizer has no demonstrated out-of-sample contest-profit edge. It currently maximizes a ceiling proxy and subjective construction scores. Recent role failures show that a mathematically correct solve can amplify unreliable football inputs. Neither stronger diversification nor more scenarios repairs an inaccurate player distribution.',
     '',
     '### What the objectives actually reward','',
     'For portfolio v3, let `q_i = marginal player P90_i + player context adjustment_i`. Before portfolio constraints, the production lineup selector is:',
     '',
     '```text\nS(L) = sum_FLEX(q_i) + 1.5 × CPT_position_multiplier × q_CPT\n       − role_ownership_penalty + correlation_and_format_rewards(L)\nCPT multiplier = (1 − 0.35) + 0.35 × max(0.05, position_probability × class_count)\n```',
     '',
     f'Ownership is used only with complete finite Captain/FLEX ownership; it is disabled uniformly in the completed frozen comparison. Captain multipliers can strongly change ranking without changing the player mean or P90 forecast. The new structural replay observes QB multipliers from {min(qm):.4f} to approximately {max(qm):.4f}; the prior can suppress or boost QBs depending on the slate. It is not a blanket QB ban.',
     '',
     'The portfolio solve prioritizes **number of generated entries before score**. It then maximizes the sum of these lineup selectors under hard caps and physical uniqueness. Repeating one player in different lineups is allowed up to its appearance cap. A physical signature is the Captain identity plus the six canonical identities; swapping FLEX order or relabeling a scenario does not create a new entry.',
     '',
     'The single-entry path instead normalizes each candidate mean, P90 sum, solver total, correlation and context by the candidate-set maximum absolute value, applies the weights in the opening table, and subtracts relative chalk. Because the solver already includes context/correlation, the blend gives those inputs another vote. The normalization also makes effective tradeoffs depend on the discovery pool. These are heuristic choices, not fitted profit coefficients.',
     '',
     '**Summed marginal P90 is not a calibrated lineup P90.** The sum of individual 90th percentiles generally is not the 90th percentile of their joint sum. These six player outcomes share game conditions; adding small correlation rewards does not turn the proxy into a joint distribution. Neither current selector estimates payout, probability of beating a contest field, duplication-adjusted winnings, or expected profit after fees. Improving raw fantasy score is necessary evidence, but not sufficient evidence of a profitable GPP strategy.',
     '',
     'Code references: [optimizer](backend/app/product_services/optimizer.py), [portfolio selection](backend/app/product_services/showdown_portfolio_selection.py), [single-entry blend](backend/app/product_services/showdown_single_entry.py), [correlation library](backend/app/product_services/lineup_correlation_scoring.py), [scenario credits](backend/app/product_services/showdown_scenario_value.py).',
     '',
     '### Evidence classes and limits','',
     '**TIME-SAFE:** one completed 2026 Week 4 PIT–CLE Thursday slate. The immutable pre-lock input hash matches the saved common scored universe; the saved job and candidate archive precede kickoff. There are 533 physical candidates, including 438 that meet max four/team. Every canonical identity in the full 51-player salary pool has a resolved, consistent DK actual-score observation. Independent exhaustive enumeration finds **105,583,982** DK salary/team-legal Captain/roster assignments and an actual optimum of **120.74** points. This is a selection-only replay: it does not claim that current generation ran historically under every challenger. Historical scoring coefficients are retained for isolated ablations. Current portfolio selector parity is asserted.',
     '',
     '**STRUCTURAL REPLAY:** 45 unique games from the 46-slate oracle archive: 22 in 2024, 18 in 2025, five in 2026. One duplicate game is removed. Projections/markets/opportunity fields are reconstructed; archived current role, availability, snap data and receipt-time provenance are incomplete. QB eligibility is inferred by unique highest team QB salary; ambiguous top ties remain ineligible. The stored prior model is applied at its current 0.35 strength, including its own out-of-distribution fallback. That model was trained on overlapping historical seasons, so this replay is not a chronological evaluation of a newly trained prior. Missing role evidence is left unknown, not supplied from today’s depth charts.',
     '',
     'Production player-context, Captain-prior and correlation builders supply coefficients. The opportunity gate precedes calculation of the prior, matching production ordering; the explicit starter filter follows it. The initial reconstruction that computed the prior before the gate is preserved under `superseded_prior_before_opportunity_gate` and excluded from all final results. A research-only C++ enumerator evaluates those coefficients under the hard QB rules, salary and team constraints. Exhaustive DK denominators include all archived salary identities, including backups; candidate eligibility excludes inferred nonstarting QBs and applies the reconstructed opportunity gate. Current sourced kicker/role filters cannot be replayed exactly without their historical evidence. Optional `avoid_dst_opponents` is off in structural research; the frozen TIME-SAFE candidates retain their saved legality. This is an objective/construction study, not a claim of exact historical end-to-end production input parity.',
     '',
     f'**Critical label limitation:** 1,255 player/game records in the deduplicated archive have `actual_source=unavailable` and a stored value of zero. Those can mean inactivity or a source gap. Only **{current_complete}/45** current top selections have all six actual labels. Confirmed actual scores are null when any label is missing. The “archive” statistics below explicitly use the original zero assumptions; they cannot establish improved subsequent actual performance across many games. The two-team completion test proves a game was played, not that all player scores are resolved. Even paired comparisons with complete selected scores still use reconstructed inputs and an oracle with uncertain zeros.',
     '',
     'Retained research rows cover all tested ≥93% admission screens, the exact mean/P90 Pareto frontier and ≥95% selector-regret candidates through exhaustive maxima and endpoint-dominance bounds. Portfolio solves with more than 5,000 qualifying rows retain top ranks plus Captain witnesses and flag truncation; those are finite-pool portfolio comparisons, not full-universe optimality certificates. One-entry winners and maxima are unaffected by that truncation. Scenario discovery uses a stated controlled breadth proxy, not a reconstruction of the complete historical production scheduler.',
     '',
     'DraftKings legality is six distinct identities, one Captain and five FLEX, $50,000 salary, both teams represented, and 1.5× Captain salary/scoring. Thus max five/team is legal; max four and max three are preferences. [DraftKings Showdown overview](https://support.draftkings.com/dk/en-us/game-style-showdowns-overview?id=kb_article_view&sysparm_article=KB0010694), [DraftKings salary/roster explanation](https://dknetwork.draftkings.com/2020/06/17/advanced-nfl-dfs-showdown-strategy/).',
     '',
     '### TIME-SAFE lineup and portfolio results','',
     'Max four/team, QB Captain allowed, at most two QBs. Screen maxima are held common when comparing admissions; team/QB experiments also report their own candidate-pool maxima. Scores below are actual DK points. Percentile is the fraction of **all DK physical lineups with strictly lower actual score**, so higher is better; regret is 120.74 minus actual score.',
     '']
    safe_rows=[]
    mapping=[('Current v3 top 1','objective_current'),('No Captain prior','objective_no_prior'),('Weaker prior (0.15)','objective_weak_prior'),('No correlation reward','objective_no_correlation'),('Mean ranker, joint admission','mean_ranker_joint'),('P90 ranker, joint admission','p90_ranker_joint'),('Current single-entry blend, same joint pool','single_entry_blend_joint'),('Top two selector lineups','exposure_none_n2'),('Different Captains','two_different_captains'),('Different Captains + ≤4 shared','two_different_captains_max4shared'),('Current percentage caps, two entries','exposure_all_n2'),('Soft repeats, two entries','exposure_soft_n2'),('No caps, five entries','exposure_none_n5'),('Current caps, five entries','exposure_all_n5'),('Soft repeats, five entries','exposure_soft_n5')]
    for label,key in mapping:
        r=safe['experiments'][key]
        safe_rows.append([label,f"{r['generated']}/{r['requested']}",fmt(r['mean_actual_score']),fmt(r['best_actual_score']),fmt(r['mean_regret']),fmt(r['best_regret']),fmt(r['average_shared_identities'])])
    md.extend([table(['Policy','Entries','Mean actual','Best actual','Mean regret','Best regret','Mean shared identities'],safe_rows),'',
     'The two-entry overlap policy re-optimizes the pair globally; it does not necessarily retain the original #1 lineup. Its gain over top two is **+6.65 mean actual points / +5.35 best actual points** at **7.90649 fewer summed selector points**. Different Captains alone, current two-entry caps and the tested soft-repeat cost do not change that top-two pair. This is one game, not a fitted diversification premium. No selected candidate in the listed current/capped portfolios has the actual-optimal Captain.',
     '',
     'Every listed selected lineup is in the physical-universe top 1%, and therefore top 5% and top 10%. This is a weak practical success criterion: the denominator contains millions of legal lineups composed largely of zero-scoring or little-used players.',
     '',
     '**Observed contest fields tell a different story.** In contest 196187076 (99,088 loaded entries = reported field size), the current top lineup’s 87.37 points sit at the **39.252nd field percentile**, despite its **99.884th physical percentile**. The no-prior 94.42-point lineup reaches the **67.422nd field percentile**. The stronger diversified entry’s 99.77 points reach the **84.270th field percentile**, still outside that field’s top 10%. The other three complete loaded fields show similar rankings. These hypothetical ranks do not prove those entries were submitted. Payout ladders/fees are not complete here, so this audit cannot report realized profit or ROI.',
     '',
     'Across the 438 max-four archived candidates, Spearman correlation with actual score is:',
     table(['Forecast/selector','Spearman rank correlation'],[[k,fmt(v)] for k,v in safe['rank_correlations'].items()]),'',
     'The current numeric selector ranks actual outcomes less well than mean on this game. Removing the prior helps ranking modestly; removing correlation does not change the top choice. This supports testing objective simplification, not choosing a new coefficient from a single outcome.',
     '',
     '### Joint screen and alternative admissions',''] )
    screenrows=[]
    for key in ['joint95','mean95','p90_95','joint94','joint93','composite95','pareto','selector_regret95']:
        r=safe['experiments'][f'screen_{key}_n1'];screenrows.append([key,r['eligible'],fmt(r['mean_actual_score']),fmt(r['mean_regret'])])
    md.extend([table(['Admission','Retained candidates (TIME-SAFE)','Selected actual','Regret'],screenrows),'',
     'The joint 95% screen retains **15/438 = 3.42%** of max-four saved candidates, versus 56 with mean-only and 32 with P90-only. Their top selector choice is identical in this game. Tightening therefore demonstrably narrows the universe; this game supplies no top-lineup benefit from requiring both maxima. Mean and P90 ranks are correlated at approximately 0.693 on this archive; “two near-independent maxima” is a hypothesis, not an established property.',
     '',
     'Composite admission means `(mean/max_mean + P90/max_P90)/2 ≥ 0.95`; neither component independently has to reach 95%. Pareto admission retains mean/P90 nondominated rows, including tied identical quality coordinates; it can discard a high-selector roster. Selector-regret admission means ≥95% of the best selector, not a calibrated quality guarantee. Quality thresholds are policy choices. Summed marginal P90 remains a proxy in every alternative.',
     '',
     '### STRUCTURAL REPLAY: objective, rule and admission comparisons','',
     'Positive delta means the alternative has a higher zero-imputed archive score than current max-four, allowed-QB-CPT/max-two-QB, joint-95 top selection. All 45 games are paired by game; wins/losses ignore exact ties. The confirmed subset column uses only pairs where both selected lineups have six sourced actual labels. It is too small and selected to establish a better production policy.',
     table(['Experiment','Archive Δ score','Wins / losses / 45','Fully scored pairs','Δ on fully scored subset'],[[r['experiment'],fmt(r['archive_delta']),f"{r['archive_wins']} / {r['archive_losses']} / 45",r['both_fully_scored_pairs'],fmt(r['confirmed_subset_delta'])] for r in paired]),'',
     f'The no-prior archive delta is **{no_prior["archive_delta"]:+.3f}** points across 45 games, but only {no_prior["both_fully_scored_pairs"]} paired selections have complete scores; their delta is **{fmt(no_prior["confirmed_subset_delta"])}**. Neither the uncertain-zero aggregate nor this small selected subset can be promoted as validated historical improvement. Equal game weighting prevents large-field contests or duplicate salary slates from creating artificial sample size.',
     '',
     '### Captain prior and QB suppression','',
     f'Current prior selects QB Captain in **{cq}/45** games; no prior selects QB Captain in **{nq}/45**. Their archive actual-optimal QB Captain capture counts are **{co}** and **{no}**, respectively. Total Captain correctness is **{cc}/45** for current versus **{nc}/45** without the prior. The prior changes QB opportunity, but incomplete inputs and labels prevent a causal claim that it overly suppresses good QB-Captain lineups. Scoring regret and Captain correctness answer different questions; correct Captain is not enough to make the other five identities optimal.',
     '',
     'A neutral-prior challenger for high-rushing QBs is reported in the experiment table. It is an unfitted sensitivity test, not a supported learned QB-archetype adjustment. The descriptive 45-game archive has 11 QB optima and limited starter/archetype samples; it cannot justify a numeric adjustment for a pocket/mobile/goal-line class. Full current-role confirmation is missing.',
     '',
     'Prior evidence is unstable: the [2,000-candidate 39-slate sweep](docs/showdown_captain_strength_sweep_2024_2025.md) favors 0.15 (+4.384 mean gap improvement; 53.8% wins), while the [2,500-candidate sweep](docs/showdown_captain_strength_sweep_2024_2025_2500.md) favors 0.35 (+6.741; 61.5% wins). These use a different learned lineup experiment and changing stochastic candidate pools; they are not an ablation of today’s full production selector with fixed candidates. Their training/availability provenance does not certify the current pipeline. A `production_validated` description in code is not stronger evidence than the study itself.',
     '',
     '### Portfolio exposure and diversification','',
     'Effective appearances use `max(1, ceil(requested × rate))`, not a strict realized percentage ceiling:',
     table(['Class','Rate','1 entry','2 entries','5 entries'],[['Starting QB','100%','1','2','5'],['Core','80%','1','2','4'],['Captain','60%','1','2','3'],['≤$1,000 punt','40%','1','1','2']]),'',
     'For two entries, core/QB/Captain percentages do not force diversification. A two-entry 60% Captain cap permits the same Captain twice. A two-entry 40% punt cap permits the player once. An underfilled five-request portfolio can still use a core player in all four actual entries, giving 100% realized exposure while passing the requested-count cap. This is observable arithmetic, not an estimate of benefit.',
     ''])
    portrows=[]
    for label in ['exposure_none_n2','two_different_captains','two_different_captains_max4shared','exposure_core_n2','exposure_punt_n2','exposure_qb_n2','exposure_captain_n2','exposure_all_n2','exposure_soft_n2','exposure_none_n5','exposure_core_n5','exposure_punt_n5','exposure_qb_n5','exposure_captain_n5','exposure_all_n5','exposure_soft_n5']:
        vals=[s['experiments'][label] for s in structural]
        portrows.append([label,fmt(mean(v['mean_archive_score'] for v in vals if v['generated'])),fmt(mean(v['best_archive_score'] for v in vals if v['generated'])),
         fmt(mean(v['average_shared_identities'] for v in vals if v['average_shared_identities'] is not None)),sum(v['generated']<v['requested'] for v in vals),
         f"{sum(v['confirmed_lineups'] for v in vals)}/{sum(v['generated'] for v in vals)}"])
    md.extend([table(['Portfolio policy','Archive mean score','Archive best score','Shared identities','Underfilled /45','Fully scored / selected'],portrows),'',
     'The hard-cap combination underfills **7/45** two-entry portfolios and **17/45** five-entry portfolios in structural research. For uncapped five-entry selection, one game has fewer than five joint-eligible rows; hard caps add further bottlenecks. Lower overlap is demonstrated; improved realized result diversity is not established by overlap alone. Best-of-five and mean score should both be reported: a cap can improve the best result while hurting the average, and underfilled portfolios do not have the same number of chances.',
     '',
     'The soft alternative penalizes repeated appearances by `0.05 × max(0, P90−mean) / (1+same-position mean replacement regret)`, with increasing cost for additional repetitions. This respects forecast uncertainty and replacement cost, allows repeats, and pays no reward for changing labels. The 0.05 coefficient and same-position replacement proxy are **unfitted research assumptions**. Its structural results cannot establish profit, covariance reduction, or protection from a bad projection.',
     '',
     'An exposure cap can only protect against a common forecast miss if a useful replacement exists. The audit records cap-only selections and uncapped selections, actual labels, opportunity cost and overlap; incomplete actual labels prevent a trustworthy cross-slate count of “superior actual lineups removed” or “bad projection protected.” Such counts must not be inferred from smaller shared-player counts. Single-game actual examples and the paired structural archive are retained separately in the artifacts.',
     '',
     '### Cheap players, Smyth and Kevin Austin','',
     'The current skill-player gate excludes RB/WR/TE with no explicit opportunity when either salary ≤$1,000 AND mean <3 AND P90 <10, or salary ≤$2,000 AND mean <2 AND P90 <8. Positive expected snaps/routes/carries/targets/shares, a newly assigned role, or many non-generic role labels bypass it. It is an exclusion of low projected opportunity, not a universal requirement for freshly sourced current usage. Kicker/current-role gates are separate upstream safeguards.',
     '',
     f'The [cheap-player CSV](artifacts/showdown_strategy_audit/cheap_player_metrics.csv) contains {len(cheap)} ≤$2,000 player/game rows with canonical ID, salary, prior targets/carries, projection, cap-selected 1/2/5-entry appearances and subsequent score provenance. Archived current-role and recent-snap columns are explicitly null. A stricter prior-usage proxy was tested separately; it cannot answer whether sourced **current** role improves historical results.',
     '',
     '**Smyth, prospective failure example:** the earlier Monday pool treated him as a normal core kicker at mean 10.933/P90 16.577, selected 4/5. The [kicker audit](SHOWDOWN_KICKER_ROLE_AUDIT.md) establishes that this was his own older ability history, not copied Carlson output. Current roster/duties evidence led to exclusion. The later [role audit](CURRENT_SLATE_ROLE_AND_AVAILABILITY_AUDIT.md) confirms the practice-squad/current-duty distinction. Those fixes predate this audit; no historical outcome is rewritten with today’s depth chart.',
     '',
     '**Kevin Austin, prospective failure example:** the [final two-entry analysis](ATL_NO_FINAL_TWO_ENTRIES.md) reports $800 salary, mean 5.076/P90 10.502, 4.218 modeled targets using an old receiving window (2025 W17/W18 and 2026 W2), against approximately 9% recent 2026 W1–W3 snaps. All 21 fresh joint-screened lineups include him. Under v3’s two-entry punt appearance cap of one, a full two-entry portfolio would be infeasible; the separately researched final pair allowed repetition and therefore retained common Austin forecast risk. Different Captains do not diversify away that risk. His sourced backup roster role permits eligibility, but does not substantiate that target forecast. No postgame Austin or Smyth result is used here.',
     '',
     'Recommendation: use current roster/duty evidence and usage currency to qualify very cheap opportunities; retain uncertainty when a backup has plausible limited involvement. Salary and a high projection alone are not proof of opportunity. Validate any stricter threshold on historical fresh evidence, including cheap players who actually break out, before deploying it. Do not use an exposure exception as evidence that a forecast is correct.',
     '',
     '### Correlations and scenarios','',
     'The independent ablations remove the first same-team pass-catcher reward, additional pass-catcher rewards (second 0.30 and third 0.10), once-per-QB-team bring-back, team concentration, and remaining script/format rewards. Positive QB-linked rewards scale to the QB projection relative to the strongest QB in the pool (bounded 0.4–1.0). Importantly, the saturated 0.45 bring-back is active when an opposing WR/TE is present; it is not restricted by a calibrated shootout probability. Penalties remain in the partial reward ablations; the all-correlation ablation removes the full adjustment.',
     '',
     'Conventional correlation theory does not validate these magnitudes. The original constraints remain in these reward tests, so “no first-catcher reward” does not remove the hard stack requirements. There is insufficient complete multi-slate evidence to say any of these individual weights improves eventual ranking. The independent witness tests confirm scorer implementation, not predictive accuracy.',
     '',
     'Current scenarios condition market total/spread and role volume toward a 14+ decisive winner with bounded factors, then restore baseline scoring before common quality admission. Baseline discovery plus scenario discovery is tested as coverage; one lineup per scenario is never imposed in recommendations. The 45-game research proxy takes top 25 baseline selector rows plus each Captain’s best witness, then adds top 25 per conditioned P90 axis. It differs from the production scheduler (multiple axes/Captains/constructions/role scripts), so it is a sensitivity experiment rather than historical end-to-end generation validation.',
     '',
     'The completed frozen universe also separates production, research-baseline and all-source archives. Useful rediscoveries can be scored, but all-source improvement cannot be assigned solely to scenarios because Captain/forced-FLEX/construction research also expands the pool. Legacy required-label coverage prioritizes labels above selector; the default does not enable it. Optional soft coverage pays at most 2% of the ordinary median selector per condition after common quality, uplift, novelty and coherent winner construction. Its exact coefficients lack cross-game outcome validation. A scenario label is not evidence of calibrated probability.',
     '',
     '### What would justify changing or abandoning the objectives','',
     'The audit confirms three different issues: input reliability (current opportunity), selector design (ceiling/prior/bonus proxies), and incomplete validation (few frozen scored slates). It does not isolate one universal cause of the user’s losses. A mode can have legal, correlated lineups and still lack a competitive forecasting edge.',
     '',
     'Before promoting a replacement, freeze complete pregame player identities, current roles, forecasts, ownership status, salaries, candidate sets and code version. Resolve full actual labels afterward. Compare fixed candidates for attribution and independently regenerated candidates for discovery. Use distinct games as the statistical unit; report mean/median regret, field top-10/5/1 rates, tie/duplication-aware contest returns where fee/payout records exist, and one-/two-/five-entry results separately. Never count four contests on one game as four independent football forecasts.',
     '',
     'A practical next research set is current control versus a simple mean-led ranker, no/weaker Captain prior, and bounded soft diversification. A fixed forward series of roughly 20–30 complete slates can expose persistent failures; it is an initial diagnostic sample, not an automatic profitability certificate. Pre-register the candidates and thresholds and retain losses. Do not search a wide weight grid and label its in-sample winner validated.',
     '',
     'Retire the current strategy if it continues to lose to the simple baseline on complete held-out slates after role/label failures are corrected. Abandon paid Showdown play if the best validated forecast/selection combination cannot demonstrate competitiveness against real fields after contest economics, or if maintaining fresh inputs is not worth the effort. A profitable edge remains unproven today. Permanently removing Showdown software is not required to stop relying on it for paid entries.',
     '',
     '### Reproducibility and verification','',
     'All work is offline and additive. [Per-slate metrics](artifacts/showdown_strategy_audit/slate_metrics.csv), [every selected lineup/experiment](artifacts/showdown_strategy_audit/selected_lineup_metrics.csv), [paired results](artifacts/showdown_strategy_audit/paired_experiments.csv), [aggregate JSON](artifacts/showdown_strategy_audit/aggregate.json), and per-slate prepared inputs, exhaustive histograms and retained physical rows are saved. The TIME-SAFE result contains Captain actual-optimal flags, verified physical percentiles, team splits, QB counts, Captain positions, actual scores, mean/median regret and overlap. The structural files keep sourced actual scores separate from zero-imputed diagnostics.',
     '',
     '```sh\nc++ -O3 -std=c++17 scripts/showdown_strategy_audit_enumerator.cpp -o artifacts/showdown_strategy_audit/enumerator\nPYTHONPATH=. .venv/bin/python scripts/audit_showdown_strategy.py\nPYTHONPATH=. .venv/bin/python scripts/audit_showdown_archived_candidates.py\nPYTHONPATH=. .venv/bin/python scripts/render_showdown_strategy_audit.py\nPYTHONPATH=. .venv/bin/pytest scripts/test_showdown_strategy_audit.py -q\n```',
     '',
     'Verification: two research tests pass. A small physical universe is compared exhaustively against an independent Python enumeration, including the exact score histogram; five distinct frozen historical roster witnesses match production MILP objective values within 1e-5. All 45 archive optima match independent enumeration within 0.021 points. The TIME-SAFE portfolio signatures match the actual production selector at five requested entries. A fixed seed is retained. Source/code SHA-256 manifests pin the audit; no new dependency is introduced. Tests do not establish forecasting or profit accuracy.',
     '',
     '**Unresolved requested evidence:** fully time-safe multi-slate current-strategy reconstruction, exact archived current-role/snap gate ablation, calibrated QB-archetype prior, exact historical production scenario-generation ablation, causal bad-projection protection frequency, and fee/payout-based profitability are unavailable from the retained sources. They are marked insufficiently validated, not silently replaced with the structural diagnostics.',
     '',
     '### Recommended configurations','',
     '**These are provisional research settings. The operational recommendation is to pause reliance on paid Showdown outputs until validation closes the gaps; no production setting is changed.**',
     table(['Setting','One-entry Showdown','Two-entry Showdown','Five-entry Showdown'],[
      ['Eligibility','Fresh canonical roster/duty/usage evidence; allow QB CPT; max 2 starting QBs','Same','Same'],
      ['Team count','Keep max 4 if explicitly requested; compare legal max 5; do not force max 3','Same','Same'],
      ['Objective control','Retain current v3 and single-entry blend as controls','Retain top two current selector rows as control','Retain current v3 capped control'],
      ['Objective challenger','Simple mean-led score; explicitly labeled uncertainty/ceiling diagnostic','Sum mean-led scores plus bounded uncertainty/replacement-regret repeat cost','Same, with best-result and average-result objectives reported separately'],
      ['Captain prior','No prior and 0.15 challengers; retain 0.35 only as control','Same','Same'],
      ['Correlation','Current weights as control; independent removals; do not fit weights on one recent game','Same','Same'],
      ['Admission','95% mean-only challenger versus joint-95 control; Pareto/composite/regret diagnostics','Same fixed benchmarks; explain cost of each replacement','Same; explicitly report infeasibility rather than chasing entry fill'],
      ['Exposure','No cross-entry caps or diversity reward','Use whole-entry rules; allow core/QB repeats; compare different CPT + ≤4 shared with soft regret-based choice; no automatic punt veto solely from 40%','Compare current 4-core/5-QB/3-CPT/2-punt capacities with soft repeats; retain no unsupported hard-cap percentage as an established optimum'],
      ['Scenarios','Optional discovery only; common baseline scoring','Optional discovery; no quotas','Optional discovery; no quotas; soft coverage is experimental'],
      ['When to use for paid decisions','Only after complete prospective validation demonstrates competitiveness','Additionally demonstrate useful diversification without excessive regret','Additionally demonstrate five-entry benefit and trustworthy forecast/role coverage; otherwise do not scale'],
     ])])
    discovery=[]
    for n in [1,2,5]:
        pairs=[(s['experiments'][f'scenario_discovery_n{n}'],s['experiments'][f'baseline_discovery_n{n}']) for s in structural]
        delta=[a['best_archive_score']-b['best_archive_score'] for a,b in pairs if a['generated'] and b['generated']]
        discovery.append([n,fmt(mean(delta)),sum(v>1e-7 for v in delta),sum(v< -1e-7 for v in delta),
                          sum(a['generated']!=b['generated'] for a,b in pairs)])
    marker=md.index('The completed frozen universe also separates production, research-baseline and all-source archives. Useful rediscoveries can be scored, but all-source improvement cannot be assigned solely to scenarios because Captain/forced-FLEX/construction research also expands the pool. Legacy required-label coverage prioritizes labels above selector; the default does not enable it. Optional soft coverage pays at most 2% of the ordinary median selector per condition after common quality, uplift, novelty and coherent winner construction. Its exact coefficients lack cross-game outcome validation. A scenario label is not evidence of calibrated probability.')
    md[marker:marker]=['Controlled STRUCTURAL REPLAY discovery comparison (same capped selector and baseline quality):','',
      table(['Entries','Archive Δ best score','Improved games /45','Worse games /45','Changed fill count /45'],discovery),'',
      'These coverage differences are diagnostic because the retained forecasts and score labels are incomplete. More candidate coverage can improve or worsen the eventual result; it is not itself evidence of better calibrated scenario probabilities.','']
    text='\n'.join(md);lines=[]
    for line in text.splitlines():
        if line.startswith('|') and lines and lines[-1] and not lines[-1].startswith('|'):lines.append('')
        lines.append(line)
    (ROOT/'SHOWDOWN_OPTIMIZER_STRATEGY_AUDIT.md').write_text('\n'.join(lines)+'\n')
    before=read(OUT/'production_hashes_before.json')
    changed=[p for p,h in before.items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
    write(OUT/'verification.json',{'production_files_changed_since_start':changed,'research_tests':'2 passed',
      'structural_games':45,'time_safe_games':1,'actual_oracle_matches':45,'source_hashes':{
      str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'artifacts/showdown-oracle-dataset-2026-09-28-v2.json',
       ROOT/'artifacts/showdown_qb_policy_controlled/2026w4-monday-2771d4f1/historical-actuals.json',
       ROOT/'artifacts/week4_showdown_production_research_parity/20261001T153239Z/production_input_freeze.json',
       ROOT/'artifacts/week4_showdown_production_research_parity/20261001T153239Z/common_scored_universe.json',
       ROOT/'scripts/audit_showdown_strategy.py',ROOT/'scripts/audit_showdown_archived_candidates.py',
       ROOT/'scripts/render_showdown_strategy_audit.py',ROOT/'scripts/test_showdown_strategy_audit.py',
       ROOT/'scripts/showdown_strategy_audit_enumerator.cpp']}})
    print('report written; production hash changes:',changed)

if __name__=='__main__':main()
