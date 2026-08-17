from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.utils import timezone
from django.views.decorators.http import (
    require_GET,
    require_POST,
)

from common.exceptions import (
    BusinessException,
    TicketPrinterException,
)
from visitors.forms import RegistrazioneVisitatoreForm, ChiusuraAccessoForm
from visitors.models import (
    AccessoVisitatore,
    Visitatore,
)
from visitors.services.reception_service import (
    ReceptionService,
)
from visitors.services.ticket_printer_service import (
    TicketPrinterService,
)
from visitors.permissions import portineria_required

def _normalizza_testo(value):
    return " ".join(
        (value or "").strip().split()
    )


def _trova_visitatore(
    codice_fiscale="",
    documento_numero="",
):
    """
    Cerca prima per codice fiscale e poi per
    numero del documento.
    """

    if codice_fiscale:
        visitatore = (
            Visitatore.objects
            .filter(
                codice_fiscale__iexact=codice_fiscale,
            )
            .first()
        )

        if visitatore:
            return visitatore

    if documento_numero:
        return (
            Visitatore.objects
            .filter(
                documento_numero__iexact=documento_numero,
            )
            .first()
        )

    return None


def _nuovo_accesso(request, tipo_accesso):
    """
    Data-entry comune a ricevimento e visita.

    Cambiano soltanto:
    - gli uffici selezionabili;
    - il tipo di accesso salvato;
    - il workflow successivo della coda.
    """

    is_visita = (
        tipo_accesso
        == AccessoVisitatore.TipoAccesso.VISITA
    )

    motivi_visita = list(
        AccessoVisitatore.objects
        .exclude(motivo="")
        .order_by("motivo")
        .values_list(
            "motivo",
            flat=True,
        )
        .distinct()
    )

    form_kwargs = {
        "tipo_accesso": tipo_accesso,
    }

    if request.method == "POST":
        form_kwargs["data"] = request.POST

    form = RegistrazioneVisitatoreForm(
        **form_kwargs,
    )

    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                documento_presentato = (
                    form.cleaned_data[
                        "documento_presentato"
                    ]
                )

                documento_tipo = (
                    form.cleaned_data.get(
                        "documento_tipo"
                    )
                    or ""
                )

                documento_numero = (
                    form.cleaned_data.get(
                        "documento_numero"
                    )
                    or ""
                )

                documento_scadenza = (
                    form.cleaned_data.get(
                        "documento_scadenza"
                    )
                )

                codice_fiscale = (
                    form.cleaned_data.get(
                        "codice_fiscale"
                    )
                    or ""
                )

                nome = _normalizza_testo(
                    form.cleaned_data["nome"]
                )

                cognome = _normalizza_testo(
                    form.cleaned_data["cognome"]
                )

                telefono = _normalizza_testo(
                    form.cleaned_data["telefono"]
                )

                motivo = form.cleaned_data[
                    "motivo"
                ]

                note = _normalizza_testo(
                    form.cleaned_data.get(
                        "note"
                    )
                )

                visitatore = _trova_visitatore(
                    codice_fiscale=codice_fiscale,
                    documento_numero=documento_numero,
                )

                if visitatore is None:
                    visitatore = Visitatore.objects.create(
                        nome=nome,
                        cognome=cognome,
                        codice_fiscale=codice_fiscale,
                        documento_tipo=documento_tipo,
                        documento_numero=documento_numero,
                        documento_scadenza=documento_scadenza,
                        telefono=telefono,
                    )

                else:
                    campi_modificati = []

                    valori = {
                        "nome": nome,
                        "cognome": cognome,
                        "telefono": telefono,
                    }

                    if codice_fiscale:
                        valori["codice_fiscale"] = (
                            codice_fiscale
                        )

                    if documento_presentato:
                        valori.update(
                            {
                                "documento_tipo": documento_tipo,
                                "documento_numero": documento_numero,
                                "documento_scadenza": documento_scadenza,
                            }
                        )

                    for campo, valore in valori.items():
                        if getattr(visitatore, campo) != valore:
                            setattr(visitatore, campo, valore)
                            campi_modificati.append(campo)

                    if campi_modificati:
                        visitatore.save(
                            update_fields=campi_modificati,
                        )

                accesso = ReceptionService.check_in(
                    visitatore=visitatore,
                    ufficio=form.cleaned_data["ufficio"],
                    motivo=motivo,
                    note=note,
                    documento_presentato=documento_presentato,
                    operatore=request.user,
                    ip_address=_get_client_ip(request),
                    tipo_accesso=tipo_accesso,
                )

            ticket_stampato = False
            errore_stampa = ""

            try:
                ticket_stampato = (
                    TicketPrinterService
                    .stampa_accesso(accesso)
                )
            except TicketPrinterException as exc:
                errore_stampa = str(exc)

            request.session[
                f"ticket_stampato_{accesso.pk}"
            ] = ticket_stampato

            request.session[
                f"errore_stampa_{accesso.pk}"
            ] = errore_stampa

            return redirect(
                "portineria:registrazione_completata",
                pk=accesso.pk,
            )

        except BusinessException as exc:
            form.add_error(None, str(exc))

    return render(
        request,
        "visitors/nuova_registrazione.html",
        {
            "form": form,
            "motivi_visita": motivi_visita,
            "tipo_accesso": tipo_accesso,
            "is_visita": is_visita,
            "titolo_registrazione": (
                "Nuova visita"
                if is_visita
                else "Nuovo ricevimento"
            ),
            "testo_registrazione": (
                "Il visitatore resterà nella hall fino "
                "all'autorizzazione alla salita da parte "
                "dell'ufficio."
                if is_visita
                else
                "Registrazione per il ricevimento del pubblico."
            ),
        },
    )


