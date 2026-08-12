"""End-to-end smoke test for the prototype — no network, no pytest needed.

Boots the real ``CocktailServer`` (the subclass with the websocket motor) and
drives it two ways:

- HTTP through httpx's ASGI transport: pages, HTMX fragments, form POSTs with
  percent-encoded values, fork/rename/delete ownership rules;
- the websocket by feeding ASGI messages straight to the server callable:
  live stats, autosave on an owned mix, no-save on a classic, bad frames.

Run from this directory:  python smoke.py
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.environ["GENRO_COCKTAIL_DB"] = os.path.join(tempfile.mkdtemp(), "smoke.db")
os.environ.pop("GOOGLE_CLIENT_ID", None)

import httpx  # noqa: E402  (a genro-asgi dependency)

from serve import CocktailServer  # noqa: E402
from config import ServerConfiguration  # noqa: E402


def check(condition, label):
    if not condition:
        raise SystemExit(f"FAIL: {label}")
    print(f"  ok: {label}")


async def ws_session(server, session_id, payloads):
    """Drive /ws at the ASGI level; returns the JSON replies."""
    inbox: asyncio.Queue = asyncio.Queue()
    replies = []
    headers = [(b"host", b"test")]
    if session_id:
        headers.append((b"cookie", f"session_id={session_id}".encode()))
    scope = {"type": "websocket", "path": "/ws", "headers": headers}
    await inbox.put({"type": "websocket.connect"})
    for payload in payloads:
        text = payload if isinstance(payload, str) else json.dumps(payload)
        await inbox.put({"type": "websocket.receive", "text": text})
    await inbox.put({"type": "websocket.disconnect"})

    async def receive():
        return await inbox.get()

    async def send(message):
        if message["type"] == "websocket.send":
            replies.append(json.loads(message["text"]))

    await server(scope, receive, send)
    return replies


async def main():
    server = CocktailServer(config=ServerConfiguration)
    transport = httpx.ASGITransport(app=server)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:

        # -- the bar -------------------------------------------------------
        r = await client.get("/")
        check(r.status_code == 200 and "Negroni" in r.text, "the bar renders the classics")
        check("Sign in" in r.text, "anonymous nav offers sign-in")

        r = await client.get("/bar_grid", params={"tag": "bitter"})
        check("Negroni" in r.text and "Daiquiri" not in r.text, "tag chip filters the grid")

        r = await client.get("/static/mixlab.js")
        check(r.status_code == 200 and "WebSocket" in r.text, "mixlab.js served")

        # -- a classic is read-only ----------------------------------------
        r = await client.get("/cocktail/1")
        check('data-editable="0"' in r.text and "Fork" in r.text,
              "classic shows sliders + fork invitation")

        r = await client.post("/update_meta",
                              data={"cocktail_id": "1", "name": "Hacked", "tags": ""})
        check(r.status_code == 400, "renaming a classic is refused")

        # -- fork and own ------------------------------------------------------
        r = await client.post("/fork", data={"cocktail_id": "1"})
        check(r.status_code == 200 and r.headers.get("hx-redirect", "").startswith("/cocktail/"),
              "fork redirects to the remix")
        fork_id = int(r.headers["hx-redirect"].rsplit("/", 1)[1])

        r = await client.get(f"/cocktail/{fork_id}")
        check("Negroni remix" in r.text and 'data-editable="1"' in r.text,
              "the remix is yours to edit")

        r = await client.post("/update_meta", data={
            "cocktail_id": str(fork_id),
            "name": "Negroni d'estate",       # apostrophe + space exercise the decode fix
            "tags": "bitter, Fresh",
            "emoji": "🌞",
        })
        check(r.status_code == 200 and r.headers.get("hx-refresh") == "true",
              "rename accepted with HX-Refresh")
        r = await client.get(f"/cocktail/{fork_id}")
        check("Negroni d'estate" in r.text,
              "apostrophe and space survive the form round-trip")
        check("fresh" in r.text, "tags normalized lowercase")

        # -- invent from scratch ------------------------------------------------
        r = await client.post("/new_cocktail", data={"name": "Lab #17"})
        new_id = int(r.headers["hx-redirect"].rsplit("/", 1)[1])
        r = await client.get(f"/cocktail/{new_id}")
        check("Lab #17" in r.text and "empty glass" in r.text.lower(),
              "new cocktail starts as an empty glass")

        r = await client.post("/line_add",
                              data={"cocktail_id": str(new_id), "ingredient_id": "1"})
        check('class="dose"' in r.text and "Gin" in r.text, "ingredient lands with a slider")

        # -- the websocket: live formula + autosave ------------------------------
        session_id = client.cookies.get("session_id")
        check(bool(session_id), "session cookie present for the ws handshake")

        negroni_mix = {"1": 30, "6": 30, "8": 30}  # gin, campari, sweet vermouth
        replies = await ws_session(server, session_id, [
            {"cocktail_id": fork_id, "qtys": negroni_mix},        # yours → saved
            {"cocktail_id": 1, "qtys": {"1": 60, "6": 30, "8": 30}},  # classic → play only
            "not even json{{{",                                    # must not kill the socket
            {"cocktail_id": fork_id, "qtys": {"1": 45, "6": 30, "8": 30}},
        ])
        check(len(replies) == 4, "one reply per ws frame")
        check(replies[0]["saved"] is True, "your mix autosaves over the websocket")
        stats = replies[0]["stats"]
        check(stats["volume"] == 90 and stats["abv"] == 27.0 and stats["cost"] == 1.62,
              "the formula: Negroni = 90 ml, 27% vol, € 1.62")
        check(stats["drinks"] == 1.9, "standard drinks computed")
        check(replies[1]["saved"] is False and replies[1]["stats"]["abv"] > 27,
              "a classic computes but never saves")
        check(replies[2]["ok"] is False, "a bad frame answers an error, socket survives")
        check(replies[3]["saved"] is True, "socket still saving after the bad frame")

        r = await client.get(f"/cocktail/{fork_id}")
        check("45 ml" in r.text, "the autosaved dose survives a page reload")

        # -- someone else cannot touch your mix ---------------------------------
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as intruder:
            r = await intruder.post("/delete_cocktail", data={"cocktail_id": str(fork_id)})
            check(r.status_code == 400, "an intruder cannot pour your mix away")
        stranger_replies = await ws_session(server, None, [
            {"cocktail_id": fork_id, "qtys": {"1": 999}},
        ])
        check(stranger_replies[0]["saved"] is False, "no cookie, no autosave")

        # -- the shelf ---------------------------------------------------------
        r = await client.get("/shelf_grid", params={"q": "gin"})
        check("Gin" in r.text and "Campari" not in r.text, "shelf search filters")
        r = await client.post("/ingredient_add", data={
            "name": "Elderflower cordial", "emoji": "🌼", "category": "sweet",
            "abv": "0", "cost_per_ml": "0.011",
        })
        check(r.status_code == 200 and "Elderflower" in r.text, "new bottle on the shelf")
        r = await client.post("/ingredient_add", data={
            "name": "Impossible spirit", "abv": "160", "cost_per_ml": "1",
        })
        check(r.status_code == 400, "ABV over 100 refused")

        # -- cleanup + auth surface ----------------------------------------------
        r = await client.post("/delete_cocktail", data={"cocktail_id": str(fork_id)})
        check(r.headers.get("hx-redirect") == "/", "pour-away redirects to the bar")
        r = await client.get(f"/cocktail/{fork_id}")
        check(r.status_code == 404, "poured away is gone")

        r = await client.get("/_server/login_methods")
        check(r.status_code == 200, "login surface answers (add OIDC creds to arm Google)")

    print("ALL SMOKE CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
