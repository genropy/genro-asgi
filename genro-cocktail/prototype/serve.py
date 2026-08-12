"""The launcher — and the websocket motor.

genro-asgi's core leaves ``on_websocket`` as an empty hook (SPECIFICATION D7 /
Q1: consume the connect, close 1000). Extension is subclassing (D16): the
server class says WHO you are, so the websocket behaviour lives on a server
subclass, chosen here at boot — never in config.

The protocol is one JSON message per slider gesture:

    client → {"cocktail_id": 7, "qtys": {"3": 45, "12": 20}}
    server → {"ok": true, "saved": true, "stats": {volume, abv, cost, drinks}}

``saved`` is true only when the cocktail is yours — a classic computes but
never changes (fork it to keep your remix). Identity is the same rule the
HTTP side uses (``mix_owner``): the middleware chain is http-only, so the
session cookie is read from the handshake scope by hand.

Run:  python serve.py        (uvicorn needs the ``websockets`` package)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from genro_asgi import AsgiServer
from genro_asgi.middleware.base import cookie_value

from app import mix_owner


class CocktailServer(AsgiServer):
    """AsgiServer + the one capability the core does not ship: a websocket."""

    async def on_websocket(self, scope, receive, send) -> None:
        message = await receive()
        if message["type"] != "websocket.connect" or scope.get("path") != "/ws":
            await send({"type": "websocket.close", "code": 4004})
            return
        await send({"type": "websocket.accept"})
        owner = self._ws_owner(scope)
        db = self.databases["default"]
        while True:
            message = await receive()
            if message["type"] == "websocket.disconnect":
                return
            # Tiny sqlite lookups: fine on the loop for a prototype. Anything
            # heavier goes through self.run_sync, like sync HTTP handlers do.
            try:
                payload = json.loads(message.get("text") or "{}")
                cocktail_id = int(payload.get("cocktail_id") or 0)
                qtys = {
                    int(ingredient_id): max(0.0, float(qty))
                    for ingredient_id, qty in (payload.get("qtys") or {}).items()
                }
                saved = db.set_qtys(cocktail_id, owner, qtys) if cocktail_id else False
                stats = db.stats_for({k: v for k, v in qtys.items() if v > 0})
                reply = {"ok": True, "saved": saved, "stats": stats}
            except Exception as exc:  # a bad frame must not kill the socket
                reply = {"ok": False, "error": str(exc)}
            await send({"type": "websocket.send", "text": json.dumps(reply)})

    def _ws_owner(self, scope) -> str:
        session_id = cookie_value(scope, "session_id")
        session = self.session_store.get(session_id) if session_id else None
        avatar = session.avatar() if session is not None else None
        return mix_owner(session, avatar)


if __name__ == "__main__":
    from config import ServerConfiguration

    CocktailServer(config=ServerConfiguration).serve()
