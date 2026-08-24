# Bridge contract

**Version**: 0.1 · **Last Updated**: 2026-08-24 · **Status**: 🔴 DA REVISIONARE

What the hosted site must provide and what it may consume: the WSGI callable
behind `WsgiSeam`, the site naming its OWN connection while serving, and the
data-plane verbs of the site-to-worker seam. genropy-asgi is the first customer,
and it implements this contract so the core never learns GenroPy's logic.
