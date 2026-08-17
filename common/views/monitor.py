from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from access_control.models import Ufficio
from access_control.services.office_service import (
    OfficeService,
)
from visitors.models import EventoAccesso, AccessoVisitatore

NUMERO_CHIAMATE_STORICO = 4


def _stato_monitor():
    """
    Costruisce lo stato del monitor pubblico.

    Non restituisce dati personali.
    """

    adesso = timezone.localtime()
    oggi = timezone.localdate()

    uffici_ricevimento_ids = list(
        OfficeService
        .get_offices_receiving_today(adesso)
        .values_list("pk", flat=True)
    )

    uffici_con_accessi_ids = list(
        AccessoVisitatore.objects
        .filter(
            ingresso__date=oggi,
            uscita__isnull=True,
            visita_conclusa_il__isnull=True,
        )
        .values_list(
            "ufficio_destinazione_id",
            flat=True,
        )
        .distinct()
    )

    uffici_ids = set(
        uffici_ricevimento_ids
        + uffici_con_accessi_ids
    )

    uffici = list(
        Ufficio.objects
        .filter(
            pk__in=uffici_ids,
            attivo=True,
        )
        .order_by("nome")
    )

    risultato = []

    for ufficio in uffici:

        eventi = list(
            EventoAccesso.objects
            .filter(
                ufficio=ufficio,
                tipo=EventoAccesso.Tipo.CHIAMATA,
                timestamp__date=oggi,
            )
            .select_related(
                "accesso",
            )
            .order_by(
                "-timestamp",
                "-pk",
            )[:NUMERO_CHIAMATE_STORICO]
        )

        ultima_chiamata = (
            eventi[0]
            if eventi
            else None
        )

        precedenti = []

        for evento in eventi[1:]:
            precedenti.append(
                {
                    "id": evento.pk,
                    "numero": (
                        evento.accesso
                        .numero_coda_formattato
                    ),
                    "ora": timezone.localtime(
                        evento.timestamp
                    ).strftime("%H:%M"),
                }
            )

        # =====================================================
        # VISITATORI AUTORIZZATI A RECARSI AL PIANO
        # =====================================================

        coda_fuori = list(
            AccessoVisitatore.objects
            .filter(
                ufficio_destinazione=ufficio,
                ingresso__date=oggi,
                uscita__isnull=True,
                spostato_fuori_ufficio_il__isnull=False,
                ingresso_ufficio_il__isnull=True,
                visita_conclusa_il__isnull=True,
            )
            .order_by(
                "spostato_fuori_ufficio_il",
                "ingresso",
                "numero_coda",
            )
        )

        numeri_al_piano = [
            {
                "id": accesso.pk,
                "numero": accesso.numero_coda_formattato,
            }
            for accesso in coda_fuori
        ]

        # =====================================================
        # PROSSIMI TRE NUMERI
        # =====================================================

        prioritari = list(
            AccessoVisitatore.objects
            .filter(
                ufficio_destinazione=ufficio,
                ingresso__date=oggi,
                uscita__isnull=True,
                appuntamento__isnull=False,
                spostato_fuori_ufficio_il__isnull=True,
                ingresso_ufficio_il__isnull=True,
                visita_conclusa_il__isnull=True,
            )
            .select_related("appuntamento")
            .order_by(
                "appuntamento__data_ora",
                "ingresso",
                "numero_coda",
            )[:3]
        )

        posti_residui = 3 - len(prioritari)

        ordinari = []

        if posti_residui > 0:
            ordinari = list(
                AccessoVisitatore.objects
                .filter(
                    ufficio_destinazione=ufficio,
                    ingresso__date=oggi,
                    uscita__isnull=True,
                    appuntamento__isnull=True,
                    spostato_fuori_ufficio_il__isnull=True,
                    ingresso_ufficio_il__isnull=True,
                    visita_conclusa_il__isnull=True,
                )
                .order_by(
                    "ingresso",
                    "numero_coda",
                )[:posti_residui]
            )

        prossimi_accessi = prioritari + ordinari

        prossimi_numeri = [
            {
                "id": accesso.pk,
                "numero": accesso.numero_coda_formattato,
                "prioritario": accesso.appuntamento_id is not None,
            }
            for accesso in prossimi_accessi
        ]

        risultato.append(
            {
                "id": ufficio.pk,
                "nome": ufficio.nome,

                "numeri_al_piano": numeri_al_piano,
                "prossimi_numeri": prossimi_numeri,

                "piano": (
                    ufficio.piano or ""
                ),

                "stanza": (
                    ufficio.stanza or ""
                ),

                "ultima_chiamata": (
                    {
                        "id": ultima_chiamata.pk,
                        "numero": (
                            ultima_chiamata
                            .accesso
                            .numero_coda_formattato
                        ),
                        "ora": (
                            timezone.localtime(
                                ultima_chiamata.timestamp
                            )
                            .strftime("%H:%M")
                        ),
                    }
                    if ultima_chiamata
                    else None
                ),

                "precedenti": precedenti,
            }
        )

    return {
        "aggiornato_il": (
            adesso.strftime("%H:%M:%S")
        ),
        "uffici": risultato,
    }


def monitor_home(request):
    """
    Pagina pubblica del monitor.
    """

    stato = _stato_monitor()

    return render(
        request,
        "common/monitor_home.html",
        {
            "uffici_monitor": (
                stato["uffici"]
            ),
            "aggiornato_il": (
                stato["aggiornato_il"]
            ),
        },
    )


@require_GET
def monitor_stato_live(request):
    """
    Endpoint pubblico per l'aggiornamento live.

    Non restituisce dati personali.
    """

    stato = _stato_monitor()

    return JsonResponse(
        {
            "success": True,
            **stato,
        }
    )