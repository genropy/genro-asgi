"""Every page and HTMX fragment of the prototype, as builder recipes.

Views are plain functions: data in, HTML string out. All markup goes through
genro-builders (text and attributes are escaped by the dialect), never through
f-strings.
"""

from .htmx import render_fragment, render_page

NAV = [
    ("Dashboard", "/", "dashboard"),
    ("Ingredients", "/ingredients", "ingredients"),
    ("Recipes", "/recipes", "recipes"),
    ("Batches", "/batches", "batches"),
]

HTMX_SRC = "https://unpkg.com/htmx.org@2.0.4"


def money(value: float) -> str:
    return f"€ {value:,.2f}"


def unit_money(value: float) -> str:
    return f"€ {value:,.4f}"


def qty(value: float) -> str:
    return f"{value:g}"


# --------------------------------------------------------------------------
# shell
# --------------------------------------------------------------------------


def page(title: str, active: str, build_main) -> str:
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
        nav.a("Genro Cocktail", href="/", class_="brand")
        links = nav.div(class_="navlinks")
        for label, href, key in NAV:
            attrs = {"href": href}
            if key == active:
                attrs["class_"] = "active"
            links.a(label, **attrs)
        main = body.main(class_="container")
        build_main(main)
    return render_page(build)


def _stat(parent, label: str, value: str):
    box = parent.div(class_="stat")
    box.div(value, class_="stat-value")
    box.div(label, class_="stat-label")


def _low_badge(cell, ingredient):
    cell.span(qty(ingredient["stock_qty"]) + f" {ingredient['unit']}")
    if ingredient["stock_qty"] <= ingredient["reorder_level"]:
        cell.span("low", class_="badge badge-warn")


# --------------------------------------------------------------------------
# dashboard
# --------------------------------------------------------------------------


def dashboard(data: dict) -> str:
    totals = data["totals"]

    def build(main):
        main.h1("Production dashboard")
        stats = main.div(class_="stats")
        _stat(stats, "ingredients", str(totals["ingredients"]))
        _stat(stats, "recipes", str(totals["recipes"]))
        _stat(stats, "batches produced", str(totals["batches"]))
        _stat(stats, "raw stock value", money(totals["stock_value"]))

        grid = main.div(class_="grid2")

        left = grid.section(class_="panel")
        left.h2("Low stock")
        if data["low_stock"]:
            table = left.table(class_="data")
            head = table.thead().tr()
            for header in ("Ingredient", "Stock", "Reorder at"):
                head.th(header)
            tbody = table.tbody()
            for ingredient in data["low_stock"]:
                row = tbody.tr()
                row.td(ingredient["name"])
                _low_badge(row.td(), ingredient)
                row.td(qty(ingredient["reorder_level"]) + f" {ingredient['unit']}")
        else:
            left.p("Everything above reorder level.", class_="muted")

        right = grid.section(class_="panel")
        right.h2("Recent batches")
        if data["recent_batches"]:
            table = right.table(class_="data")
            head = table.thead().tr()
            for header in ("When", "Recipe", "Qty", "Cost"):
                head.th(header)
            tbody = table.tbody()
            for batch in data["recent_batches"]:
                row = tbody.tr()
                row.td(batch["produced_at"])
                row.td(batch["recipe_name"])
                row.td(qty(batch["produced_qty"]) + f" {batch['unit']}")
                row.td(money(batch["cost_snapshot"]))
        else:
            right.p("No production yet.", class_="muted")

    return page("Dashboard", "dashboard", build)


# --------------------------------------------------------------------------
# ingredients
# --------------------------------------------------------------------------


def _ingredients_table(parent, ingredients, q: str):
    wrapper = parent.div(id="ing-table")
    table = wrapper.table(class_="data")
    head = table.thead().tr()
    for header in ("Name", "Category", "Unit", "Cost / unit", "Stock", "Reorder at"):
        head.th(header)
    tbody = table.tbody()
    for ingredient in ingredients:
        row = tbody.tr()
        row.td(ingredient["name"])
        row.td(ingredient["category"], class_="muted")
        row.td(ingredient["unit"])
        row.td(unit_money(ingredient["cost_per_unit"]))
        _low_badge(row.td(), ingredient)
        row.td(qty(ingredient["reorder_level"]))
    if not ingredients:
        empty = tbody.tr()
        empty.td(f"Nothing matches “{q}”." if q else "No ingredients yet.",
                 colspan="6", class_="muted")


def ingredients_table_fragment(ingredients, q: str = "") -> str:
    return render_fragment(lambda root: _ingredients_table(root, ingredients, q))


