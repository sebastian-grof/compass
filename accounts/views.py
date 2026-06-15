from django.conf import settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache

from .forms import EmailLoginForm, SettingsForm


def _client_ip(request):
    """Best-effort client IP. On Heroku the router appends the real client IP
    as the last entry of X-Forwarded-For; fall back to REMOTE_ADDR elsewhere."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.META.get("REMOTE_ADDR", "")


def _throttle_keys(request):
    keys = [f"login-fail:ip:{_client_ip(request)}"]
    email = (request.POST.get("username") or "").strip().lower()
    if email:
        keys.append(f"login-fail:email:{email}")
    return keys


def _locked_out(request):
    limit = settings.LOGIN_THROTTLE_LIMIT
    return any((cache.get(key) or 0) >= limit for key in _throttle_keys(request))


def _register_failure(request):
    timeout = settings.LOGIN_THROTTLE_TIMEOUT
    for key in _throttle_keys(request):
        cache.add(key, 0, timeout)
        try:
            cache.incr(key)
        except ValueError:
            # Counter expired between add() and incr(); start a fresh window.
            cache.set(key, 1, timeout)


class LoginView(auth_views.LoginView):
    """Email/password login with an optional persistent session.

    When 'remember me' is ticked the session lasts SESSION_COOKIE_AGE; otherwise
    it expires when the browser closes. Repeated failures (per IP and per email)
    lock the form for LOGIN_THROTTLE_TIMEOUT seconds.
    """

    template_name = "registration/login.html"
    authentication_form = EmailLoginForm
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        # While locked out, don't even validate credentials — a correct guess
        # during the lockout window must not confirm the password.
        if _locked_out(request):
            messages.error(
                request, _("Too many unsuccessful attempts. Try again later.")
            )
            return redirect("login")
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        _register_failure(self.request)
        return super().form_invalid(form)

    def form_valid(self, form):
        cache.delete_many(_throttle_keys(self.request))
        remember = form.cleaned_data.get("remember_me")
        # set_expiry(0) -> expire at browser close; None -> use SESSION_COOKIE_AGE.
        self.request.session.set_expiry(None if remember else 0)
        return super().form_valid(form)


def csrf_failure(request, reason=""):
    """Friendly CSRF failure handler (settings.CSRF_FAILURE_VIEW).

    The usual cause is a stale token — a long-idle PWA or a page restored from
    cache. Instead of Django's bare 403, send the user to a freshly rendered
    page (with a fresh token) and explain, so simply retrying works."""
    messages.error(request, _("The form expired. Please try again."))
    return redirect("home" if request.user.is_authenticated else "login")


@never_cache
@login_required
def settings_view(request):
    """The adjudicator's own settings: preferences + password change.

    One page, two independent forms told apart by the submit button's
    `action` value."""
    prefs_form = SettingsForm(instance=request.user)
    password_form = PasswordChangeForm(user=request.user)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "prefs":
            prefs_form = SettingsForm(request.POST, instance=request.user)
            if prefs_form.is_valid():
                prefs_form.save()
                messages.success(request, _("Settings saved."))
                return redirect("settings")
        elif action == "password":
            password_form = PasswordChangeForm(user=request.user, data=request.POST)
            if password_form.is_valid():
                password_form.save()
                # Keep the current session valid after the password change.
                update_session_auth_hash(request, request.user)
                messages.success(request, _("Password changed."))
                return redirect("settings")

    return render(
        request,
        "settings.html",
        {"prefs_form": prefs_form, "password_form": password_form},
    )
