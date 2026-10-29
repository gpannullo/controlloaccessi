from django.conf import settings
from django.contrib.auth import get_user_model
from common.module_access import PortineriaAccessMixin, module_required
from django.db.models import Count, Prefetch, Q
from django.shortcuts import render
from django.utils import timezone

from access_control.models import CalendarioApertura, Ufficio
from access_control.services.office_service import OfficeService
from visitors.models import (
    AccessoVisitatore,
    SessioneRicevimento,
)


User = get_user_model()


GIORNI_SETTIMANA = [
    {"numero": 0, "nome": "Lunedì", "slug": "lunedi"},
    {"numero": 1, "nome": "Martedì", "slug": "martedi"},
    {"numero": 2, "nome": "Mercoledì", "slug": "mercoledi"},
    {"numero": 3, "nome": "Giovedì", "slug": "giovedi"},
    {"numero": 4, "nome": "Venerdì", "slug": "venerdi"},
    {"numero": 5, "nome": "Sabato", "slug": "sabato"},
    {"numero": 6, "nome": "Domenica", "slug": "domenica"},
]


def _dipendenti_assegnati_ufficio(ufficio):
    """
    Restituisce gli utenti attivi assegnati esplicitamente all'ufficio.
    """

    return list(
        User.objects
        .filter(
            assegnazioni_ufficio__ufficio=ufficio,
            assegnazioni_ufficio__attiva=True,
            is_active=True,
        )
        .distinct()
        .order_by(
            "last_name",
            "first_name",
            "username",
        )
    )


def _operatori_disponibili_ufficio(ufficio):
    """Stessa regola del calcolo della capacita', senza filtri di visibilita'."""
    from visitors.services.capacity_service import CapacityService
    return list(CapacityService.operatori_per_capacita(ufficio).order_by(
        "last_name", "first_name", "username",
    ))


