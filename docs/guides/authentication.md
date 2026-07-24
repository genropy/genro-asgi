# Authentication

> **Status:** 🔴 DA REVISIONARE

## What it does

Configures how callers prove who they are and controls which routes they may
reach. genro-asgi accepts basic, bearer and JWT credentials plus API keys, and
filters routes by the tags carried on the caller's `Avatar`.

## When to use it

When some routes must be restricted to authenticated callers, or to callers with
a particular role. Pass an `auth` config to `AsgiServer` and mark the protected
routes with `auth_rule`.

## Setup

Auth is a mixin capability of `AsgiServer`. You arm it by passing the `auth`
keyword argument; doing so wires the auth middleware automatically.

```python
from genro_asgi import AsgiServer, RoutedApplication
from genro_routes import route

AUTH = {
    "basic":  {"alice": {"password": "wonderland", "tags": "admin,ops"}},
    "bearer": {"svc":   {"token": "sk_live_xyz", "tags": "api"}},
    "jwt":    [{"secret": "topsecret", "algorithm": "HS256"}],
}


class App(RoutedApplication):
    @route()
    def public(self) -> dict:
        return {"open": True}

    @route(auth_rule="admin")
    def secret(self) -> dict:
        return {"classified": True}


server = AsgiServer(primary=App(), auth=AUTH)
server.serve(host="127.0.0.1", port=8000)
```

Notes on the config shape:

- `basic` and `bearer` are dictionaries keyed by identity. A basic entry carries
  a `password`; a bearer entry carries a `token`. Both carry `tags` (a
  comma-separated string or a list) that become the avatar's roles.
- `jwt` is a **list** of verifier configurations, each with a `secret` and an
  `algorithm` — you can accept tokens from more than one issuer.
- API keys with the `gak_...` prefix are handled by an `ApiKeyStore`. Pass
  `tokens=<ApiKeyStore | dict>` alongside `auth`. Users can likewise come from a
  `UserStore` via `users=<UserStore | dict>`, and an `admin_password="..."`
  bootstraps a SUPERADMIN identity.

## Minimal snippet

Protecting a single route:

```python
@route(auth_rule="admin")
def secret(self) -> dict:
    return {"classified": True}
```

`auth_rule="admin"` means the caller's avatar must carry the `admin` tag.
Protection is **default-deny**: this route answers `403` even if no auth is
configured at all, so a protected endpoint is never accidentally open.

## The Avatar

An authenticated caller is represented by an `Avatar`:

```python
from genro_asgi import Avatar

avatar = Avatar("alice", tags="admin,ops")   # tags: comma string or list
```

The avatar's tags are what `auth_rule` matches against. The same `Avatar` type is
used whether the identity came from a header credential or from a session (see
the [sessions guide](sessions.md)).

## Header vs session precedence

- The `Authorization` header wins — genro-asgi is API-first. If a request carries
  a valid credential in the header, that identity is used.
- An **invalid** header credential produces `401` with no fallback to the session
  — a broken token is an error, not an invitation to try the cookie.
- With `auth=None`, no header backend is configured, but the server still
  resolves the identity carried by the session.

## Server-side login flow

The always-mounted `_server` app exposes a login flow for session-based clients:

- `POST /_server/login` with body `{"identity", "password"}` → `200` with
  `{identity, tags, session_id}` on success.
- `GET /_server/login_page` — an HTML login page.
- `GET /_server/login_methods` — a public JSON descriptor of available methods.
- `POST /_server/logout`.

Login lockout with backoff is configurable via `server_app={"login": {...}}`.

## OIDC

An OIDC provider is configured under `server_app`, and the server must know its
own **public base address** — `external_url`:

```python
PROVIDER = {
    "issuer": "https://accounts.example.com",
    "client_id": "client-123",
    "scopes": "openid email profile",
    "identity_claim": "email",
    "tags": [],
}
server = AsgiServer(
    primary=App(),
    external_url="https://shop.example.com",
    server_app={"oidc": {"google": PROVIDER}},
)
```

`external_url` is what the server calls *itself* when it hands its own URL to
the provider: the `redirect_uri` the browser is sent back to must be absolute,
and must match the one you registered for the client in the provider's console —
here `https://shop.example.com/_server/auth/oidc:google/callback`. It is
distinct from the `host`/`port` the server binds to, which differ behind a proxy
and mean nothing to an outside caller. Configuring a provider **without**
`external_url` is a boot error: the server refuses to start rather than fail at
the first login attempt with a provider-side error.

In a config recipe it lives on the `server` section:

```python
root.server(host="127.0.0.1", port=8000, external_url="https://shop.example.com")
```

- `GET /_server/auth/oidc:google/start?next=...` → `302` (PKCE S256).
- `GET /_server/auth/oidc:google/callback?...` → token exchange, avatar attach,
  redirect.
- The public descriptor never exposes the `client_secret` or the `issuer`.

## How to verify it

```console
$ curl -i http://127.0.0.1:8000/secret
HTTP/1.1 403 Forbidden

$ curl -u alice:wonderland http://127.0.0.1:8000/secret
{"classified": true}

$ curl -H "Authorization: Bearer sk_live_xyz" http://127.0.0.1:8000/public
{"open": true}
```

## Gotchas

- `auth_rule` is default-deny: a protected route is `403` even with no auth
  configured. If a route unexpectedly returns `403`, check whether it carries an
  `auth_rule` the caller's avatar does not satisfy.
- `jwt` is a **list**, not a dict — a single verifier still goes inside a
  one-element list.
- An invalid `Authorization` header is `401` and does **not** fall back to the
  session cookie.
- An OIDC provider needs `external_url`, and the resulting callback URL must be
  registered verbatim with the provider — a mismatch is refused by the provider,
  not by us. A missing `external_url` stops the server at boot.
- The auth symbols (`AuthMixin`, `PasswordMethod`, `OidcMethod`, `ApiKeyStore`,
  `FileApiKeyStore`, `UserStore`, `FileUserStore`, `AuthCore`, `AuthMethod`) are
  importable from `genro_asgi`.
