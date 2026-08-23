from django.conf import settings
from django.http import HttpResponseNotFound


class PublicBookingHostMiddleware:
    """Espone sul dominio pubblico solo prenotazioni e identità digitale."""

    allowed_prefixes = ("/prenotazioni/", "/identita/", "/static/", "/favicon.ico")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(":", 1)[0].lower()
        if host == settings.PUBLIC_BOOKING_HOST and not request.path.startswith(self.allowed_prefixes):
            return HttpResponseNotFound("Pagina non disponibile su questo host.")
        return self.get_response(request)
