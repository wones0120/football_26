"""Save reproducible SYNTHETIC Sunday Main and Captain strategy examples.

No live data, database writes, exports or submissions. Illustrates sensitivity
parameters; it does not assert NFL hypotheses, readiness or historical performance.
"""
from contextlib import redirect_stdout
from datetime import datetime, timezone
import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from backend.app.product_services.analyst_packets import packet_digest
from backend.app.product_services.analyst_scenarios import run_merged
from backend.app.product_services.optimizer import OptimizerService, _json_safe
from scripts.build_analyst_shadow_fixtures import fixture


def scenario_fixture(fmt):
    from copy import deepcopy
    packet,snapshot=fixture(fmt)
    for gid in [g['game_id'] for g in packet['games']][1:]:
        h=deepcopy(packet['hypotheses'][0]);h.update(hypothesis_id=gid,game_id=gid,player_master_ids=[p['player_id'] for p in packet['players'] if p['game_id']==gid][:1]);packet['hypotheses'].append(h)
    assumptions=[]
    for game in packet['games']:
        assumptions.append(dict(kind='passing_volume',game_id=game['game_id'],team=game['teams'][0],factor=1.5,elasticity=1))
        assumptions.append(dict(kind='rushing_volume',game_id=game['game_id'],team=game['teams'][1],factor=.5,elasticity=1))
    packet['scenario_assumptions']=dict(contract_id='analyst_scenarios_v1',scenarios=[dict(scenario_id='passing',label='SYNTHETIC joint passing sensitivity',hypothesis_ids=[h['hypothesis_id'] for h in packet['hypotheses']],assumptions=assumptions)])
    second=deepcopy(packet['scenario_assumptions']['scenarios'][0]);second.update(scenario_id='run_control',label='SYNTHETIC joint run control sensitivity')
    for a in second['assumptions']: a['factor']=.5 if a['kind']=='passing_volume' else 1.5
    packet['scenario_assumptions']['scenarios'].append(second)
    return packet,snapshot


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    summary=[]
    for fmt in ('CLASSIC','SHOWDOWN'):
        packet,snapshot=scenario_fixture(fmt);service=OptimizerService.__new__(OptimizerService)
        kwargs=dict(contest_type='captain' if fmt=='SHOWDOWN' else 'classic',score_col='p90',stack_params={'enabled':False},
                    locked_player_ids=set(snapshot['policy']['locked_ids']),exposure_remaining={snapshot['policy']['zero_remaining_exposure_ids'][0]:0},include_control_comparison=False)
        params=dict(analyst_strategy='MERGED_SCENARIOS',analyst_packet_sha256=packet_digest(packet),analyst_candidates_per_thesis=4,max_exposure=1,minimum_uniqueness=1)
        with (args.output/(fmt.lower()+'.log')).open('w') as log,redirect_stdout(log),patch('backend.app.product_services.analyst_scenarios.datetime') as clock:
            clock.now.return_value=datetime(2099,9,1,12,tzinfo=timezone.utc)
            lineups,report=run_merged(service,pd.DataFrame(snapshot['players']),params=params,packet=packet,fmt=fmt,
                season=2099,week=1,slate='SYNTHETIC_SUNDAY_MAIN' if fmt=='CLASSIC' else 'SYNTHETIC_CAPTAIN',requested=2,solve_kwargs=kwargs)
        report.update(evidence_status='SYNTHETIC_RESEARCH_FIXTURE_NOT_LIVE_READY',lineups=_json_safe(lineups),request=params)
        (args.output/(fmt.lower()+'_packet.json')).write_text(json.dumps(packet,indent=2,allow_nan=False)+'\n')
        (args.output/(fmt.lower()+'_report.json')).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
        selected={tuple(sorted((p['player_id'],'CPT' if p.get('roster_position')=='CPT' else 'FLEX' if fmt=='SHOWDOWN' else 'SELECTED') for p in l)) for l in lineups}
        summary.append(f"{fmt}: {len(lineups)}/2 selected, {report['generated_candidate_count']} distinct candidates, {len(report['scenario_definitions'])} scenarios; baseline comparison roster {'retained' if tuple(map(tuple,report['baseline_comparison_roster'])) in selected else 'replaced'}.")
    (args.output/'README.md').write_text('# Synthetic merged Analyst scenario examples\n\nThese are explicit research fixtures, not NFL recommendations, calibrated probabilities or live-ready slates. Classic uses three games to exercise Sunday Main joint scenarios; Showdown exercises Captain roles. Source projections and the base legal-model snapshot are saved alongside conditional assumptions and selected rosters. No outcomes were evaluated.\n\n'+'\n\n'.join(summary)+'\n\nSelection uses no 95% mean/P90 gate. Hard legality, locks, zero remaining exposure and uniqueness remain enforced.\n')
    print('\n'.join(summary))


if __name__=='__main__':main()
