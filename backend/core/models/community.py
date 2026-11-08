from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from .base import TimeStampedModel
from .tenancy import Condominium, Unit


class Feedback(TimeStampedModel):
    """A resident's rating (1–5 stars) of the estate's services, with an optional comment and the management's reply."""

    class Category(models.TextChoices):
        SECURITY = "security", "Security"
        CLEANLINESS = "cleanliness", "Cleanliness"
        FACILITIES = "facilities", "Facilities"
        MAINTENANCE = "maintenance", "Maintenance"
        MANAGEMENT = "management", "Management office"
        APP = "app", "Elix app"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        NEW = "new", "New"
        IN_PROGRESS = "in_progress", "In progress"
        RESOLVED = "resolved", "Resolved"

    condominium = models.ForeignKey(Condominium, on_delete=models.CASCADE, related_name="feedback")
    unit = models.ForeignKey(Unit, on_delete=models.SET_NULL, null=True, blank=True, related_name="feedback")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="feedback")
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    comment = models.TextField(blank=True, max_length=2000)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    reply = models.TextField(blank=True, max_length=2000, help_text="Shown to the resident in the app.")
    replied_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    replied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "feedback"

    def __str__(self):
        return f"{self.rating}★ {self.get_category_display()} ({self.unit})"
