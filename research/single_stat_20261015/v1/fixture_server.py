"""Isolated real API fixture. Never connects to the production/local football DB."""
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import tempfile
from uuid import UUID

from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.models import Base, IngestRun, PlayerAlias, PlayerMaster, RawNflWeeklyStat
from backend.app.db import get_db_session
from backend.app.api.single_stat_routes import router
from backend.app.product_services import single_stat

ROOT = Path(tempfile.mkdtemp(prefix='football-single-stat-fixture-'))
engine = create_engine('sqlite:///' + str(ROOT / 'fixture.sqlite'))
Base.metadata.create_all(engine)
factory = sessionmaker(engine)
now = datetime.now(UTC)
with factory() as session:
    session.add(IngestRun(ingest_run_id='fixture-history', source_system='fixture_stat_source', source_table='fixture_stats', status='completed'))
    for n, name, team in [(1,'Fixture Quarterback','AAA'), (2,'Fixture Receiver','AAA'), (3,'Fixture Runner','BBB'), (4,'Fixture Defender','BBB')]:
        pid = str(UUID(int=n))
        session.add(PlayerMaster(player_master_id=pid, full_name=name, normalized_name=name.lower()))
        session.add(PlayerAlias(player_master_id=pid, source_system='draftkings', source_key='fixture-'+str(n), alias_name=name, normalized_alias=name.lower()))
        session.add(PlayerAlias(player_master_id=pid, source_system='fixture_stat_source', source_key=str(n), alias_name=name, normalized_alias=name.lower()))
        session.flush()
        for week in [3,4,5]:
            stats = {key: (n*10 if 'yards' in key else n*.1) for key in set(sum(single_stat.COMPONENTS.values(), ()))}
            session.add(RawNflWeeklyStat(ingest_run_id='fixture-history', source_system='fixture_stat_source', season=2026, week=week, player_id=str(n), game_id='history-'+str(week), raw_row_json=stats, created_at=(now-timedelta(days=7)).replace(tzinfo=None)))
    session.commit()
single_stat.LEDGER = ROOT / 'ledger'
app = FastAPI(); app.include_router(router)
def db():
    with factory() as session: yield session
app.dependency_overrides[get_db_session] = db
source = dict(contest_format='single_stat', variant='total_yards', game_set_id='FIXTURE_RESEARCH_ONLY', season=2026, week=6,
    source_name='synthetic-single-stat-validation.csv', source_reference='Synthetic fixture; not a real DraftKings pool or native entry IDs', classification='fixture_research',
    source_observed_at=now.isoformat(), scoring_period_end_at=(now+timedelta(days=7)).isoformat(), scoring_period_source='Synthetic validation period', contest_status='active',
    games=[dict(game_id='fixture-game', teams=['AAA','BBB'], original_start_at=(now+timedelta(days=1)).isoformat(), scheduled_start_at=(now+timedelta(days=1)).isoformat(), provider_status='confirmed', provider_observed_at=now.isoformat(), provider_source='Synthetic fixture')],
    columns=dict(source_player_id='Native ID',name='Name',team='Team',game_id='Game'),
    native_csv='Native ID,Name,Team,Game\nfixture-1,Fixture Quarterback,AAA,fixture-game\nfixture-2,Fixture Receiver,AAA,fixture-game\nfixture-3,Fixture Runner,BBB,fixture-game\nfixture-4,Fixture Defender,BBB,fixture-game\n')
for variant in single_stat.COMPONENTS:
    (ROOT / (variant+'.json')).write_text(json.dumps({**source,'variant':variant},indent=2))
print('ISOLATED_FIXTURE_ROOT='+str(ROOT), flush=True)
