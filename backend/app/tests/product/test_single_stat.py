from datetime import UTC, datetime, timedelta
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.product_services import single_stat as stat
from backend.app.api.single_stat_routes import router
from backend.app.db import get_db_session
from backend.app.models import Base, PlayerAlias, PlayerMaster, RawNflWeeklyStat, IngestRun

NOW = datetime(2026, 10, 15, 16, tzinfo=UTC)


def package(variant='total_yards'):
    return stat.PoolImport.model_validate(dict(contest_format='single_stat', variant=variant, game_set_id='fixture-only', season=2026, week=6,
        source_name='fixture.csv', source_reference='Fixture validation: not a DraftKings contest', classification='fixture_research',
        source_observed_at=NOW.isoformat(), scoring_period_end_at=(NOW + timedelta(days=7)).isoformat(), scoring_period_source='Fixture rules scope', contest_status='active',
        games=[dict(game_id='g', teams=['A', 'B'], original_start_at=(NOW + timedelta(hours=2)).isoformat(), scheduled_start_at=(NOW + timedelta(hours=2)).isoformat(), provider_status='confirmed', provider_observed_at=NOW.isoformat(), provider_source='fixture')],
        columns=dict(source_player_id='ID', name='Name', team='Team', game_id='Game'), native_csv='ID,Name,Team,Game\n1,Same Name,A,g\n2,Same Name,A,g\n3,Other,B,g\n4,Defender,B,g\n'))


def forecast(session, pid, cutoff, season, week, variant):
    components = {key: float(pid) for key in stat.COMPONENTS[variant]}
    return dict(method='fixture', components=components, **stat.score(variant, components), covered_value=sum(components.values()), sample_games=3, evidence=[], warning='fixture')


def pool(tmp_path, variant='total_yards', **kwargs):
    return stat.import_pool(package(variant), None, directory=tmp_path, now=NOW, resolver=lambda source_id: source_id, forecaster=forecast, **kwargs)


@pytest.mark.parametrize('variant,stats,expected', [
    ('touchdowns', dict(rushing_tds=1, receiving_tds=2, passing_tds=99, kick_return_tds=1, missed_fg_return_tds=1, punt_return_tds=1, offensive_fumble_recovery_tds=1, defensive_tds=2), 9),
    ('total_yards', dict(rushing_yards=40, receiving_yards=30, passing_yards=500), 70),
    ('passing_yards', dict(rushing_yards=40, receiving_yards=30, passing_yards=500), 500),
])
def test_exact_scoring(variant, stats, expected):
    assert stat.score(variant, stats)['value'] == expected


def test_unknowns_are_not_zero():
    result = stat.score('touchdowns', dict(rushing_tds=1, receiving_tds=1))
    assert result['value'] is None and 'defensive_tds' in result['missing_components']
    assert stat.score('touchdowns', {}, disabled=True)['value'] == 0
    with pytest.raises(ValueError): stat.score('passing_yards', {'passing_yards': float('nan')})


@pytest.mark.parametrize('variant', stat.COMPONENTS)
def test_roundtrip_exact_optimizer(tmp_path, variant):
    imported = pool(tmp_path, variant)
    assert stat.load(imported['sha256'], tmp_path) == imported
    result = stat.optimize(stat.Optimize(pool_sha256=imported['sha256']), directory=tmp_path, now=NOW)
    assert {p['player_master_id'] for p in result['players']} == {'2', '3', '4'}
    assert stat.legal_lineup(result['players'])
    assert result['solver_status'] == 'OPTIMAL' and result['units'] == stat.UNITS[variant]
    assert stat.load(result['sha256'], tmp_path) == result
    assert result['export']['enabled'] is False and result['entry_ready'] is False
    assert result['rules']['salary_cap'] is None and result['rules']['position_requirements'] is None


