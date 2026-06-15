import os
import re
import tempfile
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from core import sync as sync_module
from core.models import PrivateURL, TabbycatInstance

from .models import EmailAlias

User = get_user_model()

LOCMEM_CACHE = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


@override_settings(CACHES=LOCMEM_CACHE)
class LoginTests(TestCase):
    def setUp(self):
        cache.clear()  # login failures are throttled via the cache
        self.user = User.objects.create_user(email="adj@example.com", password="pw-12345")

    def _login(self, password="pw-12345", remember=True):
        data = {"username": "adj@example.com", "password": password}
        if remember:
            data["remember_me"] = "on"
        return self.client.post(reverse("login"), data)

    def test_login_success_redirects_home(self):
        resp = self._login()
        self.assertRedirects(resp, reverse("home"))

    def test_login_failure_rerenders_with_error(self):
        resp = self._login(password="wrong")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["form"].non_field_errors())

    def test_remember_me_uses_long_session(self):
        self._login(remember=True)
        session = self.client.session
        self.assertFalse(session.get_expire_at_browser_close())
        self.assertEqual(session.get_expiry_age(), settings.SESSION_COOKIE_AGE)

    def test_no_remember_me_expires_at_browser_close(self):
        self._login(remember=False)
        self.assertTrue(self.client.session.get_expire_at_browser_close())


