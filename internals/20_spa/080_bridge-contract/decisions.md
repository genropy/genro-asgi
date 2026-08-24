# Bridge contract — decisions

**Version**: 0.1 · **Last Updated**: 2026-08-24 · **Status**: 🔴 DA REVISIONARE

Everything this entry SHOULD be when finished — the target, not the code.
To be filled by the documentation audit and ratified by the owner.

## Seeded ahead of the audit — the identity block on the return

**Source: owner, 2026-08-24 (interview on 020_applications S2). Not yet
implemented.** The hosted site already names its connection on the return
path (the answer carries the connection id the cookie is written from). The
same path gains an **identity block**: at the site's own guest→user
transition, the answer declares "this connection is now user X" —
**identity only, never tags**. Tags are the server's authorization
vocabulary and never travel from the hosted site (see
[050 authentication](../../10_server/050_authentication/decisions.md)).
