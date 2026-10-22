"""Evidence-bound retrospective review; never regenerate or alter saved lineups."""
import csv
from datetime import datetime
import hashlib
import html
import json
from pathlib import Path
from backend.app.services.simulation import calculate_dk_points

OUT=Path(__file__).parent
BASE=Path('research/opportunity_component_response_20261019/v1')
d=json.loads((OUT/'database_evidence.json').read_text())
s=json.loads((BASE/'new_count_saved_results.json').read_text())
lock=datetime.fromisoformat('2026-10-19T20:15:00-04:00')
assert datetime.fromisoformat(s['created_at'])<lock
assert datetime.fromisoformat(s['data_cutoff_at'])<lock
win=next(e for e in d['entries'] if e['entry_id']=='5303799674')
assert win['rank']==1 and win['entry_points']==123.75
lineup=s['results'][0]
signature=lambda ps:sorted((p['player_id'],p.get('roster_position',p.get('slot'))) for p in ps)
matches=[l for l in d['lineups'] if signature(l['players'])==signature(lineup)]
assert len(matches)==3
native=list(csv.reader((BASE/'verified_recommended.csv').open()))
assert native[0]==['CPT']+['FLEX']*5
assert native[1][0]==str(lineup[0]['dk_player_id'])
assert set(native[1][1:])=={str(p['dk_player_id']) for p in lineup[1:]}
actual={r['player_id']:r['raw_row_json'] for r in d['actual_stats']}
prior={r['raw_nfl_weekly_stat_id']:r for r in d['prior_stats']}
rows=[]
for p in lineup:
    f=p['workload_forecast'];role=f['current_role_evidence']
    assert datetime.fromisoformat(role['observed_at'])<lock
    assert datetime.fromisoformat(role['received_at'])<lock
    for sid in f['source_ids']:
        r=prior[sid]
        assert r['season']==2026 and r['week']<6
        # These ingest clocks are naive. Even treating them as local Eastern,
        # all precede kickoff by at least six days; no timezone guess affects it.
        assert datetime.fromisoformat(r['ingest_completed_at']).date()<lock.date()
    native_ids={prior[sid]['player_id'] for sid in f['source_ids']}
    assert len(native_ids)==1
    stat=actual[next(iter(native_ids))]
    points=calculate_dk_points(stat,floor_at_zero=False)
    rows.append(dict(name=p['name'],player_id=p['player_id'],slot=p['roster_position'],salary=p['salary'],
        role=p['canonical_role'],last_snap_share=p['snap_share_last'],raw_history=f['raw_history'],
        forecast=f['counts'],conditional_on=f['conditional_on'],base_fp_mean=p['base_projection'],
        actual_base_points=round(points,2),actual_slot_points=round(points*(1.5 if p['roster_position']=='CPT' else 1),2),
        actual_stat={k:stat.get(k) for k in ['attempts','passing_yards','passing_tds','carries','rushing_yards','rushing_tds','targets','receptions','receiving_yards','receiving_tds','fumbles_lost_total']}))
