import hashlib
import json
from dataclasses import asdict

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import connection, transaction
from django.utils.module_loading import import_string

from .contracts import (ProtocolloBackend, EsitoProtocollo, ErroreProtocollo,
                       ConfigurazioneProtocolloError, ValidazioneProtocolloError,
                       EsitoIncertoError, InvioBloccatoError)
from .models import RegistrazioneProtocollo


def _audit_esito(row):
    """Repairable audit: a retry after an audit failure never repeats the SOAP call."""
    from audit.models import AuditEvent
    with transaction.atomic():
        locked = RegistrazioneProtocollo.objects.select_for_update().get(pk=row.pk)
        AuditEvent.objects.get_or_create(
            tipo=AuditEvent.TipoEvento.SYSTEM,
            oggetto=f'protocollazione:{locked.pk}',
            defaults={'user_id': locked.operatore_id, 'descrizione': json.dumps({
                'azione': 'PROTOCOLLAZIONE_COMPLETATA', 'chiave': locked.chiave,
                'backend': locked.backend, 'esito': locked.esito,
            }, ensure_ascii=False)},
        )


def protocolla_documenti(*, ufficio, firmatario, destinatario, pdf,
                        oggetto, classificazione, chiave, operatore,
                        tipo=None, riservato=True):
    """Protocollo unico: primo PDF principale, successivi allegati.

    pdf: Documento oppure sequenza non vuota di Documento (nome, bytes).
    firmatario: Firmatario; destinatario: Soggetto oppure sequenza di Soggetto.
    Restituisce EsitoProtocollo, inclusi numero, anno e segnatura; salva l'audit.
    Chiamare fuori da transaction.atomic/ATOMIC_REQUESTS e riusare la chiave.
    """
    from .contracts import Documento, Firmatario, Soggetto, RichiestaProtocollo, TipoProtocollo
    documents = (pdf,) if isinstance(pdf, Documento) else tuple(pdf or ())
    recipients = (destinatario,) if isinstance(destinatario, Soggetto) else tuple(destinatario or ())
    if not isinstance(ufficio, str) or not ufficio.strip() or not isinstance(firmatario, Firmatario):
        raise ValidazioneProtocolloError('Ufficio e firmatario obbligatori.')
    if not recipients or any(not isinstance(p, Soggetto) for p in recipients):
        raise ValidazioneProtocolloError('Indicare almeno un destinatario valido.')
    if not documents or any(not isinstance(d, Documento) or not isinstance(d.contenuto, bytes)
                            or not d.nome.lower().endswith('.pdf') or not d.contenuto.startswith(b'%PDF-')
                            for d in documents):
        raise ValidazioneProtocolloError('Fornire uno o più PDF con nome e contenuto in bytes.')
    selected_type = tipo or TipoProtocollo.PARTENZA
    if selected_type not in (TipoProtocollo.PARTENZA, TipoProtocollo.INTERNO):
        raise ValidazioneProtocolloError('Questo metodo gestisce protocolli in partenza o interni.')
    request = RichiestaProtocollo(
        oggetto=oggetto, tipo=selected_type, documento=documents[0], allegati=documents[1:],
        classificazione=classificazione, ufficio=ufficio, firmatari=(firmatario,),
        destinatari=recipients, riservato=riservato)
    return protocolla(request, chiave=chiave, operatore=operatore)


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
    if richiesta.allegati:
        for item, doc in zip(data['allegati'], richiesta.allegati):
            if not isinstance(doc.contenuto, bytes):
                raise ValidazioneProtocolloError('Gli allegati devono contenere bytes.')
            item['contenuto'] = hashlib.sha256(doc.contenuto).hexdigest()
    else:
        # Preserve historical digests for single-document requests.
        data.pop('allegati', None)
    digest = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    def existing_result(row):
        if row.impronta_richiesta != digest:
            raise InvioBloccatoError('Chiave già utilizzata con dati diversi.')
        if row.stato == row.Stato.COMPLETATO:
            _audit_esito(row)
            return EsitoProtocollo(**row.esito)
        raise InvioBloccatoError('Richiesta già presente. Verificare l’esito prima di qualsiasi nuovo invio.')
    existing = RegistrazioneProtocollo.objects.filter(chiave=chiave).first()
    autorizzata = False
    if existing:
        if existing.reinvio_autorizzato and existing.stato in (
            existing.Stato.IN_CORSO, existing.Stato.INCERTO, existing.Stato.ERRORE
        ):
            autorizzata = True
        else:
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
    if not created and not autorizzata:
        return existing_result(row)
    if autorizzata:
        row.reinvio_autorizzato = False
        row.reinvio_autorizzato_il = None
        row.stato = row.Stato.IN_CORSO
        row.errore = ''
        row.save(update_fields=['reinvio_autorizzato', 'reinvio_autorizzato_il', 'stato', 'errore', 'aggiornato_il'])
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
    _audit_esito(row)
    return result
