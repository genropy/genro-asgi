# Executors - Analisi e Stato Attuale

**Stato**: 🔴 DA IMPLEMENTARE
**Ultimo aggiornamento**: 2025-12-13

## Sommario del Problema

Il sistema executor in genro-asgi ha codice esistente ma **non è stato realmente implementato/validato**. Questo documento raccoglie tutto ciò che esiste per avere un quadro chiaro quando affronteremo il tema.

---

## 1. Visione Originale (legacy doc)

Dal file `legacy/genro_asgi_execution.md`, la visione originale prevedeva:

### 1.1 Tre componenti

1. **Blocking Task Pool** (ThreadPoolExecutor)
   - Per I/O sincrono e librerie non-async
   - API: `await app.executor.run_blocking(func, *args, **kwargs)`
   - Use case: legacy DB drivers, file system, network blocking

2. **CPU Task Pool** (ProcessPoolExecutor)
   - Per lavoro CPU-intensive parallelo
   - API: `await app.executor.run_process(func, *args, **kwargs)`
   - Use case: data processing, image/audio, compression, calcoli numerici

3. **TaskManager** (Long-Running Jobs)
   - Per job batch e long-running
   - API:
     ```python
     task_id = app.tasks.submit(job_func, *args, **kwargs)
     status = await app.tasks.status(task_id)
     result = await app.tasks.result(task_id)
     ```
   - Features: esecuzione isolata, stato queryable, progress reporting

### 1.2 Vantaggi dichiarati su Starlette

- Modello di esecuzione unificato built-in
- Supporto nativo per blocking + CPU + long-running
- Architettura predicibile per workload misti

---

## 2. Codice Esistente (NON validato)

Esiste codice in `src/genro_asgi/executors/` ma con API diversa:

### 2.1 Struttura file

```
src/genro_asgi/executors/
├── __init__.py     # Export pubblici
├── base.py         # BaseExecutor ABC
├── local.py        # LocalExecutor (ProcessPoolExecutor)
└── registry.py     # ExecutorRegistry
```

### 2.2 BaseExecutor (ABC)

```python
class BaseExecutor(ABC):
    name: str

    @abstractmethod
    async def submit(self, func: Callable, *args, **kwargs) -> Any

    @abstractmethod
    def shutdown(self, wait: bool = True) -> None

    @property
    @abstractmethod
    def metrics(self) -> dict[str, Any]

    def __call__(self, func: F) -> F:  # Decorator pattern
```

**Note**:
- Usa pattern decorator via `__call__` (wrappa `submit`)
- Richiede metrics con: name, pending, submitted, completed, failed
- Eccezioni: `ExecutorError`, `ExecutorOverloadError`

### 2.3 LocalExecutor

```python
class LocalExecutor(BaseExecutor):
    def __init__(
        self,
        name: str = "default",
        max_workers: int | None = None,
        initializer: Callable | None = None,
        initargs: tuple = (),
        max_pending: int = 100,
        bypass: bool = False,  # Per testing
    )
```

**Features implementate**:
- ProcessPoolExecutor (bypassa GIL)
- Bypass mode per testing (`bypass=True` o `GENRO_EXECUTOR_BYPASS=1`)
- Backpressure via asyncio.Semaphore
- Metrics collection
- Error handling per pickle failures

**Esempio d'uso**:
```python
executor = LocalExecutor(name="pdf", max_workers=2)

@executor
def generate_pdf(data):
    return create_pdf(data)

result = await generate_pdf(report_data)
```

### 2.4 ExecutorRegistry

```python
class ExecutorRegistry:
    def register_factory(self, executor_type: str, factory: Callable) -> None
    def get_or_create(self, name: str, executor_type: str = "local", **kwargs) -> BaseExecutor
    def get(self, name: str) -> BaseExecutor | None
    def shutdown_all(self, wait: bool = True) -> None
    def all_metrics(self) -> list[dict]
```

**Features**:
- Lazy creation con caching
- Factory pattern per tipi custom
- Shutdown centralizzato
- Aggregazione metriche

---

## 3. Gap Analysis: Legacy vs Esistente

| Feature | Legacy Vision | Codice Esistente |
|---------|---------------|------------------|
| ThreadPool (blocking I/O) | `run_blocking()` | ❌ Non presente |
| ProcessPool (CPU) | `run_process()` | ✅ `LocalExecutor.submit()` |
| TaskManager (long-running) | `tasks.submit/status/result` | ❌ Non presente |
| Decorator pattern | Non menzionato | ✅ `__call__` |
| Backpressure | Non menzionato | ✅ Semaphore |
| Bypass mode (testing) | Non menzionato | ✅ Presente |
| Registry | Non menzionato | ✅ `ExecutorRegistry` |
| Accesso via `app.executor` | ✅ Previsto | ❌ Non integrato |

