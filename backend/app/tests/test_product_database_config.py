from Database.config import get_connection_string
from backend.app.config import get_settings


def test_product_database_config_uses_canonical_app_settings() -> None:
    assert get_connection_string() == get_settings().sqlalchemy_database_uri
