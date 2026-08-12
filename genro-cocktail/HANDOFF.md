# HANDOFF — genro-cocktail

**Read this first.** This is the single entry point for whoever picks up the
work — a person or an orchestrated multi-agent workflow. Everything referenced
here lives in this directory; the branch is self-contained.

**Branch**: `claude/genro-cocktail-roadmap-ldcwgz` of `genropy/genro-asgi`
**State at handoff**: 2026-08-12, all work committed and pushed, prototype
smoke suite green (30 checks).

---

## 1. What this project is (the three intents + one destination)

**genro-cocktail** is a playful web app: the classic cocktails are lessons,
sliders bend them into your own remix, every number (ABV, cost, standard
drinks) answers live. It exists for four reasons, all of equal rank:

1. **A game** — few things, done with a smile. If a screen doesn't make you
   want to touch it, it's wrong. (Concept and rules: `docs/DOMAIN.md`.)
2. **A showcase** — proof of the new Genropy stack (genro-asgi +
   genro-builders + HTMX + websocket + OIDC) for Nexus Mixology and beyond.
3. **A laboratory** — the first real consumer the framework authors can
   measure against; the `spa/` user-sticky pool track lives here
   (`docs/PROJECT-PLAN.md`, L1–L3).
4. **A deployment target** *(added at handoff)* — the finished app must ship
   as a **Docker container, installable on Kubernetes**. This is a first for
   the new stack: the containerization/K8s work is itself showcase + lab
   material (see §5 and milestone M6).

### The didactic intent (explicit)

The owner is using this project to LEARN the stack by building. Every
workstream below names what it teaches. When executing, prefer the solution
that exposes the framework's own idiom over the clever shortcut — the code is
course material. Explain non-obvious framework behaviour in module docstrings
(the existing files show the register: see `prototype/serve.py`,
`prototype/db.py`).

| Layer | Where it's learned |
|---|---|
| genro-asgi core idioms (routing, `_request` seam, config recipes, resolvers) | `prototype/app.py`, `prototype/config.py`, `docs/FEASIBILITY.md` §3 |
| The `databases` seam + a real adapter | `prototype/db.py`, FEASIBILITY §4 |
| WebSocket on a server subclass (D16 extension gesture) | `prototype/serve.py`, FEASIBILITY §5 |
| genro-builders HTML dialect + HTMX pairing | `prototype/ui/`, FEASIBILITY §1–2 |
| OIDC social login | `prototype/config.py`, FEASIBILITY §6 |
| The spa/ user-sticky pool (when ready) | PROJECT-PLAN, laboratory track |
| Containers & Kubernetes on this stack | milestone M6 (§5 below) |

## 2. What exists and is DONE

- **Platform survey**: `docs/GENRO-ASGI-ROADMAP.md` — genro-asgi 0.28 mapped
  (what's mature, what's missing, known drifts). Basis for every technical bet.
- **Feasibility, all verified by running code**: `docs/FEASIBILITY.md` —
  HTMX+builders fit, the four core workarounds, sqlite adapter pattern,
  websocket subclass, OAuth (Google now, Apple parked), spa-pool assessment.
- **Concept**: `docs/DOMAIN.md` — three nouns, five rules (fork, autosave,
  biglietto sharing…), the formula, the three screens.
- **Plan**: `docs/PROJECT-PLAN.md` — M0–M6 + laboratory track L1–L3 + the
  upstream contributions this project owes the framework.
- **Design system, expert-reviewed**: `docs/design/ricettario.html` (open in
  a browser — it IS the spec: role map day/night, l'insegna, the biglietto,
  phone layouts, motion rules) + `docs/design/style-study.html` (the four
  directions pitch, historical) + `docs/design/STYLE-STUDY.md` (research
  notes). Reviewed by: an art-director pass, a mobile-UX/accessibility pass
  (WCAG-checked), and an external brand consultant (velvet-neon round).
- **Brand marks, final**: `docs/design/logo/` — red Spencerian script
  (display/small/notturno/mono cuts), GC stamp, simplified favicon, PNGs,
  and `LOGO.md` (min sizes, clear space, no-go zones).
- **Runnable prototype**: `prototype/` — the full game loop working with the
  OLD (v2 speakeasy) styling: bar, mixing lab with websocket live formula +
  autosave, fork/rename/delete with ownership, the shelf, OIDC config.
  `python smoke.py` = 30 end-to-end checks, no network needed.

## 3. What is DESIGNED but NOT yet built (the immediate backlog)

Ordered; each item names its teaching. This is the natural input for an
orchestrated multi-agent run.

- **W1 — The Ricettario restyle** *(builders components, CSS craft)*:
  implement `docs/design/ricettario.html` in the prototype — paper grain,
  ledger + leaders, ink-dot sliders (5 ml snap), stamps instead of emoji,
  the role map day/notturno (`prefers-color-scheme` + toggle), l'insegna
  (logo in masthead; one neon strike at night), sticky mobile stat strip,
  rubrica tabs, icon set as a builders component (`ui/icons.py`),
  HTMX settling animations. The design file's CSS is production-grade
  reference — lift it, don't reinvent it.
- **W2 — The biglietto** *(routing, tokens, Web Share API)*: share button →
  unguessable token URL → read-only recipe card → "Falla tua" fork CTA
  (DOMAIN rule 5; mockup in the design spec).
- **W3 — Repo birth (M0)** *(packaging, deployment unit)*: lift `prototype/`
  into the new `genropy/genro-cocktail` repo per PROJECT-PLAN M0 (pyproject,
  `src/genro_cocktail/`, smoke.py → pytest, CI). Parent policies:
  meta-genro-modules (English only, no co-author lines, Pre-Alpha).