@portineria_required
def nuovo_ricevimento(request):
    return _nuovo_accesso(
        request,
        AccessoVisitatore.TipoAccesso.RICEVIMENTO,
    )


@portineria_required
def nuova_visita(request):
    return _nuovo_accesso(
        request,
        AccessoVisitatore.TipoAccesso.VISITA,
    )


@portineria_required
def nuova_registrazione(request):
    """Compatibilità con il vecchio URL."""
    return redirect("portineria:nuovo_ricevimento")


@portineria_required
def registrazione_completata(request, pk):
    accesso = get_object_or_404(
        AccessoVisitatore.objects.select_related(
            "visitatore",
            "ufficio_destinazione",
            "badge",
        ),
        pk=pk,
    )

    ticket_stampato = request.session.pop(
        f"ticket_stampato_{accesso.pk}",
        False,
    )

    errore_stampa = request.session.pop(
        f"errore_stampa_{accesso.pk}",
        "",
    )

    return render(
        request,
        "visitors/registrazione_completata.html",
        {
            "accesso": accesso,
            "ticket_stampato": ticket_stampato,
            "errore_stampa": errore_stampa,
        },
    )


@portineria_required
@require_GET
def cerca_visitatore(request):
    """
    Ricerca tramite codice fiscale oppure
    numero documento.
    """

    codice_fiscale = (
        request.GET.get("codice_fiscale")
        or ""
    ).strip().upper()

    documento_numero = (
        request.GET.get("documento_numero")
        or ""
    ).strip().upper()

    if not codice_fiscale and not documento_numero:
        return JsonResponse(
            {
                "found": False,
            }
        )

    visitatore = _trova_visitatore(
        codice_fiscale=codice_fiscale,
        documento_numero=documento_numero,
    )

    if visitatore is None:
        return JsonResponse(
            {
                "found": False,
            }
        )

    return JsonResponse(
        {
            "found": True,
            "visitatore": {
                "id": visitatore.pk,
                "nome": visitatore.nome,
                "cognome": visitatore.cognome,
                "codice_fiscale": (
                    visitatore.codice_fiscale
                ),
                "documento_tipo": (
                    visitatore.documento_tipo
                ),
                "documento_numero": (
                    visitatore.documento_numero
                ),
                "documento_scadenza": (
                    visitatore
                    .documento_scadenza
                    .isoformat()
                    if visitatore.documento_scadenza
                    else ""
                ),
                "telefono": visitatore.telefono,
            },
        }
    )


@portineria_required
@require_POST
def ristampa_ticket(request, pk):
    accesso = get_object_or_404(
        AccessoVisitatore.objects.select_related(
            "visitatore",
            "ufficio_destinazione",
            "badge",
        ),
        pk=pk,
    )

    try:
        stampato = (
            TicketPrinterService.stampa_accesso(
                accesso
            )
        )

        if stampato:
            messages.success(
                request,
                (
                    "Ticket ristampato correttamente. "
                    f"Numero di coda: "
                    f"{accesso.numero_coda_formattato}."
                ),
            )
        else:
            messages.warning(
                request,
                "La stampa dei ticket è disabilitata.",
            )

    except TicketPrinterException as exc:
        messages.error(
            request,
            str(exc),
        )

    return redirect(
        "portineria:registrazione_completata",
        pk=accesso.pk,
    )

def _get_client_ip(request):
    forwarded_for = request.META.get(
        "HTTP_X_FORWARDED_FOR"
    )

    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    return request.META.get("REMOTE_ADDR")


@portineria_required
def chiudi_accesso(request, pk):
    accesso = get_object_or_404(
        AccessoVisitatore.objects.select_related(
            "visitatore",
            "ufficio_destinazione",
            "badge",
        ),
        pk=pk,
        uscita__isnull=True,
    )

    if request.method == "POST":
        form = ChiusuraAccessoForm(
            request.POST,
            accesso=accesso,
        )

        if form.is_valid():
            try:
                ReceptionService.check_out(
                    accesso=accesso,
                    uscita=form.cleaned_data["uscita"],
                    operatore=request.user,
                    note_chiusura=(
                        form.cleaned_data["note_chiusura"]
                        .strip()
                    ),
                    ip_address=_get_client_ip(request),
                )

                messages.success(
                    request,
                    (
                        "Uscita registrata correttamente alle "
                        f"{timezone.localtime(form.cleaned_data['uscita']):%H:%M}. "
                        "Il badge è nuovamente disponibile."
                    ),
                )

                return redirect("dashboard:home")

            except BusinessException as exc:
                form.add_error(None, str(exc))

    else:
        form = ChiusuraAccessoForm(
            accesso=accesso,
        )

    return render(
        request,
        "visitors/chiudi_accesso.html",
        {
            "accesso": accesso,
            "form": form,
        },
    )