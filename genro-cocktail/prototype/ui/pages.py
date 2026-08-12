"""Every page and HTMX fragment of the bar, as builder recipes.

Views are plain functions: data in, HTML string out. All markup goes through
genro-builders (text and attributes are escaped by the dialect), never through
f-strings. ``ctx`` is the little bit of who-is-looking every page needs:
``{"user": identity-or-None, "session_id": str}``.
"""

from .htmx import render_fragment, render_page

NAV = [
    ("The bar", "/", "bar"),
    ("The shelf", "/ingredients", "shelf"),
]

HTMX_SRC = "/static/htmx.min.js"


def money(value: float) -> str:
    return f"€ {value:,.2f}"


def qty(value: float) -> str:
    return f"{value:g}"


# --------------------------------------------------------------------------
# shell
# --------------------------------------------------------------------------


def page(title: str, active: str, ctx: dict, build_main, script: str = "") -> str:
    def build(root):
        html = root.html(lang="en")
        head = html.head()
        head.meta(charset="utf-8")
        head.meta(name="viewport", content="width=device-width, initial-scale=1")
        head.title(f"{title} · Genro Cocktail")
        head.link(rel="stylesheet", href="/static/styles.css")
        head.script(src=HTMX_SRC)
        body = html.body()
        nav = body.nav(class_="topnav")
        nav.a("🍸 Genro Cocktail", href="/", class_="brand")
        links = nav.div(class_="navlinks")
        for label, href, key in NAV:
            attrs = {"href": href}
            if key == active:
                attrs["class_"] = "active"
            links.a(label, **attrs)
        who = nav.div(class_="who")
        if ctx.get("user"):
            who.span(f"🙋 {ctx['user']}", class_="muted")
            logout = who.form(
                hx_post=f"/_server/logout?session_id={ctx.get('session_id', '')}",
                hx_swap="none",
                **{"hx-on::after-request": "location.reload()"},
            )
            logout.button("sign out", html_type="submit", class_="btn btn-ghost")
        else:
            who.a("Sign in", href="/_server/login_page?next=/", class_="signin")
        main = body.main(class_="container")
        build_main(main)
        if script:
            body.script(src=script)
    return render_page(build)


def _stat(parent, label: str, value: str, value_id: str = None):
    box = parent.div(class_="stat")
    attrs = {"class_": "stat-value"}
    if value_id:
        attrs["id"] = value_id
    box.div(value, **attrs)
    box.div(label, class_="stat-label")


def _tag_chips(parent, cocktail):
    chips = parent.div(class_="chips")
    for tag in cocktail["tag_list"]:
        chips.span(tag, class_="chip")


# --------------------------------------------------------------------------
# the bar (gallery)
# --------------------------------------------------------------------------


def _bar_grid(parent, cocktails):
    grid = parent.div(id="bar-grid", class_="cards")
    for cocktail in cocktails:
        card = grid.a(class_="card", href=f"/cocktail/{cocktail['id']}")
        top = card.div(class_="card-top")
        top.span(cocktail["emoji"], class_="glass")
        if cocktail["is_classic"]:
            top.span("classic", class_="badge badge-classic")
        else:
            top.span("yours", class_="badge badge-yours")
        card.h3(cocktail["name"])
        _tag_chips(card, cocktail)
        meta = card.div(class_="card-meta")
        meta.span(f"{cocktail['abv']}% vol", class_="abv")
        meta.span(f"· {qty(cocktail['volume'])} ml · {money(cocktail['cost'])}")
    if not cocktails:
        grid.p("Nothing here — mix something!", class_="muted")


def bar_grid_fragment(cocktails) -> str:
    return render_fragment(lambda root: _bar_grid(root, cocktails))


