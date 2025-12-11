"""Base adapter class for database backends."""

from abc import ABC, abstractmethod


class DbAdapter(ABC):
    """
    Abstract base class for database adapters.

    Adapters provide a uniform interface for different database backends
    (SQLite, PostgreSQL, MySQL, etc.).
    """

    def __init__(self, connection_info: str, db):
        self.connection_info = connection_info
        self.db = db

    @abstractmethod
    def connect(self):
        """
        Create and return a new database connection.

        Uses self.connection_info for connection details.

        Returns:
            Database connection object
        """
        pass

    def cursor(self):
        """Get a cursor from the current thread's connection."""
        return self.db.connection.cursor()

    def commit(self):
        """Commit current thread's transaction."""
        self.db.connection.commit()

    def rollback(self):
        """Rollback current thread's transaction."""
        self.db.connection.rollback()

    @abstractmethod
    def checkStructure(self):
        """
        Check and create database schema if needed.

        Each adapter implements this with database-specific SQL.
        """
        pass
