from django.shortcuts import render
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django.views.decorators.http import require_GET

from visitors.models import AccessoVisitatore


@require_GET
def ticket_status(request, token):
    """Stato pubblico del ticket: non espone dati anagrafici."""
    try:
        accesso = (
            AccessoVisitatore.objects
            .select_related("ufficio_destinazione")
            .get(token_pubblico=token)
        )
    except AccessoVisitatore.DoesNotExist:
        return _ticket_non_disponibile(request)

    token_scaduto = (
        accesso.token_pubblico_creato_il
        and accesso.token_pubblico_creato_il
        < timezone.now() - timedelta(hours=settings.PUBLIC_TICKET_TOKEN_HOURS)
    )
    if accesso.uscita is not None or token_scaduto:
        return _ticket_non_disponibile(request)

    stato, istruzione = _stato_pubblico(accesso)
    if stato is None:
        return _ticket_non_disponibile(request)
    persone_davanti = _persone_davanti(accesso)
    capacita = max(1, accesso.ufficio_destinazione.numero_dipendenti)
    attesa_stimata = (
        persone_davanti
        * accesso.ufficio_destinazione.tempo_medio_servizio_default
    ) // capacita

    return render(
        request,
        "visitors/ticket_status.html",
        {
            "accesso": accesso,
            "stato": stato,
            "istruzione": istruzione,
            "persone_davanti": persone_davanti,
            "attesa_stimata": attesa_stimata,
        },
    )


def _ticket_non_disponibile(request):
    """Risposta pubblica generica: non conferma l'esistenza del token."""
    return render(
        request,
        "visitors/ticket_non_disponibile.html",
        status=404,
    )


def _stato_pubblico(accesso):
    stati = AccessoVisitatore.StatoCoda
    if accesso.stato_coda == stati.HALL:
        return "In attesa nella hall", "Attenda nella hall."
    if accesso.stato_coda == stati.FUORI_UFFICIO:
        return "Può recarsi all'ufficio", "Si rechi davanti all'ufficio indicato."
    if accesso.stato_coda == stati.IN_UFFICIO:
        return "Ricevimento in corso", "Il ricevimento è in corso."
    if accesso.stato_coda == stati.VISITA_CONCLUSA:
        return "Ricevimento concluso", "Può recarsi in portineria per l'uscita."
    return None, None


def _persone_davanti(accesso):
    if accesso.stato_coda != AccessoVisitatore.StatoCoda.HALL:
        return 0

    from visitors.services.office_queue_service import OfficeQueueService
    from django.db.models import Case, When, Value, IntegerField
    queue = AccessoVisitatore.objects.filter(
        ufficio_destinazione=accesso.ufficio_destinazione,
        stato_coda=AccessoVisitatore.StatoCoda.HALL,
        uscita__isnull=True,
        ingresso_ufficio_il__isnull=True,
        visita_conclusa_il__isnull=True,
    ).annotate(category=Case(When(rientro_prioritario=True, then=Value(0)),
        When(appuntamento__isnull=False, then=Value(1)), default=Value(2), output_field=IntegerField()))
    ids = list(queue.order_by('category', OfficeQueueService._ordine_hall(True), 'numero_coda', 'pk').values_list('pk', flat=True))
    return ids.index(accesso.pk) if accesso.pk in ids else 0
