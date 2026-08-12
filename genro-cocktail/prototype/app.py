"""genro-cocktail — the application.

A plain ``RoutedApplication`` mounted at the site root. Handlers return HTML
built by ``ui.pages``; HTMX turns fragment endpoints into interactivity.

The base-class overrides at the top are the three genro-asgi idioms every
HTML app currently needs (see docs/FEASIBILITY.md §3):

- ``_request`` injection (the core ships it only on ``ServerApplication``);
- URL-decoding of form bodies (genro-tytx's ``from_qs`` skips percent
  decoding — upstream bug, worked around here in one place);
- an explicit POST guard, since routes have no HTTP-method dispatch.
"""

from __future__ import annotations

import mimetypes
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import unquote_plus

from genro_asgi import HTTPBadRequest, HTTPNotFound, RoutedApplication
from genro_routes import route

from ui import pages

ASSETS = Path(__file__).parent / "assets"


@contextmanager
def domain_errors():
    """Translate domain exceptions into HTTP answers.

    Only ``HTTPException`` subclasses carry a status through the error
    middleware — anything else is a hidden 500. The repository speaks
    ``ValueError`` (a refused command) and ``FileNotFoundError`` (no such
    record); this seam is where they become 400 and 404.
    """
    try:
        yield
    except ValueError as exc:
        raise HTTPBadRequest(str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPNotFound(str(exc)) from exc


class CocktailApp(RoutedApplication):
    mount = ""

    # -- genro-asgi idioms -------------------------------------------------

    def bind_kwargs(self, node, request):
        kwargs = super().bind_kwargs(node, request)
        fields = node.params.get("fields") or []
        if any(field["name"] == "_request" for field in fields):
            kwargs["_request"] = request
        content_type = request.headers.get("content-type") or ""
        if "application/x-www-form-urlencoded" in content_type:
            for key, value in kwargs.items():
                if isinstance(value, str):
                    kwargs[key] = unquote_plus(value)
        return kwargs

    @staticmethod
    def _require_post(_request):
        if _request is None or _request.method != "POST":
            raise HTTPBadRequest("POST required")

    @property
    def db(self):
        return self.server.databases["default"]

    # -- static assets -------------------------------------------------------

    @route()
    def static(self, *parts):
        target = ASSETS.joinpath(*parts).resolve()
        if not target.is_file() or ASSETS.resolve() not in target.parents:
            raise HTTPNotFound("no such asset")
        media = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        return self.result_wrapper(target, media_type=media)

    # -- pages ---------------------------------------------------------------

    @route(media_type="text/html")
    def index(self) -> str:
        return pages.dashboard(self.db.dashboard_data())

    @route(media_type="text/html")
    def ingredients(self) -> str:
        return pages.ingredients_page(self.db.list_ingredients())

    @route(media_type="text/html")
    def recipes(self) -> str:
        return pages.recipes_page(self.db.list_recipes())

    @route(media_type="text/html")
    def recipe(self, *parts) -> str:
        if not parts:
            raise HTTPNotFound("which recipe?")
        with domain_errors():
            return pages.recipe_page(self.db.recipe_detail(int(parts[0])))

    @route(media_type="text/html")
    def batches(self) -> str:
        return pages.batches_page(self.db.list_batches())

    # -- HTMX fragments ---------------------------------------------------------

    @route(media_type="text/html")
    def ingredients_table(self, q: str = "") -> str:
        return pages.ingredients_table_fragment(self.db.list_ingredients(str(q)), str(q))

    @route(media_type="text/html")
    def ingredient_add(
        self,
        name: str = "",
        unit: str = "g",
        category: str = "",
        cost_per_unit: float = 0.0,
        stock_qty: float = 0.0,
        reorder_level: float = 0.0,
        _request=None,
    ) -> str:
        self._require_post(_request)
        if not str(name).strip():
            raise HTTPBadRequest("name is required")
        with domain_errors():
            self.db.add_ingredient(
                str(name).strip(), unit, cost_per_unit, stock_qty, reorder_level, category
            )
        return pages.ingredients_table_fragment(self.db.list_ingredients(), "")

    @route(media_type="text/html")
    def recipe_stats(self, recipe_id: int = 0) -> str:
        with domain_errors():
            return pages.recipe_stats_fragment(self.db.recipe_detail(recipe_id))

    @route(media_type="text/html")
    def bom(self, recipe_id: int = 0) -> str:
        with domain_errors():
            return pages.bom_fragment(self.db.recipe_detail(recipe_id))

    @route(media_type="text/html")
    def line_add(
        self, recipe_id: int = 0, component: str = "", qty: float = 0.0, _request=None
    ) -> str:
        self._require_post(_request)
        kind, _, component_id = str(component).partition(":")
        if not component_id:
            raise HTTPBadRequest("pick a component")
        with domain_errors():
            self.db.add_line(recipe_id, kind, int(component_id), qty)
            return pages.bom_fragment(self.db.recipe_detail(recipe_id))

    @route(media_type="text/html")
    def line_delete(self, line_id: int = 0, recipe_id: int = 0, _request=None) -> str:
        self._require_post(_request)
        with domain_errors():
            self.db.delete_line(line_id)
            return pages.bom_fragment(self.db.recipe_detail(recipe_id))

    @route(media_type="text/html")
    def produce(self, recipe_id: int = 0, multiplier: float = 1.0, _request=None) -> str:
        self._require_post(_request)
        with domain_errors():
            result = self.db.produce_batch(recipe_id, multiplier)
        if result["ok"]:
            # Anything on the page listening for this event refreshes itself
            # (the recipe stats strip does).
            _request.response.set_header("HX-Trigger", "batchProduced")
        return pages.produce_result_fragment(result)
