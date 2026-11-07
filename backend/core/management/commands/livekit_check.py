from django.core.management.base import BaseCommand, CommandError

from core import livekit


class Command(BaseCommand):
    help = "Verify LIVEKIT_URL / API key / secret by listing rooms on the LiveKit server."

    def handle(self, *args, **options):
        try:
            rooms = livekit.list_rooms()
        except livekit.LiveKitNotConfigured as exc:
            raise CommandError(str(exc))
        except Exception as exc:
            raise CommandError(f"LiveKit rejected the request: {exc}")
        self.stdout.write(self.style.SUCCESS(f"LiveKit OK - {len(rooms)} active room(s)."))
