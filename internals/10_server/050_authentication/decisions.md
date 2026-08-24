# Authentication — decisions

**Version**: 0.1 · **Last Updated**: 2026-08-24 · **Status**: 🔴 DA REVISIONARE

Everything this feature SHOULD be when finished — the target, not the code.
To be filled by the documentation audit and ratified by the owner.

## Seeded ahead of the audit — the avatar for a site-authenticated user

**Source: owner, 2026-08-24 (interview on 020_applications S2). Not yet
implemented.** A user authenticated by the hosted site itself (the genropy
legacy login) must not be anonymous on the non-legacy branches: without an
avatar, a tagged route challenges a user who already logged in. So the
identity block the site declares on the return (see
[080 bridge-contract](../../20_spa/080_bridge-contract/decisions.md)) becomes
a server avatar attached to the session:

- **identity**: declared by the site at its guest→user transition;
- **tags**: assigned by the SPA application's server-side configuration,
  never declared by the site — the same shape as the OIDC method, which mints
  `Avatar(identity, provider_config_tags)`. The tag vocabulary stays the
  server's; per-user granularity, if ever needed, extends server-side without
  touching the site.
