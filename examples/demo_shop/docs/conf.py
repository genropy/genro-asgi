"""Sphinx configuration for Demo Shop documentation."""

import os
import sys
from pathlib import Path

# Add sample_shop source directory to path for autodoc
sys.path.insert(0, str(Path(__file__).parent.parent / "sample_shop"))

# Project information
project = "smpub Demo Shop"
copyright = "2025, Genropy Team"
author = "Genropy Team"
release = "0.2.0"
version = "0.2"

# General configuration
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx.ext.todo",
    "sphinx.ext.githubpages",
    "sphinx_autodoc_typehints",
    "myst_parser",  # For Markdown support
    "sphinxcontrib.mermaid",  # For Mermaid diagrams
]

# MyST Parser configuration (Markdown)
myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "substitution",
    "tasklist",
]
myst_heading_anchors = 3

# Treat ```mermaid blocks as mermaid directives
myst_fence_as_directive = ["mermaid"]

# Source files
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

# The master toctree document
master_doc = "index"

# List of patterns to ignore
exclude_patterns = [
    "_build",
    "Thumbs.db",
    ".DS_Store",
]

# HTML output configuration
html_theme = "sphinx_rtd_theme"
html_theme_options = {
    "navigation_depth": 4,
    "collapse_navigation": False,
    "sticky_navigation": True,
    "includehidden": True,
    "titles_only": False,
    "prev_next_buttons_location": "bottom",
    "style_external_links": True,
}

html_static_path = ["_static"]
html_logo = "assets/logo.png" if os.path.exists("assets/logo.png") else None
html_favicon = "assets/logo.png" if os.path.exists("assets/logo.png") else None

# HTML context
html_context = {
    "display_github": True,
    "github_user": "genropy",
    "github_repo": "smpub",
    "github_version": "main",
    "conf_py_path": "/examples/demo_shop/docs/",
}

# Napoleon settings (Google-style docstrings)
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = True
napoleon_use_admonition_for_notes = True
napoleon_use_admonition_for_references = False
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_type_aliases = None
napoleon_attr_annotations = True

# Autodoc settings
autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "special-members": "__init__",
    "undoc-members": True,
    "exclude-members": "__weakref__",
    "show-inheritance": True,
}
autodoc_typehints = "description"
autodoc_typehints_description_target = "documented"

# Intersphinx mapping
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "smpub": ("https://smpub.readthedocs.io/en/latest/", None),
    "smartswitch": ("https://smartswitch.readthedocs.io/en/latest/", None),
}

# Todo extension configuration
todo_include_todos = True

# Language
language = "en"
