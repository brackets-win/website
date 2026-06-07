from django.urls import include, path

from . import views

urlpatterns = [
    path("csrf", views.get_csrf_token),
    path("test", views.test_api),
    path("api/", include("brackets.api.urls")),
]
