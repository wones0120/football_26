from copy import deepcopy
from uuid import UUID
import pytest
from backend.app.product_services import frozen_salary_opportunity_cost as f


def signed(row):
    row.pop('sha256', None)
    row['sha256'] = f.digest(row)
    return row


def fixture():
    ids = [str(UUID(int=i)) for i in range(1, 8)]
    players = [dict(player_master_id=p, game_id='g', salary=1000+i*100, projection=10+i, position='K' if i == 6 else 'WR') for i, p in enumerate(ids)]
    mapping = {f'{i}_{r}': dict(player_master_id=p, role=r) for i, p in enumerate(ids) for r in ('CPT', 'FLEX')}
    variables = [dict(name=n, cat='Integer', lowBound=0, upBound=1) for n in mapping]
    coeff = [dict(name=n, value=players[ids.index(v['player_master_id'])]['projection']*(1.5 if v['role']=='CPT' else 1)) for n, v in mapping.items()]
    snapshot = signed(dict(contract_id='analyst_shadow_model_v1', scope=dict(format='SHOWDOWN', game_ids=['g']), available_at='2026-01-01T00:00:00+00:00', decision_at='2026-01-02T00:00:00+00:00', players=players, variable_players=mapping, model=dict(parameters=dict(sense=-1), variables=variables, objective=dict(coefficients=coeff), constraints=[dict(name='roster_size', sense=0, constant=-6, coefficients=[dict(name=n, value=1) for n in mapping])], sos1=[], sos2=[]), policy=dict(complete_prepared_model=True), provenance=dict(original_availability='unknown'), quality_screens=[]))
    branches=[]
    for included in (False, True):
        roster=[dict(player_master_id=p, role='CPT' if i==0 else 'FLEX') for i,p in enumerate(ids[:5]+[ids[6] if included else ids[5]] )]
        salary=sum(players[ids.index(x['player_master_id'])]['salary']*(1.5 if x['role']=='CPT' else 1) for x in roster)
        mean=sum(players[ids.index(x['player_master_id'])]['projection']*(1.5 if x['role']=='CPT' else 1) for x in roster)
        branches.append(dict(included=included, solver_status='Optimal', achieved_lineup_count=1, roster=roster, salary=salary, baseline_mean=mean, objective_value=mean))
    comparison=signed(dict(contract_id='defense_kicker_paired_flex_v1', snapshot_sha256=snapshot['sha256'], captain_id=ids[0], specialist_id=ids[6], seed=7, requested_lineup_count=2, achieved_lineup_count=2, branches=branches, relaxations=[], baseline_mutation=False, selection_action='comparison_only', scoring_status='frozen', opportunity_cost=dict(displaced_player_ids=[ids[5]], added_player_ids=[ids[6]], salary_delta=100, baseline_mean_delta=1)))
    return snapshot, comparison


def rebind(s,c):
    signed(s)
    c['snapshot_sha256']=s['sha256']
    signed(c)


def test_full_alternatives_arithmetic_and_role_salary():
    s,c=fixture()
    result=f.validate_comparison(s,c)
    assert result['opportunity_cost']['baseline_mean_delta']==1
    assert result['branches'][0]['salary']==8000
    assert result['branches'][0]['independently_proved_optimality'] is False
    assert result['new_solver_execution'] is False


@pytest.mark.parametrize('field', ['salary', 'baseline_mean', 'objective_value'])
def test_reported_arithmetic_tamper(field):
    s,c=fixture(); c['branches'][0][field]+=1; signed(c)
    with pytest.raises(ValueError, match='mismatch'): f.validate_comparison(s,c)


def test_semantic_hash_tamper():
    s,c=fixture(); c['seed']=8
    with pytest.raises(ValueError, match='hash'): f.validate_comparison(s,c)


def test_violated_original_constraint():
    s,c=fixture(); s['model']['constraints'][0]['constant']=-5; rebind(s,c)
    with pytest.raises(ValueError, match='constraint violation'): f.validate_comparison(s,c)


@pytest.mark.parametrize('sense,constant', [(-1,-5),(1,-7)])
def test_inequality_constraints(sense,constant):
    s,c=fixture(); s['model']['constraints'][0].update(sense=sense,constant=constant); rebind(s,c)
    with pytest.raises(ValueError, match='constraint violation'): f.validate_comparison(s,c)


def test_duplicate_physical_actor_across_roles():
    s,c=fixture(); c['branches'][0]['roster'][1]['player_master_id']=c['captain_id']; signed(c)
    with pytest.raises(ValueError, match='distinct'): f.validate_comparison(s,c)


def test_changed_captain():
    s,c=fixture(); c['branches'][1]['roster'][0]['role']='FLEX'; c['branches'][1]['roster'][1]['role']='CPT'; signed(c)
    with pytest.raises(ValueError, match='Captain'): f.validate_comparison(s,c)


def test_treatment_not_just_roster_label():
    s,c=fixture(); c['branches'][0]['included']=True; signed(c)
    with pytest.raises(ValueError, match='order'): f.validate_comparison(s,c)


def test_extra_unmapped_objective_variable():
    s,c=fixture(); s['model']['objective']['coefficients'].append(dict(name='extra',value=1)); rebind(s,c)
    with pytest.raises(ValueError, match='coefficient'): f.validate_comparison(s,c)


def test_duplicate_canonical_mapping():
    s,c=fixture(); keys=list(s['variable_players']); s['variable_players'][keys[1]]=deepcopy(s['variable_players'][keys[0]]); rebind(s,c)
    with pytest.raises(ValueError, match='mapping'): f.validate_comparison(s,c)


def test_frozen_settings_and_chronology():
    s,c=fixture(); s['available_at']='2026-01-03T00:00:00+00:00'; rebind(s,c)
    with pytest.raises(ValueError, match='chronology'): f.validate_comparison(s,c)


def test_unknown_extra_quality_constraint_not_skipped():
    s,c=fixture(); s['quality_screens']=[dict(unknown=True)]; rebind(s,c)
    with pytest.raises(ValueError, match='quality'): f.validate_comparison(s,c)


def test_displacement_requires_canonical_exact_set():
    s,c=fixture(); c['opportunity_cost']['displaced_player_ids']=[]; signed(c)
    with pytest.raises(ValueError, match='displacement'): f.validate_comparison(s,c)


def test_recorded_optimality_not_silently_assumed():
    s,c=fixture(); c['branches'][0]['solver_status']='Not Solved'; signed(c)
    with pytest.raises(ValueError, match='Optimal'): f.validate_comparison(s,c)


def test_no_relaxation_or_model_mutation():
    s,c=fixture(); c['relaxations']=['salary']; signed(c)
    with pytest.raises(ValueError, match='relaxed'): f.validate_comparison(s,c)
