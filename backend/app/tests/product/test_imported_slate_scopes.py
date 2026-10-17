from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.app.api.product_routes import get_imported_slate_scopes
from backend.app.db import get_db_session


def test_imported_slates_are_scoped_deduplicated_and_independent_of_contests():
    from sqlalchemy.pool import StaticPool
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE curated_salary (season int, week int, slate text, source_system text)'))
        for season, week, slate, source in [(2026, 5, 'SUNDAY_LATE_SF_SEA', 'draftkings'),
                (2026, 5, 'sunday_late_sf_sea', 'draftkings'), (2026, 5, 'SUNDAY_MAIN', 'draftkings'),
                (2026, 4, 'OTHER_WEEK', 'draftkings'), (2025, 5, 'OTHER_SEASON', 'draftkings'),
                (2026, 5, 'OTHER_SOURCE', 'fanduel')]:
            connection.execute(text('INSERT INTO curated_salary VALUES (:season,:week,:slate,:source)'),
                dict(season=season, week=week, slate=slate, source=source))
    app = FastAPI()
    app.get('/slate/imported-scopes')(get_imported_slate_scopes)
    def session():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db_session] = session
    with TestClient(app) as client:
        response = client.get('/slate/imported-scopes?season=2026&week=5')
        assert response.status_code == 200
        assert response.json() == {'scopes': [dict(season=2026, week=5, slate=s) for s in ['SUNDAY_LATE_SF_SEA', 'SUNDAY_MAIN']]}
        assert client.get('/slate/imported-scopes?season=2026&week=6').json() == {'scopes': []}
        assert client.get('/slate/imported-scopes?season=2026&week=0').status_code == 422