assert abs(sum(p['actual_slot_points'] for p in rows)-win['entry_points'])<.001
assert sum(p['salary'] for p in rows)==49900
assert abs(sum(p['projection'] for p in lineup)-65.0018594211405)<1e-8
cmc=next(p for p in rows if p['name']=='Christian McCaffrey')
dan=next(p for p in rows if p['name']=='Jayden Daniels')
same_six_daniels=win['entry_points']-.5*(cmc['actual_base_points']-dan['actual_base_points'])
same_six_salary=49900-.5*(11800-10000)
assert abs(same_six_daniels-119.9)<1e-8 and same_six_salary==49000
pool={p['player_id']:p for p in s['player_pool']['rows']}
ok=next(p for p in pool.values() if p['player_name']=='Chig Okonkwo')
antonio=next(p for p in rows if p['name']=='Antonio Williams')
same_six_mean=sum(p['projection'] for p in lineup)-.5*(cmc['base_fp_mean']-dan['base_fp_mean'])
alt_mean=same_six_mean-antonio['base_fp_mean']+ok['projection']
assert abs(alt_mean-68.45705409816275)<1e-7
findings={
 'Christian McCaffrey':'Strong role-based Captain candidate: starter, 82% latest snaps, prior 13.67 carries and 4.33 targets. Ten actual targets, nine receptions and two rushing TDs were favorable outcomes beyond a guaranteed workload. No verified pregame goal-line share.',
 'George Kittle':'Strong FLEX role: starter, 92% latest snaps, prior targets 7/6/6. Count forecast 7.54 targets versus eight actual; touchdown outcome was uncertain. Omitting Purdy saved salary while retaining concentrated SF receiving exposure.',
 'Jayden Daniels':'Strong dual-path FLEX role: starting QB, 100% latest snaps, seven carries per last three recorded appearances. Those appearances were W1/W2/W5, not three consecutive weeks. Actual 40 attempts exceeded 27.93 forecast; 300-yard bonus helped, while rushing volume was lower.',
 'Rachaad White':'Conditional backfield choice: backup label, 60% latest snaps and prior carries 7/8/7 supported involvement. No verified sole replacement role. Forecast 5.97 carries/1.78 targets; actual seven carries/five targets and receiving TD supplied favorable receiving production.',
 'Treylon Burks':'Reasonable salary-saving FLEX with role risk: $3200, backup label but 73% latest snaps and prior targets 2/3/5. Six targets, four receptions and 66 yards produced 10.6 points without a TD. Forecast 4.75 targets remained conditional on participation.',
 'Antonio Williams':'Reasonable salary-saving FLEX with role risk: $4200, backup label but 68% latest snaps and prior targets 4/8/3. Forecast 4.11 targets versus four actual; three receptions and 50 yards produced eight points without a TD. A larger guaranteed role was not established.',
}
for p in rows:p['assessment']=findings[p['name']]
report=dict(entry=win,players=rows,matching_saved_lineups=[{k:l[k] for k in ['lineup_id','optimizer_run_id','created_at']} for l in matches],
 chronology={'run_created_at':s['created_at'],'source_cutoff':s['data_cutoff_at'],'kickoff':lock.isoformat(),
 'prior_stat_source_rows':len(prior),'latest_prior_stat_ingest':max(r['ingest_completed_at'] for r in prior.values()),
 'caveat':'Latest run clock is prelock but its lineup-table created_at is four hours later and after lock. Preserve inconsistency. Two earlier matching lineup rows are before lock even with stored timezone. No assignment links exist for observed entry, so unique export origin is unproven.'},
 method={'objective':'normalized offensive counts, not highest fantasy points or calibrated tournament EV','new_analyst_worlds_consumed':False,
 'expected_return':None,'paid_finish_probability':None,'note':'Historical source facts, conditional count forecasts and reported point means are distinct.'},
 comparisons={'actual_winner':123.75,'runner_up':119.81,'winning_margin':3.94,'same_six_daniels_captain':round(same_six_daniels,2),
 'same_six_daniels_margin_against_observed_runnerup':.09,'same_six_daniels_salary':same_six_salary,
 'same_six_daniels_reported_mean':same_six_mean,'daniels_plus_okonkwo_reported_mean':alt_mean,
 'daniels_plus_okonkwo_salary':49400,'daniels_plus_okonkwo_actual_points':125.8,
 'comparison_note':'Actuals-held-fixed arithmetic, not a physical counterfactual or a claim these alternatives were submitted. The identical-six Daniels alternative was saved #3 in the final run.'},
 limits=['Retrospective review after outcomes had already been inspected; no fresh held-out validation.',
 'No calibrated skill/luck percentage or tournament-success probability is supported.',
 'Four WAS players share team-drive failure and targets; including a rushing RB does not create independent opportunities.',
 'The archived roster-scoped upload check was provisional; it did not confirm final game dressing.',
 'No proof of unique saved-run/export origin; canonical roster corresponds to three runs.',
 'Higher-than-model scoring may reflect forecast error as well as outcome variance; do not label every positive residual luck.'])
