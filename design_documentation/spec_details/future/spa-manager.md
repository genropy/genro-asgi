# SpaManager

Gestione stato per Single Page Applications con WebSocket.

## Stato

📋 **DA PROGETTARE** - Priorità P1 (Necessario per app interattive)

## Gerarchia 4 Livelli

```text
User (identity)
  └── Connection (browser/device)
        └── Session (master page + iframe)
              └── Page (singola pagina con WebSocket)
```

Ogni livello ha il proprio **TreeDict** per dati.

## Componenti Pianificati

### SpaManager Core

- Gestione gerarchia 4 livelli
- Registry per User, Connection, Session, Page
- TreeDict per dati strutturati
- WebSocket connection management

### Worker Pool

- Pool locale con affinità utente
- Distribuzione task ai worker
- Bilanciamento carico

### ExecutorManager

- Gestione tipi executor
- Evoluzione 3 fasi:
  1. Local executor
  2. Remote executor
  3. Distributed executor

## Storage

### In-memory (v1)

```python
class SpaStorage:
    _users: dict[str, UserState]
    _connections: dict[str, ConnectionState]
    _sessions: dict[str, SessionState]
    _pages: dict[str, PageState]
```

### Future (v2+)

- NATS per messaging distribuito
- Blue-green deployment
- State migration tra istanze

## WebSocket Flow

```
1. Client connects (page_id generato)
2. Auth → User identity
3. Connection tracking
4. Session grouping
5. Page registration
6. Message handling via WSX
7. State sync tra livelli
```

## Dipendenze

- WebSocket base implementato
- WSX Protocol
- TreeDict da genro-bag
- Worker pool system

## Documentazione Dettagliata

Vedi `plan_2025_12_29/spa-manager/` per:
- `01-core.md` - Core architecture
- `02-worker-pool.md` - Worker pool design
- `03-executor-manager.md` - Executor evolution
- `04-storage-futures.md` - Storage e sviluppi futuri

## Effort Stimato

Da definire dopo design dettagliato
