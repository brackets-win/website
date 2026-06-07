"""
URL configuration for website project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import TemplateView
from django.views.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path("brackets/", include("brackets.urls")),
]

# Local dev and Fly (uploads on mounted volume at MEDIA_ROOT).
# django.conf.urls.static.static() is a no-op when DEBUG=False, so wire serve explicitly.
if settings.SERVE_MEDIA:
    urlpatterns += [
        re_path(
            r"^media/(?P<path>.*)$",
            serve,
            {"document_root": settings.MEDIA_ROOT},
        ),
    ]

# SPA catch-all: serve index.html for any route not matched above.
# This must be last so that API, admin, media, and static files take priority.
urlpatterns += [
    re_path(
        r"^(?!static/)(?!media/).*$",
        TemplateView.as_view(template_name="index.html"),
    ),
]
