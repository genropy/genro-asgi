# genro-asgi Implementation Plan

**Status**: DA REVISIONARE
**Version**: 0.2.0
**Last Updated**: 2025-01-27

---

## Vision

genro-asgi is a minimal, stable ASGI foundation with first-class WebSocket support, including the WSX protocol for RPC and subscriptions, and a **unified execution subsystem** for blocking, CPU-bound, and long-running tasks.

## Target Stack

```
SmartPublisher
      │
      ├── CLI (direct)
      ├── genro-api (HTTP, future)
      └── genro-asgi
            ├── HTTP (Request/Response)
            ├── WebSocket (transport)
            ├── Execution (blocking/CPU/tasks)  ← NEW
            └── wsx/ (RPC protocol)
                  │
                  └── NATS (future)
```

## Key Advantages Over Starlette

genro-asgi provides features that Starlette does NOT include:
- **Integrated process executor** for CPU-bound work
- **Unified execution module** for blocking + CPU + long-running jobs
- **TaskManager** for background batch processing
- Stable horizontal scalability with stateless workers

## Implementation Blocks

| Block | File | Description | Dependencies |
|-------|------|-------------|--------------|
| 01 | types.py | ASGI type definitions | None |
| 02 | datastructures.py | Headers, QueryParams, URL, State, Address | 01 |
| 03 | exceptions.py | HTTPException, WebSocketException | None |
| 04 | requests.py | Request class | 01, 02 |
| 05 | responses.py | Response classes | 01, 02 |
| 06 | websockets.py | WebSocket transport | 01, 02, 03 |
| 07 | lifespan.py | Lifespan handling | 01 |
| 08 | applications.py | App class | 01-07 |
| **08b** | **executor.py** | **Executor (run_blocking, run_process)** | **01, 07** |
| **08c** | **tasks.py** | **TaskManager for long-running jobs** | **08b** |
| 09 | middleware/base.py | BaseHTTPMiddleware | 01, 04, 05 |
| 10 | wsx/dispatcher.py | WSX message dispatcher | 06 |
| 11 | wsx/rpc.py | RPC handling | 10 |
| 12 | wsx/subscriptions.py | Channel subscriptions | 10 |

## Principles

1. **Zero dependencies** - stdlib only (orjson optional)
2. **Standalone components** - each usable independently
3. **Full type hints** - mypy strict compatible
4. **Docstring-driven** - module docstring is the source of truth
5. **Test-first** - tests before implementation
6. **Incremental commits** - one block = one commit

## Block Implementation Workflow

**MANDATORY** workflow for each block:

### Step 1: Preliminary Discussion

- Discuss the block's purpose and scope
- Ask questions, explore options
- Make design decisions
- Document decisions in the block's `.md` file

### Step 2: Module Docstring (Source of Truth)

- Write an **extremely detailed and exhaustive** module docstring
- This docstring IS the specification
- Include: purpose, API, usage examples, edge cases, design rationale
- All implementation must conform to this docstring

### Step 3: Write Tests First

- Create test file based on the docstring specification
- Tests define the expected behavior
- Cover: happy path, edge cases, error conditions
- Tests must pass before moving to step 4

### Step 4: Implementation

- Implement the module to pass all tests
- Follow the docstring specification exactly
- Run `pytest`, `mypy`, `ruff` after implementation

### Step 5: Documentation

- Write user-facing documentation for the block
- Add to `docs/` if applicable
- Update README if needed

### Step 6: Commit

- Single commit per block
- Use conventional commit message from block `.md` file
- Ensure all checks pass before commit

## File Structure (Final)

```
src/genro_asgi/
├── __init__.py
├── types.py
├── datastructures.py
├── exceptions.py
├── requests.py
├── responses.py
├── websockets.py
├── lifespan.py
├── applications.py
├── executor.py          ← NEW: Blocking/CPU task pools
├── tasks.py             ← NEW: TaskManager for long-running jobs
├── middleware/
│   ├── __init__.py
│   ├── base.py
│   ├── cors.py
│   └── errors.py
└── wsx/
    ├── __init__.py
    ├── dispatcher.py
    ├── rpc.py
    ├── subscriptions.py
    └── jsonrpc.py
```
