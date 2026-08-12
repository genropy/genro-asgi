"""SQLite through genro-asgi's ``databases`` seam.

The core defines a contract, not a database layer: the config names a
``db_class`` built once at boot and shared by every request and every thread
pool worker. Two rules follow, both encoded here:

- connections are **thread-local** (sqlite3 objects must not cross threads);
- mutations commit **inside the method that runs them**, on the same thread,
  because the framework's ``closeConnection`` cleanup runs on the event-loop
  thread, not on the pool thread that did the work.

``CocktailDb`` is both the adapter and the repository: domain queries live on
it as methods, reachable from handlers through the transparent
``AsgiDbHandlerBase`` proxy (``self.db.list_ingredients(...)``).
"""

from __future__ import annotations

import sqlite3
import threading

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ingredient (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    unit TEXT NOT NULL,
    cost_per_unit REAL NOT NULL DEFAULT 0,
    stock_qty REAL NOT NULL DEFAULT 0,
    reorder_level REAL NOT NULL DEFAULT 0,
    category TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS recipe (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL DEFAULT 'finished',
    yield_qty REAL NOT NULL,
    yield_unit TEXT NOT NULL,
    stock_qty REAL NOT NULL DEFAULT 0,
    instructions TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS bom_line (
    id INTEGER PRIMARY KEY,
    recipe_id INTEGER NOT NULL REFERENCES recipe(id),
    component_kind TEXT NOT NULL CHECK (component_kind IN ('ingredient', 'recipe')),
    component_id INTEGER NOT NULL,
    qty REAL NOT NULL,
    unit TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS batch (
    id INTEGER PRIMARY KEY,
    recipe_id INTEGER NOT NULL REFERENCES recipe(id),
    multiplier REAL NOT NULL,
    produced_qty REAL NOT NULL,
    cost_snapshot REAL NOT NULL,
    produced_at TEXT NOT NULL DEFAULT (datetime('now')),
    notes TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS batch_consumption (
    id INTEGER PRIMARY KEY,
    batch_id INTEGER NOT NULL REFERENCES batch(id),
    component_kind TEXT NOT NULL,
    component_id INTEGER NOT NULL,
    qty_used REAL NOT NULL,
    unit_cost_snapshot REAL NOT NULL
);
"""

MAX_BOM_DEPTH = 20


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

    def add_ingredient(self, name, unit, cost_per_unit, stock_qty, reorder_level, category) -> int:
        cur = self.connection.execute(
            "INSERT INTO ingredient (name, unit, cost_per_unit, stock_qty, reorder_level, category)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (name, unit, cost_per_unit, stock_qty, reorder_level, category),
        )
        self.connection.commit()
        return cur.lastrowid

    # -- recipes and costing ----------------------------------------------

    def list_recipes(self) -> list[dict]:
        recipes = self.query("SELECT * FROM recipe ORDER BY kind, name")
        for recipe in recipes:
            recipe["batch_cost"] = self.batch_cost(recipe["id"])
            recipe["unit_cost"] = recipe["batch_cost"] / recipe["yield_qty"]
        return recipes

    def unit_cost(self, kind: str, component_id: int, _depth: int = 0) -> float:
        if _depth > MAX_BOM_DEPTH:
            raise ValueError("BOM deeper than MAX_BOM_DEPTH — cycle suspected")
        if kind == "ingredient":
            row = self.one("SELECT cost_per_unit FROM ingredient WHERE id=?", (component_id,))
            if row is None:
                raise ValueError(f"unknown ingredient {component_id}")
            return row["cost_per_unit"]
        recipe = self.one("SELECT yield_qty FROM recipe WHERE id=?", (component_id,))
        if recipe is None:
            raise ValueError(f"unknown recipe {component_id}")
        return self.batch_cost(component_id, _depth=_depth + 1) / recipe["yield_qty"]

    def batch_cost(self, recipe_id: int, _depth: int = 0) -> float:
        lines = self.query("SELECT * FROM bom_line WHERE recipe_id=?", (recipe_id,))
        return sum(
            line["qty"] * self.unit_cost(line["component_kind"], line["component_id"], _depth)
            for line in lines
        )

    def cost_tree(self, recipe_id: int, _depth: int = 0, _scale: float = 1.0) -> list[dict]:
        """Recursive explosion with per-node subtotals, for the cost panel.

        ``_scale`` carries the consumed fraction down the tree: a sub-recipe's
        children are shown at the share this parent actually uses (200 ml of a
        1300 ml batch scales its sugar to 200/1300 of the batch quantity), so
        every level's children sum to their parent's line total.
        """
        if _depth > MAX_BOM_DEPTH:
            return []
        nodes = []
        for line in self.lines_of(recipe_id):
            cost = self.unit_cost(line["component_kind"], line["component_id"])
            qty = line["qty"] * _scale
            node = {
                "name": line["component_name"],
                "kind": line["component_kind"],
                "qty": qty,
                "unit": line["unit"],
                "unit_cost": cost,
                "total": qty * cost,
                "children": [],
            }
            if line["component_kind"] == "recipe":
                sub = self.one("SELECT yield_qty FROM recipe WHERE id=?", (line["component_id"],))
                node["children"] = self.cost_tree(
                    line["component_id"], _depth + 1, _scale=qty / sub["yield_qty"]
                )
            nodes.append(node)
        return nodes

    def lines_of(self, recipe_id: int) -> list[dict]:
        return self.query(
            """
            SELECT bom_line.*,
                   CASE bom_line.component_kind
                        WHEN 'ingredient' THEN (SELECT name FROM ingredient WHERE id = bom_line.component_id)
                        ELSE (SELECT name FROM recipe WHERE id = bom_line.component_id)
                   END AS component_name
            FROM bom_line WHERE recipe_id=? ORDER BY position, id
            """,
            (recipe_id,),
        )

    def recipe_detail(self, recipe_id: int) -> dict:
        recipe = self.one("SELECT * FROM recipe WHERE id=?", (recipe_id,))
        if recipe is None:
            raise FileNotFoundError(f"no recipe {recipe_id}")  # → 404 via ERROR_MAP
        lines = self.lines_of(recipe_id)
        for line in lines:
            line["unit_cost"] = self.unit_cost(line["component_kind"], line["component_id"])
            line["total"] = line["qty"] * line["unit_cost"]
        batch_cost = sum(line["total"] for line in lines)
        return {
            "recipe": recipe,
            "lines": lines,
            "batch_cost": batch_cost,
            "unit_cost": batch_cost / recipe["yield_qty"] if recipe["yield_qty"] else 0.0,
            "cost_tree": self.cost_tree(recipe_id),
            "pick_ingredients": self.query("SELECT id, name, unit FROM ingredient ORDER BY name"),
            "pick_recipes": self.query(
                "SELECT id, name, yield_unit AS unit FROM recipe WHERE id != ? ORDER BY name",
                (recipe_id,),
            ),
        }

    # -- BOM editing --------------------------------------------------------

    def _subtree_contains(self, recipe_id: int, target_id: int, _depth: int = 0) -> bool:
        if _depth > MAX_BOM_DEPTH:
            return True
        for line in self.query(
            "SELECT component_id FROM bom_line WHERE recipe_id=? AND component_kind='recipe'",
            (recipe_id,),
        ):
            child = line["component_id"]
            if child == target_id or self._subtree_contains(child, target_id, _depth + 1):
                return True
        return False

    def add_line(self, recipe_id: int, kind: str, component_id: int, qty: float) -> int:
        if qty <= 0:
            raise ValueError("quantity must be positive")
        if kind == "ingredient":
            component = self.one("SELECT unit FROM ingredient WHERE id=?", (component_id,))
        elif kind == "recipe":
            if component_id == recipe_id or self._subtree_contains(component_id, recipe_id):
                raise ValueError("that would make the recipe contain itself")
            component = self.one("SELECT yield_unit AS unit FROM recipe WHERE id=?", (component_id,))
        else:
            raise ValueError(f"unknown component kind {kind!r}")
        if component is None:
            raise ValueError(f"unknown {kind} {component_id}")
        position = self.one(
            "SELECT COALESCE(MAX(position), 0) + 1 AS p FROM bom_line WHERE recipe_id=?",
            (recipe_id,),
        )["p"]
        cur = self.connection.execute(
            "INSERT INTO bom_line (recipe_id, component_kind, component_id, qty, unit, position)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (recipe_id, kind, component_id, qty, component["unit"], position),
        )
        self.connection.commit()
        return cur.lastrowid

    def delete_line(self, line_id: int) -> None:
        self.connection.execute("DELETE FROM bom_line WHERE id=?", (line_id,))
        self.connection.commit()

    # -- production -----------------------------------------------------------

    def producibility(self, recipe_id: int, multiplier: float) -> dict:
        requirements = []
        for line in self.lines_of(recipe_id):
            table = "ingredient" if line["component_kind"] == "ingredient" else "recipe"
            stock = self.one(f"SELECT stock_qty FROM {table} WHERE id=?", (line["component_id"],))
            required = line["qty"] * multiplier
            requirements.append(
                {
                    "name": line["component_name"],
                    "kind": line["component_kind"],
                    "component_id": line["component_id"],
                    "required": required,
                    "unit": line["unit"],
                    "stock": stock["stock_qty"],
                    "unit_cost": line.get("unit_cost")
                    or self.unit_cost(line["component_kind"], line["component_id"]),
                    "missing": max(0.0, required - stock["stock_qty"]),
                }
            )
        return {
            "requirements": requirements,
            "ok": bool(requirements) and all(r["missing"] == 0 for r in requirements),
        }

    def produce_batch(self, recipe_id: int, multiplier: float, notes: str = "") -> dict:
        if multiplier <= 0:
            raise ValueError("multiplier must be positive")
        recipe = self.one("SELECT * FROM recipe WHERE id=?", (recipe_id,))
        if recipe is None:
            raise FileNotFoundError(f"no recipe {recipe_id}")
        check = self.producibility(recipe_id, multiplier)
        if not check["ok"]:
            check.update(recipe=recipe, produced_qty=0.0)
            return check
        produced_qty = recipe["yield_qty"] * multiplier
        cost = self.batch_cost(recipe_id) * multiplier
        conn = self.connection
        try:
            cur = conn.execute(
                "INSERT INTO batch (recipe_id, multiplier, produced_qty, cost_snapshot, notes)"
                " VALUES (?, ?, ?, ?, ?)",
                (recipe_id, multiplier, produced_qty, cost, notes),
            )
            batch_id = cur.lastrowid
            for req in check["requirements"]:
                table = "ingredient" if req["kind"] == "ingredient" else "recipe"
                conn.execute(
                    f"UPDATE {table} SET stock_qty = stock_qty - ? WHERE id=?",
                    (req["required"], req["component_id"]),
                )
                conn.execute(
                    "INSERT INTO batch_consumption"
                    " (batch_id, component_kind, component_id, qty_used, unit_cost_snapshot)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (batch_id, req["kind"], req["component_id"], req["required"], req["unit_cost"]),
                )
            conn.execute(
                "UPDATE recipe SET stock_qty = stock_qty + ? WHERE id=?",
                (produced_qty, recipe_id),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        check.update(
            recipe=self.one("SELECT * FROM recipe WHERE id=?", (recipe_id,)),
            batch_id=batch_id,
            produced_qty=produced_qty,
            cost=cost,
        )
        return check

    def list_batches(self, limit: int = 50) -> list[dict]:
        return self.query(
            """
            SELECT batch.*, recipe.name AS recipe_name, recipe.yield_unit AS unit
            FROM batch JOIN recipe ON recipe.id = batch.recipe_id
            ORDER BY batch.id DESC LIMIT ?
            """,
            (limit,),
        )

    # -- dashboard ---------------------------------------------------------------

    def dashboard_data(self) -> dict:
        totals = self.one(
            """
            SELECT (SELECT COUNT(*) FROM ingredient) AS ingredients,
                   (SELECT COUNT(*) FROM recipe) AS recipes,
                   (SELECT COUNT(*) FROM batch) AS batches,
                   (SELECT COALESCE(SUM(stock_qty * cost_per_unit), 0) FROM ingredient) AS stock_value
            """
        )
        low_stock = self.query(
            "SELECT * FROM ingredient WHERE stock_qty <= reorder_level ORDER BY stock_qty / MAX(reorder_level, 0.0001)"
        )
        return {"totals": totals, "low_stock": low_stock, "recent_batches": self.list_batches(8)}

    # -- seed data -----------------------------------------------------------------

    @staticmethod
    def _seed(conn: sqlite3.Connection) -> None:
        ingredients = [
            # name, unit, cost_per_unit, stock, reorder, category
            ("White cane sugar", "g", 0.0018, 5000, 1000, "sweetener"),
            ("Demerara sugar", "g", 0.0032, 2000, 500, "sweetener"),
            ("Distilled water", "ml", 0.0005, 20000, 5000, "base"),
            ("Neutral alcohol 96°", "ml", 0.0120, 3000, 1000, "alcohol"),
            ("Gentian root", "g", 0.0550, 200, 50, "botanical"),
            ("Cinchona bark", "g", 0.0480, 150, 40, "botanical"),
            ("Bitter orange peel", "g", 0.0380, 300, 80, "botanical"),
            ("Almonds", "g", 0.0140, 1500, 400, "nut"),
            ("Orange blossom water", "ml", 0.0200, 100, 150, "aroma"),
            ("Citric acid", "g", 0.0090, 500, 100, "acid"),
            ("Fresh lime", "pcs", 0.5000, 24, 12, "fresh"),
            ("Bottle 700 ml", "pcs", 0.8500, 40, 12, "packaging"),
            ("Bottle 250 ml", "pcs", 0.4500, 60, 20, "packaging"),
            ("Label", "pcs", 0.1200, 200, 50, "packaging"),
        ]
        conn.executemany(
            "INSERT INTO ingredient (name, unit, cost_per_unit, stock_qty, reorder_level, category)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            ingredients,
        )
        recipes = [
            # name, kind, yield_qty, yield_unit, stock
            ("Rich syrup 2:1", "intermediate", 1300, "ml", 1500),
            ("Orgeat syrup 250 ml", "finished", 4, "pcs", 6),
            ("Bitter Rosso 700 ml", "finished", 2, "pcs", 3),
            ("Citrus cordial 250 ml", "finished", 3, "pcs", 0),
        ]
        conn.executemany(
            "INSERT INTO recipe (name, kind, yield_qty, yield_unit, stock_qty) VALUES (?, ?, ?, ?, ?)",
            recipes,
        )
        ing = {row[0]: idx + 1 for idx, row in enumerate(ingredients)}
        rec = {row[0]: idx + 1 for idx, row in enumerate(recipes)}
        lines = [
            # recipe, kind, component id, qty, unit
            (rec["Rich syrup 2:1"], "ingredient", ing["White cane sugar"], 1000, "g"),
            (rec["Rich syrup 2:1"], "ingredient", ing["Distilled water"], 500, "ml"),
            (rec["Orgeat syrup 250 ml"], "ingredient", ing["Almonds"], 300, "g"),
            (rec["Orgeat syrup 250 ml"], "ingredient", ing["White cane sugar"], 450, "g"),
            (rec["Orgeat syrup 250 ml"], "ingredient", ing["Distilled water"], 400, "ml"),
            (rec["Orgeat syrup 250 ml"], "ingredient", ing["Orange blossom water"], 10, "ml"),
            (rec["Orgeat syrup 250 ml"], "ingredient", ing["Bottle 250 ml"], 4, "pcs"),
            (rec["Orgeat syrup 250 ml"], "ingredient", ing["Label"], 4, "pcs"),
            (rec["Bitter Rosso 700 ml"], "ingredient", ing["Neutral alcohol 96°"], 400, "ml"),
            (rec["Bitter Rosso 700 ml"], "ingredient", ing["Distilled water"], 250, "ml"),
            (rec["Bitter Rosso 700 ml"], "ingredient", ing["Gentian root"], 25, "g"),
            (rec["Bitter Rosso 700 ml"], "ingredient", ing["Cinchona bark"], 15, "g"),
            (rec["Bitter Rosso 700 ml"], "ingredient", ing["Bitter orange peel"], 30, "g"),
            (rec["Bitter Rosso 700 ml"], "recipe", rec["Rich syrup 2:1"], 200, "ml"),
            (rec["Bitter Rosso 700 ml"], "ingredient", ing["Citric acid"], 5, "g"),
            (rec["Bitter Rosso 700 ml"], "ingredient", ing["Bottle 700 ml"], 2, "pcs"),
            (rec["Bitter Rosso 700 ml"], "ingredient", ing["Label"], 2, "pcs"),
            (rec["Citrus cordial 250 ml"], "ingredient", ing["Fresh lime"], 6, "pcs"),
            (rec["Citrus cordial 250 ml"], "ingredient", ing["White cane sugar"], 300, "g"),
            (rec["Citrus cordial 250 ml"], "ingredient", ing["Distilled water"], 350, "ml"),
            (rec["Citrus cordial 250 ml"], "ingredient", ing["Citric acid"], 12, "g"),
            (rec["Citrus cordial 250 ml"], "ingredient", ing["Bottle 250 ml"], 3, "pcs"),
            (rec["Citrus cordial 250 ml"], "ingredient", ing["Label"], 3, "pcs"),
        ]
        conn.executemany(
            "INSERT INTO bom_line (recipe_id, component_kind, component_id, qty, unit, position)"
            " VALUES (?, ?, ?, ?, ?, 0)",
            lines,
        )
        conn.execute(
            "INSERT INTO batch (recipe_id, multiplier, produced_qty, cost_snapshot, notes)"
            " VALUES (?, 1.0, 1300, 2.05, 'seed batch')",
            (rec["Rich syrup 2:1"],),
        )
