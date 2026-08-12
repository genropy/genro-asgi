# genro-cocktail — the concept

**One sentence**: a playful bar where the classics teach you how cocktails
work, and sliders let you bend them into something of your own.

Not a management tool. It does few things, and each one should raise a smile:
you look at the bar, you poke at a recipe, you fork it, you name it. The
depth is hidden in the numbers that follow every gesture — alcohol, cost,
volume — computed live, saved silently.

---

## 1. The three nouns

### 1.1 `ingredient` — a bottle on the shelf

| Field | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `name` | text, unique | "Campari" |
| `emoji` | text | its face everywhere in the UI 🔴 |
| `abv` | real | % alcohol by volume, 0–100 (validated) |
| `cost_per_ml` | real | €/ml |
| `category` | text | `spirit`, `bitter`, `juice`, `mixer`, … |

The shelf is public and shared: anyone can browse it and put new bottles on
it. It is the "database of elements" — every derived number in the app comes
from these two columns, `abv` and `cost_per_ml`.

### 1.2 `cocktail` — a recipe

| Field | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `name` | text | |
| `emoji` | text | the glass 🍸 |
| `owner` | text | `''` for classics; `user:<identity>` or `anon:<session>` |
| `is_classic` | bool | classics are read-only, forever |
| `tags` | text | comma-separated taste words: `bitter,sour,dry,sweet,fruity,fresh,strong` |
| `story` | text | one playful line of history (classics only) |

### 1.3 `cocktail_line` — what's in the glass

`(cocktail_id, ingredient_id, qty_ml)` — unique per pair. Quantities are
**ml, driven by sliders**, not typed.

## 2. The rules of the game

1. **Classics never change.** They are the lesson: play with their sliders
   all you want (the numbers answer), but nothing is written. The UI says it
   with a fork: *"a classic never changes — fork it to keep your version"*.
2. **Fork makes it yours.** A copy named "<name> remix" lands on your bar,
   fully editable: rename it, retag it, change its glass, pour it away.
3. **Ownership is lazy.** Signed in (OAuth/OIDC): your creations follow your
   identity. Anonymous: they belong to your session (a week of TTL). The rule
   is one function, `mix_owner`, shared by HTTP and websocket.
4. **Every slider move is saved** — if the mix is yours. No save button
   exists anywhere in the mixing lab.

## 3. The formula (what the sliders drive)

For a mix `{ingredient → ml}`:

```
volume     = Σ ml
pure_alcohol = Σ ml × abv/100
abv%       = 100 × pure_alcohol / volume
cost       = Σ ml × cost_per_ml
alcohol_g  = pure_alcohol × 0.789          (ethanol density)
drinks     = alcohol_g / 10                (WHO standard drink)
```

Computed server-side in one place (`CocktailDb.stats_for`) from the payload,
never from stored rows — so a classic being played with and a draft being
edited go through the same formula. The ABV meter fills toward 40% vol with
a green→amber→red gradient; "standard drinks" is the playful conscience
(*"Drink water too. 💧"*).

## 4. The screens (all three of them)

| Screen | What it does | The fun |
|---|---|---|
| **The bar** (`/`) | classics + your creations as cards; tag chips filter; a name box mixes a new one | every card wears its emoji, its taste tags, its strength and its pour cost |
| **The mixing lab** (`/cocktail/<id>`) | sliders per ingredient; live stats; add/remove bottles; rename/retag; fork; pour away | the numbers dance while you drag; "saved ✓" appears without you asking |
| **The shelf** (`/ingredients`) | every bottle with ABV and €/ml; search; add a bottle | the emoji picker is the only bureaucracy |

## 5. How the pieces move (the two wires)

- **HTMX** carries the discrete gestures: filter chips, fork, add/remove
  ingredient, rename, delete — fragment swaps and `HX-Redirect`.
- **The websocket** (`/ws`) carries the continuous gesture: slider positions
  stream up, `{stats, saved}` streams back. Autosave is a side effect of
  playing, debounced at 200 ms, resilient to bad frames and reconnecting
  with backoff.

## 6. Explicitly out (until the game asks for them)

Sharing/publishing your creations to other users, ratings, comments, photos,
glass-size presets, unit conversion (oz), inventory/stock (that was v1's
world), multi-language. Apple sign-in is designed but parked (see
FEASIBILITY §6: its client_secret is a rotating signed JWT, not a string).
