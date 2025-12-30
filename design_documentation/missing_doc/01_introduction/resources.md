## Source: initial_specifications/interview/answers/M-resources.md

**A:** Framework internal resources go in `src/genro_asgi/resources/` with subfolders by type. User application static files are separate.

```
src/genro_asgi/
├── resources/           # Framework internal assets
│   ├── html/           # HTML templates
│   │   └── default_index.html
│   ├── css/            # Stylesheets
│   └── js/             # JavaScript
└── ...
```

| Resource Type | Location | Example |
|---------------|----------|---------|
| Framework default pages | `resources/html/` | `default_index.html` |
| Framework CSS | `resources/css/` | Error page styles |
| Framework JS | `resources/js/` | Client utilities |
| Framework logos/images | `resources/images/` | Logo for default page |
| **User app static files** | User's `app_dir` | Served via `StaticSite` |

**Framework resources** (`resources/`):

- Internal to genro-asgi package
- Default pages (welcome, error pages)
- Loaded via `Path(__file__).parent / "resources"`
- NOT served directly to users (embedded in responses)

**User static files** (`StaticSite`):

- External to package
- User's HTML, CSS, JS, images
- Served via HTTP from user's directory
- Configured in `config.yaml`

```python
# In server.py - reading framework resource
from pathlib import Path

@route("root")
def index(self) -> Response:
    html_path = Path(__file__).parent / "resources" / "html" / "default_index.html"
    return HTMLResponse(content=html_path.read_text())
```

- `resources/` is for framework internal assets only
- Subfolders: `html/`, `css/`, `js/`, `images/` as needed
- Resources are read from disk, not served via HTTP
- User static files use `StaticSite` application
- Clean separation: framework resources vs user content

