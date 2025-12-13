# Current WSGI Production Architecture

**Status**: Reference Document
**Source**: migrate_docs/EN/wsgi/arc/production.md

---

## Overview

The current Genropy production environment uses a multi-process architecture managed by supervisord, with nginx as reverse proxy.

```
                     ┌─────────────────┐
                     │     Client      │
                     └────────┬────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │   Nginx :8080   │
                     │  (reverse proxy)│
                     └────────┬────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
    ┌─────────────────┐             ┌─────────────────┐
    │ Gunicorn :8888  │             │ gnrasync :9999  │
    │   (HTTP/WSGI)   │             │   (WebSocket)   │
    │   5 workers     │             │   (Tornado)     │
    └────────┬────────┘             └────────┬────────┘
             │                               │
             └───────────────┬───────────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │   gnrdaemon     │
                    │  (Pyro server)  │
                    │  (in-memory)    │
                    └─────────────────┘
```

---

## Components

### 1. Nginx (Port 8080)

Entry point for all traffic. Routes by path:

- `/websocket` → gnrasync (9999)
- `/*` → Gunicorn (8888)

```nginx
server {
    listen 8080 default_server;

    # WebSocket
    location /websocket {
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_pass http://127.0.0.1:9999;
    }

    # HTTP
    location / {
        proxy_pass http://127.0.0.1:8888;
    }
}
```

### 2. Gunicorn (Port 8888)

WSGI server handling HTTP requests:

- 5 worker processes
- 120s timeout
- Graceful restart support

```bash
gunicorn --workers 5 --timeout 120 --bind 0.0.0.0:8888 root
```

### 3. gnrasync (Port 9999)

Tornado-based WebSocket server:

- Handles real-time bidirectional communication
- Connected to gnrdaemon for state

### 4. gnrdaemon

Central Pyro server holding in-memory state:

```python
# Registries maintained by gnrdaemon
registries = {
    'global': {...},                    # Global state
    'users': {user_id: {...}},          # Per-user state
    'connections': {conn_id: {...}},    # Per-connection state (22 char ID)
    'pages': {page_id: {...}},          # Per-page state (22 char ID)
}
```

Communication via Pyro (async, one request at a time).

### 5. Async Workers

Background task processing:

- **gnrtaskscheduler** - Scheduled tasks
- **gnrtaskworker** - Task execution

---

## Supervisord Configuration

All processes managed by supervisord:

```ini
[supervisord]
nodaemon=true

[program:gnrdaemon]
command=gnrdaemon main

[program:gunicorn]
command=gunicorn --workers 5 --timeout 120 --bind 0.0.0.0:8888 root

[program:gnrasync]
command=gnrasync -p 9999 main

[program:gnrtaskscheduler]
command=gnrtaskscheduler main

[program:gnrtaskworker]
command=gnrtaskworker main
```

---

## Request Flow

### HTTP Request

```
Client
  │
  ▼
Nginx :8080
  │ proxy_pass
  ▼
Gunicorn :8888
  │
  ▼
Worker Process (ephemeral page)
  │
  ├── Parse request (page_id, user_id)
  │
  ├── Pyro call to gnrdaemon
  │   └── Fetch page/user/connection state
  │
  ├── Execute business logic
  │
  ├── Pyro call to gnrdaemon
  │   └── Save updated state
  │
  └── Return response (page dies)
```

### WebSocket Message

```
Client
  │
  ▼
Nginx :8080 /websocket
  │ proxy_pass (upgrade)
  ▼
gnrasync :9999 (Tornado)
  │
  ├── Maintain persistent WS connection
  │
  ├── On message: Pyro call to gnrdaemon
  │
  └── Push messages to client
```

---

## Limitations of Current Architecture

1. **gnrdaemon bottleneck** - Single Pyro server, one request at a time
2. **Page reconstruction** - Every HTTP request rebuilds page from gnrdaemon
3. **IPC overhead** - Pyro calls for every state access
4. **Separate WS process** - Tornado isolated from Gunicorn workers
5. **No sticky sessions** - Any worker can handle any user

---

## What We Want to Keep

1. **Supervisord** - Process management works well
2. **Nginx** - Reverse proxy pattern (or replace with Uvicorn multi-worker)
3. **Async workers** - Task scheduler/worker pattern
4. **Page/Connection IDs** - 22 char unique identifiers

## What We Want to Change

1. **gnrdaemon** → In-process PageRegistry (eliminate IPC)
2. **Tornado** → Native ASGI WebSocket (unified stack)
3. **Gunicorn** → Uvicorn (ASGI native)
4. **Ephemeral pages** → Resident pages (eliminate reconstruction)
5. **Random routing** → Sticky sessions by user
