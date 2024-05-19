from django.urls import path

from . import views

urlpatterns = [
    path("csrf", views.get_csrf_token),
    path("test", views.test_api),
]
