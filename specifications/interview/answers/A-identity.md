# A. Identity and Purpose

**Date**: 2025-12-13
**Status**: Verified

---

## Question 1: What is genro-asgi today?

**Verified answer**:

genro-asgi is an **ASGI server as an instance with state**, not a function.

### Architectural Principle: Isolation via Instances

Unlike other frameworks (FastAPI, Starlette) that use global functions/apps:

```python
# Other frameworks - global state
app = FastAPI()
app.state.db = ...  # pollutes shared space

# genro-asgi - isolated instances
server = AsgiServer()      # instance with its own state
server.apps["shop"] = ...  # each app is an isolated instance
```

**Benefits**:

- `del server` → everything garbage collected, zero residue
- Clean testing: each test creates fresh instances
- Multi-tenant: same process, different servers
- Hot reload without residue

### Pattern: Dual Parent-Child Relationship

Every object created by the parent maintains a reference to the parent with a semantic name:

```python
# Server creates Dispatcher
self.dispatcher = Dispatcher(self)

# Dispatcher has ref to server
class Dispatcher:
    def __init__(self, server):
        self.server = server  # semantic name, NOT "_parent"
```

This pattern applies to the entire chain: Server → Dispatcher, Server → Router, Server → Lifespan, etc.

### Fundamental Constraint

**Never pollute Python's shared space**:

- NO mutable global variables at module level
- NO `global` keyword
- NO singleton via module
- State always inside instances

**Rule added to**: `~/.claude/CLAUDE.md` (Rule 5) and project `CLAUDE.md`.
