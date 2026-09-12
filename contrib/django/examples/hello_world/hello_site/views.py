"""The views of the example: the counter, the login and the logout."""

from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponse, HttpResponseBadRequest


def hello(request):
    """Answer ``hello world``, who is here, and how many visits this session has.

    Touching the session is what makes Django mint a session key and send its
    cookie: the worker declares the connection from that key, and the count
    comes back growing only while the pool keeps sending the session to the
    process that holds it.
    """
    visits = request.session.get("visits", 0) + 1
    request.session["visits"] = visits
    name = request.user.get_username() or "nobody"
    return HttpResponse(
        f"hello world\nuser: {name}\nvisits: {visits}\n", content_type="text/plain"
    )


def login_view(request):
    """Log in the pair given in the query string, Django's own way.

    ``?username=admin&password=changeme``. A GET is enough because this example
    has no form and no CSRF middleware; what matters downstream is that
    ``django.contrib.auth.login`` runs, cycles the session key and writes the
    user in the session — which is what the pool's middleware reads.
    """
    user = authenticate(
        request,
        username=request.GET.get("username"),
        password=request.GET.get("password"),
    )
    if user is None:
        return HttpResponseBadRequest("no\n", content_type="text/plain")
    login(request, user)
    return HttpResponse(f"logged in: {user.get_username()}\n", content_type="text/plain")


def logout_view(request):
    """Log out whoever is here, Django's own way."""
    logout(request)
    return HttpResponse("logged out\n", content_type="text/plain")
