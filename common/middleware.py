from django.conf import settings
from django.http import HttpResponseNotFound


class HostAccessMiddleware:
    """Limita le URL disponibili in base all'hostname richiesto.

    Questa è una difesa applicativa: l'isolamento effettivo della rete deve
    comunque essere applicato dal reverse proxy e dal firewall.
    """

    ticket_paths = ("/attesa/", "/static/", "/favicon.ico")
    account_paths = (
        "/account/",
        "/accounts/login/",
        "/accounts/logout/",
        "/static/",
        "/favicon.ico",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(":", 1)[0].lower()
        path = request.path

        if host == settings.PUBLIC_TICKET_HOST:
            allowed = path.startswith(self.ticket_paths)
        elif host == settings.PUBLIC_ACCOUNT_HOST:
            allowed = path.startswith(self.account_paths)
        else:
            # Gli host interni e di sviluppo restano operativi. In produzione
            # il reverse proxy deve rendere raggiungibile quello interno solo
            # da LAN/VPN.
            allowed = True

        if not allowed:
            return HttpResponseNotFound("Pagina non disponibile su questo host.")

        return self.get_response(request)
