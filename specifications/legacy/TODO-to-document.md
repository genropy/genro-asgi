# Legacy - Items to Document

This file collects items found in legacy files that still need to be documented in `interview/answers/`.

As items get documented, they are removed from here.
As legacy files are analyzed, they are deleted.

---

## From `genro-asgi-complete-en.md` (DELETED)

### G. Middleware

- [ ] Middleware pattern (wrap handler)
- [ ] apply_middlewares with reversed()
- [ ] Centralized error middleware

### I. Lifespan

- [ ] lifespan.startup / lifespan.shutdown events
- [ ] lifespan.startup.complete / lifespan.shutdown.complete

### K. WebSocket/WSX

- [ ] Delegation to genro_wsx
- [ ] ws_app(scope, receive, send)

### Testing

- [ ] Pattern with ApplicationCommunicator
- [ ] asgiref.testing

---

## From `genro_asgi_execution.md` (DELETED)

Content moved to `specifications/executors.md`.

---

## From `configuration.md` (DELETED)

OBSOLETE - used TOML format, project uses YAML.
Current documentation already in `interview/answers/E-configuration.md`.

---

## From `architecture.md` (28KB) - ANALYZED

### OBSOLETE (ignore)

- Envelope pattern - replaced by BaseRequest/HttpRequest/MsgRequest inheritance

### ALREADY IMPLEMENTED

- Multi-App Dispatcher (`servers/base.py`, `dispatcher.py`)
- Server-App Integration (`utils/binder.py`: ServerBinder, AsgiServerEnabler)
- Lifespan Management (`lifespan.py`)
- Error Handling 404 (`dispatcher.py`, `exceptions.py`)

### J. Executors

Content moved to `specifications/executors.md` (comprehensive analysis).

### Ideas for Future (to evaluate)

#### Streaming Protections (not implemented)

DoS protections for streaming endpoints:
- Max body size (upload)
- Timeouts (read/send/idle)
- Rate limiting (requests/sec, bandwidth)
- Connection limits (per-IP, per-user)

```python
# Example config
streaming_app = StreamingApp(
    max_upload_size=100 * 1024 * 1024,  # 100MB
    upload_timeout=300,
    ws_max_message_size=1 * 1024 * 1024,
    ws_idle_timeout=60,
    rate_limit_requests=100,  # per minute
)
```

#### Multi-Port Orchestration (possible, not documented)

Multiple servers on different ports in same process:

```python
public_server = AsgiServer()   # Port 80
admin_server = AsgiServer()    # Port 9090 (VPN)
ops_server = AsgiServer()      # Port 9100 (metrics)
```

#### Workload Separation Pattern (supported, to document)

Mount different app types for different workloads:

```
AsgiServer
├── /api/* → BusinessApp (full middleware, auth, DB)
├── /ws/rpc/* → BusinessApp (WSX protocol)
├── /stream/* → StreamingApp (minimal, high throughput)
└── /ws/raw/* → StreamingApp (raw WebSocket)
```

---

## From `legacy-migration/` - MOVED to specifications/wsgi_support/

This is **fundamental** documentation for WSGI support - the server must be able to run legacy WSGI apps.

Moved to `specifications/wsgi_support/` with updated README.

### O. WSGI Support (to create in answers/)

- [ ] How to mount WSGI apps in AsgiServer
- [ ] WsgiToAsgi wrapper usage
- [ ] Migration phases overview
- [ ] Backward compatibility guarantees

---

## To analyze

- [x] `genro_asgi_execution.md` - DELETED
- [x] `configuration.md` - DELETED
- [x] `architecture.md` - DELETED
- [x] `legacy-migration/` - MOVED to specifications/wsgi_support/
- [x] `migration-opinions/` - MOVED to specifications/wsgi_support/

**All legacy files processed!**
