from hmac import compare_digest

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db.models import Q, F, OuterRef, Subquery, Exists
from django.db.models.functions import Coalesce, Greatest
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from common.module_access import MonitorPortineriaAccessMixin, module_required

from access_control.models import Ufficio
from access_control.services.office_service import (
    OfficeService,
)
from visitors.models import EventoAccesso, AccessoVisitatore

NUMERO_CHIAMATE_STORICO = 4


def _token_monitor_valido(token):
    configurato = settings.PUBLIC_MONITOR_TOKEN
    return bool(
        configurato
        and token
        and compare_digest(configurato, token)
    )


def _contesto_monitor(stato, live_url, monitor_launcher_url=""):
    return {
        "uffici_monitor": stato["uffici"],
        "aggiornato_il": stato["aggiornato_il"],
        "monitor_live_url": live_url,
        "monitor_launcher_url": monitor_launcher_url,
    }


def _ordina_uffici_per_coda(uffici, oggi):
    """Ordine persistente tra refresh: ultimo evento di coda, non note."""
    eventi = EventoAccesso.objects.filter(
        ufficio_id=OuterRef("pk"), timestamp__date=oggi,
    ).exclude(tipo=EventoAccesso.Tipo.NOTA).order_by("-timestamp", "-pk")
    accessi = AccessoVisitatore.objects.filter(
        ufficio_destinazione_id=OuterRef("pk"), ingresso__date=oggi,
    ).annotate(ultimo_movimento=Greatest(
        F("ingresso"),
        Coalesce("spostato_fuori_ufficio_il", "ingresso"),
        Coalesce("ingresso_ufficio_il", "ingresso"),
        Coalesce("visita_conclusa_il", "ingresso"),
        Coalesce("uscita", "ingresso"),
    )).order_by("-ultimo_movimento", "-pk")
    return uffici.annotate(
        ha_coda=Exists(accessi.filter(
            uscita__isnull=True, visita_conclusa_il__isnull=True,
            ingresso_ufficio_il__isnull=True,
        )),
        ultimo_evento_coda_il=Subquery(eventi.values("timestamp")[:1]),
        ultimo_evento_coda_id=Subquery(eventi.values("pk")[:1]),
        ultimo_movimento_coda_il=Subquery(accessi.values("ultimo_movimento")[:1]),
    ).annotate(
        aggiornamento_coda_il=Greatest(
            Coalesce("ultimo_evento_coda_il", "ultimo_movimento_coda_il"),
            Coalesce("ultimo_movimento_coda_il", "ultimo_evento_coda_il"),
        ),
    ).order_by(
        "-ha_coda",
        F("aggiornamento_coda_il").desc(nulls_last=True),
        F("ultimo_evento_coda_id").desc(nulls_last=True), "nome", "pk",
    )


