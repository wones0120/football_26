from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
import logging
from .models import Base

class NFLDatabaseManager:
    def __init__(self, connection_string):
        self.engine = create_engine(connection_string)

    def create_all_tables(self) -> bool:
        try:
            Base.metadata.create_all(self.engine)
            logging.info("All tables created successfully")
            return True
        except SQLAlchemyError as e:
            logging.error(f"Error creating tables: {e}")
            return False
