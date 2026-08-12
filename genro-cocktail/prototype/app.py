"""genro-cocktail — the application.

A plain ``RoutedApplication`` mounted at the site root. Handlers return HTML
built by ``ui.pages``; HTMX turns fragment endpoints into interactivity; the
sliders talk to the ``/ws`` websocket (see ``serve.py``) for live stats and
autosave.

The base-class overrides at the top are the three genro-asgi idioms every
HTML app currently needs (see docs/FEASIBILITY.md §3):

- ``_request`` injection (the core ships it only on ``ServerApplication``);
- URL-decoding of form bodies (genro-tytx's ``from_qs`` skips percent
  decoding — upstream bug, worked around here in one place);
- an explicit POST guard, since routes have no HTTP-method dispatch.

Identity is playful-lazy: your creations belong to your OIDC identity when
you are signed in, to your anonymous session otherwise. ``mix_owner`` is that
one rule, shared with the websocket side.
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


def mix_owner(session, avatar) -> str:
    """Who owns what you mix: your login if you have one, your session if not."""
    if avatar is not None:
        return f"user:{avatar.identity}"
    if session is not None:
        return f"anon:{session.id}"
    return ""


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

    @staticmethod
    def _ctx(_request) -> dict:
        session = _request.session if _request else None
        avatar = _request.avatar() if _request else None
        return {
            "user": avatar.identity if avatar else None,
            "session_id": session.id if session else "",
            "owner": mix_owner(session, avatar),
        }

    # -- static assets -------------------------------------------------------

    @route()
    def static(self, *parts):
        target = ASSETS.joinpath(*parts).resolve()
        if not target.is_file() or ASSETS.resolve() not in target.parents:
            raise HTTPNotFound("no such asset")
        media = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        return self.result_wrapper(target, media_type=media)

    # -- the bar ---------------------------------------------------------------

    @route(media_type="text/html")
    def index(self, tag: str = "", _request=None) -> str:
        ctx = self._ctx(_request)
        return pages.bar_page(
            self.db.list_cocktails(owner=ctx["owner"], tag=str(tag)),
            self.db.all_tags(), str(tag), ctx,
        )

    @route(media_type="text/html")
    def bar_grid(self, tag: str = "", q: str = "", _request=None) -> str:
        ctx = self._ctx(_request)
        return pages.bar_grid_fragment(
            self.db.list_cocktails(owner=ctx["owner"], tag=str(tag), q=str(q))
        )

    @route(media_type="text/html")
    def new_cocktail(self, name: str = "", _request=None) -> str:
        self._require_post(_request)
        ctx = self._ctx(_request)
        with domain_errors():
            new_id = self.db.create_cocktail(ctx["owner"], str(name))
        _request.response.set_header("HX-Redirect", f"/cocktail/{new_id}")
        return ""

    @route(media_type="text/html")
    def fork(self, cocktail_id: int = 0, _request=None) -> str:
        self._require_post(_request)
        ctx = self._ctx(_request)
        with domain_errors():
            new_id = self.db.fork_cocktail(cocktail_id, ctx["owner"])
        _request.response.set_header("HX-Redirect", f"/cocktail/{new_id}")
        return ""

    # -- the mixing lab -----------------------------------------------------------

    @route(media_type="text/html")
    def cocktail(self, *parts, _request=None) -> str:
        if not parts:
            raise HTTPNotFound("which cocktail?")
        ctx = self._ctx(_request)
        with domain_errors():
            detail = self.db.cocktail_detail(int(parts[0]))
        owned = self.db.owns(detail["cocktail"]["id"], ctx["owner"])
        return pages.cocktail_page(detail, owned, ctx)

    @route(media_type="text/html")
    def update_meta(
        self, cocktail_id: int = 0, name: str = "", tags: str = "", emoji: str = "",
        _request=None,
    ) -> str:
        self._require_post(_request)
        ctx = self._ctx(_request)
        with domain_errors():
            self.db.update_meta(cocktail_id, ctx["owner"], str(name), str(tags), str(emoji))
        _request.response.set_header("HX-Refresh", "true")
        return ""

    @route(media_type="text/html")
    def delete_cocktail(self, cocktail_id: int = 0, _request=None) -> str:
        self._require_post(_request)
        ctx = self._ctx(_request)
        with domain_errors():
            self.db.delete_cocktail(cocktail_id, ctx["owner"])
        _request.response.set_header("HX-Redirect", "/")
        return ""

    @route(media_type="text/html")
    def line_add(self, cocktail_id: int = 0, ingredient_id: int = 0, _request=None) -> str:
        self._require_post(_request)
        ctx = self._ctx(_request)
        if not self.db.owns(cocktail_id, ctx["owner"]):
            raise HTTPBadRequest("not yours — fork it first")
        with domain_errors():
            self.db.set_qtys(cocktail_id, ctx["owner"], {int(ingredient_id): 30.0})
            detail = self.db.cocktail_detail(cocktail_id)
        return pages.mixer_fragment(detail, owned=True)

    @route(media_type="text/html")
    def line_remove(self, cocktail_id: int = 0, ingredient_id: int = 0, _request=None) -> str:
        self._require_post(_request)
        ctx = self._ctx(_request)
        if not self.db.owns(cocktail_id, ctx["owner"]):
            raise HTTPBadRequest("not yours — fork it first")
        with domain_errors():
            self.db.set_qtys(cocktail_id, ctx["owner"], {int(ingredient_id): 0.0})
            detail = self.db.cocktail_detail(cocktail_id)
        return pages.mixer_fragment(detail, owned=True)

    # -- the shelf ---------------------------------------------------------------

    @route(media_type="text/html")
    def ingredients(self, _request=None) -> str:
        return pages.ingredients_page(self.db.list_ingredients(), self._ctx(_request))

    @route(media_type="text/html")
    def shelf_grid(self, q: str = "") -> str:
        return pages.shelf_grid_fragment(self.db.list_ingredients(str(q)), str(q))

    @route(media_type="text/html")
    def ingredient_add(
        self,
        name: str = "",
        emoji: str = "",
        category: str = "",
        abv: float = 0.0,
        cost_per_ml: float = 0.0,
        _request=None,
    ) -> str:
        self._require_post(_request)
        if not str(name).strip():
            raise HTTPBadRequest("name is required")
        with domain_errors():
            self.db.add_ingredient(str(name).strip(), str(emoji), abv, cost_per_ml, category)
        return pages.shelf_grid_fragment(self.db.list_ingredients(), "")
