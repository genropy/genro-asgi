# genro-asgi Architecture

## Overview

genro-asgi adopts a **Multi-App Dispatcher** architecture to separate workloads with different characteristics (e.g., transactional RPC vs. high-throughput Streaming).

The core component is the `AsgiServer`, a singleton that acts as a root dispatcher, routing requests to specialized ASGI applications based on path prefixes.

---

## Core Rationale: Workload Separation

The primary goal is to avoid "one size fits all". Different types of traffic require different handling, both for HTTP and WebSocket:

### 1. Business Logic (RPC / REST)
*   **Characteristics**: Complex logic, authentication, database access, structured data.
*   **Protocol**: 
    *   **HTTP**: Request/Response (REST).
    *   **WebSocket**: RPC style (Request/Response over persistent connection).
*   **Abstraction**: Uses the **Envelope** pattern to unify HTTP and WS handling.
*   **Infrastructure**: Needs `EnvelopeRegistry`, detailed logging, full middleware chain.
*   **Paths**: `/api/*`, `/ws/rpc/*`

### 2. Streaming & Fire-and-Forget
*   **Characteristics**: High throughput, long-lived connections, minimal processing.
*   **Protocol**:
    *   **HTTP**: File downloads/uploads.
    *   **WebSocket**: Telemetry (Fire-and-Forget In), Notifications (Fire-and-Forget Out).
*   **Abstraction**: Raw stream handling (no heavy Envelope overhead).
*   **Infrastructure**: Minimal middleware, direct I/O access.
*   **Paths**: `/stream/*`, `/ws/raw/*`

#### Streaming Protections

Streaming endpoints require specific protections against abuse:

| Protection | HTTP Upload | HTTP Download | WebSocket |
|------------|-------------|---------------|-----------|
| **Max body size** | ✓ (configurable) | N/A | Per-message limit |
| **Timeout** | Read timeout | Send timeout | Idle timeout |
| **Rate limit** | Requests/sec | Bandwidth | Messages/sec |
| **Connection limit** | Per-IP | Per-IP | Per-user |

**Configuration example:**

```python
streaming_app = StreamingApp(
    # Upload limits
    max_upload_size=100 * 1024 * 1024,  # 100MB
    upload_timeout=300,                  # 5 min

    # Download limits
    download_timeout=600,                # 10 min
    chunk_size=64 * 1024,                # 64KB chunks

    # WebSocket limits
    ws_max_message_size=1 * 1024 * 1024, # 1MB per message
    ws_idle_timeout=60,                  # 60s idle disconnect
    ws_max_connections_per_user=10,

    # Rate limiting
    rate_limit_requests=100,             # per minute
    rate_limit_bandwidth=10 * 1024 * 1024,  # 10MB/s
)
```

**DoS Protections:**

* **Slowloris**: Read timeout kills slow-sending clients
* **Large payload**: Max body size enforced before processing
* **Connection exhaustion**: Per-IP/per-user connection limits
* **Bandwidth abuse**: Rate limiting on throughput

---

## Architecture Diagram

```
┌─────────────┐         ┌─────────────────────────────────────────────────────────┐
│   Uvicorn   │         │  AsgiServer (Root Dispatcher)                           │
│   :8000     │ ──────► │                                                         │
│             │         │  1. Setup Global Resources (Config, Metrics)            │
│             │         │  2. Dispatch by Path Prefix                             │
│             │         │                                                         │
│             │         │    ┌───────────────────────────────────────────────┐    │
│             │         │    │ /api/*, /ws/rpc/* (Business App)              │    │
│             │         │    │ AuthMW → EnvelopeMW → BusinessLogic           │    │
│             │         │    │ (Unifies HTTP & WS-RPC via Envelope)          │    │
│             │         │    └───────────────────────────────────────────────┘    │
│             │         │                                                         │
│             │         │    ┌───────────────────────────────────────────────┐    │
│             │         │    │ /stream/*, /ws/raw/* (Streaming App)          │    │
│             │         │    │ MinimalMW → RawHandler                        │    │
│             │         │    │ (Optimized for throughput/latency)            │    │
│             │         │    └───────────────────────────────────────────────┘    │
│             │         │                                                         │
└─────────────┘         └─────────────────────────────────────────────────────────┘
```

