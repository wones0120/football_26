"""Render the research report and contest-level tables from frozen offline results."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from scripts.analyze_classic_historical_study import OUT, POPS, ROOT, aggregate, field_bucket


def pct(x):
    return 'unavailable' if x is None else f'{100*x:.2f}%'


def ratio(x):
    return 'unavailable' if x is None else f'{x:.3f}'


def table(headers, rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join('---' for _ in headers)+' |']+
                     ['| '+' | '.join(str(v).replace('|',' / ') for v in row)+' |' for row in rows])+'\n'


def main():
    inventory=json.loads((OUT/'inventory_snapshot.json').read_text())
    study=json.loads((OUT/'study_summary.json').read_text())
    contests=sorted([json.loads(p.read_text()) for p in (OUT/'contests').glob('*.json')],key=lambda c:(c['contest']['season'],c['contest']['week'],c['contest']['contest_id']))
    analyzed=[c for c in contests if c['status']=='analyzed']
    conditional=list(csv.DictReader((OUT/'qb_conditioned.csv').open()))
    lines=[]
    def put(s):lines.extend([s,''])
    def stat(m,v='yes',pop='top_10',items=None,w='entry'):
        selected=items if items is not None else analyzed
        return aggregate(sorted(selected,key=lambda c:c['contest']['contest_id']),pop,w,m,v)
    def comparison(m,v='yes',items=None):
        a=stat(m,v,items=items);f=stat(m,v,'field',items=items)
        return a,f
    def binary_table(items, selected):
        rows=[]
        for label,m in selected:
            a,f=comparison(m,items=items)
            rows.append([label,f"{a['hits']:,}/{a['known']:,}",pct(a['rate']),pct(f['rate']),
                ratio(a['rate']/f['rate'] if f['rate'] else None),ratio(a['contest_mean_lift'])])
        return table(['Pattern','Top 10% count / known N','Top 10%','Field','Pooled lift','Equal contest lift'],rows)
    def distribution(metric,title,items=None):
        subset=analyzed if items is None else items
        put('### '+title)
        values=set(k for c in subset for k in c['distributions']['field']['entry'].get(metric,{}) if k!='unavailable')
        def sortkey(v):
            try:return (0,float(v))
            except ValueError:return (1,v)
        rows=[]
        for value in sorted(values,key=sortkey):
            rates=[stat(metric,value,p,subset)['rate'] for p in POPS]
            rows.append([value]+[pct(v) for v in rates])
        put(table(['Value','First place','Top 0.1%','Top 1%','Top 10%','Field'],rows))
        availability=[]
        for p in POPS:
            a=stat(metric,next(iter(values)) if values else 'yes',p,subset)
            availability.append(f"{p}: {a['known']:,} known, {a['unavailable']:,} unavailable")
        put('Denominators within classified rosters: '+ '; '.join(availability)+'.')

    primary=[('QB plus at least one WR or TE','qb_traditional_stack'),('QB plus two pass catchers and one bring-back','qb_2pc_1bring'),
        ('QB plus one pass catcher and one bring-back','qb_1pc_1bring'),('Pass catcher stack without a bring-back','qb_pc_without_bring'),
        ('Same-team RB with QB','qb_same_team_rb'),('Secondary opposing mini-stack','secondary_opposing_mini'),
        ('Two correlated environments','two_correlated_environments'),('Four or more offensive players on one team','four_plus_team_offense'),
        ('Four or more team players including DST','four_plus_team_all')]
    qb2,fqb2=comparison('qb_2pc_1bring'); four,ffour=comparison('four_plus_team_offense')
    put('# Historical DraftKings NFL Classic lineup construction study')
    put('Research date: October 4, 2026. Success means **top 10% of entries in each Classic contest**, with cutoff ties included, as clarified by the user. Cashing is outside this study. First place, top 0.1%, top 1%, and the full stored field are comparison populations.')
    primary_n=sum(c['valid_population_entries']['top_10'] for c in analyzed)
    put(f"The study inventories 39 registered contest fields and analyzes 15 verified Classic fields across 10 distinct slates. They contain {study['entries']:,} entries, of which {study['analyzed_entries']:,} have classifiable legal rosters. The primary population contains {primary_n:,} top 10% entries. The report describes their construction and compares it with the field; it does not evaluate an optimizer design.")
    put('This is a convenience sample of archived contests, not a representative sample of all DraftKings tournaments. Contest fees, entry limits, and payout shape are unknown for these 15 fields, so a GPP-only or single-entry/3-max/MME claim cannot be certified. No optimizer rules, weights, defaults, projections, or UI behavior were changed. No Week 4 lineups were generated.')
    put('## Characteristics of top 10 percent lineups')
    def pooled_values(metric,values,pop):
        d=Counter()
        for c in analyzed:d.update(c['distributions'][pop]['entry'][metric])
        return sum(d.get(v,0) for v in values)/(sum(d.values())-d.get('unavailable',0))
    portrait=[('At least one same-team WR or TE with QB','qb_traditional_stack',['yes']),
        ('Exactly one same-team pass catcher','qb_pass_catchers',['1']),
        ('Exactly two same-team pass catchers','qb_pass_catchers',['2']),
        ('Three or more same-team pass catchers','qb_pass_catchers',['3','4','5']),
        ('QB with no offensive teammate','qb_alone_offense',['yes']),
        ('No offensive bring-back','bring_back_bucket',['0']),('One offensive bring-back','bring_back_bucket',['1']),
        ('Two or more offensive bring-backs','bring_back_bucket',['2+']),
        ('QB plus two pass catchers and one bring-back','qb_2pc_1bring',['yes']),
        ('Two RBs','rb_count',['2']),('Three RBs and RB FLEX','rb_count',['3']),
        ('Secondary opposing mini-stack','secondary_opposing_mini',['yes']),
        ('At least two true unrelated one-offs','true_unrelated_oneoffs',['2','3','4','5','6','7']),
        ('Maximum two team players including DST','max_team_bucket',['2 or fewer']),
        ('Maximum three team players including DST','max_team_bucket',['3']),
        ('Four or more team players including DST','max_team_bucket',['4+'])]
    put(table(['Characteristic','Top 10% entries','Contest field'],[[label,pct(pooled_values(m,vs,'top_10')),pct(pooled_values(m,vs,'field'))] for label,m,vs in portrait]))
    def count_stats(metric,pop):
        d=Counter()
        for c in analyzed:d.update(c['distributions'][pop]['entry'][metric])
        n=sum(d.values()); cumulative=0; median=None
        for value,count in sorted(d.items(),key=lambda x:int(x[0])):
            cumulative+=count
            if median is None and cumulative>=n/2:median=int(value)
        return sum(int(k)*v for k,v in d.items())/n,median
    summaries=[]
    for metric,label in [('true_unrelated_oneoffs','True unrelated one-offs'),('unrelated_oneoffs','Offensive singleton one-offs'),
                         ('distinct_games','Games represented including DST'),('qb_game_all_players','Players from the QB game including DST')]:
        a,am=count_stats(metric,'top_10');f,fm=count_stats(metric,'field')
        summaries.append(f'{label}: top 10% mean {a:.2f}, median {am}; field mean {f:.2f}, median {fm}')
    put('Typical counts: '+ '; '.join(summaries)+'.')
    put('The observed top 10% population contains a broad mix of constructions. Compared with the field, it has more two-pass-catcher QB stacks, more RB FLEX entries, and somewhat fewer unrelated one-offs. Secondary opposing mini-stacks are common in both groups. Many successful lineups contain no bring-back, and several unrelated one-offs remain typical. These pooled descriptions are supplemented below by contest/slate weighting, duplication checks, and QB-conditioned comparisons.')
    put('## Historical data inventory')
    season_rows=[]
    for year in sorted({r['season'] for r in inventory['salaries']}):
        s=[r for r in inventory['salaries'] if r['season']==year]
        season_rows.append([year,', '.join(map(str,sorted({r['week'] for r in s}))),len({(r['week'],r['slate']) for r in s}),
            sum(c['contest']['season']==year for c in analyzed),', '.join(map(str,sorted({c['contest']['week'] for c in analyzed if c['contest']['season']==year}))) or 'none'])
    put(table(['Season','Salary weeks available','Salary slate scopes','Analyzed Classic contests','Classic result weeks'],season_rows))
    put('The 2024 salary and hindsight-optimal-lineup history does not provide registered, dated contest standings for this population. One additional registered source, `contest-standings-171680612.zip`, has a nine-player Classic roster but no linked contest season/week/slate; it is quarantined from analysis. Its players suggest an older slate, but that is not treated as verified historical context. The linked source archive inventory contains 44 file instances, including ZIP/CSV copies; hashes identify copies of the 40 registered source payloads. There are 24 registered Showdown fields, excluded using actual roster slots. Test fixtures, generated optimizer portfolios, and the 8,800 computed `actual_top_lineup` rows are not contest results. The latter are explicitly generated by the actual-score optimizer in `LineupLearningService.build_actual_top_lineups`.')
    invrows=[];observations=[]
    for i,c in enumerate(analyzed,1):
        meta=c['contest'];k=c['market_inventory']; c['study_label']=f'C{i:02d}'
        sv=c['score_validation']; raw=c['raw_population_entries'];valid=c['valid_population_entries']
        invrows.append([c['study_label'],meta['season'],meta['week'],c['analysis_scope'],f"{meta['field_size']:,}",k['slate_games'],f"{valid['top_10']:,}",
            f"{100*valid['field']/raw['field']:.3f}%", f"{k['market_games']}/{k['slate_games']}"])
        observations.append({'label':c['study_label'],'contest_id':meta['contest_id'],'contest_name':meta['contest_name'],
            'season':meta['season'],'week':meta['week'],'source_slate':meta['slate_id'],'analysis_scope':c['analysis_scope'],
            'field_size':meta['field_size'],'field_bucket':field_bucket(meta['field_size']),'slate_games':k['slate_games'],
            'classified_field':valid['field'],'raw_top10':raw['top_10'],'classified_top10':valid['top_10'],
            'unique_field':c['unique_population_rosters']['field'],'unique_top10':c['unique_population_rosters']['top_10'],
            'winner_entries':raw['winner'],'unique_first_place_rosters':c['unique_population_rosters']['winner'],
            'source_file_id':meta['source_file_id'],'entry_fee':meta['entry_fee'],'max_entries_per_user':meta['max_entries_per_user'],
            'contest_type':meta['contest_type'],'score_matched':sv.get('matched',0),'score_unavailable':sv.get('unavailable',0),
            'score_mismatched':sv.get('mismatched',0)})
    put(table(['Contest','Season','Week','Analysis slate','Stored entries','Games','Classified top 10%','Roster coverage','Pre-lock markets'],invrows))
    put('The original contest names are imported filenames or generic ID labels, not verified marketed contest names. `contest_inventory.csv` records their exact names, identities, and source links. C10–C12 retain original `SUNDAY_NIGHT` metadata but are analyzed against the same-week `SUNDAY_MAIN` salary universe. This correction is explicit, and their available player score sums reconcile to the stored entry scores. The 2025 Week 13 `THURSDAY_NIGHT` label covers all three Thanksgiving games; it is a three-game Classic slate, not a one-game Showdown.')
    put(table(['Dimension','Historical availability and treatment'],[
        ['Full fields, ranks, ties, scores','Full stored field counts and rank-population counts captured by lineup text; entry IDs remain in source standings and first-place exports. Blank/reserved rosters remain in raw cohort counts. Official contest capacity is not independently verified.'],
        ['Top finishers and first place','Available from stored contest ranks; all tied first-place entries and boundary ties preserved. Exact first-place rosters are in contest JSON and the report below.'],
        ['Fees, entry limits, payout structures','Unavailable for all 15; no registered payout tiers. SE, 3-max, MME, cash, and GPP categories remain unknown.'],
        ['Ownership','Contest-specific realized %Drafted/ownership observations; no current ownership forecast substitution. Conflicting or missing player values remain unavailable.'],
        ['Salaries and identity','Archived same-season/week/slate salary rows with native DK IDs, team, opponent, and compatible positions; canonical IDs where available. Conflicting identities are quarantined.'],
        ['Frozen projections','Archived before-lock references for 2026 Weeks 1–3 only, selected by both creation and cutoff timestamps. Older retrospective model runs are excluded. These are model references, not proof of best standalone plays.'],
        ['Betting markets','Verified, content-hashed before-lock source captures for 2026 Weeks 1–3; all games covered on those slates. 2025 retrospective schedule lines have no verified pre-lock source capture and are unavailable in the primary market analysis.'],
        ['Totals, spreads, implied team totals','Available only from qualified market sources; implied points calculated with the source-specific spread sign. Relative ranks require the whole salary slate to be covered.'],
        ['Injuries and status','Timestamped injury/status references exist for 2026 Weeks 1–3; older backfills are not frozen pre-lock status evidence. No causal injury or news explanation is inferred for an entry.'],
        ['Actual fantasy points','Contest scores and player result side tables; missing player outcomes remain null, not zero. Structural classification does not require complete individual fantasy scores.'],
        ['Prior rushing and volume','Archived native-ID stat history mapped through unique canonical aliases; strictly earlier weeks only. Last eight available prior appearances, at least four, form descriptive usage proxies.']]))
    put('The complete inventory snapshot includes 27,178 salary rows, 88 hindsight-oracle slate scopes, 136 projection run headers, 356 source-snapshot records, injury coverage, normalized and legacy result scope counts, and supporting table counts. Raw source files were neither modified nor ingested. Historical fields were exported through an enforced read-only, repeatable-read database transaction.')
    put('## Population definitions and validity')
    poprows=[]
    for p,label,fraction in [('winner','First place',None),('top_01','Top 0.1%',.001),('top_1','Top 1%',.01),('top_10','Top 10%',.1),('field','Full stored field',None)]:
        raw=sum(c['raw_population_entries'][p] for c in analyzed);valid=sum(c['valid_population_entries'][p] for c in analyzed)
        unique=sum(c['unique_population_rosters'][p] for c in analyzed)
        nominal=sum(__import__('math').ceil(c['contest']['field_size']*fraction) for c in analyzed) if fraction else None
        poprows.append([label,f'{raw:,}',f'{valid:,}',f'{unique:,}',f'{raw-nominal:,}' if nominal else 'n/a'])
    put(table(['Population','Raw entries','Classified entries','Unique rosters summed across contests','Extra entries from boundary ties'],poprows))
    audit=Counter();sv=Counter()
    for c in analyzed:audit.update(c['audit']);sv.update(c['score_validation'])
    put(f"Exclusions from structural denominators: {audit.get('invalid_roster_entries',0):,} invalid/blank rosters, {audit.get('unresolved_entries',0):,} rosters with unresolved or ambiguous salary identities, {audit.get('duplicate_player_entries',0):,} repeated-player rosters, and {audit.get('over_salary_cap_entries',0):,} verified over-cap rosters. Score-sum audit among classified field entries: {sv.get('matched',0):,} reconciled within 0.05 DK points, {sv.get('unavailable',0):,} lacked a complete player-score sum, and {sv.get('mismatched',0):,} disagreed. The raw cohorts and weighted unresolved tokens remain available in each contest JSON.")
    put('Top-percentile membership uses `rank <= ceil(field_size × fraction)` from the full stored field. This includes all ties at the boundary rather than selecting an arbitrary number of tied entries. The nested populations overlap. Valid Classic slots are QB, two RB, three WR, TE, FLEX, and DST, with nine distinct resolved identities; salary is checked when all nine values are known.')
    put('Entry weighting counts every contest entry. Unique weighting counts each unordered nine-player identity set once within each contest, including entries that rearrange interchangeable slots. It does not count duplicated entries as independent football constructions. The same roster may appear in several contests on a slate; those contests are dependent, which is why uncertainty resamples whole slates. Unique roster counts across contests are not asserted to be globally unique.')
    unique_top=sum(c['unique_population_rosters']['top_10'] for c in analyzed)
    unique_field=sum(c['unique_population_rosters']['field'] for c in analyzed)
    put(f"Extra copies beyond the first instance of each roster account for {100*(1-unique_top/primary_n):.2f}% of top 10% entries versus {100*(1-unique_field/study['analyzed_entries']):.2f}% of classified field entries. This measures repeated constructions within contests; it is not the fraction of entries belonging to any duplicated roster or a measure of winnings after splits.")
    put('Pooled lift is top-percentile pattern frequency divided by field pattern frequency on available observations. Equal-contest lift divides the mean contest top-percentile frequency by the mean corresponding field frequency; it is not the mean of contest lifts. Slate-balanced lift averages contests within each slate and then weights slates equally. Reported 95% intervals use 3,000 bootstrap draws of the whole slate with seed 20261004; fewer than five covered slates have no interval. These are exploratory intervals, without multiple-comparison correction. Millions of entries do not turn ten football slates into millions of independent trials.')
    put('The additional Mantel–Haenszel odds ratio compares the odds of placing in the top 10% for a pattern versus other constructions **within the same contest and QB**. Its interval also resamples slates. This helps separate construction patterns from selecting a particular successful QB, but it does not control all player choices, salaries, ownership, injuries, or entrant skill. It is an association, not a causal optimizer parameter.')
    put('## Primary top 10 percent results')
    put(binary_table(analyzed,primary))
    cirows=[]
    for label,m in primary:
        a=stat(m)
        r=next((r for r in conditional if r['stratum']=='all' and r['metric']==m and r['value']=='yes'),{})
        ci=lambda lo,hi:'unavailable' if lo is None or hi is None else f'{lo:.3f}–{hi:.3f}'
        low=float(r['slate_bootstrap_low']) if r.get('slate_bootstrap_low') else None
        high=float(r['slate_bootstrap_high']) if r.get('slate_bootstrap_high') else None
        cirows.append([label,ratio(a['slate_mean_lift']),ci(a['slate_bootstrap_lift_low'],a['slate_bootstrap_lift_high']),
            ratio(float(r['mh_top10_odds_ratio'])) if r.get('mh_top10_odds_ratio') else 'unavailable',ci(low,high)])
    put(table(['Pattern','Slate-balanced lift','Exploratory 95% interval','Within QB and contest odds ratio','Exploratory 95% interval'],cirows))
    put('## Contest and slate strata')
    strata=[('All',analyzed),('Sunday Main',[c for c in analyzed if c['analysis_scope']=='SUNDAY_MAIN']),
        ('Main fields 20000+',[c for c in analyzed if c['analysis_scope']=='SUNDAY_MAIN' and c['contest']['field_size']>=20000])]
    for b in ['<1000','1000-4999','5000-19999','20000+']:
        strata.append(('Field '+b,[c for c in analyzed if field_bucket(c['contest']['field_size'])==b]))
    for y in [2025,2026]:strata.append((str(y),[c for c in analyzed if c['contest']['season']==y]))
    rows=[]
    for label,cs in strata:
        if not cs:
            rows.append([label,0,0,'unavailable','unavailable','unavailable']);continue
        rows.append([label,len(cs),len({c['slate_key'] for c in cs}),ratio(stat('qb_2pc_1bring',items=cs)['contest_mean_lift']),
            ratio(stat('secondary_opposing_mini',items=cs)['contest_mean_lift']),ratio(stat('four_plus_team_offense',items=cs)['contest_mean_lift'])])
    put(table(['Stratum','Contests','Slates','2 PC and 1 bring-back lift','Secondary opposing mini lift','4+ offense team lift'],rows))
    main_large=[c for c in analyzed if c['analysis_scope']=='SUNDAY_MAIN' and c['contest']['field_size']>=20000]
    ml=stat('four_plus_team_offense',items=main_large)
    put(f"The eight large Sunday Main fields have a different four-player offensive concentration result from the pooled mixed-slate sample: slate-balanced lift {ratio(ml['slate_mean_lift'])}, exploratory interval {ml['slate_bootstrap_lift_low']:.3f}–{ml['slate_bootstrap_lift_high']:.3f}. This subgroup is enriched in the observed sample. Its interval is marginal at the lower endpoint and unadjusted for multiple comparisons, so the overall pooled result should not erase it or establish a universal conclusion.")
    put('These are equal-contest lifts. Field-size groups use <1,000; 1,000–4,999; 5,000–19,999; and 20,000+, so the boundaries neither overlap nor omit 5,000 or 20,000. No 1,000–4,999 Classic field is available. The <1,000 group has one 356-entry contest; the three-game group has one Thanksgiving contest. SE, 3-max, MME, and GPP-only comparisons are unavailable. File sizes and observed user entry suffixes are not substituted for official entry limits.')
    put('### Entry weighting and roster deduplication')
    rows=[]
    for label,m in primary:
        a,f=comparison(m);u,uf=comparison(m,items=analyzed)
        u=stat(m,w='unique');uf=stat(m,pop='field',w='unique')
        rows.append([label,pct(a['rate']),pct(f['rate']),pct(u['rate']),pct(uf['rate']),ratio(u['rate']/uf['rate'] if uf['rate'] else None)])
    put(table(['Pattern','Entry top 10%','Entry field','Unique top 10%','Unique field','Unique pooled lift'],rows))
    put('## QB stack construction')
    put('A pass catcher means a same-team WR or TE. A same-team RB is recorded separately. QB alone means no offensive teammate; DST is excluded from that definition. Team counts with and without DST are both retained. QB + RB can supplement a pass-catching stack or replace it; these are separate indicators.')
    distribution('qb_family','Exclusive QB families')
    distribution('qb_pc_positions','Same team pass catcher positions')
    distribution('qb_team_offense_including_qb','Offensive players from the QB team')
    put(binary_table(analyzed,[('QB alone among offensive players','qb_alone_offense'),('QB with WR','qb_has_wr'),('QB with TE','qb_has_te'),
        ('RB added to pass catcher stack','qb_rb_added_to_pc'),('RB used instead of pass catcher','qb_rb_instead_of_pc'),
        ('Two teammates including RB','qb_2_teammates_including_rb'),('Three teammates including RB','qb_3_teammates_including_rb')]))
    distribution('qb_prior_carry_bucket','QB prior rushing carries')
    put(binary_table(analyzed,[('QB with rushing oriented prior usage','qb_rushing_oriented')]))
    put('The rushing-oriented proxy requires at least four prior appearances among the latest eight and either at least five carries/game or 30 rushing yards/game. These are disclosed exploratory thresholds, not a claim that all such QBs share the same playing style. Prior-year games may contribute; current-week games never do. Rookie or sparse-history QBs remain unavailable. Backfilled stat records establish earlier realized usage, not a contemporaneously frozen scouting designation.')
    put('## Bring backs and primary game size')
    put('Bring-backs are opposing RB/WR/TE players in the QB game. An opposing DST is not counted as an offensive bring-back. The QB game is called the primary game even for a QB-alone roster; those lineups are not silently excluded from the denominators.')
    distribution('bring_back_bucket','Number of offensive bring backs')
    distribution('bring_back_position','Bring back positions')
    distribution('qb_game_all_players','Players in the QB game including DST')
    put('## Running back construction')
    distribution('rb_count','Number of running backs')
    distribution('flex_position','FLEX natural position')
    put(binary_table(analyzed,[('Two RBs from one game','two_rb_same_game'),('Two RBs from one team','two_rb_same_team'),
        ('QB with same-team RB','qb_same_team_rb'),('Opposing RB bring-back','bring_back_rb'),
        ('RB plus opposing pass catcher','rb_opposing_pc'),('Two RBs at $7000 or above','two_high_salary_rb'),
        ('At least one RB at $4500 or below','low_salary_rb'),('Two $7000+ RBs each at 20%+ ownership','two_high_salary_high_owned_rb')]))
    distribution('rb_favorite_count','Running backs from favored teams')
    distribution('rb_underdog_count','Running backs from underdogs')
    distribution('rb_high_implied_count','Running backs with implied points at least 26')
    put('The salary and ownership thresholds are declared research buckets. Ownership is realized contest ownership. Favorite/underdog and implied-total counts require qualified markets for every RB in the roster; unavailable is not interpreted as a pick-em, low-total team, or zero favorite RBs.')
    put('## Betting environment')
    covered=[c for c in analyzed if c['market_inventory']['relative_ranks_available']]
    put(f"Qualified complete pre-lock market coverage spans {len(covered)} contests but only {len({c['slate_key'] for c in covered})} independent slates, all in 2026 Weeks 1–3. This is too few for a stable claim that high-total games improve top 10% results. Source captures, hashes, timestamps, lines, and slate ranks are saved in each contest's market inventory.")
    put(binary_table(covered,[('QB in highest-total game','qb_highest_total'),('QB in a top-three-total game','qb_top3_total'),
        ('QB in top quartile by total','qb_top25_total'),('QB team among top three implied totals','qb_top3_team_total'),('QB team favored','qb_favorite')]))
    distribution('qb_game_total_bucket','Absolute QB game totals',covered)
    distribution('qb_total_relative','Slate relative QB game totals',covered)
    distribution('qb_total_rank','QB game total rank',covered)
    distribution('qb_team_total_bucket','QB implied team points',covered)
    put('The archived nflverse `spread_line` is the expected home scoring margin; normalized conventional home spread is its negative. Home implied points are `(total − home_spread)/2`, away implied points `(total + home_spread)/2`. Only pre-lock raw bytes with matching stored hashes and both observed/captured timestamps before the first salary-slate kickoff qualify. A later capture of an old game is never promoted into pre-lock evidence. All available games are ranked against the archived salary slate, not against the entire week. Rank 1 and top 3 use competition ranks, preserving tied lines. Relative quartiles use tie-aware midrank percentiles; fixed total buckets are <40, 40–44.5, 45–49.5, and 50+ for the available half-point lines.')
    put('These are the latest qualifying captures recovered here, not certified closing lines. Some were captured days or weeks before the slate. Their recorded timing is preserved in the market inventory, and market age further limits comparisons of expected game environments.')
    put('Pooling heavily weights the 832,342-entry Week 1 contest. Highest-total results can look very different under pooled versus equal-contest weighting, demonstrating why a broad statement about game totals is not supported by this market subsample. The result is an availability-limited observation, not a reason to replace historical missing lines with current betting markets.')
    put('## One offs and secondary game correlations')
    put('Outside-primary offensive players are RB/WR/TE players outside the QB game. An offensive singleton is the only offensive player from its game outside that primary game. It may still share a team/game with DST. A true unrelated one-off is an offensive singleton whose game also contains no rostered DST. Secondary opposing mini-stacks require two offensive players on opposite teams in the same non-QB game; same-team pairs are tracked as game clusters but are not described as opposing correlations. Categories can overlap and do not assert the entrant intended a particular correlation.')
    distribution('outside_primary_offense','Offensive players outside the primary game')
    distribution('unrelated_oneoffs','Offensive singleton one offs')
    distribution('true_unrelated_oneoffs','True unrelated one offs excluding DST links')
    distribution('outside_distinct_games','Nonprimary offensive games represented')
    distribution('secondary_two_player_games','Secondary games with exactly two offensive players')
    put(binary_table(analyzed,[('Secondary opposing mini-stack','secondary_opposing_mini'),('Secondary RB and opposing WR or TE','secondary_rb_opposing_pc'),
        ('Secondary WR and opposing WR or TE','secondary_wr_opposing_pc'),('Secondary TE and opposing WR or TE','secondary_te_opposing_pc'),
        ('QB pass catcher stack and secondary opposing game','two_correlated_environments'),
        ('WR and opposing WR anywhere','wr_opposing_wr'),('RB and same-team DST','rb_dst_same_team')]))
    distribution('oneoff_low_salary_count','Singleton one offs at 4500 salary or below')
    distribution('oneoff_chalk_count','Singleton one offs at 20 percent ownership or above')
    distribution('oneoff_low_owned_count','Singleton one offs at 5 percent ownership or below')
    distribution('oneoff_favorite_count','Singleton one offs from favored teams')
    distribution('oneoff_high_implied_count','Singleton one offs with implied points at least 26')
    distribution('oneoff_top25_game_count','Singleton one offs from the top total quartile')
    distribution('oneoff_middle50_game_count','Singleton one offs from the middle total half')
    distribution('oneoff_bottom25_game_count','Singleton one offs from the bottom total quartile')
    distribution('oneoff_top25_team_total_count','Singleton one offs from the top implied total quartile')
    distribution('oneoff_underdog_prior_volume_count','Underdog singleton one offs with high prior usage')
    distribution('oneoff_top10_position_projection_count','Singleton one offs among the top ten projected players at their position')
    put('The prior-volume proxy uses the same earlier-game history: at least 15 carries/game for RB or seven targets/game for WR/TE, and a verified underdog spread. It is not a forecast of current-week volume. The standalone projection proxy uses an archived pre-lock model reference, ranks all available players within natural position, and includes ties at rank ten. A complete singleton group is required for the count; otherwise it is unavailable. A low salary does not establish value without a credible projection, and low ownership does not itself establish leverage. Injuries, opportunity changes, opposing chalk, and individual player quality cannot be inferred from lineup structure alone. Consequently the question whether non-stack players were simply the strongest standalone plays has a limited model-proxy answer, not a definitive historical explanation.')
    put('For counts that classify singleton players by market or usage, a roster with no singleton players has a known count of zero even if other games on its slate lack that input. This does not fill any missing player market or usage value. Lineups with actual singleton players require complete relevant coverage.')
    put('## Team and game concentration')
    distribution('max_team_bucket','Maximum team concentration including DST')
    distribution('max_team_offense','Maximum offensive team concentration')
    distribution('max_game_all','Maximum players from one game including DST')
    distribution('distinct_teams','Distinct teams represented')
    distribution('distinct_games','Distinct games represented')
    distribution('games_with_1','Games represented by exactly one player')
    distribution('games_with_2','Games represented by exactly two players')
    distribution('games_with_3plus','Games represented by three or more players')
    put(binary_table(analyzed,[('At least four offensive players on one team','four_plus_team_offense'),
        ('At least four players on QB team excluding DST','four_plus_qb_team_offense'),
        ('At least four team players including DST','four_plus_team_all'),('At least four Jacksonville offensive players','four_jax_offense'),
        ('At least four Jacksonville players including DST','four_jax_all')]))
    put('Four-player constructions must be distinguished by composition. QB plus three pass catchers differs from QB plus RB plus two pass catchers, and either differs from an offensive trio plus DST. The top 10% rates above describe how often those concentration levels occur; the field comparison and slate uncertainty describe whether they are enriched in this sample. Jacksonville-specific counts are a narrow historical subgroup, not a general explanation of four-player team concentration.')
    put('### First place constructions')
    rows=[]
    for c in analyzed:
        for winner in c['winners']:
            f=winner['features']
            rows.append([c['study_label'],winner['entry_count'],winner['points'],f['qb_family'],f['bring_back_bucket'],f['max_team_all'],f['max_game_all'],f['unrelated_oneoffs'],f['true_unrelated_oneoffs']])
    put(table(['Contest','Tied entries','DK points','QB family','Bring-backs','Max team with DST','Max game','Offense singletons','True one-offs'],rows))
    put('Exact first-place player names, canonical/native IDs, source IDs, salaries, available ownership, scores, and classified features are preserved in the corresponding `contests/*.json` files. First place is a comparison population, not the success definition.')
    put('## Additional construction patterns')
    distribution('salary_left_bucket','Salary left unused')
    distribution('ownership_sum_bucket','Sum of realized player ownership')
    distribution('high_owned_players','Players at least 20 percent owned')
    distribution('low_owned_players','Players at most 5 percent owned')
    distribution('offense_against_dst','Offensive players facing rostered DST')
    put('Salary remaining, FLEX position, number of distinct games, and ownership concentration can confound stack comparisons. Sum of ownership is not lineup ownership or expected duplication; correlated player selections invalidate a naive independence interpretation. This study measures actual duplication from canonical roster signatures instead of multiplying player ownership percentages.')
    put('## Differences between top 10 percent entries and the field')
    put(table(['Characteristic','Observed difference and interpretation'],[
        ['QB pass catcher stacks','84.83% of top 10% entries contain a same-team WR or TE versus 80.29% of the field. The relationship remains positive in the within-contest/QB comparison.'],
        ['Two pass catchers with one bring-back','15.68% versus 11.26%; the equal-contest lift is 1.527 and slate-balanced lift is 1.461. The positive difference persists after conditioning on QB, while remaining descriptive.'],
        ['Stacks without a bring-back','Common among successful entries: 36.91% of all top 10% entries have a QB pass catcher stack without an offensive bring-back, versus 42.62% of the field.'],
        ['Same-team RB with QB','19.16% versus 21.59%. The within-QB odds ratio is approximately 1.016, suggesting the crude difference is partly associated with which QBs were used.'],
        ['Secondary opposing mini-stack','53.61% versus 52.15%. The pooled difference is small and the equal-slate interval includes parity. Most top 10% entries still have multiple unrelated one-offs.'],
        ['Two correlated game environments','43.29% versus 39.52% when defined as a QB pass catcher stack plus a secondary opposing mini-stack. This composite differs from a mini-stack in isolation.'],
        ['Four-player offensive team concentration','8.33% versus 7.15%. The slate-balanced interval and within-QB interval both include parity; enrichment is not consistent enough to describe it as a general advantage.'],
        ['Game totals and implied totals','Available-case distributions are reported, but only three independent slates have verified pre-lock markets. They do not establish a broad historical scoring-environment profile.'],
        ['Standalone player strength','The pre-lock projection proxy is limited to 2026. It cannot establish that every non-stack player was the strongest standalone choice or explain entrants\' reasons.']]))
    put('## Limitations and next evidence needed')
    put('The most consequential limits are ten independent slates, nonrandom archive availability, unknown contest categories, one small contest, one three-game contest, and pre-lock markets available on only three slates. A valid top 10% association can reflect which QB/game succeeded, selected player quality, salary allocations, ownership, entrant skill, or injury information. The within-QB diagnostic narrows one confounder but does not remove the others. First-place evidence has only fifteen contest observations and repeated football slates.')
    put('For unresolved structural rosters, the primary tables use complete cases. Missingness is explicitly retained by contest and token. For a fully observed binary metric, a worst-case raw-field frequency lies between `known_hits/raw_population_N` and `(known_hits + unclassified_entries)/raw_population_N`; those bounds are exported for focal patterns. Market, ownership, projection, and usage tables have their own available-case denominators and may have much larger missingness. Their availability is not silently converted to false.')
    put('A stronger follow-up study would need verified contest metadata and date/slate linkage for the unscoped archive; more independently dated Classic fields across seasons and slate sizes; broad immutable pre-lock market/projection/role captures; and a preregistered set of hypotheses evaluated on held-out later slates. This report makes no promotion recommendation and changes no production rule.')
    put('## Reproduction and evidence')
    put('All analysis can be reproduced offline from the saved artifacts with no API calls, no live source refresh, no optimizer solve, and no database writes:')
    put('```sh\nPYTHONPATH=. .venv/bin/python -m unittest scripts.test_classic_historical_study\n.venv/bin/python scripts/analyze_classic_historical_study.py\nPYTHONPATH=. .venv/bin/python scripts/render_classic_historical_study.py\n```')
    put('`capture_classic_historical_study.py` is a separate optional read-only exporter for the inventory snapshot; it reuses existing compressed raw exports. Offline analysis verifies their recorded hashes and invalidates derived contest caches if the analysis source, inventory, support inputs, or raw hash manifest changes. The final manifest hashes the request, capture/analysis/render/test scripts, snapshots, raw exports, derived contest records, CSV tables, and report.')
    put('Evidence: [full distributions and lift tables](../artifacts/classic_historical_study/summary.csv), [QB and contest conditioned comparisons](../artifacts/classic_historical_study/qb_conditioned.csv), [contest inventory](../artifacts/classic_historical_study/contest_inventory.csv), [contest pattern observations](../artifacts/classic_historical_study/contest_patterns.csv), [missing-roster sensitivity bounds](../artifacts/classic_historical_study/missing_roster_bounds.csv), [study summary](../artifacts/classic_historical_study/study_summary.json), [source archive inventory](../artifacts/classic_historical_study/linked_archive_inventory.json), and [manifest](../artifacts/classic_historical_study/manifest.json).')
    report=ROOT/'docs/classic_historical_lineup_construction_study.md'
    report.write_text('\n'.join(lines))
    with (OUT/'contest_inventory.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(observations[0]));w.writeheader();w.writerows(observations)
    patternrows=[];bounds=[]
    for c in analyzed:
        for pop in POPS:
            for weighting in ['entry','unique']:
                for m,dist in c['distributions'][pop][weighting].items():
                    known=sum(dist.values())-dist.get('unavailable',0)
                    for v,n in dist.items():
                        patternrows.append({'contest':c['study_label'],'contest_id':c['contest']['contest_id'],'slate':c['slate_key'],
                            'population':pop,'weighting':weighting,'metric':m,'value':v,'count':n,'known':known,
                            'known_rate':n/known if v!='unavailable' and known else None})
        for label,m in primary:
            for pop in ['top_10','field']:
                d=c['distributions'][pop]['entry'][m];raw=c['raw_population_entries'][pop]
                missing=raw-c['valid_population_entries'][pop]
                bounds.append({'contest':c['study_label'],'population':pop,'metric':m,'raw_N':raw,'known_yes':d.get('yes',0),
                    'unclassified':missing,'lower':d.get('yes',0)/raw,'upper':(d.get('yes',0)+missing)/raw})
    for filename,rows in [('contest_patterns.csv',patternrows),('missing_roster_bounds.csv',bounds)]:
        with (OUT/filename).open('w') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='manifest.json'}
    for p in [report,ROOT/'scripts/capture_classic_historical_study.py',ROOT/'scripts/analyze_classic_historical_study.py',ROOT/'scripts/render_classic_historical_study.py',ROOT/'scripts/test_classic_historical_study.py']:
        hashes[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
    (OUT/'manifest.json').write_text(json.dumps({'success_definition':'top 10% per Classic contest with boundary ties; no cashing analysis',
        'source_database_access':'read-only','production_changes':False,'week4_lineups_generated':False,'sha256':hashes},sort_keys=True,indent=2)+'\n')
    print(report, len(lines),'blocks',len(patternrows),'contest-pattern rows')


if __name__=='__main__':
    main()
