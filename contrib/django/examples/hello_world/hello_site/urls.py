"""The URLs of the example: the site root and nothing else."""

from django.urls import path

from hello_site.views import hello

urlpatterns = [path("", hello)]
