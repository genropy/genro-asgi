# PageApplication

Micro-app on-demand per risorse dinamiche.

## Stato

❌ **NON IMPLEMENTATO** - Dipende da Session e Avatar.

## Differenze da AsgiApplication

| Aspetto | AsgiApplication | PageApplication |
|---------|-----------------|-----------------|
| Montaggio | Statico in config.yaml | Dinamico da index.py |
| Lifecycle | Persistente | Per-request |
| Router | Ha router genro-routes | No router |
| Endpoints | Via @route() | Metodi diretti |
| Scope | Tutta l'app | Singola risorsa |

## Concetto

```
GET /_resource/admin/
→ Carica resources/admin/index.py
→ Istanzia PageApplication
→ Chiama index() → HTML
→ Istanza scartata
```

## Design Proposto

```python
class PageApplication:
    def __init__(
        self,
        server: AsgiServer,
        request: BaseRequest,
        resource_path: Path,
    ): ...

    @property
    def session(self) -> Session | None:
        """Session for this request."""

    @property
    def avatar(self) -> Avatar | None:
        """Avatar for current user."""

    def load_resource(self, name: str) -> bytes:
        """Load resource from this page's directory."""

    def render_template(self, name: str, **context) -> str:
        """Render template with context."""

    def redirect(self, url: str, status_code: int = 302) -> Response:
        """Return redirect response."""

    def index(self) -> str | bytes | dict | Response:
        """Default index page. Override in subclass."""
```

## Esempio

```python
# resources/admin/index.py
class AdminPage(PageApplication):
    def index(self) -> str:
        if not self.avatar.has_tag("admin"):
            return self.redirect("/login")

        return self.render_template(
            "dashboard.html",
            user=self.avatar.identity,
        )
```

## Dipendenze

1. Session - Per stato utente
2. Avatar - Per identificare utente
3. PageLoader - Per caricamento dinamico
4. Template system - Per rendering HTML

## Quando Implementare

- **Utile per**: Dashboard admin, wizard multi-step, form complessi
- **Non necessario per**: API REST, SPA, risorse statiche

## Effort Stimato

~2-3 giorni (dopo Session/Avatar)
