"""HTMX-friendly flavour of the genro-builders HTML dialect.

The stock ``HtmlRenderer`` emits attribute names verbatim, so ``hx_get=``
would render as ``hx_get="..."``. This renderer kebab-cases the attribute
families that are hyphenated in HTML (``hx-*``, ``data-*``, ``aria-*``,
``sse-*``, ``ws-*``), letting recipes read like idiomatic HTMX:

    root.button("Load", hx_get="/rows", hx_target="#list")

``Fragment`` + ``render_fragment`` wrap the builder lifecycle for the common
case of a handler that renders one piece of HTML from a closure.
"""

from genro_builders.contrib.html import HtmlBuilder
from genro_builders.contrib.html.html_renderer import HtmlRenderer

_HYPHEN_PREFIXES = ("hx_", "data_", "aria_", "sse_", "ws_")


class HtmxRenderer(HtmlRenderer):
    def adapt_attrs(self, attrs):
        out = super().adapt_attrs(attrs)
        return {
            (key.replace("_", "-") if key.startswith(_HYPHEN_PREFIXES) else key): value
            for key, value in out.items()
        }


class UiBuilder(HtmlBuilder):
    # No _name: registering a second "html" dialect would collide; the
    # inherited name keeps the html_* attribute escapes working.

    @property
    def renderer_html(self):
        return HtmxRenderer(builder=self)


class Fragment(UiBuilder):
    """A builder whose ``main`` is a plain callable — one-off fragments."""

    def __init__(self, build):
        super().__init__()
        self._build = build

    def main(self, root):
        self._build(root)


def render_fragment(build) -> str:
    fragment = Fragment(build)
    fragment.create()
    return fragment.render(target=False, xml=False)


def render_page(build) -> str:
    """Like render_fragment, with the DOCTYPE the dialect does not emit."""
    return "<!DOCTYPE html>\n" + render_fragment(build)
