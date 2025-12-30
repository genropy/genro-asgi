# Executor

Unified execution subsystem per blocking e CPU-bound tasks.

## Overview

Genro-asgi include pool di esecuzione integrati, a differenza di Starlette.

```python
# Via application
result = await app.executor.run_blocking(func, *args)
result = await app.executor.run_process(func, *args)
```

## Classe Executor

```python
class Executor:
    def __init__(
        self,
        max_threads: int = 40,
        max_processes: int | None = None,  # Default: CPU count
    ): ...

    @property
    def is_running(self) -> bool: ...

    async def startup(self) -> None:
        """Start execution pools. Called on lifespan startup."""

    async def shutdown(self, wait: bool = True) -> None:
        """Shutdown pools. Called on lifespan shutdown."""

    async def run_blocking(self, func: Callable, *args, **kwargs) -> T:
        """Run blocking function in ThreadPoolExecutor."""

    async def run_process(self, func: Callable, *args, **kwargs) -> T:
        """Run CPU-bound function in ProcessPoolExecutor."""
```

## Casi d'Uso

### run_blocking (ThreadPool)

- Legacy database drivers (non-async)
- File system operations
- Blocking network calls
- Synchronous library compatibility

```python
def read_file(path):
    with open(path) as f:
        return f.read()

content = await executor.run_blocking(read_file, "/path/to/file")
```

### run_process (ProcessPool)

- Heavy data processing
- Image/audio transformation
- Compression or hashing
- Numerical computation

```python
def compress_data(data):
    import zlib
    return zlib.compress(data)

compressed = await executor.run_process(compress_data, large_data)
```

**Nota**: `func` deve essere picklable (funzione top-level, non lambda/closure).

## Integrazione con Application

```python
class Application:
    def __init__(self, ...):
        self.executor = Executor()

    async def _handle_lifespan(self, scope, receive, send):
        # startup
        await self.executor.startup()
        # ...
        # shutdown
        await self.executor.shutdown()
```

## Decisioni

- **Thread default 40** - Bilanciamento per I/O bound
- **Process default CPU count** - Ottimale per CPU bound
- **startup/shutdown idempotenti** - Safe chiamare multiple volte
- **RuntimeError se not started** - Fail fast se pool non inizializzato
- **Eccezioni propagate** - Eccezioni da func ritornate al caller
