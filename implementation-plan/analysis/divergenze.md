# Divergenze tra documento e valutazione finale

Di seguito il riepilogo delle **uniche divergenze** riscontrate tra le raccomandazioni presenti nel documento e il mio parere finale.

---

## ❗ Divergenza 1 — Costruttore “duale” per Headers e QueryParams

### Cosa suggerisce il documento
Il documento considera accettabile la scelta di avere un costruttore con due parametri alternativi:

```python
Headers(raw_headers=...)
Headers(scope=...)
```

Lo stesso per `QueryParams`.

### Mio parere (divergente)
È preferibile **non** avere due modalità nel costruttore, perché introduce ambiguità API e complica i type hints.

### Soluzione consigliata
Separare nettamente le due funzioni:

1. **Costruttore semplice e univoco**  
   ```python
   Headers(raw_headers)
   ```

2. **Funzione module-level per costruire dallo scope**  
   ```python
   headers_from_scope(scope)
   ```

### Motivazione
- API più esplicita e pulita  
- Nessuna ambivalenza nella firma  
- Pattern coerente con la scelta per URL (`url_from_scope`)  
- Migliore manutenibilità e leggibilità  

---

## ✔ Nessun’altra divergenza
Tutte le altre decisioni e raccomandazioni sono pienamente allineate.

