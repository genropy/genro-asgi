"""PostgreSQL database adapter."""

from .base import DbAdapter


class PostgresAdapter(DbAdapter):
    """PostgreSQL database adapter. TODO: Implement using psycopg2 or asyncpg."""

    placeholder = "%s"  # PostgreSQL uses %s for parameters

    def connect(self):
        raise NotImplementedError("PostgreSQL adapter not yet implemented")

    def check_structure(self):
        raise NotImplementedError("PostgreSQL adapter not yet implemented")
