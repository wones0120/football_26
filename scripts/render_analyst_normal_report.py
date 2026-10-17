"""Render actual normal-pipeline Analyst evidence, candidates and selected rosters."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path)
    args=parser.parse_args();root=args.directory
    baseline=json.loads((root/'without_analyst.json').read_text())
    current=json.loads((root/'with_analyst.json').read_text())
    report=current['params']['strategy_runtime']['football_analyst']
    selected=current['lineups']; names={str(p['player_id']):p['name'] for lineup in selected+baseline['lineups'] for p in lineup}
    # Canonical names from saved normal pool audit cover unselected candidates too.
    for row in current['params'].get('player_pool_report',{}).get('players',[]):
        names.setdefault(str(row.get('player_id')), row.get('name'))
    selector=current['params']['strategy_runtime'].get('showdown_portfolio_policy',{}).get('candidate_selection',{})
    for row in selector.get('ranked_metrics',[]):
        for p in row.get('players',[]): names.setdefault(str(p['player_id']),p['name'])
    baseline_keys={tuple(sorted((str(p['player_id']),p['roster_position']) for p in lineup)) for lineup in baseline['lineups']}
    lines=['# Thursday Analyst normal-generation test','',
      '**The imported packet entered normal construction generation and the existing selector. This replay used exported real inputs and in-memory checkpoints; live readiness remains unapproved.**','',
      'Packet: `'+report['packet_sha256']+'`. Stored base projection cutoff and analyst analysis time are retained independently in source/packet artifacts. Later opinions are evaluated at the current research decision, not backdated to the projection cutoff.','',
      'Without Analyst: '+baseline['message'], 'With Analyst: '+current['message'],'',
      '| Analyst thought | Typed construction | Requested / generated | Outcome |','|---|---|---|---|']
    for t in report['theses']:
        ids=t.get('candidate_ids',[]); rows=[r for r in report['shadow'] if r['candidate_id'] in ids]
        outcomes=', '.join(('selected' if r.get('selected') else 'not selected')+'; quality '+str(r.get('quality_eligible','not separately evaluated')) for r in rows) or ', '.join(t['reasons'])
        lines.append('| '+str(t['analyst_thought']).replace('|','/')+' | '+t['construction']['type']+' | '+str(t['requested'])+' / '+str(t['achieved'])+' | '+outcomes+' |')
    lines+=['','## Generated Analyst candidates','','| Candidate | Captain | FLEX | Salary | Mean | Original objective |95% screen | Selected |','|---|---|---|---:|---:|---:|---|---|']
    for i,r in enumerate(report['shadow'],1):
        cap=next(p['player_master_id'] for p in r['roster'] if p['role']=='CPT')
        flex=', '.join(names.get(p['player_master_id'],p['player_master_id']) for p in r['roster'] if p['role']=='FLEX')
        lines.append('| '+str(i)+' | '+names.get(cap,cap)+' | '+flex+' | '+str(round(r['salary']))+' | '+str(round(r['projected_mean'],2))+' | '+str(round(r['baseline_objective'],4))+' | '+str(r.get('quality_eligible','Not separately evaluated'))+' | '+str(r.get('selected','See selected roster table'))+' |')
    lines+=['','## Selected normal portfolio','','| Lineup | Captain | FLEX | Salary | Mean | Analyst thesis attribution | Baseline selected roster? |','|---|---|---|---:|---:|---|---|']
    for i,lineup in enumerate(selected,1):
        cap=next(p for p in lineup if p['roster_position']=='CPT')
        key=tuple(sorted((str(p['player_id']),p['roster_position']) for p in lineup))
        lines.append('| '+str(i)+' | '+cap['name']+' | '+', '.join(p['name'] for p in lineup if p['roster_position']=='FLEX')+' | '+str(round(sum(p['salary'] for p in lineup)))+' | '+str(round(sum(p['projection'] for p in lineup),2))+' | '+', '.join(lineup[0].get('analyst_thesis_ids',[]))+' | '+str(key in baseline_keys)+' |')
    lines+=['','The two SEA role branches anchor JSN and Darnold in opposite Captain/FLEX constructions. Their remaining FLEX players are chosen by the unchanged baseline objective. The original pool already discovered these four rosters, so the test proves ingestion, generation, attribution and unchanged-rule evaluation, not a new performance improvement.',
      'The five-entry portfolio retains its existing joint95% common-baseline mean/P90 screen and Captain/player caps. It achieved4/5 without relaxing those constraints. No fresh market or missing salary chronology was invented to claim READY.',
      'A Darnold-Captain branch can include Broncos DST alongside opposing SEA offensive players when existing avoid_dst_opponents is false. This is a football-coherence concern to review; simple Analyst anchors do not automatically fix every FLEX pairing.',
      'The saved readiness display says DEN @ SEA; verified packet schedule identifies SEA @ DEN. The generator binds the canonical two-team game scope and does not adopt the reversed display as venue evidence.']
    (root/'REPORT.md').write_text('\n'.join(lines)+'\n')
    files=[root/'without_analyst.json',root/'with_analyst.json',root/'comparison.json',Path(__file__),Path('backend/app/product_services/analyst_generation.py'),Path('backend/app/product_services/analyst_packets.py'),Path('backend/app/product_services/analyst_shadow.py'),Path('backend/app/product_services/gpp_optimizer.py'),Path('backend/app/product_services/optimizer.py')]
    (root/'manifest.json').write_text(json.dumps(dict(contract_id='analyst_normal_test_manifest_v1',files={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}),indent=2)+'\n')


if __name__=='__main__':main()
