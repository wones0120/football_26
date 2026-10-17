"""Render saved actual focused-generation comparisons, never infer output from requests."""
from pathlib import Path
from collections import Counter
import json,html,re
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'research/analyst_contrarian_focus_20261014'
def load(name):return json.loads((OUT/(name+'.json')).read_text())
def ids(roster):return tuple(sorted((r['player_id'],r.get('roster_position','SELECTED')) for r in roster))
def mean(roster):return sum(float(r['projection']) for r in roster)
def conditional(roster,scenario):return sum((1.5 if r.get('roster_position')=='CPT' else 1)*scenario['moments'][r['player_id']]['mean'] for r in roster)
def render(label,before,after,world):
 lines=[f'# {label}: mixed versus explicit football focus',f"Actual saved runs `{before['job_id']}` and `{after['job_id']}`. Requested 5; achieved {len(before['results'])}/{len(after['results'])}. Canonical base projection and salary inputs remain unchanged. These are conditional research constructions, not proven edges or entry-cleared forecasts.",f"Packet `{after['football_analyst']['packet_sha256']}`; projection `{after['projection_run_id']}`. Selected IDs `{after['football_analyst']['focus']['selected_scenario_ids']}`. Common comparison world `{world['scenario_id']}` is evaluated identically for both portfolios. Conditional mean is an opportunity sensitivity in DK units; it is not a calibrated expected score. Selector utility also includes a spread term and is reported separately in saved JSON."]
 if label.startswith('Thursday'):
  lines+=['The original flawed run09f62bfe is preserved: four cheap unsupported Captains received equal self-normalized coverage votes because other-Captain rosters were zeroed in each world. The corrected engine scores every roster under shared moments and counts equivalent numeric outcomes once. Automatically authored stories require positive sourced primary-role opportunity or a supported Captain opinion; an explicit lock remains a transparent what-if. Missing dated-packet workload may use labeled fresh prepared projection proxies, not invented observed usage.', 'Denver roughly 40 points is the user’s what-if. This sensitivity shifts18 percentage points of a conserved 100-unit skill-opportunity mix toward passing, with bounded optional outlook tilts. It requires sustained protection/decisions, successful drives and TD finishing; no source proves a breakout or40-point probability. No automatic opponent bringback is required. This engine does not fit exact score-target-conditioned touchdown or efficiency distributions.', 'Both final requests share candidate budget2, five-lineup count, fresh normal preparation, ownership, projection, Q policy and other user settings. Only selected-only focus/IDs differ. First focused attempt underfilled 2/5 and saved no usable lineups; its failure/partial trace remains separate. Final correction consumes legitimate fresh prepared workload proxies consistently in both reruns; no preference was relaxed. The normal old top-four candidates on these inputs are Bo Nix, Sam Darnold, J.K. Dobbins and Emanuel Wilson; that read-only shortlist receipt is saved, not claimed as a newly generated legacy portfolio.']
 else:
  lines+=['Both Sunday builds retain the frozen preliminary snapshot 1d4bd679 and its explicit 25-questionable exclusions; final entry readiness remains false. New weekly source observations were captured after the original projection snapshot and are explicitly conditional research context with a later packet decision clock. Cook’s two fumbles/one lost and return to rushing, and Kyle Williams’ receiving game, remain watchlists. They create no arbitrary fumble penalty, motivation bonus or assumed next-game workload shift.', 'BUF running focus is a sourced conditional opportunity alternative, not a claim of low ownership or a proven model gap. Every focused lineup requires a BUF RB and omits its own QB under the same run-control construction; remaining slots can use other games. A focused portfolio intentionally shares that selected football outcome and must not be described as five independent scripts. The mixed build enables its bounded hunters/research; focused mode explicitly disables unselected hunter/teammate branches. This is a generation experiment, not a fixed-candidate-pool selector test.']
 for name,data in [('Corrected mixed' if label.startswith('Thursday') else 'Weekly mixed',before),('Selected football focus',after)]:
  lines.append('## '+name)
  for i,l in enumerate(data['results'],1):
   lines.append(f"### Lineup {i}\n\nSalary ${sum(r['salary'] for r in l):,.0f}; base DK mean {mean(l):.2f}; common conditional mean {conditional(l,world):.2f}. Focus compliance: {l[0].get('analyst_focus_story_compliance','not applicable')}.")
   lines.append('| Role/position | Player | Salary | Base DK mean |\n|---|---|---:|---:|\n'+'\n'.join(f"| {r.get('roster_position',r['position'])} | {r['name']} | ${r['salary']:,.0f} | {r['projection']:.2f} |" for r in l))
 lines.append('## Exposure changes\n\n| Player | Mixed /5 | Focus /5 |\n|---|---:|---:|')
 a,b=[Counter(r['name'] for l in d['results'] for r in l) for d in [before,after]]
 for n in sorted(set(a)|set(b)):
  if a[n]!=b[n]:lines.append(f'| {n} | {a[n]} | {b[n]} |')
 overlap=len({ids(l) for l in before['results']} & {ids(l) for l in after['results']});lines.append(f'Canonical format-aware roster overlap: {overlap}/5. Base portfolio mean sum: {sum(mean(l) for l in before["results"]):.2f}→{sum(mean(l) for l in after["results"]):.2f}. Common conditional mean sum: {sum(conditional(l,world) for l in before["results"]):.2f}→{sum(conditional(l,world) for l in after["results"]):.2f}. These are opportunity costs under assumptions, not profit or future-performance evidence.')
 lines.append('## Saved authority and limitations\n\n```json\n'+json.dumps(after['football_analyst']['focus'],indent=2)+'\n```')
 if label.startswith('Thursday'):
  report=after['football_analyst']['captain_analysis'];lines.append('| Captain | Story authority | Opportunity proxy | Generated / selected |\n|---|---|---:|---:|')
  for a in report['assessments']:lines.append(f"| {a['player_name']} | {a.get('story_authority',a.get('suppression_reason'))} | {a.get('measured_channel_opportunity','unknown')} | {a.get('generated_candidate_count',0)} / {a.get('selected_lineup_count',0)} |")
 filename='THURSDAY_COMPARISON' if label.startswith('Thursday') else 'SUNDAY_COMPARISON';text=re.sub(r'(?<=\|)\n\n(?=\|)', '\n', '\n\n'.join(lines));(OUT/(filename+'.md')).write_text(text);(OUT/(filename+'.html')).write_text('<!doctype html><meta charset="utf-8"><style>body{font:16px system-ui;max-width:1200px;margin:30px auto}pre{white-space:pre-wrap}</style><pre>'+html.escape(text)+'</pre>')
 return dict(before_run_id=before['job_id'],after_run_id=after['job_id'],canonical_overlap=overlap,achieved=[len(before['results']),len(after['results'])],common_scenario_id=world['scenario_id'])
def main():
 summary={}
 for label,a,b in [('Thursday','thursday_corrected_final_result','thursday_denver_focus_final_result'),('Sunday','sunday_weekly_mixed_result','sunday_buf_run_focus_result')]:
  if not (OUT/(a+'.json')).exists() or not (OUT/(b+'.json')).exists():continue
  before,after=load(a),load(b)
  if not before.get('results') or not after.get('results'):continue
  world=after['football_analyst']['scenario_definitions'][0];summary[label]=render(label,before,after,world)
 (OUT/'comparison_summary.json').write_text(json.dumps(summary,indent=2))
if __name__=='__main__':main()
