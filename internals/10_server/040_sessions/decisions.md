# Sessions — decisions

**Version**: 0.1 · **Last Updated**: 2026-08-24 · **Status**: 🔴 DA REVISIONARE

Everything this feature SHOULD be when finished — the target, not the code.
To be filled by the documentation audit and ratified by the owner.

## Seeded ahead of the audit — the session knows its authenticating connection

**Source: owner, 2026-08-24 (interview on 020_applications S2). Not yet
implemented.** The session record carries the connection id of the SPA
connection that authenticated it — a **scalar**, written once by the first
application that performs authentication, cleared when the session's identity
decays. The reverse direction (connection → session) lives on the
`connection_register_item`. Writer and moment are the front's, on the return:
see [010 spa-application](../../20_spa/010_spa-application/decisions.md).