def ingredients_page(ingredients) -> str:
    def build(main):
        main.h1("Ingredients")

        bar = main.div(class_="toolbar")
        bar.input(
            name="q", html_type="search", placeholder="Search name or category…",
            class_="search",
            hx_get="/ingredients_table", hx_target="#ing-table", hx_swap="outerHTML",
            hx_trigger="input changed delay:300ms, keyup[key=='Enter']",
        )

        form = main.form(
            class_="panel inline-form",
            hx_post="/ingredient_add", hx_target="#ing-table", hx_swap="outerHTML",
            **{"hx-on::after-request": "if(event.detail.successful) this.reset()"},
        )
        form.h2("New ingredient")
        row = form.div(class_="form-row")
        row.input(name="name", placeholder="Name", required=True)
        row.input(name="category", placeholder="Category")
        select = row.select(name="unit")
        for unit in ("g", "ml", "pcs"):
            select.option(unit, value=unit)
        row.input(name="cost_per_unit", html_type="number", step="0.0001", min="0",
                  placeholder="Cost per unit €", required=True)
        row.input(name="stock_qty", html_type="number", step="any", min="0",
                  placeholder="Initial stock")
        row.input(name="reorder_level", html_type="number", step="any", min="0",
                  placeholder="Reorder level")
        row.button("Add", html_type="submit", class_="btn")

        _ingredients_table(main, ingredients, "")

    return page("Ingredients", "ingredients", build)


# --------------------------------------------------------------------------
# recipes
# --------------------------------------------------------------------------


def recipes_page(recipes) -> str:
    def build(main):
        main.h1("Recipes")
        cards = main.div(class_="cards")
        for recipe in recipes:
            card = cards.a(class_="card", href=f"/recipe/{recipe['id']}")
            top = card.div(class_="card-top")
            top.h3(recipe["name"])
            top.span(recipe["kind"], class_=f"badge badge-{recipe['kind']}")
            meta = card.div(class_="card-meta")
            meta.div(f"batch yield: {qty(recipe['yield_qty'])} {recipe['yield_unit']}")
            meta.div(f"batch cost: {money(recipe['batch_cost'])}")
            meta.div(f"unit cost: {unit_money(recipe['unit_cost'])} / {recipe['yield_unit']}")
            meta.div(f"in stock: {qty(recipe['stock_qty'])} {recipe['yield_unit']}")
    return page("Recipes", "recipes", build)


def _cost_tree(parent, nodes):
    ul = parent.ul(class_="cost-tree")
    for node in nodes:
        li = ul.li()
        line = li.div(class_="cost-line")
        line.span(node["name"], class_="cost-name")
        line.span(f"{qty(node['qty'])} {node['unit']} × {unit_money(node['unit_cost'])}",
                  class_="muted")
        line.span(money(node["total"]), class_="cost-total")
        if node["children"]:
            _cost_tree(li, node["children"])


def _recipe_stats(parent, detail: dict):
    recipe = detail["recipe"]
    stats = parent.div(
        id="recipe-stats", class_="stats",
        hx_get=f"/recipe_stats?recipe_id={recipe['id']}",
        hx_trigger="batchProduced from:body", hx_swap="outerHTML",
    )
    _stat(stats, "batch yield", f"{qty(recipe['yield_qty'])} {recipe['yield_unit']}")
    _stat(stats, "batch cost", money(detail["batch_cost"]))
    _stat(stats, "unit cost", f"{unit_money(detail['unit_cost'])} / {recipe['yield_unit']}")
    _stat(stats, "in stock", f"{qty(recipe['stock_qty'])} {recipe['yield_unit']}")


def recipe_stats_fragment(detail: dict) -> str:
    return render_fragment(lambda root: _recipe_stats(root, detail))


