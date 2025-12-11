# Implementation Plan - genro-asgi

Questa cartella contiene la documentazione di design e implementazione per tutti i moduli di genro-asgi.

## Struttura

```
implementation-plan/
├── README.md              # Questo file
├── to-do/                 # Blocchi in lavorazione
│   └── XX-name-NN/        # Blocco logico (es. 04-server-01)
│       ├── XX-name-initial.md    # Idea iniziale, motivazioni
│       ├── XX-name-questions.md  # Domande aperte (se ci sono)
│       ├── XX-name-decisions.md  # Decisioni prese (se ci sono)
│       ├── 01-submodule/         # Sotto-modulo (se il blocco è complesso)
│       │   ├── initial.md
│       │   ├── questions.md
│       │   ├── decisions.md
│       │   └── final.md
│       └── 02-submodule-done/    # Sotto-modulo completato (marcato -done)
│           └── ...
├── done/                  # Blocchi completati
│   └── XX-name-NN-done/   # Blocco completato
│       ├── ...            # Tutti i file del blocco
│       └── XX-name-release_note.md  # Note di rilascio
└── archive/               # Documentazione storica (piani originali)
```

## Numerazione Blocchi

| # | Blocco | Descrizione | Stato |
|---|--------|-------------|-------|
| 01 | types | Tipi base ASGI (Scope, Receive, Send) | DONE |
| 02 | datastructures | Headers, URL, QueryParams, Envelope | DONE |
| 03 | exceptions | Eccezioni HTTP/WS | DONE |
| 04 | server | AsgiServer, config, logger, registry | TO-DO |
| 05 | middleware | Sistema middleware, EnvelopeMiddleware | TO-DO |
| 06 | application | AsgiApplication, dispatch | TO-DO |
| 07 | http | Request, Response | DONE |
| 08 | websocket | WebSocket connection | TO-DO |
| 09 | utils | Utilities condivise (url_from_scope, TYTX) | TO-DO |

## Workflow di Implementazione

### Fase 1: Initial (Discussione Preliminare)

1. Creare `XX-name-initial.md` con:
   - Motivazione e contesto
   - Architettura proposta
   - Dipendenze
   - Scope (cosa è incluso, cosa è escluso)

2. Se ci sono domande aperte, creare `XX-name-questions.md`

3. Discutere con l'utente fino a chiarire tutti i dubbi

### Fase 2: Decisions (Decisioni)

1. Documentare le decisioni in `XX-name-decisions.md`
2. Ogni decisione deve avere:
   - Contesto
   - Opzioni considerate
   - Decisione presa
   - Motivazione

### Fase 3: Final (Design Approvato)

1. Creare `XX-name-final.md` con il design definitivo
2. Questo documento è la **source of truth** per l'implementazione
3. Deve contenere:
   - API pubblica completa
   - Docstring dettagliate
   - Esempi d'uso
   - Edge cases

**IMPORTANTE**: Il documento `final.md` richiede **approvazione esplicita** dell'utente prima di procedere all'implementazione.

### Fase 4: Test (Test-First)

1. Scrivere i test basandosi su `final.md`
2. I test devono coprire:
   - Happy path
   - Edge cases
   - Error handling
3. I test devono passare prima di procedere

### Fase 5: Implementazione

1. Implementare seguendo esattamente `final.md`
2. Tutti i test devono passare
3. mypy e ruff devono passare

### Fase 6: Commit

1. Commit con messaggio descrittivo
2. Aggiungere `release_note.md` al blocco
3. Rinominare sotto-modulo con suffisso `-done` (es. `01-config` → `01-config-done`)
4. Quando tutti i sotto-moduli sono `-done`, spostare il blocco in `done/`

## Workflow per Blocchi Complessi

Se un blocco tocca più moduli, viene diviso in sotto-moduli:

```
to-do/04-server-01/
├── 04-server-initial.md      # Overview del blocco
├── 04-server-questions.md    # Domande generali
├── 04-server-decisions.md    # Decisioni generali
├── 01-config/                # Sotto-modulo 1
│   ├── initial.md
│   ├── final.md
│   └── release_note.md
├── 02-logger-done/           # Sotto-modulo 2 (completato)
│   └── ...
└── 03-registry/              # Sotto-modulo 3
    └── ...
```

Ogni sotto-modulo segue lo stesso workflow (initial → questions → decisions → final → test → impl → commit).

## Regole di Approvazione

### Prima di implementare qualsiasi codice:

1. **`initial.md` deve esistere** - descrive cosa vogliamo fare
2. **Domande devono essere risolte** - nessuna ambiguità
3. **`final.md` deve essere approvato** - l'utente deve dire esplicitamente "ok" o "procedi"

### MAI:

- Combinare scrittura docstring + implementazione senza approvazione
- Saltare la fase di test
- Implementare senza `final.md` approvato
- Modificare codice già approvato senza nuova discussione

## Marcatura Stato

- Sotto-modulo in lavorazione: `01-config/`
- Sotto-modulo completato: `01-config-done/`
- Blocco in lavorazione: `to-do/04-server-01/`
- Blocco completato: `done/04-server-01-done/`

## File Speciali

- `initial.md` - Idea e motivazione iniziale
- `questions.md` - Domande aperte (opzionale)
- `decisions.md` - Decisioni prese (opzionale)
- `final.md` - Design approvato, source of truth
- `release_note.md` - Note di rilascio post-implementazione
- `divergenze.md` - Differenze tra piano e implementazione (se ci sono)
- `improvements.md` - Miglioramenti successivi

## Archive

La cartella `archive/` contiene i piani originali scritti prima di adottare questa struttura. Sono mantenuti come riferimento storico ma non sono più la source of truth.

---

**Ultimo aggiornamento**: 2025-11-27
