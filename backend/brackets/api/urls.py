from django.urls import path

from . import views

urlpatterns = [
    path("auth/me", views.auth_me),
    path("auth/login", views.auth_login),
    path("auth/logout", views.auth_logout),
    path("brackets", views.brackets_list),
    path("brackets/<int:bracket_id>", views.bracket_detail),
    path("user-brackets", views.user_brackets_list_create),
    path("user-brackets/<int:user_bracket_id>", views.user_bracket_detail),
    path("matchups/<int:matchup_id>", views.matchup_patch),
]
