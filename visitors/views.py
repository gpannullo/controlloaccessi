from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Value
from django.db.models.functions import Replace, Upper
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

from ControlloAccessi.settings import DIRECTORY
from prenotazioni.services import appuntamento_wordpress_per_checkin
from common.exceptions import (
    BusinessException,
    TicketPrinterException,
)
from visitors.forms import (
    RegistrazioneVisitatoreForm,
    ChiusuraAccessoForm,
    RientroBadgeForm,
)
from visitors.models import (
    Appuntamento,
    AccessoVisitatore,
    Visitatore,
    Badge,
    AmministratoreEnte,
    TransitoAmministratore,
)
from visitors.services.reception_service import (
    ReceptionService,
)
from visitors.services.ticket_printer_service import (
    TicketPrinterService,
)
from visitors.permissions import portineria_required
from visitors.services.continuity_service import ContinuitaAccessoService

def _normalizza_testo(value):
    return " ".join(
        (value or "").strip().split()
    )


def _normalizza_numero_documento(value):
    """Rende confrontabili i numeri documento inseriti in formati diversi."""
    return (
        (value or "")
        .strip()
        .upper()
        .replace(" ", "")
        .replace("-", "")
        .replace(".", "")
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

    documento_numero = _normalizza_numero_documento(documento_numero)
    if documento_numero:
        return (
            Visitatore.objects
            .annotate(
                documento_normalizzato=Replace(
                    Replace(
                        Replace(
                            Upper("documento_numero"),
                            Value(" "),
                            Value(""),
                        ),
                        Value("-"),
                        Value(""),
                    ),
                    Value("."),
                    Value(""),
                )
            )
            .filter(
                documento_normalizzato=documento_numero,
            )
            .first()
        )

    return None


def _appuntamento_per_ricevimento(request):
    """Restituisce l'appuntamento scelto dalla lista di Portineria.

    L'appuntamento deve essere odierno, non annullato e non ancora collegato
    a un accesso. In questo modo il collegamento non dipende dal confronto
    del nominativo digitato dall'operatore.
    """
    appuntamento_id = (
        request.POST.get("appuntamento_id")
        or request.GET.get("appuntamento")
    )
    if not appuntamento_id:
        return None

    return get_object_or_404(
        Appuntamento.objects.select_related("ufficio").filter(
            pk=appuntamento_id,
            data_ora__date=timezone.localdate(),
            stato__in=[
                Appuntamento.Stato.PRENOTATO,
                Appuntamento.Stato.CONFERMATO,
            ],
            accesso__isnull=True,
        ),
    )


@portineria_required
def appuntamenti_oggi(request):
    """Elenco operativo degli appuntamenti da registrare in Portineria."""
    ricerca = " ".join((request.GET.get("q") or "").split())
    appuntamenti = (
        Appuntamento.objects.select_related("ufficio")
        .filter(
            data_ora__date=timezone.localdate(),
            stato__in=[
                Appuntamento.Stato.PRENOTATO,
                Appuntamento.Stato.CONFERMATO,
            ],
            accesso__isnull=True,
        )
        .order_by("ufficio__nome", "data_ora", "cognome_cittadino", "nome_cittadino")
    )
    if ricerca:
        from django.db.models import Q

        appuntamenti = appuntamenti.filter(
            Q(nome_cittadino__icontains=ricerca)
            | Q(cognome_cittadino__icontains=ricerca)
            | Q(origine_wordpress__nome_prenotato__icontains=ricerca)
            | Q(origine_wordpress__codice_fiscale__icontains=ricerca)
        )

    appuntamenti_per_ufficio = []
    for appuntamento in appuntamenti:
        if (
            not appuntamenti_per_ufficio
            or appuntamenti_per_ufficio[-1]["ufficio"].pk
            != appuntamento.ufficio_id
        ):
            appuntamenti_per_ufficio.append(
                {"ufficio": appuntamento.ufficio, "appuntamenti": []}
            )
        appuntamenti_per_ufficio[-1]["appuntamenti"].append(appuntamento)

    return render(
        request,
        "visitors/appuntamenti_oggi.html",
        {
            "ricerca": ricerca,
            "appuntamenti_per_ufficio": appuntamenti_per_ufficio,
            "numero_appuntamenti": sum(
                len(gruppo["appuntamenti"])
                for gruppo in appuntamenti_per_ufficio
            ),
        },
    )


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

    appuntamento_selezionato = None
    if not is_visita:
        appuntamento_selezionato = _appuntamento_per_ricevimento(request)

    form_kwargs = {
        "tipo_accesso": tipo_accesso,
    }

    if appuntamento_selezionato and request.method != "POST":
        form_kwargs["initial"] = {
            "appuntamento_id": appuntamento_selezionato.pk,
            "nome": appuntamento_selezionato.nome_cittadino,
            "cognome": appuntamento_selezionato.cognome_cittadino,
            "telefono": appuntamento_selezionato.telefono,
            "ufficio": appuntamento_selezionato.ufficio_id,
            "motivo": appuntamento_selezionato.motivo,
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

                appuntamento = appuntamento_selezionato
                if appuntamento and appuntamento.ufficio_id != form.cleaned_data["ufficio"].pk:
                    raise BusinessException(
                        "L'ufficio selezionato non corrisponde all'appuntamento."
                    )
                if not is_visita and appuntamento is None:
                    appuntamento = appuntamento_wordpress_per_checkin(
                        visitatore,
                        form.cleaned_data["ufficio"],
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
                    accompagnato=form.cleaned_data.get("accompagnato", False),
                    appuntamento=appuntamento,
                )

                if appuntamento:
                    appuntamento.conferma()
                    messages.success(
                        request,
                        "Appuntamento verificato: al visitatore è stata attribuita la priorità in coda.",
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
            "appuntamento_selezionato": appuntamento_selezionato,
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

    documento_numero = _normalizza_numero_documento(
        request.GET.get("documento_numero") or ""
    )

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

        request.session[f"ticket_stampato_{accesso.pk}"] = stampato
        request.session[f"errore_stampa_{accesso.pk}"] = ""

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
        request.session[f"ticket_stampato_{accesso.pk}"] = False
        request.session[f"errore_stampa_{accesso.pk}"] = str(exc)
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
                    riserva_badge_rientro=(
                        request.POST.get("azione") == "rientro"
                    ),
                )

                riservato = (
                    request.POST.get("azione") == "rientro"
                )
                testo_badge = (
                    "Il badge resta riservato per il rientro."
                    if riservato
                    else "Il badge è nuovamente disponibile."
                )
                messages.success(
                    request,
                    (
                        "Uscita registrata correttamente alle "
                        f"{timezone.localtime(form.cleaned_data['uscita']):%H:%M}. "
                        f"{testo_badge}"
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

@portineria_required
def rientro_badge(request):
    form = RientroBadgeForm(request.POST or None)
    badge_riservati = Badge.objects.filter(
        attivo=True, riservato_rientro=True
    ).order_by("codice")

    if request.method == "POST" and form.is_valid():
        try:
            accesso = ContinuitaAccessoService.rientro_da_badge(
                codice_badge=form.cleaned_data["badge"],
                operatore=request.user,
                ip_address=_get_client_ip(request),
            )
            messages.success(
                request,
                f"Rientro registrato. Badge {accesso.badge.codice}, "
                f"coda {accesso.numero_coda_formattato} con priorità.",
            )
            return redirect(
                "portineria:registrazione_completata", pk=accesso.pk
            )
        except BusinessException as exc:
            form.add_error("badge", str(exc))

    return render(
        request,
        "visitors/rientro_badge.html",
        {"form": form, "badge_riservati": badge_riservati},
    )


@portineria_required
@require_POST
def libera_badge_rientro(request, badge_id):
    badge = get_object_or_404(Badge, pk=badge_id)
    try:
        ContinuitaAccessoService.libera_badge_rientro(
            badge=badge,
            operatore=request.user,
            ip_address=_get_client_ip(request),
        )
        messages.success(
            request, f"Badge {badge.codice} nuovamente disponibile."
        )
    except BusinessException as exc:
        messages.warning(request, str(exc))
    return redirect("portineria:rientro_badge")


@portineria_required
def amministratori(request):
    """
    Pannello portineria per la registrazione rapida dei transiti
    degli utenti appartenenti ai gruppi AD Giunta e Consiglieri.
    La portineria non calcola né mostra lo stato presente/assente.
    """
    User = get_user_model()

    def prepara_gruppo(nome_gruppo):
        utenti = list(
            User.objects
            .filter(
                is_active=True,
                groups__name=nome_gruppo,
            )
            .distinct()
            .order_by(
                "last_name",
                "first_name",
                "username",
            )
        )

        persone = []

        for utente in utenti:
            persona, _ = AmministratoreEnte.objects.get_or_create(
                utente=utente,
                defaults={
                    "attivo": True,
                    "ordine": 0,
                },
            )

            if not persona.attivo:
                persona.attivo = True
                persona.save(update_fields=["attivo"])

            persone.append(persona)

        return persone

    return render(
        request,
        "visitors/amministratori.html",
        {
            "giunta": prepara_gruppo(DIRECTORY['GIUNTA_GROUP']),
            "consiglieri": prepara_gruppo(DIRECTORY['CONSIGLIERI_GROUP']),
        },
    )


@portineria_required
@require_POST
def registra_transito_amministratore(request, pk):
    """
    Registra il passaggio indicato esplicitamente dall'operatore:
    ingresso oppure uscita. Nessun calcolo di stato viene eseguito
    nella pagina di portineria.
    """
    persona = get_object_or_404(
        AmministratoreEnte.objects.select_related("utente"),
        pk=pk,
        attivo=True,
        utente__is_active=True,
    )

    tipo = request.POST.get("tipo")

    tipi_validi = {
        TransitoAmministratore.Tipo.INGRESSO,
        TransitoAmministratore.Tipo.USCITA,
    }

    if tipo not in tipi_validi:
        messages.error(
            request,
            "Tipo di transito non valido.",
        )
        return redirect("portineria:amministratori")

    transito = TransitoAmministratore.objects.create(
        amministratore=persona,
        tipo=tipo,
        operatore=request.user,
    )

    nome = (
        persona.utente.get_full_name()
        or persona.utente.username
    )

    messages.success(
        request,
        (
            f"{transito.get_tipo_display()} registrato per "
            f"{nome} alle "
            f"{timezone.localtime(transito.timestamp):%H:%M}."
        ),
    )

    return redirect("portineria:amministratori")
