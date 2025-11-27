# Claude Code Instructions - genro-asgi

## Project Context

**genro-asgi** (Genro ASGI) is a minimal, stable ASGI foundation - a framework-agnostic toolkit for building high-performance web services.

**Naming Convention**:
- **Package name**: `genro-asgi` (PyPI package name, with hyphen)
- **Import name**: `genro_asgi` (Python imports, with underscore)
- **Repository**: `genropy/genro-asgi`

### Current Status
- **Development Status**: Alpha (`Development Status :: 3 - Alpha`)
- **Version**: 0.1.0
- **Has Implementation**: Stub implementations (core structure in place)
- **Dependencies**: NONE (Python stdlib only, optional orjson)

### Project Overview

genro-asgi provides:
- Minimal ASGI application core
- Request/Response utilities
- Lifespan event management
- Essential middleware (CORS, errors, compression, static files)
- Zero external dependencies (stdlib only)
- Full type hints

## Repository Information

- **Owner**: genropy
- **Repository**: https://github.com/genropy/genro-asgi
- **Documentation**: https://genro-asgi.readthedocs.io (planned)
- **License**: Apache License 2.0
- **Copyright**: Softwell S.r.l. (2025)

## Project Structure

```
genro-asgi/
├── src/genro_asgi/
│   ├── __init__.py          # Package exports
│   ├── application.py       # ASGI application core
│   ├── request.py           # Request utilities
│   ├── response.py          # Response classes
│   ├── lifespan.py          # Lifespan management
│   └── middleware/          # Middleware collection
│       ├── __init__.py
│       ├── cors.py          # CORS middleware
│       ├── errors.py        # Error handling
│       ├── compression.py   # Gzip compression
│       └── static.py        # Static files
├── tests/                   # Test suite
├── docs/                    # Sphinx documentation
├── examples/                # Example applications
├── pyproject.toml          # Package configuration
├── README.md               # Project overview
├── LICENSE                 # Apache 2.0 license
└── CLAUDE.md               # This file
```

## Language Policy

- **Code, comments, and commit messages**: English
- **Documentation**: English (primary)
- **Communication with user**: Italian (per user preference)

## Git Commit Policy

- **NEVER** include Claude as co-author in commits
- **ALWAYS** remove "Co-Authored-By: Claude <noreply@anthropic.com>" line
- Use conventional commit messages following project style

## Development Guidelines

### Core Principles

1. **Zero dependencies**: Only Python stdlib (except optional orjson)
2. **Minimalism**: Essential features only, no bloat
3. **Type safety**: Full type hints throughout
4. **Production-ready**: Stable, tested, documented
5. **Framework-agnostic**: Not tied to any specific framework

### Testing

All code must have tests:
- Unit tests for all classes and functions
- Integration tests for middleware
- Type checking with mypy
- Code coverage > 90%

### Current Implementation Status

**Completed**:
- Project structure
- Package configuration (pyproject.toml)
- Core module stubs (Application, Request, Response, Lifespan)
- Middleware stubs (CORS, Errors, Compression, StaticFiles)
- README and LICENSE

**TODO**:
1. **Implement Application class**:
   - HTTP request handling
   - WebSocket support
   - Routing capabilities
   - Middleware chain

2. **Implement Request class**:
   - Body reading
   - JSON parsing
   - Form data
   - Query parameters

3. **Implement Response classes**:
   - Streaming responses
   - File downloads
   - Redirects

4. **Implement Middleware**:
   - CORS with proper headers
   - Error handling with custom error pages
   - Gzip compression
   - Static file serving

5. **Tests**:
   - Unit tests for all components
   - Integration tests
   - Performance benchmarks

6. **Documentation**:
   - API reference
   - User guide
   - Examples
   - Migration guides

## Design Decisions

1. **Stdlib-only by default**: Optional fast JSON with orjson
2. **Type-safe**: Full type hints, mypy strict mode
3. **ASGI-compliant**: Follow ASGI spec strictly
4. **Minimal abstractions**: Close to ASGI, avoid over-engineering
5. **Apache 2.0 license**: Permissive, business-friendly

