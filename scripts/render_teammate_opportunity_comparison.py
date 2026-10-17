"""Render actual persisted all-slate paired research and explicit apply receipt."""
import json,html
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'research/analyst_teammate_opportunity_20261014'
def load(n):return json.loads((OUT/n).read_text())
def table(rows):
 return '| Position | Player | Salary | Base DK mean |\n|---|---|---:|---:|\n'+'\n'.join(f"| {r['position']} | {r.get('name',r.get('player_name'))} | ${float(r['salary']):,.0f} | {float(r.get('projection',r.get('base_mean',0))):.2f} |" for r in rows)
def main():
 source,applied=load('source_result.json'),load('apply_result.json'); t=source['football_analyst']['teammate_opportunity']; choice=applied['football_analyst']['teammate_opportunity']['applied_choice'];p=source['football_analyst']['packet_sha256']
 text=[f'# Sunday Main: all Analyst tools and cheaper-teammate review\n\nActual saved runs: source `{source["job_id"]}`; explicit Ty apply `{applied["job_id"]}`. Both five of five. Packet `{p}`. The same frozen Sunday projection/salary/ownership and Q-exclusion manifest are used. Both are **PRELIMINARY_RESEARCH; not entry cleared**. New optional saved team/game outlook is an unproven conditional sensitivity, separately identified from canonical projections. Older v4 frozen precheck is preserved and has different conditional numbers; this report uses actual v5 live runs.\n',
 'Discovery reserved the sourced provisional NE running branch (Stevenson), Rams passing, CAR passing, BAL rushing and a hunter Rams-rushing/Puka-downside alternative complete the source portfolio. The hunter uses an explicit low-end stress, not a factual injury prediction. Discovery, planning and hunter traces are saved before/after their respective steps. Specialists screened all20 Sunday DST: all remain watchlist, with no unsupported boost.\n',
 'The teammate pass scanned all10 games and ran six bounded solves for three same-game pairs. It does not automatically replace the portfolio. The user-selected Ty receiving-back hypothesis then replaced only slot3 after full exposure, legality, uniqueness and discovery-reservation revalidation. Slots1/2/4/5 remain canonical-equal. No constraints were relaxed; no95% quality veto.\n']
 for label,data in [('All-feature source portfolio',source),('Explicit Ty alternative portfolio',applied)]:
  text.append('## '+label+'\n')
  for i,roster in enumerate(data['results'],1):
   first=roster[0];score=first.get('analyst_scenario_scores',{});key=first.get('analyst_challenger_conditions') or next(iter(first.get('analyst_thesis_ids') or []),''); own=score.get(key)
   text.append(f"### Lineup {i}\n\nSalary ${sum(float(r['salary']) for r in roster):,.0f}; base mean {sum(float(r['projection']) for r in roster):.2f}. Idea `{first.get('analyst_allocated_idea_id')}`. Conditional selector score {own if own is not None else 'see saved scenario score vector'} (mean/upside sensitivity score, not expected DK points).\n\n"+table(roster)+'\n')
 text.append('## Whole-roster paired alternatives\n\nAll branches retain unchanged base forecasts. Conditional means below belong to their declared same-game sensitivity; they are not forecasts of expected performance. Salary saving alone is not the ranking criterion.\n')
 for pair in t['pairs']:
  if pair['status']!='paired_evaluated':continue
  text.append(f"### {pair['primary_name']} → {pair['backup_name']}\n\nSame-game channel: {pair['channel']}; saves ${pair['salary_saved']:,.0f}, reinvests ${pair['salary_saved_reinvested']:,.0f}. Base roster mean change {pair['base_mean_delta']:+.2f}; conditional mean change {pair['conditional_mean_delta']:+.2f}; conditional selector score change {pair['conditional_score_delta']:+.2f}. Secondary-player break-even {pair['secondary_points_break_even']:.2f} DK points under this sensitivity. {pair['reason']}. Possible legal portfolio replacement slots: {pair['possible_portfolio_replacement_slots']}.\n\nMechanism: {pair['conditional_mechanism']}. Counterevidence: {'; '.join(pair['counterevidence'])}\n")
  for name,b in pair['branches'].items():
   text.append(f"**{name}** — salary ${b['salary']:,.0f}, base {b['base_mean']:.2f}, conditional mean {b['conditional_mean']:.2f}, conditional selector score {b['conditional_score']:.2f}.\n\n"+table(b['roster'])+'\n')
  if pair.get('conditional_point_checks'):text.append('\n'.join(f"User what-if {c['secondary_points']:.0f} DK points → full-roster conditional mean {c['full_lineup_conditional_mean']:.2f}, difference {c['delta_vs_primary']:+.2f} versus primary. This was not an optimization bonus or expected projection." for c in pair['conditional_point_checks'])+'\n')
 text.append('## All-game coverage and rejections\n')
 for game in t['scanned_games']:text.append('`'+str(game)+'`\n')
 text.append('| Team | Primary → cheaper | Savings | Status / reason |\n|---|---|---:|---|')
 for pair in t['pairs']:text.append(f"| {pair['team']} | {pair['primary_name']} → {pair['backup_name']} | ${pair['salary_saved']:,.0f} | {pair['status']}: {pair.get('reason','')} |")
 text.append('\nChicago: Swift $6,700 versus Monangai $5,200 is excluded by the explicit Q policy, not inferred absent; Roschon $4,200 is below the unchanged $4,500 RB minimum. No legal supported Chicago substitution is admitted under these controls.\n')
 text.append('## Corum 10–15 DK points: conditions, not a forecast\n\nDK gives0.1 per rushing/receiving yard,1 per catch,6 per rushing/receiving TD and a3-point100-yard rushing bonus. For illustration with no fumbles:50 rushing yards + one10-yard catch =7 points; a TD makes13.60 rushing + two catches/20 receiving =10.80 rushing + three catches/30 receiving =14.100 rushing yards alone reaches13 with the bonus. These are scoring identities, not proposed probabilities or guaranteed touches. [DraftKings scoring guide](https://dknetwork.draftkings.com/2025/08/27/nfl-dfs-beginners-guide-draftkings/). Saved historical PPR points are not treated as DK projections.\n\nCorum has a sourced secondary role and positive workload proxy, but neither depth order nor a Rams lead proves a coaching split or valuable TD opportunity. The conserved bounded sensitivity retains Kyren opportunity and does not grant Corum all starter work. Even the15-point what-if loses to the same-branch primary roster here. Ty’s positive conditional full-lineup result is a receiving-back hypothesis, not evidence that he will outscore Cook.\n')
 text.append('## Explicit apply lineage and exposures\n\n```json\n'+json.dumps(choice,indent=2)+'\n```\n')
 text.append('Original persisted apply receipt retained its paired-phase portfolio_effect sentence saying unchanged; its explicit applied_choice and saved rosters are authoritative. This stale explanation is corrected for future runs. Actual source portfolio base sum665.034→660.755 (−4.279); the paired Ty primary/cheaper base delta−4.59 compares different same-branch full rosters and is not that portfolio delta.\n')
 counts=[]
 for data in [source,applied]:counts.append(Counter(r['name'] for roster in data['results'] for r in roster))
 text.append('| Player | Source /5 | Applied /5 |\n|---|---:|---:|')
 for n in sorted(set(counts[0])|set(counts[1])):
  if counts[0][n]!=counts[1][n]:text.append(f'| {n} | {counts[0][n]} | {counts[1][n]} |')
 (OUT/'LINEUP_COMPARISON.md').write_text('\n\n'.join(text));(OUT/'LINEUP_COMPARISON.html').write_text('<!doctype html><meta charset="utf-8"><title>Sunday Analyst comparison</title><style>body{font:16px system-ui;max-width:1200px;margin:30px auto}pre{white-space:pre-wrap}</style><pre>'+html.escape('\n\n'.join(text))+'</pre>')
 (OUT/'comparison.json').write_text(json.dumps(dict(source_run_id=source['job_id'],applied_run_id=applied['job_id'],packet_sha256=p,source=source,applied=applied),indent=2))
if __name__=='__main__':main()