@module_required(PortineriaAccessMixin)
def dashboard_home(request):
    adesso = timezone.localtime()
    oggi = timezone.localdate()
    giorno_corrente = adesso.weekday()

    visitatori_presenti = list(
        AccessoVisitatore.objects
        .filter(
            uscita__isnull=True,
            ingresso__date=oggi,
        )
        .select_related(
            "visitatore",
            "ufficio_destinazione",
            "badge",
            "operatore_assegnato",
        )
        .order_by(
            "ufficio_destinazione__nome",
            "ingresso",
        )
    )

    accessi_giorni_precedenti = list(
        AccessoVisitatore.objects
        .filter(
            uscita__isnull=True,
            ingresso__date__lt=oggi,
        )
        .select_related(
            "visitatore",
            "ufficio_destinazione",
            "badge",
        )
        .order_by("ingresso")
    )

    visitatori_per_ufficio = {}

    for accesso in visitatori_presenti:
        ufficio = accesso.ufficio_destinazione

        if ufficio.pk not in visitatori_per_ufficio:
            visitatori_per_ufficio[ufficio.pk] = {
                "ufficio": ufficio,
                "accessi": [],
            }

        visitatori_per_ufficio[ufficio.pk]["accessi"].append(
            accesso
        )

    visitatori_per_ufficio = list(
        visitatori_per_ufficio.values()
    )

    ultime_registrazioni = (
        AccessoVisitatore.objects
        .filter(ingresso__date=oggi)
        .select_related(
            "ufficio_destinazione",
            "badge",
        )
        .order_by("-ingresso")[:10]
    )

    # Uffici con una fascia di ricevimento pianificata per oggi:
    # rappresentano l'offerta di appuntamenti del giorno.
    uffici_in_calendario_oggi = (
        OfficeService
        .get_active_offices_for_day(giorno_corrente)
    )

    # Uffici realmente selezionabili nel form "Nuovo ricevimento".
    # Se non c'è personale presente, il visitatore resta in hall.
    uffici_prenotabili = (
        OfficeService
        .get_offices_receiving_today()
    )

    uffici_visita_ids = set(OfficeService.get_offices_with_present_staff().values_list("pk", flat=True))
    uffici_ricevimento_ids = set(uffici_prenotabili.values_list("pk", flat=True))

    aperture_odierne = (
        CalendarioApertura.objects
        .filter(giorno=giorno_corrente)
        .order_by("ora_inizio")
    )

    uffici_che_ricevono_oggi = (
        Ufficio.objects.filter(pk__in=uffici_visita_ids | uffici_ricevimento_ids).order_by("nome")
        .annotate(
            visitatori_in_coda=Count(
                "visite",
                filter=Q(
                    visite__uscita__isnull=True,
                    visite__ingresso__date=oggi,
                    visite__visita_conclusa_il__isnull=True,
                ),
                distinct=True,
            ),
            accessi_registrati_oggi=Count(
                "visite",
                filter=Q(
                    visite__ingresso__date=oggi,
                ),
                distinct=True,
            ),
        )
        .prefetch_related(
            Prefetch(
                "aperture",
                queryset=aperture_odierne,
                to_attr="aperture_di_oggi",
            ),
            "assegnazioni_personale__utente",
        )
    )

    uffici_oggi = []

    for ufficio in uffici_che_ricevono_oggi:
        ufficio.dipendenti_assegnati = (
            _dipendenti_assegnati_ufficio(ufficio)
        )

        ufficio.dipendenti_presenti = [
            dipendente
            for dipendente in ufficio.dipendenti_assegnati
            if dipendente.stato_presenza == User.StatoPresenza.PRESENTE
        ]

        ufficio.numero_dipendenti_assegnati = len(
            ufficio.dipendenti_assegnati
        )

        ufficio.numero_dipendenti_presenti = len(
            ufficio.dipendenti_presenti
        )

        uffici_oggi.append(ufficio)

    calendario_settimanale = []
    uffici_con_personale_presente = set(
        OfficeService
        .get_offices_with_present_staff()
        .values_list("pk", flat=True)
    )

    for giorno in GIORNI_SETTIMANA:
        aperture_giorno = (
            CalendarioApertura.objects
            .filter(giorno=giorno["numero"])
            .order_by("ora_inizio")
        )

        uffici_giorno = (
            OfficeService
            .get_active_offices_for_day(
                giorno["numero"],
            )
            .prefetch_related(
                Prefetch(
                    "aperture",
                    queryset=aperture_giorno,
                    to_attr="aperture_del_giorno",
                )
            )
        )

        uffici_giorno = list(uffici_giorno)
        for ufficio in uffici_giorno:
            # La disponibilità è riferita alla situazione effettiva adesso,
            # non al solo calendario della giornata selezionata nel modal.
            ufficio.personale_disponibile = (
                ufficio.pk in uffici_con_personale_presente
            )

        calendario_settimanale.append(
            {
                **giorno,
                "uffici": uffici_giorno,
            }
        )

    context = {
        "numero_visitatori_presenti": len(
            visitatori_presenti
        ),
        "visitatori_per_ufficio": visitatori_per_ufficio,

        "accessi_giorni_precedenti": (
            accessi_giorni_precedenti
        ),
        "numero_accessi_giorni_precedenti": len(
            accessi_giorni_precedenti
        ),

        "ultime_registrazioni": ultime_registrazioni,

        "numero_uffici_prenotazioni": uffici_in_calendario_oggi.count(),
        "numero_uffici_che_ricevono": len(uffici_visita_ids),
        "uffici_visita": [u for u in uffici_oggi if u.pk in uffici_visita_ids],

        "numero_utenti_attivi": (
            User.objects
            .filter(is_active=True)
            .count()
        ),

        "uffici_oggi": uffici_oggi,
        "calendario_settimanale": calendario_settimanale,
        "giorno_corrente": giorno_corrente,
        "oggi": oggi,
        "adesso": adesso,
    }

    return render(
        request,
        "dashboard/home.html",
        context,
    )
