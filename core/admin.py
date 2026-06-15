from datetime import timedelta

from django.conf import settings
from django.contrib import admin, messages
from django.db import models
from django.forms import Textarea
from django.utils import timezone
from django.utils.html import format_html
from django.utils.timesince import timesince

from .models import PrivateURL, SiteSettings, TabbycatInstance, Tournament
from .sync import sync_instance


@admin.register(TabbycatInstance)
class TabbycatInstanceAdmin(admin.ModelAdmin):
    list_display = ("name", "base_url", "is_active", "sync_health", "last_sync_status")
    list_filter = ("is_active",)
    readonly_fields = ("last_synced_at", "last_sync_status")
    actions = ["sync_now"]

    @admin.display(description="Last synced")
    def sync_health(self, obj):
        """Colour-coded sync recency — a red flag here usually means the cron
        job driving `sync_tabbycat` has died."""
        if not obj.is_active:
            return format_html('<span style="color:#999;">—</span>')
        if obj.last_synced_at is None:
            return format_html('<b style="color:#ba2121;">● Never synced</b>')
        stale_after = timedelta(minutes=settings.SYNC_STALE_AFTER_MINUTES)
        ago = timesince(obj.last_synced_at)
        if timezone.now() - obj.last_synced_at > stale_after:
            return format_html('<b style="color:#ba2121;">● Stale ({} ago)</b>', ago)
        return format_html('<span style="color:#1a7a3a;">● {} ago</span>', ago)

    @admin.action(description="Sync now — pull tournaments + private URLs")
    def sync_now(self, request, queryset):
        for instance in queryset:
            stats = sync_instance(instance)
            level = messages.WARNING if stats["errors"] else messages.SUCCESS
            self.message_user(request, f"{instance.name}: {instance.last_sync_status}", level=level)


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    """Read-only mirror — tournaments are owned by Tabbycat, not edited here."""

    list_display = ("__str__", "instance", "active", "is_running", "slug", "last_seen_at")
    list_filter = ("instance", "active", "is_running")
    search_fields = ("name", "short_name", "slug")
    readonly_fields = ("instance", "slug", "name", "short_name", "active", "is_running", "seq", "last_seen_at")

    def has_add_permission(self, request):
        return False


@admin.register(PrivateURL)
class PrivateURLAdmin(admin.ModelAdmin):
    """Read-only, and deliberately never exposes the secret url_key."""

    list_display = ("user", "tournament", "source_email", "last_synced_at")
    list_filter = ("tournament__instance", "tournament")
    search_fields = ("user__email", "source_email", "tournament__name")
    readonly_fields = ("user", "tournament", "source_email", "last_synced_at")
    exclude = ("url_key",)

    def has_add_permission(self, request):
        return False


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    """Singleton — site-wide switches plus the editable privacy-policy text."""

    list_display = ("__str__", "privacy_policy_visible")
    fieldsets = (
        (None, {"fields": ("privacy_policy_visible",)}),
        ("Privacy policy text", {
            "fields": ("privacy_html_sk", "privacy_html_en"),
            "description": (
                "Shown on the /privacy/ page. HTML is allowed. Leave both blank "
                "for an empty page; English falls back to Slovak when blank."
            ),
        }),
    )
    formfield_overrides = {
        models.TextField: {"widget": Textarea(attrs={"rows": 20, "cols": 100, "style": "font-family:monospace;"})},
    }

    def has_add_permission(self, request):
        # Only allow creating the singleton if it doesn't exist yet.
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
