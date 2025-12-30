# StaticSite Application

`StaticSite` is a specialized application designed for serving static assets, specifically optimized for modern frontend frameworks (React, Vue, Svelte).

## Key Features
- **SPA Routing**: Automatically serves `index.html` for non-file requests, allowing for client-side routing.
- **MIME Type Detection**: Efficiently identifies and serves diverse file types with correct headers.
- **Caching Headers**: Supports configuration for browser caching to improve performance.

## Configuration
In your `config.yaml`, you can mount a `StaticSite` by pointing it to a directory:

```yaml
apps:
  frontend:
    module: "genro_asgi.applications.static_site:StaticSite"
    base_dir: "./dist"
```
