# genro-cocktail — project plan

From this seed kit to a polished showcase, in milestones sized for evenings.
Each milestone ends runnable; each teaches one layer of the stack (that is a
stated goal of the project: learning by building).

---

## M0 — Repo birth (½ day)

- Create `genropy/genro-cocktail` (Pre-Alpha, parent policies from
  meta-genro-modules: English only, no co-author lines, CLAUDE.md pointing at
  the parent).
- Lift `prototype/` → `src/genro_cocktail/`, `docs/` → `docs/`; add
  `pyproject.toml` (dep: `genro-asgi>=0.28,<0.29`), console entry
  `genro-cocktail = genro_cocktail.__main__:main` (thin wrapper over
  `genro-asgi serve`).
- Port the kit's smoke test into `tests/` (pytest, the throwaway-server
  pattern from genro-asgi's own suite: boot on port 0, drive the ASGI
  callable).
- **Learning target**: the genro-asgi CLI/config deployment unit.

## M1 — Data layer hardened (1–2 days)

- Split `db.py` into adapter (`SqliteDb`) + repository functions per entity;
  proper transactions on batch production; schema migrations as numbered SQL
  files applied at boot.
- Unit tests for: cost rollup (multi-level), cycle guard, producibility,
  batch transaction (including the refusal path).
- **Learning target**: the `databases` seam, thread-pool/loop discipline.

## M2 — UI complete (2–4 days)

- All six views of DOMAIN §4 built as genro-builders pages/fragments;
  extract the component library (`ui/components.py`: page shell, card, table,
  form row, badge, cost tree) — this becomes the reusable "genro-htmx" pattern
  collection.
- The dark showcase styling; empty states; error banners (styled, not the
  core's text/plain).
- **Learning target**: builders components (`@component`, `iterate=`,
  containers), HTMX patterns (swap strategies, `HX-Trigger` event bus,
  out-of-band swaps for the dashboard counters).

## M3 — Auth & polish (1–2 days)

- `admin_password=` + user store; `auth_rule` on mutating routes; the shipped
  login challenge flow (note: the login page needs the form-decoding fix
  upstream, or a custom login form in our UI — decide when we get there).
- Seed dataset worthy of a demo: ~25 ingredients, ~8 recipes including two
  intermediates (rich syrup, citrus stock), batch history.
- **Learning target**: auth/session subsystem end to end.

## M4 — Wow features (pick per demo audience)

- **SSE live dashboard**: stock ticks and batch events pushed over `SseStream`
  + the HTMX SSE extension (the pattern is in FEASIBILITY §5).
- **MCP face**: swap the base class to `McpOpenApiApplication`, mark read
  routes `channel_channels="mcp,rest"` — the BOM becomes queryable by an AI
  agent ("how much orgeat can we make right now?"). This is the demo that
  lands with a tech-curious owner.
- **Scheduled task**: nightly low-stock report via
  `@route(task="stock_report", task_cron="0 7 * * *")`.
- **Cost history chart**: tiny inline SVG via genro-builders' `svg` dialect —
  no JS chart library.

## M5 — Showcase packaging

- One-command demo (`genro-cocktail demo` → seeded db + server), README with
  screenshots, a 10-minute demo script for the Nexus meeting.

## Upstream contributions this project should produce

1. **genro-tytx**: the form-body URL-decoding bug (FEASIBILITY §3.1) — file
   with a failing test.
2. **genro-asgi**: propose promoting the `_request` injection into
   `RoutedApplication.bind_kwargs` (§3.2), and a docs fix for the
   "return a Response" claims (concepts.md, streaming.md).
3. **genro-builders**: propose an `HtmxRenderer` (or `hx_*` kebab-casing) in
   `contrib/html` — 12 lines, makes the HTML dialect HTMX-idiomatic out of
   the box.

These three are small, well-evidenced, and exactly the kind of feedback a
first consumer project exists to generate.
