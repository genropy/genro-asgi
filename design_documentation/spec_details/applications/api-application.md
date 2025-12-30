# ApiApplication

Subclass specializzata per API M2M stateless.

## Stato

❌ **NON IMPLEMENTATO** - Attualmente si usa `AsgiApplication` per tutto.

## Caratteristiche Proposte

| Feature | ApiApplication | AsgiApplication |
|---------|----------------|-----------------|
| Session | No (stateless) | Supportata |
| Auth default | Required | Optional |
| Rate limiting | Built-in | No |
| Error format | RFC 7807 | Semplice |
| Pagination | Helper built-in | No |

## Design Proposto

```python
class ApiApplication(AsgiApplication):
    rate_limit: str | None = None  # "100/minute"
    require_auth: bool = True

    @property
    def auth(self) -> dict[str, Any]:
        """Get auth info. Raises HTTPUnauthorized if not authenticated."""

    @property
    def identity(self) -> str | None:
        """Get authenticated identity."""

    @property
    def tags(self) -> list[str]:
        """Get auth tags."""

    def require_tag(self, *tags: str, mode: str = "any") -> None:
        """Require specific auth tags. Raises HTTPForbidden."""

    def problem(self, status: int, title: str, detail: str = None) -> dict:
        """Create RFC 7807 Problem Details response."""

    def paginate(self, items: list, page: int = 1, per_page: int = 20) -> dict:
        """Helper for paginated responses."""
```

## RFC 7807 Problem Details

```json
{
  "type": "https://api.example.com/errors/insufficient-balance",
  "title": "Insufficient balance",
  "status": 400,
  "detail": "Your balance of $10 is not enough for $25",
  "balance": 10,
  "required": 25
}
```

Content-Type: `application/problem+json`

## Quando Implementare

- **Utile per**: API REST dedicate, microservizi M2M
- **Non necessario per**: API semplici (AsgiApplication sufficiente)

## Effort Stimato

~1.5 giorni
