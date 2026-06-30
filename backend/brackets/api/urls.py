from django.urls import path

from . import streak_views, views

urlpatterns = [
    path("auth/me", views.auth_me),
    path("auth/login", views.auth_login),
    path("auth/register", views.auth_register),
    path("auth/logout", views.auth_logout),
    path("auth/change-password", views.auth_change_password),
    path("brackets", views.brackets_list),
    path("bracket-templates", views.bracket_templates_list),
    path("brackets/<int:bracket_id>", views.bracket_detail),
    path(
        "brackets/<int:bracket_id>/group-results-mode",
        views.bracket_group_results_mode,
    ),
    path(
        "brackets/<int:bracket_id>/materialize-scores",
        views.bracket_materialize_scores,
    ),
    path(
        "brackets/<int:bracket_id>/next-match",
        views.bracket_next_match,
    ),
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
    path("challenges/<int:challenge_id>/teams", views.challenge_teams),
    path(
        "challenges/<int:challenge_id>/leaderboard",
        views.challenge_leaderboard,
    ),
    path(
        "challenges/<int:challenge_id>/stats",
        views.challenge_stats,
    ),
    path(
        "challenges/<int:challenge_id>/poll-votes",
        views.challenge_poll_votes,
    ),
    path("streak-competitions", streak_views.streak_competitions_list_create),
    path(
        "streak-competitions/<int:streak_competition_id>",
        streak_views.streak_competition_detail,
    ),
    path(
        "streak-competitions/<int:streak_competition_id>/questions",
        streak_views.streak_competition_question_create,
    ),
    path("streak-challenges", streak_views.streak_challenges_list_create),
    path("streak-challenges/join", streak_views.streak_challenges_join),
    path(
        "streak-challenges/<int:streak_challenge_id>",
        streak_views.streak_challenge_detail,
    ),
    path(
        "streak-challenges/<int:streak_challenge_id>/leaderboard",
        streak_views.streak_challenge_leaderboard,
    ),
    path(
        "streak-challenges/<int:streak_challenge_id>/stats",
        streak_views.streak_challenge_stats,
    ),
    path(
        "streak-challenges/<int:streak_challenge_id>/awards",
        streak_views.streak_challenge_awards,
    ),
    path(
        "streak-challenges/<int:streak_challenge_id>/knockout",
        streak_views.streak_challenge_knockout,
    ),
    path(
        "streak-challenges/<int:streak_challenge_id>/knockout/start",
        streak_views.streak_challenge_knockout_start,
    ),
    path(
        "streak-challenges/<int:streak_challenge_id>/knockout/setup",
        streak_views.streak_challenge_knockout_setup,
    ),
    path(
        "streak-challenges/<int:streak_challenge_id>/knockout/advance",
        streak_views.streak_challenge_knockout_advance,
    ),
    path(
        "streak-challenges/<int:streak_challenge_id>/players/<int:user_id>/picks",
        streak_views.streak_participant_picks,
    ),
    path("streak-questions/<int:question_id>/pick", streak_views.streak_pick),
    path(
        "streak-questions/<int:question_id>/resolve",
        streak_views.streak_question_resolve,
    ),
    path(
        "streak-questions/<int:question_id>",
        streak_views.streak_question_detail,
    ),
    path("matchups/<int:matchup_id>", views.matchup_patch),
    path(
        "admin/delete-impact/<str:resource>/<int:object_id>",
        views.admin_delete_impact,
    ),
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
    path(
        "admin/brackets/<int:bracket_id>/stages",
        views.admin_bracket_stages_update,
    ),
    path("admin/users", views.admin_users_list),
    path("admin/users/<int:user_id>", views.admin_user_detail),
    path(
        "admin/users/<int:user_id>/reset-password",
        views.admin_user_reset_password,
    ),
]
