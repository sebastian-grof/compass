import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordResetForm
from django.test import TestCase, override_settings
from django.urls import reverse

from core import sync as sync_module
from core.links import InvalidPrivateURL, add_private_url_for_user, parse_private_url
from core.models import PrivateURL, TabbycatInstance, Tournament

User = get_user_model()


class FakeClient:
    """Stand-in for TabbycatClient that returns fixed API payloads.

    Patched in for `core.sync.TabbycatClient`, so sync runs without a real
    Tabbycat instance (the approach described in SETUP.md).
    """

    def __init__(self, adjudicators):
        self._adjudicators = adjudicators

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def close(self):
        pass

    def tournaments(self):
        return [{"slug": "t1", "name": "Tournament One", "active": True, "current_rounds": []}]

    def adjudicators(self, slug):
        return list(self._adjudicators)


class AutoCreateAdjudicatorTests(TestCase):
    """Auto-provisioning accounts for Tabbycat adjudicators during sync."""

    def setUp(self):
        self.instance = TabbycatInstance.objects.create(
            name="T", base_url="https://x.test", api_token="tok",
        )

    def _sync(self, adjudicators, enabled):
        fake = FakeClient(adjudicators)
        with patch.object(sync_module, "TabbycatClient", lambda *a, **k: fake), \
                override_settings(AUTO_CREATE_ADJUDICATOR_ACCOUNTS=enabled):
            return sync_module.sync_instance(self.instance)

    def test_disabled_does_not_create_accounts(self):
        stats = self._sync(
            [{"email": "new@example.com", "url_key": "k1", "name": "New"}], enabled=False,
        )
        self.assertEqual(stats["accounts_created"], 0)
        self.assertFalse(User.objects.filter(email="new@example.com").exists())

    def test_enabled_creates_active_account_eligible_for_reset(self):
        stats = self._sync(
            [{"email": "New@Example.com", "url_key": "k1", "name": "New Person"}], enabled=True,
        )
        self.assertEqual(stats["accounts_created"], 1)
        user = User.objects.get(email="new@example.com")
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.name, "New Person")
        self.assertTrue(PrivateURL.objects.filter(user=user).exists())
        # Random (unknown) password => nobody can log in, but the account IS
        # eligible for the reset flow so the person can set their own password.
        self.assertTrue(user.has_usable_password())
        eligible = list(PasswordResetForm().get_users("new@example.com"))
        self.assertIn(user, eligible)

    def test_only_creates_for_adjudicator_with_email_and_key(self):
        # An entry without a url_key (token can't see it) or without an email must
        # never produce an account — the gate is structural.
        stats = self._sync(
            [
                {"email": "nokey@example.com", "url_key": "", "name": "No Key"},
                {"email": "", "url_key": "k2", "name": "No Email"},
            ],
            enabled=True,
        )
        self.assertEqual(stats["accounts_created"], 0)
        self.assertFalse(User.objects.filter(email="nokey@example.com").exists())

    def test_existing_user_is_reused_not_duplicated(self):
        User.objects.create_user(email="existing@example.com", password="pw")
        stats = self._sync(
            [{"email": "existing@example.com", "url_key": "k1", "name": "E"}], enabled=True,
        )
        self.assertEqual(stats["accounts_created"], 0)
        self.assertEqual(User.objects.filter(email="existing@example.com").count(), 1)

    def test_idempotent_across_runs(self):
        adj = [{"email": "new@example.com", "url_key": "k1", "name": "New"}]
        self._sync(adj, enabled=True)
        stats2 = self._sync(adj, enabled=True)
        self.assertEqual(stats2["accounts_created"], 0)
        self.assertEqual(User.objects.filter(email="new@example.com").count(), 1)


class ParsePrivateURLTests(TestCase):
    def test_valid(self):
        base, slug, key = parse_private_url(
            "https://tabbycat.sda.sk/fjdl1-2026/privateurls/abc123/"
        )
        self.assertEqual(base, "https://tabbycat.sda.sk")
        self.assertEqual(slug, "fjdl1-2026")
        self.assertEqual(key, "abc123")

    def test_http_is_upgraded(self):
        base, _, _ = parse_private_url("http://host.example/t/privateurls/k/")
        self.assertEqual(base, "https://host.example")

    def test_rejects_non_private_url(self):
        for bad in ["", "not a url", "https://host/foo/bar",
                    "https://host/privateurls/", "ftp://h/t/privateurls/k/"]:
            with self.assertRaises(InvalidPrivateURL):
                parse_private_url(bad)


class SelfAddTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="adj@example.com", password="pw")

    def test_add_creates_inactive_instance_and_self_added_link(self):
        link, created = add_private_url_for_user(
            self.user, "https://newtab.example/cup/privateurls/key9/"
        )
        self.assertTrue(created)
        self.assertTrue(link.self_added)
        self.assertEqual(link.url_key, "key9")
        self.assertEqual(link.full_url, "https://newtab.example/cup/privateurls/key9/")
        inst = link.tournament.instance
        self.assertEqual(inst.base_url, "https://newtab.example")
        self.assertFalse(inst.is_active)  # never synced against an unknown host

    def test_add_reuses_known_instance(self):
        inst = TabbycatInstance.objects.create(
            name="SDA", base_url="https://tabbycat.sda.sk", api_token="t", is_active=True,
        )
        link, _ = add_private_url_for_user(
            self.user, "https://tabbycat.sda.sk/cup/privateurls/k/"
        )
        self.assertEqual(link.tournament.instance, inst)
        self.assertEqual(TabbycatInstance.objects.count(), 1)

    def test_add_is_idempotent(self):
        url = "https://h.example/t/privateurls/k/"
        add_private_url_for_user(self.user, url)
        link, created = add_private_url_for_user(self.user, url)
        self.assertFalse(created)
        self.assertEqual(PrivateURL.objects.filter(user=self.user).count(), 1)

    def test_self_added_link_survives_sync_prune(self):
        inst = TabbycatInstance.objects.create(
            name="SDA", base_url="https://tabbycat.sda.sk", api_token="t", is_active=True,
        )
        # user self-adds a link for a tournament on this instance
        link, _ = add_private_url_for_user(
            self.user, "https://tabbycat.sda.sk/cup/privateurls/mykey/"
        )

        class Fake:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def close(self): pass
            def tournaments(self):
                return [{"slug": "cup", "name": "Cup", "active": True, "current_rounds": []}]
            def adjudicators(self, slug):
                # a *different* adjudicator has a key; our user is not in the list
                return [{"email": "someone@else.com", "url_key": "otherkey", "name": "X"}]

        with patch.object(sync_module, "TabbycatClient", lambda *a, **k: Fake()):
            sync_module.sync_instance(inst)

        # sync would normally prune links not seen, but self-added must remain
        self.assertTrue(PrivateURL.objects.filter(pk=link.pk).exists())


class ImportGuestTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="g@example.com", password="pw")
        self.client.force_login(self.user)

    def test_import_creates_links(self):
        resp = self.client.post(
            reverse("import_guest"),
            data=json.dumps({"urls": [
                "https://h.example/a/privateurls/k1/",
                "https://h.example/b/privateurls/k2/",
                "garbage",
            ]}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["imported"], 2)
        self.assertEqual(body["failed"], 1)
        self.assertEqual(PrivateURL.objects.filter(user=self.user, self_added=True).count(), 2)

    def test_import_requires_login(self):
        self.client.logout()
        resp = self.client.post(
            reverse("import_guest"),
            data=json.dumps({"urls": []}),
            content_type="application/json",
        )
        self.assertIn(resp.status_code, (302, 401, 403))


class PageRenderTests(TestCase):
    def test_guest_page_is_public(self):
        self.assertEqual(self.client.get(reverse("guest")).status_code, 200)

    def test_add_page_requires_login(self):
        self.assertEqual(self.client.get(reverse("add_tournament")).status_code, 302)

    def test_offline_page_is_public_and_token_free(self):
        resp = self.client.get(reverse("offline"))
        self.assertEqual(resp.status_code, 200)
        # The service worker caches this page; it must never embed a CSRF token.
        self.assertNotIn(b"csrfmiddlewaretoken", resp.content)
        self.assertNotIn(b"csrf-token", resp.content)


class HomeAutoRedirectTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="solo@example.com", password="pw", auto_redirect=True
        )
        self.client.force_login(self.user)
        self.link, _ = add_private_url_for_user(
            self.user, "https://h.example/cup/privateurls/k/"
        )

    def test_single_tournament_redirects_to_go(self):
        resp = self.client.get(reverse("home"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("go", args=[self.link.tournament_id]))
        self.assertIn("compass_stay", resp.cookies)

    def test_stay_param_shows_list(self):
        resp = self.client.get(reverse("home") + "?stay=1")
        self.assertEqual(resp.status_code, 200)

    def test_return_within_cookie_window_shows_list(self):
        # First visit redirects and sets the short-lived cookie...
        self.client.get(reverse("home"))
        # ...so coming straight back from Tabbycat shows the list, not a bounce.
        resp = self.client.get(reverse("home"))
        self.assertEqual(resp.status_code, 200)

    def test_no_redirect_with_multiple_tournaments(self):
        add_private_url_for_user(self.user, "https://h.example/cup2/privateurls/k2/")
        resp = self.client.get(reverse("home"))
        self.assertEqual(resp.status_code, 200)


class RemoveTournamentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="r@example.com", password="pw")
        self.client.force_login(self.user)

    def test_remove_self_added(self):
        link, _ = add_private_url_for_user(self.user, "https://h.example/t/privateurls/k/")
        resp = self.client.post(reverse("remove_tournament", args=[link.tournament_id]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(PrivateURL.objects.filter(pk=link.pk).exists())

    def test_cannot_remove_synced_link(self):
        inst = TabbycatInstance.objects.create(
            name="SDA", base_url="https://tabbycat.sda.sk", api_token="t", is_active=True)
        tournament = Tournament.objects.create(instance=inst, slug="s", name="S", active=True)
        link = PrivateURL.objects.create(
            user=self.user, tournament=tournament, url_key="k", self_added=False)
        self.client.post(reverse("remove_tournament", args=[tournament.id]))
        self.assertTrue(PrivateURL.objects.filter(pk=link.pk).exists())

    def test_cannot_remove_other_users_link(self):
        other = User.objects.create_user(email="o@example.com", password="pw")
        link, _ = add_private_url_for_user(other, "https://h.example/t/privateurls/k/")
        self.client.post(reverse("remove_tournament", args=[link.tournament_id]))
        self.assertTrue(PrivateURL.objects.filter(pk=link.pk).exists())

    def test_remove_requires_login(self):
        self.client.logout()
        resp = self.client.post(reverse("remove_tournament", args=[1]))
        self.assertIn(resp.status_code, (302, 401, 403))
