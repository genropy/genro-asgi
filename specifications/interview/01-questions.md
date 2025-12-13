# Domande per definire le specifiche di genro-asgi

**Data**: 2025-12-13
**Scopo**: Chiarire architettura e funzionamento prima di scrivere le specifiche ufficiali

---

## A. IDENTITÀ E SCOPO

1. **Cos'è genro-asgi oggi?**
   - Le vecchie spec parlano di "minimal ASGI layer", "Multi-App Dispatcher", "foundation of Genro ecosystem". Qual è la definizione corretta attuale?

2. **Qual è il rapporto con genro_routes?**
   - Il codice attuale usa `genro_routes.Router` e `RoutedClass`. AsgiServer eredita da `RoutedClass`. È corretto? Questo significa che genro-asgi dipende fortemente da genro_routes?

3. **Qual è il rapporto con genro-toolbox?**
   - Il codice usa `SmartOptions` per la configurazione. È una dipendenza obbligatoria?

---

## B. ARCHITETTURA SERVER

4. **AsgiServer è un singleton o può essere istanziato più volte?**
   - Le vecchie spec parlano di "singleton", ma il codice sembra permettere istanze multiple.

5. **Qual è il flusso di una request HTTP oggi?**
   - Le spec mostrano: `Uvicorn → AsgiServer → Dispatcher → Router → Handler`
   - Ma il codice mostra: `AsgiServer.__call__ → middleware_chain(Dispatcher) → Dispatcher → router.get()`
   - Qual è il flusso corretto?

6. **Come funziona il routing?**
   - Le vecchie spec parlano di "path prefix routing" (`/api/*`, `/stream/*`)
   - Il codice attuale usa `genro_routes.Router` con selettori e `attach_instance`
   - Quale dei due modelli è corretto?

7. **Cosa sono le "apps" oggi?**
   - Config: `apps: {shop: "shop:ShopApp"}`
   - Sono `RoutedClass` attaccate al router? O ASGI apps montate per path?

---

## C. CONFIGURAZIONE

8. **Formato config: TOML o YAML?**
   - Le vecchie spec dicono TOML, il codice usa YAML (`config.yaml`). Quale è il formato ufficiale?

9. **Come si passano parametri alle apps?**
   - Formato deciso nella discussione:
     ```yaml
     apps:
       office: "office:OfficeApp"  # senza parametri
       shop:
         module: "shop:ShopApp"    # con parametri
         db: "shop.db"
     ```
   - Confermi questo formato?

10. **Priorità configurazione?**
    - Le vecchie spec dicono: CLI > ENV > file > defaults
    - Il codice (`_configure`) fa: `DEFAULTS < config.yaml < env_argv < caller_opts`
    - Confermi questa priorità?

---

## D. MIDDLEWARE

11. **Come funziona il sistema middleware oggi?**
    - Auto-registrazione via `__init_subclass__`?
    - Configurazione via `middleware` nel config.yaml?
    - Formato: lista di tuple, lista di dict, o dict flattened?

12. **Quali middleware esistono e sono funzionanti?**
    - CORS, Errors, Static sono tutti implementati e funzionanti?

---

## E. STATIC FILES

13. **Tre modi per servire static files: quali sono attivi?**
    - `StaticSite` (RoutedClass con genro_routes)
    - `StaticFiles` (ASGI app standalone)
    - `StaticFilesMiddleware` (middleware per prefisso)
    - Tutti e tre sono supportati? Quando usare quale?

---

## F. REQUEST/RESPONSE

14. **Gerarchia Request: cosa esiste oggi?**
    - Le spec WSX parlano di: `BaseRequest → HttpRequest, WsxRequest → WsRequest, NatsRequest`
    - Il codice esporta: `BaseRequest`, `HttpRequest`, `MsgRequest`
    - Qual è la struttura corretta?

15. **Response classes: quali esistono?**
    - Il codice esporta: `Response`, `JSONResponse`, `HTMLResponse`, `PlainTextResponse`, `RedirectResponse`, `StreamingResponse`, `FileResponse`
    - Sono tutte funzionanti?

---

## G. LIFESPAN

16. **Come funziona il lifespan oggi?**
    - `ServerLifespan` gestisce startup/shutdown?
    - Le apps montate ricevono eventi lifespan?
    - Ordine: server prima, poi apps in ordine di mount?

---

## H. EXECUTORS

17. **Il sistema executor esiste ed è funzionante?**
    - Le vecchie spec descrivono `ProcessPoolExecutor`, `ExecutorDecorator`, metriche, backpressure...
    - Il codice esporta: `BaseExecutor`, `LocalExecutor`, `ExecutorRegistry`
    - Quanto di questo è implementato vs pianificato?

---

## I. WEBSOCKET

18. **Come funziona WebSocket oggi?**
    - `WebSocket` class in websocket.py
    - Delegazione a genro_wsx o gestione diretta?

---

## J. INTEGRAZIONE SERVER-APP

19. **ServerBinder e AsgiServerEnabler esistono?**
    - Le spec li descrivono per permettere alle apps di accedere a config/logger/executors
    - Il codice esporta entrambi. Sono funzionanti?

---

## K. FUTURO vs PRESENTE

**Cosa è implementato vs cosa è pianificato?**

- WSX protocol (BaseRequest/BaseResponse transport-agnostic)
- NATS integration
- Remote executors
- Envelope pattern
- TaskManager per long-running jobs

---

## L. EXTERNAL APPS INTEGRATION

**Come posso montare app esterne (Starlette, FastAPI) su AsgiServer?**

- Possono accedere alle risorse del server (config, logger, executors)?
- Come funziona `AsgiServerEnabler`?

---

## M. RISORSE E ASSETS

**Dove vanno le risorse statiche del framework (HTML, CSS, JS, loghi)?**

- Pagine di default del server
- Assets interni del framework
- Differenza rispetto alle static files delle app utente

---

## N. CLI

**Come si avvia genro-asgi da riga di comando?**

- C'è un comando CLI?
- Come funziona `python -m genro_asgi`?
- Quali opzioni sono disponibili?

---

## Prossimi passi

1. Rispondere a queste domande una alla volta
2. Consolidare le risposte in `02-answers.md`
3. Usare le risposte come base per riscrivere `01-overview.md`
4. Procedere con architecture/ e guides/