def bar_page(cocktails, tags, active_tag: str, ctx: dict) -> str:
    def build(main):
        hero = main.div(class_="hero")
        hero.h1("Every classic is a lesson.")
        hero.p("Poke at the recipes below — sliders, not rules. "
               "When one starts to feel like yours, fork it and give it a name.",
               class_="muted")

        toolbar = main.div(class_="toolbar")
        chips = toolbar.div(class_="chips chips-filter")
        all_attrs = {
            "class_": "chip chip-btn" + ("" if active_tag else " chip-on"),
            "hx_get": "/bar_grid", "hx_target": "#bar-grid", "hx_swap": "outerHTML",
        }
        chips.button("all", **all_attrs)
        for tag in tags:
            attrs = {
                "class_": "chip chip-btn" + (" chip-on" if tag == active_tag else ""),
                "hx_get": f"/bar_grid?tag={tag}", "hx_target": "#bar-grid",
                "hx_swap": "outerHTML",
            }
            chips.button(tag, **attrs)

        form = toolbar.form(class_="newdrink", hx_post="/new_cocktail", hx_swap="none")
        form.input(name="name", placeholder="Name your invention…", required=True)
        form.button("🍸 Mix a new one", html_type="submit", class_="btn btn-primary")

        _bar_grid(main, cocktails)

    return page("The bar", "bar", ctx, build)


# --------------------------------------------------------------------------
# the mixing lab (editor)
# --------------------------------------------------------------------------


def _abv_meter(parent, abv: float):
    meter = parent.div(class_="meter")
    fill_pct = min(100.0, abv * 100.0 / 40.0)  # 40% vol = full bar
    meter.div(class_="meter-fill", id="abv-fill", style=f"width: {fill_pct}%")


def _stats_panel(parent, stats: dict):
    panel = parent.div(id="mix-stats", class_="panel stats-panel")
    row = panel.div(class_="stats")
    _stat(row, "in the glass", f"{qty(stats['volume'])} ml", value_id="stat-volume")
    _stat(row, "strength", f"{stats['abv']}% vol", value_id="stat-abv")
    _stat(row, "pour cost", money(stats["cost"]), value_id="stat-cost")
    _stat(row, "standard drinks", f"{stats['drinks']}", value_id="stat-drinks")
    _abv_meter(panel, stats["abv"])
    footer = panel.div(class_="stats-footer")
    footer.span("", id="save-state", class_="save-state muted")
    footer.span("Drink water too. 💧", class_="muted tiny")


def _mixer(parent, detail: dict, owned: bool):
    cocktail = detail["cocktail"]
    mixer = parent.section(
        id="mixer", class_="panel",
        data_cocktail_id=str(cocktail["id"]),
        data_editable="1" if owned else "0",
    )
    mixer.h2("The mix")
    if not detail["lines"]:
        mixer.p("An empty glass. Add your first ingredient below. 🧊", class_="muted")
    for line in detail["lines"]:
        row = mixer.div(class_="slider-row")
        label = row.div(class_="slider-label")
        label.span(f"{line['emoji']} {line['name']}")
        label.span(f"{line['abv']}% vol · {money(line['cost_per_ml'])}/ml",
                   class_="muted tiny")
        controls = row.div(class_="slider-controls")
        controls.input(
            html_type="range", min="0", max="200", step="5",
            value=qty(line["qty_ml"]),
            class_="dose", data_ingredient=str(line["ingredient_id"]),
        )
        controls.span(f"{qty(line['qty_ml'])} ml", class_="dose-label",
                      id=f"dose-{line['ingredient_id']}")
        if owned:
            controls.button(
                "✕", class_="btn btn-ghost",
                hx_post="/line_remove", hx_target="#mixer", hx_swap="outerHTML",
                hx_vals=f'{{"cocktail_id": {cocktail["id"]}, "ingredient_id": {line["ingredient_id"]}}}',
            )

    if owned and detail["shelf"]:
        form = mixer.form(class_="form-row",
                          hx_post="/line_add", hx_target="#mixer", hx_swap="outerHTML")
        form.input(html_type="hidden", name="cocktail_id", value=str(cocktail["id"]))
        select = form.select(name="ingredient_id")
        for item in detail["shelf"]:
            select.option(f"{item['emoji']} {item['name']} ({item['abv']}% vol)",
                          value=str(item["id"]))
        form.button("Add to the glass", html_type="submit", class_="btn")


def mixer_fragment(detail: dict, owned: bool) -> str:
    return render_fragment(lambda root: _mixer(root, detail, owned))


