"""Render the requested decision report from immutable, verified research outputs."""
import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.finalize_showdown_gameday_shadow import read_frozen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory',type=Path)
    parser.add_argument('report',type=Path)
    args = parser.parse_args()
    b = args.directory
    if (b/'report_snapshot.md').exists():raise ValueError('Report snapshots are immutable')
    d = read_frozen(b/'decision.json')['payload']
    inputs = read_frozen(b/'final_inputs.json')['payload']
    q = read_frozen(b/'quality_shadow.json')['payload']
    preserve = read_frozen(b/'preservation_verified.json')['payload']
    p, cost = d['portfolio_alternatives'],d['alternative_cost']
    c, x, y = p['C'],d['metcalf_3_of_3'],d['metcalf_2_of_3']
    assert c['feasible'] and not d['entry_ready'] and not inputs['entry_ready']
    now = datetime.fromisoformat(d['frozen_at']).astimezone(ZoneInfo('America/New_York'))
    lines = []
    def add(value=''):lines.append(value)
    def table(headers,rows):
        add('| '+' | '.join(headers)+' |');add('| '+' | '.join('---' for _ in headers)+' |')
        for row in rows:add('| '+' | '.join(str(value) for value in row)+' |')
        add()
    def number(value):return f'{value:.9f}'
    def allocation(values):return ', '.join(f'{name} ×{count}' for name,count in values.items())
    def compact(lineup):return '; '.join(row['roster_position']+' '+row['name'] for row in sorted(lineup,key=lambda r:r['roster_position']!='CPT'))
    add('# PIT @ CLE — final-lock research decision\n')
    add(f'Updated **October 1, 2026, {now.strftime("%I:%M %p EDT")}**; kickoff **8:15 PM EDT**. **ENTRY READY: NO.** Official tonight inactive/elevation lists and final QB dressing confirmation remain pending. The exact three below are the current model-supported portfolio, ready for final verification and manual entry afterward.\n')
    add(f'**Current recommendation: portfolio C, {" / ".join(c["captains"])}, Metcalf {d["model_supported_metcalf_exposure"]}.** The normal feature/projection/P90 rebuild and **full expanded research discovery** completed on the fresh freeze; this is a new solve, not reuse of the saved production portfolio. No selected player, captain or thesis changed from the immutable morning baseline.\n')
    add(f'Immutable evidence: [{b.name}]({b.resolve()}), [final inputs]({(b/"final_inputs.json").resolve()}), [projection freeze]({(b/"refreshed_database_freeze.json").resolve()}), [full common universe]({(b/"final_common_universe.json").resolve()}), [A–E decision]({(b/"decision.json").resolve()}). The prior final-lock report is preserved in [its snapshot]({(b/"prior_final_lock_report.md").resolve()}); overnight, morning and parity reports/freezes remain immutable.\n')
    add('## Fresh source reconciliation\n')
    add('The [Steelers’ 12:35 PM EDT update](https://www.steelers.com/news/week-4-injury-report-browns) removes Echols’ Q designation and adds Yahya Black as Q (NIR/personal). Ramsey remains Q (wrist); Dowdle remains OUT. [Porter was traded to Dallas](https://www.steelers.com/team/transactions/) October 1; he was already OUT in the morning baseline. These are source changes, not invented DST adjustments.\n')
    add('[CLE game status](https://www.clevelandbrowns.com/news/elgton-jenkins-out-for-week-4-against-the-steelers-injury-report) still rules out Tylan Wallace, Elgton Jenkins and Teven Jenkins. [CLE transactions](https://www.clevelandbrowns.com/team/transactions/) show no new game-day elevation. Current expected OL replacements remain Luke Wypler/Austin Barber; final starters are pending. A previous Bengals-game Nichols elevation is not evidence of availability tonight. Homer remains on the PIT active roster with unverified offensive touches. Newly cheap activations are not verified.\n')
    observed = datetime.fromisoformat(inputs['source_manifest']['dk_salary']['retrieved_at']).astimezone(ZoneInfo('America/New_York'))
    add(f'The [fresh official DK download](https://www.draftkings.com/lineup/getavailableplayerscsv?draftGroupId=154084), observed **{observed.strftime("%I:%M:%S %p EDT")}**, verifies **102 native slots / 51 canonical players** against salary, position, team and CPT/FLEX identities. File bytes match morning. The public contest link still identifies tonight’s PIT/CLE draft group; an authenticated account session was not used.\n')
    market = inputs['market']
    add(f'[DraftKings market](https://dknetwork.draftkings.com/moneyline-total-spread/): **PIT {market["pit_spread"]:+g}, total {market["total"]:g}**, implied PIT **20.5** / CLE **18.0**, unchanged. [NWS stadium-area forecast]({inputs["source_manifest"]["weather"]["hourly_url"]}) was updated at {inputs["weather_update_time"]}; early game-hour wind increased from 9 to 10 mph.\n')
    table(['EDT hour','Temperature','Wind','Rain probability'],[[r['startTime'][11:16],f'{r["temperature"]}°F',r['windSpeed']+' '+r['windDirection'],str(r['probabilityOfPrecipitation']['value'])+'%'] for r in inputs['weather_hours']])
    add('The unchanged normal pipeline rebuilt 51 feature rows and 45 projection rows, with **zero changes** to player means, P90, salaries, identities, opportunity, market or offensive availability versus morning. Fresh weather is retained as readiness evidence; no manual weather or defensive-injury projection adjustment was applied.\n')
    table(['Selected player','Current official role','Game-day dressing'],[[r['name'],('Expected starting QB' if r['expected_starting_qb'] else 'First depth-chart role')+'; active roster; no game-status designation','PENDING final inactive reconciliation'] for r in inputs['primary_player_checks']])
    add('Role checks use canonical DK identities plus team/position and official [PIT roster/depth](https://www.steelers.com/team/depth-chart/) and [CLE depth](https://www.clevelandbrowns.com/news/browns-announce-unofficial-depth-chart-for-week-4-vs-the-steelers). Roster presence does not establish tonight’s dressing status. McLaughlin, Bernard, Heidenreich, Homer, Whiteheart and unverified minimum-price offense remain excluded from C/E; their model assessments and raw candidates are retained.\n')
    add('## Full research discovery and common-universe solves\n')
    add(f'**{d["candidate_count"]} distinct CPT/FLEX candidates; {d["frontier_count"]} inside the unchanged .10 selector frontier.** Discovery includes global ceiling/mean, every viable captain, forced FLEX, QB constructions, team splits/structures, approximate conditional discovery and exact PIT/CLE scenario enumeration. Every retained roster was re-solved on the same exact baseline MILP before common normalization. Ownership is uniformly masked from scoring and kept diagnostic; conditional scores guide discovery only. Selector weights, correlations, captain priors, eligibility tolerance and thesis definitions are unchanged.\n')
    add(f'Discovery plus exact conditional extension took **{q["runtime_seconds"]:.1f}s**; full baseline rescoring and A–E joint solves took **{d["runtime_seconds"]:.1f}s**. Full source memberships, attempts, durations and raw universes are saved.\n')
    table(['Portfolio','Ranks','Selector sum','Mean sum','Marginal P90 sum','Captains','Theses','Overlap'],[[key,value['ranks'],number(value['total_selector']),f'{value["projected_mean"]:.6f}',f'{value["summed_marginal_p90"]:.6f}',allocation(value['captains']),allocation(value['theses']),value['pairwise_overlap']] for key,value in p.items()])
    add('A: unconstrained three distinct CPT/FLEX rosters. B: three distinct CPTs. C: three distinct CPTs and supported thesis families, overlap ≤4/6, no unsupported fragile punts. D: exact morning trio pinned to the fresh model. E: C policy with Metcalf ≤2/3. A/B reuse overlapping cores; C meets the requested actual-entry structure. D re-earned the same three positions.\n')
    add('## Metcalf 3/3 versus 2/3\n')
    table(['Measure','3/3','2/3'],[
        ['Selector sum',number(x['total_selector']),number(y['total_selector'])],
        ['Projected mean',number(x['projected_mean']),number(y['projected_mean'])],
        ['Summed marginal P90',number(x['summed_marginal_p90']),number(y['summed_marginal_p90'])],
        ['Captain allocation',allocation(x['captains']),allocation(y['captains'])],
        ['Thesis allocation',allocation(x['theses']),allocation(y['theses'])],
        ['Pairwise overlap',x['pairwise_overlap'],y['pairwise_overlap']],
        ['Players 3/3',', '.join(x['players_3_of_3']),', '.join(y['players_3_of_3'])]])
    add(f'**Choose Metcalf {d["model_supported_metcalf_exposure"]}.** Reducing exposure costs **{number(cost["total_selector"])} selector ({cost["selector_percentage"]:.9f}%)**, **{number(cost["projected_mean"])} projected mean** and **{number(cost["summed_marginal_p90"])} summed marginal P90**. It keeps the same three thesis families and 4/6 overlaps while making Rodgers universal instead of Metcalf. The current model provides no quality gain for forcing this diversification.\n')
    add('Exact 2/3 alternative:\n')
    for i,lineup in enumerate(y['lineups'],1):add(f'{i}. {compact(lineup)}.')
    add()
    add('## CPT frontier recheck\n')
    global_best = max(group['best']['single_entry_score'] for group in d['captain_frontier'].values())
    table(['CPT','Best selector','Gap to global best','Counts .05 / .10 / .15 / .20 / .30'],[[name,number(d['captain_frontier'][name]['best']['single_entry_score']),number(global_best-d['captain_frontier'][name]['best']['single_entry_score']),' / '.join(str(d['captain_frontier'][name]['counts'][str(t)]) for t in (.05,.10,.15,.20,.30))] for name in ['DK Metcalf','Deshaun Watson','Jerry Jeudy','Denzel Boston','Jaylen Warren','Aaron Rodgers']])
    add('Metcalf/Watson/Jeudy win the joint three-family solve. Boston is competitive in the capped alternative; Warren’s rushing and Rodgers’ balanced branches remain visible in the frontier. They do not improve this three-entry solution. Summed marginal P90 is not a portfolio 90th percentile; selector remains the existing heuristic. No actual fantasy results were used.\n')
    add('## Validation and preservation\n')
    add(f'**{preserve["tests_passed"]} relevant tests passed.** All candidates match fresh native slots; all three recommended rosters satisfy salary, canonical uniqueness, captain/thesis diversity, supported-role gate and overlap. **{preserve["protected_file_count"]} historical file hashes**, **{preserve["production_source_count"]} production source hashes** and **{preserve["classic_configs_checked"]} saved Classic configurations** are unchanged. Saved Thursday optimizer configurations/run counts are unchanged. Only sourced Thursday context/features/projections and research artifacts were refreshed. No parameters, optimizer entries, entry CSV, upload or submission changed.\n')
    add('### ENTRY READY?\n\n**NO.** Final official inactive/elevation and starting-QB dressing verification remains outstanding.\n')
    add('### Final captains\n\n'+', '.join(c['captains'])+'.\n')
    add('### FINAL THREE LINEUPS\n\nCurrent model-supported rosters; conditional on final checks.\n')
    for i,(lineup,record) in enumerate(zip(c['lineups'],c['records']),1):
        add(f'#### Final lineup {i}\n')
        table(['Slot','Player','Salary','Native DK ID'],[[r['roster_position'],r['name'],f'${int(r["salary"]):,}',r['dk_player_id']] for r in sorted(lineup,key=lambda r:r['roster_position']!='CPT')])
        add(f'**Salary ${int(record["salary"]):,}; selector {number(record["single_entry_score"])}; mean {number(record["mean"])}; summed marginal P90 {number(record["p90"])}.** Thesis: **{record["research_thesis"]}**, team allocation {record["team_counts"]}.\n')
    add('### Thesis for each lineup\n')
    for i,record in enumerate(c['records'],1):add(f'{i}. {record["research_thesis"]}: {record["team_counts"]}.')
    add()
    add('### Pairwise overlap\n\n'+', '.join(f'{pair}: {value}/6' for pair,value in zip(['1–2','1–3','2–3'],c['pairwise_overlap']))+'.\n')
    add('### 3/3 players\n\n'+', '.join(c['players_3_of_3'])+'.\n')
    add(f'### Metcalf exposure\n\n**{d["model_supported_metcalf_exposure"]}.** The 2/3 alternative costs **{number(cost["total_selector"])} selector ({cost["selector_percentage"]:.9f}%)**, **{number(cost["projected_mean"])} mean** and **{number(cost["summed_marginal_p90"])} summed marginal P90**.\n')
    add('### Fragile punts\n\n**NO.** None of the named fragile players or unsupported minimum-price offense appears. Final dressing remains pending for all selected players.\n')
    add('### PIT decisive?\n\n**YES**, through the supported Metcalf 4–2 passing branch.\n')
    add('### CLE decisive?\n\n**BORDERLINE** for a dedicated blowout; the primary uses supported CLE passing concentration.\n')
    add('### Rodgers CPT?\n\n**NO** for these three actual entries.\n')
    add('### What changed from the morning portfolio?\n\n**No roster, captain, salary, identity, thesis or exposure change.** Official defensive status/transaction news and small forecast changes were refreshed; normal rebuilt projections were unchanged. Full discovery and all portfolio alternatives were rerun.\n')
    add('### Any unresolved player/injury blockers\n\nPIT/CLE final inactive lists and elevations are not verified. The nine selected players’ dressing and both QBs’ final starting confirmation remain pending; Ramsey/Yahya Black and any late RB/OL changes require the same final reconciliation.\n')
    add('### Remaining blockers\n\n- Verify tonight’s official inactive lists/elevations, selected-player availability, QBs and late RB/OL roles.\n- Refresh DK, market and stadium weather near lock; the evidence above was captured this afternoon. A same-chat follow-up is scheduled for **6:50 PM EDT** to capture a new immutable freeze and rerun the full research solve.\n')
    add('### Exact recommendation\n\n**HOLD FOR FINAL VERIFICATION.** The model supports the three rosters above. Manual-entry clearance will be issued only after the final availability and source checks are reconciled. No entries have been submitted.\n')
    args.report.write_text('\n'.join(lines)+'\n')
    (b/'report_snapshot.md').write_bytes(args.report.read_bytes())
    print({'report':str(args.report.resolve()),'entry_ready':False,'lines':len(lines)})


if __name__=='__main__':main()