---

## 4. Domande Aperte

### 4.1 Architetturali

1. **Serve ThreadPool separato?**
   - Per blocking I/O potrebbe bastare `asyncio.to_thread()`
   - O serve pool dedicato per isolare carico?

2. **TaskManager è necessario?**
   - Per job batch serve davvero un sistema interno?
   - O meglio delegare a Celery/RQ/etc?

3. **Integrazione con Server/Application**
   - Come si accede? `server.executors`? `app.executor`?
   - Chi gestisce il lifecycle (startup/shutdown)?

### 4.2 Implementative

1. **Il codice esistente è corretto?**
   - Non ci sono test (o non validati)
   - Pattern decorator funziona come atteso?
   - Pickle serialization gestita bene?

2. **Semaphore è sufficiente per backpressure?**
   - O serve qualcosa di più sofisticato?

3. **Metriche: Prometheus integration?**
   - Il codice menziona "optional" ma non c'è

---

## 5. Raccomandazioni

### 5.1 Approccio Minimalista (Consigliato)

1. **Mantenere solo LocalExecutor** (ProcessPool)
   - Copre il caso principale: CPU-bound work
   - Per blocking I/O: usare `asyncio.to_thread()`

2. **Rimuovere visione TaskManager**
   - Troppo complesso per un framework minimale
   - Chi serve job complessi usa strumenti dedicati

3. **Validare e testare codice esistente**
   - Scrivere test per LocalExecutor
   - Verificare integrazione con server lifecycle

### 5.2 Approccio Completo

Se si vuole la visione completa:

1. **Aggiungere ThreadExecutor** per blocking I/O
2. **Implementare TaskManager** con status/result
3. **Integrare con Lifespan** per startup/shutdown
4. **Aggiungere Prometheus metrics**

---

## 6. Idee da architecture.md (da valutare)

Dal documento `legacy/architecture.md` emergono idee aggiuntive sugli executor:

### 6.1 Worker Initialization (Preloaded Data)

**Idea**: Worker che caricano dati immutabili all'avvio e li riusano per tutte le esecuzioni.

```python
# Worker-side globals
_model = None

def init_ml_worker(model_path):
    """Chiamata una volta per worker all'avvio."""
    global _model
    _model = load_heavy_model(model_path)  # Caricato una volta

def predict(data):
    """Usa dati precaricati - nessun overhead di caricamento."""
    return _model.predict(data)

# Creazione pool con initializer
executor_ml = server.executor(
    name='ml',
    max_workers=4,
    initializer=init_ml_worker,
    initargs=('/models/v1.pkl',)
)
```

**Use case**:
- ML models (sklearn, pytorch, tensorflow)
- Large lookup tables / dictionaries
- Compiled regex patterns
- Database connection pools (per-worker)
- Configuration immutabile

**Nota**: Il codice esistente in `LocalExecutor` **già supporta** `initializer` e `initargs`.

### 6.2 Multithreaded Workers

**Idea**: Worker con thread pool interno per task I/O-bound.

```
Main Process (asyncio event loop)
│
├── DB Worker Process 1
│     ├── _orm_metadata (preloaded schema)
│     ├── _db_url (connection string)
│     └── _thread_pool (8 threads)
│           ├── Thread → connect → transaction → close
│           └── ...
│
└── DB Worker Process 2
      └── (same structure)
```

**Benefici**:
- ORM schema caricato una volta per worker
- Multiple thread gestiscono transazioni concorrenti durante I/O wait
- External pooler (Neon, PgBouncer) gestisce connessioni reali
- Processi isolano DB work dal main async loop

**Valutazione**: Potrebbe essere troppo complesso per un framework minimale. Alternativa: lasciare che l'utente gestisca i thread nel proprio `initializer`.

### 6.3 Multiple Isolated Pools

**Idea**: Pool separati per workload diversi, così un task lento non blocca gli altri.

```python
# Pool isolati - un PDF lento non blocca prediction ML
executor_pdf = server.executor(name='pdf', max_workers=2)
executor_ml = server.executor(name='ml', max_workers=4)
executor_image = server.executor(name='image', max_workers=2)
```

**Nota**: `ExecutorRegistry` esistente **già supporta** questo pattern.

### 6.4 Executor come SmartRoute Plugin

**Idea**: Offload handler a pool con configurazione runtime.

