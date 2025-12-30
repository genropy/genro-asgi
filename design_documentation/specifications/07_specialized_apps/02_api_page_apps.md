# ApiApplication and PageApplication

These implementation patterns extend `AsgiApplication` to provide specialized behaviors for data and content.

## ApiApplication (Design Pattern)
Focuses on providing clean, data-oriented endpoints.
- **JSON-First**: Automatically handles JSON serialization and sets correct `application/json` headers.
- **Error Handling**: Standardized JSON error objects for API consumers.
- **Validation**: Integration with `genro-tytx` for input validation and typed responses.

## PageApplication (Design Pattern)
Designed for traditional server-side rendering or template-based views.
- **Template Integration**: Support for engines like Jinja2 or Mako.
- **Static Asset Mapping**: Easy linking to application-specific CSS and JS files.
- **Contextual Rendering**: Passing data from Python handlers directly to the template context.
