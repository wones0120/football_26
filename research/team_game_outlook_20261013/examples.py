"""Saved real Sunday/Captain previews; no live writes or readiness claims."""
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime,timezone
import json
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from backend.app.product_services.team_game_outlook import bind_outlook,conditional_factors,digest
from backend.app.product_services.analyst_packets import validate,packet_digest
from backend.app.product_services.optimizer import _json_safe
from scripts.run_analyst_normal_offline import OfflineNormal
from scripts.run_captain_analyst_fixture import real_packet
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]


def enrich(packet,block,fmt):
    packet=deepcopy(packet);now=datetime.now(timezone.utc).isoformat();packet.update(packet_id=packet['packet_id']+'_team_outlook_v1',decision_at=now,frozen_at=now)
    packet['team_game_outlook']=bind_outlook(block,packet['games'])
    source='fitted_team_game_outlook_v1';packet['sources'].append(dict(source_id=source,uri=str(HERE/'outlook_2026w6.json'),coverage='verified',observed_at=block['generated_at'],available_at=block['generated_at'],capture_sha256=block['sha256'],note='Saved fitted estimate; empirical probabilities unproven forward calibration; revised historical data'))
    for game in packet['games']:
        members=[p['player_master_id'] for p in packet['players'] if p['game_id']==game['game_id']]
        if not members:continue
        gid=game['game_id'];hid='team_outlook_'+gid
        packet['hypotheses'].append(dict(hypothesis_id=hid,status='research_only',game_id=gid,formats=[fmt],player_master_ids=members,source_ids=[source],hypothesis='Fitted game context and conditional opportunity budgets are an alternative to central estimates.',supporting_evidence=['Strictly earlier completed-game history; paired residual estimates saved with validation metrics.'],contrary_evidence=['Sunday team scoring MAE slightly worse than simple scoring history; probability reliability not established.'],conditional_assumptions=['Budget-ratio elasticity is a sensitivity, not a fitted player fantasy response.'],unknowns=['Current injury/QB/role uncertainty unmodeled; source revisions lack contemporaneous history.'],testable_implication='Compare frozen future team totals and plays against completed games, then inspect player response separately.',uncertainty='Empirical model estimate, no calibrated lineup probability.',recheck_triggers=['new completed game','injury or QB change','source update'],expires_at=game['kickoff_at'],action='none',numeric_effect_proposal=None))
    if fmt=='CLASSIC':
        scenarios=[]
        for game in packet['games']:
            assumptions=[];notes=[]
            for team in game['teams']:
                factors=conditional_factors(packet,game['game_id'],team,'competitive_scoring')
                if not factors:factors=(1,1);notes.append(team+': conditional branch unavailable/beyond contract; central budgets retained')
                assumptions.extend(dict(kind=kind,game_id=game['game_id'],team=team,factor=factor,elasticity=.6) for kind,factor in zip(['passing_volume','rushing_volume'],factors))
            scenarios.append(dict(scenario_id='outlook_competitive_'+game['game_id'],label='Model competitive scoring budget sensitivity '+game['game_id'],team_game_branch='competitive_scoring',hypothesis_ids=['team_outlook_'+game['game_id']],assumptions=assumptions))
        packet['scenario_assumptions']['scenarios']=scenarios
    else:
        # Existing unknown Captain mechanism/capability remains unknown; all branches
        # retained. Fitted joint budgets can replace fixed numeric volume designs.
        packet.setdefault('captain_analysis',dict(contract_id='captain_analysis_v1',opponents=[],captains=[]))
    packet.setdefault('coverage_gaps',[]).extend(['Fitted outlook does not clear injury uncertainty or final entry readiness','Player elasticity and portfolio weights remain uncalibrated sensitivities'])
    errors=validate(packet)
    if errors:raise ValueError('; '.join(errors))
    return packet


def main():
    block=json.loads((HERE/'outlook_2026w6.json').read_text())
    receipt=json.loads((ROOT/'research/sunday_main_merged_comparison_20261013/preliminary_snapshot_receipt.json').read_text());snapshot=json.loads((ROOT/'artifacts/preliminary_optimizer_snapshots'/(receipt['snapshot_sha256']+'.json')).read_text())
    classic_source={'season':2026,'week':6,'slate':'SUNDAY_MAIN','projection_run_id':snapshot['projection_run_id'],'projection_header':[{'data_cutoff_at':snapshot['data_cutoff_at']}],'player_pool':snapshot['pool'],'pool_attrs':snapshot['pool_attrs']}
    captain_source=ROOT/'research/analyst_shadow_lineups_20261013/real_capture_v4/source.json'
    cp,cf=real_packet(captain_source)
    packets={'CLASSIC':enrich(json.loads((ROOT/'research/sunday_main_analyst_20261013/v3/packet.json').read_text()),block,'CLASSIC'),'SHOWDOWN':enrich(cp,block,'SHOWDOWN')}
    summary={}
    for fmt,frozen,strategy in [('CLASSIC',classic_source,'classic_large_gpp_v1'),('SHOWDOWN',cf,'showdown_single_entry_gpp')]:
        packet=packets[fmt];service=OfflineNormal(frozen)
        params=dict(num_lineups=2,max_exposure=1,analyst_strategy='MERGED_SCENARIOS',analyst_packet_sha256=packet_digest(packet),analyst_candidates_per_thesis=1,refresh_ownership=False)
        if fmt=='CLASSIC':params['exclude_player_ids']=snapshot['assumption_manifest']['exclude_player_ids'];params['ownership_run_id']=snapshot['ownership_run_id']
        with (HERE/(fmt.lower()+'_preview.log')).open('w') as log,redirect_stdout(log),patch('backend.app.product_services.analyst_packets.load_packet',return_value=packet):
            job=service.run_job(frozen['season'],frozen['week'],frozen['slate'],strategy,params,contest_format=fmt.lower(),objective='gpp',projection_run_id=frozen['projection_run_id'],allow_incomplete_evidence=True)
        result=_json_safe(dict(status=job.status,message=job.message,lineups=job.results,params=job.params,packet_sha256=packet_digest(packet),live_persistence=False,entry_ready=False,evidence_status='OFFLINE_PRELIMINARY_CURRENT_TEAM_OUTLOOK_WITH_FROZEN_PLAYER_INPUTS',baseline_source_sha256=snapshot['sha256'] if fmt=='CLASSIC' else digest(frozen),source_caveat='Sunday pool uses saved preliminary injury exclusions; Captain pool is dated frozen evidence. Neither certifies final preparation.'))
        (HERE/(fmt.lower()+'_packet.json')).write_text(json.dumps(packet,indent=2,allow_nan=False)+'\n');(HERE/(fmt.lower()+'_preview.json')).write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
        summary[fmt]={'status':job.status,'lineups':len(job.results or []),'packet_sha256':packet_digest(packet),'message':job.message}
    (HERE/'example_summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))
if __name__=='__main__':main()