- **W4 — OAuth live (M1)** *(auth end-to-end)*: real Google client, adopt
  anonymous mixes at login (one UPDATE on `owner`), decide Apple.
- **W5 — Container & Kubernetes (M6, the new destination)**: see §5.
- **W6 — UX debts from the expert review**: dose value as tappable stepper,
  undo snackbar for pours, auto-fork on first slider touch of a classic,
  bottom-sheet ingredient picker (all specified in FEASIBILITY/review notes
  inside the design page).
- **W-lab — L1 when desired**: single-role spa pool experiment
  (PROJECT-PLAN laboratory track).

## 4. Known traps (learned the hard way — do not rediscover them)

1. **Form bodies are not URL-decoded** by genro-tytx (`from_qs`): the
   `bind_kwargs` override in `app.py` fixes it once. File the upstream issue
   (with failing test) — it's on the contributions list.
2. **`_request` injection** exists only on `ServerApplication` — every app
   copies the 5-line `bind_kwargs` idiom. Propose upstream promotion.
3. **No HTTP-method dispatch** — every mutating route needs the POST guard.
4. Handler exceptions other than `HTTPException` become hidden 500s — the
   `domain_errors()` context manager translates ValueError/FileNotFoundError.
5. **uvicorn needs `pip install websockets`** for the ws motor.
6. One `db_class` instance is shared across threads → connections thread-local,
   commit on the same thread (see `db.py` docstring).
7. The middleware chain is http-only: the websocket handshake reads the
   session cookie by hand (`cookie_value(scope, ...)`).
8. The server class is chosen at boot, never in config (D16) → the app ships
   its own launcher (`serve.py`), not `genro-asgi serve`.
9. TYTX types form/query values (`"123"` → int): annotate handler params.
10. Sage `#6e7a5f` fails WCAG on paper for small text — the role map's
    `#5d6852` is the floor. Contrast values live in the design spec.

## 5. The deployment destination: Docker + Kubernetes (M6)

Goal: `docker run` gives you the bar; a `kubectl apply` (or helm install)
gives you the bar in a cluster. Ship shape, honestly scoped:

**v1 topology — one replica, by design.** The app is a single ASGI process
(uvicorn inside `CocktailServer`); state is a sqlite file + in-memory
sessions. That maps cleanly to: `Deployment(replicas=1)` + PVC (RWO) for
`GENRO_COCKTAIL_DB` + `Service` + `Ingress` with websocket upgrade. This is
not a limitation to hide — it's the honest v1, and the framework agrees:
genro-asgi deliberately has no `--workers` (multi-process is an orchestrator
concern; in K8s the orchestrator is the cluster).

**Build tasks (W5):**
- `Dockerfile`: `python:3.12-slim`, non-root user, `pip install genro-asgi
  websockets`, copy the app, `CMD ["python", "serve.py"]`. Vendored htmx means
  no build step and no CDN at runtime.
- **Bind address/port from env**: today `config.py` hardcodes
  `127.0.0.1:8075` — switch to `EnvResolver("COCKTAIL_HOST", default=...)` /
  `COCKTAIL_PORT` (dtype `L`), default `0.0.0.0:8075` in the container.
  The config recipe is already resolver-based — this is the 12-factor story
  the config layer was built for (didactic point).
- `docker-compose.yml` for local parity (volume for the db, env for OAuth).
- K8s manifests (plain YAML first, helm later): Deployment (liveness =
  readiness = `GET /` 200; verify `/_server/index` as a lighter probe),
  resources, `securityContext` (runAsNonRoot, readOnlyRootFilesystem except
  the db volume), PVC, Service, Ingress (annotations for ws timeouts),
  Secret for `GOOGLE_CLIENT_ID/SECRET`, `COCKTAIL_EXTERNAL_URL` from the
  Ingress host (OIDC callbacks need it).
- CI: build + smoke inside the container (`python smoke.py` needs no network
  — it was built for this).

**v2 scaling path (documented, not built):** >1 replica requires the sqlite →
PostgreSQL adapter swap behind the same `databases` seam, a shared session
store backend, and ws fan-out — OR the spa/ user-sticky pool, which is the
framework's own answer to per-user state and would make genro-cocktail's K8s
story converge with the laboratory track. Decide then, not now.

## 6. How to restart the work (the superworkflow brief)

From a fresh machine/session:

```bash
git clone https://github.com/genropy/genro-asgi -b claude/genro-cocktail-roadmap-ldcwgz
cd genro-asgi/genro-cocktail
pip install genro-asgi websockets
(cd prototype && python smoke.py)     # must print: ALL SMOKE CHECKS PASSED
open docs/design/ricettario.html      # the visual spec, in a browser
```

Then brief the orchestrator with, in this order: this file → `docs/DOMAIN.md`
→ `docs/design/ricettario.html` → `docs/PROJECT-PLAN.md`. Suggested opening
prompt for the workflow:

> Read genro-cocktail/HANDOFF.md and the docs it references. Execute W1
> (Ricettario restyle) and W2 (biglietto) against the prototype, keeping
> smoke.py green and extending it for every new behaviour; then W3 (repo
> birth) and W5 (Docker + Kubernetes). Screenshot each screen desktop and
> mobile, day and notturno, and verify against docs/design/ricettario.html
> before calling a workstream done. Respect §4 (known traps) and the
> didactic register: framework-idiomatic solutions, documented seams.

Definition of done for the whole handoff: the game runs styled as the spec,
shareable, signed-in with Google, `docker run`-nable, `kubectl apply`-able —
and every screen would make the owner of a cocktail bar smile.
