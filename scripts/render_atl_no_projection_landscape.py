"""Render the corrected projection landscape audit from immutable research artifacts."""
from collections import Counter
from itertools import combinations
import csv
import hashlib
from pathlib import Path
import numpy as np

from scripts.audit_atl_no_projection_landscape import DEST, SOURCE, ROOT, FLOORS, portfolio, certify_batch
from scripts.enumerate_showdown_policy_universe import certify
from scripts.run_showdown_qb_policy_experiment import read, write


def supplementary(snapshot, a, analysis):
    path=DEST/'supplementary.json'
    if path.exists():return read(path)
    players=snapshot['player_pool'];out={}
    for label in 'ABCDEF':
        p=analysis['policies'][label]
        allow,maxqb=(label not in 'CD',1 if label in 'BD' else 2)
        limit=4 if label=='E' else 3 if label=='F' else 5
        legal=(a['qb_count']<=maxqb)&((~a['qb_captain'])|allow)&(a['no_count']<=limit)&(6-a['no_count']<=limit)
        rows=np.flatnonzero(legal & (a['mean']>=.95*p['raw_maxima']['mean']-1e-7)&(a['p90']>=.95*p['raw_maxima']['p90']-1e-7))
        limits=dict(p['player_limits'])
        pid=next(p['player_id'] for p in players if p['name']=='Kevin Austin Jr.')
        limits[pid]=5
        out[label]={'only_austin_cap_relaxed':portfolio(a,rows,players,limits,p['captain_limit'])}
        for field in ('mean','p90'):
            subset=np.flatnonzero(legal & (a[field]>=.95*p['raw_maxima'][field]-1e-7))
            out[label][field+'_screen_only']=portfolio(a,subset,players,p['player_limits'],p['captain_limit'])
    groups=np.array(list(combinations(range(len(players)),6)),dtype=np.int16)
    indices=np.repeat(groups,6,axis=0);captains=groups.reshape(-1)
    sample=np.linspace(0,len(indices)-1,151,dtype=int)
    ok,score,_=certify_batch(snapshot['solver_model'],captains[sample],indices[sample])
    for j,r in enumerate(sample):
        scalar=certify(snapshot['solver_model'],int(captains[r]),tuple(indices[r]))
        assert ok[j]==(scalar is not None)
        if scalar is not None:assert abs(score[j]-scalar)<1e-6
    out['validation']=dict(full_assignment_samples=len(sample),accepted=int(ok.sum()),rejected=int((~ok).sum()),scalar_parity='passed')
    write(path,out);return out


def fmt(value):
    if value is None:return 'unavailable'
    if isinstance(value,float):return f'{value:.3f}'
    if isinstance(value,dict):return '; '.join(f'{k}: {v}' for k,v in value.items()) or 'none'
    return str(value).replace('|',' / ').replace('\n',' ')


def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join('---' for _ in headers)+' |']+
                     ['| '+' | '.join(fmt(v) for v in row)+' |' for row in rows])


def pct(value):return f'{100*value:.1f}%'


