"""Render saved matched preliminary Analyst runs; no solves or source refresh."""
from collections import Counter
import hashlib
import html
import json
from pathlib import Path


def signature(lineup):return tuple(sorted(str(p['player_id']) for p in lineup))
def name(player):return player.get('name',player.get('player_name',player['player_id']))
def names(lineup):return ', '.join(name(p) for p in lineup)
def total(lineup,key):return sum(float(p.get(key) or 0) for p in lineup)


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--directory',type=Path,required=True)
    args=parser.parse_args();root=args.directory
    old=json.loads((root/'old_result_v2.json').read_text());merged=json.loads((root/'merged_result_v3.json').read_text());snapshot=json.loads((root/'preliminary_snapshot_receipt.json').read_text());settings=json.loads((root/'shared_settings_v2.json').read_text())
    assert old['status']==merged['status']=='completed'
    for report in (old,merged):
        assert report['preliminary_report']['snapshot_sha256']==snapshot['snapshot_sha256']
        assert report['entry_readiness']['entry_ready'] is False
        assert report['data_readiness']['status']!='READY'
        assert report['projection_run_id']==snapshot['projection_run_id']
    oldlineups=old['results'];new=merged['results'];engine=merged['football_analyst'];scenarios=engine['scenario_definitions'];candidate_by_sig={tuple(sorted(p['player_master_id'] for p in c['roster'])):c for c in engine['candidates']}
    ids_to_player={str(p['player_id']):p for l in oldlineups+new for p in l}
    def exposure(lineups):return Counter(str(p['player_id']) for l in lineups for p in l)
    before=exposure(oldlineups);after=exposure(new)
    deltas=[]
    for index,lineup in enumerate(new,1):
        ids=set(signature(lineup));match=max(enumerate(oldlineups,1),key=lambda item:len(ids&set(signature(item[1]))))
        oldids=set(signature(match[1]));candidate=candidate_by_sig[signature(lineup)]
        deltas.append(dict(merged_lineup=index,closest_original_lineup=match[0],shared_players=len(ids&oldids),removed=[name(ids_to_player[p]) for p in sorted(oldids-ids)],added=[name(ids_to_player[p]) for p in sorted(ids-oldids)],scenario_ids=candidate['scenario_ids'],scenario_scores=candidate['scores'],base_mean=total(lineup,'projection'),base_p90_sum=total(lineup,'p90'),salary=total(lineup,'salary')))
    # Score BOTH arms under the same declared conditional metric. Never compare
    # the original solver objective with the merged normalized coverage objective.
    conditional={}
    for arm,lineups in [('original',oldlineups),('merged',new)]:
        conditional[arm]=[{s['scenario_id']:sum(s['moments'][str(p['player_id'])]['mean']+.35*(s['moments'][str(p['player_id'])]['p90']-s['moments'][str(p['player_id'])]['mean']) for p in lineup) for s in scenarios} for lineup in lineups]
    common=set(map(signature,oldlineups))&set(map(signature,new))
    report=dict(classification='PRELIMINARY_RESEARCH',entry_ready=False,experiment_kind='generation_and_selection_comparison',candidate_pools_identical=False,
        declared_treatment='Original CONSTRUCTION generation/scoring vs conditional scenario generation and portfolio coverage selection.',
        original_run_id=old['job_id'],merged_run_id=merged['job_id'],projection_run_id=snapshot['projection_run_id'],ownership_run_id=snapshot['ownership_run_id'],packet_sha256=engine['packet_sha256'],snapshot_sha256=snapshot['snapshot_sha256'],assumption_manifest_sha256=snapshot['assumption_manifest_sha256'],source_sha256=snapshot['source_sha256'],pool_sha256=snapshot['pool_sha256'],
        requested_portfolio_size=settings['params']['num_lineups'],achieved={'original':len(oldlineups),'merged':len(new)},same_canonical_rosters=len(common),
        settings=settings,normal_reason_codes=snapshot['normal_reason_codes'],assumption_manifest=snapshot['assumption_manifest'],roster_differences=deltas,
        exposures=[dict(player_id=pid,player=name(ids_to_player[pid]),original=before[pid],merged=after[pid]) for pid in sorted(set(before)|set(after),key=lambda p:(-max(before[p],after[p]),name(ids_to_player[p])))],
        conditional_metric='Conditional mean + 0.35 × nonnegative conditional P90 spread; sensitivity score, not calibrated lineup P90/EV.',conditional_scores=conditional,
        scenario_coverage={s['scenario_id']:{arm:max(row[s['scenario_id']] for row in conditional[arm]) for arm in conditional} for s in scenarios},
        limitations=['Unpublished applicable official injury/practice evidence remains missing.','All material current-questionable players excluded; no healthy or full-workload assumption.','Non-questionable roster/depth status does not establish game-day dressing or absence of injury.','Equal design weights and elasticities are uncalibrated.','Different generated pools: this is not an isolated controlled selector experiment or a performance forecast.','Season-average ranks intentionally unrestricted because complete Week5 snap coverage unavailable.'])
    (root/'comparison.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    lines=['# Preliminary Sunday Main — original vs merged Analyst strategy','',f"Both strategies saved {len(oldlineups)} and {len(new)} of {settings['params']['num_lineups']} requested lineups. **Not entry cleared.** They share the exact frozen input and injury-assumption snapshot. {len(common)} canonical rosters are identical.",'',f"Original run: `{old['job_id']}`. Merged run: `{merged['job_id']}`.",'',f"Projection: `{snapshot['projection_run_id']}`. Ownership: `{snapshot['ownership_run_id']}`.",'',f"Packet: `{engine['packet_sha256']}`. Frozen research snapshot: `{snapshot['snapshot_sha256']}`.",'','The preliminary snapshot excludes 25 material current-questionable players instead of assuming healthy or full workload. Other sourced roster/role facts and base projections are retained. The official Week6 injury feed still identifies the wrong week; missing practice/usage clocks remain unresolved. Normal readiness stays ERROR and final entry readiness stays false.','',f"Settings: 5 lineups; max exposure 100%; minimum uniqueness 2; max team 4/game 5; one TE; avoid offensive players against selected DST; favored RB/TE/DST; QB/RB minimum salary $4,500; no locks or manual exclusions. Season-average ranks: **No restriction** in both arms. The initial inferred app-rank defaults failed because Week5 snap coverage is incomplete; those attempts remain saved separately.",'','## Actual saved lineups','']
    for arm,lineups in [('Original construction',oldlineups),('Merged scenarios',new)]:
        lines.extend(['### '+arm,''])
        for i,lineup in enumerate(lineups,1):
            lines.extend([f"**Lineup {i} — ${total(lineup,'salary'):,.0f}; base projected mean {total(lineup,'projection'):.2f}; sum of player P90s {total(lineup,'p90'):.2f}.**",'', '| Position | Player | Team | Salary | Base mean |','|---|---|---|---:|---:|'])
            order={'QB':0,'RB':1,'WR':2,'TE':3,'DST':4}
            for p in sorted(lineup,key=lambda p:(order.get(p['position'],5),name(p))):lines.append(f"| {p['position']} | {name(p)} | {p.get('player_team',p.get('team',''))} | ${float(p['salary']):,.0f} | {float(p['projection']):.2f} |")
            lines.append('')
            if arm=='Merged scenarios':
                delta=deltas[i-1];lines.append('Generated under: '+', '.join(delta['scenario_ids'])+'.');lines.append('')
    lines.extend(['## Changed constructions',''])
    for d in deltas:lines.append(f"- Merged #{d['merged_lineup']} is closest to original #{d['closest_original_lineup']} ({d['shared_players']}/9 common): removes {', '.join(d['removed']) or 'none'}; adds {', '.join(d['added']) or 'none'}.")
    lines.extend(['','## Portfolio exposures','', '| Player | Original / 5 | Merged / 5 |','|---|---:|---:|'])
    for row in report['exposures']:lines.append(f"| {row['player']} | {row['original']} | {row['merged']} |")
    lines.extend(['','## Same-metric conditional outcome coverage','', 'The following compares the best selected roster under each identical sensitivity metric. This is conditional mean + 0.35 × conditional P90 spread, not calibrated lineup P90, payout probability or expected return. Original and merged solver objectives are not compared.','', '| Scenario | Original best conditional score | Merged best conditional score |','|---|---:|---:|'])
    for sid,scores in report['scenario_coverage'].items():lines.append(f"| {sid} | {scores['original']:.2f} | {scores['merged']:.2f} |")
    lines.extend(['','## Injury assumptions and selected-roster uncertainty','', 'All ten displayed rosters depend on the preliminary assumption manifest. None contains an unresolved current-questionable player; no player is newly assumed healthy. Each remaining player retains the sourced roster/role and base forecast, with current practice, workload and game-day dressing uncertainty explicitly unevaluated.','', 'Excluded material questionable players: '+', '.join(p.get('player',p['player_id'])+' ('+p.get('team','')+')' for p in snapshot['assumption_manifest']['players'])+'.','', 'Scenario IDs record the outcomes under which a candidate was generated. Repeated canonical rosters preserve all generating IDs; that overlap does not establish a unique origin or guarantee every football hypothesis will occur.'])
    lines.extend(['',engine['selection']['selection_reason']+'.','', 'This is a generation-and-selection comparison with different candidate pools. It demonstrates roster and exposure consequences of declared assumptions, not an isolated selector experiment or evidence of improved future performance. No contest submission or CSV export occurred.','', '[Machine comparison](comparison.json) · [Original saved response](old_result_v2.json) · [Merged saved response](merged_result_v3.json) · [Frozen assumptions](preliminary_snapshot_receipt.json)'])
    markdown='\n'.join(lines)+'\n';(root/'LINEUP_COMPARISON.md').write_text(markdown)
    def portfolio_table(lineups):
        rendered=[]
        for i,lineup in enumerate(lineups,1):
            cells=[str(i)]+[html.escape(', '.join(name(p) for p in lineup if p['position']==position)) for position in ('QB','RB','WR','TE','DST')]+[f'${total(lineup,"salary"):,.0f}',f'{total(lineup,"projection"):.2f}']
            rendered.append('<tr>'+''.join('<td>'+cell+'</td>' for cell in cells)+'</tr>')
        return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+h+'</th>' for h in ('#','QB','RB','WR','TE','DST','Salary','Base mean'))+'</tr></thead><tbody>'+''.join(rendered)+'</tbody></table></div>'
    swaps=''.join('<li>Merged #'+str(d['merged_lineup'])+' vs closest original #'+str(d['closest_original_lineup'])+': '+str(d['shared_players'])+'/9 shared. Removes '+html.escape(', '.join(d['removed']) or 'none')+'; adds '+html.escape(', '.join(d['added']) or 'none')+'. Generated under '+html.escape(', '.join(d['scenario_ids']))+'.</li>' for d in deltas)
    exposure_rows=''.join('<tr><td>'+html.escape(row['player'])+'</td><td>'+str(row['original'])+'/5</td><td>'+str(row['merged'])+'/5</td></tr>' for row in report['exposures'])
    coverage_rows=''.join('<tr><td>'+html.escape(sid)+'</td><td>'+f'{scores["original"]:.2f}'+'</td><td>'+f'{scores["merged"]:.2f}'+'</td></tr>' for sid,scores in report['scenario_coverage'].items())
    page='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Preliminary Sunday Main comparison</title><style>body{font:15px system-ui;max-width:1400px;margin:32px auto;padding:0 20px;line-height:1.5;color:#172333;background:#f7f9fc}h1,h2{color:#12334d}.banner{padding:20px;background:#fff0d4;border:1px solid #dcac48;border-radius:10px}.scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;background:white;margin:16px 0}th,td{padding:12px;border-bottom:1px solid #d8e0e8;text-align:left;vertical-align:top}th{background:#e8eff7}pre{white-space:pre-wrap;overflow-wrap:anywhere}li{margin:12px 0}a{color:#135f97}</style></head><body><h1>Sunday Main — original vs merged Analyst strategy</h1><div class="banner"><strong>PRELIMINARY RESEARCH · NOT ENTRY CLEARED</strong><p>5/5 lineups saved in both portfolios; '+str(len(common))+'/5 identical canonical rosters. Same immutable inputs and injury assumptions. Current questionable players excluded; no healthy or full-workload clearance inferred. Normal readiness remains ERROR; contest CSV export is blocked.</p></div><p>Original run '+html.escape(old['job_id'])+' · Merged run '+html.escape(merged['job_id'])+'</p><p>Shared settings: five lineups, single TE, favored RB/TE/DST, 100% exposure maximum, team 4/game 5, minimum uniqueness 2, avoid DST opponents, QB/RB salary minimum $4,500. Season ranks: No restriction because Week5 snap coverage is incomplete.</p><h2>Original construction portfolio</h2>'+portfolio_table(oldlineups)+'<h2>Merged scenario portfolio</h2>'+portfolio_table(new)+'<h2>Changed constructions</h2><ul>'+swaps+'</ul><h2>Player exposures</h2><table><thead><tr><th>Player</th><th>Original</th><th>Merged</th></tr></thead><tbody>'+exposure_rows+'</tbody></table><h2>Same-metric conditional outcome coverage</h2><p>Best selected roster under each shared sensitivity metric: conditional mean + 0.35 × conditional P90 spread. These are uncalibrated scores, not lineup P90 or expected return. Original and merged solver objectives are not compared.</p><table><thead><tr><th>Scenario</th><th>Original best score</th><th>Merged best score</th></tr></thead><tbody>'+coverage_rows+'</tbody></table><p>Different generated pools: this demonstrates generation and selection consequences, not an isolated selector experiment or future performance improvement.</p><p><a href="LINEUP_COMPARISON.md">Full player salaries/base means and injury assumptions</a> · <a href="comparison.json">Machine comparison</a> · <a href="independent_verification.json">Independent checks</a></p><details><summary>Exact frozen snapshot and assumptions</summary><pre>'+html.escape(json.dumps(snapshot,indent=2))+'</pre></details></body></html>'
    (root/'LINEUP_COMPARISON.html').write_text(page)
    print(json.dumps({'original':len(oldlineups),'merged':len(new),'same_rosters':len(common),'differences':deltas},indent=2))


if __name__=='__main__':main()
