"""Parsing and self-service provisioning of Tabbycat private URLs.

A Tabbycat private URL looks like:

    https://<host>/<slug>/privateurls/<key>/

The key IS the access credential, so anyone holding the URL can open that
adjudicator's page. Self-add lets a user register their own URL (pasted or
scanned) instead of waiting for the email-matched sync.
"""

from urllib.parse import urlsplit

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import PrivateURL, TabbycatInstance, Tournament


class InvalidPrivateURL(ValueError):
    """The supplied string is not a recognisable Tabbycat private URL."""


def parse_private_url(raw):
    """Return (base_url, slug, key) for a Tabbycat private URL, or raise.

    `base_url` is scheme://host (no trailing slash); http is upgraded to https.
    """
    if not raw or not raw.strip():
        raise InvalidPrivateURL(_("Enter a link."))
    parts = urlsplit(raw.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise InvalidPrivateURL(_("That doesn't look like a valid link."))

    segments = [s for s in parts.path.split("/") if s]
    if "privateurls" not in segments:
        raise InvalidPrivateURL(_("That doesn't look like a Tabbycat private URL (missing “privateurls”)."))

    i = segments.index("privateurls")
    if i < 1 or i + 1 >= len(segments):
        raise InvalidPrivateURL(_("The link is missing the tournament slug or key."))

    slug = segments[i - 1]
    key = segments[i + 1]
    if not slug or not key:
        raise InvalidPrivateURL(_("The link is missing the tournament slug or key."))

    # Always store https — Tabbycat private URLs are served over TLS.
    base_url = f"https://{parts.netloc}"
    return base_url, slug, key


def _instance_for(base_url):
    """Reuse a configured instance if the host matches; else a lightweight,
    inactive placeholder so sync never tries to talk to an unknown host."""
    existing = TabbycatInstance.objects.filter(base_url=base_url).first()
    if existing:
        return existing
    host = urlsplit(base_url).netloc
    return TabbycatInstance.objects.create(
        name=host, base_url=base_url, api_token="", is_active=False,
    )


def add_private_url_for_user(user, raw_url):
    """Validate `raw_url` and upsert a self-added PrivateURL for `user`.

    Returns (private_url, created). Raises InvalidPrivateURL on a bad URL.
    """
    base_url, slug, key = parse_private_url(raw_url)
    now = timezone.now()

    instance = _instance_for(base_url)
    tournament, _ = Tournament.objects.get_or_create(
        instance=instance, slug=slug,
        defaults={"name": slug, "active": True, "last_seen_at": now},
    )

    link, created = PrivateURL.objects.update_or_create(
        user=user, tournament=tournament,
        defaults={
            "url_key": key,
            "self_added": True,
            "last_synced_at": now,
        },
    )
    return link, created
