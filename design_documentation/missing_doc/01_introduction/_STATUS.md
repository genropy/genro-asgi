# Missing Doc - 01_introduction - Status

Materiale estratto da documenti sorgente, organizzato per destinazione.

## Legenda

| Stato | Significato |
|-------|-------------|
| ~~INTEGRATO~~ | Contenuto già in specifications/, può essere eliminato |
| ⚠️ OBSOLETO | Contiene API/nomi vecchi (es: `routedclass` → `routing`) |
| 📋 CAP XX | Da integrare nel capitolo XX |
| ❓ DA VALUTARE | Verificare se ancora rilevante |

---

## File e Stato

### Integrati in Capitolo 01-02 (possono essere eliminati)

| File | Stato | Destinazione |
|------|-------|--------------|
| `genro-routes.md` | ~~INTEGRATO~~ + ⚠️ OBSOLETO | `01/05_genro_routes_the_server_foundation.md` - **ATTENZIONE**: contiene `routedclass` obsoleto |

### Da integrare in capitoli futuri

| File | Stato | Destinazione |
|------|-------|--------------|
| `applications-guide.md` | 📋 CAP 03 | Application System |
| `resources.md` | 📋 CAP 05 | Data and Resources |
| `cli.md` | 📋 CAP 02 o Appendice | Server Foundation / CLI |
| `request-lifecycle.md` | ~~INTEGRATO~~ | Già in `02/04_dispatcher.md` |
| `transport.md` | 📋 CAP 04 | Request/Response |

### WebSocket/WSX (Capitolo 08)

| File | Stato | Destinazione |
|------|-------|--------------|
| `websockets.md` | 📋 CAP 08 | Realtime WSX |
| `wsx-handler.md` | 📋 CAP 08 | Realtime WSX |
| `wsx-subscriptions.md` | 📋 CAP 08 | Realtime WSX |

### Request/Response (Capitolo 04)

| File | Stato | Destinazione |
|------|-------|--------------|
| `requests.md` | 📋 CAP 04 | Request/Response |
| `responses.md` | 📋 CAP 04 | Request/Response |
| `datastructures.md` | 📋 CAP 04 | Request/Response |
| `datastructures-done.md` | 📋 CAP 04 | Request/Response |
| `request-done.md` | 📋 CAP 04 | Request/Response |
| `response-improvements.md` | 📋 CAP 04 | Request/Response |

### Lifecycle/Executor (Capitolo 02/09)

| File | Stato | Destinazione |
|------|-------|--------------|
| `lifespan.md` | ~~INTEGRATO~~ | Già in `02/03_lifecycle.md` |
| `executor.md` | 📋 CAP 09 | Scalability Architecture |
| `worker-pool.md` | 📋 CAP 09 | Scalability Architecture |

### Types/Exceptions (Capitolo 04)

| File | Stato | Destinazione |
|------|-------|--------------|
| `types.md` | 📋 CAP 04 | Request/Response |
| `exceptions.md` | 📋 CAP 04 | Request/Response |

### Specialized Apps (Capitolo 07)

| File | Stato | Destinazione |
|------|-------|--------------|
| `swagger-app.md` | 📋 CAP 07 | Specialized Apps |
| `openapi-info.md` | 📋 CAP 07 | Specialized Apps |
| `api-application.md` | 📋 CAP 07 | Specialized Apps |

### Future/Planned (Capitolo 10)

| File | Stato | Destinazione |
|------|-------|--------------|
| `session.md` | 📋 CAP 10 | SPA Management |
| `context.md` | 📋 CAP 10 | SPA Management |

### Utilities

| File | Stato | Destinazione |
|------|-------|--------------|
| `utils.md` | ❓ DA VALUTARE | Potrebbe essere appendice |

---

## Azioni Post-Revisione

1. Eliminare file marcati ~~INTEGRATO~~
2. Verificare file ⚠️ OBSOLETO contro codice attuale
3. Integrare file 📋 CAP XX nei rispettivi capitoli
4. Valutare file ❓ DA VALUTARE
