"""Collegamento prudente fra Persone pubbliche WordPress e utenti Django."""

import re
import unicodedata

from django.contrib.auth import get_user_model


def _chiave_nominativo(nome, cognome):
    valore = unicodedata.normalize("NFKD", f"{nome or ''} {cognome or ''}")
    valore = "".join(carattere for carattere in valore if not unicodedata.combining(carattere))
    return re.sub(r"[^a-z0-9]+", "", valore.casefold())


def collega_persone_pubbliche(queryset):
    """Collega solo corrispondenze univoche nome+cognome e non sovrascrive scelte manuali."""
    Utente = get_user_model()
    per_nominativo = {}
    for utente in Utente.objects.filter(is_active=True).only("id", "first_name", "last_name"):
        chiave = _chiave_nominativo(utente.first_name, utente.last_name)
        if chiave:
            per_nominativo.setdefault(chiave, []).append(utente)

    risultato = {"collegati": 0, "gia_collegati": 0, "nessuna_corrispondenza": 0, "ambigui": 0}
    for persona in queryset.select_related("utente"):
        if persona.utente_id:
            risultato["gia_collegati"] += 1
            continue
        candidati = per_nominativo.get(_chiave_nominativo(persona.nome, persona.cognome), [])
        if len(candidati) == 1:
            persona.utente = candidati[0]
            persona.save(update_fields=["utente", "aggiornato_il"])
            risultato["collegati"] += 1
        elif len(candidati) > 1:
            risultato["ambigui"] += 1
        else:
            risultato["nessuna_corrispondenza"] += 1
    return risultato
