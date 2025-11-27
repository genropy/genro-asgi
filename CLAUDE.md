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
