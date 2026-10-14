import hashlib
import json
from dataclasses import asdict

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.utils.module_loading import import_string

from .contracts import (ProtocolloBackend, EsitoProtocollo, ErroreProtocollo,
                       ConfigurazioneProtocolloError, ValidazioneProtocolloError,
                       EsitoIncertoError, InvioBloccatoError)
from .models import RegistrazioneProtocollo


def get_backend():
    path = settings.PROTOCOLLAZIONE_BACKEND
    cls = import_string(path)
    if not isinstance(cls, type) or not issubclass(cls, ProtocolloBackend):
        raise ConfigurazioneProtocolloError('Backend non conforme a ProtocolloBackend.')
    return cls()


def protocolla(richiesta, *, chiave, operatore):
    """Unico ingresso pubblico. Riutilizzare la stessa chiave per lo stesso documento.

    Non chiamare dentro transaction.atomic/ATOMIC_REQUESTS: il registro deve essere
    persistito PRIMA dell'effetto remoto e non deve poter essere annullato dopo.
    """
    if not operatore or not operatore.is_active or not operatore.has_perm('protocollazione.add_registrazioneprotocollo'):
        raise PermissionDenied('Non autorizzato alla protocollazione.')
    if not isinstance(chiave, str) or not chiave.strip() or len(chiave) > 200:
        raise ValidazioneProtocolloError('Chiave richiesta obbligatoria, massimo 200 caratteri.')
    if not connection.get_autocommit() or connection.in_atomic_block:
        raise InvioBloccatoError('Protocollare fuori da transazioni database aperte.')
    if not isinstance(richiesta.documento.contenuto, bytes):
        raise ValidazioneProtocolloError('Il documento deve contenere bytes.')
    content_hash = hashlib.sha256(richiesta.documento.contenuto).hexdigest()
    data = asdict(richiesta)
    data['documento']['contenuto'] = content_hash
    digest = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    def existing_result(row):
        if row.impronta_richiesta != digest:
            raise InvioBloccatoError('Chiave già utilizzata con dati diversi.')
        if row.stato == row.Stato.COMPLETATO:
            return EsitoProtocollo(**row.esito)
        raise InvioBloccatoError('Richiesta già presente. Verificare l’esito prima di qualsiasi nuovo invio.')
    existing = RegistrazioneProtocollo.objects.filter(chiave=chiave).first()
    if existing:
        return existing_result(existing)
    if not settings.PROTOCOLLAZIONE_ENABLED:
        raise ConfigurazioneProtocolloError('Protocollazione non abilitata.')
    backend = get_backend()
    backend.valida(richiesta)
    row, created = RegistrazioneProtocollo.objects.get_or_create(chiave=chiave, defaults={
        'backend':settings.PROTOCOLLAZIONE_BACKEND,'impronta_richiesta':digest,
        'impronta_documento':content_hash,'nome_documento':richiesta.documento.nome,
        'oggetto':richiesta.oggetto,'operatore':operatore,
    })
    if not created:
        return existing_result(row)
    try:
        result = backend.protocolla(richiesta)
        if not isinstance(result, EsitoProtocollo) or not all((result.anno,result.numero,result.segnatura)):
            raise EsitoIncertoError('Risposta incompleta: verificare nel gestionale.')
    except ErroreProtocollo as exc:
        row.stato = row.Stato.INCERTO if isinstance(exc, EsitoIncertoError) else row.Stato.ERRORE
        row.errore = type(exc).__name__
        row.save(update_fields=['stato','errore','aggiornato_il'])
        raise
    except Exception:
        row.stato = row.Stato.INCERTO
        row.errore = 'Errore inatteso: verificare sul gestionale, non reinviare.'
        row.save(update_fields=['stato','errore','aggiornato_il'])
        raise EsitoIncertoError(row.errore) from None
    row.stato = row.Stato.COMPLETATO
    row.esito = asdict(result)
    # If this save fails, the row remains IN_CORSO and prevents duplicate sends.
    row.save(update_fields=['stato','esito','aggiornato_il'])
    return result
