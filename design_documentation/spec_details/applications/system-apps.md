# System Applications

Applicazioni di sistema incluse in genro-asgi.

## SwaggerApp

Interfaccia Swagger UI per documentazione API.

```python
class SwaggerApp(AsgiApplication):
    openapi_info = {
        "title": "Swagger UI",
        "version": "1.0.0",
    }
```

### Funzionalità

- Serve Swagger UI HTML
- Endpoint `/openapi.json` per spec OpenAPI
- Raccoglie spec da tutte le app montate

### Config

```yaml
apps:
  swagger:
    module: "genro_asgi.applications:SwaggerApp"
```

## GenroApiApp

API di sistema per interazione con il server.

```python
class GenroApiApp(AsgiApplication):
    openapi_info = {
        "title": "Genro API",
        "version": "1.0.0",
    }
```

### Endpoint

- `GET /health` - Health check
- `GET /info` - Server info
- `GET /apps` - Lista app montate
- Endpoint per WebSocket/WSX

### Config

```yaml
apps:
  _genro:
    module: "genro_asgi.applications:GenroApiApp"
```

## StaticFilesApp

Serve file statici (CSS, JS, immagini).

### Stato

Considerato per implementazione futura. Attualmente si usa `ResourceLoader` o middleware dedicato.

## Pattern Comune

Tutte le system apps:
- Estendono `AsgiApplication`
- Hanno `openapi_info` per documentazione
- Si montano in `config.yaml`
- Non richiedono autenticazione speciale (configurabile)
