from django.http import Http404
from django.shortcuts import get_object_or_404, render
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django.views.decorators.http import require_GET

from visitors.models import AccessoVisitatore


@require_GET
def ticket_status(request, token):
    """Stato pubblico del ticket: non espone dati anagrafici."""
    accesso = get_object_or_404(
        AccessoVisitatore.objects.select_related("ufficio_destinazione"),
        token_pubblico=token,
    )

    token_scaduto = (
        accesso.token_pubblico_creato_il
        and accesso.token_pubblico_creato_il
        < timezone.now() - timedelta(hours=settings.PUBLIC_TICKET_TOKEN_HOURS)
    )
    if accesso.uscita is not None or token_scaduto:
        raise Http404("Ticket non più disponibile.")

    stato, istruzione = _stato_pubblico(accesso)
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
    raise Http404("Ticket non disponibile.")


def _persone_davanti(accesso):
    if accesso.stato_coda != AccessoVisitatore.StatoCoda.HALL:
        return 0

    return AccessoVisitatore.objects.filter(
        ufficio_destinazione=accesso.ufficio_destinazione,
        stato_coda=AccessoVisitatore.StatoCoda.HALL,
        uscita__isnull=True,
        ingresso__lt=accesso.ingresso,
    ).count()
