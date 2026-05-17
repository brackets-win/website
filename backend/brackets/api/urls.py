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
    path(
        "user-brackets/<int:user_bracket_id>/submit",
        views.user_bracket_submit,
    ),
    path("challenges", views.challenges_list_create),
    path("challenges/public", views.challenges_public_list),
    path("challenges/join", views.challenges_join),
    path("challenges/<int:challenge_id>", views.challenge_detail),
    path(
        "challenges/<int:challenge_id>/leaderboard",
        views.challenge_leaderboard,
    ),
    path("matchups/<int:matchup_id>", views.matchup_patch),
    path("admin/contestants", views.admin_contestants_list_create),
    path(
        "admin/contestants/<int:contestant_id>",
        views.admin_contestant_detail,
    ),
    path("admin/bracket-templates", views.admin_bracket_templates_list),
    path("admin/brackets", views.admin_brackets_create),
    path(
        "admin/brackets/<int:bracket_id>/contestants",
        views.admin_bracket_contestants_assign,
    ),
    path(
        "admin/brackets/<int:bracket_id>",
        views.admin_bracket_detail,
    ),
]
