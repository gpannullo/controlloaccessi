"""Client PDND per la fruizione degli e-service autorizzati all'Ente.

Gli endpoint e i campi dei payload appartengono al singolo e-service: non sono
codificati nel sorgente e vengono quindi configurati dopo l'adesione in PDND.
Le chiavi private restano nel filesystem protetto del server.
"""

import hashlib
import json
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings

from .models import PDNDAuditLog


class PDNDConfigurationError(Exception):
    pass


class PDNDService:
    SERVIZI = {
        "anpr-soggetto": PDNDAuditLog.Servizio.ANPR_SOGGETTO,
        "anpr-famiglia": PDNDAuditLog.Servizio.ANPR_FAMIGLIA,
        "inps-isee": PDNDAuditLog.Servizio.INPS_ISEE,
        "durc": PDNDAuditLog.Servizio.DURC,
    }

    @classmethod
    def configuration(cls):
        return settings.PDND

    @classmethod
    def servizio(cls, slug):
        try:
            return cls.SERVIZI[slug]
        except KeyError as exc:
            raise PDNDConfigurationError("Servizio PDND non riconosciuto.") from exc

    @classmethod
    def _audit(cls, servizio, identificativo, operatore):
        digest = hashlib.sha256(
            f'{settings.SECRET_KEY}:{identificativo}'.encode("utf-8")
        ).hexdigest()
        return PDNDAuditLog.objects.create(
            operatore=operatore if getattr(operatore, "is_authenticated", False) else None,
            servizio=servizio,
            identificativo_hash=digest,
            esito=PDNDAuditLog.Esito.NON_CONFIGURATA,
        )

    @classmethod
    def _private_key(cls):
        key_path = cls.configuration()["PRIVATE_KEY_PATH"]
        if not key_path:
            raise PDNDConfigurationError("Manca il percorso della chiave privata PDND.")
        try:
            with open(key_path, encoding="utf-8") as key_file:
                return key_file.read()
        except OSError as exc:
            raise PDNDConfigurationError("Impossibile leggere la chiave privata PDND.") from exc

    @classmethod
    def _client_assertion(cls, purpose_id):
        try:
            from authlib.jose import jwt
        except ImportError as exc:
            raise PDNDConfigurationError(
                "Dipendenza Authlib non installata sul server."
            ) from exc
        config = cls.configuration()
        now = int(time.time())
        payload = {
            "iss": config["CLIENT_ID"],
            "sub": config["CLIENT_ID"],
            "aud": config["CLIENT_ASSERTION_AUDIENCE"],
            "purposeId": purpose_id,
            "iat": now,
            "nbf": now,
            "exp": now + 300,
            "jti": str(uuid.uuid4()),
        }
        return jwt.encode(
            {"alg": "RS256", "kid": config["KID"], "typ": "JWT"},
            payload,
            cls._private_key(),
        ).decode("utf-8")

    @classmethod
    def _access_token(cls, purpose_id):
        config = cls.configuration()
        required = ("TOKEN_URL", "CLIENT_ID", "KID", "PRIVATE_KEY_PATH")
        if not config["ENABLED"] or not all(config[key] for key in required):
            raise PDNDConfigurationError("Autenticazione PDND non configurata.")
        body = urlencode({
            "grant_type": "client_credentials",
            "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
            "client_id": config["CLIENT_ID"],
            "client_assertion": cls._client_assertion(purpose_id),
        }).encode("utf-8")
        request = Request(config["TOKEN_URL"], data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
        with urlopen(request, timeout=config["TIMEOUT"]) as response:
            payload = json.loads(response.read().decode("utf-8"))
        token = payload.get("access_token")
        if not token:
            raise PDNDConfigurationError("PDND non ha restituito il voucher di accesso.")
        return token

    @classmethod
    def interroga(cls, slug, identificativo, operatore):
        servizio = cls.servizio(slug)
        audit = cls._audit(servizio, identificativo, operatore)
        service_config = cls.configuration()["SERVICES"].get(servizio, {})
        if not service_config.get("ENDPOINT") or not service_config.get("PURPOSE_ID"):
            return None, audit
        try:
            token = cls._access_token(service_config["PURPOSE_ID"])
            field = service_config.get("PAYLOAD_FIELD", "codiceFiscale")
            method = service_config.get("METHOD", "POST").upper()
            endpoint = service_config["ENDPOINT"].format(identificativo=identificativo)
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Correlation-Id": str(uuid.uuid4()),
            }
            payload = {field: identificativo}
            if method == "GET":
                separator = "&" if "?" in endpoint else "?"
                endpoint = f"{endpoint}{separator}{urlencode(payload)}"
                body = None
            else:
                body = json.dumps(payload).encode("utf-8")
            request = Request(endpoint, data=body, headers=headers, method=method)
            with urlopen(request, timeout=cls.configuration()["TIMEOUT"]) as response:
                response_body = response.read().decode("utf-8")
                audit.request_id = response.headers.get("X-Request-Id", "")[:100]
            result = json.loads(response_body) if response_body else {}
            audit.esito = PDNDAuditLog.Esito.ESEGUITA
            audit.save(update_fields=["esito", "request_id"])
            return result, audit
        except HTTPError as exc:
            audit.esito = PDNDAuditLog.Esito.NEGATA if exc.code in {401, 403, 404, 422} else PDNDAuditLog.Esito.ERRORE
            audit.dettaglio_errore = f"Risposta PDND {exc.code}"[:500]
        except (URLError, OSError, ValueError, PDNDConfigurationError) as exc:
            audit.esito = PDNDAuditLog.Esito.ERRORE
            audit.dettaglio_errore = str(exc)[:500]
        audit.save(update_fields=["esito", "dettaglio_errore"])
        return None, audit
