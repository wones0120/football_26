"""Save Captain-conditioned synthetic examples and optional dated real-input preview.

No database persistence, exports, contest submissions, or observed outcomes. The
real-input arm reconstructs a new packet from an existing frozen source; its
opponent capability remains unknown. It is not a fresh football research review.
"""
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from backend.app.product_services.analyst_packets import packet_digest, validate
from backend.app.product_services.analyst_scenarios import run_merged
from backend.app.product_services.captain_analyst import STATES, DIMENSIONS
from backend.app.product_services.optimizer import OptimizerService, _json_safe
from scripts.run_analyst_normal_offline import OfflineNormal
from scripts.run_merged_analyst_fixture import scenario_fixture


def synthetic_packet(capability):
    packet,snapshot=scenario_fixture('SHOWDOWN')
    qb=next(p for p in packet['players'] if p['team']=='BBB' and p['position']=='QB')
    packet['captain_analysis']=dict(contract_id='captain_analysis_v1',captains=[],opponents=[dict(
        game_id='SYNTH_A_B',team='BBB',capability=capability,
        alternative_capabilities=['trailing_productive_passing'] if capability!='trailing_productive_passing' else ['drive_stall_runout'],
        evidence={d:dict(status='reviewed',summary='SYNTHETIC '+d+' evidence, not an NFL claim',source_ids=['synthetic'],player_master_ids=[qb['player_master_id']]) for d in DIMENSIONS},
        supporting_evidence=['SYNTHETIC capability premise'],contrary_evidence=['Opposing synthetic branch retained'],unknowns=['No real research or calibrated magnitude'],hypothesis_ids=['synthetic_context'],expires_at='2099-09-02T12:00:00Z')])
    return packet,snapshot


