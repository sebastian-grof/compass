from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),  # set_language view
    # Served from the root so the service worker's scope covers the whole app.
    path(
        "sw.js",
        TemplateView.as_view(
            template_name="sw.js", content_type="application/javascript",
        ),
        name="service-worker",
    ),
    path("", include("accounts.urls")),
    path("", include("core.urls")),
]
