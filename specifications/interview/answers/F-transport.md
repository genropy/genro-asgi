# F. Transport and Serialization (genro-tytx)

## F.1 What is the serialization layer?

**genro-tytx** handles all data serialization between client and server.

It solves the fundamental problem: JSON loses types (Decimal becomes string, Date becomes string).

## F.2 What types are preserved?

| Python | JavaScript | Wire Format |
|--------|------------|-------------|
| `Decimal` | `Big` (big.js) | `"99.99::N"` |
| `date` | `Date` (midnight UTC) | `"2025-01-15::D"` |
| `datetime` | `Date` | `"2025-01-15T10:30:00.000Z::DHZ"` |
| `time` | `Date` (epoch date) | `"10:30:00.000::H"` |

Native JSON types pass through unchanged.

## F.3 What transports are available?

| Transport | Content-Type | Use Case |
|-----------|--------------|----------|
| JSON | `application/vnd.tytx+json` | Default, debugging |
| MessagePack | `application/vnd.tytx+msgpack` | Performance |
| XML | `application/vnd.tytx+xml` | Legacy systems |

## F.4 How is transport selected?

**Auto-detection from Content-Type header.**

Client chooses transport:
```javascript
// JSON (default)
await fetchTytx('/api/order', { body: data });

// MessagePack
await fetchTytx('/api/order', { body: data, transport: 'msgpack' });
```

Server auto-detects and responds with same transport.
**No code changes needed in handlers.**

## F.5 How does this affect Dispatcher?

Dispatcher uses `asgi_data()` to extract typed parameters:

```python
async def dispatch(self, scope, receive, send):
    # Auto-detects transport, decodes to Python types
    data = await asgi_data(scope, receive)

    # params are Decimal, date, etc. - NOT strings
    result = await handler(**data['body'])

    # Response uses same transport
    await self.send_response(result, data['transport'], send)
```

## F.6 How does this affect Response?

Response uses `to_tytx()` to encode typed results:

```python
async def send_response(self, result, transport, send):
    body = to_tytx(result, transport)
    content_type = f'application/vnd.tytx+{transport}'
    # ... send ASGI response
```

## F.7 Why does MessagePack matter?

For high-frequency operations (live grids, real-time updates):

1. **Smaller payload**: ~30-50% smaller than JSON
2. **Faster parsing**: binary, no string parsing
3. **Same API**: just change `transport` parameter
4. **Transparent**: handlers don't know or care

## F.8 Example: Before vs After TYTX

**Without TYTX** (20 manual conversions):

```python
# Receive: string → Decimal
unit_price = Decimal(json_data['unit_price'])

# Send: Decimal → string
return {'total': str(result['total'])}
```

```javascript
// Send: Big → string
body: { unit_price: orderData.unit_price.toString() }

// Receive: string → Big
const total = new Big(json.total);
```

**With TYTX** (0 conversions):

```python
# Receive: already Decimal
data = await asgi_data(scope, receive)
unit_price = data['body']['unit_price']  # Decimal

# Send: just return
return {'total': total}  # Decimal preserved
```

```javascript
// Send: just pass types
await fetchTytx('/api', { body: { unit_price: new Big('99.99') } });

// Receive: already Big
result.total  // Big, ready to use
```

## F.9 Key functions for genro-asgi

| Function | Input | Output | Used by |
|----------|-------|--------|---------|
| `asgi_data(scope, receive)` | ASGI request | `{body: dict, transport: str}` | Dispatcher |
| `to_tytx(data, transport)` | Python dict | Wire format (str/bytes) | Response |

## F.10 Dependencies

- **genro-tytx** (Python): `pip install genro-tytx`
- **genro-tytx** (JavaScript): `npm install genro-tytx`
- **big.js** (JavaScript): recommended for Decimal
