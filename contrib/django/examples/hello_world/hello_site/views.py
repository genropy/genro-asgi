"""The one view of the example."""

from django.http import HttpResponse


def hello(request):
    """Answer ``hello world`` and how many times this session has been here.

    Touching the session is what makes Django mint a session key and send its
    cookie: the worker declares the connection from that key, and the count
    comes back growing only while the pool keeps sending the session to the
    process that holds it.
    """
    visits = request.session.get("visits", 0) + 1
    request.session["visits"] = visits
    return HttpResponse(f"hello world\nvisits: {visits}\n", content_type="text/plain")
