"""SQLite database adapter."""

import sqlite3
from .base import DbAdapter


class SqliteAdapter(DbAdapter):
    """SQLite database adapter."""

    def connect(self):
        """
        Create and return a new SQLite connection.

        Returns:
            sqlite3.Connection
        """
        conn = sqlite3.connect(self.connection_info)
        conn.row_factory = sqlite3.Row  # Return rows as dict-like objects
        return conn

    def checkStructure(self):
        """
        Check and create SQLite database schema if needed.

        Creates tables:
        - article_types (id, name, description)
        - articles (id, article_type_id, code, description, price)
        - purchases (id, article_id, quantity, purchase_date)
        """
        cursor = self.cursor()

        # Article types table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS article_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT
            )
        """
        )

        # Articles table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_type_id INTEGER NOT NULL,
                code TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL,
                price REAL NOT NULL,
                FOREIGN KEY (article_type_id) REFERENCES article_types(id)
            )
        """
        )

        # Purchases table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                purchase_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (article_id) REFERENCES articles(id)
            )
        """
        )

        self.commit()
