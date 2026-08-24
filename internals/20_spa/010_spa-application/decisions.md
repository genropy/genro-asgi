# SPA application (the front) — decisions

**Version**: 0.1 · **Last Updated**: 2026-08-24 · **Status**: 🔴 DA REVISIONARE

Everything this feature SHOULD be when finished — the target, not the code.
To be filled by the documentation audit and ratified by the owner.

## Seeded ahead of the audit — the front writes the connection↔session link

**Source: owner, 2026-08-24 (interview on 020_applications S2). Not yet
implemented.** The front is the one place both ids are in the same hands: the
request enters with the server session already loaded, the site's answer
carries the connection id. On the return — the same moment the
`spa_connection_id` cookie is written — the front records the link in both
directions:

- `session_id` becomes a field of the `connection_register_item`, written to
  the commander over the lane the front already uses;
- the session record gains the connection id **of the authenticating app
  only** — a scalar, not a map: the link is written by the first application
  that authenticates, later returns from other apps never touch it, and the
  field decays with the session's identity (logout, expiry).

One writer, one moment, both directions — the pair cannot diverge. Updates
happen only when the arriving pair differs from the recorded one, exactly as
the connection cookie is rewritten only when it changes.
