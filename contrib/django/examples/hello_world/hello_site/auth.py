"""The users of the example: two literals and no database.

Django's login machinery needs a user object with a primary key and a password
to derive the session hash from; it does not need that object to come from a
database, and this example has none. The backend answers with an unsaved
``User`` built from the table below, which is enough for
``django.contrib.auth.login`` and for ``get_user`` on every later request.
"""

from django.contrib.auth.models import User

#: username -> (primary key, password). A real project has a database here.
KNOWN_USERS = {"admin": (1, "changeme"), "mario": (2, "changeme")}


class LiteralUserBackend:
    """Authenticates against ``KNOWN_USERS`` and rebuilds the user from it."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        """Answer the user when the pair is one of the two, else None."""
        known = KNOWN_USERS.get(username or "")
        if known is None or known[1] != password:
            return None
        return self.build_user(username, known)

    def get_user(self, user_id):
        """Rebuild the user the session names, by primary key."""
        for username, known in KNOWN_USERS.items():
            if str(known[0]) == str(user_id):
                return self.build_user(username, known)
        return None

    def build_user(self, username, known):
        """One unsaved ``User``: the pk the session carries and the password.

        The password is stored as it is written, not hashed: nothing here
        verifies a hash — ``authenticate`` above compares the two literals — and
        the only other reader is ``get_session_auth_hash``, which signs whatever
        string it finds.
        """
        return User(pk=known[0], username=username, password=known[1])
