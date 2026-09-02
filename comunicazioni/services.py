from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from accounts.models import CustomUser
from audit.services.audit_service import AuditService
from post_office import mail

from .models import ComunicazioneEmail, DestinatarioComunicazioneEmail


class ComunicazioneEmailError(RuntimeError):
    pass


def _utenti_destinatari(comunicazione):
    utenti = CustomUser.objects.filter(is_active=True)
    if comunicazione.tutti_gli_utenti_attivi:
        return utenti
    filtri = Q(pk__in=comunicazione.destinatari.values("pk"))
    filtri |= Q(groups__in=comunicazione.gruppi.all())
    filtri |= Q(assegnazioni_ufficio__ufficio__in=comunicazione.uffici.all(), assegnazioni_ufficio__attiva=True)
    return utenti.filter(filtri).distinct()


def _indirizzo(utente, destinazione):
    campi = {
        ComunicazioneEmail.Destinazione.ISTITUZIONALE: "email",
        ComunicazioneEmail.Destinazione.PERSONALE: "email_personale",
        ComunicazioneEmail.Destinazione.AGGIUNTIVA: "email_aggiuntiva",
    }
    return (getattr(utente, campi[destinazione], "") or "").strip()


def accoda_comunicazione(comunicazione, autore=None):
    if comunicazione.stato != ComunicazioneEmail.Stato.BOZZA:
        raise ComunicazioneEmailError("La comunicazione è già stata accodata e non può essere inviata una seconda volta.")

    destinatari = []
    for utente in _utenti_destinatari(comunicazione):
        indirizzo = _indirizzo(utente, comunicazione.destinazione)
        if indirizzo:
            destinatari.append((utente, indirizzo))
    if not destinatari:
        raise ComunicazioneEmailError("Non è stato trovato alcun destinatario attivo con l'indirizzo e-mail selezionato.")

    for utente, indirizzo in destinatari:
        mail.send(
            recipients=[indirizzo],
            sender=settings.DEFAULT_FROM_EMAIL,
            subject=comunicazione.oggetto,
            message=comunicazione.messaggio,
        )
        DestinatarioComunicazioneEmail.objects.get_or_create(
            comunicazione=comunicazione,
            indirizzo_email=indirizzo,
            defaults={"utente": utente},
        )
    comunicazione.stato = ComunicazioneEmail.Stato.ACCODATA
    comunicazione.accodata_il = timezone.now()
    comunicazione.save(update_fields=["stato", "accodata_il"])
    AuditService.log(
        user=autore,
        tipo="CREATE",
        oggetto=f"ComunicazioneEmail:{comunicazione.pk}",
        descrizione=f"Comunicazione accodata per {len(destinatari)} destinatari.",
    )
    return len(destinatari)
