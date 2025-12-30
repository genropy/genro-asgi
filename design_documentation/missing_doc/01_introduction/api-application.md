## Source: plan_2025_12_29/10-api-application.md

**Stato**: ❌ NON IMPLEMENTATO
**Priorità**: P2 (Nice to have)
**Data**: 2025-12-29

Il documento originale proponeva:
- `ApiApplication` come subclass specializzata per API M2M
- No session (stateless by design)
- Token auth only
- Rate limiting built-in
- Standard error responses (RFC 7807)

**Non implementato**. Attualmente si usa `AsgiApplication` per tutto.

- `AsgiApplication` - Base class generica
- `AuthMiddleware` - Supporta bearer/basic/JWT
- `Response.set_error()` - Error mapping base

- `ApiApplication` subclass
- Rate limiting built-in
- RFC 7807 error responses
- Helper per auth validation

```python
class ApiApplication(AsgiApplication):
    """Specialized application for M2M APIs.

Features:
    - Stateless by design (no session support)
    - Token authentication helpers
    - Rate limiting per-endpoint or global
    - RFC 7807 Problem Details error responses
    - Standard headers (X-Request-ID, X-RateLimit-*)
    """

# Class-level configuration
    rate_limit: str | None = None  # e.g., "100/minute", "1000/hour"
    require_auth: bool = True       # Require auth by default

openapi_info: ClassVar[dict[str, Any]] = {
        "title": "API",
        "version": "1.0.0",
    }

def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._rate_limiter: RateLimiter | None = None
        if self.rate_limit:
            self._rate_limiter = RateLimiter.from_string(self.rate_limit)

@property
    def auth(self) -> dict[str, Any]:
        """Get auth info. Raises HTTPUnauthorized if not authenticated."""
        request = self.server.request
        if not request:
            raise HTTPUnauthorized("No request context")

auth = request.scope.get("auth")
        if auth is None and self.require_auth:
            raise HTTPUnauthorized("Authentication required")

@property
    def identity(self) -> str | None:
        """Get authenticated identity. None if anonymous."""
        return self.auth.get("identity")

@property
    def tags(self) -> list[str]:
        """Get auth tags."""
        return self.auth.get("tags", [])

def require_tag(self, *required_tags: str, mode: str = "any") -> None:
        """Require specific auth tags.

Args:
            *required_tags: Tags to check
            mode: "any" (at least one) or "all" (all required)

Raises:
            HTTPForbidden: If tags not present
        """
        user_tags = self.tags

if mode == "any":
            if not any(tag in user_tags for tag in required_tags):
                raise HTTPForbidden(f"Requires one of: {', '.join(required_tags)}")
        else:  # all
            missing = [tag for tag in required_tags if tag not in user_tags]
            if missing:
                raise HTTPForbidden(f"Missing required tags: {', '.join(missing)}")

def require_identity(self) -> str:
        """Require authenticated identity.

Returns:
            Identity string

Raises:
            HTTPUnauthorized: If not authenticated
        """
        identity = self.identity
        if identity is None:
            raise HTTPUnauthorized("Authentication required")
        return identity

def problem(
        self,
        status: int,
        title: str,
        detail: str | None = None,
        type_uri: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """Create RFC 7807 Problem Details response.

Args:
            status: HTTP status code
            title: Short human-readable summary
            detail: Longer explanation (optional)
            type_uri: URI identifying problem type
            **extra: Additional fields

Returns:
            Problem Details dict (set response.status_code manually)
        """
        response = self.server.response
        if response:
            response.status_code = status
            response._media_type = "application/problem+json"

problem = {
            "type": type_uri or "about:blank",
            "title": title,
            "status": status,
        }
        if detail:
            problem["detail"] = detail
        problem.update(extra)

def paginate(
        self,
        items: list[Any],
        page: int = 1,
        per_page: int = 20,
        max_per_page: int = 100,
    ) -> dict[str, Any]:
        """Helper for paginated responses.

Args:
            items: Full list of items
            page: Page number (1-indexed)
            per_page: Items per page
            max_per_page: Maximum allowed per_page

Returns:
            Dict with items, pagination info
        """
        per_page = min(per_page, max_per_page)
        total = len(items)
        total_pages = (total + per_page - 1) // per_page
        start = (page - 1) * per_page
        end = start + per_page

return {
            "items": items[start:end],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            },
        }
```

