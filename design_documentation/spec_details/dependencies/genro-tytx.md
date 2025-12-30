# genro-tytx

Type-tagged text encoding per preservare tipi attraverso serializzazione.

## Overview

TYTX (TYped TeXt) permette di preservare tipi Python in stringhe JSON-safe.

## Sintassi

```
valore::TIPO
```

## Tipi Supportati

| Suffix | Python Type | Esempio |
|--------|-------------|---------|
| `::L` | int (long) | `"42::L"` → `42` |
| `::N` | Decimal | `"99.50::N"` → `Decimal("99.50")` |
| `::B` | bool | `"true::B"` → `True` |
| `::D` | date | `"2025-01-15::D"` → `date(2025, 1, 15)` |
| `::DH` | datetime | `"2025-01-15T10:30::DH"` → `datetime(...)` |
| `::DHZ` | datetime (tz) | `"2025-01-15T10:30:00+01:00::DHZ"` → `datetime(...)` |
| `::T` | time | `"10:30:00::T"` → `time(10, 30)` |

## Uso in WSX

```json
{
    "query": {
        "limit": "10::L",
        "active": "true::B"
    },
    "data": {
        "price": "99.50::N",
        "birth": "1990-05-15::D"
    }
}
```

Dopo hydration:
```python
query = {"limit": 10, "active": True}
data = {"price": Decimal("99.50"), "birth": date(1990, 5, 15)}
```

## Funzioni

```python
from genro_tytx import hydrate, dehydrate

# String → Python
value = hydrate("42::L")  # → 42

# Python → String
text = dehydrate(42)  # → "42::L"

# Dict recursive
data = hydrate_dict({"n": "42::L", "nested": {"b": "true::B"}})
```

## Integrazione

WSX parser chiama automaticamente `hydrate_dict()` su query e data.

## Vantaggi

- Tipi preservati attraverso JSON
- Nessuna perdita di precisione (Decimal)
- Date/datetime corretti
- Compatibile con JavaScript client