---

## The Unified Envelope Pattern

For the **Business App**, genro-asgi unifies HTTP and WebSocket-RPC under a single abstraction: the **Envelope**.

*   **HTTP**: Request Body → Envelope Input → Result → Response Body
*   **WebSocket RPC**: JSON Frame → Envelope Input → Result → JSON Frame

This allows sharing:
*   **Authentication/Authorization** logic
*   **Validation** schemas
*   **Business Logic** handlers
*   **Registry** tracking (monitoring active operations regardless of transport)

---

## AsgiServer Implementation

The `AsgiServer` is a lightweight ASGI application that delegates to registered sub-applications.

```python
class AsgiServer:
    def __init__(self):
        self.apps: list[tuple[str, ASGIApp]] = []
        self._executors: dict[str, Executor] = {}
        # Global resources managed here
        self.config = ...
        self.logger = ...

    def mount(self, path: str, app: ASGIApp):
        # Auto-bind server-enabled apps
        if isinstance(app, AsgiServerEnabler):
            app.binder = ServerBinder(self)
        else:
            # Warn if app seems to expect server features but lacks mixin
            if hasattr(app, 'binder'):
                import warnings
                warnings.warn(
                    f"App {app.__class__.__name__} has 'binder' attribute "
                    "but doesn't inherit from AsgiServerEnabler. "
                    "Server features will not be available.",
                    UserWarning
                )
        self.apps.append((path, app))

    async def __call__(self, scope, receive, send):
        # Dispatcher Logic
        path = scope['path']
        for prefix, app in self.apps:
            if path.startswith(prefix):
                # Adjust path for sub-app (strip prefix)
                scope['root_path'] = scope.get('root_path', '') + prefix
                scope['path'] = path[len(prefix):]
                await app(scope, receive, send)
                return

        # 404 Not Found
        ...
```

### Lifespan Management

The Server manages the lifecycle of global resources and propagates lifespan events to sub-apps.

#### Startup Sequence

```python
async def lifespan(self, scope, receive, send):
    message = await receive()
    if message['type'] == 'lifespan.startup':
        try:
            # 1. Server resources first
            await self._init_config()
            await self._init_logger()
            await self._init_executors()

            # 2. Sub-apps in mount order
            for path, app in self.apps:
                if hasattr(app, 'on_startup'):
                    await app.on_startup()

            await send({'type': 'lifespan.startup.complete'})
        except Exception as e:
            await send({'type': 'lifespan.startup.failed', 'message': str(e)})
            return

    # Wait for shutdown signal
    message = await receive()
    if message['type'] == 'lifespan.shutdown':
        # 3. Sub-apps in reverse order
        for path, app in reversed(self.apps):
            if hasattr(app, 'on_shutdown'):
                await app.on_shutdown()

        # 4. Server resources last
        self.shutdown()  # Executors
        await send({'type': 'lifespan.shutdown.complete'})
```

#### Startup/Shutdown Order

| Phase | Startup Order | Shutdown Order |
|-------|---------------|----------------|
| 1 | Config | Sub-apps (reverse) |
| 2 | Logger | Executors |
| 3 | Executors | Logger |
| 4 | Sub-apps (mount order) | Config |

**Principle**: Resources are shut down in reverse order of creation. Sub-apps may depend on server resources, so server shuts down last.

### Error Handling & Fallbacks

#### 404 Not Found

When no mounted app matches the path:

```python
async def __call__(self, scope, receive, send):
    path = scope['path']
    for prefix, app in self.apps:
        if path.startswith(prefix):
            # ... dispatch to app
            return

    # No match - return 404
    if scope['type'] == 'http':
        await send({
            'type': 'http.response.start',
            'status': 404,
            'headers': [(b'content-type', b'application/json')],
        })
        await send({
            'type': 'http.response.body',
            'body': b'{"error": "Not Found"}',
        })
    elif scope['type'] == 'websocket':
        await send({'type': 'websocket.close', 'code': 4404})
```

#### 405 Method Not Allowed

Each sub-app is responsible for its own 405 handling. The dispatcher only routes by path, not by method.

