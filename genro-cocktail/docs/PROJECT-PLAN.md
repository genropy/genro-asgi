# genro-cocktail — project plan

The project has **three souls**, and every milestone serves at least one:

1. **A game** — few things, done with a smile (DOMAIN.md).
2. **A showcase** — what the new Genropy stack can do, for Nexus and beyond.
3. **A laboratory** — the first real consumer of the new pieces: a live,
   instrumented app Giovanni can tune against and measure with. Where the
   framework has provisional edges (the `spa/` pool above all), this project
   supplies the evidence: real traffic, real state, real numbers.

From this seed kit to that, in milestones sized for evenings. Each ends
runnable; each teaches one layer of the stack. The game milestones (M*) and
the laboratory track (L*) can interleave freely.

---

## M0 — Repo birth (½ day)

- Create `genropy/genro-cocktail` (Pre-Alpha, parent policies from
  meta-genro-modules: English only, no co-author lines, CLAUDE.md pointing at
  the parent).
- Lift `prototype/` → `src/genro_cocktail/`, `docs/` → `docs/`; add
  `pyproject.toml` (deps: `genro-asgi>=0.28,<0.29`, `websockets`), console
  entry `genro-cocktail = genro_cocktail.serve:main`.
- Port `smoke.py` into `tests/` as pytest (its ASGI-level websocket driver
  comes along unchanged).
- **Learning target**: the deployment unit; why the launcher is ours
  (server subclass = the websocket motor, FEASIBILITY §5).

## M1 — Social login for real (1 day)

- Create the Google OAuth client, wire the env vars, exercise the full
  round trip (start → consent → callback → avatar attached, session id
  unchanged).
- "Adopt my anonymous mixes" at login: one UPDATE moving `anon:<session>`
  creations to `user:<identity>` — D24 makes this trivial since the session
  survives the login.
- Decide Apple: the ES256-JWT client_secret resolver (needs the paid dev
  account) or park it visibly on the login page ("soon").
- **Learning target**: the auth subsystem end to end (OIDC method, avatar,
  challenge redirect).

## M2 — The lab gets lush (2–3 days)

- Slider polish: per-category slider colors, snap points at classic doses,
  a "reset to the classic" button on forks.
- Taste radar: the tags become a computed flavour hint (bitter share, sweet
  share, citrus share from ingredient categories) drawn as a tiny inline SVG
  via genro-builders' `svg` dialect — no JS chart library.
- Extract the component library (`ui/components.py`) with `@component` /
  `iterate=` so cards and slider rows become reusable builders idioms.
- Empty states, playful 404/400 pages (styled, not the core's text/plain).
- **Learning target**: builders components and the svg dialect.

## M3 — The bar becomes social (1–2 days)

- Publish switch on your creations: published mixes appear in everyone's bar
  under "from the community" with the author's name.
- A "tonight's special" on the home: highest-rated or newest published mix.
- Simple thumbs-up (one per session/identity per cocktail).
- **Learning target**: ownership/query patterns, HTMX optimistic updates.

## M4 — Wow features (pick per demo audience)

- **MCP face**: swap the base to `McpOpenApiApplication`, mark read routes
  `channel_channels="mcp,rest"` — an AI agent can browse the bar and answer
  "mix me something bitter under €2". The demo that lands with a
  tech-curious owner.
- **Live bar**: the websocket already exists — broadcast "someone just
  forked the Negroni" toasts to everyone on the bar page.
- **Print card**: a cocktail as a beautiful A6 recipe card (builders → HTML →
  print CSS).

## M5 — Showcase packaging

- One-command demo (seeded db + server), README with screenshots, a
  10-minute demo script for the Nexus meeting: play a classic, fork it,
  slide it, sign in with Google, show it survived.

---

## The laboratory track — riding the user-sticky pool

The `spa/` subsystem (FEASIBILITY §7) is genro-asgi's distinguishing
strength and its least-consumed part: heavily tested from the inside,
never yet driven by a real application. This track makes genro-cocktail
that application — deliberately separate from the game milestones so an
unstable experiment never blocks the showcase.

### L1 — Single role, native seam (an evening, no infrastructure)

- Mount a trimmed cocktail app behind `SpaApplication(workers=0,
  local_worker=True)` — the whole pool machine, zero extra processes.
- Write the `UserStickyWorker` subclass with a native (non-WSGI)
  `serve_http` hosting our handlers, the way the e2e suite does it.
- **Output for Giovanni**: the first ASGI-shaped consumer of the hosted-app
  seam — concrete requirements for the post-WSGI `serve_http` form.

### L2 — Real processes, real users, real numbers

- `workers=2+`: sticky `sticky_cid` routing across true child processes;
  each user's bar living in their worker's memory (sqlite becomes the cold
  store, the register the hot one).
- A small load harness (a python driver simulating N users mixing at
  once) reading the commander's own observables: occupancy per component
  (memory/cpu/executor), placement decisions, rebalance and user-move
  events, recycle verdicts.
- **Output for Giovanni**: tuning evidence for the 14 `PROVISIONAL`
  constants (probe cadence, admission/reception thresholds, compaction
  margin, recycle horizon) against a workload that is not synthetic.

### L3 — The hard scenarios, on purpose

- Kill a worker mid-mix: does the user's next gesture land on a fresh one,
  does the dump/restore bring the register back, what does the browser see?
- A leaking worker (inject growth): watch evidence-based recycling succeed
  it; measure what the user notices (target: nothing).
- Version-switch a group under load (the blue/green primitive) with people
  mid-slider.
- **Output for Giovanni**: reproducible failure drills + the measured user
  impact of each — the material acceptance tests are made of.

Each L milestone feeds the upstream list below; L1's seam findings are the
biggest single item the framework can harvest from this project.

---

## Upstream contributions this project should produce

1. **genro-tytx**: the form-body URL-decoding bug (FEASIBILITY §3.1) — file
   with a failing test.
2. **genro-asgi**: propose promoting the `_request` injection into
   `RoutedApplication.bind_kwargs` (§3.2); docs fix for the "return a
   Response" claims (concepts.md, streaming.md); consider shipping a
   reference `on_websocket` cookbook page based on FEASIBILITY §5.
3. **genro-builders**: propose an `HtmxRenderer` (or `hx_*` kebab-casing) in
   `contrib/html` — 12 lines, makes the HTML dialect HTMX-idiomatic out of
   the box.

These are small, well-evidenced, and exactly the kind of feedback a first
consumer project exists to generate.
