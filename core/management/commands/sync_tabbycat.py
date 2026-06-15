from django.core.management.base import BaseCommand

from core.models import TabbycatInstance
from core.sync import sync_all, sync_instance


class Command(BaseCommand):
    help = "Pull tournaments and adjudicator private URLs from Tabbycat instance(s)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--instance",
            help="Sync only the instance with this exact name (default: all active).",
        )

    def handle(self, *args, **options):
        log = self.stdout.write
        name = options.get("instance")

        if name:
            try:
                instance = TabbycatInstance.objects.get(name=name)
            except TabbycatInstance.DoesNotExist:
                self.stderr.write(f"No Tabbycat instance named {name!r}.")
                return
            log(f"Syncing {instance.name} ({instance.base_url})…")
            results = {instance.name: sync_instance(instance, log=log)}
        else:
            results = sync_all(log=log)

        if not results:
            self.stdout.write(self.style.WARNING("No active Tabbycat instances to sync."))
            return

        total_links = sum(r["links_upserted"] for r in results.values())
        total_accounts = sum(r.get("accounts_created", 0) for r in results.values())
        total_errors = sum(len(r["errors"]) for r in results.values())
        summary = f"Done: {total_links} private URL(s) synced across {len(results)} instance(s)."
        if total_accounts:
            summary += f" {total_accounts} new account(s) auto-provisioned."
        if total_errors:
            self.stdout.write(self.style.WARNING(summary + f" {total_errors} warning(s)."))
        else:
            self.stdout.write(self.style.SUCCESS(summary))