def main():
    s=read(SOURCE/'prepared_input.json');players=s['player_pool'];pool={p['player_id']:p for p in players}
    analysis=read(DEST/'analysis_v2.json');policies=analysis['policies']
    bridge=read(DEST/'projection_bridge.json');usage=read(DEST/'prior_usage.json')
    a=dict(np.load(DEST/'full_universe.npz'));sup=supplementary(s,a,analysis)
    cal=read(ROOT/'artifacts/current_slate_role_audit/corrected_projection_run.json')['calibration_metrics']
    allocations=cal['pregame_context']['allocations']
    names={p['player_id']:p['name'] for p in players}
    bplayers=sorted(bridge['players'],key=lambda p:(pool[p['player_id']]['player_team'],pool[p['player_id']]['position'],p['name']))
    text=[
        '# ATL NO corrected projection landscape audit',
        'The corrected forecasts produce a narrow 95% quality universe through **a combination of projection and salary structure, the joint quality screen, and exposure caps**. The full enumeration reproduces A/B/C/D/E/F maximum fills of **3/2/2/2/4/2**. Candidate discovery is not the cause. No live optimizer rule, projection, default, exposure cap, or persisted lineup was changed.',
        'Kevin Austin Jr. has the strongest salary efficiency, but his receiving history comes from a different time window than his recent snaps. His mean rises principally through the opportunity anchor; neither a roster-promotion bonus nor sparse-history fallback explains it. This is a concrete forecast-validation concern, not proof that his projection is incorrect. Shough has the highest absolute mean and P90, costs less than several stars, and enables Saints passing constructions. His universality survives a 90% screen.',
        'Policy A fills five at a diagnostic 93% joint floor, E at 94%, and one-QB B at 92%. Those results support investigating the screen and usage currency before any permanent rule decision. They do not validate a new default or a football projection adjustment.',
        '## Baseline and method',
        f"Baseline: 2026 Week 4 ATL–NO Monday Night, corrected projection `{s['projection_run_id']}`. The fitted artifact was reloaded by checksum and every eligible player’s mean/P90 reproduced to 1e-6. The 23-player prepared pool and saved production MILP supply legality and selector scoring. No earlier ATL–NO projection run was substituted.",
        'A permits QB Captain and up to two starting QBs, with max five from one team. B keeps QB Captain but permits at most one QB. C permits two QBs and forbids QB Captain; D forbids QB Captain and permits one QB. E follows A with max four from one team; F follows A with max three.',
        'A physical signature is Captain UUID plus the six canonical player UUIDs. FLEX order creates no new roster. Raw mean and summed marginal P90 use 1.5× Captain fantasy points. Selector is the objective of the saved MILP and separately includes context, Captain weighting, format rules, and correlation rewards. Selector ranks are computed before the quality screen and exposure constraints.',
        f"Enumeration covers {analysis['enumeration']['all_six_player_captain_signatures']:,} six-player/Captain assignments: {analysis['enumeration']['salary_team_legal_signatures']:,} pass salary/team prefilters, and {analysis['enumeration']['saved_model_legal_signatures']:,} satisfy every saved MILP constraint. The 583,690 figure is a prefilter count, not the final legal universe. The earlier rank-pruned universe was sufficient for 95% feasibility but insufficient for whole-universe percentile frequencies; this audit enumerates all legal signatures.",
        'Quality maxima are recalculated within each policy, as in the existing experiment. Each floor holds that policy’s independent mean maximum and P90 maximum fixed. Exposure caps remain integers derived from the requested five entries: QB 5, core/non-punt player 4, salary ≤$1,000 player 2, Captain 3. Underfilled portfolios do not renormalize those caps. Portfolio solves maximize count up to five first, then summed selector. Pairwise overlap counts shared canonical players; it is not simulated fantasy-score correlation.',
        '## Part 1 Projection construction for every eligible player',
        'The fitted gradient-boosting tree consumes salary, market, prior fantasy history, opponent history, prior snaps, and offensive-role features. Exact tree-path contributions and consumed features are retained in `projection_bridge.json`. These are additive explanations of the raw tree, not causal claims. The tree alone does not explicitly forecast routes or snaps.',
        'For non-kickers, base point mean = 0.80 × raw tree + 0.20 × history anchor. History anchor = 0.60 × prior-three-record fantasy mean + 0.40 × prior-eight-record fantasy mean, provided at least three history records exist; otherwise it is the position training mean. When team opportunity context applies, WR/TE opportunity units are modeled targets and RB units are carries + 1.75 × targets. A monotonic isotonic curve fit on prior position data gives the opportunity anchor. The blend weight is 0.55 with at least three records and 0.70 otherwise. QB/DST bypass this opportunity anchor.',
        'Final conditional mean = post-opportunity point mean + the stored market residual adjustment. Availability multiplies the final mean and quantiles; QB participation also multiplies starter probability. All 23 eligible baseline players have participation 1.0. P90 = final conditional mean + the selected walk-forward residual P90, with nonnegative/monotonic quantile enforcement. Residual calibration does not add a separate bonus to mean.',
        'Kicker mean bypasses the tree and uses its own 60/40 history blend. Folk and Carlson both have history; neither uses a peer fallback. The fitted DST point blend uses the position training mean as its history fallback. Barion Brown’s two-record history uses the WR position baseline for the 20% history term and the 70% opportunity weight. Everyone else in this eligible pool has at least three records.',
        '### Prior inputs and current opportunity estimates',
        'Targets and carries show prior three available player-stat records → current allocator volume. Snap share is the mean of the last three available participation records. Those windows need not cover the same games. Expected snaps and routes are unavailable for every eligible player; historical snap share is not an expected snap-count forecast.',
        table(['Player','Role','History records','FP prior 3 / 8','Targets prior → modeled','Carries prior → modeled','Prior snap share'],
              [[p['name'],p['target_features'].get('expected_depth_role'),
                p['target_features']['player_games_history'],
                f"{p['target_features']['player_roll3_mean']:.3f} / {p['target_features']['player_roll8_mean']:.3f}",
                f"{p['target_features'].get('pregame_base_targets_mean_3',0):.3f} → {fmt(p['target_features'].get('projected_targets'))}",
                f"{p['target_features'].get('pregame_base_carries_mean_3',0):.3f} → {fmt(p['target_features'].get('projected_carries'))}",
                pct(p['target_features']['snap_share_mean_3'])] for p in bplayers]),
        '### Exact numerical bridge',
        'Opportunity Δ is post-opportunity minus base mean, not a measured promotion effect. Kicker override is shown separately because its tree blend is unused. Market Δ below is the additional team-response reconciliation after market features have already entered the tree; it is not the tree’s total market contribution.',
        table(['Player','Raw tree','History anchor','Base blend','Opportunity anchor / weight','Opportunity Δ','Market Δ','Kicker override Δ','FLEX mean','P90 residual','FLEX P90'],
              [[p['name'],p['raw_tree_mean'],p['history_anchor'],p['base_blended_mean'],
                f"{fmt(p['opportunity']['pregame_opportunity_point_anchor'])} / {p['opportunity']['pregame_opportunity_point_weight']:.2f}",
                p['opportunity']['pregame_point_mean_after_opportunity']-p['base_blended_mean'],p['market_residual_adjustment'],
                p['mean']-p['base_blended_mean'] if pool[p['player_id']]['position']=='K' else 0,
                p['mean'],p['p90']-p['mean'],p['p90']] for p in bplayers]),
        '### Shares and residual calibration',
        'Shares are allocator outputs. Historical role importance remains a historical feature rather than being rewritten by user preferences or by current allocation. STARTER/BACKUP depth labels are distinct from residual calibration roles. The residual scorer recognizes explicit LEAD/COMMITTEE/PRIMARY/SECONDARY/ROTATION; STARTER/BACKUP falls through to measured historical workload classification.',
        table(['Player','Target share','RB carry share','Calibration group','Residual sample size','History fallback','Residual shrinkage'],
              [[p['name'],pct(p['target_features'].get('target_share_mean_3',0)),pct(p['target_features'].get('carry_share_mean_3',0)),
                p['calibration_key'],p['calibration_profile']['sample_size'],p['history_fallback'],
                'global fallback' if 'fallback' in p['calibration_profile']['source'] else 'parent shrinkage' if 'shrunk' in p['calibration_profile']['source'] else 'none at selected group size'] for p in bplayers]),
        'The selected non-kicker position/role/importance groups have full empirical weight at their group size. The kicker residual group has 14 observations: its role profile shrinks toward the position profile at weight 14/50, and that position profile shrinks toward the global profile at weight 14/30. Kicker mean still uses own history. Position shrinkage reaches full weight at 30 rows, role at 50, and importance-bin shrinkage at 100. The historical calibration promotion gate is blocked because not every position has 30 residual rows. Its overall position/role empirical coverage is not independent validation of this current corrected allocator.',
        '### Recent usage and source windows',
        'Each row shows the last three raw stat records and the last three participation records available before the frozen cutoff, with duplicate captures resolved by their latest record. Blank source windows do not negate the fitted artifact’s separately retained fantasy history. The last target and snap shares are measured historical values, not current expected shares. QB carries in the fitted feature matrix are historical features; the allocator supplies an explicit projected carry count only for RBs.',
        table(['Player','Last three stat periods','Last three snap periods','Latest target share','Latest snap share','Target share trend','Snap share trend'],
              [[p['name'],', '.join(f"{r['season']} W{r['week']}" for r in [r for r in usage['weekly_stats'] if r['canonical_player_id']==p['player_id']][-3:]) or 'unavailable',
                ', '.join(f"{r['season']} W{r['week']}" for r in list({(r['season'],r['week']):r for r in usage['participation'] if str(r['player_master_id'])==p['player_id']}.values())[-3:]) or 'unavailable',
                p['target_features'].get('target_share_last'),p['target_features'].get('snap_share_last'),p['target_features'].get('target_share_trend'),p['target_features'].get('snap_share_trend')] for p in bplayers]),
        '### Football changes and vacated opportunity',
        'Unavailable players retain their football lineage while receiving zero participation. Lost targets stay unallocated unless source-supported recipients and an explicit redistribution assumption identify them. Kevin Austin receives zero vacated targets. Kamara and Miller receive Etienne carry opportunity in proportion to measured prior carries, a committee allocation assumption rather than a sourced numerical split. No automatic Fant-to-Juwan transfer, generic injury fantasy-point transfer, or depth-rank point bonus is applied.',
        table(['Team','Opportunity','Lagged team volume','Projected volume','Unallocated volume','Redistributed share'],
              [[r['team'],r['opportunity'],r['team_volume'],r['player_projected_volume_sum'],r['unallocated_volume'],r['redistributed_share']] for r in allocations]),
        table(['Supported recipient','Opportunity','Own normalized prior volume','Received vacated volume','Expected volume'],
              [[names[r['player_id']],allocation['opportunity'],r['prior_volume'],r['received_volume'],r['expected_volume']]
               for allocation in allocations for r in allocation['players'] if r['received_volume']>0]),
        'Only Kamara and Miller receive vacated volume in this freeze: 4.321639 and 2.574189 carries respectively. Every other optimizer-eligible player receives zero vacated targets/carries. No separately identified point bonus is attributed to roster promotion or demotion; the numerical opportunity delta above combines the pooled volume anchor and team allocation, so a causal promotion-only point effect would require an additional counterfactual.',
        'The anchor decreases Olave, Vele, Juwan, Pitts, London, Bijan, Miller, Lance, and Woerner relative to their base blends; it raises Austin, Kamara, Brian Robinson, Dotson, Zaccheaus, Hooper, and Branch. Thus the correction is not a general upward shift. Shough’s mean is 20.146 tree → 21.117 history blend → 21.658 market reconciliation; his source role is QB1. His 32.384 P90 adds 10.726 from the QB residual distribution. Kamara’s 8.768 mean adds 1.173 through the carry/target anchor and 0.219 market adjustment; his LEAD residual group contributes 11.235 to P90. None of these observations by itself proves overprojection.',
        '## Part 2 Kevin Austin Jr diagnostic',
        '### Origin of the 4.218 targets',
        'Austin’s prior targets average 5.000 from **2025 Week 17: 5; 2025 Week 18: 9; 2026 Week 2: 1**. Those source records resolve to canonical UUID `b9c707f4-67b9-425a-a357-7c1e039582df` through nflreadpy source ID `00-0037231`. The raw-row IDs are 472457, 473493, and 498896. His prior target-share average is (5/27 + 9/34 + 1/32)/3 = 0.160380356.',
        'The allocator’s sum of NO prior player target shares is 1.571700113. It normalizes Austin’s prior share to 0.160380356 / 1.571700113 = 0.102042594. Multiplying that by the latest full-team three-game target volume, 41.333333333, gives **4.217760535**. This is a share-times-team-volume estimate, not a new observation of four targets. The normalization lowers his modeled targets below his prior average of five.',
        'There are no 2026 Week 1 or Week 3 receiving stat rows for Austin in the cutoff-safe source slice. Missing rows are not assumed to be measured zero. His fantasy three-record mean is (15.2 + 7.7 + 1.7)/3 = 8.2, and his eight-record mean is 5.0375. His history anchor is therefore 6.935. He has 14 history records and does not use the sparse-player position baseline.',
        'His participation window is different: 2026 Weeks 1–3 have 5/5/10 offensive snaps and shares 6%/7%/14%, yielding **9%** mean snap share. His latest measured target share is **3.125%**; its stored trend versus the preceding three stat records is **−13.999 percentage points**. Late-2025 receiving usage is therefore being carried into a forecast whose recent participation is materially lower.',
        '### Mean and ceiling mechanisms',
        'Raw tree 1.336695589 and history anchor 6.935 produce base mean **2.456356471**. Because team opportunity context is active, the WR isotonic curve maps his 4.217760535 targets to a **7.256994576** opportunity anchor. A 55% blend gives 0.45×2.456356471 + 0.55×7.256994576 = **5.096707429**, a **+2.640350958** adjustment. Market reconciliation adds **0.130590425**, giving **5.227297853**.',
        'His prior offensive-role importance 0.142785267 exceeds the WR ROTATION median split 0.083703704. The selected high-importance ROTATION group has **660 residual observations**, no sparse-bin shrinkage, and residual P90 **5.426010822**. Final P90 is **5.227297853 + 5.426010822 = 10.653308676**. The residual increment is 50.93% of that marginal P90 level. It is not a separable causal share of tail probability. Using the parent ROTATION profile would add 4.036100470 instead; the selected group adds 1.389910353 more. That comparison describes calibration selection and does not authorize changing his profile.',
        'Residuals are learned from chronological tree/history point predictions. The current opportunity-anchor and market-reconciliation stages are not applied by `generate_walk_forward_residuals`. Consequently, historical residual coverage does not directly establish calibration of the full current corrected bridge. This applies to the model generally and is not an Austin-only sparse-history issue.',
        '### Answers to the ten individual questions',
        '1. **Target origin:** normalized own prior target share × full-team prior volume, as shown above.\n2. **Own measured usage:** yes, but the last three available receiving records span late 2025 and 2026 Week 2.\n3. **Inherited unavailable-player work:** zero received targets, zero redistribution. Unavailable teammates can activate team context and the anchor, which is an indirect model-stage effect, not inherited volume.\n4. **October 1 active-roster promotion:** it establishes roster availability and eligibility. It supplies no numeric targets, routes, snaps, or promotion bonus.\n5. **Roster membership versus offensive role:** represented separately in source facts and depth labels. Numeric receiving workload nevertheless remains based on measured history; BACKUP is not mapped to a new target cap or reduction. `pregame_newly_assigned_role` is false.\n6. **Consistency with expected backup:** not logically impossible, since backups can receive targets. It is insufficiently supported as a current expectation because it combines older receiving usage with 9% recent snaps and a latest one-target record. Forecast validity remains unresolved.\n7. **Routes/snaps support:** no projected routes or expected snap counts are supplied. Recent measured snaps do not independently validate 4.218 targets.\n8. **P90 usage versus calibration:** usage anchor adds 2.640 to the point mean; market adds 0.131; the residual profile adds 5.426 above final mean.\n9. **Fallback inflation:** no player-history fallback, peer-copying, or sparse residual fallback applies to Austin. The opportunity curve is a position-level peer relationship blended at 55%; the residual group is also pooled. Those mechanisms, plus stale usage, merit scrutiny.\n10. **Analogues:** current and archived examples follow below; older archives are contextual comparisons and never replace this corrected baseline.',
        '### Current and archived cheap-player analogues',
        'Current sourced backups Lance, Branch, Hooper, and Brian Robinson retain positive football assessments, but none is near-mandatory at 95%. Austin’s $800 price is unusual relative to his forecast. Charlie Woerner is $600 and has P90 5.798, but is a sourced expected starter, not a backup; low salary alone is insufficient for universality.',
        table(['Current player','Salary','Mean','P90','A joint95 frequency','A top1 selector frequency'],
              [[p['name'],p['salary'],p['projection'],p['p90'],pct(policies['A']['thresholds']['0.95']['quality_universe']['player_frequencies'][p['name']]),pct(policies['A']['selector_rank_frequencies']['0.01']['player_frequencies'][p['name']])]
               for p in players if p['name'] in ['Kevin Austin Jr.','Bryce Lance','Zachariah Branch','Austin Hooper','Brian Robinson Jr.','Charlie Woerner']]),
        'Archived 2026 Week 2 KC–IND selects Brashard Smith ($400, mean 2.701, P90 10.726) in 2/5 production entries. The Week 3 ATL–GB freeze selects Josh Whyle in 1/5 and Chris Brooks in 1/5. These demonstrate that inexpensive secondary players can matter structurally. Their official backup designation and exhaustive historical 95% mandatory frequency are not established by those archives. The Week 2 DET–BUF role audit also has Tay Martin ($800, rotational, mean 2.029/P90 4.560), Jackson Hawes ($600, rotational, 1.813/6.947), Keleki Latu ($200, rotational, 1.541/6.675), and Skyler Bell ($200, missing role evidence, 2.429/9.719). That prior run used the superseded salary-fallback allocator and is not evidence that current corrected ceilings are validated. A systematic historical cohort of officially sourced backups is still needed to establish prevalence and calibration of the mechanism.',
        '## Part 3 Football strength and salary relief',
        'Near-mandatory means ≥75% of that policy’s joint95 universe, a descriptive cutoff used only in this audit. Across A–F the near/mandatory set is Shough, Austin, Bijan, Olave, and Penix. Austin is the only inexpensive backup in that set. Full per-policy top 1/5/10/25% frequencies for all eligible players are saved in `player_rank_frequencies.csv`.',
        '### Efficiency and whole-universe selector ranks',
        'The following percentile columns refer to A’s **entire 61,396 legal roster universe**. Rankings include ties at each boundary. Roster frequencies are unweighted counts, not probabilities that a lineup is optimal, and not selected portfolio exposures.',
        table(['Player','Salary','Mean','P90','Mean / $1k','P90 / $1k','A joint95','A top1%','A top5%','A top10%','A top25%'],
              [[p['name'],p['salary'],p['projection'],p['p90'],1000*p['projection']/p['salary'],1000*p['p90']/p['salary'],
                pct(policies['A']['thresholds']['0.95']['quality_universe']['player_frequencies'][p['name']])]+
               [pct(policies['A']['selector_rank_frequencies'][str(q)]['player_frequencies'][p['name']]) for q in (.01,.05,.1,.25)]
               for p in sorted(players,key=lambda p:-1000*p['projection']/p['salary'])]),
        '### Frequency under every 95% policy',
        table(['Player','A','B','C','D','E','F'],[[p['name']]+[pct(policies[k]['thresholds']['0.95']['quality_universe']['player_frequencies'][p['name']]) for k in 'ABCDEF'] for p in players]),
        'Austin has only 5.227 football points of mean, but **6.534 mean and 13.317 P90 per $1,000**, both the highest in the pool. He costs $800 versus Lance $1,800, Zaccheaus $2,000, Hooper $2,800, and Dotson $3,000. Those alternatives generally either cost more or lose point mean/ceiling. Woerner costs $200 less but loses 4.073 mean and 4.856 P90; it is not an equivalent cheap replacement.',
        'Removing the salary constraint while holding football forecasts, all other saved policy legality, and the **original dollar-constrained maxima** fixed makes Austin-free ≥95% lineups possible under every policy. That isolates his essential salary-relief value. This diagnostic does not claim salary-neutral lineups are legal entries.',
        table(['Policy','Best joint fraction without Austin','Without Austin and without salary cap','Austin-free joint95 signatures','Austin cap + free signatures','Certified max fill'],
              [[k,f"{100*policies[k]['best_without_player']['Kevin Austin Jr.']['best_joint_fraction']:.4f}%",f"{100*policies[k]['best_without_player']['Kevin Austin Jr.']['no_salary_limit_joint_fraction']:.4f}%",
                round(policies[k]['thresholds']['0.95']['quality_universe']['count']*(1-policies[k]['thresholds']['0.95']['quality_universe']['player_frequencies']['Kevin Austin Jr.'])),
                '2 + '+str(round(policies[k]['thresholds']['0.95']['quality_universe']['count']*(1-policies[k]['thresholds']['0.95']['quality_universe']['player_frequencies']['Kevin Austin Jr.']))),
                policies[k]['thresholds']['0.95']['portfolio']['maximum_feasible_count']] for k in 'ABCDEF']),
        'The Austin bound is exact: A has one qualifying signature without Austin, E has two, B/C/D/F have none. Since every signature can be used at most once and Austin may appear twice, fills cannot exceed 3/4/2 respectively; each bound has a feasible witness. In B/D/F, Bijan is also universal and his four-appearance cap becomes relevant if Austin’s cap alone is relaxed. Other caps can still bind after one restriction is lifted.',
        'Austin universality is particularly close to the cutoff in B and D: their best Austin-free joint fractions miss 95% by only **0.0386 and 0.0376 percentage points**. A’s only Austin-free qualifying signature clears it by just **0.0061 percentage points**. In B, Austin-free rosters can independently clear either 95% mean or 95% P90, but no single Austin-free roster clears both. Mandatory status therefore depends on the exact intersection, not only on a large individual-projection gap. All decisions use full precision; rounding these fractions to one decimal place would hide the distinction.',
        'Shough’s **21.658 mean and 32.384 P90** are the pool’s absolute maxima, and his $9,600 salary is below Olave ($10,800), Bijan ($11,800), and London ($10,000). Penix is only $600 cheaper but loses 8.868 mean and 8.782 P90. Bijan and Olave are near-mandatory because they supply premium raw points; they are not cheap relief. Penix becomes universal in F because the balanced six-player construction plus two-QB scoring and its tighter policy maxima constrain alternatives. It is not universally required under A–E.',
        '## Part 4 Shough universality',
        'Both quality dimensions independently exclude every Shough-free A roster at 95%. The best Shough-free mean is 71.047 against 83.513838125, a **12.466813041** deficit. The best Shough-free summed marginal P90 is 136.456 against 145.548896481, a **9.092690836** deficit. Those best values occur in different rosters. The best common quality fraction without Shough is only **80.8186%**, so relaxing to 90% does not remove his universality.',
        '### A best legal lineups with and without Shough',
        '“Best” depends on the objective. Each row below is the exact independent maximum for its criterion. The maximum-selector Shough lineup itself fails the 95% mean floor; selector strength is distinct from joint screen qualification.',
        table(['Condition / objective','Captain','Mean','Summed marginal P90','Selector','Salary','Split','Roster'],
              [[presence+' / '+field,r['captain'],r['mean'],r['p90'],r['selector'],r['salary'],r['team_split'],', '.join(r['players'])]
               for presence,key in [('With Shough','True'),('Without Shough','False')]
               for field in ('mean','p90','selector') for r in [policies['A']['shough_best'][key][field]]]),
        'The best mean with Shough uses Shough CPT, Bijan, Juwan, Olave, Austin, Carlson (ATL 1/NO 5, $50,000). The best mean without him uses Bijan CPT, Penix, Woerner, Olave, Kamara, Carlson (3/3, $49,900). This replaces Shough/Juwan/Austin with Penix/Woerner/Kamara and moves Captain to Bijan. It is a legal construction change, not a one-for-one projection perturbation.',
        'The saved lineup constraints require at least one QB. A Saints WR/TE Captain requires the Saints QB; selecting more than one Saints receiver also requires Shough. Shough CPT requires at least two same-team pass catchers. These rules reduce the options without Shough and are held fixed. In the mean-max Shough roster he correlates with Juwan, Olave, and Austin; the mean-max Shough-free roster has Penix paired with Woerner. The selector separately awards saturated stacks and format/correlation bonuses. The P90-max Shough roster includes Penix without an ATL WR/TE, which is allowed by the saved constraints. No frozen joint score-draw matrix exists, so a numeric fantasy-score correlation is unavailable; these are construction correlations.',
        table(['Policy','Mean95 floor','Best no-Shough mean','Mean gap','P90 95 floor','Best no-Shough P90','P90 gap','Best no-Shough joint fraction'],
              [[k,.95*policies[k]['raw_maxima']['mean'],policies[k]['best_without_player']['Tyler Shough']['best_mean'],policies[k]['shough_best']['False']['independent_threshold_gaps']['mean'],
                .95*policies[k]['raw_maxima']['p90'],policies[k]['best_without_player']['Tyler Shough']['best_p90'],policies[k]['shough_best']['False']['independent_threshold_gaps']['p90'],pct(policies[k]['shough_best']['False']['maximum_joint_fraction'])] for k in 'ABCDEF']),
        'Shough’s universality is mathematically justified **conditional on the frozen projections, salaries, and saved correlation legality**. It is not an independent empirical validation of his football forecast or those correlation rules. His point mean is not unusually inflated by the new opportunity mechanism: that mechanism does not apply to QBs. Removing salary alone still leaves Shough-free A below 95% (best 92.321%). This audit supplies no evidence-based reason to reduce him just because he is universal.',
        '## Part 5 Joint quality floor sensitivity',
        'Each universe table reports all quality-eligible physical signatures. Each portfolio table reports the exact count-first, selector-second solution under the unchanged requested-five caps. The separate frequency table shows both denominators to prevent confusing structural frequency with final allocation. Lower-floor solutions can contain higher-scoring portfolios without raising every average; summed selector is not directly comparable across different portfolio sizes.',
    ]
    focus=['Tyler Shough','Kevin Austin Jr.','Bijan Robinson','Alvin Kamara','Michael Penix Jr.','Chris Olave']
    for label in 'AEB':
        p=policies[label]
        text += [f'### Policy {label} quality universe',
                 table(['Joint floor','Legal physical rosters','Quality signatures','Captains','Players','Pairwise overlap','Average mean','Average P90','Team splits','QB counts'],
                       [[pct(f),p['legal_physical_rosters'],t['quality_universe']['count'],t['quality_universe']['unique_captains'],t['quality_universe']['unique_players'],t['quality_universe']['average_pairwise_overlap'],t['quality_universe']['average_mean'],t['quality_universe']['average_p90'],t['quality_universe']['team_split_distribution'],t['quality_universe']['qb_count_distribution']]
                        for f in FLOORS for t in [p['thresholds'][str(f)]]]),
                 f'### Policy {label} maximum feasible portfolio',
                 table(['Joint floor','Entries','Captains','Players','Pairwise overlap','Average mean','Average P90','Portfolio selector','Team splits','QB counts'],
                       [[pct(f),v['maximum_feasible_count'],m['unique_captains'],m['unique_players'],m['average_pairwise_overlap'],m['average_mean'],m['average_p90'],v['selector'],m['team_split_distribution'],m['qb_count_distribution']]
                        for f in FLOORS for v in [p['thresholds'][str(f)]['portfolio']] for m in [v['metrics']]]),
                 f'### Policy {label} player frequencies',
                 'Each cell is quality-universe frequency / selected-portfolio frequency.',
                 table(['Joint floor']+focus,
                       [[pct(f)]+[pct(t['quality_universe']['player_frequencies'][n])+' / '+pct(t['portfolio']['metrics']['player_frequencies'][n]) for n in focus]
                        for f in FLOORS for t in [p['thresholds'][str(f)]]])]
    text += [
        'A’s eligible signatures increase 22 → 404 between 95% and 90%; E 29 → 415; B 16 → 262. A reaches five at 93%, E at 94%, B at 92%. All still contain Shough. Austin’s universe frequency drops from 95.5% to 64.9% in A, 93.1% to 57.8% in E, and 100% to 65.3% in B. This is screen sensitivity rather than a forecast change.',
        '## Part 6 Which quality dimension binds',
        'Mean-only rejection means mean is below the chosen floor while P90 passes it; P90-only is the converse; both means both fail. The next tables classify **every roster in the fixed joint90 universe** at each higher threshold. This is a consistent cohort, so the categories sum to the 90% count on every row. `analysis_v2.json` also reports all-legal rejection counts and the broader cohort where either dimension clears 90%. Per-signature classifications for the broader cohort are saved in `rejection_band_A.csv.gz` through F.',
    ]
    for label in 'AEB':
        text += [f'### Policy {label} rejection distribution from the joint90 cohort',
                 table(['Floor','Mean only','P90 only','Both','Pass both'],[[pct(f)]+[policies[label]['thresholds'][str(f)]['rejection_within_joint90'][k] for k in ['mean_only','p90_only','both','pass_both']] for f in FLOORS])]
    text += [
        'The screen is a restrictive intersection for A and E. Among A’s 404 joint90 signatures, the 95% floor rejects 315 on both, 36 on mean only, and 31 on P90 only; 22 pass. B is more mean-led: 41 fail mean only versus eight P90 only, with 197 failing both. C’s mean-only universe still has a two-entry capacity, so P90 is not the sole cause of underfill there.',
        table(['Policy','95% mean only','95% P90 only','95% both','Reduction vs mean only','Reduction vs P90 only','Same independent maximizing signature'],
              [[k,policies[k]['thresholds']['0.95']['mean_only_pass'],policies[k]['thresholds']['0.95']['p90_only_pass'],policies[k]['thresholds']['0.95']['quality_universe']['count'],
                pct(1-policies[k]['thresholds']['0.95']['quality_universe']['count']/policies[k]['thresholds']['0.95']['mean_only_pass']),
                pct(1-policies[k]['thresholds']['0.95']['quality_universe']['count']/policies[k]['thresholds']['0.95']['p90_only_pass']),policies[k]['independent_maxima_same_signature']] for k in 'ABCDEF']),
        'A’s independent mean maximum (87.909303) has P90 **144.940106**, below the P90 floor **145.548896** by **0.608790**. Its independent P90 maximum (153.209365) has mean 85.809833 and passes the mean floor. This is a real competing-maximum effect, but the intersection is not empty. E’s independent mean/P90 maxima come from the same roster; nevertheless its intersection falls from 58 mean-only or 83 P90-only signatures to 29. A narrow intersection can therefore occur even without different maximizing rosters.',
        '### Exposure and screen diagnostics at 95%',
        'These are counterfactual research solves. All nonvaried rules and player projections stay fixed; none is a live change.',
        table(['Policy','Current joint95','Mean screen only','P90 screen only','Only Austin cap relaxed','All player caps relaxed','Captain caps relaxed'],
              [[k,policies[k]['thresholds']['0.95']['portfolio']['maximum_feasible_count'],sup[k]['mean_screen_only']['maximum_feasible_count'],sup[k]['p90_screen_only']['maximum_feasible_count'],sup[k]['only_austin_cap_relaxed']['maximum_feasible_count'],policies[k]['cap_ablation95']['no_player_caps'],policies[k]['cap_ablation95']['no_captain_caps']] for k in 'ABCDEF']),
        'Relaxing only Captain caps never improves current 95% capacity. Removing all player caps allows five in each policy. Relaxing only Austin permits five in A/C/E, four in B/D, and three in F. Thus cheap-player exposure is the immediate universal-player bottleneck, while other player caps and construction constraints become relevant after it is lifted. In A/E, a single quality dimension is enough for five under unchanged caps; in B the mean-only screen still limits fill to four.',
        '## Part 7 Mathematical design review',
        'The supplied request stops after “Evaluate whether the current quality screen is mathematically”. The review here addresses the screen’s mathematical interpretation and observed behavior; any missing requested comparison or acceptance criterion remains unspecified.',
        'The joint screen is mathematically well-defined as min(mean/max_mean, summed_marginal_P90/max_summed_marginal_P90) ≥ α. It places a rectangular admissible region in two objective dimensions, with maxima found independently. It is feasible here, reproducible, and sufficient to explain underfill with exposure caps. It does not guarantee a diverse or fillable portfolio, nor do its coordinate maxima incorporate portfolio constraints.',
        '**Summed marginal P90 is not a lineup P90.** Quantiles do not generally add. Summing six player 90th-percentile fantasy outcomes, including the Captain multiplier, aligns marginal tail levels without a joint score distribution. Perfectly aligned monotone outcomes are a special case where they do add; realistic shared targets, touchdowns, team volume, and opponent interactions do not establish that condition. Existing correlation selector terms do not turn the sum into a jointly calibrated 90th percentile. Therefore “95% ceiling quality” is a marginal-tail proxy threshold, not a demonstrated guarantee about lineup ceiling or contest EV.',
        'This proxy can reward pooled residual variance separately from modeled opportunity. Austin’s modest raw tree mean is raised by the opportunity curve and then receives a pooled tail increment; Dotson’s 13.640 P90 versus 3.918 mean is another large residual contribution. Requiring both near-max point mean and near-max sum of residual-based ceilings favors a small set of high-point stars plus efficient salary relief, then exposure caps prohibit repeating that relief often enough.',
        'The separate policy reference maxima mean E and A use different numerical floors: E’s lower constrained maxima partially explain why E admits 29 signatures at 95% versus A’s 22, despite stricter team balance. E’s quality universe need not be a subset of A’s when each is normalized to its own maximum. This is not proof that max-four improves underlying football quality or EV.',
        'A sensible next design experiment would compare a calibrated joint lineup-draw measure, a validated EV/selector regret floor, and the current two-coordinate proxy on historical slates, with portfolio capacity and forecast error reported together. A Pareto or composite-score floor changes the tradeoff and would require explicit validation. The observed 93%/94% fill breakpoints are diagnostics, not justified production defaults. Current player forecast currency should be resolved before attributing every effect to the screen.',
        '## Findings that justify follow-up',
        'The projection arithmetic and optimizer feasibility are confirmed. The current forecasts are not independently established as correct football expectations. Austin’s mismatch between receiving and participation windows is the clearest individual concern. The team allocator normalizes shares from player-specific last-available-record windows, so stale individual windows can also affect the denominator and other receivers. The opportunity curve is a pooled usage anchor, not a route-based player forecast, and the residual calibration has not been walk-forward evaluated through the complete corrected opportunity/market bridge.',
        'Priorities are to verify current receiving-stat coverage through Week 3, distinguish true measured zeros from missing/inactive records, preserve the actual observation periods in role diagnostics, and evaluate the full corrected bridge on time-safe historical replay. Source-confirmed snaps/routes or explicit expected target evidence would clarify whether Austin’s backup role supports four targets. These are proposed future investigations; no forecast correction is asserted or applied here.',
        'The results support **combination** as the answer to the five-way diagnostic: projection/salary structure establishes Austin and Shough value, the joint95 screen makes alternative signatures scarce, and the requested-five player caps convert scarcity into underfill. The evidence does not establish that one aggressive forecast alone caused the problem, and it does not support reducing Shough solely for universality.',
        '## Validation and reproducibility',
        'All six policy raw maxima, 95% signature counts, maximum portfolio counts, and optimal selectors match the earlier independent corrected certificates within 1e-6. Every previously retained signature score agrees with the full enumeration, and 101 deterministic full-universe legal samples agree with the scalar certifier. An additional 151 samples of the entire assignment space verify both acceptance and rejection (17 accepted, 134 rejected). All 23 fitted-artifact mean/P90 bridges reproduce the saved corrected forecasts within 1e-6. Each selected research portfolio satisfies unique signatures and the original player/Captain caps.',
        'The two existing tests in `backend/app/tests/product/test_showdown_policy_audit.py` pass. Both new research scripts compile, and `git diff --check` passes. Delivery/source checksums, 23 decomposition rows, 138 policy/player rank rows, 30 threshold/denominator rows, all rejection partitions, and selected-witness quality thresholds were independently checked.',
        'No application or optimizer source was edited in this task. Database source reads ran in explicitly read-only transactions. The audit added research scripts, immutable/checksummed JSON artifacts, compressed full-universe arrays, diagnostic CSVs, and this report. The broad working-tree changes already present in the repository belong to earlier work and are not part of this audit.',
        'Run `.venv/bin/python -m scripts.audit_atl_no_projection_landscape --stage capture` to reproduce fitted-artifact/source reads, then `.venv/bin/python -m scripts.audit_atl_no_projection_landscape` for enumeration/analysis and `.venv/bin/python -m scripts.render_atl_no_projection_landscape` for supporting diagnostics and report tables. Existing JSON artifacts are immutable; use a fresh output directory or matching existing captures for a new run. The fitted artifact and local database are required only for the capture stage.',
        'Supporting artifacts: `projection_bridge.json` (all inputs and exact stages), `prior_usage.json` (canonical raw stat/participation evidence), `analysis_v2.json` (all A–F threshold and rank results), `supplementary.json` (single-dimension/cap diagnostics), `full_universe.npz` (all certified signatures), `player_efficiency.csv`, `player_rank_frequencies.csv`, `projection_decomposition.csv`, `threshold_metrics.csv`, and per-policy compressed rejection files. Data and code hashes are retained in JSON/manifest files.',
    ]
    report=ROOT/'ATL_NO_CORRECTED_PROJECTION_LANDSCAPE_AUDIT.md'
    report.write_text('\n\n'.join(text)+'\n')
    with (DEST/'player_rank_frequencies.csv').open('w') as f:
        w=csv.writer(f);w.writerow(['policy','player_id','player','joint95_frequency','top1_frequency','top5_frequency','top10_frequency','top25_frequency'])
        for label,p in policies.items():
            for row in players:
                w.writerow([label,row['player_id'],row['name'],p['thresholds']['0.95']['quality_universe']['player_frequencies'][row['name']]]+[p['selector_rank_frequencies'][str(q)]['player_frequencies'][row['name']] for q in (.01,.05,.1,.25)])
    with (DEST/'projection_decomposition.csv').open('w') as f:
        fields=['player_id','player','team','position','role','history_records','fp_prior3','fp_prior8','snap_share3','expected_snaps','expected_routes','targets_prior3','targets_modeled','carries_prior3','carries_modeled','target_share','carry_share','raw_tree','history_anchor','base_blend','opportunity_anchor','opportunity_weight','opportunity_delta','market_delta','mean','residual_p90','p90','history_fallback','calibration_group','residual_samples']
        w=csv.writer(f);w.writerow(fields)
        for p in bplayers:
            t=p['target_features'];r=pool[p['player_id']];o=p['opportunity']
            w.writerow([p['player_id'],p['name'],r['player_team'],r['position'],t.get('expected_depth_role'),t['player_games_history'],t['player_roll3_mean'],t['player_roll8_mean'],t['snap_share_mean_3'],t.get('pregame_expected_snaps'),t.get('pregame_expected_routes'),t.get('pregame_base_targets_mean_3'),t.get('projected_targets'),t.get('pregame_base_carries_mean_3'),t.get('projected_carries'),t.get('target_share_mean_3'),t.get('carry_share_mean_3'),p['raw_tree_mean'],p['history_anchor'],p['base_blended_mean'],o['pregame_opportunity_point_anchor'],o['pregame_opportunity_point_weight'],o['pregame_point_mean_after_opportunity']-p['base_blended_mean'],p['market_residual_adjustment'],p['mean'],p['p90']-p['mean'],p['p90'],p['history_fallback'],p['calibration_key'],p['calibration_profile']['sample_size']])
    with (DEST/'threshold_metrics.csv').open('w') as f:
        w=csv.writer(f);w.writerow(['policy','floor','denominator','legal_rosters','quality_signatures','count','captains','players','pairwise_overlap','mean','p90','portfolio_selector']+focus+['team_split_distribution','qb_count_distribution'])
        for label in 'AEB':
            for floor in FLOORS:
                t=policies[label]['thresholds'][str(floor)]
                for denominator,m in [('quality_universe',t['quality_universe']),('portfolio',t['portfolio']['metrics'])]:
                    w.writerow([label,floor,denominator,t['legal_physical_rosters'],t['quality_universe']['count'],m['count'],m['unique_captains'],m['unique_players'],m['average_pairwise_overlap'],m['average_mean'],m['average_p90'],t['portfolio']['selector'] if denominator=='portfolio' else None]+[m['player_frequencies'][n] for n in focus]+[str(m['team_split_distribution']),str(m['qb_count_distribution'])])
    hashes={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in [report,Path(__file__),ROOT/'scripts/audit_atl_no_projection_landscape.py',DEST/'analysis_v2.json',DEST/'projection_bridge.json',DEST/'prior_usage.json',DEST/'supplementary.json',DEST/'full_universe.npz']}
    (DEST/'delivery_manifest.json').write_text(__import__('json').dumps(dict(projection_run_id=s['projection_run_id'],sha256=hashes),indent=2,sort_keys=True)+'\n')
    print(report)


if __name__=='__main__':main()
