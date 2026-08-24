# Middleware

**Version**: 0.1 · **Last Updated**: 2026-08-24 · **Status**: 🔴 DA REVISIONARE

A middleware is a layer wrapped around the dispatch. It sees the request before
the server decides who will serve it, and it sees the answer on the way out: it
can look, it can add, it can answer instead, and it can refuse — for every HTTP
request, whichever application the request was going to. That is what keeps
questions with one machine-wide answer out of the applications: authentication,
cross-origin reads, what to do when something raises, whether a request deserves
a line in a log. Each layer declares one integer, `middleware_order`, and the
chain sorts itself by it, lowest outermost. This core ships six — errors,
wellknown, logging, cors, session, auth.

Its parts:

- **the ring and its order** — one number per layer, and why the order is the design
- **assembly** — built once, from an explicit list, with no global registry
- **the six** — what each one does, and what it puts on the request
- **the outermost layer** — the one that turns a raised exception into an answer
- **what the ring does not see** — and why that is a decision, not an omission
- **what a site writes** — the switches, and what the capabilities arm by themselves
- **writing one** — the base class, the two attributes, and how it is installed
