# Channel — decisions

**Version**: 0.3 · **Last Updated**: 2026-09-08 · **Status**: 🔴 DA REVISIONARE

Everything this feature SHOULD be when finished — the target, not the code.
To be filled by the documentation audit and ratified by the owner.

---

# Open frictions

Seeded before this entry is audited, by a friction found in a neighbouring one
and written here in the same words. It is settled once for both.

**Implementation follow-up, 2026-09-08 (not a new ratification).** The
historical no-WebSocket finding below is superseded by the delivered
`BaseServer.on_websocket`, `WsxConnection` and raw `serve_websocket` seam.
The Origin gate belongs to WSX handshake processing; raw applications own their
handshake policy after the server state gate. Evidence and owner provenance:
[WebSocket decisions](../../10_server/055_websocket/decisions.md) and [WebSocket status](../../10_server/055_websocket/status.md).

**S1 — an application cannot answer a WebSocket.** The only WebSocket door is
the server's, and at the base it accepts the connection and closes it politely;
no composition hands a socket to an application, so no application can hold a
long-lived conversation. Meanwhile the ratified delivery design for this world
puts pushed traffic on WebSockets. **Q1**, SPECIFICATION.md:695, foresees one
dispatch engine with two transports, designed so that context, resolution hooks
and cleanups exist on both. The question that belongs to the application side is
what the application contract's WebSocket door looks like, since it is the
contract that would grow a further obligation. Recorded in the same wording in
[10_server/020 applications](../../10_server/020_applications/decisions.md),
friction S6.
