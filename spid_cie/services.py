import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from .models import IdentitaDigitale, MessaggioIO


class SpidCieConfigurationError(Exception):
    pass


class AppIOService:
    """Client per i messaggi personali del servizio App IO dell'Ente."""

    @classmethod
    def configuration(cls):
        return settings.APP_IO

    @classmethod
    def is_configured(cls):
        config = cls.configuration()
        return bool(config["ENABLED"] and config["SUBSCRIPTION_KEY"])

    @classmethod
    def invia_messaggio(cls, codice_fiscale, oggetto, contenuto, *, riferimento_esterno=""):
        codice_fiscale = (codice_fiscale or "").strip().upper()
        oggetto = (oggetto or "").strip()
        contenuto = (contenuto or "").strip()
        if len(codice_fiscale) != 16:
            raise ValueError("Per App IO è necessario un codice fiscale di 16 caratteri.")
        if not 10 <= len(oggetto) <= 120:
            raise ValueError("L'oggetto del messaggio IO deve contenere da 10 a 120 caratteri.")
        if not contenuto:
            raise ValueError("Il contenuto del messaggio IO è obbligatorio.")

        message = MessaggioIO.objects.create(
            codice_fiscale=codice_fiscale,
            oggetto=oggetto,
            contenuto=contenuto,
            riferimento_esterno=riferimento_esterno[:64],
            stato=MessaggioIO.Stato.NON_CONFIGURATO,
        )
        if not cls.is_configured():
            return message

        config = cls.configuration()
        payload = {
            "fiscal_code": codice_fiscale,
            "feature_level_type": "STANDARD",
            "content": {"subject": oggetto, "markdown": contenuto},
        }
        request = Request(
            f'{config["BASE_URL"].rstrip("/")}/messages',
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Ocp-Apim-Subscription-Key": config["SUBSCRIPTION_KEY"],
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=config["TIMEOUT"]) as response:
                body = response.read().decode("utf-8")
            data = json.loads(body) if body else {}
            message.stato = MessaggioIO.Stato.INVIATO
            message.messaggio_io_id = str(data.get("id", ""))[:100]
            message.risposta = body
        except HTTPError as exc:
            message.risposta = exc.read().decode("utf-8", errors="replace")[:4000]
            message.stato = MessaggioIO.Stato.NON_ABILITATO if exc.code in {404, 409} else MessaggioIO.Stato.ERRORE
        except (URLError, TimeoutError, OSError) as exc:
            message.stato = MessaggioIO.Stato.ERRORE
            message.risposta = str(exc)[:4000]
        message.save(update_fields=["stato", "messaggio_io_id", "risposta"])
        return message

    @classmethod
    def invia_conferma_prenotazione(cls, prenotazione):
        """Invia una conferma personale senza dati nel titolo, come richiesto da IO."""
        appuntamento = timezone.localtime(prenotazione.data_ora).strftime("%d/%m/%Y alle %H:%M")
        contenuto = (
            "# Prenotazione ricevuta\n\n"
            f"La tua prenotazione presso **{prenotazione.ufficio.nome}** è fissata per **{appuntamento}**.\n\n"
            f"Codice prenotazione: **{prenotazione.codice}**.\n\n"
            "Conserva questo messaggio e presentati all'ufficio nell'orario indicato."
        )
        return cls.invia_messaggio(
            prenotazione.codice_fiscale,
            "Conferma prenotazione",
            contenuto,
            riferimento_esterno=prenotazione.codice,
        )


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
