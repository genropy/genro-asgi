"""The URLs of the example: the site root, the login and the logout."""

from django.urls import path

from hello_site.views import hello, login_view, logout_view

urlpatterns = [
    path("", hello),
    path("login/", login_view),
    path("logout/", logout_view),
]