---

## Server-App Integration

Apps can optionally access server resources (config, logger, executors) through a controlled interface.

### ServerBinder

`ServerBinder` provides a controlled API to access server resources. The private `_server` attribute is available for advanced use cases.

```python
class ServerBinder:
    """Controlled interface to access server resources."""

    def __init__(self, server: AsgiServer):
        self._server = server  # Private, for advanced access

    @property
    def config(self):
        return self._server.config

    @property
    def logger(self):
        return self._server.logger

    def executor(
        self,
        name: str = 'default',
        max_workers: int = None,
        initializer: Callable = None,
        initargs: tuple = ()
    ) -> ExecutorDecorator:
        """Get or create a named executor that can be used as decorator."""
        return self._server.executor(name, max_workers, initializer, initargs)
```

### AsgiServerEnabler

`AsgiServerEnabler` is a mixin that enables an app to receive a `ServerBinder`. It does NOT define `__call__` - the app's own `__call__` is used.

```python
class AsgiServerEnabler:
    """Mixin that enables access to AsgiServer via binder."""
    binder: ServerBinder | None = None
```

### Usage Patterns

**Our apps** inherit from `AsgiServerEnabler`:

```python
class BusinessApp(AsgiServerEnabler):
    async def __call__(self, scope, receive, send):
        self.binder.logger.info("Handling request")
        # ... handle request
```

**External apps** (e.g., Starlette) - put `AsgiServerEnabler` LAST in inheritance so the external app's `__call__` is used:

```python
class MyStarletteApp(Starlette, AsgiServerEnabler):
    pass  # Starlette's __call__ is used, but binder is available
```

**Apps without server** work normally (binder is None):

```python
app = BusinessApp()
# app.binder is None - app works standalone
await app(scope, receive, send)  # Works fine
```

---

## Concurrency & Executors

The `AsgiServer` manages executors (process pools) to handle blocking/CPU-bound operations without freezing the async event loop.

### Executor Types

* **ProcessPoolExecutor**: For CPU-bound and blocking I/O tasks. Workers stay alive and can hold preloaded data in memory. For blocking I/O, workers can use internal thread pools (see Multithreaded Workers section).

### Decorator Pattern

Executors are created at module level and used as decorators:

```python
# In your app module
from myproject import server

# Create named process pools (can have multiple isolated pools)
executor_pdf = server.executor(name='pdf', max_workers=2)
executor_ml = server.executor(name='ml', max_workers=4)

@executor_pdf
def generate_pdf(data):
    """CPU-bound: runs in process pool."""
    return create_pdf(data)

@executor_ml
def predict(data):
    """Uses preloaded model in worker memory."""
    return _model.predict(data)

# In async handler - just await the decorated function
async def handle_request(request):
    pdf = await generate_pdf(report_data)
    prediction = await predict(input_data)
```

### Worker Initialization (Preloaded Data)

Workers can load immutable data at startup (models, lookup tables, config) and reuse it across all task executions:

```python
# Worker-side globals
_model = None
_lookup_table = None

def init_ml_worker(model_path, lookup_path):
    """Called once when each worker process starts."""
    global _model, _lookup_table
    _model = load_heavy_model(model_path)      # Load once
    _lookup_table = load_lookup(lookup_path)   # Load once

def predict(data):
    """Uses preloaded data - no loading overhead."""
    features = _lookup_table[data['category']]
    return _model.predict(features)

# Create pool with initializer
executor_ml = server.executor(
    name='ml',
    max_workers=4,
    initializer=init_ml_worker,
    initargs=('/models/v1.pkl', '/data/lookup.json')
)

@executor_ml
def predict(data):
    return _model.predict(data)  # Model already loaded
```

**Use cases for preloaded data:**

* ML models (sklearn, pytorch, tensorflow)
* Large lookup tables / dictionaries
* Compiled regex patterns
* Database connection pools (per-worker)
* Configuration that doesn't change

### Server Implementation

