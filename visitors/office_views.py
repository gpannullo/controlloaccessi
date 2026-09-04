from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.views.decorators.http import require_POST, require_GET

from access_control.models import IndisponibilitaUfficio, Ufficio
from access_control.services.office_service import OfficeService
from common.exceptions import BusinessException
from visitors.forms import IndisponibilitaUfficioForm
from visitors.models import AccessoVisitatore
from visitors.permissions import ufficio_required
from visitors.services.capacity_service import CapacityService
from visitors.services.continuity_service import ContinuitaAccessoService
from visitors.services.office_queue_service import (
    OfficeQueueService,
)

User = get_user_model()


def _operatori_disponibili_ufficio(ufficio):
    """Almeno un dipendente dell'ufficio deve risultare presente."""
    return User.objects.filter(
        is_active=True,
        stato_presenza=User.StatoPresenza.PRESENTE,
        assegnazioni_ufficio__ufficio=ufficio,
        assegnazioni_ufficio__attiva=True,
    ).exists()


def _get_client_ip(request):
    forwarded_for = request.META.get(
        "HTTP_X_FORWARDED_FOR"
    )

    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    return request.META.get("REMOTE_ADDR")


def _uffici_utente(user):
    """
    Restituisce gli uffici ai quali l'utente appartiene
    tramite i gruppi organizzativi.

    Gli utenti della portineria vengono bloccati prima
    dal decorator ufficio_required.
    """

    if user.is_superuser:
        return (
            Ufficio.objects
            .filter(attivo=True)
            .order_by("nome")
        )

    return (
        Ufficio.objects
        .filter(
            attivo=True,
        ).filter(
            Q(
                assegnazioni_personale__utente=user,
                assegnazioni_personale__attiva=True,
            )
            | Q(responsabile=user)
        )
        .distinct()
        .order_by("nome")
    )


def _get_ufficio_autorizzato(user, ufficio_id):
    """
    Restituisce l'ufficio soltanto se appartiene
    all'utente autenticato.
    """

    return get_object_or_404(
        _uffici_utente(user),
        pk=ufficio_id,
    )


@login_required
def gestisci_indisponibilita(request, ufficio_id):
    """Permette al responsabile di sospendere temporaneamente il ricevimento."""
    ufficio = get_object_or_404(Ufficio, pk=ufficio_id)
    if not request.user.is_superuser and ufficio.responsabile_id != request.user.pk:
        raise PermissionDenied("Solo il responsabile dell'ufficio può gestire le indisponibilità.")

    indisponibilita = ufficio.indisponibilita.select_related("comunicata_da").all()
    if request.method == "POST" and request.POST.get("azione") == "revoca":
        periodo = get_object_or_404(indisponibilita, pk=request.POST.get("periodo_id"))
        periodo.attiva = False
        periodo.save(update_fields=["attiva"])
        messages.success(request, "Indisponibilità revocata.")
        return redirect("uffici:indisponibilita", ufficio_id=ufficio.pk)

    form = IndisponibilitaUfficioForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        periodo = form.save(commit=False)
        periodo.ufficio = ufficio
        periodo.comunicata_da = request.user
        periodo.save()
        messages.success(
            request,
            "Indisponibilità comunicata: l'ufficio non riceverà pubblico nel periodo indicato.",
        )
        return redirect("uffici:indisponibilita", ufficio_id=ufficio.pk)

    return render(
        request,
        "visitors/gestione_indisponibilita.html",
        {"ufficio": ufficio, "form": form, "indisponibilita": indisponibilita},
    )


@ufficio_required
def selezione_ufficio(request):
    """
    Pagina iniziale dell'area uffici.

    Mostra sempre tutti gli uffici assegnati e lascia
    al dipendente la scelta dell'ufficio sul quale operare.
    """

    uffici = list(
        _uffici_utente(request.user)
    )

    return render(
        request,
        "visitors/selezione_ufficio.html",
        {
            "uffici": uffici,
        },
    )


