# AsgiApplication: The Building Block

The `AsgiApplication` class is the base for every service or module mounted on the server.

## Core Features
- **Isolation**: Each application operates within its own namespace and base directory.
- **Internal Router**: Managed via the `self.main` attribute, allowing for granular control over application routes.
- **Server Referencing**: Applications can access the parent server for shared resources like storage or registries.

## Lifecycle Hooks
Applications can implement specific hooks to manage their state:
- `on_init(**kwargs)`: Called when the application is instantiated. Receives configuration from the YAML file.
- `on_startup()`: Triggered when the ASGI server starts. Ideal for opening DB connections.
- `on_shutdown()`: Triggered before the server stops. Used for cleaning up resources.

## Example Usage

```python
from genro_asgi import AsgiApplication
from genro_routes import route

class MyService(AsgiApplication):
    def on_init(self, db_uri=None):
        self.db_uri = db_uri

    @route()
    def hello(self):
        return "Hello from Genro-ASGI!"
```