def cocktail_page(detail: dict, owned: bool, ctx: dict) -> str:
    cocktail = detail["cocktail"]

    def build(main):
        crumbs = main.div(class_="crumbs")
        crumbs.a("The bar", href="/")
        crumbs.span(f" / {cocktail['name']}")

        head = main.div(class_="page-head")
        head.span(cocktail["emoji"], class_="glass glass-big")
        head.h1(cocktail["name"])
        if cocktail["is_classic"]:
            head.span("classic", class_="badge badge-classic")
        elif owned:
            head.span("yours", class_="badge badge-yours")

        if cocktail["story"]:
            main.p(cocktail["story"], class_="story muted")
        _tag_chips(main, cocktail)

        if not owned:
            bench = main.div(class_="panel fork-panel")
            bench.p("Play with the sliders all you want — a classic never changes. "
                    "Fork it to keep your version.", class_="muted")
            fork = bench.form(hx_post="/fork", hx_swap="none")
            fork.input(html_type="hidden", name="cocktail_id", value=str(cocktail["id"]))
            fork.button(f"🍴 Fork {cocktail['name']}", html_type="submit",
                        class_="btn btn-primary")
        else:
            meta = main.form(class_="form-row meta-form",
                             hx_post="/update_meta", hx_swap="none")
            meta.input(html_type="hidden", name="cocktail_id", value=str(cocktail["id"]))
            meta.input(name="emoji", value=cocktail["emoji"], class_="emoji-input",
                       maxlength="4")
            meta.input(name="name", value=cocktail["name"], required=True)
            meta.input(name="tags", value=cocktail["tags"],
                       placeholder="tags: bitter, sour, sweet…")
            meta.button("Save details", html_type="submit", class_="btn")
            meta.button(
                "🚰 Pour it away", html_type="button", class_="btn btn-ghost",
                hx_post="/delete_cocktail", hx_swap="none",
                hx_vals=f'{{"cocktail_id": {cocktail["id"]}}}',
                hx_confirm=f"Pour {cocktail['name']} down the drain, forever?",
            )

        _stats_panel(main, detail["stats"])
        _mixer(main, detail, owned)

    return page(cocktail["name"], "bar", ctx, build, script="/static/mixlab.js")


# --------------------------------------------------------------------------
# the shelf (ingredients)
# --------------------------------------------------------------------------


def _shelf_grid(parent, ingredients, q: str):
    grid = parent.div(id="shelf-grid", class_="cards")
    for item in ingredients:
        card = grid.div(class_="card")
        top = card.div(class_="card-top")
        top.span(item["emoji"], class_="glass")
        top.span(item["category"], class_="chip")
        card.h3(item["name"])
        meta = card.div(class_="card-meta")
        meta.span(f"{item['abv']}% vol", class_="abv")
        meta.span(f"· {money(item['cost_per_ml'])}/ml")
    if not ingredients:
        grid.p(f"Nothing matches “{q}”." if q else "The shelf is empty.", class_="muted")


def shelf_grid_fragment(ingredients, q: str = "") -> str:
    return render_fragment(lambda root: _shelf_grid(root, ingredients, q))


def ingredients_page(ingredients, ctx: dict) -> str:
    def build(main):
        main.h1("The shelf")
        main.p("What the bar is made of: every bottle with its strength and its price.",
               class_="muted")

        toolbar = main.div(class_="toolbar")
        toolbar.input(
            name="q", html_type="search", placeholder="Search the shelf…", class_="search",
            hx_get="/shelf_grid", hx_target="#shelf-grid", hx_swap="outerHTML",
            hx_trigger="input changed delay:300ms",
        )

        form = main.form(class_="panel inline-form",
                         hx_post="/ingredient_add", hx_target="#shelf-grid",
                         hx_swap="outerHTML",
                         **{"hx-on::after-request": "if(event.detail.successful) this.reset()"})
        form.h2("New bottle")
        row = form.div(class_="form-row")
        row.input(name="emoji", placeholder="🧴", class_="emoji-input", maxlength="4")
        row.input(name="name", placeholder="Name", required=True)
        row.input(name="category", placeholder="Category")
        row.input(name="abv", html_type="number", step="0.1", min="0", max="100",
                  placeholder="% vol", required=True)
        row.input(name="cost_per_ml", html_type="number", step="0.001", min="0",
                  placeholder="€/ml", required=True)
        row.button("Put it on the shelf", html_type="submit", class_="btn")

        _shelf_grid(main, ingredients, "")

    return page("The shelf", "shelf", ctx, build)
