## Source: plan_2025_12_29/spa-manager/02-worker-pool.md

**Stato**: 📋 DA PROGETTARE
**Priorità**: P2 (Necessario per computazioni pesanti)
**Dipendenze**: SpaManager core
**Data**: 2025-12-30

SpaManager gestisce un pool di processi worker per delegare computazioni pesanti, con **affinità utente**: ogni utente viene sempre assegnato allo stesso worker.

```text
┌─────────────────────────────────────────────────────────────┐
│                      AsgiServer                              │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                   SpaManager                         │    │
│  │                                                      │    │
│  │   Users/Sessions/Pages (in-memory)                  │    │
│  │                                                      │    │
│  │   WorkerPool                                        │    │
│  │   ├── Worker 0 ◄── users hash % N == 0             │    │
│  │   ├── Worker 1 ◄── users hash % N == 1             │    │
│  │   ├── Worker 2 ◄── users hash % N == 2             │    │
│  │   └── Worker 3 ◄── users hash % N == 3             │    │
│  │                                                      │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

```python
def get_worker_for_user(self, identity: str) -> Worker:
    """Ritorna sempre lo stesso worker per un dato utente."""
    worker_index = hash(identity) % len(self._workers)
    return self._workers[worker_index]
```

**Vantaggi affinità**:
- Cache locale per utente nel worker
- Nessun conflitto di stato tra worker
- Predicibile e debuggabile

```python
@dataclass
class WorkerInfo:
    worker_id: int
    process: Process
    queue_in: Queue          # Task da eseguire
    queue_out: Queue         # Risultati
    assigned_users: set[str] # Utenti assegnati (per stats)

class WorkerPool:
    """Pool di worker processes con affinità utente."""

__slots__ = ("_workers", "_num_workers")

def __init__(self, num_workers: int = 4) -> None:
        self._num_workers = num_workers
        self._workers: list[WorkerInfo] = []

async def start(self) -> None:
        """Avvia i worker processes."""
        for i in range(self._num_workers):
            queue_in = Queue()
            queue_out = Queue()
            process = Process(
                target=worker_main,
                args=(i, queue_in, queue_out),
            )
            process.start()
            self._workers.append(WorkerInfo(
                worker_id=i,
                process=process,
                queue_in=queue_in,
                queue_out=queue_out,
                assigned_users=set(),
            ))

async def stop(self) -> None:
        """Ferma tutti i worker."""
        for worker in self._workers:
            worker.queue_in.put(None)  # Segnale di stop
            worker.process.join(timeout=5)
            if worker.process.is_alive():
                worker.process.terminate()

def get_worker(self, identity: str) -> WorkerInfo:
        """Ritorna il worker assegnato all'utente."""
        idx = hash(identity) % self._num_workers
        worker = self._workers[idx]
        worker.assigned_users.add(identity)
        return worker

async def submit(self, identity: str, task: dict) -> Any:
        """Sottomette task al worker dell'utente."""
        worker = self.get_worker(identity)
        task_id = uuid()

worker.queue_in.put({
            "task_id": task_id,
            "identity": identity,
            **task,
        })

# Attendi risultato (async)
        result = await self._wait_result(worker, task_id)
        return result

async def _wait_result(self, worker: WorkerInfo, task_id: str) -> Any:
        """Attende risultato dal worker."""
        # Implementazione con asyncio.Queue o polling
        ...
```

```python
def worker_main(worker_id: int, queue_in: Queue, queue_out: Queue) -> None:
    """Main loop del worker process."""
    while True:
        task = queue_in.get()

if task is None:  # Segnale di stop
            break

task_id = task.pop("task_id")
        identity = task.pop("identity")

try:
            result = execute_task(task)
            queue_out.put({
                "task_id": task_id,
                "success": True,
                "result": result,
            })
        except Exception as e:
            queue_out.put({
                "task_id": task_id,
                "success": False,
                "error": str(e),
            })
```

```python
class SpaManager:
    def __init__(
        self,
        server: AsgiServer,
        num_workers: int = 4,
        # ... altri parametri
    ) -> None:
        self._worker_pool = WorkerPool(num_workers)
        # ...

async def on_startup(self) -> None:
        await self._worker_pool.start()

async def on_shutdown(self) -> None:
        await self._worker_pool.stop()

async def delegate_to_worker(self, identity: str, task: dict) -> Any:
        """Delega task al worker dell'utente."""
        return await self._worker_pool.submit(identity, task)
```

```python
class MyApp(AsgiApplication):

@route("heavy_computation")
    async def heavy_computation(self, data: dict) -> dict:
        """Delega computazione pesante al worker."""
        identity = self.request.auth.get("identity", "anonymous")

result = await self.server.spa_manager.delegate_to_worker(
            identity,
            {"type": "compute", "data": data}
        )

```yaml
spa_manager:
  workers:
    enabled: true
    num_workers: 4          # Default: CPU count
    affinity: user          # user | round_robin | least_loaded
```

| Componente | Effort |
|------------|--------|
| WorkerPool class | 4h |
| Worker process main | 2h |
| Integrazione SpaManager | 2h |
| Tests | 4h |
| **Totale** | ~1.5 giorni |

**Ultimo aggiornamento**: 2025-12-30

