import uuid

from django.conf import settings
from django.db import models


class Subscription(models.Model):
    class Plan(models.TextChoices):
        FREE = "FREE", "Free"
        PRO = "PRO", "Pro"
        MANAGER = "MANAGER", "Manager"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        PAST_DUE = "PAST_DUE", "Past due"
        CANCELED = "CANCELED", "Canceled"
        INACTIVE = "INACTIVE", "Inactive"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscription",
    )
    plan = models.CharField(max_length=12, choices=Plan.choices, default=Plan.FREE)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("user__email",)

    def __str__(self):
        return f"{self.user.email}: {self.plan}/{self.status}"