def test_canonical_rosters_and_scope(tmp_path):
    assert not stat.legal_lineup([dict(player_master_id='same', team=t) for t in ['A', 'B', 'B']])
    assert not stat.legal_lineup([dict(player_master_id=str(i), team='A') for i in range(3)])
    req = package(); req.native_csv += '5,Out,C,g\n'
    with pytest.raises(ValueError, match='outside'): stat.import_pool(req, None, directory=tmp_path, now=NOW, resolver=lambda _: None)
    req = package()
    with pytest.raises(ValueError, match='Duplicate canonical'): stat.import_pool(req, None, directory=tmp_path, now=NOW, resolver=lambda _: '1', forecaster=forecast)
    unresolved = stat.import_pool(package(), None, directory=tmp_path, now=NOW, resolver=lambda _: None)
    assert len(unresolved['players']) == 4
    assert 'pool_identity_or_stat_coverage_incomplete' in stat.readiness(unresolved, now=NOW)['reason_codes']


def test_lock_disabled_early_start_and_provider_decision(tmp_path):
    imported = pool(tmp_path)
    assert stat.readiness(imported, now=NOW)['status'] == 'READY_FOR_RESEARCH'
    game = imported['source']['games'][0]
    game['started_at'] = (NOW - timedelta(seconds=1)).isoformat()
    assert all('player_locked' in p['reason_codes'] for p in stat.readiness(imported, now=NOW)['players'])
    game['started_at'] = None; game['disabled'] = True
    assert all('provider_disabled_game' in p['reason_codes'] for p in stat.readiness(imported, now=NOW)['players'])
    game['disabled'] = False; game['provider_status'] = 'decision_pending'
    assert 'provider_game_decision_unresolved' in stat.readiness(imported, now=NOW)['reason_codes']
    imported['source']['contest_status'] = 'cancelled'
    assert 'provider_contest_status_cancelled' in stat.readiness(imported, now=NOW)['reason_codes']


def test_td_partial_is_explicit(tmp_path):
    imported = pool(tmp_path, 'touchdowns')
    for p in imported['players']:
        p['forecast']['components']['defensive_tds'] = None
        p['forecast'].update(stat.score('touchdowns', p['forecast']['components']))
        p['forecast']['covered_value'] = sum(v for v in p['forecast']['components'].values() if v is not None)
    imported.pop('sha256'); imported = stat._save(imported, tmp_path)
    with pytest.raises(ValueError, match='stat_forecast_missing|coverage_incomplete'): stat.optimize(stat.Optimize(pool_sha256=imported['sha256']), directory=tmp_path, now=NOW)
    result = stat.optimize(stat.Optimize(pool_sha256=imported['sha256'], allow_partial_touchdown_research=True), directory=tmp_path, now=NOW)
    assert result['objective'] == 'highest_expected_covered_touchdowns'
    assert result['classification'] == 'PARTIAL_STAT_RESEARCH'
    assert all('defensive_tds' in p['missing_components'] for p in result['players'])


def test_hash_tamper_and_wrong_format(tmp_path):
    imported = pool(tmp_path)
    path = tmp_path / (imported['sha256'] + '.json')
    data = json.loads(path.read_text()); data['variant'] = 'passing_yards'; path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='hash mismatch'): stat.load(imported['sha256'], tmp_path)
    with pytest.raises(ValueError): stat.load('../bad', tmp_path)
    with pytest.raises(ValueError): stat.PoolImport.model_validate({**package().model_dump(), 'contest_format': 'classic'})


