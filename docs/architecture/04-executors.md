# Executors

**Version**: 1.0.0
**Status**: SOURCE OF TRUTH
**Last Updated**: 2025-12-03

---

## Overview

Executors handle blocking and CPU-bound operations without freezing the async event loop.

Key features:
- **ProcessPoolExecutor** for CPU-bound work
- **Decorator pattern** for easy usage
- **Worker initialization** for preloaded data
- **Bypass mode** for testing
- **Metrics** for observability

---

## Architecture

```
Main Process (asyncio event loop)
│
├── Executor Pool "pdf" (2 workers)
│     ├── Worker 1 → generate_pdf()
│     └── Worker 2 → generate_pdf()
│
├── Executor Pool "ml" (4 workers)
│     ├── Worker 1 → predict() [with preloaded model]
│     ├── Worker 2 → predict()
│     ├── Worker 3 → predict()
│     └── Worker 4 → predict()
│
└── async handlers await executor results
```

---

## Decorator Pattern

```python
from myproject import server

# Create named process pools
executor_pdf = server.executor(name="pdf", max_workers=2)
executor_ml = server.executor(name="ml", max_workers=4)

@executor_pdf
def generate_pdf(data):
    """CPU-bound: runs in process pool."""
    return create_pdf(data)

@executor_ml
def predict(data):
    """Uses preloaded model in worker memory."""
    return _model.predict(data)

# In async handler - just await
async def handle_request(request):
    pdf = await generate_pdf(report_data)
    prediction = await predict(input_data)
```

---

## Server Integration

### server.executor()

```python
class AsgiServer:
    def __init__(self):
        self._executors: dict[str, ExecutorDecorator] = {}

    def executor(
        self,
        name: str = "default",
        max_workers: int | None = None,
        initializer: Callable | None = None,
        initargs: tuple = (),
    ) -> ExecutorDecorator:
        """
        Get or create a named process pool executor.

        Args:
            name: Pool identifier (allows multiple isolated pools)
            max_workers: Number of workers (default: CPU count)
            initializer: Function called once per worker at startup
            initargs: Arguments passed to initializer

        Returns:
            ExecutorDecorator that can decorate functions
        """
        if name not in self._executors:
            pool = ProcessPoolExecutor(
                max_workers=max_workers,
                initializer=initializer,
                initargs=initargs,
            )
            self._executors[name] = ExecutorDecorator(pool, name)
        return self._executors[name]

    def shutdown(self):
        """Shutdown all executors."""
        for executor in self._executors.values():
            executor.shutdown(wait=True)
```

---

## ExecutorDecorator

```python
class ExecutorDecorator:
    """Wraps a function to run in an executor pool."""

    def __init__(self, pool: Executor | None, name: str = "default"):
        self.pool = pool
        self.name = name

    def __call__(self, func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Bypass mode: if no pool, run synchronously
            if self.pool is None:
                return func(*args, **kwargs)

            loop = asyncio.get_running_loop()
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

---

## Worker Initialization (Preloaded Data)

Workers can load data at startup and reuse across all tasks:

```python
# Worker-side globals
_model = None
_lookup_table = None

def init_ml_worker(model_path, lookup_path):
    """Called once when each worker process starts."""
    global _model, _lookup_table
    _model = load_heavy_model(model_path)
    _lookup_table = load_lookup(lookup_path)

def predict(data):
    """Uses preloaded data - no loading overhead."""
    features = _lookup_table[data["category"]]
    return _model.predict(features)

# Create pool with initializer
executor_ml = server.executor(
    name="ml",
    max_workers=4,
    initializer=init_ml_worker,
    initargs=("/models/v1.pkl", "/data/lookup.json"),
)

@executor_ml
def predict(data):
    return _model.predict(data)  # Model already loaded
```

Use cases:
- ML models (sklearn, pytorch, tensorflow)
- Large lookup tables / dictionaries
- Compiled regex patterns
- Database connection pools (per-worker)
- Configuration that doesn't change

---

## Multiple Pools

Isolated pools for different workloads:

```python
# One slow PDF doesn't block ML predictions
executor_pdf = server.executor(name="pdf", max_workers=2)
executor_ml = server.executor(name="ml", max_workers=4)
executor_image = server.executor(name="image", max_workers=2)
```

---

## Multithreaded Workers

For I/O-bound tasks, workers can use internal thread pools:

```python
# Worker globals
_thread_pool = None

def init_db_worker(db_url, n_threads):
    global _thread_pool
    _thread_pool = ThreadPoolExecutor(max_workers=n_threads)

def db_transaction(operations):
    def _execute():
        conn = connect(db_url)
        try:
            for op in operations:
                conn.execute(op)
            conn.commit()
        finally:
            conn.close()
    return _thread_pool.submit(_execute).result()

executor_db = server.executor(
    name="db",
    max_workers=2,              # 2 processes
    initializer=init_db_worker,
    initargs=(DB_URL, 8),       # 8 threads per process
)
```

---

## Bypass Mode for Testing

```python
# Create decorator without pool
executor_pdf = ExecutorDecorator(None)  # Bypass mode

@executor_pdf
def generate_pdf(data):
    return create_pdf(data)

# Works without pool - runs synchronously
async def test_generate_pdf():
    result = await generate_pdf({"title": "Test"})
    assert result is not None
```

Environment variable bypass:

```python
import os

def executor(...) -> ExecutorDecorator:
    if os.environ.get("GENRO_EXECUTOR_BYPASS") == "1":
        return ExecutorDecorator(None)  # Bypass all pools
    # Normal pool creation...
```

---

## Backpressure & Queue Management

### Semaphore-based Throttling

```python
class ExecutorDecorator:
    def __init__(self, pool, max_pending: int = 100):
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

### Fail-Fast on Overload

```python
async def wrapper(*args, **kwargs):
    if self._semaphore.locked():
        raise ExecutorOverloadError(
            f"Executor '{self.name}' has {self.max_pending} pending tasks."
        )
    # ... proceed
```

---

## Metrics

```python
class ExecutorDecorator:
    def __init__(self, pool, name: str = "default"):
        self.pool = pool
        self.name = name
        self._tasks_submitted = 0
        self._tasks_completed = 0
        self._tasks_failed = 0
        self._total_duration_ms = 0.0

    @property
    def metrics(self) -> dict:
        return {
            "name": self.name,
            "pending": self._tasks_submitted - self._tasks_completed - self._tasks_failed,
            "submitted": self._tasks_submitted,
            "completed": self._tasks_completed,
            "failed": self._tasks_failed,
            "avg_duration_ms": (
                self._total_duration_ms / self._tasks_completed
                if self._tasks_completed > 0 else 0
            ),
        }
```

Server-level metrics:

```python
class AsgiServer:
    def get_executor_metrics(self) -> list[dict]:
        return [ex.metrics for ex in self._executors.values()]
```

---

## Constraints

- Decorated functions must be **top-level** (not lambdas or methods)
- Arguments and return values must be **pickle-serializable**
- Preloaded data in workers is **read-only**
- Workers are **persistent** - started at pool creation, reused for all tasks

---

## Remote Executors (Future)

```python
executor_remote = server.executor(
    "nats",
    name="heavy",
    subject="tasks.heavy",
    url="nats://worker:4222",
)

@executor_remote
def heavy_task(data):
    return process(data)  # Executed on remote worker

result = await heavy_task(data)
```

Benefits:
- Horizontal scaling across machines
- Automatic load balancing (NATS)
- Fault tolerance
- Same API as local executors

---

**Copyright**: Softwell S.r.l. (2025)
**License**: Apache License 2.0
