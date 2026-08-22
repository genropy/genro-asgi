# Features — internal technical documentation

**Version**: 0.1 · **Last Updated**: 2026-08-22 · **Status**: 🔴 DA REVISIONARE

genro-asgi seen as a system of features. Each feature owns one folder with
four documents, each with its own job:

| File | Job |
|---|---|
| `README.md` | the feature in brief, and who it interacts with |
| `design.md` | the desired design — everything we want it to be, ratified by the owner |
| `frictions.md` | open problems and frictions, kept updated; entries leave only when resolved or explicitly accepted |
| `status.md` | the current state — the feature's local memory, updated in the SAME change that alters the behaviour |

`design.md` and `status.md` deliberately separate what we WANT from what
EXISTS: mixing the two is how documents rot. A claim in `status.md` must be
verifiable in the code; a claim in `design.md` needs no code at all.

## The features

### Server layer

| Feature | In brief |
|---|---|
| [configuration](configuration/) | recipe, config builder, CLI |
| [middleware](middleware/) | errors, auth, session, cors, logging, wellknown |
| [routing](routing/) | route tree + OpenAPI and MCP faces |
| [authentication](authentication/) | auth core, OIDC, api keys, tokens, users |
| [sessions](sessions/) | MemoryStore, avatar, cookie ttl×24 |
| [storage](storage/) | storage nodes, logical volumes, pinned sync |
| [tasks](tasks/) | scheduler, spool, executor |
| [task-thermometers](task-thermometers/) | live batch progress + cooperative stop |
| [server-application](server-application/) | the `_server` app and its sections |
| [monitor](monitor/) | one page over every mounted app |
| [inspector](inspector/) | admin read surface over the SPA fronts |
| [console](console/) | eval door as MCP tools; mounting IS the gate |

### SPA layer

| Feature | In brief |
|---|---|
| [spa-application](spa-application/) | the stateless front: cookie identity, demux, HTTP translation |
| [orchestration](orchestration/) | commander → groups → workers → sites; freezer, mobility, deaths |
| [channel](channel/) | frames, hub, the worker wire |
| [global-store](global-store/) | one master on the commander, reads as calls, lock grant/release |
| [datachanges](datachanges/) | addressed distribution of page changes |
| [dbevents](dbevents/) | table subscriptions and event delivery |
| [restart](restart/) | soft/hard restart liturgy, dump/restore — second pass |
| [deployment-bundles](deployment-bundles/) | 🔴 proposal: dynamic groups, immutable bundles, S3 |

## Interaction map

Who stands on whom. An arrow means "uses / is carried by".

```text
spa-application ──► orchestration ──► channel
                        │  ├──► global-store
                        │  ├──► datachanges ◄─► dbevents   (one DeliveryDesk)
                        │  ├──► storage (freezer parcels)
                        │  └──► restart (park / refill)
console ──► orchestration (eval over the lane)   inspector ──► spa-application
monitor ──► every app (snapshot/panel contract)
server-application ──► {monitor, inspector, tasks, authentication}
task-thermometers ──► tasks (spool) + live event channel
middleware ──► {authentication, sessions}
routing ──► {OpenAPI, MCP} faces — console rides the MCP face
configuration ──► every feature (each reads its recipe subtree)
```

Cross-feature seams that deserve watching are recorded in each feature's
`frictions.md`; a friction that lives BETWEEN two features is recorded in
both, with the same wording.
