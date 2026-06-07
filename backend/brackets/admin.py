from django.contrib import admin

from brackets.models import (
    StreakChallenge,
    StreakCompetition,
    StreakQuestion,
    StreakQuestionChoice,
)
from brackets.utils.streak_scoring import recalculate_streak_competition


class StreakQuestionChoiceInline(admin.TabularInline):
    model = StreakQuestionChoice
    extra = 2
    fields = ("order", "label")
    ordering = ("order", "id")


class StreakQuestionInline(admin.TabularInline):
    model = StreakQuestion
    extra = 0
    fields = ("order", "text", "closes_at", "correct_choice", "resolved_at")
    ordering = ("order", "id")
    show_change_link = True


@admin.register(StreakCompetition)
class StreakCompetitionAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)
    inlines = [StreakQuestionInline]


@admin.register(StreakChallenge)
class StreakChallengeAdmin(admin.ModelAdmin):
    list_display = ("name", "streak_competition", "created_by", "is_public", "created_at")
    list_filter = ("is_public", "streak_competition")
    search_fields = ("name", "join_code")
    raw_id_fields = ("created_by", "streak_competition")


@admin.register(StreakQuestion)
class StreakQuestionAdmin(admin.ModelAdmin):
    list_display = (
        "text",
        "streak_competition",
        "closes_at",
        "correct_choice",
        "resolved_at",
    )
    list_filter = ("streak_competition",)
    search_fields = ("text",)
    inlines = [StreakQuestionChoiceInline]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.correct_choice_id and obj.resolved_at:
            recalculate_streak_competition(obj.streak_competition_id)
