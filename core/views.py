import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import get_language, gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .links import InvalidPrivateURL, add_private_url_for_user
from .models import PrivateURL, SiteSettings


def _active_links(user):
    return (
        PrivateURL.objects
        .filter(user=user, tournament__active=True)
        .select_related("tournament", "tournament__instance")
        .order_by("-tournament__is_running", "tournament__seq", "tournament__name")
    )


@never_cache
@login_required
def home(request):
    """The adjudicator's active tournaments, newest/running first."""
    links = list(_active_links(request.user))

    # Optional one-tap behaviour: if the user opted in and has exactly one active
    # tournament, skip the list and go straight to its private URL. `?stay=1`
    # bypasses it (used by the settings page), and the short-lived cookie set
    # below means coming straight back from Tabbycat shows the list instead of
    # bouncing forward again.
    if (
        request.user.auto_redirect
        and len(links) == 1
        and "stay" not in request.GET
        and "compass_stay" not in request.COOKIES
    ):
        response = redirect("go", tournament_id=links[0].tournament_id)
        response.set_cookie("compass_stay", "1", max_age=60, samesite="Lax")
        return response

    tournaments = []
    for link in links:
        tournament = link.tournament
        tournament.self_added = link.self_added  # drives the per-row remove control
        tournaments.append(tournament)
    return render(request, "home.html", {"tournaments": tournaments})


@never_cache
@login_required
def go(request, tournament_id):
    """Redirect to the current user's private URL for one tournament.

    Filtering on `user=request.user` enforces isolation: a user can only ever be
    redirected to their own private URL (others 404)."""
    link = get_object_or_404(
        PrivateURL.objects.select_related("tournament", "tournament__instance"),
        user=request.user,
        tournament_id=tournament_id,
    )
    return redirect(link.full_url)


@never_cache
@login_required
def add_tournament(request):
    """Let a signed-in user add their own tournament from a pasted/scanned URL."""
    error = None
    url_value = ""
    if request.method == "POST":
        url_value = (request.POST.get("url") or "").strip()
        try:
            link, created = add_private_url_for_user(request.user, url_value)
        except InvalidPrivateURL as exc:
            error = str(exc)
        else:
            name = link.tournament.display_name
            template = _("Tournament “%(name)s” added.") if created else _("Tournament “%(name)s” updated.")
            messages.success(request, template % {"name": name})
            return redirect("home")
    return render(request, "add_tournament.html", {"error": error, "url_value": url_value})


@never_cache
@login_required
@require_POST
def remove_tournament(request, tournament_id):
    """Remove a *self-added* tournament for the current user.

    Synced links (self_added=False) are owned by the API sync, not the user, so
    the filter below never matches them — they can't be removed here."""
    link = (
        PrivateURL.objects
        .filter(user=request.user, tournament_id=tournament_id, self_added=True)
        .select_related("tournament", "tournament__instance")
        .first()
    )
    if link:
        tournament = link.tournament
        instance = tournament.instance
        link.delete()
        messages.success(request, _("Tournament removed."))
        # Tidy up placeholder tournaments/instances created for unknown hosts;
        # never touch a real (active) instance like SDA.
        if not instance.is_active and not tournament.private_urls.exists():
            tournament.delete()
            if not instance.tournaments.exists():
                instance.delete()
    return redirect("home")


def offline(request):
    """Offline fallback page, pre-cached by the service worker.

    Deliberately cacheable and form-free: it must never embed a CSRF token
    (see templates/sw.js). The retry button reloads the originally requested
    URL, because the service worker serves this body under that URL."""
    return render(request, "offline.html")


def privacy(request):
    """Public privacy notice. The body is admin-editable (SiteSettings), per
    language, and may be left blank for an empty page.

    Admins can also hide it entirely from the Django admin (SiteSettings); when
    hidden the page returns 404 and its footer link is suppressed.
    """
    site = SiteSettings.load()
    if not site.privacy_policy_visible:
        raise Http404("Privacy policy is currently unavailable.")
    content = site.privacy_html_en if (get_language() or "").startswith("en") else site.privacy_html_sk
    if not content.strip():
        content = site.privacy_html_sk or site.privacy_html_en
    return render(request, "privacy.html", {"privacy_html": content})


@never_cache
def guest(request):
    """No-login page: tournaments are kept in the browser's localStorage only.

    Signed-in users have a real account/list, so send them to home (this also
    avoids rendering the base header twice)."""
    if request.user.is_authenticated:
        return redirect("home")
    return render(request, "guest.html")


@never_cache
@login_required
@require_POST
def import_guest(request):
    """Upsert locally-saved guest tournaments into the signed-in user's account."""
    try:
        payload = json.loads(request.body or b"{}")
        urls = payload.get("urls") or []
    except (ValueError, TypeError):
        return JsonResponse({"error": "bad payload"}, status=400)

    imported, failed = 0, 0
    for raw in urls:
        try:
            add_private_url_for_user(request.user, raw)
            imported += 1
        except InvalidPrivateURL:
            failed += 1
    return JsonResponse({"imported": imported, "failed": failed})