@ufficio_required
def ufficio_dashboard(request, ufficio_id):
    """
    Dashboard operativa dell'ufficio selezionato.
    """

    ufficio = _get_ufficio_autorizzato(
        request.user,
        ufficio_id,
    )

    uffici = list(
        _uffici_utente(request.user)
    )

    visita_corrente = (
        OfficeQueueService.visita_corrente(
            ufficio=ufficio,
            operatore=request.user,
        )
    )

    coda_fuori = list(
        OfficeQueueService.coda_fuori_ufficio(
            ufficio
        )
    )

    ha_ricevimenti_fuori = any(
        accesso.rientro_prioritario
        or accesso.appuntamento_id is not None
        or (
            accesso.tipo_accesso
            == AccessoVisitatore.TipoAccesso.RICEVIMENTO
        )
        for accesso in coda_fuori
    )

    coda_prioritaria = list(
        OfficeQueueService.coda_prioritaria(
            ufficio
        )
    )

    coda_hall = list(
        OfficeQueueService.coda_hall(
            ufficio
        )
    )

    visite_in_corso = list(
        OfficeQueueService.visite_in_corso_ufficio(
            ufficio
        )
    )

    uffici_trasferimento = list(
        Ufficio.objects.filter(attivo=True)
        .exclude(pk=ufficio.pk)
        .order_by("nome")
    )
    uffici_trasferimento = [
        candidato for candidato in uffici_trasferimento
        if _operatori_disponibili_ufficio(candidato)
    ]

    return render(
        request,
        "visitors/ufficio_dashboard.html",
        {
            "uffici": uffici,
            "ufficio": ufficio,
            "visita_corrente": visita_corrente,
            "coda_fuori": coda_fuori,
            "coda_prioritaria": coda_prioritaria,
            "coda_hall": coda_hall,
            "visite_in_corso": visite_in_corso,
            "numero_fuori": len(coda_fuori),
            "ha_ricevimenti_fuori": ha_ricevimenti_fuori,
            "numero_prioritari": len(
                coda_prioritaria
            ),
            "numero_hall": len(coda_hall),
            "numero_in_ufficio": len(
                visite_in_corso
            ),
            "uffici_trasferimento": uffici_trasferimento,
            "puo_gestire_indisponibilita": (
                request.user.is_superuser
                or ufficio.responsabile_id == request.user.pk
            ),
        },
    )


@ufficio_required
@require_POST
def fai_entrare_prossimo(request, ufficio_id):
    ufficio = _get_ufficio_autorizzato(
        request.user,
        ufficio_id,
    )

    try:
        accesso = (
            OfficeQueueService
            .fai_entrare_prossimo(
                ufficio=ufficio,
                operatore=request.user,
                ip_address=_get_client_ip(request),
            )
        )

        messages.success(
            request,
            (
                f"Numero "
                f"{accesso.numero_coda_formattato} "
                f"preso in carico correttamente."
            ),
        )

    except BusinessException as exc:
        messages.warning(
            request,
            str(exc),
        )

    return redirect(
        "uffici:dashboard",
        ufficio_id=ufficio.pk,
    )


@ufficio_required
@require_POST
def autorizza_salita_visita(
    request,
    ufficio_id,
    accesso_id,
):
    ufficio = _get_ufficio_autorizzato(
        request.user,
        ufficio_id,
    )

    accesso = get_object_or_404(
        AccessoVisitatore,
        pk=accesso_id,
        ufficio_destinazione=ufficio,
    )

    try:
        OfficeQueueService.autorizza_salita_visita(
            accesso=accesso,
            ufficio=ufficio,
            operatore=request.user,
            ip_address=_get_client_ip(request),
        )

        messages.success(
            request,
            (
                f"Visita {accesso.numero_coda_formattato} "
                f"autorizzata a recarsi all'ufficio."
            ),
        )

    except BusinessException as exc:
        messages.warning(request, str(exc))

    return redirect(
        "uffici:dashboard",
        ufficio_id=ufficio.pk,
    )


@ufficio_required
@require_POST
def fai_entrare_visitatore(
    request,
    ufficio_id,
    accesso_id,
):
    ufficio = _get_ufficio_autorizzato(
        request.user,
        ufficio_id,
    )

    accesso = get_object_or_404(
        AccessoVisitatore,
        pk=accesso_id,
        ufficio_destinazione=ufficio,
    )

    try:
        OfficeQueueService.fai_entrare_visitatore(
            accesso=accesso,
            ufficio=ufficio,
            operatore=request.user,
            ip_address=_get_client_ip(request),
        )

        messages.success(
            request,
            (
                f"Visitatore {accesso.numero_coda_formattato} "
                f"fatto entrare nell'ufficio."
            ),
        )

    except BusinessException as exc:
        messages.warning(request, str(exc))

    return redirect(
        "uffici:dashboard",
        ufficio_id=ufficio.pk,
    )


@ufficio_required
@require_POST
def concludi_visita(
    request,
    ufficio_id,
    accesso_id,
):
    ufficio = _get_ufficio_autorizzato(
        request.user,
        ufficio_id,
    )

    accesso = get_object_or_404(
        AccessoVisitatore.objects.select_related(
            "ufficio_destinazione",
        ),
        pk=accesso_id,
        ufficio_destinazione=ufficio,
    )

    note = (
        request.POST.get(
            "note_conclusione"
        )
        or ""
    ).strip()

    try:
        OfficeQueueService.concludi_visita(
            accesso=accesso,
            operatore=request.user,
            note=note,
            ip_address=_get_client_ip(request),
        )

        messages.success(
            request,
            "Visita conclusa correttamente.",
        )

    except BusinessException as exc:
        messages.warning(
            request,
            str(exc),
        )

    return redirect(
        "uffici:dashboard",
        ufficio_id=ufficio.pk,
    )

