"""Explicitly synthetic fixtures, captured through the existing production solver."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import pandas as pd
import pulp

from backend.app.product_services.analyst_shadow import freeze_model
from backend.app.product_services.optimizer import OptimizerService


class Capture(pulp.LpSolver):
    def actualSolve(self, problem, **kwargs):
        self.model = problem
        return pulp.LpStatusNotSolved


def fixture(fmt):
    players = []
    # Every name, team, amount and forecast below is synthetic, not NFL research.
    for team, opp, game in [('AAA','BBB','SYNTH_A_B'), ('BBB','AAA','SYNTH_A_B'), ('CCC','DDD','SYNTH_C_D'), ('DDD','CCC','SYNTH_C_D'), ('EEE','FFF','SYNTH_E_F'), ('FFF','EEE','SYNTH_E_F')]:
        if fmt == 'SHOWDOWN' and game != 'SYNTH_A_B': continue
        for pos in ['QB','RB','RB','WR','WR','WR','TE','DST']:
            i = len(players)
            players.append(dict(player_id=str(UUID(int=i+1)), player_master_id=str(UUID(int=i+1)),
                                name='Synthetic '+str(i), position=pos, player_team=team, team=team, opponent_team=opp,
                                game_id=game, salary=4000+i*50, projection=10+i*.17, p90=15+i*.19,
                                pregame_availability_probability=1, showdown_captain_shortlisted=pos in {'QB','WR'},
                                showdown_captain_p90=15+i*.19, showdown_flex_mean=10+i*.17))
    frame = pd.DataFrame(players)
    capture = Capture()
    kwargs = dict(contest_type='captain' if fmt == 'SHOWDOWN' else 'classic', score_col='p90',
                  stack_params={'enabled': False}, include_control_comparison=False,
                  locked_player_ids={players[-3]['player_id']},
                  exposure_remaining={players[2]['player_id']:0})
    with patch('backend.app.product_services.optimizer.pulp.PULP_CBC_CMD', return_value=capture), redirect_stdout(StringIO()):
        OptimizerService._solve_lineup(OptimizerService.__new__(OptimizerService), frame, **kwargs)
    mapping = {}
    for i,p in enumerate(players):
        for prefix,role in ([('captain','CPT'),('flex','FLEX')] if fmt == 'SHOWDOWN' else [('player','SELECTED')]):
            mapping[prefix+'_'+str(i)] = dict(player_master_id=p['player_id'], role=role)
    snapshot = freeze_model(capture.model, variable_players=mapping, players=players,
        scope=dict(format=fmt, season=2099, week=1, slate_id='SYNTHETIC_'+fmt, game_ids=sorted({p['game_id'] for p in players})),
        available_at='2099-09-01T10:00:00Z', decision_at='2099-09-01T12:00:00Z',
        policy=dict(complete_prepared_model=True, synthetic=True, locked_ids=[players[-3]['player_id']],
                    zero_remaining_exposure_ids=[players[2]['player_id']], exposure_policy='frozen per-lineup remaining gates; candidate pool is not a portfolio'),
        provenance=dict(generator='existing OptimizerService._solve_lineup', evidence='SYNTHETIC'))
    games = [dict(game_id=gid, teams=sorted({p['team'] for p in players if p['game_id']==gid}), kickoff_at='2099-09-02T12:00:00Z', format_membership={fmt:'confirmed_in_scope'}) for gid in snapshot['scope']['game_ids']]
    packet = dict(contract_id='wones_football_analyst_v1', analyst_name='Wones Football Analyst', packet_id='synthetic_'+fmt,
                  decision_at=snapshot['decision_at'], frozen_at=snapshot['decision_at'], baseline_mutation=False, user_preferences=[],
                  baseline_input_sha256=snapshot['sha256'], games=games, players=players,
                  baseline_facts=[], coverage_gaps=['SYNTHETIC_ONLY'],
                  hypotheses=[dict(hypothesis_id='synthetic_context',status='research_only',game_id=games[0]['game_id'],formats=[fmt],player_master_ids=[players[0]['player_id']],source_ids=['synthetic'],
                    hypothesis='Synthetic research premise',supporting_evidence=['Synthetic fixture only'],contrary_evidence=['No NFL facts'],conditional_assumptions=['Synthetic'],unknowns=['No real outcome'],testable_implication='Synthetic construction test',uncertainty='unquantified',recheck_triggers=['fixture changes'],expires_at='2099-09-02T12:00:00Z',action='none',numeric_effect_proposal=None)],
                  sources=[dict(source_id='synthetic', uri='synthetic:fixture', coverage='verified', observed_at=snapshot['available_at'], available_at=snapshot['available_at'], capture_sha256='0'*64)],
                  analyst_assessments=[])
    for player in packet['players']:
        player.update(source_native_key='SYNTHETIC:'+player['player_id'], identity_source_ids=['synthetic'],
            workload_evidence=dict(contract_id='workload_evidence_v1',player_id=player['player_id'],historical={},derived_proxies={},explicit_pregame={}))
    def thesis(aid, kind, roles, thought):
        ids = [p for values in roles.values() for p in values]
        packet['analyst_assessments'].append(dict(assessment_id=aid, kind='subjective_analyst_judgment', status='research_only', production_action='none',
            game_id=players[0]['game_id'], formats=[fmt], player_master_ids=ids, source_ids=['synthetic'], lean=thought,
            expires_at='2099-09-02T12:00:00Z', confidence_label='unquantified',
            supporting_reasoning=['Synthetic opinion'],contrary_evidence=['Synthetic only'],conditions=['Synthetic branch'],
            strongest_alternative='Other synthetic construction',what_changes_view=['Fixture changes'], construction_implications=[dict(type=kind, format=fmt, roles=roles, action='shadow_comparison_only')]))
    ids = [p['player_id'] for p in players]
    thesis('breakout', 'player_emphasis', {'PLAYER':[ids[3]]}, 'Synthetic WR breakout opinion → include this receiver')
    thesis('rebound', 'qb_receiver_bringback', {'QB':[ids[0]],'RECEIVER':[ids[3]],'BRINGBACK':[ids[11]]}, 'Synthetic passing rebound → QB, receiver and opposing bringback')
    thesis('rushing', 'rb_dst_scenario', {'RB':[ids[1]],'DST':[ids[7]]}, 'Synthetic rushing/defense branch → same-team RB and DST')
    if fmt == 'SHOWDOWN': thesis('captain', 'explicit_roles', {'CPT':[ids[3]],'FLEX':[ids[0]]}, 'Synthetic breakout receiver Captain with his QB')
    else: thesis('avoid', 'diversify_away_from_game', {'AVOID':[ids[0]]}, 'Synthetic game disappointment → generate entirely elsewhere')
    return packet, snapshot


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    for fmt in ('CLASSIC','SHOWDOWN'):
        packet,snapshot = fixture(fmt)
        for name,value in [('packet',packet),('snapshot',snapshot)]:
            (args.output/(fmt.lower()+'_'+name+'.json')).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


if __name__ == '__main__': main()