## Coding Style Rules (MANDATORY)

### 1. No globals

No global variables at module level (except constants and type aliases).

### 2. No class methods

Avoid `@classmethod`. If factory pattern needed, use module-level functions or alternative patterns.

### 3. Module entry point

Every module with a primary class ends with:

```python
if __name__ == '__main__':
    instance = MyClass(...)
    instance.xxx()
```

### 4. Nested classes: explicit parent with semantic name

When a child class needs reference to parent:

- Pass parent to constructor
- Save with **semantic name**, NOT `self._parent`
- Use `self.application`, `self.request`, `self.connection`, etc.

```python
# ✅ Correct
class Response:
    def __init__(self, request: Request):
        self.request = request  # Semantic name

# ❌ Wrong
class Response:
    def __init__(self, parent):
        self._parent = parent  # Generic, unclear
```

### 5. Simple patterns only

- Always use simple, direct patterns
- For complex patterns → ask for approval before implementing
- Exceptions to these rules → case-by-case approval required

## Implementation Workflow (6 Steps)

For each implementation block:

1. **Preliminary Discussion**: Ask questions, clarify scope, make design decisions
2. **Module Docstring (Source of Truth)**: Write extremely detailed docstring - if code is deleted, must be able to recreate from docstring alone
3. **Write Tests First**: Based on docstring, cover happy path, edge cases, errors
4. **Implementation**: Implement to pass all tests, follow docstring exactly
5. **Documentation**: User-facing docs if applicable
6. **Commit**: One commit per block

## Git Hooks (MANDATORY)

**ALWAYS verify hooks exist at session start:**

```bash
ls -la .git/hooks/pre-commit .git/hooks/pre-push
```

If hooks are missing, create them:

### pre-commit hook

Location: `.git/hooks/pre-commit`
Runs: `ruff check src/` + `mypy src/`

### pre-push hook

Location: `.git/hooks/pre-push`
Runs: `pytest tests/`
Skip with: `SKIP_TESTS=1 git push` (use with caution)

## Development Workflow

**MANDATORY sequence before every push:**

1. **Run pytest locally**

   ```bash
   pytest
   ```

2. **Run ruff locally**

   ```bash
   ruff check .
   ```

3. **Run mypy locally**

   ```bash
   mypy src
   ```

4. **Push only if all pass**

   ```bash
   git push origin main
   ```

**CRITICAL RULES:**

- **NEVER use `--no-verify`** without explicit user authorization
- **ALWAYS investigate** pre-push failures instead of bypassing
- Local testing is FAST (seconds) vs CI is SLOW (minutes)
- "LOCALE PRIMA, CI POI" (Local first, CI after)
- **ALWAYS verify hooks exist** at the start of each session

## Mistakes to Avoid

❌ **DON'T**:
- Add external dependencies without strong justification
- Over-engineer solutions
- Break ASGI spec compliance
- Skip tests when adding features
- Include Claude as co-author in commits
- Use `--no-verify` to bypass pre-push hook without authorization

✅ **DO**:
- Keep implementations minimal and focused
- Follow ASGI specification strictly
- Write tests for all code
- Maintain type safety
- Document public APIs
- Run all checks locally before pushing

## Quick Reference

| File | Purpose |
|------|---------|
| application.py | ASGI application core |
| request.py | Request utilities |
| response.py | Response classes |
| lifespan.py | Lifecycle management |
| middleware/ | Middleware collection |
| __init__.py | Package exports |

## Relationship with Genro Modules

genro-asgi is part of the **Genro Modules** ecosystem:
- Built for **Genro storage** and related projects
- Provides minimal ASGI foundation
- No dependencies on other Genro modules
- Can be used standalone

---

**Copyright**: Softwell S.r.l. (2025)
**License**: Apache License 2.0
**Python**: 3.10+
**Part of**: Genro Modules ecosystem


      IMPORTANT: this context may or may not be relevant to your tasks. You should not respond to this context unless it is highly relevant to your task.