```python
class AsgiServer:
    def __init__(self):
        self._executors: dict[str, ExecutorDecorator] = {}

    def executor(
        self,
        name: str = 'default',
        max_workers: int = None,
        initializer: Callable = None,
        initargs: tuple = ()
    ) -> ExecutorDecorator:
        """
        Get or create a named process pool executor.

        Args:
            name: Pool identifier (allows multiple isolated pools)
            max_workers: Number of workers (default: CPU count)
            initializer: Function called once per worker at startup
            initargs: Arguments passed to initializer
        """
        if name not in self._executors:
            pool = ProcessPoolExecutor(
                max_workers=max_workers,
                initializer=initializer,
                initargs=initargs
            )
            self._executors[name] = ExecutorDecorator(pool)
        return self._executors[name]

    def shutdown(self):
        """Shutdown all executors."""
        for executor in self._executors.values():
            executor.shutdown(wait=True)


```python
class ExecutorDecorator:
    """Wraps a function to run in an executor pool."""

    def __init__(self, pool: Executor | None):
        self.pool = pool

    def __call__(self, func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Bypass mode: if no pool, run synchronously (useful for testing)
            if self.pool is None:
                return func(*args, **kwargs)

            loop = asyncio.get_running_loop()
            # functools.partial for kwargs support
            call = partial(func, *args, **kwargs)
            try:
                return await loop.run_in_executor(self.pool, call)
            except pickle.PicklingError as e:
                raise ExecutorError(
                    f"Cannot serialize arguments for {func.__name__}. "
                    f"Ensure all args are pickle-serializable. Original: {e}"
                ) from e
        return wrapper

    def shutdown(self, wait=True):
        if self.pool is not None:
            self.pool.shutdown(wait=wait)
```

### Executor as SmartRoute Plugin

For endpoints exposed via `smartroute`, we can use a plugin to offload execution to a worker pool. This offers **runtime configuration** (enable/disable offloading per-handler without code changes).

```python
class ExecutorPlugin(BasePlugin):
    """Offloads handler execution to a server-managed executor."""
    
    plugin_code = "executor"

    def __init__(self, router, server_binder: ServerBinder, **config):
        self.binder = server_binder
        super().__init__(router, **config)

    def on_decore(self, route, func, entry):
        # Read executor name from @route(..., executor="pdf")
        # Store in entry metadata
        pass

    def wrap_handler(self, route, entry, call_next):
        def wrapper(*args, **kwargs):
            # Check runtime config
            cfg = self.configuration(entry.name)
            pool_name = cfg.get("pool")
            
            # If disabled or no pool specified, run inline (sync/async)
            if not pool_name or cfg.get("disabled"):
                return call_next(*args, **kwargs)

            # Get executor from server
            executor = self.binder.get_executor(pool_name)
            
            # Run in executor
            return executor.run(call_next, *args, **kwargs)
            
        return wrapper
```

**Usage:**

```python
@route("generate_report", executor="pdf")
def generate_report(self, data):
    # Runs in 'pdf' process pool
    return make_pdf(data)
```

**Runtime Debugging:**

```python
# Force 'generate_report' to run locally (in-process) for debugging
app.router.configure("generate_report", executor_disabled=True)
```
```

### Multiple Pools

You can create multiple isolated pools for different workloads:

```python
# Isolated pools - one slow PDF doesn't block ML predictions
executor_pdf = server.executor(name='pdf', max_workers=2)
executor_ml = server.executor(name='ml', max_workers=4)
executor_image = server.executor(name='image', max_workers=2)
```

### Multithreaded Workers

For I/O-bound tasks (like database operations), workers can use internal thread pools to handle multiple concurrent operations while waiting for I/O:

```python
# Worker globals
_orm_metadata = None
_db_url = None
_thread_pool = None

def init_db_worker(db_url, orm_path, n_threads):
    """Initialize worker with ORM schema and thread pool."""
    global _orm_metadata, _db_url, _thread_pool
    _orm_metadata = load_orm_models(orm_path)  # Schema ORM (preloaded)
    _db_url = db_url                            # Connection string
    _thread_pool = ThreadPoolExecutor(max_workers=n_threads)

def db_transaction(operations):
    """Execute operations in a transaction, using internal thread pool."""
    def _execute():
        conn = connect(_db_url)  # External pooler (e.g., Neon) handles pooling
        try:
            for op in operations:
                conn.execute(_orm_metadata.compile(op))
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()  # Release to external pooler

    return _thread_pool.submit(_execute).result()

# Create executor
executor_db = server.executor(
    name='db',
    max_workers=2,              # 2 processes
    initializer=init_db_worker,
    initargs=(DB_URL, ORM_PATH, 8)  # 8 threads per process
)

@executor_db
def save_order(order_data):
    return db_transaction([
        ('insert', 'orders', order_data),
        ('update', 'inventory', {'product_id': order_data['product_id']}),
    ])
```

**Architecture:**

```text
Main Process (asyncio event loop)
│
├── DB Worker Process 1
│     ├── _orm_metadata (preloaded schema)
│     ├── _db_url (connection string)
│     └── _thread_pool (8 threads)
│           ├── Thread → connect → transaction → close
│           ├── Thread → connect → transaction → close
│           └── ...
│                    ↓
│              External DB Pooler (Neon PgBouncer, etc.)
│
└── DB Worker Process 2
      └── (same structure)
```

**Benefits:**

* ORM schema loaded once per worker (no repeated parsing)
* Multiple threads handle concurrent transactions during I/O waits
* External pooler (Neon, PgBouncer) manages actual connections
* Processes isolate DB work from main async loop

### Remote Executors (Future)

The executor pattern can be extended to support remote workers via NATS or WebSocket:

```python
# Same decorator API, different backend
executor_remote = server.executor(
    'nats',                    # or 'websocket'
    name='heavy',
    subject='tasks.heavy',     # NATS subject
    url='nats://worker:4222'
)

@executor_remote
def heavy_task(data):
    return process(data)  # Executed on remote worker

# Usage remains the same
result = await heavy_task(data)
```

**Remote worker benefits:**

* Horizontal scaling across machines
* Automatic load balancing (NATS)
* Fault tolerance (worker dies, another takes over)
* Same API as local executors

### Constraints

* Decorated functions must be **top-level** (not lambdas or methods)
* Arguments and return values must be **pickle-serializable**
* Preloaded data in workers is **read-only** (changes don't propagate back)
* Workers are **persistent** - started at pool creation, reused for all tasks

### Backpressure & Queue Management

ProcessPoolExecutor has an implicit unbounded queue. To prevent memory exhaustion under high load:

#### Option 1: Semaphore-based Throttling

```python
class ExecutorDecorator:
    def __init__(self, pool: Executor | None, max_pending: int = 100):
        self.pool = pool
        self._semaphore = asyncio.Semaphore(max_pending) if pool else None

    def __call__(self, func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if self.pool is None:
                return func(*args, **kwargs)

            # Block if too many pending tasks
            async with self._semaphore:
                loop = asyncio.get_running_loop()
                call = partial(func, *args, **kwargs)
                return await loop.run_in_executor(self.pool, call)
        return wrapper
```

#### Option 2: Fail-Fast on Overload

```python
async def wrapper(*args, **kwargs):
    if self._semaphore.locked():
        raise ExecutorOverloadError(
            f"Executor '{self.name}' has {self.max_pending} pending tasks. "
            "Try again later."
        )
    # ... proceed with execution
```

### Observability & Metrics

Executors expose metrics for monitoring:

```python
class ExecutorDecorator:
    def __init__(self, pool: Executor | None, name: str = 'default'):
        self.pool = pool
        self.name = name
        # Metrics
        self._tasks_submitted = 0
        self._tasks_completed = 0
        self._tasks_failed = 0
        self._total_duration_ms = 0.0

    @property
    def metrics(self) -> dict:
        """Return current executor metrics."""
        return {
            'name': self.name,
            'pending': self._tasks_submitted - self._tasks_completed - self._tasks_failed,
            'submitted': self._tasks_submitted,
            'completed': self._tasks_completed,
            'failed': self._tasks_failed,
            'avg_duration_ms': (
                self._total_duration_ms / self._tasks_completed
                if self._tasks_completed > 0 else 0
            ),
        }

    def __call__(self, func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            self._tasks_submitted += 1
            start = time.monotonic()
            try:
                result = await self._execute(func, *args, **kwargs)
                self._tasks_completed += 1
                return result
            except Exception:
                self._tasks_failed += 1
                raise
            finally:
                self._total_duration_ms += (time.monotonic() - start) * 1000
        return wrapper
```

#### Server-Level Metrics Endpoint

```python
class AsgiServer:
    def get_executor_metrics(self) -> list[dict]:
        """Return metrics for all executors."""
        return [ex.metrics for ex in self._executors.values()]

# Expose via metrics app
@metrics_app.route("/metrics/executors")
async def executor_metrics(request):
    return JSONResponse(server.get_executor_metrics())
```

#### Prometheus Integration (Optional)

```python
from prometheus_client import Counter, Histogram, Gauge

executor_tasks_total = Counter(
    'executor_tasks_total',
    'Total executor tasks',
    ['executor', 'status']  # status: submitted, completed, failed
)
executor_duration = Histogram(
    'executor_task_duration_seconds',
    'Task execution duration',
    ['executor']
)
executor_pending = Gauge(
    'executor_pending_tasks',
    'Currently pending tasks',
    ['executor']
)
```

### Testing & Robustness

#### Bypass Mode for Testing

The `ExecutorDecorator` supports a **bypass mode** when pool is `None`. This allows testing business logic without starting actual process pools:

```python
# In tests: create decorator without pool
executor_pdf = ExecutorDecorator(None)  # Bypass mode

@executor_pdf
def generate_pdf(data):
    return create_pdf(data)

# Works without pool - runs synchronously
async def test_generate_pdf():
    result = await generate_pdf({"title": "Test"})
    assert result is not None
```

Alternatively, use environment variable to globally bypass all executors:

```python
import os

def executor(...) -> ExecutorDecorator:
    if os.environ.get('GENRO_EXECUTOR_BYPASS') == '1':
        return ExecutorDecorator(None)  # Bypass all pools
    # Normal pool creation...
```

#### Pickling Error Handling

Process pools require all arguments to be pickle-serializable. The decorator catches `PicklingError` and provides a clear error message:

```python
# This will fail with clear error
@executor_pdf
def bad_function(data, callback):  # callbacks can't be pickled!
    return callback(data)

# Error: "Cannot serialize arguments for bad_function.
#         Ensure all args are pickle-serializable."
```

#### Mount Warning

If an app has a `binder` attribute but doesn't inherit from `AsgiServerEnabler`, a warning is raised at mount time:

```python
class MyApp:
    binder = None  # Looks like it wants server features

server.mount("/app", MyApp())
# Warning: "App MyApp has 'binder' attribute but doesn't inherit
#           from AsgiServerEnabler. Server features will not be available."
```

This helps catch configuration errors early, at startup rather than at runtime.

---

## Advanced Usage: Orchestration

Since `AsgiServer` is a standard Python class with encapsulated state, you can instantiate multiple servers in the same process (or controlled by a master process) to bind different ports:

```python
# orchestrator.py
async def main():
    # Public facing API (Port 80)
    public_server = AsgiServer(config="public.ini")
    public_server.mount("/api", BusinessApp())

    # Internal Admin API (Port 9090 - VPN only)
    admin_server = AsgiServer(config="admin.ini")
    admin_server.mount("/admin", AdminApp())
    
    # Metrics/Health (Port 9100)
    ops_server = AsgiServer(config="ops.ini")
    ops_server.mount("/metrics", MetricsApp())

    await asyncio.gather(
        public_server.serve(port=80),
        admin_server.serve(port=9090),
        ops_server.serve(port=9100)
    )
```

This flexibility allows complex deployment topologies without microservices overhead.

---

## Summary of Benefits

1.  **Optimized Performance**: Heavy "Envelope" logic doesn't slow down raw streaming endpoints.
2.  **Code Reuse**: Business logic is written once (Envelope handler) and served via both HTTP and WS.
3.  **Isolation**: A crash or block in the streaming app doesn't necessarily impact the RPC app (depending on async loop health).
4.  **Flexibility**: Can swap out the streaming implementation without touching the business logic.
5.  **Managed Concurrency**: Centralized executors prevent resource exhaustion and simplify async/sync integration.
6.  **Scalability**: Supports multi-port orchestration within a single codebase.
