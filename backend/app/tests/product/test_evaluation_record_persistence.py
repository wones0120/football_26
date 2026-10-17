"""Opt-in local PostgreSQL checks; all inserted evidence is rolled back."""
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from backend.app.config import get_settings
from backend.app.product_services.evaluation_record import append_record

pytestmark = pytest.mark.skipif(os.getenv('EVALUATION_RECORD_DATABASE_TESTS') != '1',
                               reason='Opt-in local database rollback test')


def test_evaluation_evidence_is_idempotent_and_cannot_be_rewritten():
    engine = create_engine(get_settings().sqlalchemy_database_uri)
    assert engine.url.host in {'localhost', '127.0.0.1', '::1'}
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            payload = {'test_id': str(uuid4()), 'candidate_ids': ['run:candidate:1']}
            record = append_record(connection, 'rollback_test', payload)
            assert append_record(connection, 'rollback_test', payload) == record
            assert connection.execute(text('SELECT count(*) FROM target.evaluation_record WHERE record_id=:id'),
                                      {'id':record}).scalar_one() == 1
            for sql in ['UPDATE target.evaluation_record SET kind=kind WHERE record_id=:id',
                        'DELETE FROM target.evaluation_record WHERE record_id=:id']:
                savepoint = connection.begin_nested()
                with pytest.raises(DBAPIError):
                    connection.execute(text(sql), {'id':record})
                savepoint.rollback()
        finally:
            transaction.rollback()
    engine.dispose()
