# Claude Revision Instructions for Design Documentation

This document defines the methodology, style, and quality standards for revising the genro-asgi design documentation.

## Purpose

The `design_documentation/specifications/` folder serves as the **source of truth** for the development team. Documents must be:

- **Accurate**: Every statement must be verifiable against the actual codebase
- **Detailed**: Sufficient information for a contributor to understand and modify the system
- **Consistent**: Same terminology, style, and depth across all documents

## Target Audience

**Contributors, not end users.**

Documents should answer: "How does this work internally?" not "How do I use this?"

| Audience | Focus |
| -------- | ----- |
| ❌ End user | API usage, quick examples, getting started |
| ✅ Contributor | Architecture, internals, design decisions, file locations |

## Revision Process

### Step 1: Gather Information

Before revising any document, collect information from multiple sources:

1. **Existing document** - Understand current content and identify gaps
2. **Source code** - Verify accuracy against actual implementation
3. **spec_details/** - Technical micro-decisions and API details
4. **missing_doc/** - Paragraphs identified as missing from specifications
5. **pyproject.toml** - Dependencies, versions, configuration

```text
Sources to check:
├── specifications/<chapter>/          # Current document
├── spec_details/                      # Technical details
├── missing_doc/<chapter>.md           # Missing content analysis
├── src/genro_asgi/                    # Actual implementation
└── pyproject.toml                     # Dependencies and config
```

### Step 2: Identify Issues

Check for:

| Issue Type | Example |
| ---------- | ------- |
| **Factual errors** | "Minimal dependencies" but lists 6 packages |
| **Outdated information** | References to removed classes or changed APIs |
| **Syntax errors in code** | Methods not indented inside class definition |
| **Missing information** | Key components not documented |
| **Wrong audience** | User guide content in contributor docs |
| **Vague statements** | "Uses modern patterns" without specifics |

### Step 3: Restructure Content

Organize documents with this structure:

```markdown
# Title

Brief introduction (1-2 sentences)

## Main Sections

### Subsection with Code

```python
# Actual code from the project, not hypothetical
class RealClass:
    def real_method(self):
        pass
```

### Subsection with Table

| Column 1 | Column 2 | Column 3 |
| -------- | -------- | -------- |
| Data     | Data     | Data     |

## Related Documents

- [Link](path) - Brief description
```

### Step 4: Verify Against Code

Every code example must be:

1. **Syntactically correct** - Will parse without errors
2. **Semantically accurate** - Reflects actual implementation
3. **Complete** - Shows full context (imports, class definition, method)

```python
# ❌ WRONG - Method outside class, missing import
@route()
def hello(self):
    return "Hello"

# ✅ CORRECT - Full context
from genro_asgi import AsgiApplication
from genro_routes import route

class MyApp(AsgiApplication):
    @route("main")
    def hello(self):
        return {"message": "Hello"}
```

## Style Guidelines

### Code Examples

**Always include**:
- File path as comment: `# src/genro_asgi/server.py`
- Imports when relevant
- Full class context for methods
- Type hints as they appear in source

**Format**:
```python
# src/genro_asgi/server.py
class AsgiServer(RoutingClass):
    apps: dict[str, AsgiApplication]

    def __init__(self, server_dir: str | Path | None = None):
        self.config = ServerConfig(server_dir)
```

### Tables

Use tables for:
- Attribute listings with types and descriptions
- Method signatures with parameters
- Comparison of options
- Feature matrices

**Format**:
```markdown
| Attribute | Type | Description |
| --------- | ---- | ----------- |
| `config` | `ServerConfig` | YAML + CLI configuration |
| `router` | `Router` | Root router (genro-routes) |
```

### Correct/Incorrect Examples

When showing patterns, use clear markers:

```python
# ✅ CORRECT: State inside instance
class Server:
    def __init__(self):
        self.apps = {}  # Instance state

# ❌ WRONG: Global state
_apps = {}  # Module-level mutable state
```

### Section Headers

Use hierarchical headers consistently:

```markdown
# Document Title (H1 - only one per document)

## Major Section (H2)

### Subsection (H3)

#### Detail (H4 - use sparingly)
```

### Links and References

**Internal links** (within design_documentation):
```markdown
- [Core Principles](02_core_principles.md)
- [Server Architecture](../02_server_foundation/01_server_architecture.md)
```

**Source file references**:
```markdown
**Source**: `src/genro_asgi/server.py`
```

**External links** (sparingly):
```markdown
See [ASGI specification](https://asgi.readthedocs.io/)
```

## Content Depth by Document Type

### Introduction Documents (01_introduction/)

| Document | Purpose | Depth |
| -------- | ------- | ----- |
| vision_and_goals | Project overview, objectives | High-level with examples |
| core_principles | Architectural decisions | Conceptual with code patterns |
| terminology | Glossary | Detailed definitions with source refs |
| quick_start | Development setup | Step-by-step with commands |

### Architecture Documents (02-10)

- Full technical detail
- Complete code examples from source
- Diagrams where helpful (ASCII art for text docs)
- Design decision rationale

## Quality Checklist

Before completing a revision, verify:

### Accuracy
- [ ] All class names match source code
- [ ] All method signatures match source code
- [ ] All attribute types match source code
- [ ] Dependencies list matches pyproject.toml
- [ ] File paths are correct and exist

### Completeness
- [ ] All major components documented
- [ ] All public APIs covered
- [ ] Lifecycle hooks explained
- [ ] Configuration options listed
- [ ] Error cases mentioned

### Style
- [ ] Consistent header hierarchy
- [ ] Tables properly formatted
- [ ] Code blocks have language specified
- [ ] Links are relative and work
- [ ] No orphan sections

### Contributor Focus
- [ ] Source file locations provided
- [ ] Internal architecture explained
- [ ] Design decisions documented
- [ ] Testing approach mentioned
- [ ] Extension points identified

## Common Patterns

### Documenting a Class

```markdown
### ClassName

Brief description of purpose.

**Source**: `src/genro_asgi/module.py`

```python
class ClassName:
    def __init__(self, param1: Type1, param2: Type2 = default):
        self.attr1 = param1
        self.attr2 = param2
```

**Attributes**:

| Attribute | Type | Description |
| --------- | ---- | ----------- |
| `attr1` | `Type1` | Description |
| `attr2` | `Type2` | Description |

**Methods**:

| Method | Returns | Description |
| ------ | ------- | ----------- |
| `method1()` | `ReturnType` | Description |
```

### Documenting a Pattern

```markdown
### Pattern Name

Description of when and why to use this pattern.

```python
# ✅ CORRECT
class Correct:
    def __init__(self):
        self.state = {}  # Explanation

# ❌ WRONG
class Wrong:
    state = {}  # Why this is wrong
```

**Benefits**:
- Benefit 1
- Benefit 2

**When to use**:
- Situation 1
- Situation 2
```

### Documenting Configuration

```markdown
### Configuration Section

**Location**: `config.yaml`

```yaml
section:
  option1: "value"    # Description
  option2: true       # Description
  option3: 8000       # Description
```

| Option | Type | Default | Description |
| ------ | ---- | ------- | ----------- |
| `option1` | `str` | `"value"` | Description |
| `option2` | `bool` | `false` | Description |
| `option3` | `int` | `8000` | Description |
```

## Error Handling in Documentation

When you find inconsistencies:

1. **Document what the code actually does** (not what docs say it should do)
2. **Note discrepancies** if docs describe planned features
3. **Mark unimplemented features** clearly:

```markdown
### FeatureName (Planned)

> **Status**: Not yet implemented

Description of planned feature...
```

## Revision Summary Template

After completing revisions, provide a summary:

```markdown
## Revision Summary

### document_name.md
- **Before**: Brief description of original state
- **After**: Brief description of improvements
- **Key changes**:
  - Change 1
  - Change 2

### Errors Corrected
1. Error description and fix
2. Error description and fix

### Information Added
1. New section or content
2. New section or content
```

## Maintenance

This document should be updated when:

- New document types are added to specifications
- Style conventions change
- New patterns emerge in the codebase
- Common revision issues are identified

---

**Last Updated**: 2024-12-30
**Applies to**: `design_documentation/specifications/` folder