```python
class ExecutorPlugin(BasePlugin):
    """Offloads handler execution to a server-managed executor."""

    plugin_code = "executor"

    def wrap_handler(self, route, entry, call_next):
        def wrapper(*args, **kwargs):
            cfg = self.configuration(entry.name)
            pool_name = cfg.get("pool")

            if not pool_name or cfg.get("disabled"):
                return call_next(*args, **kwargs)  # Run inline

            executor = self.binder.get_executor(pool_name)
            return executor.run(call_next, *args, **kwargs)

        return wrapper
```

**Uso**:
```python
@route("generate_report", executor="pdf")
def generate_report(self, data):
    return make_pdf(data)

# Runtime debugging - forza esecuzione locale
app.router.configure("generate_report", executor_disabled=True)
```

**Valutazione**: Interessante per debugging runtime, ma aggiunge complessità.

### 6.5 Remote Executors (Future Vision)

**Idea**: Estendere il pattern a worker remoti via NATS o WebSocket.

```python
executor_remote = server.executor(
    'nats',
    name='heavy',
    subject='tasks.heavy',
    url='nats://worker:4222'
)

@executor_remote
def heavy_task(data):
    return process(data)  # Eseguito su worker remoto

result = await heavy_task(data)  # Stessa API
```

**Benefici dichiarati**:
- Horizontal scaling across machines
- Automatic load balancing (NATS)
- Fault tolerance
- Stessa API dei local executor

**Valutazione**: Fuori scope per framework minimale. Chi serve questo usa Celery/RQ/etc.

### 6.6 Backpressure Strategies

Due opzioni descritte:

**Option 1: Semaphore-based Throttling** (implementato)
```python
async with self._semaphore:
    result = await self._execute(func, *args, **kwargs)
```
Blocca se troppi task pending.

**Option 2: Fail-Fast on Overload**
```python
if self._semaphore.locked():
    raise ExecutorOverloadError(
        f"Executor '{self.name}' has {self.max_pending} pending tasks."
    )
```
Fallisce immediatamente invece di bloccare.

**Valutazione**: Option 1 già implementata. Option 2 potrebbe essere un parametro.

### 6.7 Prometheus Integration

**Idea**: Metriche esportabili per Prometheus.

```python
from prometheus_client import Counter, Histogram, Gauge

executor_tasks_total = Counter(
    'executor_tasks_total',
    'Total executor tasks',
    ['executor', 'status']
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

**Valutazione**: Utile ma opzionale. Il codice esistente ha già metriche base, Prometheus può essere aggiunto sopra.

### 6.8 Server-Level Metrics Endpoint

**Idea**: Endpoint per esporre metriche di tutti gli executor.

```python
class AsgiServer:
    def get_executor_metrics(self) -> list[dict]:
        return [ex.metrics for ex in self._executors.values()]

@metrics_app.route("/metrics/executors")
async def executor_metrics(request):
    return JSONResponse(server.get_executor_metrics())
```

**Nota**: `ExecutorRegistry.all_metrics()` **già implementa** questo.

---

## 7. Sintesi: Cosa Tenere

| Idea | Già Implementato | Da Implementare | Scartare |
|------|------------------|-----------------|----------|
| Worker Initialization | ✅ `initializer/initargs` | - | - |
| Multithreaded Workers | - | - | ⚠️ Troppo complesso |
| Multiple Isolated Pools | ✅ `ExecutorRegistry` | - | - |
| Executor Plugin | - | ❓ Valutare | - |
| Remote Executors | - | - | ❌ Fuori scope |
| Backpressure Semaphore | ✅ Implementato | - | - |
| Backpressure Fail-Fast | - | ❓ Come opzione | - |
| Prometheus Integration | - | ❓ Opzionale | - |
| Server Metrics Endpoint | ✅ `all_metrics()` | - | - |

---

## 8. File Legacy Correlati

- `legacy/genro_asgi_execution.md` - **ELIMINATO** (contenuto integrato qui)
- `legacy/architecture.md` - Sezione Executors integrata qui

---

## 9. Prossimi Passi

Quando si deciderà di implementare gli executors:

1. [ ] Decidere approccio (minimalista vs completo)
2. [ ] Scrivere test per codice esistente
3. [ ] Definire API di integrazione con Server (`server.executor()` vs `ServerBinder.executor()`)
4. [ ] Implementare integrazione Lifespan (shutdown automatico)
5. [ ] Valutare: aggiungere fail-fast backpressure come opzione
6. [ ] Valutare: Executor Plugin per genro-routes
7. [ ] Documentare in answers/J-executors.md
