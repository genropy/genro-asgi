# genro-tytx - Typed Data Interchange

## Purpose

genro-tytx eliminates manual type conversions between Python and JavaScript.
It preserves types (Decimal, date, datetime, time) across the wire.

## Role in genro-asgi

genro-tytx is the **serialization layer** for genro-asgi:

1. **Dispatcher**: extracts typed parameters from request
2. **Response**: encodes typed results for client

## Key Functions

| Function | Purpose | Used by |
|----------|---------|---------|
| `asgi_data(scope, receive)` | Decode request → typed dict | Dispatcher |
| `to_tytx(data, transport)` | Encode response → wire format | Response |
| `from_tytx(encoded, transport)` | Decode wire format → typed dict | (internal) |

## Supported Types

| Python | JavaScript | Wire Format |
|--------|------------|-------------|
| `Decimal` | `Big` (big.js) | `"99.99::N"` |
| `date` | `Date` (midnight UTC) | `"2025-01-15::D"` |
| `datetime` | `Date` | `"2025-01-15T10:30:00.000Z::DHZ"` |
| `time` | `Date` (epoch date) | `"10:30:00.000::H"` |

Native JSON types (string, number, boolean, null, list, dict) pass through unchanged.

## Transports

Three transports available, **auto-detected from Content-Type**:

| Transport | Content-Type | Use Case |
|-----------|--------------|----------|
| JSON | `application/vnd.tytx+json` | Default, human-readable, debugging |
| MessagePack | `application/vnd.tytx+msgpack` | Binary, better performance |
| XML | `application/vnd.tytx+xml` | Legacy XML systems |

### Auto-Detection

The server detects transport from request Content-Type header.
No code changes needed - same handler works with all transports.

```python
# Handler doesn't know or care about transport
async def process_order(unit_price, quantity, discount, ...):
    # unit_price is Decimal (regardless of JSON or MessagePack)
    total = unit_price * quantity - discount
    return {'total': total}  # Decimal preserved in response
```

### Client Transport Selection

```javascript
// JSON (default)
const result = await fetchTytx('/api/order', { body: orderData });

// MessagePack - same API, binary format, better performance
const result = await fetchTytx('/api/order', { body: orderData, transport: 'msgpack' });
```

## Integration Flow

```
Client JS                    genro-asgi                      Handler
    │                            │                              │
    │  fetchTytx(body, transport)│                              │
    │  ─────────────────────────>│                              │
    │  Content-Type: vnd.tytx+X  │                              │
    │                            │                              │
    │                            │  asgi_data(scope, receive)   │
    │                            │  - auto-detects transport    │
    │                            │  - decodes to Python types   │
    │                            │                              │
    │                            │  handler(**params)           │
    │                            │  ──────────────────────────>│
    │                            │                              │
    │                            │  result (Decimal, date...)   │
    │                            │  <──────────────────────────│
    │                            │                              │
    │                            │  to_tytx(result, transport)  │
    │                            │  - uses same transport       │
    │                            │  - encodes Python types      │
    │                            │                              │
    │  response                  │                              │
    │  <─────────────────────────│                              │
    │  (auto-decoded by client)  │                              │
```

## Implementation Notes for genro-asgi

### Dispatcher

```python
async def dispatch(self, scope, receive, send):
    # asgi_data auto-detects transport from Content-Type
    data = await asgi_data(scope, receive)

    # params are already typed (Decimal, date, etc.)
    result = await handler(**data['body'])

    # Response encodes with same transport
    await self.send_response(result, data['transport'], send)
```

### Response

```python
async def send_response(self, result, transport, send):
    # to_tytx preserves types in wire format
    body = to_tytx(result, transport)

    # Content-Type matches transport
    content_type = f'application/vnd.tytx+{transport}'

    await send({
        'type': 'http.response.start',
        'status': 200,
        'headers': [(b'content-type', content_type.encode())]
    })
    await send({
        'type': 'http.response.body',
        'body': body if isinstance(body, bytes) else body.encode()
    })
```

## Why MessagePack Matters

MessagePack provides:

1. **Smaller payload**: ~30-50% smaller than JSON
2. **Faster parsing**: binary format, no string parsing
3. **Same API**: just change `transport` parameter
4. **Auto-negotiation**: server responds with same transport as request

For high-frequency RPC calls (e.g., live grids, real-time updates), MessagePack significantly reduces latency and bandwidth.

## Package Info

- **PyPI**: `pip install genro-tytx`
- **npm**: `npm install genro-tytx`
- **License**: Apache 2.0
- **Copyright**: Softwell S.r.l. (2025)
