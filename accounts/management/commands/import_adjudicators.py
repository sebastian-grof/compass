import csv

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordResetForm
from django.core.management.base import BaseCommand, CommandError
from django.utils.crypto import get_random_string

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Bulk-provision adjudicator accounts from a CSV with 'email' and optional "
        "'name' columns. New users get a random password; pass --invite to email "
        "each a set-password link."
    )

    def add_arguments(self, parser):
        parser.add_argument("csv_path", help="Path to a CSV file with email[,name] columns.")
        parser.add_argument("--invite", action="store_true", help="Email a set-password link to new users.")

    def handle(self, *args, **options):
        path = options["csv_path"]
        try:
            with open(path, newline="", encoding="utf-8-sig") as fh:
                rows = list(csv.DictReader(fh))
        except OSError as exc:
            raise CommandError(f"Could not read {path}: {exc}")

        if not rows or "email" not in rows[0]:
            raise CommandError("CSV must have a header row including an 'email' column.")

        created, updated, invited = 0, 0, 0
        for row in rows:
            email = (row.get("email") or "").strip().lower()
            if not email:
                continue
            name = (row.get("name") or "").strip()

            user, was_created = User.objects.get_or_create(
                email=email, defaults={"name": name},
            )
            if was_created:
                user.set_password(get_random_string(24))  # usable but unknown
                user.save()
                created += 1
            elif name and not user.name:
                user.name = name
                user.save(update_fields=["name"])
                updated += 1

            if options["invite"]:
                form = PasswordResetForm({"email": user.email})
                if form.is_valid():
                    # No request here, so supply the domain/protocol explicitly.
                    form.save(
                        domain_override=settings.SITE_DOMAIN,
                        use_https=not settings.DEBUG,
                        email_template_name="registration/password_reset_email.html",
                        subject_template_name="registration/password_reset_subject.txt",
                    )
                    invited += 1

        msg = f"Imported: {created} created, {updated} updated"
        if options["invite"]:
            msg += f", {invited} invite email(s) sent"
        self.stdout.write(self.style.SUCCESS(msg + "."))