```python
class RateLimiter:
    """Simple rate limiter using token bucket algorithm."""

def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window = window_seconds
        self._buckets: dict[str, tuple[int, float]] = {}

@classmethod
    def from_string(cls, spec: str) -> RateLimiter:
        """Parse rate limit spec like "100/minute" or "1000/hour"."""
        limit_str, period = spec.split("/")
        limit = int(limit_str)

windows = {
            "second": 1,
            "minute": 60,
            "hour": 3600,
            "day": 86400,
        }
        window = windows.get(period, 60)

def check(self, key: str) -> tuple[bool, dict[str, int]]:
        """Check if request is allowed.

Args:
            key: Rate limit key (e.g., IP, user ID)

Returns:
            Tuple of (allowed, headers_dict)
            headers_dict contains X-RateLimit-* values
        """
        now = time.time()

if key in self._buckets:
            count, window_start = self._buckets[key]
            if now - window_start > self.window:
                # Window expired, reset
                count = 0
                window_start = now
        else:
            count = 0
            window_start = now

count += 1
        self._buckets[key] = (count, window_start)

remaining = max(0, self.limit - count)
        reset_time = int(window_start + self.window)

headers = {
            "X-RateLimit-Limit": self.limit,
            "X-RateLimit-Remaining": remaining,
            "X-RateLimit-Reset": reset_time,
        }

return count <= self.limit, headers
```

```python
class OrdersApi(ApiApplication):
    """Orders API with rate limiting."""

rate_limit = "100/minute"
    require_auth = True

openapi_info = {
        "title": "Orders API",
        "version": "1.0.0",
    }

@route()
    def list_orders(self, page: int = 1, per_page: int = 20) -> dict:
        """List orders for authenticated user."""
        user_id = self.require_identity()
        orders = self.db.get_orders(user_id)
        return self.paginate(orders, page, per_page)

@route(auth_tags="admin")
    def all_orders(self) -> dict:
        """List all orders (admin only)."""
        self.require_tag("admin")
        return {"orders": self.db.get_all_orders()}

@route()
    def get_order(self, order_id: int) -> dict:
        """Get single order."""
        user_id = self.require_identity()
        order = self.db.get_order(order_id)

if not order:
            return self.problem(
                status=404,
                title="Order not found",
                detail=f"Order {order_id} does not exist",
            )

if order["user_id"] != user_id:
            return self.problem(
                status=403,
                title="Access denied",
                detail="You can only view your own orders",
            )

```yaml
apps:
  orders:
    module: "orders:OrdersApi"

auth_middleware:
  bearer:
    api_key:
      token: "tk_production_key"
      tags: "orders"
    admin_key:
      token: "tk_admin_key"
      tags: "orders,admin"
```

| Aspetto | AsgiApplication | ApiApplication |
|---------|-----------------|----------------|
| Session | Supportata | No (stateless) |
| Avatar | Opzionale | No |
| Auth default | Optional | Required |
| Rate limiting | No | Built-in |
| Error format | Semplice | RFC 7807 |
| Pagination | No | Built-in helper |

```json
{
  "type": "https://api.example.com/errors/insufficient-balance",
  "title": "Insufficient balance",
  "status": 400,
  "detail": "Your account balance of $10 is not enough for $25 purchase",
  "balance": 10,
  "required": 25
}
```

Content-Type: `application/problem+json`

- **ApiApplication class**: 4h
- **RateLimiter**: 2h
- **Problem Details**: 1h
- **Pagination helper**: 1h
- **Tests**: 4h
- **Totale**: ~1.5 giorni

**Ultimo aggiornamento**: 2025-12-29

