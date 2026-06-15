"""Sync logic: pull tournaments + adjudicator private URLs from Tabbycat.

Kept separate from the management command so the admin "Sync now" action can call
the same code path.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.crypto import get_random_string

from .models import PrivateURL, TabbycatInstance, Tournament
from .tabbycat import TabbycatClient, TabbycatError

User = get_user_model()


def _email_index():
    """Map lowercased email -> user, including aliases, for active users."""
    index = {}
    for user in User.objects.filter(is_active=True).prefetch_related("email_aliases"):
        for email in user.all_emails:
            if email:
                index[email.lower()] = user
    return index


def sync_instance(instance, log=None):
    """Sync one Tabbycat instance. Returns a stats dict and records status."""

    def emit(message):
        if log is not None:
            log(message)

    now = timezone.now()
    auto_create = getattr(settings, "AUTO_CREATE_ADJUDICATOR_ACCOUNTS", False)
    stats = {
        "tournaments": 0,
        "active_tournaments": 0,
        "links_upserted": 0,
        "links_removed": 0,
        "accounts_created": 0,
        "errors": [],
    }

    try:
        client_cm = TabbycatClient(instance.base_url, instance.api_token)
    except Exception as exc:  # pragma: no cover - construction is trivial
        _record(instance, now, f"ERROR: {exc}")
        stats["errors"].append(str(exc))
        return stats

    with client_cm as client:
        try:
            remote_tournaments = client.tournaments()
        except TabbycatError as exc:
            _record(instance, now, f"ERROR: {exc}")
            stats["errors"].append(str(exc))
            emit(f"  ✗ {exc}")
            return stats

        stats["tournaments"] = len(remote_tournaments)
        email_index = _email_index()

        for t in remote_tournaments:
            slug = t.get("slug")
            if not slug:
                continue

            tournament, _ = Tournament.objects.update_or_create(
                instance=instance,
                slug=slug,
                defaults={
                    "name": t.get("name") or slug,
                    "short_name": t.get("short_name") or "",
                    "active": bool(t.get("active", True)),
                    "is_running": bool(t.get("current_rounds")),
                    "seq": t.get("seq"),
                    "last_seen_at": now,
                },
            )
            if not tournament.active:
                continue
            stats["active_tournaments"] += 1

            try:
                adjudicators = client.adjudicators(slug)
            except TabbycatError as exc:
                stats["errors"].append(f"{slug}: {exc}")
                emit(f"  ✗ {slug}: {exc}")
                continue

            seen_user_ids = set()
            keys_present = 0
            for adj in adjudicators:
                email = (adj.get("email") or "").strip().lower()
                url_key = adj.get("url_key")
                if not url_key:
                    continue
                keys_present += 1
                if not email:
                    continue
                user = email_index.get(email)
                if user is None:
                    if not auto_create:
                        continue
                    # The email belongs to a real adjudicator with a private URL,
                    # so provisioning here can never create an account for a
                    # non-adjudicator. Give a random (unknown) password — same as the
                    # invite flow — so nobody can log in, yet the account stays
                    # eligible for the password-reset form (an *unusable* password
                    # would be skipped by it). No mail is ever sent from here.
                    user = User.objects.create_user(
                        email=email,
                        password=get_random_string(24),
                        name=adj.get("name") or "",
                    )
                    email_index[email] = user  # reuse across later tournaments this run
                    stats["accounts_created"] += 1
                PrivateURL.objects.update_or_create(
                    user=user,
                    tournament=tournament,
                    defaults={
                        "url_key": url_key,
                        "source_email": email,
                        "last_synced_at": now,
                    },
                )
                seen_user_ids.add(user.id)
                stats["links_upserted"] += 1

            # Prune links for adjudicators dropped from this tournament — but only
            # when keys are actually flowing, so a token that lacks VIEW_PRIVATE_URLS
            # (every url_key stripped) can never wipe existing links. Self-added
            # links are never pruned: the user owns those, not the sync.
            if keys_present:
                removed, _ = (
                    PrivateURL.objects.filter(tournament=tournament, self_added=False)
                    .exclude(user_id__in=seen_user_ids)
                    .delete()
                )
                stats["links_removed"] += removed
            elif adjudicators:
                stats["errors"].append(
                    f"{slug}: adjudicators returned but no url_key visible — "
                    "token likely lacks VIEW_PRIVATE_URLS."
                )

            emit(f"  • {slug}: {len(seen_user_ids)} matched")

    status = (
        f"OK: {stats['active_tournaments']} active tournaments, "
        f"{stats['links_upserted']} links"
    )
    if stats["accounts_created"]:
        status += f", {stats['accounts_created']} account(s) created"
    if stats["errors"]:
        status += f", {len(stats['errors'])} warning(s)"
    _record(instance, now, status)
    emit(status)
    return stats


def _record(instance, when, status):
    instance.last_synced_at = when
    instance.last_sync_status = status[:255]
    instance.save(update_fields=["last_synced_at", "last_sync_status"])


def sync_all(log=None):
    results = {}
    for instance in TabbycatInstance.objects.filter(is_active=True):
        if log is not None:
            log(f"Syncing {instance.name} ({instance.base_url})…")
        results[instance.name] = sync_instance(instance, log=log)
    return results