def _bom_panel(parent, detail: dict):
    recipe = detail["recipe"]
    panel = parent.section(id="bom", class_="panel")
    panel.h2("Bill of materials")

    if detail["lines"]:
        table = panel.table(class_="data")
        head = table.thead().tr()
        for header in ("Component", "Qty / batch", "Unit cost", "Line total", ""):
            head.th(header)
        tbody = table.tbody()
        for line in detail["lines"]:
            row = tbody.tr()
            cell = row.td()
            cell.span(line["component_name"])
            if line["component_kind"] == "recipe":
                cell.span("sub-recipe", class_="badge badge-intermediate")
            row.td(f"{qty(line['qty'])} {line['unit']}")
            row.td(unit_money(line["unit_cost"]))
            row.td(money(line["total"]))
            row.td().button(
                "remove", class_="btn btn-ghost",
                hx_post="/line_delete", hx_target="#bom", hx_swap="outerHTML",
                hx_vals=f'{{"line_id": {line["id"]}, "recipe_id": {recipe["id"]}}}',
                hx_confirm=f"Remove {line['component_name']} from the bill?",
            )
    else:
        panel.p("No components yet — add the first line below.", class_="muted")

    form = panel.form(class_="inline-form",
                      hx_post="/line_add", hx_target="#bom", hx_swap="outerHTML")
    form.input(html_type="hidden", name="recipe_id", value=str(recipe["id"]))
    row = form.div(class_="form-row")
    select = row.select(name="component")
    group = select.optgroup(html_label="Ingredients")
    for item in detail["pick_ingredients"]:
        group.option(f"{item['name']} ({item['unit']})", value=f"ingredient:{item['id']}")
    group = select.optgroup(html_label="Recipes (intermediates)")
    for item in detail["pick_recipes"]:
        group.option(f"{item['name']} ({item['unit']})", value=f"recipe:{item['id']}")
    row.input(name="qty", html_type="number", step="any", min="0",
              placeholder="Qty per batch", required=True)
    row.button("Add line", html_type="submit", class_="btn")

    if detail["cost_tree"]:
        panel.h2("Cost rollup")
        _cost_tree(panel, detail["cost_tree"])


def bom_fragment(detail: dict) -> str:
    return render_fragment(lambda root: _bom_panel(root, detail))


def recipe_page(detail: dict) -> str:
    recipe = detail["recipe"]

    def build(main):
        crumbs = main.div(class_="crumbs")
        crumbs.a("Recipes", href="/recipes")
        crumbs.span(" / ")
        crumbs.span(recipe["name"])
        header = main.div(class_="page-head")
        header.h1(recipe["name"])
        header.span(recipe["kind"], class_=f"badge badge-{recipe['kind']}")
        _recipe_stats(main, detail)

        _bom_panel(main, detail)

        produce = main.section(class_="panel")
        produce.h2("Produce a batch")
        form = produce.form(class_="inline-form",
                            hx_post="/produce", hx_target="#produce-result", hx_swap="innerHTML")
        form.input(html_type="hidden", name="recipe_id", value=str(recipe["id"]))
        row = form.div(class_="form-row")
        row.input(name="multiplier", html_type="number", step="any", min="0.1",
                  value="1", required=True)
        row.span(f"× {qty(recipe['yield_qty'])} {recipe['yield_unit']}", class_="muted")
        row.button("Produce", html_type="submit", class_="btn btn-primary")
        produce.div(id="produce-result")

    return page(recipe["name"], "recipes", build)


def produce_result_fragment(result: dict) -> str:
    def build(root):
        if result["ok"]:
            recipe = result["recipe"]
            banner = root.div(class_="banner banner-ok")
            banner.strong(f"Batch #{result['batch_id']} produced. ")
            banner.span(
                f"+{qty(result['produced_qty'])} {recipe['yield_unit']} at "
                f"{money(result['cost'])} — stock is now "
                f"{qty(recipe['stock_qty'])} {recipe['yield_unit']}."
            )
        else:
            banner = root.div(class_="banner banner-warn")
            banner.strong("Not enough stock. ")
            missing = [r for r in result["requirements"] if r["missing"] > 0]
            items = root.ul(class_="missing")
            for req in missing:
                items.li(
                    f"{req['name']}: need {qty(req['required'])} {req['unit']}, "
                    f"have {qty(req['stock'])} — short {qty(req['missing'])}"
                )
    return render_fragment(build)


# --------------------------------------------------------------------------
# batches
# --------------------------------------------------------------------------


def batches_page(batches) -> str:
    def build(main):
        main.h1("Batch log")
        panel = main.section(class_="panel")
        if batches:
            table = panel.table(class_="data")
            head = table.thead().tr()
            for header in ("#", "When", "Recipe", "Multiplier", "Produced", "Cost", "Notes"):
                head.th(header)
            tbody = table.tbody()
            for batch in batches:
                row = tbody.tr()
                row.td(str(batch["id"]))
                row.td(batch["produced_at"])
                row.td(batch["recipe_name"])
                row.td(f"×{qty(batch['multiplier'])}")
                row.td(qty(batch["produced_qty"]) + f" {batch['unit']}")
                row.td(money(batch["cost_snapshot"]))
                row.td(batch["notes"], class_="muted")
        else:
            panel.p("No batches yet.", class_="muted")
    return page("Batches", "batches", build)
