from django.db import models
from django.db.models.functions import Lower
from django.contrib.auth.models import AbstractUser


class UserTier(models.Model):
    name = models.CharField(max_length=50, unique=True)
    min_xp = models.PositiveIntegerField()

    def __str__(self):
        return self.name


class User(AbstractUser):
    xp = models.PositiveIntegerField(default=0)
    tier = models.ForeignKey(
        UserTier, on_delete=models.SET_NULL, null=True, blank=True)
    public_profile = models.BooleanField(default=True)
    must_change_password = models.BooleanField(default=False)

    class Meta(AbstractUser.Meta):
        constraints = [
            models.UniqueConstraint(
                Lower("username"),
                name="user_username_ci_unique",
            ),
        ]

    def __str__(self):
        return self.username
