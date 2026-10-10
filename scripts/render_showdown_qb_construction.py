"""Render the saved standings research tables into a reviewable Markdown report."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/showdown_qb_construction'


def pct(v):
    if v is None:return 'Unavailable'
    return f'{100*float(v):.4f}%' if 0<abs(float(v))<.001 else f'{100*float(v):.2f}%'
def num(v):return 'Unavailable' if v is None else f'{float(v):.2f}'
def count(v):return 'Unavailable' if v is None else f'{int(v):,}'
def ci(v,percentage=False):
    return 'Unavailable' if not v else ('–'.join(pct(x) if percentage else num(x) for x in v))
def rows(name):return list(csv.DictReader((OUT/(name+'.csv')).open()))
def numeric(row):
    result={}
    for k,v in row.items():
        try:result[k]=float(v) if v else None
        except ValueError:result[k]=v
    return result
def table(headers,data):
    return ['| '+' | '.join(headers)+' |','| '+' | '.join('---' for _ in headers)+' |']+['| '+' | '.join(str(v) for v in row)+' |' for row in data]+['']


def main():
    d=json.loads((OUT/'analysis.json').read_text());inventory=d['inventory'];audits=d['contest_audits']
    primary={r['group']:r for r in d['entry_weighted'] if r['season']=='pooled'}
    cw={r['group']:r for r in d['contest_weighted']};cis={r['group']:r for r in d['rate_confidence_intervals']}
    groups=['QB Captain','Non-QB Captain','Both QBs','Exactly one QB','Zero QB','QB Captain + both QBs',
            'QB Captain + one QB','Non-QB Captain + both QBs','Non-QB Captain + one QB','Non-QB Captain + zero QB']
    major=['QB Captain','Both QBs','QB Captain + both QBs']
    lines=['# DraftKings NFL Showdown QB Construction Analysis','',
        '## Executive summary','',
        '**Decision: retain current optimizer rules. These standings do not support a general QB-Captain penalty, a two-QB penalty, or a prohibition of QB Captain + both starting QBs.** They also do not validate the current optimizer weights. This is an observational analysis of the locally stored contests, with a small number of independent games.','',
        f'1. **QB Captain: efficiency is unresolved.** Field usage is {pct(primary["QB Captain"]["field_share"])}; pooled top-10% lift is {num(primary["QB Captain"]["top10_lift"])}×. Equal-contest mean lift is {num(cw["QB Captain"]["mean_top10_lift"])}×, with game-clustered 95% interval {ci(cw["QB Captain"]["mean_top10_lift_game_bootstrap_95"])}×. Neither “overused” nor “underused” is established across games.',
        f'2. **Both starters: no stable underperformance at top 10% or top 1%.** Usage is {pct(primary["Both QBs"]["field_share"])}; entry-weighted top-10% lift is {num(primary["Both QBs"]["top10_lift"])}×, equal-contest mean {num(cw["Both QBs"]["mean_top10_lift"])}×. Actual first-place rates are much weaker; duplication is higher. This distinction prevents calling the construction tournament-efficient.',
        f'3. **QB Captain + both starters is not generally shown to be weak.** Its top-10% rate is {pct(primary["QB Captain + both QBs"]["top10_rate"])} and pooled lift {num(primary["QB Captain + both QBs"]["top10_lift"])}×. The 2025 top-10% lift is 3.37× across only two usable games, versus 0.89× across eight 2026 games. The result is unstable across seasons and starter-evidence cohorts.',
        '4. **The evidence is not strong enough to justify changing production rules.** Only 12 games support the Captain analysis and 10 support both-starter comparisons. Major top-10% pairwise intervals mostly include zero absolute difference; every available Holm-adjusted top-10%/top-1% sign-flip p-value exceeds 0.05. This is limited directional evidence, not proof of no effect.',
        '5. **Recommended next optimizer treatment: no scoring/eligibility change.** Collect more independent completed games with archived starter identity and exact payout economics, then test a modest exposure cap or soft adjustment in a frozen, chronological shadow replay. First-place/duplication-aware validation is the priority. The current data does not establish the sign or size of a penalty.','',
        '## Data actually available','',
        f'The read-only snapshot contains {count(inventory["all_contests"])} normalized contests. Actual six-slot Showdown standings are present in **{count(inventory["showdown_files"])} files, {count(inventory["loaded_entries"])} entries, and {inventory["games"]} salary-dated NFL games**. {count(inventory["resolved_entries"])} entries ({pct(inventory["resolved_entries"]/inventory["loaded_entries"])}) have fully parsed, uniquely resolved, structurally valid rosters; salary legality is checked where native Showdown salaries exist. The other {count(inventory["loaded_entries"]-inventory["resolved_entries"])} entries have blank/malformed lineups and remain in the coverage audit.','',
        f'The starting-QB cohort contains {count(inventory["starter_eligible_entries"])} entries in {inventory["starter_eligible_contests"]} contests / 10 games, after uncertain starter slates and nonstarter QB rosters are excluded. Each roster is counted once per actual entry, including repeated physical lineups. Contest IDs inferred by the old importer from source content are retained as synthetic local IDs; they cannot be assumed to match live DraftKings contest economics.','',
        '**There are no stored 2024 contest standings.** The 2024 actual-score oracle is not a substitute. Four 2025 contests and 24 2026 contests are available; only two 2025 games qualify for both-starter analysis. No older standings were found in the normalized or legacy inventory. Legacy CPT files have matching normalized season/week/slate inventory; legacy data is not added again. These are the contests available locally, not a representative sample of all DraftKings Showdowns.','',
        'The season/format labels are source/import labels, not independently authenticated historical contest records. Six slots, distinct players, two opposing teams and available native Showdown salaries are checked. Historical scoring-rule version is not stored, so era equivalence is not certified; season results are kept separate and no older eras are silently pooled.','',
        '### Coverage and starter provenance by game','']
    game_audits=defaultdict(list)
    for c in audits:game_audits[c['game_key']].append(c)
    lines+=table(['Game','Files','Loaded / resolved','Starting-QB evidence','Winner entries / distinct winning rosters'],[
        [game,len(cs),f'{count(sum(c["loaded_entries"] for c in cs))} / {count(sum(c["resolved_entries"] for c in cs))}',
         '; '.join(f'{p["name"]}: {p["method"]}' for p in cs[0]['starters']) or 'Uncertain; excluded from starter cohort',
         f'{sum(c["first_place_tie_size"] for c in cs)} / {sum(c["unique_winning_rosters"] for c in cs)}'] for game,cs in sorted(game_audits.items())])
    lines += [
        'Winning-roster counts in this table are summed per contest; the same physical winner may occur in several contests on one game. Counts of tied-first entries are not counts of independent winning events.','',
        '### Specific corrections and exclusions','',
        '- The 2025 file labeled Week 6 / SUNDAY_LATE resolves completely to the preserved **Week 5 KC–JAX Monday game**, dated October 6, 2025 in the salary game information and matched schedule. The analysis uses that game as its cluster and uses only pre-Week-5 statistics for starter/role inference. The original source labels remain intact.',
        '- Week 3 2026 THURSDAY_NIGHT curated salary rows were overwritten by a later 671-row import. The original **106 raw DK salary rows** from ingest `ed209cc0-fe7e-45a9-ac8f-7a7be79896cf`, checksum `cdaba70ab3cac21c18d88bd73fdc5fce1caad8e26554a720e4bccdd956db44d2`, were recovered for research. Source-native IDs link them to existing canonical aliases; no database record was repaired.',
        '- The 2025 Week 8 MIN starter remains uncertain. The higher-salary QB does not satisfy the prior-volume rule. That game remains in the Captain-position analysis but is excluded from both-starter/combination analyses.',
        '- The 2025 Week 13 CIN–BAL file has Classic Thanksgiving salaries, not a retained Showdown salary grid. Its rosters can be identified using the specific game/team/position salary and alias universe, including team-constrained kicker aliases, but salary-cap validation is unavailable. Both starter identities remain uncertain and the game is excluded from starter-dependent results.',
        '- Some Week 1 Sunday and Week 2 Sunday starter rows were stored after kickoff. A claimed earlier observation inside those rows is insufficient; those rows are rejected. A separately labeled salary/prior-volume inference may qualify the slate. No current-game usage, schedule QB-name field, or actual-score optimality identifies a starter.','',
        'Identity joins require the selected source salary slate and matchup, native/canonical IDs, team and position. Normalized-name matching is only a candidate lookup inside that constrained universe. Conflicting IDs are quarantined. Alias fallback supplies identity only, never missing salary, availability or starter status.','',
        '## Definitions and statistical method','',
        '**Successful-lineup share:** `successful entries with X / all successful entries in the eligible cohort`. **Success rate:** `successful entries with X / all entries using X`. **Lift/performance index:** `success rate of X / success rate of the full eligible cohort`, algebraically equal to `successful-lineup share / field usage share`. **Odds ratio:** `(success_X / failure_X) / (success_comparator / failure_comparator)`. Zero comparator successes produce an unavailable/infinite-limit ratio; no arbitrary continuity correction is applied.','',
        'Rank cutoffs use `floor(N × fraction)` of the complete contest field, with all competition-rank ties at the boundary included. Consequently, the realized top-10% rate can exceed 10%. Top 0.1% is available only for fields of at least 1,000; top 1% requires at least 100. Tiny contests are not relabeled as top 0.1% simply because they have a winner. Each cutoff’s conditional rates and lift use only supported contests; cutoff-specific field shares and denominators are exported. The Captain-position share index uses its displayed all-field usage, which differs slightly from the cutoff-eligible lift when tiny contests are excluded. A fractional boundary-tie sensitivity allocates the remaining threshold positions proportionally within the tied block.','',
        'Average/median finish percentile uses the full-field **tie midrank / N × 100**, with lower values better. Winners are entries with actual standings rank 1, including ties. Optimizers/oracles do not supply any success outcome.','',
        'Captain and position tables use complete resolved rosters. Starter/combination tables additionally require two identified expected starters and no backup/gadget/emergency QB. These populations differ: Captain metrics use 900,342 entries; starter metrics use 733,434. An excluded backup is not a zero-QB roster. Group counts partition their own cohort; groups across these cohorts should not be added together.','',
        'Entry-weighted pooling gives each entry equal weight. Equal-contest results compute each contest metric first and report its mean, median, IQR and outperforming count. Bootstrap intervals resample **NFL games**, retaining all contests on each sampled game together (4,000 draws; seed 20261005). Pairwise rates use only contests with both constructions represented. Exact paired game-level sign flips are diagnostic under a symmetric null; Holm adjustment covers all available major top-10%/top-1% comparisons. P-values use a game-mean paired effect, whereas entry-weighted intervals use a pooled entry effect; they answer different estimand questions.','',
        'There are only 10–12 independent clusters. Bootstrap intervals and p-values are exploratory, not precise guarantees. Repeated entries/users, endogenous construction choice, slate differences and contest-type selection prevent causal inference. No binomial test treating 900,000 entries as independent is used.','',
        '## Frequency among successful entries (A, B, E)','',
        'Percentages below are shares within the complete classified cohort for that row. They answer how prevalent the construction is among successful entries.','']
    lines+=table(['Construction','Entries','Field usage','Top 20 share','Top 10 share','Top 5 share','Top 1 share','Top 0.1 share','Winner share'],[
        [g,count(primary[g]['entries']),pct(primary[g]['field_share']),*[pct(primary[g][m+'_share']) for m in ['top20','top10','top5','top1','top01','winner']]] for g in groups[:5]])
    lines+=['## Conditional success and combined construction (A–C)','',
        'These percentages answer how likely an entry using the construction was to achieve the specified finish. Relative lift compares with its own eligible full field.','']
    lines+=table(['Construction','Entries','Field usage','Avg / median percentile','Top 20 rate','Top 10 rate','Top 5 rate','Top 1 rate','Winner rate','Lift top 10 / top 1'],[
        [g,count(primary[g]['entries']),pct(primary[g]['field_share']),f'{num(primary[g]["average_percentile"])} / {num(primary[g]["median_percentile"])}',
         *[pct(primary[g][m+'_rate']) for m in ['top20','top10','top5','top1','winner']],f'{num(primary[g]["top10_lift"])}× / {num(primary[g]["top1_lift"])}×'] for g in groups])
    lines+=['The complete underlying table also contains top-0.1% rates, every success count/denominator, economic coverage and fractional-tie lift: [summary.csv](artifacts/showdown_qb_construction/summary.csv). The five combination groups are disjoint and exhaustive within the starter-eligible cohort.','',
        '### All-entry missing-roster bounds','',
        'Complete-case estimates above cannot assign a construction to blank rosters. All-entry usage below assigns every unknown roster away from, then to, the construction. Success-rate bounds separately allocate unknown successes and unknown failures. These are deterministic missingness bounds, not confidence intervals.','']
    bounds=[numeric(r) for r in rows('missing_roster_bounds')]
    lines+=table(['Construction','Full contest entries / unknown','All-entry usage interval','Top 10 conditional-rate interval','Unknown top-10 successes'],[
        [g, f'{count(sum(r["full_entries"] for r in bounds if r["group"]==g))} / {count(sum(r["unknown_rosters"] for r in bounds if r["group"]==g))}',
         ci([sum(r['known_group_entries'] for r in bounds if r['group']==g)/sum(r['full_entries'] for r in bounds if r['group']==g),
             sum(r['known_group_entries']+r['unknown_rosters'] for r in bounds if r['group']==g)/sum(r['full_entries'] for r in bounds if r['group']==g)],True),
         ci([sum(r['top10_known_success'] for r in bounds if r['group']==g)/sum(r['known_group_entries']+r['unknown_rosters']-r['top10_unknown_success'] for r in bounds if r['group']==g),
             sum(r['top10_known_success']+r['top10_unknown_success'] for r in bounds if r['group']==g)/sum(r['known_group_entries']+r['top10_unknown_success'] for r in bounds if r['group']==g)],True),
         count(sum(r['top10_unknown_success'] for r in bounds if r['group']==g))] for g in major])
    lines+=['No unknown roster is top 10%, top 1%, or tied first in these exports. Blank rosters mostly have zero scores; removing them modestly raises the classified-field baseline. For starter rows, all-entry exposure refers only to the contests with identified starters, and retains known nonstarter-QB rosters in the exposure denominator. Full per-contest bounds are in [missing_roster_bounds.csv](artifacts/showdown_qb_construction/missing_roster_bounds.csv).','',
        '## Captain-position baseline (D)','']
    lines+=table(['Captain position','Field usage','Top 10 share','Top 1 share','Winner share','Index top 10','Index top 1','Index winner'],[
        [g.removeprefix('CPT '),*[pct(primary[g][m]) for m in ['field_share','top10_share','top1_share','winner_share']],
         *[num(primary[g][m+'_share']/primary[g]['field_share'])+'×' for m in ['top10','top1','winner']]] for g in primary if g.startswith('CPT ')])
    lines+=['## Contest-weighted and statistical comparisons (F, K)','']
    lines+=table(['Construction','Contests / games','Entries','Mean top 10 rate','Mean lift','Median lift','Lift IQR','Outperformed field','95% CI mean lift'],[
        [g,f'{cw[g]["contests"]} / {cw[g]["games"]}',count(cw[g]['entries']),pct(cw[g]['mean_top10_rate']),num(cw[g]['mean_top10_lift'])+'×',num(cw[g]['median_top10_lift'])+'×',
         ci(cw[g]['top10_lift_iqr']),f'{cw[g]["contests_outperforming"]}/{cw[g]["contests"]} ({pct(cw[g]["contests_outperforming_share"])})',ci(cw[g]['mean_top10_lift_game_bootstrap_95'])] for g in groups])
    lines+=['A construction absent from a contest has an undefined conditional success rate; that contest is omitted from that row’s mean/median/IQR. Thus the 25-contest rows do not have the same denominator as the 26-contest rows. The pooled field exposure still includes zero exposure in otherwise eligible contests.','',
        '### Game-clustered rate and lift intervals','']
    lines+=table(['Construction','Top 10 rate 95% CI','Top 10 lift 95% CI','Top 1 rate 95% CI','Top 1 lift 95% CI','Winner lift 95% CI'],[
        [g,ci(cis[g]['top10_rate_game_bootstrap_95'],True),ci(cis[g]['top10_lift_game_bootstrap_95']),
         ci(cis[g]['top1_rate_game_bootstrap_95'],True),ci(cis[g]['top1_lift_game_bootstrap_95']),ci(cis[g]['winner_lift_game_bootstrap_95'])] for g in groups[:8]])
    for metric,label in [('top10','Top 10%'),('top1','Top 1%')]:
        lines+=['### '+label+' paired comparisons','']
        lines+=table(['Comparison A vs B','Games','N A / N B','Rate A / B','Difference (pp), 95% CI','Rate ratio','Odds ratio, 95% CI','Game p / Holm p'],[
            [r['a']+' vs '+r['b'],r['paired_games'],f'{count(r["a_entries"])} / {count(r["b_entries"])}',f'{pct(r["a_success_rate"])} / {pct(r["b_success_rate"])}',
             f'{num(100*r["absolute_difference"])}; {ci([100*v for v in r["absolute_difference_game_bootstrap_95"]])}',
             num(r['relative_rate']),f'{num(r["odds_ratio"])}; {ci(r["odds_ratio_game_bootstrap_95"])}',
             f'{num(r["game_sign_flip_p"])} / {num(r.get("holm_adjusted_p"))}'] for r in d['comparisons'] if r['metric']==metric and r['status']!='unavailable'])
    lines+=['Relative-rate intervals, contest-weighted paired differences and their intervals are also stored in [comparisons.csv](artifacts/showdown_qb_construction/comparisons.csv). A bootstrap interval excluding zero in an isolated comparison does not override small-cluster, multiple-comparison and season-instability concerns.','',
        '## Season and sensitivity checks (L)','',
        '2024: unavailable, not zero success. 2025 and 2026 rows are actual standings under their stored source-season labels.','']
    lines+=table(['Season','Construction','Contests / games','Entries','Field usage','Top 10 rate / lift','Top 1 rate / lift','Winner rate'],[
        [r['season'],r['group'],f'{r["contests"]} / {r["games"]}',count(r['entries']),pct(r['field_share']),f'{pct(r["top10_rate"])} / {num(r["top10_lift"])}×',
         f'{pct(r["top1_rate"])} / {num(r["top1_lift"])}×',pct(r['winner_rate'])] for r in d['entry_weighted'] if r['season'] in (2025,2026) and r['group'] in major])
    lines+=table(['Sensitivity','Construction','Games','Top 10 lift','Top 1 lift'],[
        [r['sensitivity'],r['group'],r['games'],num(r['top10_lift'])+'×',num(r['top1_lift'])+'×'] for r in d['sensitivities'] if r['sensitivity']!='leave_one_game_out' and r['group'] in major])
    lines+=table(['Construction','Boundary-tie lift top 10','Fractional-tie lift top 10','Boundary-tie lift top 1','Fractional-tie lift top 1','Leave-one-game-out top 10 lift range'],[
        [g,num(primary[g]['top10_lift']),num(primary[g]['top10_fractional_lift']),num(primary[g]['top1_lift']),num(primary[g]['top1_fractional_lift']),
         ci([min(r['top10_lift'] for r in d['sensitivities'] if r['group']==g and r['sensitivity']=='leave_one_game_out'),
             max(r['top10_lift'] for r in d['sensitivities'] if r['group']==g and r['sensitivity']=='leave_one_game_out')])] for g in major])
    lines+=['The archived-starters-only sensitivity has 19 contests but just six games; all starter records in that subset are still inferred, not final independent confirmation of kickoff starters. Reconstructed starter inference adds two 2025 games and two 2026 games. Its very different mix explains why pooled success should not be promoted into a general rule. Leave-one-game-out pooling stays positive at top 10%, but that does not resolve the broader 2025-versus-2026 reversal.','',
        '## Slate characteristics (G)','',
        '**All strata are exploratory.** The CSV includes group counts, rates, field shares, success shares, lift and number of contests/games within each stratum. The full set is [exploratory_summary.csv](artifacts/showdown_qb_construction/exploratory_summary.csv), with per-contest inputs in [exploratory.csv](artifacts/showdown_qb_construction/exploratory.csv). The selected tables below show the main QB exposures and their conditional rates.','',
        'Three games have hash-verified market CSV snapshots with both observed and captured timestamps before kickoff (2026 ATL–GB, CLE–PIT, CAR–DET). Those are the pregame market strata. Retrospective schedule closing lines cover more games and are reported separately as audit-only; they do not establish what a historical optimizer knew. A winning-team label is inherently postgame and audit-only.','']
    exploratory=[numeric(r) for r in rows('exploratory_summary')]
    for dims,title in [({'game_total_pregame','spread_pregame','favorite_captain_pregame'},'Pregame-supported total, spread and favorite'),
                       ({'captain_archetype'},'QB rushing archetype'),
                       ({'captain_qb_salary','combined_starting_qb_salary'},'Salary level'),
                       ({'team_split'},'5–1, 4–2 and 3–3 team construction'),
                       ({'winning_team_captain_audit'},'Winning versus losing team QB Captain (audit only)'),
                       ({'game_total_audit','spread_audit','favorite_captain_audit'},'Retrospective schedule markets (audit only)')]:
        lines+=['### '+title,'']
        subset=[r for r in exploratory if r['dimension'] in dims and r['group'] in major]
        lines+=table(['Dimension','Bucket','Construction','Games','Entries','Top 10 rate','Top 1 rate'],[
            [r['dimension'],r['bucket'],r['group'],count(r['games']),count(r['entries']),pct(r['top10_rate']),pct(r['top1_rate'])] for r in subset])
    lines+=['There are no pregame-supported 43–49 total or >7 spread games in this sample. Historical pregame large-favorite comparisons remain unavailable. Archetypes use the mean carries in the last up-to-three completed regular-season games: pocket ≤1.67, mobile (1.67, 3.33], high-rush >3.33; these fixed descriptive cutoffs approximate existing research buckets. They do not measure designed runs, scramble rate or goal-line role. Unknown/sparse prior history is retained and sample sizes are shown. No fitted effect or rushing-specific penalty is warranted.','',
        'QB salary is FLEX salary. Combined starting-QB salary is the sum of the two FLEX salaries divided by the $50,000 cap, a slate affordability measure. If one QB is Captain, the actual two-QB roster cost adds another half of that QB’s FLEX salary. Missing Showdown salaries remain unknown; Classic salaries are not substituted. Favorite/archetype/which-team Captain strata condition on QB-Captain entries, so their baseline is that stratum rather than all non-QB Captains. Within a bucket several contests can still represent one underlying game.','',
        'Winning-team labels cannot be used as pregame optimizer conditions. The CAR–DET schedule record lacks final team scores, so its winning/losing-team label remains unknown even though final contest standings are available.','',
        '## Duplication, wins and payouts (H, I)','',
        'Duplicate signatures preserve canonical Captain identity and sort the five FLEX identities. Different FLEX orderings are the same lineup; the same six players with a different Captain are different lineups. Counts below are entry-weighted total copies including the entry itself (additional opponents = copies − 1), within each contest. Uniqueness means exactly one copy.','']
    lines+=table(['Construction','Mean copies','Median copies','Unique entries','Top 10 entries duplicated','Tied-first entries','Median first-place chop size'],[
        [g,num(primary[g]['average_duplicates']),num(primary[g]['median_duplicates']),pct(primary[g]['unique_entry_share']),pct(primary[g]['top10_duplicate_entry_rate']),
         count(primary[g]['winner_count']),num(primary[g]['first_place_chop_median'])] for g in groups])
    lines+=['**Top-percentile strength does not imply first-place or payout strength.** Both-QB entries have higher pooled top-10% and top-1% rates, yet much lower actual winner rates. A handful of tied winning rosters can create many winning entries in the one-QB group. The winner index and clustered intervals are shown separately; this is a reason to investigate tournament value rather than optimize solely for top-10% frequency.','',
        'No normalized historical payout tiers are stored. One exact-native match, contest **195943257**, has a complete cash ladder, entry fee $1 and field size 8,917 in a saved observation. ROI below is reconstructed for that one contest only, with 8,871 classified entries; it is not an overall historical ROI estimate. Tied scores share the sum of prizes at all occupied ranks, including ties involving different rosters. This follows [DraftKings tie rules](https://support.draftkings.com/dk/en-us/what-happens-when-i-tie-with-others-in-a-fantasy-sports-contest?id=kb_article_view&sysparm_article=KB0010633). Six-player roster and Captain conventions follow [DraftKings Showdown overview](https://support.draftkings.com/dk/en-us/game-style-showdowns-overview?id=kb_article_view&sysparm_article=KB0010694).','']
    lines+=table(['Construction','Economic entries','Reconstructed ROI (one game)','Average cash reduction from all score ties'],[
        [g,count(primary[g]['economic_entries']),pct(primary[g]['roi']),'$'+num(primary[g]['payout_impact'])] for g in groups])
    lines+=['The reduction compares the prize at an entry’s displayed starting rank with its split payout. It includes all score ties and cannot attribute the loss exclusively to identical-lineup duplication. There is no calibrated ex ante win probability or payout distribution, so **expected future payout impact remains unavailable**. Zero-QB profitability on this single game does not outweigh its weaker top-percentile rates across games.','',
        'Actual-score optimum, actual rank-1 roster, top 1%, and top 10% are separate concepts throughout. The existing oracle’s 45 games (22 in 2024, 18 in 2025, five in 2026) and 11 QB optimal Captains are background only; zero oracle results enter any standings numerator or denominator.','',
        '## Current optimizer audit (O)','',
        'This is a review of the working-tree implementation and frozen saved-output inventory, not a controlled causal backtest of those rules. Production files were already modified before this task, and a concurrent optimizer edit was detected during final checks. The reviewed QB mechanisms were rechecked after that edit. Audited source copies and hashes are retained under `artifacts/showdown_qb_construction/audited_code/` and `source_hashes.json`; later working-tree edits do not change this audit. No optimizer rule, projection, default, job or database state was changed by this research task.','',
        '### Confirmed code mechanisms','',
        '- `build_showdown_captain_prior` multiplies Captain selector score by `(1−s) + s × max(0.05, class_count × position_probability)`. Configured strength is **0.35** and the artifact is `docs/showdown_captain_model_2024_2025.json`. It predicts actual-score optimal Captain position, not realized contest success or payout. In the historical-mix fallback (five model classes), QB 24.39% becomes **1.07683×** and WR 41.46% becomes **1.37561×**. QB receives positive credit, but WR receives substantially more. A rushing-specific prior in the newer oracle remains shadow-only.',
        '- The strategy hard-correlations branch requires a team’s starting QB if two same-team WR/TE are selected; WR/TE Captain also requires that team’s QB. Pocket QB Captain requires two own WR/TE, while high-rush QB Captain requires one. This can indirectly pull the opposing QB into a lineup when the opposing pass-catcher stack reaches two.',
        '- A `shootout` script directly requires a QB on **each** team. The legacy five-lineup v3 script schedule has two shootout slots out of five. That is a structural two-QB requirement in those solves, not an empirical demonstration of tournament superiority. Later candidate portfolio selection can alter which discoveries are actually selected.',
        '- Modern v3/single-entry/three-max/small-max paths saturate positive correlation rewards: **0.60 + 0.30 + 0.10** for the first three pass catchers and **0.45** for one opposing WR/TE bring-back per selected QB, before QB-quality scaling. With both QBs selected, each team can activate its own reward set (maximum 1.45 per QB). Generic QB/pass-catcher, bring-back, opposing-pass-catcher and QB/receiver-Captain pair bonuses are removed in the saturated path. They are not all stacked together there.',
        '- The bring-back soft reward targets opposing WR/TE, not the opposing QB directly. There is no basis for asserting that a QB Captain automatically forces both QBs in every strategy. Historical versions, cash paths and current paths differ. Individual starting-QB exposure defaults can be 100%; that is not a joint two-QB portfolio cap.','',
        'Relevant functions are in [optimizer.py](backend/app/product_services/optimizer.py), [lineup_correlation_scoring.py](backend/app/product_services/lineup_correlation_scoring.py) and [showdown_portfolio_selection.py](backend/app/product_services/showdown_portfolio_selection.py). Model evaluation in the configured Captain artifact reports 41 slates, 33 walk-forward evaluations and optimal-position accuracy lift; these metrics do not validate top-1% finish, first place, ROI or duplication.','',
        '### Quantified saved-output effect','']
    opt=[numeric(r) for r in rows('optimizer_lineups')];runrows=[numeric(r) for r in rows('optimizer_runs')]
    unique={(r['season'],r['week'],r['slate'],r['roster_signature']):r for r in opt}
    v3=[r for r in opt if r['strategy']=='showdown_gpp_portfolio_v3']
    lines += [f'Across **{len(runrows)} saved runs / {len(opt)} saved six-slot lineups**, QB Captain occurs in {pct(d["optimizer_summary"]["qb_captain_share"])}, two positional QBs in {pct(d["optimizer_summary"]["two_qb_position_share"])}, and QB Captain + two positional QBs in {pct(d["optimizer_summary"]["qb_captain_two_qb_share"])}. These are repeated local runs, not independent contests or verified submissions. One older roster has three positional QBs and stays in an “other QBs” audit row. Starting identities are not retroactively assumed for every saved run.','',
        f'The {len(v3)} saved v3 lineups contain two positional QBs in {pct(sum(r["qb_count_position_audit"]==2 for r in v3)/len(v3))}. Deduplicating physical roster by stored season/week/slate leaves {len(unique)} rosters overall. Saved-output exposure is much larger than the historical field’s two-starter exposure, but mixes slates, objectives and versions; it is an overconcentration diagnostic, not proof of a negative expected return.','']
    grouped=defaultdict(list)
    for r in opt:grouped[r['group']].append(r)
    lines+=table(['Saved construction (positional QB audit)','Lineups','Avg Captain-prior contribution','Avg correlation contribution','Captain multiplier range'],[
        [g,len(rs),num(sum(r['captain_prior_score_contribution'] for r in rs)/len(rs)),num(sum(r['correlation_contribution'] or 0 for r in rs)/len(rs)),
         ci([min(r['captain_multiplier'] for r in rs),max(r['captain_multiplier'] for r in rs)])] for g,rs in sorted(grouped.items())])
    rr=rows('optimizer_candidate_rerank');counts=Counter((r['adjustment_removed'],r['rank_changed']) for r in rr)
    lines+=['Saved quality-eligible candidate sets are available in **19 runs**. Holding those candidates and their quality eligibility fixed, removing reported score components produces the following individual-best-candidate rank changes. This does not regenerate candidates or reoptimize exposure-feasible portfolios.','']
    lines+=table(['Removed score contribution','Changed best rank','Unchanged best rank'],[[g,counts[g,'True'],counts[g,'False']] for g in ['correlation','captain_position_prior_contribution','both']])
    lines+=['Of these 19 reports, nine have complete canonical candidate-position coverage sufficient to classify both compared rosters. Among those nine, removing Captain-position prior changes every best candidate: two move from non-QB Captain/two QBs to non-QB Captain/one QB, and seven move **toward QB Captain/two QBs**. Removing correlation alone changes none of those nine constructions. The other ten reports have insufficient complete candidate roster identity for this construction comparison, though their stored rank changes remain observable.','',
        'This directly cautions against the claim that the current prior is uniquely inflating QB Captain. The confirmed issue is a surrogate objective and substantial two-QB generation pressure, with effect sizes attributable to constraints versus scores not isolated by an end-to-end historical A/B. A same-pool, same-policy, prelock candidate-generation and portfolio replay across many independent games remains necessary before assigning causality to each rule.','',
        '## Reproducibility, artifacts and checks','',
        '- Standings capture uses an enforced `REPEATABLE READ READ ONLY` transaction; primary inputs are hashed in `inputs/manifest.json`. Recovery/identity/QB-stat supplements were read in separate read-only transactions minutes later, so they are not claimed to be part of the exact same MVCC snapshot. Every supplemental input and market archive is hashed in `analysis.json`.',
        '- Recompute from saved inputs: `PYTHONPATH=. .venv/bin/python scripts/analyze_showdown_qb_construction.py`; render: `PYTHONPATH=. .venv/bin/python scripts/render_showdown_qb_construction.py`. For a future database capture, use `scripts/capture_showdown_qb_construction.py --output <new-directory>`; existing snapshots are never overwritten.',
        '- Targeted validation: `PYTHONPATH=. .venv/bin/python -m pytest scripts/test_showdown_qb_construction.py -q`. Checks cover ties, tiny fields, medians, source-native/canonical identity conflicts, backups, after-lock starter evidence, prior-stat leakage, cash tie splits, missing-roster bounds and game-cluster comparisons.',
        '- Main JSON: [analysis.json](artifacts/showdown_qb_construction/analysis.json). Tables: [summary.csv](artifacts/showdown_qb_construction/summary.csv), [contest_weighted.csv](artifacts/showdown_qb_construction/contest_weighted.csv), [comparisons.csv](artifacts/showdown_qb_construction/comparisons.csv), [contest_inventory.csv](artifacts/showdown_qb_construction/contest_inventory.csv), [contest_metrics.csv](artifacts/showdown_qb_construction/contest_metrics.csv), [rate_confidence_intervals.csv](artifacts/showdown_qb_construction/rate_confidence_intervals.csv), [sensitivities.csv](artifacts/showdown_qb_construction/sensitivities.csv).',
        '- Optimizer attribution: [optimizer_lineups.csv](artifacts/showdown_qb_construction/optimizer_lineups.csv), [optimizer_runs.csv](artifacts/showdown_qb_construction/optimizer_runs.csv), [optimizer_candidate_rerank.csv](artifacts/showdown_qb_construction/optimizer_candidate_rerank.csv). Unknown roster records are retained separately; no raw source is deleted or overwritten.','',
        '## Final decision table (P)','',
        'All displayed usage/rates are entry-weighted complete-cohort percentages; relative lift is top 10% / top 1%. Evidence strength reflects games, stability and economics, not raw entry count.','']
    lines+=table(['Construction','Field usage','Top-10% rate','Top-1% rate','Winner rate','Relative lift (10 / 1)','Evidence strength','Recommended optimizer treatment'],[
        [g,pct(primary[g]['field_share']),pct(primary[g]['top10_rate']),pct(primary[g]['top1_rate']),pct(primary[g]['winner_rate']),
         f'{num(primary[g]["top10_lift"])}× / {num(primary[g]["top1_lift"])}×',
         'Limited; season/starter-sensitive' if g!='Zero QB' else 'Limited; weak percentile results, one-game ROI exception',
         'Retain eligibility; no boost' if g=='Zero QB' else 'No new penalty, exclusion or cap'] for g in groups[:8]])
    lines+=['**Concrete next recommendation:** make no optimizer rule change from this study. Keep QB Captain and both starters legal, including rare exceptions. Before any future adjustment, run chronological shadow A/Bs that separate Captain-position prior, hard stack/script constraints and saturated correlation scoring; evaluate first-place/chop-adjusted return as well as top-10% and top-1% rates. A soft cap/penalty is a candidate to test, not a result established here. No recommendation is tuned to Week 4 Monday Night.','']
    (ROOT/'SHOWDOWN_QB_CONSTRUCTION_ANALYSIS.md').write_text('\n'.join(lines))
    source_paths=[ROOT/'scripts/analyze_showdown_qb_construction.py',ROOT/'scripts/capture_showdown_qb_construction.py',
        ROOT/'scripts/render_showdown_qb_construction.py',ROOT/'scripts/test_showdown_qb_construction.py',
        ROOT/'backend/app/product_services/optimizer.py',ROOT/'backend/app/product_services/lineup_correlation_scoring.py',
        ROOT/'backend/app/product_services/showdown_portfolio_selection.py',ROOT/'docs/showdown_captain_model_2024_2025.json']
    hashes={}
    snapshots=OUT/'audited_code';snapshots.mkdir(exist_ok=True)
    for path in source_paths:
        content=path.read_bytes();digest=hashlib.sha256(content).hexdigest();hashes[str(path.relative_to(ROOT))]=digest
        if str(path.relative_to(ROOT)).startswith(('backend/','docs/')):
            target=snapshots/(path.name+'.'+digest[:12]+'.txt')
            if not target.exists():target.write_bytes(content)
            elif target.read_bytes()!=content:raise ValueError('Audited code snapshot conflict')
    (OUT/'source_hashes.json').write_text(json.dumps(hashes,indent=2,sort_keys=True)+'\n')
    print('Wrote SHOWDOWN_QB_CONSTRUCTION_ANALYSIS.md',len(lines),'lines')


if __name__=='__main__':main()
