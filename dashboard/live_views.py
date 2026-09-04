from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from access_control.services.office_service import OfficeService
from visitors.models import AccessoVisitatore
from visitors.permissions import portineria_required
from visitors.services.capacity_service import CapacityService


@portineria_required
@require_GET
def stato_dashboard_portineria(request):
    oggi = timezone.localdate()
    adesso = timezone.localtime()

    numero_visitatori_presenti = (
        AccessoVisitatore.objects
        .filter(
            uscita__isnull=True,
            ingresso__date=oggi,
        )
        .count()
    )

    uffici_oggi = list(
        OfficeService.get_offices_receiving_with_present_staff()
    )

    dati_uffici = []

    for ufficio in uffici_oggi:
        visitatori_da_servire = (
            AccessoVisitatore.objects
            .filter(
                ufficio_destinazione=ufficio,
                ingresso__date=oggi,
                uscita__isnull=True,
                visita_conclusa_il__isnull=True,
            )
            .count()
        )

        registrati_oggi = (
            AccessoVisitatore.objects
            .filter(
                ufficio_destinazione=ufficio,
                ingresso__date=oggi,
            )
            .count()
        )

        dipendenti_presenti = (
            CapacityService.numero_dipendenti_presenti(
                ufficio
            )
        )

        dati_uffici.append(
            {
                "id": ufficio.pk,
                "visitatori_da_servire": (
                    visitatori_da_servire
                ),
                "registrati_oggi": registrati_oggi,
                "dipendenti_presenti": (
                    dipendenti_presenti
                ),
            }
        )

    return JsonResponse(
        {
            "success": True,
            "aggiornato_il": adesso.isoformat(),
            "numero_visitatori_presenti": (
                numero_visitatori_presenti
            ),
            "numero_uffici_che_ricevono": len(
                uffici_oggi
            ),
            "uffici": dati_uffici,
        }
    )
