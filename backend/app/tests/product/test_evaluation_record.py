from copy import deepcopy
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from backend.app.product_services.evaluation_record import snapshot_payload, record_recommendation
from backend.app.product_services.optimizer_effectiveness import (
    candidate_signature, chronological_validation, execution_diagnostics, evaluate_run,
    extract_saved_pool, field_benchmarks,
)
from backend.app.product_services.contest_scope import verify_history_scope
from backend.app.product_services.contest_ownership_identity import frozen_salary_rows, resolve_observations
from backend.app.product_services.showdown_data_readiness import digest
import pandas as pd


def candidate(last='p8', rank=17):
    return {'player_ids': [f'p{i}' for i in range(8)] + [last], 'rank': rank, 'mean': 100,
            'games_represented': ['A@B 10/11/2026 01:00PM ET']}


def run(rows=None):
    return {'optimizer_run_id': 'r', 'contest_format': 'classic',
            'created_at': '2026-10-11T12:00:00+00:00', 'data_cutoff_at': '2026-10-11T11:00:00+00:00',
            'constraint_config_json': {'strategy_runtime': {'single_lineup': {'all_candidates': rows or [candidate()]}}}}


def test_snapshot_distinguishes_candidate_lineup_number_and_selector_rank_without_mutation():
    source = run(); before = deepcopy(source)
    lineups = [{'lineup_id': 'r:3', 'lineup_number': 3,
                'players': [{'player_id': p, 'roster_position': 'FLEX'} for p in candidate()['player_ids']]}]
    result = snapshot_payload(source, lineups, [{'player_id': 'p0', 'point_prediction': 4}])
    row = result['candidate_lineup_mapping'][0]
    assert row['candidate_id'] == 'r:candidate:1'
    assert row['selector_rank'] == 17
    assert row['saved_lineups'] == [{'lineup_id': 'r:3', 'saved_lineup_number': 3}]
    assert source == before
    assert result['timing']['status'] == 'predecision'


def test_sequential_classic_pool_requires_explicit_complete_generation_contract():
    row = candidate(); row.pop('rank')
    config = {'strategy_runtime': {'strategy_contract_audit': {'candidate_rosters': [row]}},
              'effective_strategy_contract': {'effective': {
                  'generation': 'sequential exposure-aware ILP; accepted candidates are the selected portfolio', 'entry_count': 1}}}
    assert extract_saved_pool(config, 'classic')['count'] == 1
    config['effective_strategy_contract']['effective']['entry_count'] = 10
    assert extract_saved_pool(config, 'classic')['reason'] == 'incomplete_sequential_candidate_pool'
    config.pop('effective_strategy_contract')
    assert extract_saved_pool(config, 'classic')['status'] == 'unavailable'


def test_cross_contest_score_difference_is_hindsight_not_execution():
    low, high = candidate('low',1), candidate('high',2)
    source = run([low, high])
    selected = [{'signature': candidate_signature(c,'classic')} for c in [low,high]]
    entered = [{'contest_id':'a','entry_id':'ea','signature': selected[0]['signature'],'entry_points': 90},
               {'contest_id':'b','entry_id':'eb','signature': selected[1]['signature'],'entry_points': 130}]
    field = field_benchmarks({'field_size':2}, [{'entry_points':140},{'entry_points':80}], [])
    result = evaluate_run(source,selected,entered,{**{f'p{i}':10 for i in range(8)},'low':10,'high':50}, {'a':field,'b':field})
    assert result['field']['a']['best_entered_actual'] == 90
    assert result['field']['b']['best_entered_actual'] == 130
    assert not any(r['stage']=='EXECUTION' for r in result['diagnostic'])
    assert [r['contest_id'] for r in result['diagnostic'] if r['stage']=='HINDSIGHT_GAP'] == ['a']


def test_execution_requires_exact_contest_entry_intent_and_identity():
    p = {'player_id':'p','roster_position':'CPT'}
    entries = [{'contest_id':'a','entry_id':'e','identity_complete':True,'players':[p]}]
    assert execution_diagnostics(entries,[],{})[0]['status']=='intended_entry_unavailable'
    assignment = {'contest_id':'b','entry_id':'e','lineup_id':'r:1','optimizer_run_id':'r'}
    saved = {'r:1':[{'player_id':'q','roster_position':'CPT'}]}
    assert execution_diagnostics(entries,[assignment],saved)[0]['status']=='intended_entry_unavailable'
    assignment['contest_id']='a'
    assert execution_diagnostics(entries,[assignment],saved)[0]['stage']=='EXECUTION'
    saved['r:1']=[p]
    assert execution_diagnostics(entries,[assignment],saved)[0]['status']=='matched'
    entries[0]['identity_complete']=False
    assert execution_diagnostics(entries,[assignment],saved)[0]['status']=='identity_or_intended_roster_unavailable'


def test_saved_frozen_games_supply_lock_instead_of_current_schedule():
    source = run(); source['optimizer_created_at']=source['created_at']
    source['constraint_config_json']['showdown_evidence_snapshot']={'player_pool':[{'game_id':'BAL@ATL 10/11/2026 08:20PM ET'}]}
    pool={'status':'slate_source_pool','candidates':[]}
    assert chronological_validation(source,pool)['first_saved_kickoff_at']=='2026-10-11T20:20:00-04:00'
    source['data_cutoff_at']='2026-10-12T01:00:00+00:00'
    assert chronological_validation(source,pool)['status']=='unavailable'


