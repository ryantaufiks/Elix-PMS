from django.core.management.base import BaseCommand

from core import privacy


class Command(BaseCommand):
    help = "PDPA: purge visitor personal data older than each condominium's retention period (also runs daily)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Only count what would be purged.")

    def handle(self, *args, dry_run=False, **options):
        for code, counts in privacy.purge_all(dry_run=dry_run).items():
            self.stdout.write(f"{code}: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run: nothing was changed."))
