# Avatar — current state

**Version**: 0.2 · **Last Updated**: 2026-09-08 · **Status**: 🔴 evidence refreshed; design ratification unchanged

Verified against source revision `2465fcc` (develop baseline). Test references
below identify the executable contracts; they are not a new coverage percentage.

## Identity value

`Avatar(identity, tags=None)` is a slotted value object with `identity`, a
normalized list of `tags`, and an extensible `data` Bag. An anonymous request is
represented by `None`, not an anonymous Avatar. Authentication methods return
this common type and `Session` stores it in keyed slots, with `root` the default.

`Request.avatar()` reads the HTTP scope's root auth verdict; other avatar keys
are resolved through the session. Avatar data is distinct from session data.
The type itself does not select a SPA group or create the proposed
connection-to-session link.

Claim anchors: [`Avatar`](../../../../src/genro_asgi/session/avatar.py#L31), [`identity`](../../../../src/genro_asgi/session/avatar.py#L43), [`tags`](../../../../src/genro_asgi/session/avatar.py#L48), [`Session`](../../../../src/genro_asgi/session/session.py#L60), [`Request`](../../../../src/genro_asgi/request.py#L107), [`avatar`](../../../../src/genro_asgi/session/session.py#L93), [`avatar`](../../../../src/genro_asgi/request.py#L349).

## Source and test evidence

- [src/genro_asgi/session/avatar.py](../../../../src/genro_asgi/session/avatar.py)
- [src/genro_asgi/session/session.py](../../../../src/genro_asgi/session/session.py)
- [src/genro_asgi/request.py](../../../../src/genro_asgi/request.py)
- [tests/core/test_auth.py](../../../../tests/core/test_auth.py)
- [tests/core/test_session.py](../../../../tests/core/test_session.py)
- [tests/core/test_request.py](../../../../tests/core/test_request.py)
