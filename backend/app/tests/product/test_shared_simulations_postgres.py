"""Opt-in SQL integration against an EMPTY disposable PostgreSQL database.

Set SHARED_SLATE_TEST_DATABASE_URL to a dedicated test database, never app data.
No tables are removed; the fixture refuses an existing target schema.
"""
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from backend.app.product_services.simulations import SimulationService, simulate_showdown_lineups, simulate_optimal_lineups
from backend.app.product_services.target_schema import actual_target_schema_contract
from backend.app.tests.product.test_simulations import classic_pool
from backend.app.tests.product.test_showdown_simulations import showdown_pool

SCOPES = [('SUNDAY_MAIN', 'classic'), ('SUNDAY_EARLY', 'classic'), ('SUNDAY_LATE', 'classic'),
          ('THURSDAY_NIGHT', 'showdown'), ('SUNDAY_NIGHT', 'showdown'), ('MONDAY_NIGHT', 'showdown'),
          ('DK_SECOND_SUNDAY_GAME', 'showdown')]


@pytest.fixture(scope='module')
def engine():
    url = os.environ.get('SHARED_SLATE_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Requires an explicitly configured empty disposable PostgreSQL database')
    engine = create_engine(url)
    assert not inspect(engine).has_schema('target'), 'Refusing an existing target schema; use an empty test database'
    root = Path(__file__).resolve().parents[4]
    with engine.begin() as connection:
        for name in ['0011_target_product_schema.sql', '0012_target_ownership_and_digital_twin.sql']:
            connection.exec_driver_sql((root / 'migrations' / name).read_text())
        connection.execute(text('CREATE TABLE public.target_schema_contract (object_type text, table_name text, object_name text, definition text)'))
    contract = actual_target_schema_contract(engine)
    with engine.begin() as connection:
        connection.execute(text('INSERT INTO public.target_schema_contract VALUES (:kind,:table,:name,:definition)'),
                           [dict(kind=k[0], table=k[1], name=k[2], definition=v) for k, v in contract.items()])
        connection.execute(text("INSERT INTO target.model_registry (model_id, model_name, model_version) VALUES ('fixture','fixture','fixture')"))
        connection.execute(text("INSERT INTO target.model_run (model_run_id, model_id) VALUES ('fixture','fixture')"))
        for slate, format in SCOPES:
            pool = showdown_pool() if format == 'showdown' else classic_pool()
            for i, player in pool.iterrows():
                uid = f'{slate}-{i}'
                game = f'{slate}-game'
                connection.execute(text('INSERT INTO target.dim_player (player_id,full_name,primary_position) VALUES (:id,:name,:pos)'),
                                   dict(id=uid, name=uid, pos=player.position))
                roles = [('FLEX', int(player.salary)), ('CPT', int(player.captain_salary))] if format == 'showdown' else [(player.position, int(player.salary))]
                for role, salary in roles:
                    connection.execute(text('''INSERT INTO target.snapshot_salary
                        (season,week,slate,player_id,site,site_player_id,salary,roster_position,team_id,opponent_team_id,game_id,as_of)
                        VALUES (2026,5,:slate,:id,'draftkings',:native,:salary,:role,:team,:opp,:game,'2026-10-01T00:00:00Z')'''),
                        dict(slate=slate, id=uid, native=f'{uid}-{role}', salary=salary, role=role,
                             team=player.get('team_id', 'A'), opp=player.get('opponent_team_id', 'B'), game=game))
                connection.execute(text('''INSERT INTO target.player_projection
                    (projection_run_id,model_run_id,season,week,game_id,slate_id,player_id,mean,median,p10,p25,p75,p90,data_cutoff_at)
                    VALUES (:run,'fixture',2026,5,:game,:slate,:id,:mean,:median,:p10,:p25,:p75,:p90,'2026-10-02T00:00:00Z')'''),
                    dict(run=f'proj-{slate}', game=game, slate=slate, id=uid, mean=player.projection_mean,
                         median=player.projection_p50, p10=player.projection_p10, p25=player.projection_p25,
                         p75=player.projection_p75, p90=player.projection_p90))
            connection.execute(text('''INSERT INTO target.ownership_model_run
                (ownership_run_id,model_id,season,week,slate_id,data_cutoff_at,training_rows,status)
                VALUES (:run,'fixture',2026,5,:slate,'2026-10-02T00:00:00Z',0,'completed')'''), dict(run=f'own-{slate}',slate=slate))
            for i, player in pool.iterrows():
                roles = ['CPT', 'FLEX'] if format == 'showdown' else [player.position]
                for role in roles:
                    connection.execute(text('''INSERT INTO target.ownership_projection
                        (ownership_run_id,season,week,slate_id,player_id,roster_position,projected_ownership,data_cutoff_at)
                        VALUES (:run,2026,5,:slate,:id,:role,10,'2026-10-02T00:00:00Z')'''),
                        dict(run=f'own-{slate}',slate=slate,id=f'{slate}-{i}',role=role))
    yield engine
    engine.dispose()