@ufficio_required
@require_POST
def aggiorna_coda_fuori(request, ufficio_id):
    ufficio = _get_ufficio_autorizzato(
        request.user,
        ufficio_id,
    )

    if not OfficeService.is_open(ufficio):
        messages.warning(
            request,
            "L'ufficio è chiuso in questo momento: i visitatori restano nella hall.",
        )
        return redirect("uffici:dashboard", ufficio_id=ufficio.pk)

    numero_operatori = CapacityService.numero_dipendenti_presenti(ufficio)

    numero_gia_fuori = (
        OfficeQueueService
        .coda_fuori_ufficio(ufficio)
        .filter(
            tipo_accesso=(
                AccessoVisitatore.TipoAccesso.RICEVIMENTO
            )
        )
        .count()
    )

    posti_disponibili = max(
        numero_operatori - numero_gia_fuori,
        0,
    )

    if numero_operatori <= 0:
        messages.warning(
            request,
            (
                "Non risultano dipendenti assegnati e presenti "
                "per questo ufficio."
            ),
        )

    elif posti_disponibili <= 0:
        messages.info(
            request,
            (
                "La coda fuori dall'ufficio è già completa. "
                f"Capacità attuale: {numero_operatori}."
            ),
        )

    else:
        accessi_spostati = (
            OfficeQueueService.promuovi_dalla_hall(
                ufficio=ufficio,
                numero_posti=posti_disponibili,
                operatore=request.user,
                ip_address=_get_client_ip(request),
            )
        )

        if accessi_spostati:
            numeri = ", ".join(
                accesso.numero_coda_formattato
                for accesso in accessi_spostati
            )

            messages.success(
                request,
                (
                    f"Spostati fuori dall'ufficio "
                    f"{len(accessi_spostati)} visitatori: "
                    f"{numeri}."
                ),
            )
        else:
            messages.info(
                request,
                "Non ci sono visitatori da spostare dalla hall.",
            )

    return redirect(
        "uffici:dashboard",
        ufficio_id=ufficio.pk,
    )



@ufficio_required
@require_POST
def trasferisci_visitatore(request, ufficio_id, accesso_id):
    ufficio = _get_ufficio_autorizzato(request.user, ufficio_id)
    accesso = get_object_or_404(
        AccessoVisitatore, pk=accesso_id, ufficio_destinazione=ufficio
    )
    nuovo_ufficio = get_object_or_404(
        Ufficio,
        pk=request.POST.get("nuovo_ufficio"),
        attivo=True,
    )
    if not _operatori_disponibili_ufficio(nuovo_ufficio):
        messages.error(request, "L'ufficio selezionato non ha dipendenti presenti disponibili.")
        return redirect("uffici:dashboard", ufficio_id=ufficio.pk)
    note = (request.POST.get("note_trasferimento") or "").strip()
    motivo = (request.POST.get("motivo_trasferimento") or "").strip()
    if not motivo:
        messages.error(request, "Indicare il motivo del trasferimento.")
        return redirect("uffici:dashboard", ufficio_id=ufficio.pk)
    try:
        nuovo_accesso = ContinuitaAccessoService.trasferisci_ufficio(
            accesso=accesso,
            nuovo_ufficio=nuovo_ufficio,
            operatore=request.user,
            motivo=motivo,
            note=note,
            ip_address=_get_client_ip(request),
        )
        messages.success(
            request,
            f"Visitatore trasferito a {nuovo_ufficio.nome}. "
            f"Nuova coda {nuovo_accesso.numero_coda_formattato}.",
        )
    except BusinessException as exc:
        messages.warning(request, str(exc))
    return redirect("uffici:dashboard", ufficio_id=ufficio.pk)

@ufficio_required
@require_GET
def stato_ufficio_live(request, ufficio_id):
    ufficio = _get_ufficio_autorizzato(
        request.user,
        ufficio_id,
    )

    visita_corrente = (
        OfficeQueueService.visita_corrente(
            ufficio=ufficio,
            operatore=request.user,
        )
    )

    numero_prioritari = (
        OfficeQueueService
        .coda_prioritaria(ufficio)
        .count()
    )

    numero_hall = (
        OfficeQueueService
        .coda_hall(ufficio)
        .count()
    )

    numero_fuori = (
        OfficeQueueService
        .coda_fuori_ufficio(ufficio)
        .count()
    )

    numero_in_ufficio = (
        OfficeQueueService
        .visite_in_corso_ufficio(ufficio)
        .count()
    )

    return JsonResponse(
        {
            "success": True,
            "numero_prioritari": numero_prioritari,
            "numero_hall": numero_hall,
            "numero_fuori": numero_fuori,
            "numero_in_ufficio": numero_in_ufficio,
            "visita_corrente": (
                {
                    "id": visita_corrente.pk,
                    "numero": (
                        visita_corrente
                        .numero_coda_formattato
                    ),
                }
                if visita_corrente
                else None
            ),
        }
    )