def _stato_monitor():
    """
    Costruisce lo stato del Monitor portineria.

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
        _ordina_uffici_per_coda(Ufficio.objects
        .filter(
            pk__in=uffici_ids,
            attivo=True,
        )
        , oggi)
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

        rientri = list(
            AccessoVisitatore.objects
            .filter(
                ufficio_destinazione=ufficio,
                ingresso__date=oggi,
                uscita__isnull=True,
                rientro_prioritario=True,
                spostato_fuori_ufficio_il__isnull=True,
                ingresso_ufficio_il__isnull=True,
                visita_conclusa_il__isnull=True,
            )
            .order_by("ingresso", "numero_coda")[:3]
        )

        posti_residui = 3 - len(rientri)
        appuntamenti = []
        if posti_residui > 0:
            appuntamenti = list(
                AccessoVisitatore.objects
                .filter(
                    ufficio_destinazione=ufficio,
                    ingresso__date=oggi,
                    uscita__isnull=True,
                    rientro_prioritario=False,
                    appuntamento__isnull=False,
                    spostato_fuori_ufficio_il__isnull=True,
                    ingresso_ufficio_il__isnull=True,
                    visita_conclusa_il__isnull=True,
                )
                .select_related("appuntamento")
                .order_by(
                    "appuntamento__data_ora", "ingresso", "numero_coda"
                )[:posti_residui]
            )

        posti_residui -= len(appuntamenti)
        ordinari = []
        if posti_residui > 0:
            ordinari = list(
                AccessoVisitatore.objects
                .filter(
                    ufficio_destinazione=ufficio,
                    ingresso__date=oggi,
                    uscita__isnull=True,
                    rientro_prioritario=False,
                    appuntamento__isnull=True,
                    spostato_fuori_ufficio_il__isnull=True,
                    ingresso_ufficio_il__isnull=True,
                    visita_conclusa_il__isnull=True,
                )
                .order_by("ingresso", "numero_coda")[:posti_residui]
            )

        prossimi_accessi = rientri + appuntamenti + ordinari

        prossimi_numeri = [
            {
                "id": accesso.pk,
                "numero": accesso.numero_coda_formattato,
                "prioritario": accesso.prioritario,
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


@module_required(MonitorPortineriaAccessMixin)
def monitor_home(request):
    """
    Pagina del Monitor portineria.
    """

    stato = _stato_monitor()

    return render(
        request,
        "common/monitor_home.html",
        _contesto_monitor(
            stato,
            reverse("monitor_stato_live"),
            reverse("monitor_scarica_avvio")
            if request.user.is_superuser and settings.PUBLIC_MONITOR_TOKEN
            else "",
        ),
    )


@module_required(MonitorPortineriaAccessMixin)
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


@module_required(MonitorPortineriaAccessMixin)
@require_GET
def monitor_scarica_avvio(request):
    """Scarica il launcher Windows con il token pubblico già configurato."""
    if not request.user.is_superuser:
        raise PermissionDenied

    token = settings.PUBLIC_MONITOR_TOKEN
    if not token:
        raise Http404

    contenuto = """@echo off
setlocal

REM Monitor portineria - Comune di Aversa
REM Coordinate del monitor secondario: a sinistra del principale per impostazione predefinita.
set \"SECONDARY_X=-1920\"
set \"SECONDARY_Y=0\"
set \"MONITOR_URL=https://controlloaccessi.comune.aversa.ce.it/monitor/pubblico/%s/\"
set \"PROFILE_DIR=%%LOCALAPPDATA%%\\ControlloAccessiMonitor\"

if exist \"C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe\" (
    start \"\" \"C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe\" --kiosk --new-window --user-data-dir=\"%%PROFILE_DIR%%\" --window-position=%%SECONDARY_X%%,%%SECONDARY_Y%% \"%%MONITOR_URL%%\"
    exit /b 0
)

if exist \"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe\" (
    start \"\" \"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe\" --kiosk --new-window --user-data-dir=\"%%PROFILE_DIR%%\" --window-position=%%SECONDARY_X%%,%%SECONDARY_Y%% \"%%MONITOR_URL%%\"
    exit /b 0
)

echo Non sono stati trovati Microsoft Edge o Google Chrome.
pause
exit /b 1
""" % token
    response = HttpResponse(contenuto, content_type="application/octet-stream")
    response["Content-Disposition"] = 'attachment; filename="apri-monitor-portineria.bat"'
    response["Cache-Control"] = "no-store, private"
    return response


@require_GET
def monitor_pubblico(request, token):
    """Monitor senza login, protetto da un token casuale nell'URL."""
    if not _token_monitor_valido(token):
        raise Http404

    stato = _stato_monitor()
    response = render(
        request,
        "common/monitor_home.html",
        _contesto_monitor(
            stato,
            reverse("monitor_pubblico_stato_live", args=[token]),
        ),
    )
    response["Cache-Control"] = "no-store, private"
    return response


@require_GET
def monitor_pubblico_stato_live(request, token):
    """Stato live del monitor senza sessione Django."""
    if not _token_monitor_valido(token):
        raise Http404

    response = JsonResponse({"success": True, **_stato_monitor()})
    response["Cache-Control"] = "no-store, private"
    return response
