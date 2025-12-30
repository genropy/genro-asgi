# Configuration System

Genro-ASGI uses a centralized configuration system that can be defined in multiple ways.

## Configuration Sources
1.  **YAML File**: The primary method for defining server settings, active middleware, and application mounts.
2.  **Environment Variables**: Used for overriding specific keys (e.g., ports, database strings).
3.  **CLI Arguments**: Quick parameters for starting the server (e.g., `--reload`, `--port`).

## Config Structure
A standard `config.yaml` is divided into three main sections:
- `server`: Host, port, and debug settings.
- `middleware`: A list of middleware components to enable in the pipeline.
- `apps`: A mapping of mount points to application classes and their initialization arguments.

## Example Config
```yaml
server:
  host: "127.0.0.1"
  port: 8000
  reload: true

middleware:
  auth: true
  cors: true

apps:
  shop:
    module: "apps.shop:ShopApp"
    db_uri: "sqlite:///shop.db"
```
