# Genro Cocktail — brand marks

Two marks, one ledger: the **script** is the liquorista's signature (the
hand), the **stamp** is the shop's timbro (the office). A real Italian
account-book page is exactly this pair — a handwritten entry validated by a
stamp. Externally reviewed (brand consultant, 2026-08-12): pairing approved;
the fixes below are applied.

## Files

| File | What | Use |
|---|---|---|
| `genro-cocktail-logo.svg` | red script, display cut | hero sizes: masthead, biglietto, print |
| `genro-cocktail-logo-small.svg` | script with +stroke offset (hairlines thickened ~20%) | any rendering **under ~360 px wide** |
| `genro-cocktail-logo-notturno.svg` | script recolored `#c9584a`, small-cut stroke | dark grounds — never use `#a63329` on `#201c16` (2.5:1, fails) |
| `genro-cocktail-logo-mono.svg` | ink `#26221c` | one-color print |
| `genro-cocktail-stamp.svg` | GC rubber stamp, rotated −4°, double border | avatar, app icon 32 px+, UI stamp contexts |
| `genro-cocktail-stamp-mono.svg` | ink version | one-color |
| `genro-cocktail-favicon.svg` / `-64.png` | simplified cut: single border, no rotation, heavier GC | 16–32 px favicons (the double border smudges below 32 px) |
| `*-1200.png`, `-512.png` | raster renders on their grounds | previews, stores |

Typefaces (converted to paths — no font dependency): script **Great Vibes**,
stamp **Fraunces 600**.

## Rules

1. **Minimum size**: the script never renders below ~180 px width / 32 px
   x-height — below that the stamp takes over. Encode this in components,
   not in memory.
2. **Clear space**: the height of the script's "o" on all sides.
3. **Notturno**: script becomes `#c9584a`; no permanent glow in chrome. The
   glow exists only as *l'insegna* — the one neon-sign instance over the bar
   list at night (one 900 ms strike on mount, then steady; disabled under
   `prefers-reduced-motion`).
4. **No-go zones** (trademark hygiene — Spencerian script is a genre, not
   Coca-Cola's property, but): never white script on a solid red field;
   no ribbon/wave underline beneath the wordmark; no copy that winks at Coke.
5. The detached hairline curls on the capitals are Great Vibes' authentic
   calligraphic entry strokes — a chosen flourish, not clipping. Keep canvas
   padding generous so they never touch an edge.
6. The stamp's texture stays clean in the asset; ink-grain effects are
   applied in-context (CSS), matching the UI's stamp component.
