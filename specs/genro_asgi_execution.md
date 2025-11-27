# Genro-ASGI Execution Architecture

## 1. Overview
Genro-ASGI provides a unified execution subsystem enabling third-party developers to run:
- blocking tasks,
- CPU-bound work,
- long-running background jobs.

This is implemented through:
1. A **Blocking Task Pool** (ThreadPoolExecutor)  
2. A **CPU Task Pool** (ProcessPoolExecutor)  
3. A **TaskManager** for detached long-running operations

---

## 2. Blocking Task Pool

Used for synchronous I/O and non-async libraries.

### API
```python
result = await app.executor.run_blocking(func, *args, **kwargs)
```

### Use cases
- legacy DB drivers  
- file system operations  
- network calls using blocking libraries  
- compatibility with existing synchronous code  

---

## 3. CPU Task Pool

Used for parallel CPU-intensive work.

### API
```python
result = await app.executor.run_process(func, *args, **kwargs)
```

### Use cases
- heavy data processing  
- image/audio transformation  
- compression or hashing  
- numerical computation  

---

## 4. TaskManager (Long-Running Jobs)

Dedicated process pool for long-running or batch jobs.

### API
```python
task_id = app.tasks.submit(job_func, *args, **kwargs)
status = await app.tasks.status(task_id)
result = await app.tasks.result(task_id)
```

### Features
- isolated execution  
- background tasks independent of ASGI workers  
- queryable status  
- scalable process count  
- optional progress reporting  

---

## 5. Separation of Concerns

- ASGI workers stay stateless and lightweight  
- Thread pool isolates blocking calls  
- Process pool handles CPU load  
- TaskManager offloads long tasks  
- Predictable performance under load  

---

## 6. Advantages Over Starlette

Genro-ASGI provides:
- built‑in unified execution model  
- native support for blocking + CPU + long-running jobs  
- stable horizontal scalability with stateless workers  
- a predictable architecture for real‑time and batch workloads  

Starlette does **not** include:
- integrated process executor  
- unified execution module  
- long-running task engine  

---

## 7. Summary

Genro-ASGI includes:
1. **run_blocking()** for sync I/O  
2. **run_process()** for CPU tasks  
3. **TaskManager** for batch jobs  

This makes Genro-ASGI a stronger alternative to Starlette for applications requiring mixed workloads, parallelism, and background processing.
