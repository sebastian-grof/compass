from .models import SiteSettings


def site_settings(request):
    """Expose admin-controlled site switches to every template (e.g. the footer)."""
    return {"privacy_policy_visible": SiteSettings.load().privacy_policy_visible}
