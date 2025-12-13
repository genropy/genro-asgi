# Page ID Routing

**Status**: Design Proposal
**Source**: migrate_docs/EN/asgi/arc/architecture.md

---

## Current Page ID Format

Currently, page IDs are 22-character unique identifiers:

```
abc123def456ghi789jkl
```

To find which process owns a page, the system must query the global gnrdaemon registry.

---

## Proposed: Page ID with Process Indicator

Embed the process identifier directly in the page ID:

```
abc123def456ghi789|p02
                  └─┬─┘
                process indicator
```

### Benefits

1. **Direct routing** - No global registry lookup needed
2. **Stateless routing** - Any router can decode the destination
3. **Backward compatible** - Old IDs without `|` default to legacy behavior

### Format

```
{base_id}|{process_id}

base_id:     22 characters (existing format)
separator:   | (pipe)
process_id:  p{NN} where NN is zero-padded process number
```

### Examples

```
abc123def456ghi789jkl|p01  → Process 1
xyz789abc123def456ghi|p02  → Process 2
old_style_page_id_here     → Legacy (no indicator)
```

---

## Routing Logic

```python
def route_request(page_id: str) -> int:
    """Extract process number from page_id."""
    if '|' in page_id:
        _, process_part = page_id.rsplit('|', 1)
        if process_part.startswith('p'):
            return int(process_part[1:])
    # Legacy page_id - use fallback routing
    return route_by_user(request.user_id)


def create_page_id(process_id: int) -> str:
    """Generate new page_id with process indicator."""
    base_id = generate_unique_id(22)  # Existing logic
    return f"{base_id}|p{process_id:02d}"
```

---

## Connection ID

Same pattern can apply to connection IDs:

```
conn_abc123def456ghi|p01
```

This allows routing WebSocket messages directly to the correct process.

---

## State Hierarchy

With process indicators embedded in IDs:

| Level | ID Format | Routing |
|-------|-----------|---------|
| **Process** | `p01`, `p02`, ... | From page_id/conn_id |
| **User** | `user_123` | Hash or lookup table |
| **Connection** | `conn_xxx|p01` | Direct from ID |
| **Page** | `page_xxx|p01` | Direct from ID |

---

## Migration Strategy

### Phase 1: Dual Format Support

```python
def parse_page_id(page_id: str) -> tuple[str, int | None]:
    """Parse page_id, return (base_id, process_id or None)."""
    if '|' in page_id:
        base, process_part = page_id.rsplit('|', 1)
        process_id = int(process_part[1:]) if process_part.startswith('p') else None
        return base, process_id
    return page_id, None  # Legacy format
```

### Phase 2: New Pages Use New Format

All newly created pages get process indicator. Old pages continue to work via gnrdaemon fallback.

### Phase 3: Migration Complete

After sufficient time, all active pages have new format. gnrdaemon registry becomes optional.

---

## Considerations

### Process Restart

If process P02 dies and restarts, pages with `|p02` still route correctly. The process must be able to reconstruct page state (from DB or accept reconstruction).

### Process Scaling

Adding P03 doesn't affect existing pages. New pages can be assigned to P03.

Removing P02 requires:
1. Drain existing connections
2. Let pages expire naturally
3. Or migrate pages to another process (state serialization)

### Load Balancing

With sticky routing by page_id, load balancing happens at:
1. **User assignment time** - Which process gets new user
2. **Page creation time** - Which process creates new page

Not at request time (requests are deterministically routed).
