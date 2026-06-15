from django.conf import settings
from django.db import models

from .fields import EncryptedTextField


class TabbycatInstance(models.Model):
    """A Tabbycat deployment to pull tournaments and private URLs from.

    Usually there's just one (the SDA server), but several are supported.
    """

    name = models.CharField(max_length=120)
    base_url = models.URLField(
        help_text="Root URL of the Tabbycat site, e.g. https://sda.calicotab.com",
    )
    api_token = EncryptedTextField(
        help_text="A staff API token with permission to view private URLs and contacts.",
    )
    is_active = models.BooleanField(default=True)

    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_sync_status = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "Tabbycat instance"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.base_url = self.base_url.rstrip("/")
        super().save(*args, **kwargs)


class Tournament(models.Model):
    """A local mirror of a Tabbycat tournament, refreshed by the sync job."""

    instance = models.ForeignKey(
        TabbycatInstance, on_delete=models.CASCADE, related_name="tournaments",
    )
    slug = models.SlugField(max_length=100)
    name = models.CharField(max_length=200)
    short_name = models.CharField(max_length=50, blank=True)
    active = models.BooleanField(default=True)
    is_running = models.BooleanField(
        default=False, help_text="A round is currently in progress.",
    )
    seq = models.IntegerField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("instance", "slug")
        ordering = ["-is_running", "seq", "name"]

    def __str__(self):
        return self.short_name or self.name

    @property
    def display_name(self):
        return self.name or self.short_name


class PrivateURL(models.Model):
    """An adjudicator's private URL key for one tournament (matched by email)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="private_urls",
    )
    tournament = models.ForeignKey(
        Tournament, on_delete=models.CASCADE, related_name="private_urls",
    )
    url_key = EncryptedTextField()
    source_email = models.EmailField(
        blank=True,
        help_text="The Tabbycat adjudicator email this URL was matched on (blank if self-added).",
    )
    self_added = models.BooleanField(
        default=False,
        help_text="Added by the user from a private URL/QR rather than matched by sync.",
    )
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("user", "tournament")

    def __str__(self):
        return f"{self.user} @ {self.tournament}"

    @property
    def full_url(self):
        base = self.tournament.instance.base_url
        return f"{base}/{self.tournament.slug}/privateurls/{self.url_key}/"


class SiteSettings(models.Model):
    """Singleton holding admin-editable, site-wide switches.

    Always row pk=1 — use ``SiteSettings.load()`` to read/create it.
    """

    privacy_policy_visible = models.BooleanField(
        default=True,
        help_text=(
            "When unchecked, the privacy policy page is hidden (returns 404) "
            "and its link disappears from the footer."
        ),
    )
    privacy_html_sk = models.TextField(
        blank=True,
        default="",
        verbose_name="Privacy policy — Slovak (HTML)",
        help_text=(
            "Content shown on the privacy page in Slovak. HTML is allowed "
            "(e.g. <h2>, <p>, <ul>, <a>). Leave blank for an empty page."
        ),
    )
    privacy_html_en = models.TextField(
        blank=True,
        default="",
        verbose_name="Privacy policy — English (HTML)",
        help_text=(
            "Content shown on the privacy page in English. HTML is allowed. "
            "Falls back to the Slovak text when left blank."
        ),
    )

    class Meta:
        verbose_name = "Site settings"
        verbose_name_plural = "Site settings"

    def __str__(self):
        return "Site settings"

    def save(self, *args, **kwargs):
        self.pk = 1  # enforce a single row
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # pragma: no cover - guarded in admin too
        pass  # the singleton is never deleted

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
