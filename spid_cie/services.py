from urllib.parse import urlparse

from django.conf import settings
from django.urls import reverse

from .models import IdentitaDigitale


class SpidCieConfigurationError(Exception):
    pass


class SpidCieService:
    """Adapter OIDC per la federazione/aggregatore dell'Ente.

    L'adapter usa esclusivamente metadata OIDC verificabili. La federazione
    nazionale diretta, se richiede JAR/client assertion, resta configurabile
    presso l'aggregatore senza salvare chiavi o token nel database.
    """

    SESSION_IDENTITY_KEY = "spid_cie_identity_id"
    SESSION_NEXT_KEY = "spid_cie_next"
    SESSION_PROVIDER_KEY = "spid_cie_provider"

    @classmethod
    def configuration(cls):
        return settings.SPID_CIE

    @classmethod
    def is_configured(cls):
        config = cls.configuration()
        return bool(
            config["ENABLED"]
            and config["SERVER_METADATA_URL"]
            and config["CLIENT_ID"]
            and config["CLIENT_SECRET"]
        )

    @classmethod
    def client(cls):
        if not cls.is_configured():
            raise SpidCieConfigurationError(
                "L'accesso SPID/CIE non è ancora configurato."
            )
        try:
            from authlib.integrations.django_client import OAuth
        except ImportError as exc:
            raise SpidCieConfigurationError(
                "Dipendenza Authlib non installata sul server."
            ) from exc

        config = cls.configuration()
        oauth = OAuth()
        oauth.register(
            "spid_cie",
            client_id=config["CLIENT_ID"],
            client_secret=config["CLIENT_SECRET"],
            server_metadata_url=config["SERVER_METADATA_URL"],
            client_kwargs={"scope": config["SCOPE"]},
        )
        return oauth.spid_cie

    @classmethod
    def safe_next_url(cls, value):
        if not value:
            return reverse("prenotazioni:wizard")
        parsed = urlparse(value)
        if parsed.scheme or parsed.netloc or not value.startswith("/"):
            return reverse("prenotazioni:wizard")
        return value

    @classmethod
    def identity_from_session(cls, request):
        identity_id = request.session.get(cls.SESSION_IDENTITY_KEY)
        if not identity_id:
            return None
        return IdentitaDigitale.objects.filter(pk=identity_id).first()

    @classmethod
    def save_identity(cls, token, provider):
        userinfo = token.get("userinfo") or {}
        subject = str(userinfo.get("sub") or "").strip()
        if not subject:
            raise SpidCieConfigurationError(
                "La federazione non ha restituito l'identificativo del cittadino."
            )
        fiscal_code = str(
            userinfo.get("fiscal_number")
            or userinfo.get("fiscal_code")
            or userinfo.get("codice_fiscale")
            or ""
        ).upper().replace("TINIT-", "")
        identity, _ = IdentitaDigitale.objects.update_or_create(
            provider=provider,
            subject=subject,
            defaults={
                "codice_fiscale": fiscal_code[:16],
                "nome": str(userinfo.get("given_name") or userinfo.get("name") or "")[:100],
                "cognome": str(userinfo.get("family_name") or "")[:100],
                "email": str(userinfo.get("email") or "")[:254],
            },
        )
        return identity
