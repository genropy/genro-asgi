# Middleware

**Version**: 0.1 · **Last Updated**: 2026-08-22 · **Status**: 🔴 DA REVISIONARE

The wrappers around the server dispatch, applied in a fixed order:
errors (exception → HTTP answer), authentication, session, cors, logging,
wellknown. Each is a small module in `middleware/`; `base.py` holds the
shared contract and cookie helpers.

Interactions: authentication · sessions · every HTTP request.
