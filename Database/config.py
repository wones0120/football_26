"""Shared database configuration for imported product services and scripts."""

from backend.app.config import get_settings


def get_connection_string() -> str:
    """Return the canonical repo-local database URL.

    ``backend.app.config`` deliberately loads this repository's ``.env`` with
    precedence over inherited shell variables. Keeping product scripts on the
    same settings object prevents an unrelated global ``PGDATABASE`` value from
    silently sending CLI work to a different database than the API.
    """

    return get_settings().sqlalchemy_database_uri
