"""PostgreSQL database adapter."""

from .base import DbAdapter


class PostgresAdapter(DbAdapter):
    """
    PostgreSQL database adapter.

    TODO: Implement using psycopg2 or asyncpg.
    Connection info format: postgresql://user:password@host:port/database
    """

    def connect(self):
        raise NotImplementedError("PostgreSQL adapter not yet implemented")

    def checkStructure(self):
        raise NotImplementedError("PostgreSQL adapter not yet implemented")
