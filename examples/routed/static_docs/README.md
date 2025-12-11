# Static Documentation Server

Example of serving Sphinx documentation for all genro-modules using genro-asgi.

## Structure

```
static_docs/
├── genro-asgi.toml    # Configuration file
├── public/            # Landing page
│   └── index.html
└── README.md
```

## Configuration

The `genro-asgi.toml` mounts each module's Sphinx docs:

```toml
[static]
"/storage" = "../../genro-storage/docs/_build/html"
"/tytx" = "../../genro-tytx/docs/_build/html"
"/mail-proxy" = "../../genro-mail-proxy/docs/_build/html"
```

## Usage

```bash
cd examples/static_docs
genro-asgi
```

Then open http://127.0.0.1:8080

## URLs

| URL | Content |
|-----|---------|
| `/` | Landing page with module index |
| `/storage/` | genro-storage Sphinx docs |
| `/tytx/` | genro-tytx Sphinx docs |
| `/mail-proxy/` | genro-mail-proxy Sphinx docs |

## Building Documentation

Before running, ensure Sphinx docs are built:

```bash
cd ../genro-storage/docs && make html
cd ../genro-tytx/docs && make html
cd ../genro-mail-proxy/docs && make html
```
