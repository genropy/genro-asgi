# Bridge contract

**Version**: 0.1 · **Last Updated**: 2026-08-24 · **Status**: 🔴 DA REVISIONARE

What the hosted site must provide and what it may consume: the WSGI callable
behind `WsgiSeam`, the site naming its OWN connection while serving, and the
seams the core names for the site's own data plane — the two dispatchers, the
row class and its capture, the request slot, the newborn process, the vertex's
data. genropy-asgi is the first customer, and it implements this contract so
the core never learns GenroPy's logic.
