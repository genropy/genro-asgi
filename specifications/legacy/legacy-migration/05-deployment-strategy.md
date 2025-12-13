# Deployment Strategy: Green/Blue/Canary

**Status**: Design Proposal
**Source**: migrate_docs/EN/asgi/arc/architecture.md

---

## Overview

To manage system versions in a controlled manner and allow safe transitions between releases, the orchestrator supports a **Green/Blue/Canary deployment strategy**.

```
                    ┌─────────────────────┐
                    │    Orchestrator     │
                    │  (routes by flag)   │
                    └──────────┬──────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
        ▼                      ▼                      ▼
┌───────────────┐      ┌───────────────┐      ┌───────────────┐
│    GREEN      │      │     BLUE      │      │    CANARY     │
│  (stable)     │      │  (candidate)  │      │ (experimental)│
│   v1.2.3      │      │   v1.3.0-rc   │      │   v1.4.0-dev  │
│               │      │               │      │               │
│  users: 90%   │      │  users: 8%    │      │  users: 2%    │
└───────────────┘      └───────────────┘      └───────────────┘
```

---

## Process Colors

| Color | Purpose | Stability | User Base |
|-------|---------|-----------|-----------|
| **Green** | Stable production | High | Majority (default) |
| **Blue** | Candidate for next release | Medium | Selected testers |
| **Canary** | Experimental features | Low | Developers/beta testers |

---

## User Assignment

Each user has a `flag` field in their record:

```python
# User table field
flag: Literal['gr', 'bl', 'can'] = 'gr'  # Default: green
```

### Assignment Logic

```python
def assign_user_to_color(user_record: dict) -> str:
    """Map user flag to process color."""
    flag = user_record.get('flag', 'gr')
    return {
        'gr': 'green',
        'bl': 'blue',
        'can': 'canary'
    }.get(flag, 'green')


def select_process_for_user(user_id: str, color: str) -> str:
    """Select a process of the specified color."""
    available = [p for p in process_registry if p['color'] == color]
    if not available:
        # Fallback to green if no processes of requested color
        available = [p for p in process_registry if p['color'] == 'green']
    # Load balance among available processes
    return min(available, key=lambda p: len(p['users']))
```

---

## Process Registry

Each process declares its color at registration:

```python
process_registry = {
    'p01': {'color': 'green', 'version': '1.2.3', 'users': ['user_a', 'user_b']},
    'p02': {'color': 'green', 'version': '1.2.3', 'users': ['user_c']},
    'p03': {'color': 'blue', 'version': '1.3.0-rc', 'users': ['user_d']},
    'p04': {'color': 'canary', 'version': '1.4.0-dev', 'users': ['user_e']},
}
```

---

## Deployment Workflows

### Normal Release (Green → Blue → Green)

```
Day 1: Deploy v1.3.0-rc to Blue processes
       - 8% of users (flag='bl') test new version
       - Monitor errors, performance

Day 3: If stable, promote Blue to Green
       - Update Green processes to v1.3.0
       - Blue becomes next candidate slot

Day 5: All users on v1.3.0
```

### Hotfix (Direct to Green)

```
Emergency: Deploy hotfix to all Green processes
           - Blue/Canary unaffected
           - Immediate rollout to 90% of users
```

### Rollback

```
Problem detected in Blue:
  - Stop routing new users to Blue
  - Existing Blue users moved to Green
  - Blue processes revert or shut down
```

---

## Configuration

### Process Startup

```python
# Process declares its color at startup
process = AsgiProcess(
    color='green',      # or 'blue', 'canary'
    version='1.2.3',
    max_users=50
)
process.register_with_orchestrator()
```

### Orchestrator Config

```python
# orchestrator_config.py
DEPLOYMENT_CONFIG = {
    'colors': {
        'green': {'min_processes': 2, 'max_processes': 10},
        'blue': {'min_processes': 1, 'max_processes': 3},
        'canary': {'min_processes': 1, 'max_processes': 1},
    },
    'default_color': 'green',
    'fallback_color': 'green',  # If requested color unavailable
}
```

---

## Monitoring

### Per-Color Metrics

```python
# Track metrics by color
metrics = {
    'green': {
        'requests': 10000,
        'errors': 5,
        'avg_latency_ms': 45,
    },
    'blue': {
        'requests': 800,
        'errors': 2,
        'avg_latency_ms': 52,
    },
    'canary': {
        'requests': 200,
        'errors': 10,  # ⚠️ Higher error rate!
        'avg_latency_ms': 120,
    },
}
```

### Alerts

- **Blue error rate > Green**: Pause Blue rollout
- **Canary error rate spike**: Auto-disable Canary
- **Green capacity low**: Scale up Green processes

---

## User Flag Management

### Admin Interface

```python
# Move user to Blue for testing
update_user(user_id='user_123', flag='bl')

# Move user back to stable
update_user(user_id='user_123', flag='gr')

# Bulk update for beta program
update_users(
    where={'role': 'beta_tester'},
    set={'flag': 'bl'}
)
```

### Self-Service (Optional)

```python
# User opts into beta
if user.can_join_beta:
    user.flag = 'bl'
    user.save()
```

---

## Benefits

| Aspect | Benefit |
|--------|---------|
| **Safe releases** | Test with subset before full rollout |
| **Instant rollback** | Route users back to Green immediately |
| **A/B testing** | Compare performance between versions |
| **Gradual rollout** | Increase Blue percentage over time |
| **Developer access** | Canary for internal testing |
| **Isolation** | Bug in Blue doesn't affect Green |

---

## Relationship with Migration Phases

The Green/Blue/Canary strategy can be used during the WSGI→ASGI migration.

**Actual path**: 0 → 3 → 4 → 5 → 6 → 7 (Phases 1-2 deferred)

| Phase | Green | Blue | Canary |
|-------|-------|------|--------|
| **0** | ASGI wraps WSGI | - | - |
| **3** | Mono-process + WS | - | New features |
| **4** | No daemon (in-process) | - | Testing |
| **5** | Resident pages | - | New features |
| **6** | Stabilization | Testing | Bug fixes |
| **7** | Multi-process stable | Next version | Experimental |

### Phase Details

- **Phase 0**: Single entry point, WSGI wrapped, gnrdaemon unchanged
- **Phase 3**: Mono-process, PageRegistry for WS, ephemeral pages, gnrdaemon unchanged
- **Phase 4**: All registries in-process, gnrdaemon eliminated, fast reconstruction
- **Phase 5**: Resident pages, no reconstruction, HTTP=WS same page
- **Phase 6**: Testing and stabilization, bug fixing
- **Phase 7**: Multi-process, sticky routing, NATS for IPC, horizontal scaling

### Deferred Phases

- **Phase 1**: Sticky sessions (deferred to Phase 7)
- **Phase 2**: NATS alternative (deferred, integrated in Phase 7)

This allows gradual migration with mono-process first, then scaling to multi-process once stable.
