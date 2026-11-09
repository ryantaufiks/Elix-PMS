import uuid
from pathlib import Path

from django.db import models

from core.fields import EncryptedTextField

from .base import TimeStampedModel
from .devices import Kiosk
from .tenancy import Condominium


class AssistantSettings(TimeStampedModel):
    """The kiosk AI assistant of one site: whether it is on, how it introduces itself, and its own
    OpenAI key when the site pays for its usage itself (otherwise the platform key is used)."""

    condominium = models.OneToOneField(Condominium, on_delete=models.CASCADE, related_name="assistant")
    enabled = models.BooleanField(default=False, help_text="Show the assistant on this site's kiosks.")
    name = models.CharField(max_length=60, default="Elix Assistant")
    greeting = models.CharField(
        max_length=300, blank=True,
        default="Hello! I can help with directions, facilities and registering your visit. How can I help?",
    )
    languages = models.CharField(
        max_length=200, blank=True, default="English, Bahasa Melayu, Chinese, Tamil, Bahasa Indonesia",
        help_text="Languages to answer in. The assistant replies in the visitor's language.",
    )
    instructions = models.TextField(
        blank=True, help_text="Extra guidance on tone or behaviour, e.g. 'Mention that visitor parking is free for 2 hours.'",
    )
    openai_api_key = EncryptedTextField("OpenAI API key", blank=True, default="",
                                        help_text="Optional: this site's own key. Blank uses the platform key.")

    def __str__(self):
        return f"Assistant of {self.condominium}"


class AssistantModule(TimeStampedModel):
    """A piece of knowledge the assistant may use: directions, facilities and hours, rules, contacts, FAQ…"""

    condominium = models.ForeignKey(Condominium, on_delete=models.CASCADE, related_name="assistant_modules")
    title = models.CharField(max_length=120)
    content = models.TextField()
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "title"]

    def __str__(self):
        return self.title


def _map_path(instance, filename):
    return f"assistant/maps/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


class AssistantMap(TimeStampedModel):
    """A floor plan or site map the assistant can put on the kiosk screen."""

    condominium = models.ForeignKey(Condominium, on_delete=models.CASCADE, related_name="assistant_maps")
    name = models.CharField(max_length=120, help_text="e.g. 'Site map' or 'Tower B lobby, level 1'.")
    description = models.TextField(blank=True, help_text="What it shows, so the assistant knows when to use it.")
    image = models.ImageField(upload_to=_map_path)
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class AssistantSession(models.Model):
    """One conversation at a kiosk, counted for the usage limits. What was said is never stored."""

    class Mode(models.TextChoices):
        PIPELINE = "pipeline", "Speech to text"
        REALTIME = "realtime", "Realtime"

    condominium = models.ForeignKey(Condominium, on_delete=models.CASCADE, related_name="+")
    kiosk = models.ForeignKey(Kiosk, null=True, on_delete=models.SET_NULL, related_name="+")
    mode = models.CharField(max_length=10, choices=Mode.choices)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    turns = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-started_at"]
