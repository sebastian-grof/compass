"""Language selection middleware.

English is the default for everyone; Slovak is opt-in via the language switcher
on the Settings page (Django's set_language view, which sets the
LANGUAGE_COOKIE_NAME cookie). We deliberately *ignore* the browser's
Accept-Language header so a Slovak-locale browser still defaults to English
until the user explicitly switches.
"""

from django.conf import settings
from django.utils import translation


class LanguageMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self._supported = dict(settings.LANGUAGES)

    def __call__(self, request):
        lang = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
        if lang not in self._supported:
            lang = settings.LANGUAGE_CODE  # default: English
        translation.activate(lang)
        request.LANGUAGE_CODE = translation.get_language()
        try:
            response = self.get_response(request)
        finally:
            translation.deactivate()
        response.setdefault("Content-Language", request.LANGUAGE_CODE)
        return response
