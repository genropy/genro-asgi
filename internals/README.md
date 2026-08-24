# Internals — the technical dossier

**Version**: 0.4 · **Last Updated**: 2026-08-23 · **Status**: 🔴 DA REVISIONARE

genro-asgi as three worlds, read in order. Start from
**[00_overview](00_overview/README.md)** — it explains the documents every entry owns,
the cycle they serve, the rules, and lists everything with one line and a
link.

- [00_overview/](00_overview/README.md) — how to read, the whole building at a glance
- [10_server/](10_server/README.md) — the machine: from BaseServer to configuration, cli and restart
- [20_spa/](20_spa/README.md) — the SPA world: front, orchestration, data plane, the bridge contract
- [30_deploy/](30_deploy/README.md) — 🔴 proposals: bundles, Kubernetes, subcommanders

## Reading it as a site

These pages carry diagrams and cross-links, and both read better rendered.
From the repository root:

```
pip install -e '.[internals]'
mkdocs serve
```

That serves this folder at <http://127.0.0.1:8771/> with navigation, full-text
search and the diagrams drawn — reading the files on disk, on your own branch,
with no copy produced anywhere. The port is fixed so a deep link works for
anyone else who has the reader running.