@override_settings(CACHES=LOCMEM_CACHE, LOGIN_THROTTLE_LIMIT=3)
class LoginThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email="adj@example.com", password="pw-12345")

    def _attempt(self, password):
        return self.client.post(
            reverse("login"), {"username": "adj@example.com", "password": password}
        )

    def test_lockout_blocks_even_correct_password(self):
        for _ in range(3):
            self._attempt("wrong")
        resp = self._attempt("pw-12345")
        # Locked out: bounced back to the login page, not logged in.
        self.assertRedirects(resp, reverse("login"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_lockout_message_shown(self):
        for _ in range(3):
            self._attempt("wrong")
        resp = self._attempt("pw-12345")
        follow = self.client.get(resp.url)
        self.assertIn("Too many unsuccessful attempts", follow.content.decode())

    def test_success_resets_counters(self):
        for _ in range(2):
            self._attempt("wrong")
        resp = self._attempt("pw-12345")
        self.assertRedirects(resp, reverse("home"))
        self.client.post(reverse("logout"))
        # Counters were cleared, so two more failures still stay under the limit.
        for _ in range(2):
            self._attempt("wrong")
        resp = self._attempt("pw-12345")
        self.assertRedirects(resp, reverse("home"))


class CsrfFailureTests(TestCase):
    def setUp(self):
        self.csrf_client = Client(enforce_csrf_checks=True)
        User.objects.create_user(email="adj@example.com", password="pw-12345")

    def test_missing_token_redirects_with_message_instead_of_403(self):
        resp = self.csrf_client.post(
            reverse("login"), {"username": "adj@example.com", "password": "pw-12345"}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("login"))
        follow = self.csrf_client.get(resp.url)
        self.assertIn("The form expired", follow.content.decode())


class EmailAliasTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="primary@example.com", password="pw")
        EmailAlias.objects.create(user=self.user, email="old@example.com")

    def test_all_emails_includes_aliases(self):
        self.assertCountEqual(
            self.user.all_emails, ["primary@example.com", "old@example.com"]
        )

    def test_sync_matches_by_alias(self):
        instance = TabbycatInstance.objects.create(
            name="T", base_url="https://x.test", api_token="tok"
        )

        class Fake:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def close(self):
                pass

            def tournaments(self):
                return [{"slug": "t1", "name": "T1", "active": True, "current_rounds": []}]

            def adjudicators(self, slug):
                # Tabbycat knows the *old* address; the alias must still match.
                return [{"email": "Old@Example.com", "url_key": "k1", "name": "A"}]

        with patch.object(sync_module, "TabbycatClient", lambda *a, **k: Fake()):
            sync_module.sync_instance(instance)

        link = PrivateURL.objects.get(user=self.user)
        self.assertEqual(link.source_email, "old@example.com")
        self.assertEqual(link.url_key, "k1")


class ImportAdjudicatorsTests(TestCase):
    def _csv(self, content):
        tmp = tempfile.NamedTemporaryFile(
            "w", suffix=".csv", delete=False, encoding="utf-8"
        )
        tmp.write(content)
        tmp.close()
        self.addCleanup(os.unlink, tmp.name)
        return tmp.name

    def test_creates_and_updates_users(self):
        path = self._csv("email,name\nnew@example.com,New Person\n")
        call_command("import_adjudicators", path)
        user = User.objects.get(email="new@example.com")
        self.assertEqual(user.name, "New Person")
        self.assertTrue(user.has_usable_password())

        # A second run fills in a missing name without duplicating the user.
        user.name = ""
        user.save(update_fields=["name"])
        call_command("import_adjudicators", path)
        user.refresh_from_db()
        self.assertEqual(user.name, "New Person")
        self.assertEqual(User.objects.filter(email="new@example.com").count(), 1)

    def test_invite_sends_set_password_email(self):
        path = self._csv("email\ninvitee@example.com\n")
        call_command("import_adjudicators", path, "--invite")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("invitee@example.com", mail.outbox[0].to)
        self.assertRegex(mail.outbox[0].body, r"/reset/[^/]+/[^/]+/")

    def test_missing_email_header_raises(self):
        path = self._csv("name\nNo Email\n")
        with self.assertRaises(CommandError):
            call_command("import_adjudicators", path)


class PasswordResetFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="adj@example.com", password="old-pw-123")

    def test_full_reset_flow(self):
        resp = self.client.post(reverse("password_reset"), {"email": "adj@example.com"})
        self.assertRedirects(resp, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)

        match = re.search(r"(/reset/[^/]+/[^/]+/)", mail.outbox[0].body)
        self.assertIsNotNone(match)
        # The confirm view redirects to a session-backed set-password URL.
        resp = self.client.get(match.group(1), follow=True)
        self.assertEqual(resp.status_code, 200)
        set_password_url = resp.request["PATH_INFO"]

        resp = self.client.post(
            set_password_url,
            {"new_password1": "fresh-pw-456", "new_password2": "fresh-pw-456"},
        )
        self.assertRedirects(resp, reverse("password_reset_complete"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("fresh-pw-456"))


class SettingsPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="adj@example.com", password="pw-12345")
        self.client.force_login(self.user)

    def test_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse("settings"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("login"), resp.url)

    def test_toggle_auto_redirect(self):
        resp = self.client.post(
            reverse("settings"), {"action": "prefs", "auto_redirect": "on"}
        )
        self.assertRedirects(resp, reverse("settings"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.auto_redirect)

        self.client.post(reverse("settings"), {"action": "prefs"})
        self.user.refresh_from_db()
        self.assertFalse(self.user.auto_redirect)

    def test_password_change_keeps_session(self):
        resp = self.client.post(
            reverse("settings"),
            {
                "action": "password",
                "old_password": "pw-12345",
                "new_password1": "fresh-pw-456",
                "new_password2": "fresh-pw-456",
            },
        )
        self.assertRedirects(resp, reverse("settings"))
        # Still logged in after the change (update_session_auth_hash).
        self.assertEqual(self.client.session.get("_auth_user_id"), str(self.user.pk))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("fresh-pw-456"))
        self.assertFalse(self.user.check_password("pw-12345"))

    def test_wrong_old_password_rejected(self):
        resp = self.client.post(
            reverse("settings"),
            {
                "action": "password",
                "old_password": "nope",
                "new_password1": "fresh-pw-456",
                "new_password2": "fresh-pw-456",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("pw-12345"))
