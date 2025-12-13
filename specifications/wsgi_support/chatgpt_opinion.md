# ChatGPT Opinion on Legacy Migration Plan

**Date**: 2025-02-11  
**Scope**: Revisione dei documenti in `spec/legacy-migration/` e valutazione del percorso sticky ASGI con PageRegistry in-process.

## Per documento: sintesi + opinione
- `01-overview.md`: propone sticky routing per eliminare gnrdaemon, PageRegistry in-process, tolleranza al rilogin su crash. Opinione: direzione giusta; serve policy esplicita per process down (`pXX` non disponibile).
- `02-current-architecture.md`: foto dell’attuale WSGI/Tornado/Pyro con supervisord. Opinione: chiaro baseline; nessuna azione.
- `03-page-id-routing.md`: introduce `page_id|pXX` per routing deterministico, fallback per legacy. Opinione: bene; da fissare validazione/formato e comportamento se il processo indicato è down.
- `04-migration-phases.md`: fasi 0→1→2 con rollback. Opinione: struttura ok; mancano Definition of Done per fase (test/metriche/rollback concreti).
- `05-deployment-strategy.md`: green/blue/canary per rollout ASGI/legacy. Opinione: utile, ma vanno aggiunti limiti stickiness per WS/HTTP durante switch di colore e metriche per colore.
- `09-gemini-opinion.md`: propone container + NATS come evoluzione. Opinione: interessante come step successivo, ma non vincolante; con volumi attuali basta IPC leggero.
- `10-migration-proposal.md`: “Modern Monolith” con smart router + worker stateful. Opinione: coerente con sticky; richiede scelte pratiche su IPC e backpressure.
- `11-chatgpt-opinion.md`: bozza precedente (questa è la versione aggiornata).

## Valutazione sintetica complessiva
- Direzione corretta: sticky routing (`page_id|pXX`), PageRegistry in memoria per eliminare Pyro/gnrdaemon e unificare HTTP/WS in ASGI. Con volumi (10–20 utenti, 20–300 pagine, payload 0.2–20 KB) è fattibile e a basso rischio.
- Stato in-process: purge on close già previsto; TTL idle + sweep probabilistico e persistenza JSON opzionale sono economici. Servono write atomico + checksum/versione, cleanup periodico.
- Routing ID: `page_id|pXX` per nuovi; legacy senza `|` devono restare sul percorso legacy con fail fast in ASGI. Da definire riassegnazione su process down.
- IPC cross-process: oggi solo opzioni; scegliere canale minimo (socket/queue) e misurare latenza; NATS è evoluzione, non prerequisito.
- Backpressure/ops: da completare limiti connessioni/payload, timeout, health/readiness e metriche base (pagine attive, evict, restore, drop per flag errato, riassegnazioni).

## Raccomandazioni operative
1) Aggiungere DoD per fasi 0/1/2 in `04-migration-phases.md` (test, metriche, rollback).  
2) Formalizzare policy process down: rigenerare `page_id|pYY` al primo roundtrip o errore chiaro; loggare riassegnazioni.  
3) Scegliere un IPC minimo e misurare latenza (socket/queue locale; NATS se già a portata).  
4) Documentare backpressure/limiti e health/readiness; aggiungere metriche base.  
5) Persist/restore: usare write atomico + checksum/versione, naming per processo, cleanup periodico; ricreare pagina se file mancante/corrotto.

## PoC sì/no
- Se mancano misure in ASGI su p50/p95 WS/HTTP, stickiness `|pXX`, e latenza IPC, fare un micro-PoC (router + 2 worker + PageRegistry + echo RPC) in 1–2 giorni.  
- Se questi punti sono già accettati, si può procedere direttamente con implementazione incrementale sotto feature flag.
