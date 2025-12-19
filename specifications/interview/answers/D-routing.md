# D. Routing (via genro-routes)

**Date**: 2025-12-13
**Status**: Verified
**Verified in**: `dispatcher.py`, genro-routes documentation

---

## Dependency

genro-asgi uses **genro-routes** for routing. Full documentation in:
`specifications/dependencies/genro-routes.md`

## Path → Handler Flow

```text
Request path: /shop/products/list
       ↓
Selector: "shop/products/list"  (path.strip("/"))
       ↓
router.get(selector)
       ↓
Handler (RoutingClass method)
```

## Dispatcher Behavior (verified in code)

1. **Path → Selector**: `selector = path.strip("/") or "index"`
2. **Selector → Handler**: `handler = router.get(selector)`
3. **If handler is a Router** (not a method):
   - Look for `index` in sub-router
   - If no index → **show `members()` as HTML** (navigation)
4. **Handler invocation**:
   - If first parameter is `request`/`req` → `handler(request, **query_params)`
   - Otherwise → `handler(**query_params)`

## Mounted Apps = Sub-routers

```python
server.router.attach_instance(shop_app, name="shop")
# Now: /shop/products → router.get("shop/products") → shop_app.products()
```

## Automatic Introspection

- **`router.members()`**: router structure (entries, child routers)
- **`router.openapi()`**: OpenAPI schema generated from type hints
- **Lazy mode**: `members(lazy=True)` returns callable instead of expanding

## genro-routes Plugins

Plugin = middleware at individual method level, runtime configurable.

**Use in genro-asgi** (potential):

- Authentication on specific methods
- Delegation to executors
- Python debug on specific methods
- Permissions and filters

**Available hooks**: `on_decore`, `wrap_handler`, `allow_entry`, `entry_metadata`, `configure`

**Runtime configuration**: `routedclass.configure("router:plugin/selector", ...)`
