from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from dashboard.permissions import dirigenza_required
from visitors.models import (
    AccessoVisitatore,
    AmministratoreEnte,
    TransitoAmministratore,
    Visitatore,
)


User = get_user_model()


GRUPPI_AMMINISTRATORI = (
    "Giunta",
    "Consiglieri",
)


def _profilo_amministratore_per_utente(utente):
    """
    Il profilo serve solo come chiave per i transiti.
    L'anagrafica continua a provenire dall'utente AD.
    """
    profilo, _ = AmministratoreEnte.objects.get_or_create(
        utente=utente,
        defaults={
            "attivo": True,
            "ordine": 0,
        },
    )

    if not profilo.attivo:
        profilo.attivo = True
        profilo.save(update_fields=["attivo"])

    return profilo


def _amministratori_per_gruppo(nome_gruppo):
    utenti = (
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

    risultato = []

    for utente in utenti:
        profilo = _profilo_amministratore_per_utente(
            utente
        )

        ultimo = (
            profilo.transiti
            .order_by("-timestamp", "-pk")
            .first()
        )

        risultato.append(
            {
                "profilo": profilo,
                "utente": utente,
                "ultimo_transito": ultimo,
                "presente": bool(
                    ultimo
                    and ultimo.tipo
                    == TransitoAmministratore.Tipo.INGRESSO
                ),
            }
        )

    return risultato


@dirigenza_required
def area_dirigenza(request):
    giunta = _amministratori_per_gruppo("Giunta")
    consiglieri = _amministratori_per_gruppo(
        "Consiglieri"
    )

    presenti = sum(
        1
        for riga in giunta + consiglieri
        if riga["presente"]
    )

    return render(
        request,
        "dashboard/dirigenza_home.html",
        {
            "numero_giunta": len(giunta),
            "numero_consiglieri": len(consiglieri),
            "numero_amministratori_presenti": presenti,
        },
    )


@dirigenza_required
def ricerca_visitatori(request):
    query = (
        request.GET.get("q")
        or ""
    ).strip()

    risultati = Visitatore.objects.none()

    if query:
        risultati = (
            Visitatore.objects
            .filter(
                Q(nome__icontains=query)
                | Q(cognome__icontains=query)
                | Q(codice_fiscale__icontains=query)
                | Q(documento_numero__icontains=query)
                | Q(telefono__icontains=query)
            )
            .order_by(
                "cognome",
                "nome",
            )[:100]
        )

    return render(
        request,
        "dashboard/ricerca_visitatori.html",
        {
            "query": query,
            "risultati": risultati,
        },
    )


@dirigenza_required
def dettaglio_visitatore(request, pk):
    visitatore = get_object_or_404(
        Visitatore,
        pk=pk,
    )

    accessi = (
        AccessoVisitatore.objects
        .filter(visitatore=visitatore)
        .select_related(
            "ufficio_destinazione",
            "badge",
            "operatore_assegnato",
        )
        .order_by("-ingresso")
    )

    return render(
        request,
        "dashboard/dettaglio_visitatore.html",
        {
            "visitatore": visitatore,
            "accessi": accessi,
        },
    )


@dirigenza_required
def stato_amministratori(request):
    giunta = _amministratori_per_gruppo("Giunta")
    consiglieri = _amministratori_per_gruppo(
        "Consiglieri"
    )

    return render(
        request,
        "dashboard/stato_amministratori.html",
        {
            "giunta": giunta,
            "consiglieri": consiglieri,
        },
    )


@dirigenza_required
def log_amministratore(request, pk):
    profilo = get_object_or_404(
        AmministratoreEnte.objects
        .select_related("utente"),
        pk=pk,
        utente__is_active=True,
    )

    transiti = (
        profilo.transiti
        .select_related("operatore")
        .order_by("-timestamp", "-pk")[:250]
    )

    ultimo = transiti.first()

    presente = bool(
        ultimo
        and ultimo.tipo
        == TransitoAmministratore.Tipo.INGRESSO
    )

    return render(
        request,
        "dashboard/log_amministratore.html",
        {
            "profilo": profilo,
            "transiti": transiti,
            "ultimo_transito": ultimo,
            "presente": presente,
        },
    )
