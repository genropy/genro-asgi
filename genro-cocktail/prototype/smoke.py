"""End-to-end smoke test for the prototype — no network, no pytest needed.

Boots the configured AsgiServer and drives it through httpx's ASGI transport:
every page, the HTMX fragments, a form POST (with percent-encoded values, the
case that exercises the form-decoding workaround), BOM editing including the
cycle guard, and a full production round-trip.

Run from this directory:  python smoke.py
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.environ["GENRO_COCKTAIL_DB"] = os.path.join(tempfile.mkdtemp(), "smoke.db")

import httpx  # noqa: E402  (a genro-asgi dependency)

from genro_asgi import AsgiServer  # noqa: E402


def check(condition, label):
    if not condition:
        raise SystemExit(f"FAIL: {label}")
    print(f"  ok: {label}")


async def main():
    server = AsgiServer(config=str(Path(__file__).parent / "config.py"))
    transport = httpx.ASGITransport(app=server)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:

        r = await client.get("/")
        check(r.status_code == 200 and "Production dashboard" in r.text, "dashboard renders")
        check("&lt;" not in r.text.split("<title>")[0], "no stray escaping in shell")

        r = await client.get("/static/styles.css")
        check(r.status_code == 200 and "text/css" in r.headers["content-type"], "static css served")

        r = await client.get("/static/../app.py")
        check(r.status_code == 404, "traversal guarded")

        r = await client.get("/ingredients")
        check(r.status_code == 200 and "Gentian root" in r.text, "ingredients page")

        r = await client.get("/ingredients_table", params={"q": "sugar"})
        check("Demerara sugar" in r.text and "Gentian" not in r.text, "search fragment filters")

        # form POST with characters that need URL-decoding
        r = await client.post(
            "/ingredient_add",
            data={
                "name": "Angostura bark & spice",
                "unit": "g",
                "category": "botanical",
                "cost_per_unit": "0.07",
                "stock_qty": "120",
                "reorder_level": "30",
            },
        )
        check(r.status_code == 200 and "Angostura bark &amp; spice" in r.text,
              "form POST decoded and escaped")

        r = await client.get("/ingredient_add")
        check(r.status_code == 400, "GET on mutating route refused")

        r = await client.get("/recipes")
        check("Bitter Rosso 700 ml" in r.text and "unit cost" in r.text, "recipes page with costs")

        r = await client.get("/recipe/3")
        check(r.status_code == 200 and "Rich syrup 2:1" in r.text and "sub-recipe" in r.text,
              "recipe detail shows the multi-level BOM")

        # cost rollup sanity: rich syrup batch = 1000g sugar*0.0018 + 500ml water*0.0005 = 2.05
        r = await client.get("/recipe_stats", params={"recipe_id": 1})
        check("€ 2.05" in r.text, "cost rollup (rich syrup batch = € 2.05)")

        # cycle guard: rich syrup (1) may not contain bitter rosso (3), which contains it
        r = await client.post("/line_add", data={"recipe_id": "1", "component": "recipe:3", "qty": "10"})
        check(r.status_code == 400, "cycle guard refuses recursive BOM")

        # produce one batch of Bitter Rosso, stock allows it
        r = await client.post("/produce", data={"recipe_id": "3", "multiplier": "1"})
        check(r.status_code == 200 and "produced" in r.text.lower(), "batch produced")
        check(r.headers.get("hx-trigger") == "batchProduced", "HX-Trigger emitted")

        # an absurd multiplier must be refused with the shortfall list
        r = await client.post("/produce", data={"recipe_id": "3", "multiplier": "100"})
        check("Not enough stock" in r.text, "shortfall refused with missing list")

        r = await client.get("/batches")
        check("Bitter Rosso 700 ml" in r.text, "batch log shows the run")

        r = await client.get("/nowhere")
        check(r.status_code == 404, "unknown path is 404")

    print("ALL SMOKE CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
