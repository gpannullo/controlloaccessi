"""Sincronizzazione della pubblicazione WordPress a partire dall'Ufficio.

L'ufficio locale è l'anagrafica proprietaria: le unità organizzative
WordPress sono esclusivamente la sua proiezione sul sito pubblico.
"""

from django.db.models import Q


def allinea_e_verifica_ufficio_wordpress(ufficio):
    from prenotazioni.models import PersonaleWordPress
    from prenotazioni.wordpress_connector import leggi_anagrafiche_wordpress, WordPressConnectorError

    unita = list(ufficio.unita_organizzative_wordpress.all())
    if not unita:
        raise WordPressConnectorError('Nessuna Unità organizzativa WordPress collegata.')
    ids = set(ufficio.assegnazioni_personale.filter(attiva=True).values_list('utente_id', flat=True))
    if ufficio.responsabile_id:
        ids.add(ufficio.responsabile_id)
    linked = set(PersonaleWordPress.objects.filter(utente_id__in=ids, attivo=True).exclude(origine_id='').values_list('utente_id', flat=True))
    if ids - linked:
        raise WordPressConnectorError('Persone pubbliche attive mancanti per gli utenti ID: %s. Nessun invio eseguito.' % ', '.join(map(str, sorted(ids-linked))))

    def snapshot():
        remote = {str(item.get('id')): item for item in leggi_anagrafiche_wordpress()['uffici']}
        for unit in unita:
            item = remote.get(str(unit.origine_id))
            if not item or not {'persone', 'responsabile', 'nome', 'stato'} <= item.keys() or not isinstance(item['persone'], list):
                raise WordPressConnectorError('Unità WP %s non verificabile: dati incompleti o connettore da aggiornare.' % unit.origine_id)
        return remote

    snapshot()  # Fail before writing if verification is not supported.
    result = sincronizza_ufficio_wordpress(ufficio)
    remote = snapshot()
    differences = []
    for unit in unita:
        unit.refresh_from_db()
        item = remote[str(unit.origine_id)]
        expected = {str(value) for value in unit.personale_wordpress.values_list('origine_id', flat=True)}
        actual = {str(value) for value in item['persone']}
        if expected != actual:
            differences.append('WP %s: personale mancante [%s], in più [%s]' % (unit.origine_id, ', '.join(sorted(expected-actual)), ', '.join(sorted(actual-expected))))
        responsible = str(unit.responsabile.origine_id) if unit.responsabile_id else ''
        if str(item['responsabile'] or '') != responsible:
            differences.append('WP %s: responsabile non allineato' % unit.origine_id)
        if item['nome'] != unit.nome or item['stato'] != unit.stato:
            differences.append('WP %s: nome o stato editoriale non allineato' % unit.origine_id)
    result['differenze'] = differences
    return result


def sincronizza_ufficio_wordpress(ufficio):
    """Allinea personale, responsabile e dati dell'ufficio sulle unità mappate.

    Restituisce il numero di unità e persone pubblicate. Le persone abilitate
    nell'ufficio diventano esattamente le persone pubbliche mostrate per ogni
    unità organizzativa mappata all'ufficio.
    """
    # Import ritardati: prenotazioni dipende da access_control per il mapping.
    from prenotazioni.models import (
        AssegnazionePersonaleWordPress,
        PersonaleWordPress,
    )
    from prenotazioni.wordpress_connector import (
        pubblica_persona_pubblica_wordpress,
        pubblica_unita_organizzativa_wordpress,
    )

    unita = list(ufficio.unita_organizzative_wordpress.all())
    if not unita:
        return {"unita": 0, "persone": 0, "responsabile_non_pubblico": False}

    utenti_attivi = ufficio.assegnazioni_personale.filter(
        attiva=True,
    ).values_list("utente_id", flat=True)
    persone_attive = list(
        PersonaleWordPress.objects.filter(
            utente_id__in=utenti_attivi,
            attivo=True,
        ).distinct()
    )

    responsabile = None
    if ufficio.responsabile_id:
        responsabile = (
            PersonaleWordPress.objects.filter(
                utente_id=ufficio.responsabile_id,
                attivo=True,
            )
            .order_by("pk")
            .first()
        )

    # Comprende le persone che erano collegate prima della modifica, affinché
    # vengano pubblicate anche le rimozioni dalla pagina WordPress.
    persone_coinvolte = list(
        PersonaleWordPress.objects.filter(
            Q(pk__in=[persona.pk for persona in persone_attive])
            | Q(unita_organizzative__in=unita)
        )
        .distinct()
    )
    persone_attive_ids = {persona.pk for persona in persone_attive}

    AssegnazionePersonaleWordPress.objects.filter(
        unita_organizzativa__in=unita,
    ).exclude(personale_id__in=persone_attive_ids).delete()
    esistenti = set(
        AssegnazionePersonaleWordPress.objects.filter(
            unita_organizzativa__in=unita,
            personale_id__in=persone_attive_ids,
        ).values_list("unita_organizzativa_id", "personale_id")
    )
    AssegnazionePersonaleWordPress.objects.bulk_create(
        [
            AssegnazionePersonaleWordPress(
                unita_organizzativa=singola_unita,
                personale=persona,
            )
            for singola_unita in unita
            for persona in persone_attive
            if (singola_unita.pk, persona.pk) not in esistenti
        ]
    )

    for persona in persone_coinvolte:
        pubblica_persona_pubblica_wordpress(persona)

    for singola_unita in unita:
        # Nome e stato editoriale rimangono propri dell'Unità Organizzativa:
        # dal modello Ufficio derivano esclusivamente personale e responsabile.
        singola_unita.responsabile = responsabile
        singola_unita.save(update_fields=["responsabile", "aggiornato_il"])
        pubblica_unita_organizzativa_wordpress(singola_unita)

    return {
        "unita": len(unita),
        "persone": len(persone_coinvolte),
        "responsabile_non_pubblico": bool(ufficio.responsabile_id and not responsabile),
    }