(OUT/'review.json').write_text(json.dumps(report,indent=2)+'\n')
def table(headers,rs):
    esc=lambda x:html.escape(str(x))
    return '<table><tr>'+''.join('<th>'+esc(h)+'</th>' for h in headers)+'</tr>'+''.join('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in row)+'</tr>' for row in rs)+'</table>'
body='<h1>McCaffrey winning-entry pregame review</h1><p>Observed entry 5303799674, contest 196944422, wones0120 (2/2), rank 1 of 1189, 123.75 points, $49,900 roster salary. Local imported evidence only.</p>'
body+='<h2>Pregame case and outcome</h2>'+table(['Player','Slot','Latest prior snap share','Prior raw usage','Count forecast','Actual base DK points','Assessment'],[[p['name'],p['slot'],f"{p['last_snap_share']:.0%}",json.dumps(p['raw_history']),json.dumps(p['forecast']),p['actual_base_points'],p['assessment']] for p in rows])
body+='<h2>Whole-lineup mechanism</h2><p>CMC ground and receiving production plus Kittle receiving concentration supply SF points without paying for Purdy. Daniels supplies Washington passing/rushing points; White/Burks/Antonio need genuine participation on functioning drives. Four Washington slots share drive failure; the pass catchers compete for targets. SF rushing TDs and Kittle receiving TDs can occur on separate possessions. This is plausible, not a calibrated likelihood.</p>'
body+='<h2>Complete matched-input alternatives</h2>'+table(['Construction','Captain','Five FLEX','Salary','Pregame reported FP mean','Actual points'],[
 ['Observed winner','McCaffrey','Daniels / Kittle / White / Burks / Antonio',49900,65.0018594211405,123.75],
 ['Same six; saved final #3','Daniels','McCaffrey / Kittle / White / Burks / Antonio',49000,same_six_mean,119.9],
 ['Retrospectively constructed legal comparison','Daniels','McCaffrey / Kittle / White / Burks / Okonkwo',49400,alt_mean,125.8]])
body+='<p>The workload objective selected the first roster; it did not claim the highest fantasy-point mean. Forecast calibration/selector superiority cannot be established by one winning result. Highest scorer Captain increased this roster by3.85 points; holding the observed field fixed, the same-six Daniels roster still beats119.81 by0.09.</p>'
body+='<h2>Chronology and provenance</h2><p>'+html.escape(report['chronology']['caveat'])+'</p><p>Prior-stat ingestion completed by Oct13. Role evidence observed and received on Oct19 before kickoff. Final run recorded7:53PMET, cutoff7:00PMET, kickoff8:15PMET. Recommended CSV native IDs exactly match the saved roster. Recorded availability review7:58PMET remained provisional.</p>'
body+='<h2>Limitations</h2><ul>'+''.join('<li>'+html.escape(v)+'</li>' for v in report['limits'])+'</ul>'
(OUT/'review.html').write_text('<!doctype html><meta charset="utf-8"><title>Winning McCaffrey pregame review</title><style>body{font:16px system-ui;max-width:1400px;margin:36px auto;padding:0 20px;line-height:1.5;color:#172332}table{border-collapse:collapse;width:100%;font-size:14px}th,td{border:1px solid #ccd5df;padding:10px;text-align:left;vertical-align:top}th{background:#eef3f8}h2{margin-top:35px}</style>'+body)
paths=[OUT/'database_evidence.json',OUT/'assignment_evidence.json',BASE/'new_count_saved_results.json',BASE/'verified_recommended.csv',BASE/'new_count_upload_readiness.json']
(OUT/'validation.json').write_text(json.dumps({'checks':'passed: canonical roster correspondence, native CSV identity, six unique players, salary, raw-stat chronology, role source chronology, exact DK actual-score reconciliation, alternative salary/scoring arithmetic',
 'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},'limitations':report['limits'],'timestamp_inconsistency_preserved':True},indent=2)+'\n')
print(json.dumps({'entry':win['entry_id'],'matches':len(matches),'actual_points':sum(p['actual_slot_points'] for p in rows),'alternative_mean':alt_mean,'checks':'passed'}))