@pytest.mark.parametrize('slate,format', SCOPES)
def test_real_sql_simulation_persistence_replay_and_scope_isolation(engine, slate, format):
    service = SimulationService(engine=engine)
    result = service.run(season=2026, week=5, slate=slate, contest_format=format,
                         projection_run_id=f'proj-{slate}', ownership_run_id=f'own-{slate}', num_simulations=3)
    assert len(result.rows) == (8 if format == 'showdown' else 10)
    assert all(r['player_id'].startswith(slate + '-') for r in result.rows)
    assert all(r['field_ownership'] == (20 if format == 'showdown' else 10) for r in result.rows)
    assert result.successful_simulations == 3
    restored = service.fetch_by_id(result.simulation_run_id)
    latest = service.fetch_latest(season=2026, week=5, slate=slate, contest_format=format)
    assert restored.simulation_run_id == latest.simulation_run_id == result.simulation_run_id
    saved = service._load_persisted_pool(result.simulation_run_id)
    args = dict(num_simulations=3, seed=result.seed, salary_cap=result.salary_cap)
    if format == 'showdown':
        counts, captains, successful = simulate_showdown_lineups(saved, **args)
        assert sum(r['captain_optimal_count'] for r in restored.rows) == 3
        assert min(saved.salary) == 200  # The Classic salary floor must not drop this player.
        assert 'K' in saved.position.values
    else:
        counts, successful = simulate_optimal_lineups(saved, **args)
    expected = {r['player_id']: r['optimal_lineup_count'] for r in result.rows}
    assert dict(zip(saved.player_id, counts)) == expected
    assert successful == 3
    with engine.connect() as connection:
        metadata = connection.execute(text('SELECT roster_size,params_json FROM target.simulation_run WHERE simulation_run_id=:id'), dict(id=result.simulation_run_id)).mappings().one()
    assert metadata['roster_size'] == (6 if format == 'showdown' else 9)
    assert metadata['params_json']['contest_outcome_model'] == 'unavailable'
    with pytest.raises(ValueError, match='Projection run not found'):
        service.run(season=2026,week=5,slate=slate,contest_format=format,projection_run_id='proj-WRONG')


def test_salary_snapshot_after_cutoff_cannot_leak_into_simulation(engine):
    service = SimulationService(engine=engine)
    with engine.begin() as connection:
        connection.execute(text("UPDATE target.snapshot_salary SET as_of='2026-10-03T00:00:00Z' WHERE slate='DK_SECOND_SUNDAY_GAME'"))
    with pytest.raises(ValueError, match='No salary rows'):
        service.run(season=2026, week=5, slate='DK_SECOND_SUNDAY_GAME', contest_format='showdown',
                    projection_run_id='proj-DK_SECOND_SUNDAY_GAME', num_simulations=1)
