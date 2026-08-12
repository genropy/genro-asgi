# Style study — four art directions

**Deliverable**: `style-study.html` (open in a browser) — palette, icon voice,
type & motion notes, and mockups of the two key screens (the bar, the mixing
lab) for each direction. This note records the research behind it and what is
reusable regardless of the chosen direction.

## The four directions

| | Name | One line | Risk |
|---|---|---|---|
| A | **Deco d'Oro** | the speakeasy taken seriously: charcoal + champagne gold, engraved icons, serif titling | lowest — evolution of the running prototype |
| B | **Neon Notturno** | ink-blue night, glass cards, glowing monospaced numbers — the live websocket numbers are the hero | low-mid |
| C | **Ricettario** | a printed liquorista's ledger that happens to be alive: paper, ink hairlines, dotted leaders, red spent only on numbers | mid — most distinctive in screenshots |
| D | **Fluo Pop** | sticker cards, fat outlines, candy palette, bouncy motion — the toy, unapologetically | highest — strongest first smile |

Mixes are legitimate (C's paper + A's gold; B's number treatment in A's room;
D's motion on B's palette).

## What is direction-independent (build once)

- **The SVG icon set** — one hand-drawn set of `<symbol>`s (coupe, shaker,
  highball, citrus, cherry, bottle), geometric strokes, restyled per direction
  purely via `stroke`/`stroke-width`/`filter`. Lives in the study file;
  production version becomes a genro-builders component (`ui/icons.py`)
  emitting `<use href="#i-...">`.
- **The screen grammar** — nav / hero / chip row / card grid / stats strip /
  slider rows / save-state line. All four mockups share the same skeleton
  with different skins: the builders page functions we already have map 1:1.
- **Numbers as instruments** — `font-variant-numeric: tabular-nums` on every
  stat and dose label, whatever the direction.

## HTMX polish techniques (researched, apply to any direction)

1. **Stable-id settling**: keep the same `id` across a swap and htmx applies
   the new content in a way CSS transitions can animate — fragment updates
   crossfade instead of blinking.
2. **View Transitions API**: `hx-swap="... transition:true"` +
   `::view-transition-old/new` keyframes for page-level moves (bar → lab).
3. **Settling classes**: `.htmx-added` / `.htmx-settling` are the animation
   hooks for "new row bounces in" (D) or "stat pulses" (B) or "stamp inks
   in" (C).
4. **Indicators**: `hx-indicator` + a skeleton/shimmer on the target during
   the round trip, so filters feel instant even on slow links.
5. Respect `prefers-reduced-motion` everywhere; the websocket save-state line
   never animates (it's a status, not a show).

Production fonts (the app is not under the artifact CSP, so real webfonts are
fine there): A → Marcellus/Cormorant; B → a geometric sans + JetBrains Mono
for numbers; C → Fraunces/Lora; D → Baloo 2/Nunito 800. The mockups use
system stacks so they render faithfully anywhere.

## Sources consulted

- htmx animation model and settling: htmx.org examples/animations and the
  view-transitions essay (bigskysoftware/htmx).
- Cocktail/bar visual trends: 99designs cocktail design gallery, Sip The
  Style on 2025 art-deco bar design, Kreafolk cocktail illustration roundup.
