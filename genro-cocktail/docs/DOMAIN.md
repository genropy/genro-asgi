# genro-cocktail — domain model

**Scope**: bill-of-materials (BOM) management for a mixology production lab:
syrups, bitters, premixes, infusions, finished bottled products.

The model is deliberately small — six tables — but structurally honest: it has
the one property that makes a BOM domain interesting (recursive composition)
and the one workflow that makes it useful (batch production against stock).

---

## 1. Entities

### 1.1 `ingredient` — raw material

Something bought, not produced: sugar, citric acid, gentian root, 96° alcohol,
distilled water, orange peel, glass bottles, labels.

| Field | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `name` | text, unique | "Demerara sugar" |
| `unit` | text | canonical stock unit: `g`, `ml`, `pcs` |
| `cost_per_unit` | numeric | purchase cost per canonical unit |
| `stock_qty` | numeric | current stock in canonical unit |
| `reorder_level` | numeric | below this → low-stock warning |
| `category` | text | `sweetener`, `botanical`, `alcohol`, `acid`, `packaging`, … |
| `notes` | text | supplier, origin |

### 1.2 `recipe` — a produced item (the BOM header)

Anything the lab makes. A recipe may be a **finished product** (Bitter Rosso
700ml) or an **intermediate** (rich syrup base) used inside other recipes.

| Field | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `name` | text, unique | "Orgeat syrup" |
| `kind` | text | `finished` \| `intermediate` |
| `yield_qty` | numeric | what one batch produces… |
| `yield_unit` | text | …in this unit (`ml`, `pcs`) |
| `stock_qty` | numeric | stock of the produced item itself |
| `instructions` | text | method, free text |

### 1.3 `bom_line` — one row of a recipe's bill

| Field | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `recipe_id` | FK → recipe | the parent |
| `component_kind` | text | `ingredient` \| `recipe` |
| `component_id` | int | FK into the table named by `component_kind` |
| `qty` | numeric | per **one batch** of the parent (i.e. per `yield_qty`) |
| `unit` | text | must equal the component's canonical unit (v1 rule) |
| `position` | int | display order |

### 1.4 `batch` — a production run

| Field | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `recipe_id` | FK → recipe | |
| `multiplier` | numeric | 1.0 = one standard batch |
| `produced_qty` | numeric | `yield_qty × multiplier`, snapshotted |
| `cost_snapshot` | numeric | rolled-up cost at production time |
| `produced_at` | timestamp | |
| `notes` | text | lot code, operator |

`batch_consumption` (child of batch): `component_kind`, `component_id`,
`qty_used`, `unit_cost_snapshot` — the audit trail of what a run consumed.

## 2. Invariants

1. **No cycles**: a recipe may not contain itself, directly or transitively.
   Enforced at line insertion by walking the component subtree (depth cap 20).
2. **Unit coherence (v1)**: a BOM line's `unit` equals the component's
   canonical unit. Unit conversion (kg↔g, l↔ml) is a later refinement, kept
   out of v1 to keep arithmetic honest.
3. **Quantities are per one batch** of the parent recipe; scaling is done by
   the batch `multiplier`, never by editing lines.
4. **Deleting is guarded**: an ingredient/recipe referenced by a BOM line or a
   batch cannot be hard-deleted (v1: refuse; later: archive flag).
5. **Costs are snapshotted on production**: ingredient prices change; a
   batch records the cost that was true when it ran.

## 3. Derived values

### 3.1 Cost rollup (recursive)

```
unit_cost(ingredient) = cost_per_unit
batch_cost(recipe)    = Σ over bom_lines:
                          qty × unit_cost(component)
unit_cost(recipe)     = batch_cost(recipe) / yield_qty
```

Intermediates make this genuinely recursive: the cost of *Bitter Rosso*
includes the per-ml cost of *rich syrup base*, itself rolled up from sugar and
water. Displayed on the recipe page as a cost tree with per-line subtotals and
percentage weight.

### 3.2 Producibility

For a requested batch (recipe × multiplier), the **one-level explosion**
lists each line's required qty vs available stock → *can produce* /
*missing list*. (v1 consumes intermediates from their stock rather than
recursively producing them — matching real lab practice: you make the base
first, then the bitter.)

### 3.3 Producing a batch (the one transaction)

```
check: every line's required qty ≤ component stock  (else refuse, listing shortfalls)
in one transaction:
  decrement each component's stock by required qty
  write batch + batch_consumption rows (with cost snapshots)
  increment the recipe's stock_qty by produced_qty
```

## 4. UI surface (v1 showcase)

| View | Content | HTMX behaviour |
|---|---|---|
| **Dashboard** | stock health, low-stock list, recent batches, headline numbers | fragments refreshed on `HX-Trigger` events |
| **Ingredients** | searchable table, inline create/edit | search-as-you-type (`hx-get` on keyup), row edit-in-place |
| **Recipe list** | cards by kind with cost + stock | filter chips |
| **Recipe detail** | BOM editor: lines with component picker, qty; cost rollup tree; producibility panel | add/remove/edit lines by fragment swap; cost panel re-renders on every change |
| **Produce** | multiplier input → live requirement/stock check → confirm | `hx-post`, disabled-until-valid, result banner |
| **Batch log** | history with cost snapshots | paged fragments |

Aesthetic direction for the showcase: dark "speakeasy" palette (charcoal,
amber/copper accents, cream text), generous type, the product photography of
a good cocktail menu. One hand-written CSS file; no CSS framework.

## 5. Explicitly out of v1

Multi-warehouse stock, purchase orders and supplier management, unit
conversion, lot tracking / expiry (FEFO), user roles beyond a single login,
recipe versioning, PDF export, barcode. Each is a clean extension of the
model above; none is needed to make the showcase convincing.
