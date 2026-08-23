# Channel — desired design

**Version**: 0.2 · **Last Updated**: 2026-08-23 · **Status**: 🔴 DA REVISIONARE

Everything this feature SHOULD be when finished — the target, not the code.
To be filled by the documentation audit and ratified by the owner.

---

# Open frictions

Seeded before this entry is audited, by a friction found in a neighbouring one
and written here in the same words. It is settled once for both.

**S1 — an application cannot answer a WebSocket.** The only WebSocket door is
the server's, and at the base it accepts the connection and closes it politely;
no composition hands a socket to an application, so no application can hold a
long-lived conversation. Meanwhile the ratified delivery design for this world
puts pushed traffic on WebSockets. **Q1**, SPECIFICATION.md:695, foresees one
dispatch engine with two transports, designed so that context, resolution hooks
and cleanups exist on both. The question that belongs to the application side is
what the application contract's WebSocket door looks like, since it is the
contract that would grow a further obligation. Recorded in the same wording in
[10_server/020 applications](../../10_server/020_applications/design.md),
friction S6.
