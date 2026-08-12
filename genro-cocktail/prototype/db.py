"""SQLite through genro-asgi's ``databases`` seam — the cocktail bar edition.

The core defines a contract, not a database layer: the config names a
``db_class`` built once at boot and shared by every request and every thread
pool worker. Two rules follow, both encoded here:

- connections are **thread-local** (sqlite3 objects must not cross threads);
- mutations commit **inside the method that runs them**, on the same thread,
  because the framework's ``closeConnection`` cleanup runs on the event-loop
  thread, not on the pool thread that did the work.

``CocktailDb`` is both the adapter and the repository: domain queries live on
it as methods, reachable from handlers through the transparent
``AsgiDbHandlerBase`` proxy (``self.db.list_cocktails(...)``).

Domain in one breath: **ingredients** carry an ABV and a cost per ml;
**cocktails** are lists of (ingredient, ml). The classics are read-only
teachers — fork one and the copy is yours to remix. Everything interesting
(volume, alcohol, cost, standard drinks) is derived by ``stats_for``.
"""

from __future__ import annotations

import sqlite3
import threading

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ingredient (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    emoji TEXT NOT NULL DEFAULT '🧴',
    abv REAL NOT NULL DEFAULT 0,            -- % alcohol by volume, 0-100
    cost_per_ml REAL NOT NULL DEFAULT 0,    -- €/ml
    category TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS cocktail (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    emoji TEXT NOT NULL DEFAULT '🍸',
    owner TEXT NOT NULL DEFAULT '',          -- '' for the classics
    is_classic INTEGER NOT NULL DEFAULT 0,
    tags TEXT NOT NULL DEFAULT '',           -- comma-separated: bitter,sour,...
    story TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS cocktail_line (
    id INTEGER PRIMARY KEY,
    cocktail_id INTEGER NOT NULL REFERENCES cocktail(id),
    ingredient_id INTEGER NOT NULL REFERENCES ingredient(id),
    qty_ml REAL NOT NULL,
    UNIQUE (cocktail_id, ingredient_id)
);
"""

ETHANOL_DENSITY = 0.789        # g/ml
STANDARD_DRINK_GRAMS = 10.0    # WHO standard drink


class CocktailDb:
    """db_class for the config's ``databases`` section."""

    def __init__(self, path: str = "cocktail.db", seed: bool = True):
        self._path = path
        self._local = threading.local()
        boot = sqlite3.connect(self._path)
        try:
            boot.executescript(_SCHEMA)
            if seed and boot.execute("SELECT COUNT(*) FROM ingredient").fetchone()[0] == 0:
                self._seed(boot)
            boot.commit()
        finally:
            boot.close()

    # -- connection discipline -------------------------------------------

    @property
    def connection(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._path, timeout=5.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    def closeConnection(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    def query(self, sql: str, params=()) -> list[dict]:
        return [dict(row) for row in self.connection.execute(sql, params).fetchall()]

    def one(self, sql: str, params=()) -> dict | None:
        row = self.connection.execute(sql, params).fetchone()
        return dict(row) if row is not None else None

    # -- ingredients ------------------------------------------------------

    def list_ingredients(self, q: str = "") -> list[dict]:
        if q:
            return self.query(
                "SELECT * FROM ingredient WHERE name LIKE ? OR category LIKE ? ORDER BY name",
                (f"%{q}%", f"%{q}%"),
            )
        return self.query("SELECT * FROM ingredient ORDER BY name")

    def add_ingredient(self, name, emoji, abv, cost_per_ml, category) -> int:
        if not 0 <= abv <= 100:
            raise ValueError("ABV must be between 0 and 100")
        cur = self.connection.execute(
            "INSERT INTO ingredient (name, emoji, abv, cost_per_ml, category) VALUES (?, ?, ?, ?, ?)",
            (name, emoji or "🧴", abv, cost_per_ml, category),
        )
        self.connection.commit()
        return cur.lastrowid

    # -- the mixing formula -------------------------------------------------

    def stats_for(self, qtys: dict[int, float]) -> dict:
        """The data formula behind the sliders.

        ``qtys`` maps ingredient_id → ml. Works for anything — a saved
        cocktail, a classic being played with, a draft that only exists in
        the browser — because it computes from the payload, never from a row.
        """
        if not qtys:
            return {"volume": 0.0, "abv": 0.0, "cost": 0.0, "alcohol_g": 0.0, "drinks": 0.0}
        rows = self.query(
            f"SELECT id, abv, cost_per_ml FROM ingredient"
            f" WHERE id IN ({','.join('?' * len(qtys))})",
            tuple(qtys),
        )
        known = {row["id"]: row for row in rows}
        unknown = set(qtys) - set(known)
        if unknown:
            raise ValueError(f"unknown ingredients: {sorted(unknown)}")
        volume = sum(max(0.0, ml) for ml in qtys.values())
        pure_alcohol = sum(max(0.0, ml) * known[iid]["abv"] / 100.0 for iid, ml in qtys.items())
        cost = sum(max(0.0, ml) * known[iid]["cost_per_ml"] for iid, ml in qtys.items())
        alcohol_g = pure_alcohol * ETHANOL_DENSITY
        return {
            "volume": round(volume, 1),
            "abv": round(100.0 * pure_alcohol / volume, 1) if volume else 0.0,
            "cost": round(cost, 2),
            "alcohol_g": round(alcohol_g, 1),
            "drinks": round(alcohol_g / STANDARD_DRINK_GRAMS, 1),
        }

    # -- cocktails ---------------------------------------------------------

    def list_cocktails(self, owner: str = "", tag: str = "", q: str = "") -> list[dict]:
        """The bar: every classic plus the caller's own creations."""
        sql = "SELECT * FROM cocktail WHERE (is_classic = 1 OR owner = ?)"
        params: list = [owner]
        if tag:
            sql += " AND (',' || tags || ',') LIKE ?"
            params.append(f"%,{tag},%")
        if q:
            sql += " AND name LIKE ?"
            params.append(f"%{q}%")
        sql += " ORDER BY is_classic DESC, name"
        cocktails = self.query(sql, tuple(params))
        for cocktail in cocktails:
            cocktail.update(self.stats_for(self.qtys_of(cocktail["id"])))
            cocktail["tag_list"] = [t for t in cocktail["tags"].split(",") if t]
        return cocktails

    def qtys_of(self, cocktail_id: int) -> dict[int, float]:
        return {
            row["ingredient_id"]: row["qty_ml"]
            for row in self.query(
                "SELECT ingredient_id, qty_ml FROM cocktail_line WHERE cocktail_id=?",
                (cocktail_id,),
            )
        }

    def cocktail_detail(self, cocktail_id: int) -> dict:
        cocktail = self.one("SELECT * FROM cocktail WHERE id=?", (cocktail_id,))
        if cocktail is None:
            raise FileNotFoundError(f"no cocktail {cocktail_id}")
        lines = self.query(
            """
            SELECT cocktail_line.*, ingredient.name, ingredient.emoji,
                   ingredient.abv, ingredient.cost_per_ml
            FROM cocktail_line JOIN ingredient ON ingredient.id = cocktail_line.ingredient_id
            WHERE cocktail_line.cocktail_id=? ORDER BY ingredient.abv DESC, ingredient.name
            """,
            (cocktail_id,),
        )
        cocktail["tag_list"] = [t for t in cocktail["tags"].split(",") if t]
        return {
            "cocktail": cocktail,
            "lines": lines,
            "stats": self.stats_for({line["ingredient_id"]: line["qty_ml"] for line in lines}),
            "shelf": self.query(
                """
                SELECT * FROM ingredient
                WHERE id NOT IN (SELECT ingredient_id FROM cocktail_line WHERE cocktail_id=?)
                ORDER BY name
                """,
                (cocktail_id,),
            ),
        }

    def create_cocktail(self, owner: str, name: str, emoji: str = "🍸") -> int:
        if not owner:
            raise ValueError("no owner — is the session cookie missing?")
        if not name.strip():
            raise ValueError("give it a name")
        cur = self.connection.execute(
            "INSERT INTO cocktail (name, emoji, owner) VALUES (?, ?, ?)",
            (name.strip(), emoji or "🍸", owner),
        )
        self.connection.commit()
        return cur.lastrowid

    def fork_cocktail(self, cocktail_id: int, owner: str) -> int:
        """Copy a cocktail (typically a classic) onto the caller's shelf."""
        if not owner:
            raise ValueError("no owner — is the session cookie missing?")
        source = self.one("SELECT * FROM cocktail WHERE id=?", (cocktail_id,))
        if source is None:
            raise FileNotFoundError(f"no cocktail {cocktail_id}")
        conn = self.connection
        try:
            cur = conn.execute(
                "INSERT INTO cocktail (name, emoji, owner, tags, story) VALUES (?, ?, ?, ?, ?)",
                (f"{source['name']} remix", source["emoji"], owner, source["tags"], ""),
            )
            new_id = cur.lastrowid
            conn.execute(
                """
                INSERT INTO cocktail_line (cocktail_id, ingredient_id, qty_ml)
                SELECT ?, ingredient_id, qty_ml FROM cocktail_line WHERE cocktail_id=?
                """,
                (new_id, cocktail_id),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return new_id

    def owns(self, cocktail_id: int, owner: str) -> bool:
        row = self.one("SELECT owner, is_classic FROM cocktail WHERE id=?", (cocktail_id,))
        return bool(row) and not row["is_classic"] and row["owner"] == owner and bool(owner)

    def update_meta(self, cocktail_id: int, owner: str, name: str, tags: str, emoji: str) -> None:
        if not self.owns(cocktail_id, owner):
            raise ValueError("not yours to rename — fork it first")
        if not name.strip():
            raise ValueError("give it a name")
        clean_tags = ",".join(sorted({t.strip().lower() for t in tags.split(",") if t.strip()}))
        self.connection.execute(
            "UPDATE cocktail SET name=?, tags=?, emoji=? WHERE id=?",
            (name.strip(), clean_tags, emoji or "🍸", cocktail_id),
        )
        self.connection.commit()

    def delete_cocktail(self, cocktail_id: int, owner: str) -> None:
        if not self.owns(cocktail_id, owner):
            raise ValueError("not yours to pour down the drain")
        conn = self.connection
        conn.execute("DELETE FROM cocktail_line WHERE cocktail_id=?", (cocktail_id,))
        conn.execute("DELETE FROM cocktail WHERE id=?", (cocktail_id,))
        conn.commit()

    def set_qtys(self, cocktail_id: int, owner: str, qtys: dict[int, float]) -> bool:
        """The autosave seam: persist slider positions, but only on YOUR mix.

        Returns True when saved, False when the cocktail is a classic or
        someone else's (the stats still compute — playing is free).
        """
        if not self.owns(cocktail_id, owner):
            return False
        conn = self.connection
        try:
            for ingredient_id, qty in qtys.items():
                if qty <= 0:
                    conn.execute(
                        "DELETE FROM cocktail_line WHERE cocktail_id=? AND ingredient_id=?",
                        (cocktail_id, ingredient_id),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO cocktail_line (cocktail_id, ingredient_id, qty_ml)
                        VALUES (?, ?, ?)
                        ON CONFLICT (cocktail_id, ingredient_id) DO UPDATE SET qty_ml=excluded.qty_ml
                        """,
                        (cocktail_id, ingredient_id, qty),
                    )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return True

    def all_tags(self) -> list[str]:
        tags: set[str] = set()
        for row in self.query("SELECT tags FROM cocktail WHERE tags != ''"):
            tags.update(t for t in row["tags"].split(",") if t)
        return sorted(tags)

    # -- seed: the shelf and the classics ------------------------------------

    @staticmethod
    def _seed(conn: sqlite3.Connection) -> None:
        ingredients = [
            # name, emoji, abv %, €/ml, category
            ("Gin", "🌲", 40.0, 0.022, "spirit"),
            ("Vodka", "❄️", 40.0, 0.018, "spirit"),
            ("White rum", "🏝️", 38.0, 0.018, "spirit"),
            ("Tequila", "🌵", 40.0, 0.025, "spirit"),
            ("Bourbon", "🛢️", 45.0, 0.028, "spirit"),
            ("Campari", "🔴", 25.0, 0.020, "bitter"),
            ("Aperol", "🟠", 11.0, 0.015, "bitter"),
            ("Sweet vermouth", "🍷", 16.0, 0.012, "fortified"),
            ("Dry vermouth", "🥂", 18.0, 0.012, "fortified"),
            ("Triple sec", "🍊", 30.0, 0.016, "liqueur"),
            ("Coffee liqueur", "☕", 20.0, 0.020, "liqueur"),
            ("Prosecco", "🍾", 11.0, 0.008, "wine"),
            ("Lime juice", "🟢", 0.0, 0.008, "juice"),
            ("Lemon juice", "🍋", 0.0, 0.007, "juice"),
            ("Simple syrup", "🍯", 0.0, 0.003, "sweet"),
            ("Angostura bitters", "🌰", 44.7, 0.150, "bitter"),
            ("Espresso", "☕", 0.0, 0.010, "coffee"),
            ("Soda water", "💧", 0.0, 0.002, "mixer"),
            ("Tonic water", "✨", 0.0, 0.003, "mixer"),
            ("Mint cordial", "🌿", 0.0, 0.012, "sweet"),
        ]
        conn.executemany(
            "INSERT INTO ingredient (name, emoji, abv, cost_per_ml, category) VALUES (?, ?, ?, ?, ?)",
            ingredients,
        )
        ing = {row[0]: idx + 1 for idx, row in enumerate(ingredients)}
        classics = [
            # name, emoji, tags, story, [(ingredient, ml), ...]
            ("Negroni", "🥃", "bitter,strong",
             "Count Negroni wanted his Americano stronger. Florence, 1919.",
             [("Gin", 30), ("Campari", 30), ("Sweet vermouth", 30)]),
            ("Americano", "🥂", "bitter,fresh",
             "The gentle ancestor: Milano-Torino with a splash of soda.",
             [("Campari", 30), ("Sweet vermouth", 30), ("Soda water", 60)]),
            ("Daiquiri", "🍸", "sour,fresh",
             "Rum, lime, sugar. The proof that three is a crowd done right.",
             [("White rum", 60), ("Lime juice", 25), ("Simple syrup", 15)]),
            ("Margarita", "🍹", "sour,fresh",
             "Tequila's passport to the world, salt rim optional.",
             [("Tequila", 50), ("Triple sec", 20), ("Lime juice", 25)]),
            ("Old Fashioned", "🧊", "strong,sweet",
             "The cocktail that refuses to be improved. Since ~1880.",
             [("Bourbon", 60), ("Simple syrup", 10), ("Angostura bitters", 3)]),
            ("Mojito", "🌿", "fresh,sweet",
             "Havana's answer to summer.",
             [("White rum", 50), ("Lime juice", 25), ("Mint cordial", 15), ("Soda water", 60)]),
            ("Whiskey Sour", "🍋", "sour",
             "The sour template: spirit, citrus, sweet. Balance is everything.",
             [("Bourbon", 60), ("Lemon juice", 30), ("Simple syrup", 20)]),
            ("Spritz", "🌅", "bitter,fresh,fruity",
             "Venice at 6 pm, in a glass.",
             [("Prosecco", 90), ("Aperol", 60), ("Soda water", 30)]),
            ("Gin & Tonic", "✨", "dry,fresh",
             "A highball and a history of malaria prevention.",
             [("Gin", 50), ("Tonic water", 150)]),
            ("Espresso Martini", "☕", "sweet,strong",
             "Wake me up and mess me up, 1983.",
             [("Vodka", 50), ("Coffee liqueur", 20), ("Espresso", 30), ("Simple syrup", 5)]),
        ]
        for name, emoji, tags, story, lines in classics:
            cur = conn.execute(
                "INSERT INTO cocktail (name, emoji, owner, is_classic, tags, story)"
                " VALUES (?, ?, '', 1, ?, ?)",
                (name, emoji, tags, story),
            )
            conn.executemany(
                "INSERT INTO cocktail_line (cocktail_id, ingredient_id, qty_ml) VALUES (?, ?, ?)",
                [(cur.lastrowid, ing[iname], ml) for iname, ml in lines],
            )
