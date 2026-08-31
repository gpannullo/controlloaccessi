"""Client del Web Service WordPress degli appuntamenti storici."""

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone as datetime_timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from access_control.models import CalendarioApertura, GruppoOrganizzativo

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
    try:
        with urlopen(request, timeout=timeout) as response:  # nosec B310 - endpoint configurato dall'ente
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        dettaglio = exc.read().decode("utf-8", errors="replace").strip()
        raise WordPressConnectorError(f"WordPress ha risposto con errore HTTP {exc.code}: {dettaglio[:500]}") from exc
    except URLError as exc:
        raise WordPressConnectorError(f"WordPress non è raggiungibile: {exc.reason}") from exc
    except (TimeoutError, json.JSONDecodeError) as exc:
        raise WordPressConnectorError(f"Risposta WordPress non valida o scaduta: {exc}") from exc


def _endpoint(config, name):
    endpoint = config.get(name, "")
    if endpoint:
        return endpoint
    base = config["ENDPOINT"].rsplit("/appuntamenti", 1)[0]
    percorsi = {
        "ANAGRAFICHE_ENDPOINT": "anagrafiche",
        "CALENDARI_ENDPOINT": "calendari",
        "PERSONE_PUBBLICHE_ENDPOINT": "persone-pubbliche",
        "UNITE_ORGANIZZATIVE_ENDPOINT": "unita-organizzative",
    }
    try:
        return f"{base}/{percorsi[name]}"
    except KeyError as exc:
        raise WordPressConnectorError(f"Endpoint WordPress non riconosciuto: {name}") from exc


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
    for item in payload.get("persone_pubbliche", []):
        if not item.get("id"):
            continue
        persona, creata = PersonaleWordPress.objects.get_or_create(
            origine_id=str(item["id"]),
            defaults={
                "titolo": item.get("titolo") or "",
                "nome": item.get("nome") or "",
                "cognome": item.get("cognome") or "",
                "competenze": item.get("competenze") or "",
                "attivo": bool(item.get("attivo", True)),
            },
        )
        # Django è l'owner dell'anagrafica: da WordPress importiamo solo le
        # persone non ancora presenti, senza sovrascrivere modifiche locali.
        if not creata:
            personale += 1
            continue
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


def simula_allineamento_persone_pubbliche_wordpress():
    """Confronta le associazioni locali con entrambi i lati pubblicati su WordPress.

    Non esegue scritture: serve a verificare preventivamente quali persone
    dovranno essere ripubblicate dal connettore reciproco.
    """
    config = settings.WORDPRESS_APPOINTMENTS
    if not config["ENABLED"] or not config["SHARED_SECRET"]:
        raise WordPressConnectorError("Connettore WordPress non abilitato o chiave non configurata.")
    payload = _request(_endpoint(config, "ANAGRAFICHE_ENDPOINT"), config["SHARED_SECRET"], config["TIMEOUT"])
    if not isinstance(payload, dict):
        raise WordPressConnectorError("Risposta anagrafiche WordPress non valida.")

    persone_remote = {
        str(item.get("id")): {str(unita_id) for unita_id in item.get("uffici", [])}
        for item in payload.get("persone_pubbliche", [])
        if item.get("id")
    }
    unita_remote = {
        str(item.get("id")): {str(persona_id) for persona_id in item.get("persone", [])}
        for item in payload.get("uffici", [])
        if item.get("id")
    }

    attese_per_persona = {}
    attese_per_unita = {}
    persone_locali = PersonaleWordPress.objects.prefetch_related("unita_organizzative")
    for persona in persone_locali:
        persona_id = str(persona.origine_id)
        unita_ids = {str(unita_id) for unita_id in persona.unita_organizzative.values_list("origine_id", flat=True)}
        attese_per_persona[persona_id] = unita_ids
        for unita_id in unita_ids:
            attese_per_unita.setdefault(unita_id, set()).add(persona_id)

    persone_da_pubblicare = []
    for persona_id, attese in attese_per_persona.items():
        remote = persone_remote.get(persona_id, set())
        if remote != attese:
            persone_da_pubblicare.append({
                "persona_id": persona_id,
                "aggiunte": sorted(attese - remote),
                "rimozioni": sorted(remote - attese),
            })

    aggiunte_in_unita = []
    rimozioni_in_unita = []
    persone_note = set(attese_per_persona)
    persone_da_ripubblicare = set()
    for unita_id in set(unita_remote) | set(attese_per_unita):
        remote = unita_remote.get(unita_id, set())
        attese = attese_per_unita.get(unita_id, set())
        da_aggiungere = attese - remote
        da_rimuovere = (remote & persone_note) - attese
        if da_aggiungere:
            aggiunte_in_unita.append({"unita_id": unita_id, "persone": sorted(da_aggiungere)})
            persone_da_ripubblicare.update(da_aggiungere)
        if da_rimuovere:
            rimozioni_in_unita.append({"unita_id": unita_id, "persone": sorted(da_rimuovere)})
            persone_da_ripubblicare.update(da_rimuovere)

    persone_per_id = {str(persona.origine_id): str(persona) for persona in persone_locali}

    return {
        "persone_da_pubblicare": persone_da_pubblicare,
        "persone_da_ripubblicare": [
            {"persona_id": persona_id, "nome": persone_per_id.get(persona_id, "Persona non presente in Django")}
            for persona_id in sorted(persone_da_ripubblicare, key=lambda item: persone_per_id.get(item, "").casefold())
        ],
        "aggiunte_in_unita": aggiunte_in_unita,
        "rimozioni_in_unita": rimozioni_in_unita,
    }


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