def test_api_contract_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(stat, 'LEDGER', tmp_path)
    original = stat.import_pool
    monkeypatch.setattr(stat, 'import_pool', lambda request, session: original(request, session, now=NOW, resolver=lambda source_id: source_id, forecaster=forecast))
    monkeypatch.setattr(stat, 'readiness', lambda record: {'status': 'FIXTURE'})
    app = FastAPI(); app.include_router(router); app.dependency_overrides[get_db_session] = lambda: None
    client = TestClient(app)
    response = client.post('/api/single-stat/pools', json=package().model_dump(mode='json'))
    assert response.status_code == 200, response.text
    key = response.json()['sha256']
    assert client.get('/api/single-stat/records/' + key).json()['sha256'] == key
    assert len(client.get('/api/single-stat/records').json()['rows']) == 1
    assert client.get('/api/single-stat/records/invalid').status_code == 404
    assert client.post('/api/single-stat/pools', json={'contest_format': 'showdown'}).status_code == 422


def test_baseline_native_identity_and_chronology():
    engine = create_engine('sqlite://', poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        pid = '00000000-0000-0000-0000-000000000001'
        session.add(PlayerMaster(player_master_id=pid, full_name='Example', normalized_name='example'))
        session.add(PlayerAlias(player_master_id=pid, source_system='nflverse', source_key='gsis-1', alias_name='Example', normalized_alias='example'))
        session.add(IngestRun(ingest_run_id='run', source_system='nflverse', source_table='stats'))
        session.flush()
        for week, value, observed in [(3, 50, NOW-timedelta(days=20)), (4, 100, NOW-timedelta(days=13)), (5, 999, NOW+timedelta(days=1)), (6, 999, NOW-timedelta(days=1))]:
            session.add(RawNflWeeklyStat(ingest_run_id='run', source_system='nflverse', season=2026, week=week, player_id='gsis-1', raw_row_json={'passing_yards': value}, created_at=observed.replace(tzinfo=None)))
        session.flush()
        result = stat.historical_baseline(session, pid, NOW, 2026, 6, 'passing_yards')
        assert result['value'] == 75 and result['sample_games'] == 2
        assert stat.historical_baseline(session, 'other', NOW, 2026, 6, 'passing_yards')['value'] is None


def test_import_idempotency_and_separate_evaluations(tmp_path):
    first = pool(tmp_path)
    retry = stat.import_pool(package(), None, directory=tmp_path, now=NOW+timedelta(minutes=1), resolver=lambda _: None)
    assert retry == first
    req = package(); req.evaluation_id = 'after_identity_review'
    reviewed = stat.import_pool(req, None, directory=tmp_path, now=NOW, resolver=lambda _: None)
    assert reviewed['sha256'] != first['sha256']
    assert reviewed['native_csv_sha256'] == first['native_csv_sha256']


def test_actual_result_incomplete_categories_remain_unknown(tmp_path):
    imported = pool(tmp_path, 'touchdowns')
    report = stat.optimize(stat.Optimize(pool_sha256=imported['sha256']), directory=tmp_path, now=NOW)
    request = stat.ActualResult(report_sha256=report['sha256'], source_reference='fixture official-results source', source_observed_at=NOW,
        official_nfl_statistics=True, original_scoring_period_only=True, suspended_game_resumption_stats_excluded=True,
        players=[stat.ActualPlayer(player_master_id=p['player_master_id'], stats=dict(rushing_tds=1, receiving_tds=1, passing_tds=99)) for p in report['players']])
    result = stat.actual_result(request, directory=tmp_path, now=NOW)
    assert result['actual_metric'] is None and result['classification'] == 'FIXTURE_ACTUALS'
    for player in request.players: player.stats.update({k: 1 for k in stat.COMPONENTS['touchdowns']})
    complete = stat.actual_result(request, directory=tmp_path, now=NOW)
    assert complete['actual_metric'] == 21
    request.players[0].player_master_id = 'different'
    with pytest.raises(ValueError, match='canonical'): stat.actual_result(request, directory=tmp_path, now=NOW)


def test_incomplete_pool_requires_explicit_subset_research(tmp_path):
    imported = pool(tmp_path)
    imported['players'][0]['forecast'] = None
    imported.pop('sha256'); imported = stat._save(imported, tmp_path)
    with pytest.raises(ValueError, match='coverage_incomplete'): stat.optimize(stat.Optimize(pool_sha256=imported['sha256']), directory=tmp_path, now=NOW)
    result = stat.optimize(stat.Optimize(pool_sha256=imported['sha256'], allow_incomplete_pool_research=True), directory=tmp_path, now=NOW)
    assert result['objective_scope'] == 'measured_eligible_subset_only'
    assert result['classification'] == 'INCOMPLETE_POOL_RESEARCH'
    assert result['excluded_players'][0]['source_player_id'] == '1'
    assert 'stat_forecast_missing' in result['excluded_players'][0]['reason_codes']


def test_unresolved_rows_create_traceable_idempotent_queue(tmp_path):
    from backend.app.models import UnresolvedPlayerQueue
    engine = create_engine('sqlite://', poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        imported = stat.import_pool(package(), session, directory=tmp_path, now=NOW)
        queued = list(session.scalars(select(UnresolvedPlayerQueue)))
        assert len(queued) == 4 and {q.source_player_key for q in queued} == {'1','2','3','4'}
        assert all(q.raw_row_json['identity_status'] == 'unresolved_native_id' for q in queued)
        run = session.get(IngestRun, queued[0].ingest_run_id)
        assert run.rows_unresolved == 4 and run.source_checksum == imported['native_csv_sha256']
        retry = stat.import_pool(package(), session, directory=tmp_path, now=NOW)
        assert retry['sha256'] == imported['sha256']
        assert len(list(session.scalars(select(UnresolvedPlayerQueue)))) == 4


def test_clocks_and_scoring_period_are_explicit(tmp_path):
    with pytest.raises(ValueError, match='future'):
        stat.import_pool(package(), None, directory=tmp_path, now=NOW-timedelta(seconds=1))
    payload = package().model_dump(); payload['source_observed_at'] = NOW.replace(tzinfo=None)
    with pytest.raises(ValueError, match='timezone'): stat.PoolImport.model_validate(payload)
    payload = package().model_dump(); payload['games'][0]['provider_observed_at'] = NOW+timedelta(seconds=1)
    with pytest.raises(ValueError, match='cannot follow'): stat.PoolImport.model_validate(payload)
    imported = pool(tmp_path)
    assert 'scoring_period_closed' in stat.readiness(imported, now=NOW+timedelta(days=8))['reason_codes']


def test_actual_disabled_source_decision_creates_new_result(tmp_path):
    imported = pool(tmp_path)
    report = stat.optimize(stat.Optimize(pool_sha256=imported['sha256']), directory=tmp_path, now=NOW)
    req = stat.ActualResult(report_sha256=report['sha256'], source_reference='fixture later provider disabled decision', source_observed_at=NOW,
        official_nfl_statistics=True, original_scoring_period_only=True, suspended_game_resumption_stats_excluded=True,
        disabled_game_ids=['g'], players=[stat.ActualPlayer(player_master_id=p['player_master_id'], stats={}) for p in report['players']])
    result = stat.actual_result(req, directory=tmp_path, now=NOW)
    assert result['actual_metric'] == 0
    assert stat.load(report['sha256'],tmp_path)['expected_metric'] > 0
    req.disabled_game_ids = ['outside']
    with pytest.raises(ValueError, match='outside'): stat.actual_result(req, directory=tmp_path, now=NOW)


def test_native_actuals_cannot_predate_game(tmp_path):
    imported = pool(tmp_path)
    imported['classification'] = 'native_pool'; imported.pop('sha256'); imported = stat._save(imported, tmp_path)
    report = stat.optimize(stat.Optimize(pool_sha256=imported['sha256']), directory=tmp_path, now=NOW)
    request = stat.ActualResult(report_sha256=report['sha256'], source_reference='chronology test', source_observed_at=NOW,
        official_nfl_statistics=True, original_scoring_period_only=True, suspended_game_resumption_stats_excluded=True,
        players=[stat.ActualPlayer(player_master_id=p['player_master_id'], stats={'rushing_yards':1,'receiving_yards':1}) for p in report['players']])
    with pytest.raises(ValueError, match='predate'): stat.actual_result(request, directory=tmp_path, now=NOW)


def test_optimize_and_actual_api_contracts(tmp_path, monkeypatch):
    imported = pool(tmp_path)
    monkeypatch.setattr(stat, 'LEDGER', tmp_path)
    optimize_at = stat.optimize
    monkeypatch.setattr(stat, 'optimize', lambda req: optimize_at(req, now=NOW))
    app = FastAPI(); app.include_router(router); client = TestClient(app)
    response = client.post('/api/single-stat/optimize', json={'pool_sha256':imported['sha256']})
    assert response.status_code == 200, response.text
    report = response.json()
    assert report['expected_metric'] == 18 and report['objective'] == 'highest_expected_total_yards'
    assert report['pool_classification'] == 'fixture_research'
    actual = client.post('/api/single-stat/actual-results', json={
        'report_sha256':report['sha256'], 'source_reference':'synthetic API actuals', 'source_observed_at':NOW.isoformat(),
        'official_nfl_statistics':True,'original_scoring_period_only':True,'suspended_game_resumption_stats_excluded':True,
        'players':[{'player_master_id':p['player_master_id'],'stats':{'rushing_yards':1,'receiving_yards':1,'passing_yards':999}} for p in report['players']]})
    assert actual.status_code == 200, actual.text
    assert actual.json()['actual_metric'] == 6
    assert actual.json()['classification'] == 'FIXTURE_ACTUALS'
    assert client.post('/api/single-stat/optimize', json={'pool_sha256':imported['sha256'],'salary_cap':50000}).status_code == 422


def test_native_bom_game_mapping_and_status_retention(tmp_path):
    req=package(); req.native_csv='\ufeffPosition,Name,ID,TeamAbbrev,Game Info,Status\nRB,Same Name,1,A,A@B 10/18/2026 01:00PM ET,OUT\nWR,Other,2,A,A@B 10/18/2026 01:00PM ET,\nTE,Third,3,B,A@B 10/18/2026 01:00PM ET,\nRB,Fourth,4,B,A@B 10/18/2026 01:00PM ET,\n'
    req.columns=dict(source_player_id='ID',name='Name',team='TeamAbbrev',game_id='Game Info');req.native_game_ids={'A@B 10/18/2026 01:00PM ET':'g'}
    imported=stat.import_pool(req,None,directory=tmp_path,now=NOW,resolver=lambda s:s,forecaster=forecast)
    assert imported['players'][0]['position']=='RB' and imported['players'][0]['native_status']=='OUT'
    ready=stat.readiness(imported,now=NOW)
    assert len(ready['players'])==4 and 'confirmed_or_doubtful_unavailable' in ready['players'][0]['reason_codes']
    report=stat.optimize(stat.Optimize(pool_sha256=imported['sha256']),directory=tmp_path,now=NOW)
    assert {p['source_player_id'] for p in report['players']}=={'2','3','4'}
    assert imported['source']['native_csv'].startswith('\ufeff')


def test_native_new_id_uses_scoped_identity_and_persists_alias(tmp_path):
    engine=create_engine('sqlite://',poolclass=StaticPool);Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(PlayerMaster(player_master_id='canonical',full_name='Exact Player',normalized_name='exact player',primary_team='A',position='RB'))
        session.commit()
        req=package();req.native_csv='Position,Name,ID,Team,Game\nRB,Exact Player,new-id,A,g\n'
        imported=stat.import_pool(req,session,directory=tmp_path,now=NOW)
        assert imported['players'][0]['player_master_id']=='canonical'
        assert session.scalar(select(PlayerAlias.player_master_id).where(PlayerAlias.source_key=='new-id'))=='canonical'
