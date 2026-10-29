import hashlib
import hmac
import json
import secrets
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse

from djangosaml2_spid.views import AssertionConsumerServiceView


class GatewayAssertionConsumerServiceView(AssertionConsumerServiceView):
    """Verifica SAML e passa all'app principale solo un codice monouso."""

    def authenticate_user(self, request, session_info, attribute_mapping, create_unknown_user, assertion_info):
        attributes = session_info.get("ava") or {}

        def value(name):
            values = attributes.get(name) or []
            return str(values[0]).strip() if values else ""

        fiscal_code = value("fiscalNumber").upper().replace("TINIT-", "")
        if len(fiscal_code) != 16:
            raise PermissionDenied("SPID non ha restituito un codice fiscale valido.")
        code = secrets.token_urlsafe(48)
        destination = request.POST.get("RelayState", "/prenotazioni/?step=4")
        parsed_destination = urlparse(destination)
        if parsed_destination.scheme or parsed_destination.netloc or not destination.startswith("/"):
            destination = "/prenotazioni/?step=4"
        payload = {"code": code, "codice_fiscale": fiscal_code, "nome": value("name"), "cognome": value("familyName"), "email": value("email"), "destinazione": destination}
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        timestamp = str(int(__import__("time").time()))
        signature = hmac.new(settings.SPID_GATEWAY_SHARED_SECRET.encode("utf-8"), f"{timestamp}.".encode("ascii") + body, hashlib.sha256).hexdigest()
        callback = Request(settings.SPID_APPLICATION_CALLBACK_URL, data=body, headers={"Content-Type": "application/json", "X-Spid-Gateway-Timestamp": timestamp, "X-Spid-Gateway-Signature": signature}, method="POST")
        try:
            with urlopen(callback, timeout=10) as response:
                if not 200 <= response.status < 300:
                    raise PermissionDenied("L'applicazione non ha accettato l'identità SPID.")
        except (HTTPError, URLError, OSError) as exc:
            raise PermissionDenied("Impossibile consegnare l'identità SPID all'applicazione.") from exc
        request.session["spid_gateway_code"] = code
        return None

    def custom_redirect(self, user, relay_state, session_info):
        code = self.request.session.pop("spid_gateway_code", None)
        if not code:
            return None
        return f"{settings.SPID_APPLICATION_COMPLETE_URL}?{urlencode({'code': code})}"