def pubblica_persona_pubblica_wordpress(persona):
    """Pubblica su WordPress l'anagrafica locale della persona pubblica."""
    config = settings.WORDPRESS_APPOINTMENTS
    if not config["ENABLED"] or not config["SHARED_SECRET"]:
        raise WordPressConnectorError("Connettore WordPress non abilitato o chiave non configurata.")
    endpoint = f'{_endpoint(config, "PERSONE_PUBBLICHE_ENDPOINT").rstrip("/")}/{persona.origine_id}'
    response = _request(
        endpoint,
        config["SHARED_SECRET"],
        config["TIMEOUT"],
        method="POST",
        payload={
            "titolo": persona.titolo,
            "nome": persona.nome,
            "cognome": persona.cognome,
            "competenze": persona.competenze,
            "attivo": persona.attivo,
            "organizzazioni": list(persona.unita_organizzative.values_list("origine_id", flat=True)),
        },
    )
    if not isinstance(response, dict) or not response.get("aggiornato"):
        raise WordPressConnectorError("WordPress non ha confermato l'aggiornamento della persona pubblica.")
    return response


def pubblica_organizzazioni_persona_pubblica_wordpress(persona):
    """Compatibilità: pubblica l'intera persona, incluse le organizzazioni."""
    return pubblica_persona_pubblica_wordpress(persona)


def crea_unita_organizzativa_wordpress(ufficio):
    """Crea l'unità organizzativa WordPress collegata all'ufficio locale."""
    config = settings.WORDPRESS_APPOINTMENTS
    if not config["ENABLED"] or not config["SHARED_SECRET"]:
        raise WordPressConnectorError("Connettore WordPress non abilitato o chiave non configurata.")
    response = _request(
        _endpoint(config, "UNITE_ORGANIZZATIVE_ENDPOINT"),
        config["SHARED_SECRET"],
        config["TIMEOUT"],
        method="POST",
        payload={"nome": ufficio.nome},
    )
    origine_id = response.get("id") if isinstance(response, dict) else None
    if not origine_id:
        raise WordPressConnectorError("WordPress non ha restituito l'identificativo dell'unità organizzativa.")
    unita, _ = UnitaOrganizzativaWordPress.objects.update_or_create(
        origine_id=str(origine_id),
        defaults={
            "nome": response.get("nome") or ufficio.nome,
            "stato": response.get("stato") or "publish",
            "ufficio": ufficio,
        },
    )
    return unita


def pubblica_unita_organizzativa_wordpress(unita):
    """Aggiorna su WordPress i dati locali dell'Unità organizzativa."""
    config = settings.WORDPRESS_APPOINTMENTS
    if not config["ENABLED"] or not config["SHARED_SECRET"]:
        raise WordPressConnectorError("Connettore WordPress non abilitato o chiave non configurata.")
    endpoint = f'{_endpoint(config, "UNITE_ORGANIZZATIVE_ENDPOINT").rstrip("/")}/{unita.origine_id}'
    response = _request(
        endpoint,
        config["SHARED_SECRET"],
        config["TIMEOUT"],
        method="POST",
        payload={
            "nome": unita.nome,
            "attivo": unita.stato == "publish",
        },
    )
    if not isinstance(response, dict) or not response.get("aggiornato"):
        raise WordPressConnectorError("WordPress non ha confermato l'aggiornamento dell'Unità organizzativa.")
    return response


def crea_persona_pubblica_wordpress(utente):
    """Crea e collega a WordPress la Persona pubblica dell'utente Django."""
    if PersonaleWordPress.objects.filter(utente=utente).exists():
        raise WordPressConnectorError(f"L'utente {utente.username} è già collegato a una Persona pubblica.")
    config = settings.WORDPRESS_APPOINTMENTS
    if not config["ENABLED"] or not config["SHARED_SECRET"]:
        raise WordPressConnectorError("Connettore WordPress non abilitato o chiave non configurata.")
    unita = UnitaOrganizzativaWordPress.objects.filter(
        ufficio__gruppi__django_group__user=utente,
        ufficio__gruppi__tipo=GruppoOrganizzativo.Tipo.ORGANIZZATIVO,
    ).distinct()
    nome = utente.first_name.strip()
    cognome = utente.last_name.strip()
    titolo = " ".join(item for item in (nome, cognome) if item) or utente.username
    response = _request(
        _endpoint(config, "PERSONE_PUBBLICHE_ENDPOINT"),
        config["SHARED_SECRET"],
        config["TIMEOUT"],
        method="POST",
        payload={
            "titolo": titolo,
            "nome": nome,
            "cognome": cognome,
            "competenze": "",
            "attivo": utente.is_active,
            "organizzazioni": list(unita.values_list("origine_id", flat=True)),
        },
    )
    origine_id = response.get("id") if isinstance(response, dict) else None
    if not origine_id:
        raise WordPressConnectorError("WordPress non ha restituito l'identificativo della Persona pubblica.")
    persona = PersonaleWordPress.objects.create(
        origine_id=str(origine_id),
        titolo=response.get("titolo") or titolo,
        nome=response.get("nome") or nome,
        cognome=response.get("cognome") or cognome,
        competenze="",
        attivo=bool(response.get("attivo", utente.is_active)),
        utente=utente,
    )
    for unita_organizzativa in unita:
        AssegnazionePersonaleWordPress.objects.get_or_create(
            personale=persona,
            unita_organizzativa=unita_organizzativa,
        )
    return persona