def test_monday_history_cannot_inherit_next_ui_week():
    history=[{'contest_id':'c','sport':'NFL','contest_date_est':'2026-10-05T20:15:00'}]
    schedule=[{'season':2026,'week':4,'game_date':'2026-10-05','game_id':'2026_04_ATL_NO'}]
    result=verify_history_scope(history,schedule,contest_id='c',season=2026,week=5)
    assert result['status']=='conflict' and result['week']==4
    assert verify_history_scope(history,schedule,contest_id='c',season=2026,week=4)['status']=='verified'
    assert verify_history_scope([],schedule,contest_id='c',season=2026,week=5)['status']=='missing'


def test_frozen_native_ids_restore_overwritten_slate_but_tampered_snapshot_does_not():
    frame={'contract_id':'showdown_frozen_evidence_v1','player_pool':[{
        'player_id':'canonical','name':'Player','player_team':'ATL','opponent_team':'BAL','position':'WR',
        'dk_player_id':'11','dk_captain_id':'12','game_id':'BAL@ATL 10/11/2026 08:20PM ET'}],
        'data_readiness':{'status':'READY'}}
    frame['sha256']=digest(frame)
    source={'optimizer_run_id':'r','optimizer_created_at':datetime(2026,10,11,12,tzinfo=UTC),
            'data_cutoff_at':datetime(2026,10,11,11,tzinfo=UTC),'constraint_config_json':{'showdown_evidence_snapshot':frame}}
    salaries=frozen_salary_rows([source])
    observations=pd.DataFrame([{'player_display_name':'Player','roster_position':'CPT'}])
    result=resolve_observations(observations,salaries)
    assert result.iloc[0].player_id=='canonical'
    assert result.iloc[0].identity_evidence['salary_candidates'][0]['source_player_key']=='12'
    frame['player_pool'][0]['player_id']='tampered'
    assert frozen_salary_rows([source]).empty


def test_recommendation_rejects_lineup_number_as_candidate_id():
    connection=MagicMock()
    connection.execute.return_value.scalar_one_or_none.return_value={'candidate_lineup_mapping':[{
        'candidate_id':'r:candidate:1','saved_lineups':[{'lineup_id':'r:3','saved_lineup_number':3}]}]}
    with pytest.raises(ValueError,match='Candidate IDs'):
        record_recommendation(connection,'r',{'actor':'ai','source_reference':'chat','candidate_ids':['r:3']})


def test_recommendation_intent_uses_server_time_and_exact_canonical_roster():
    from backend.app.product_services.evaluation_record import prelock_recommendation_assignments
    record = {'optimizer_run_id':'r', 'recorded_at':datetime(2026,10,11,12,tzinfo=UTC),
        'payload':{'verified_lock_at':'2026-10-11T17:00:00+00:00',
            'recorded_at':'2026-10-10T12:00:00+00:00',
            'candidate_lineup_mapping':[{'candidate_id':'r:candidate:1', 'canonical_roster':[['p',True]]}],
            'assignments':[{'contest_id':'c','entry_id':'e','candidate_id':'r:candidate:1'}]}}
    assignments = prelock_recommendation_assignments([record])
    assert assignments[0]['intended_players'] == [{'player_id':'p','roster_position':'CPT'}]
    actual = [{'contest_id':'c','entry_id':'e','identity_complete':True,
               'players':[{'player_id':'p','roster_position':'CPT'}]}]
    assert execution_diagnostics(actual,assignments,{})[0]['status'] == 'matched'
    record['recorded_at'] = datetime(2026,10,11,18,tzinfo=UTC)
    assert prelock_recommendation_assignments([record]) == []
    record['payload']['verified_lock_at'] = None
    assert prelock_recommendation_assignments([record]) == []


def test_record_recommendation_is_content_idempotent_and_cannot_backdate():
    connection=MagicMock()
    connection.execute.return_value.scalar_one_or_none.return_value={'candidate_lineup_mapping':[{
        'candidate_id':'r:candidate:1','saved_lineups':[]}], 'timing':{}}
    payload={'actor':'ai','source_reference':'chat:turn','candidate_ids':['r:candidate:1']}
    first=record_recommendation(connection,'r',payload)
    second=record_recommendation(connection,'r',{**payload,'recorded_at':'1999-01-01'})
    assert first==second


def test_recovered_lineage_and_ledger_change_the_report_identity():
    from backend.app.tests.product.test_slate_learning import complete_evidence, NOW
    from backend.app.product_services.slate_learning import build_slate_learning_report
    evidence=complete_evidence()
    def report():
        return build_slate_learning_report(season=2026,week=1,slate='SUNDAY_NIGHT',
            entry_user='wones0120',evidence=evidence,generated_at=NOW)
    original=report()['report_id']
    evidence['evaluation_records']=[{'record_id':'evaluation-new','kind':'run_snapshot'}]
    assert report()['report_id'] != original
    second=report()['report_id']
    evidence['entry_candidate_lineage']=[{'contest_id':'contest-1','entry_id':'entry-1',
        'matches':[{'optimizer_run_id':'optimizer-1','candidate_id':'optimizer-1:candidate:1'}]}]
    assert report()['report_id'] != second


def test_saved_lineup_game_preserves_kickoff_without_inventing_prelock_decision_time():
    source=run(); source['optimizer_created_at']='2026-10-05T21:32:00-04:00'
    source['saved_lineup_games']=['ATL@NO 10/05/2026 08:15PM ET']
    result=chronological_validation(source,{'status':'original_candidate_pool','candidates':[]})
    assert result['first_saved_kickoff_at']=='2026-10-05T20:15:00-04:00'
    assert result['status']=='unavailable'
