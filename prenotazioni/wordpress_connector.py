"""Client del Web Service WordPress degli appuntamenti storici."""

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone as datetime_timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import AppuntamentoWordPress, MappaturaUfficioWordPress, StatoSincronizzazioneWordPress


class WordPressConnectorError(RuntimeError):
    pass


def _parse_datetime(value, required=False):
    if not value:
        if required:
            raise WordPressConnectorError("L'appuntamento WordPress non ha una data di aggiornamento valida.")
        return None
    if value.startswith("0000-00-00"):
        # Alcuni appuntamenti storici WordPress non hanno date GMT valorizzate.
        return datetime(1970, 1, 1, tzinfo=datetime_timezone.utc) if required else None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        if required:
            raise WordPressConnectorError(f"Data WordPress non valida: {value!r}") from exc
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, datetime_timezone.utc)
    return parsed


def _request(url, secret, timeout):
    timestamp = str(int(time.time()))
    signature = hmac.new(secret.encode(), timestamp.encode(), hashlib.sha256).hexdigest()
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "X-Aversa-Timestamp": timestamp,
            "X-Aversa-Signature": signature,
        },
    )
    with urlopen(request, timeout=timeout) as response:  # nosec B310 - endpoint configurato dall'ente
        return json.loads(response.read().decode("utf-8"))


def _mappatura(item):
    unita_id = str(item.get("unita_organizzativa_id") or "")
    luogo_id = str(item.get("luogo_id") or "")
    if not unita_id and not luogo_id:
        return None
    mapping, _ = MappaturaUfficioWordPress.objects.get_or_create(
        unita_organizzativa_id=unita_id,
        luogo_id=luogo_id,
        defaults={"unita_organizzativa": item.get("unita_organizzativa", "")},
    )
    if item.get("unita_organizzativa") and mapping.unita_organizzativa != item["unita_organizzativa"]:
        mapping.unita_organizzativa = item["unita_organizzativa"]
        mapping.save(update_fields=["unita_organizzativa", "aggiornato_il"])
    return mapping


def _salva(item):
    mapping = _mappatura(item)
    defaults = {
        "origine_stato": item.get("stato", ""),
        "origine_aggiornato_il": _parse_datetime(item["aggiornato_il"], required=True),
        "prenotato_il": _parse_datetime(item.get("prenotato_il")),
        "data_ora_inizio": _parse_datetime(item.get("data_ora_inizio")),
        "data_ora_fine": _parse_datetime(item.get("data_ora_fine")),
        "unita_organizzativa_id": str(item.get("unita_organizzativa_id") or ""),
        "unita_organizzativa": item.get("unita_organizzativa", ""),
        "luogo_id": str(item.get("luogo_id") or ""),
        "servizio": item.get("servizio", ""),
        "email": item.get("email", ""),
        "codice_fiscale": (item.get("codice_fiscale", "") or "").upper(),
        "dettaglio_richiesta": item.get("dettaglio_richiesta", ""),
        "ufficio": mapping.ufficio if mapping else None,
        "dati_origine": item,
    }
    return AppuntamentoWordPress.objects.update_or_create(origine_id=item["id"], defaults=defaults)


def sincronizza_appuntamenti_wordpress():
    config = settings.WORDPRESS_APPOINTMENTS
    if not config["ENABLED"]:
        raise WordPressConnectorError("Connettore WordPress non abilitato.")
    if not config["ENDPOINT"] or not config["SHARED_SECRET"]:
        raise WordPressConnectorError("Endpoint o chiave del connettore WordPress non configurati.")

    stato, _ = StatoSincronizzazioneWordPress.objects.get_or_create(chiave="appuntamenti")
    cursor = stato.cursore
    page = 1
    totale = creati = aggiornati = 0
    cursor_finale = cursor

    while True:
        params = {"page": page, "per_page": config["PAGE_SIZE"]}
        if cursor:
            params["updated_after"] = cursor.astimezone(datetime_timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        separatore = "&" if "?" in config["ENDPOINT"] else "?"
        payload = _request(f'{config["ENDPOINT"]}{separatore}{urlencode(params)}', config["SHARED_SECRET"], config["TIMEOUT"])
        items = payload.get("items")
        if not isinstance(items, list):
            raise WordPressConnectorError("Risposta WS WordPress non valida.")

        with transaction.atomic():
            for item in items:
                if not isinstance(item, dict) or "id" not in item or "aggiornato_il" not in item:
                    raise WordPressConnectorError("Un appuntamento WS non contiene id o data di aggiornamento.")
                _, creato = _salva(item)
                creati += int(creato)
                aggiornati += int(not creato)
                totale += 1
                aggiornato_il = _parse_datetime(item["aggiornato_il"])
                if cursor_finale is None or aggiornato_il > cursor_finale:
                    cursor_finale = aggiornato_il

        if not payload.get("has_more"):
            break
        page += 1

    stato.cursore = cursor_finale
    stato.ultima_esecuzione_il = timezone.now()
    stato.save(update_fields=["cursore", "ultima_esecuzione_il"])
    return {"totale": totale, "creati": creati, "aggiornati": aggiornati, "cursore": cursor_finale}
