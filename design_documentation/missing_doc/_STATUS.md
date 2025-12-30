# Missing Doc - Status Globale

Materiale sorgente riorganizzato per capitolo di destinazione.

**Ultimo aggiornamento**: 2024-12-30

## Legenda

| Stato | Significato |
|-------|-------------|
| ~~INTEGRATO~~ | Contenuto già in specifications/, può essere eliminato |
| ⚠️ OBSOLETO | Contiene API/nomi vecchi (es: `routedclass` → `routing`) |
| 📋 CAP XX | Da integrare nel capitolo XX |
| ❓ DA VALUTARE | Verificare se ancora rilevante |

---

## Struttura

```
missing_doc/
├── _STATUS.md                      # Questo file
├── 01_introduction/                # Materiale per cap 01 e altri
│   ├── _STATUS.md                  # Dettaglio file
│   ├── genro-routes.md             # ~~INTEGRATO~~ + ⚠️ OBSOLETO
│   ├── lifespan.md                 # ~~INTEGRATO~~
│   ├── request-lifecycle.md        # ~~INTEGRATO~~
│   └── ... (altri per cap futuri)
├── 02_server_foundation/           # Materiale per cap 02 e altri
│   ├── _STATUS.md                  # Dettaglio file
│   ├── genro-toolbox.md            # ~~INTEGRATO~~
│   └── configuration.md            # ~~PARZIALE~~ + 📋 CAP 06
├── 01_introduction.md.ARCHIVED     # File originale (backup)
└── 02_server_foundation.md.ARCHIVED # File originale (backup)
```

---

## Riepilogo per Capitolo

### Capitolo 01 - Introduction

| File | Stato |
|------|-------|
| `01_introduction/genro-routes.md` | ~~INTEGRATO~~ (⚠️ contiene `routedclass` obsoleto) |
| `01_introduction/request-lifecycle.md` | ~~INTEGRATO~~ |

### Capitolo 02 - Server Foundation

| File | Stato |
|------|-------|
| `01_introduction/lifespan.md` | ~~INTEGRATO~~ |
| `02_server_foundation/genro-toolbox.md` | ~~INTEGRATO~~ |
| `02_server_foundation/configuration.md` | ~~PARZIALE~~ |

### Capitolo 03 - Application System

| File | Stato |
|------|-------|
| `01_introduction/applications-guide.md` | 📋 CAP 03 |

### Capitolo 04 - Request/Response

| File | Stato |
|------|-------|
| `01_introduction/requests.md` | 📋 CAP 04 |
| `01_introduction/responses.md` | 📋 CAP 04 |
| `01_introduction/datastructures.md` | 📋 CAP 04 |
| `01_introduction/datastructures-done.md` | 📋 CAP 04 |
| `01_introduction/request-done.md` | 📋 CAP 04 |
| `01_introduction/response-improvements.md` | 📋 CAP 04 |
| `01_introduction/types.md` | 📋 CAP 04 |
| `01_introduction/exceptions.md` | 📋 CAP 04 |
| `01_introduction/transport.md` | 📋 CAP 04 |

### Capitolo 05 - Data and Resources

| File | Stato |
|------|-------|
| `01_introduction/resources.md` | 📋 CAP 05 |

### Capitolo 06 - Security & Middleware

| File | Stato |
|------|-------|
| `02_server_foundation/configuration.md` | 📋 CAP 06 (middleware per-app) |

### Capitolo 07 - Specialized Apps

| File | Stato |
|------|-------|
| `01_introduction/swagger-app.md` | 📋 CAP 07 |
| `01_introduction/openapi-info.md` | 📋 CAP 07 |
| `01_introduction/api-application.md` | 📋 CAP 07 |

### Capitolo 08 - Realtime WSX

| File | Stato |
|------|-------|
| `01_introduction/websockets.md` | 📋 CAP 08 |
| `01_introduction/wsx-handler.md` | 📋 CAP 08 |
| `01_introduction/wsx-subscriptions.md` | 📋 CAP 08 |

### Capitolo 09 - Scalability Architecture

| File | Stato |
|------|-------|
| `01_introduction/executor.md` | 📋 CAP 09 |
| `01_introduction/worker-pool.md` | 📋 CAP 09 |

### Capitolo 10 - SPA Management

| File | Stato |
|------|-------|
| `01_introduction/session.md` | 📋 CAP 10 |
| `01_introduction/context.md` | 📋 CAP 10 |

### Da valutare

| File | Stato |
|------|-------|
| `01_introduction/cli.md` | ❓ Appendice o Cap 02 |
| `01_introduction/utils.md` | ❓ Appendice |

---

## Azioni Post-Completamento

1. **Dopo ogni capitolo**: eliminare i file marcati ~~INTEGRATO~~
2. **File .ARCHIVED**: eliminare quando tutti i contenuti sono stati processati
3. **spec_details/**: stesso trattamento (vedi file con header STATUS)
