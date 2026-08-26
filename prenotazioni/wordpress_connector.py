"""Client del Web Service WordPress degli appuntamenti storici."""

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone as datetime_timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from access_control.models import CalendarioApertura

from .models import AppuntamentoWordPress, AssegnazionePersonaleWordPress, MappaturaUfficioWordPress, PersonaleWordPress, SedeWordPress, StatoSincronizzazioneWordPress, UnitaOrganizzativaWordPress


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


def _request(url, secret, timeout, *, method="GET", payload=None):
    timestamp = str(int(time.time()))
    signature = hmac.new(secret.encode(), timestamp.encode(), hashlib.sha256).hexdigest()
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if data else {}),
            "X-Aversa-Timestamp": timestamp,
            "X-Aversa-Signature": signature,
        },
    )
    with urlopen(request, timeout=timeout) as response:  # nosec B310 - endpoint configurato dall'ente
        return json.loads(response.read().decode("utf-8"))


def _endpoint(config, name):
    endpoint = config.get(name, "")
    if endpoint:
        return endpoint
    base = config["ENDPOINT"].rsplit("/appuntamenti", 1)[0]
    return f"{base}/{name.lower().replace('_endpoint', '')}"


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


def sincronizza_anagrafiche_wordpress():
    """Importa le anagrafiche WordPress, senza creare oggetti applicativi locali."""
    config = settings.WORDPRESS_APPOINTMENTS
    if not config["ENABLED"] or not config["SHARED_SECRET"]:
        raise WordPressConnectorError("Connettore WordPress non abilitato o chiave non configurata.")
    payload = _request(_endpoint(config, "ANAGRAFICHE_ENDPOINT"), config["SHARED_SECRET"], config["TIMEOUT"])
    if not isinstance(payload, dict):
        raise WordPressConnectorError("Risposta anagrafiche WordPress non valida.")

    sedi = 0
    for item in payload.get("sedi", []):
        if not item.get("id"):
            continue
        SedeWordPress.objects.update_or_create(
            origine_id=str(item["id"]),
            defaults={"nome": item.get("nome", ""), "stato": item.get("stato", "")},
        )
        sedi += 1

    unita = {}
    for item in payload.get("uffici", []):
        if not item.get("id"):
            continue
        unita_id = str(item["id"])
        unita[unita_id], _ = UnitaOrganizzativaWordPress.objects.update_or_create(
            origine_id=unita_id,
            defaults={"nome": item.get("nome", ""), "stato": item.get("stato", "")},
        )

    mappature = 0
    for item in payload.get("calendari", []):
        unita_id, luogo_id = str(item.get("ufficio_id") or ""), str(item.get("sede_id") or "")
        if not unita_id or not luogo_id:
            continue
        sede = SedeWordPress.objects.filter(origine_id=luogo_id).first()
        mapping, _ = MappaturaUfficioWordPress.objects.get_or_create(
            unita_organizzativa_id=unita_id,
            luogo_id=luogo_id,
        )
        unita_wordpress = unita.get(unita_id)
        mapping.unita_organizzativa = unita_wordpress.nome if unita_wordpress else mapping.unita_organizzativa
        mapping.unita_organizzativa_wordpress = unita_wordpress
        mapping.sede = sede
        mapping.calendario_wordpress_id = str(item.get("id") or "")
        mapping.save()
        mappature += 1

    personale = 0
    for item in payload.get("personale", []):
        if not item.get("id"):
            continue
        persona, _ = PersonaleWordPress.objects.update_or_create(
            origine_id=str(item["id"]),
            defaults={
                "username": item.get("username") or "",
                "nome": item.get("nome") or "",
                "cognome": item.get("cognome") or "",
                "email": item.get("email") or "",
                "attivo": bool(item.get("attivo", True)),
            },
        )
        unita_ids = [str(unita_id) for unita_id in item.get("uffici", [])]
        AssegnazionePersonaleWordPress.objects.filter(personale=persona).exclude(
            unita_organizzativa__origine_id__in=unita_ids
        ).delete()
        for unita_id in unita_ids:
            if unita_id in unita:
                AssegnazionePersonaleWordPress.objects.get_or_create(
                    personale=persona,
                    unita_organizzativa=unita[unita_id],
                )
        personale += 1
    return {"sedi": sedi, "unita_organizzative": len(unita), "mappature": mappature, "personale": personale}


def _disponibilita_ufficio(ufficio):
    minuti = settings.PRENOTAZIONI_DURATA_SLOT_MINUTI
    disponibilita = {str(giorno): [] for giorno in range(7)}
    aperture = CalendarioApertura.objects.filter(ufficio=ufficio, su_appuntamento=True).order_by("giorno", "ora_inizio")
    for apertura in aperture:
        corrente = datetime.combine(datetime.today(), apertura.ora_inizio)
        fine = datetime.combine(datetime.today(), apertura.ora_fine)
        while corrente + timedelta(minutes=minuti) <= fine:
            disponibilita[str(apertura.giorno)].append(corrente.strftime("%H:%M"))
            corrente += timedelta(minutes=minuti)
    return {"durata_minuti": minuti, "slot_per_giorno": disponibilita, "eccezioni": []}


def pubblica_calendario_wordpress(mappatura):
    """Pubblica gli orari locali dell'ufficio sul suo calendario WordPress."""
    config = settings.WORDPRESS_APPOINTMENTS
    if not config["ENABLED"] or not config["SHARED_SECRET"]:
        raise WordPressConnectorError("Connettore WordPress non abilitato o chiave non configurata.")
    if not mappatura.ufficio_id:
        raise WordPressConnectorError("Associare prima un ufficio locale alla mappatura.")
    if not mappatura.luogo_id or not mappatura.unita_organizzativa_id:
        raise WordPressConnectorError("La mappatura WordPress non contiene ufficio o sede.")
    payload = {
        "ufficio_id": mappatura.unita_organizzativa_id,
        "sede_id": mappatura.luogo_id,
        "titolo": f"{mappatura.unita_organizzativa} - {mappatura.sede or mappatura.luogo_id}",
        "disponibilita": _disponibilita_ufficio(mappatura.ufficio),
    }
    response = _request(
        _endpoint(config, "CALENDARI_ENDPOINT"),
        config["SHARED_SECRET"],
        config["TIMEOUT"],
        method="POST",
        payload=payload,
    )
    calendario_id = response.get("id") if isinstance(response, dict) else None
    if not calendario_id:
        raise WordPressConnectorError("WordPress non ha restituito l'identificativo del calendario.")
    mappatura.calendario_wordpress_id = str(calendario_id)
    mappatura.save(update_fields=["calendario_wordpress_id", "aggiornato_il"])
    return response


def pubblica_uffici_personale_wordpress(persona):
    """Aggiorna su WordPress le sole competenze ufficio del personale selezionato."""
    config = settings.WORDPRESS_APPOINTMENTS
    if not config["ENABLED"] or not config["SHARED_SECRET"]:
        raise WordPressConnectorError("Connettore WordPress non abilitato o chiave non configurata.")
    endpoint = f'{_endpoint(config, "PERSONALE_ENDPOINT").rstrip("/")}/{persona.origine_id}/uffici'
    response = _request(
        endpoint,
        config["SHARED_SECRET"],
        config["TIMEOUT"],
        method="POST",
        payload={"uffici": list(persona.unita_organizzative.values_list("origine_id", flat=True))},
    )
    if not isinstance(response, dict) or not response.get("aggiornato"):
        raise WordPressConnectorError("WordPress non ha confermato l'aggiornamento delle assegnazioni.")
    return response