def real_packet(source_path):
    frozen=json.loads(source_path.read_text());now=datetime.now(timezone.utc).isoformat()
    teams=sorted({p['player_team'] for p in frozen['player_pool']})
    gid=f"{frozen['season']}_W{frozen['week']:02d}_SEA_DEN"
    packet=json.loads(Path('research/pregame_ai_packet_20261013/packet.json').read_text())
    game=next(g for g in packet['games'] if g['game_id']==gid)
    packet.update(packet_id='captain_unknown_reconstructed_'+now,decision_at=now,frozen_at=now,
        games=[game],players=[],analyst_assessments=[],baseline_facts=[],hypotheses=[h for h in packet['hypotheses'] if h['game_id']==gid],
        coverage_gaps=['Dated frozen inputs, not current live preparation','Opponent capability and Captain-specific high-end likelihood unknown','Later reconstruction, not original pregame packet'])
    packet.pop('slate_synthesis',None)
    packet['sources'].append(dict(source_id='dated_frozen_pool',uri=str(source_path.resolve()),coverage='verified',observed_at=now,available_at=now,capture_sha256=sha256(source_path.read_bytes()).hexdigest(),note='File observed now; underlying source clocks remain in original rows. Not a fresh football source.'))
    for row in frozen['player_pool']:
        pid=str(row['player_id'])
        packet['players'].append(dict(player_master_id=pid,position=row['position'],team=row['player_team'],game_id=gid,
            source_native_key=str(row.get('dk_player_id') or row.get('salary_source_row_id') or pid),identity_source_ids=['dated_frozen_pool'],
            workload_evidence=dict(contract_id='workload_evidence_v1',player_id=pid,historical={},derived_proxies={},explicit_pregame={},lineage={'status':'unavailable_in_reconstructed_packet'})))
    packet['scenario_assumptions']=dict(contract_id='analyst_scenarios_v1',scenarios=[dict(scenario_id='dated_game_sensitivity',label='Dated SEA-DEN inputs; opponent unknown',hypothesis_ids=[h['hypothesis_id'] for h in packet['hypotheses']],assumptions=[dict(kind='passing_volume',game_id=gid,team=teams[0],factor=1,elasticity=.6)])])
    packet['captain_analysis']=dict(contract_id='captain_analysis_v1',opponents=[],captains=[])
    errors=validate(packet)
    if errors:raise ValueError('; '.join(errors))
    return packet,frozen


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--real-source',type=Path)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    sections=[]
    for state in STATES:
        packet,snapshot=synthetic_packet(state)
        captain=next(p['player_id'] for p in snapshot['players'] if p['team']=='AAA' and p['position']=='WR')
        kwargs=dict(contest_type='captain',score_col='p90',stack_params={'enabled':False},locked_captain_player_id=captain,locked_player_ids=set(snapshot['policy']['locked_ids']),exposure_remaining={snapshot['policy']['zero_remaining_exposure_ids'][0]:0},include_control_comparison=False)
        with (args.output/(state+'.log')).open('w') as log,redirect_stdout(log),patch('backend.app.product_services.analyst_scenarios.datetime') as clock:
            clock.now.return_value=datetime(2099,9,1,12,tzinfo=timezone.utc)
            lineups,report=run_merged(OptimizerService.__new__(OptimizerService),pd.DataFrame(snapshot['players']),params=dict(max_exposure=1,analyst_candidates_per_thesis=2),packet=packet,fmt='SHOWDOWN',season=2099,week=1,slate='SYNTHETIC_CAPTAIN',requested=2,solve_kwargs=kwargs)
        report.update(lineups=lineups,evidence_status='SYNTHETIC_FIXTURE_NOT_NFL_RESEARCH',live_persistence=False)
        (args.output/(state+'_packet.json')).write_text(json.dumps(packet,indent=2,allow_nan=False)+'\n')
        (args.output/(state+'_report.json')).write_text(json.dumps(_json_safe(report),indent=2,allow_nan=False)+'\n')
        sections.append('## SYNTHETIC '+state+'\n\n'+lineup_table(lineups)+'\n\n'+f"{report['generated_candidate_count']} distinct Captain/FLEX candidates; {len(report['scenario_definitions'])} alternative scenarios. No probability claim.")
    if args.real_source:
        packet,frozen=real_packet(args.real_source)
        service=OfflineNormal(frozen)
        with (args.output/'real_frozen_preview.log').open('w') as log,redirect_stdout(log),patch('backend.app.product_services.analyst_packets.load_packet',return_value=packet):
            job=service.run_job(frozen['season'],frozen['week'],frozen['slate'],'showdown_single_entry_gpp',dict(num_lineups=2,max_exposure=1,analyst_strategy='MERGED_SCENARIOS',analyst_packet_sha256=packet_digest(packet),analyst_candidates_per_thesis=1),contest_format='showdown',objective='gpp',projection_run_id=frozen['projection_run_id'],allow_incomplete_evidence=True)
        output=_json_safe(dict(status=job.status,message=job.message,params=job.params,lineups=job.results,
            source_path=str(args.real_source),source_sha256=sha256(args.real_source.read_bytes()).hexdigest(),evidence_status='DATED_REAL_INPUT_RECONSTRUCTION_OPPONENT_UNKNOWN_NOT_LIVE_READY',live_persistence=False))
        (args.output/'real_frozen_preview_packet.json').write_text(json.dumps(packet,indent=2,allow_nan=False)+'\n')
        (args.output/'real_frozen_preview.json').write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
        sections.append('## Dated SEA-DEN frozen-input preview\n\n'+f"Status: {job.status}. Projection `{frozen['projection_run_id']}`. Later reconstructed packet; opponent capability unknown for every Captain. This does not certify current live preparation or entry readiness.\n\n"+lineup_table(job.results or []))
    (args.output/'README.md').write_text('# Captain-specific Analyst examples\n\nAll numeric changes are declared sensitivity hypotheses. Original projections remain visible. The three capability demonstrations are fictitious fixtures. Dated real inputs, if provided, retain unknown football judgments and are a separately identified later reconstruction. No outcomes, exports, submissions or live optimizer writes.\n\n'+'\n\n'.join(sections)+'\n')
    print(str(args.output/'README.md'))


def lineup_table(lineups):
    lines=['| Captain | Supporting FLEX | Salary | Base mean |','| --- | --- | ---: | ---: |']
    for lineup in lineups:
        captain=next(p for p in lineup if p['roster_position']=='CPT')
        lines.append('| '+str(captain['name'])+' | '+', '.join(str(p['name']) for p in lineup if p['roster_position']=='FLEX')+f" | ${sum(p['salary'] for p in lineup):,.0f} | {sum(p['projection'] for p in lineup):.2f} |")
    return '\n'.join(lines)


if __name__=='__main__':main()
