"""Deployment recipe for the genro-cocktail prototype.

Run with:  python serve.py
(the ``CocktailServer`` subclass carries the websocket motor, so the launcher
is ours — the generic ``genro-asgi serve config.py`` would serve everything
except ``/ws``.)

Environment knobs, all optional:

- ``GENRO_COCKTAIL_DB``      sqlite path (default ``cocktail.db``)
- ``COCKTAIL_EXTERNAL_URL``  the public base URL (needed by OAuth callbacks)
- ``GOOGLE_CLIENT_ID`` / ``GOOGLE_CLIENT_SECRET``
      arm "Sign in with Google" (OIDC, authorization-code + PKCE). Register
      ``<external_url>/_server/auth/oidc:google/callback`` as the redirect
      URI in the Google console. Without these the app still runs — your
      mixes simply belong to the anonymous session.

Apple note: "Sign in with Apple" is OIDC too, but its client_secret must be
a short-lived ES256-signed JWT, not a static string — feed it through a
resolver that mints/rotates the JWT (a later milestone; see FEASIBILITY §6).
"""

import os

from genro_asgi.config import AsgiConfigBuilder
from genro_bag.resolvers import EnvResolver

from app import CocktailApp
from db import CocktailDb


class ServerConfiguration(AsgiConfigBuilder):
    """Genro Cocktail — the playful mixing lab (prototype)."""

    def main(self, root):
        cfg = root.configuration()
        cfg.server(
            host="127.0.0.1",
            port=8075,
            external_url=EnvResolver("COCKTAIL_EXTERNAL_URL", default="http://127.0.0.1:8075"),
        ).session(ttl=7 * 24 * 3600)  # a week: your unsaved bar keeps waiting for you
        cfg.applications(default="cocktail").application(
            code="cocktail", mount="", app_class=CocktailApp
        )
        cfg.databases().database(
            code="default",
            db_class=CocktailDb,
            path=EnvResolver("GENRO_COCKTAIL_DB", default="cocktail.db"),
        )
        self.authentication_section(cfg)

    def authentication_section(self, cfg):
        """Social login: one OIDC provider per identity source (D27).

        Providers are added only when their credentials are present, so the
        recipe boots anywhere; the login page builds itself from whatever
        methods are registered.
        """
        if os.environ.get("GOOGLE_CLIENT_ID"):
            auth = cfg.authentication()
            auth.oidc().provider(
                code="google",
                issuer="https://accounts.google.com",
                client_id=EnvResolver("GOOGLE_CLIENT_ID"),
                client_secret=EnvResolver("GOOGLE_CLIENT_SECRET"),
                identity_claim="email",
                tags="member",
            )
