import re
import secrets
import unicodedata

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.http import JsonResponse

from accounts.services.directory_admin_service import DirectoryAdminException, DirectoryAdminService
from access_control.models import GruppoOrganizzativo, Ufficio
from audit.services.audit_service import AuditService
from dashboard.permissions import directory_admin_required

User = get_user_model()


def _username_base(first_name, last_name):
    """Mario Rossi -> m.rossi; gli accenti e i separatori non entrano nello username."""
    def normalizza(value):
        value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
        return re.sub(r"[^a-z0-9]", "", value.lower())

    nome, cognome = normalizza(first_name), normalizza(last_name)
    if not nome or not cognome:
        raise DirectoryAdminException("Nome e cognome devono contenere almeno una lettera o un numero.")
    return "%s.%s" % (nome[0], cognome)


def _username_proposto(first_name, last_name):
    base = _username_base(first_name, last_name)
    servizio = DirectoryAdminService()
    suffisso = 1
    while True:
        candidato = base if suffisso == 1 else "%s%s" % (base, suffisso)
        if not User.objects.filter(username__iexact=candidato).exists() and not servizio.username_esiste(candidato):
            return candidato
        suffisso += 1


def _password_provvisoria():
    gruppi = (
        "ABCDEFGHJKLMNPQRSTUVWXYZ",
        "abcdefghijkmnopqrstuvwxyz",
        "23456789",
        "!@#$%",
    )
    caratteri = [secrets.choice(gruppo) for gruppo in gruppi]
    alfabeto = "".join(gruppi)
    caratteri.extend(secrets.choice(alfabeto) for _ in range(12))
    secrets.SystemRandom().shuffle(caratteri)
    return "".join(caratteri)


@directory_admin_required
def directory_home(request):
    return render(request, "dashboard/directory_portal.html")


@directory_admin_required
def directory_user_create(request):
    gruppi_operativi = GruppoOrganizzativo.objects.filter(
        tipo=GruppoOrganizzativo.Tipo.ORGANIZZATIVO,
        attivo=True,
        ufficio__attivo=True,
    ).select_related("ufficio", "django_group").order_by("ufficio__nome", "nome")
    return render(
        request,
        "dashboard/directory_user_create.html",
        {
            "uffici": Ufficio.objects.filter(attivo=True).order_by("nome"),
            "gruppi_operativi": gruppi_operativi,
            "domini_istituzionali": settings.INSTITUTIONAL_EMAIL_DOMAINS,
        },
    )


@directory_admin_required
def directory_username_suggestion(request):
    try:
        username = _username_proposto(request.GET.get("first_name", ""), request.GET.get("last_name", ""))
        return JsonResponse({"username": username})
    except DirectoryAdminException as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({"error": "Impossibile verificare lo username in Active Directory: %s" % exc}, status=503)


@directory_admin_required
@require_POST
def directory_user_create_submit(request):
    try:
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        email = request.POST.get("email", "").strip()
        mobile = request.POST.get("mobile", "").strip()
        if not first_name or not last_name or not email:
            raise DirectoryAdminException("Nome, cognome ed e-mail sono obbligatori.")
        gruppo = get_object_or_404(
            GruppoOrganizzativo.objects.select_related("ufficio", "django_group"),
            pk=request.POST.get("gruppo_organizzativo"),
            tipo=GruppoOrganizzativo.Tipo.ORGANIZZATIVO,
            attivo=True,
            ufficio_id=request.POST.get("ufficio"),
            ufficio__attivo=True,
        )
        username = _username_proposto(first_name, last_name)
        password = _password_provvisoria()
        mail_istituzionale = request.POST.get("mail_istituzionale") == "on"
        dominio = request.POST.get("dominio_istituzionale", "").strip().lower()
        if mail_istituzionale and dominio not in settings.INSTITUTIONAL_EMAIL_DOMAINS:
            raise DirectoryAdminException("Selezionare un dominio valido per la mail istituzionale.")
        email_directory = "%s@%s" % (username, dominio) if mail_istituzionale else email
        service = DirectoryAdminService()
        user_dn = service.crea_utente(username, first_name, last_name, email_directory, email, mobile, password)
        service.aggiungi_al_gruppo(user_dn, gruppo.directory_name)

        gruppi_locali = [gruppo.django_group]
        if mail_istituzionale:
            service.aggiungi_al_gruppo(user_dn, "MDAEMON")
            gruppo_mdaemon, _ = Group.objects.get_or_create(name="MDAEMON")
            gruppi_locali.append(gruppo_mdaemon)

        utente, creato = User.objects.update_or_create(
            username=username,
            defaults={"first_name": first_name, "last_name": last_name, "email": email_directory, "is_active": True},
        )
        if creato:
            utente.set_unusable_password()
            utente.save(update_fields=["password"])
        utente.groups.set(gruppi_locali)
        AuditService.log(
            user=request.user,
            tipo="CREATE",
            oggetto="ActiveDirectory:%s" % username,
            descrizione="Creato utente AD nell'ufficio %s e assegnato al gruppo %s%s" % (
                gruppo.ufficio,
                gruppo.directory_name,
                " e MDAEMON (%s)" % email_directory if mail_istituzionale else "",
            ),
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        try:
            from post_office import mail

            mail.send(
                recipients=[email],
                sender=settings.DEFAULT_FROM_EMAIL,
                subject="Credenziali di accesso",
                message=(
                    "Buongiorno %s %s,\n\n"
                    "è stato creato il suo account.\n"
                    "Username: %s\nPassword provvisoria: %s\n\n"
                    "Al primo accesso sarà richiesto di cambiare la password."
                ) % (first_name, last_name, username, password),
            )
        except Exception as exc:
            messages.warning(request, "Account creato, ma l'e-mail non è stata accodata: %s" % exc)
        messages.success(request, "Utente %s creato in Active Directory, sincronizzato localmente e password accodata per l'invio e-mail." % username)
        return redirect("dashboard:directory_users")
    except Exception as exc:
        messages.error(request, str(exc))
        return redirect("dashboard:directory_user_create")


@directory_admin_required
def directory_users(request):
    session_key = "directory_users_filters"
    if "reset" in request.GET:
        request.session.pop(session_key, None)
        filtri = {}
    elif request.GET:
        filtri = {"q": request.GET.get("q", ""), "tipo_attivita": request.GET.getlist("tipo_attivita"), "stato_presenza": request.GET.get("stato_presenza", ""), "stato_account": request.GET.get("stato_account", ""), "gruppo": request.GET.get("gruppo", "")}
        request.session[session_key] = filtri
    else:
        filtri = request.session.get(session_key, {})
    query = (filtri.get("q") or "").strip()
    utenti = User.objects.all().prefetch_related("groups")
    if query:
        utenti = utenti.filter(Q(username__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(email__icontains=query))
    tipi = filtri.get("tipo_attivita", [])
    presenza = filtri.get("stato_presenza", "")
    attivo = filtri.get("stato_account", "")
    gruppo = filtri.get("gruppo", "")
    if tipi: utenti = utenti.filter(tipo_attivita__in=tipi)
    if presenza: utenti = utenti.filter(stato_presenza=presenza)
    if attivo == "attivi": utenti = utenti.filter(is_active=True)
    elif attivo == "disattivi": utenti = utenti.filter(is_active=False)
    if gruppo: utenti = utenti.filter(groups__pk=gruppo)
    risultati = utenti.distinct().order_by("last_name", "first_name", "username")
    return render(request, "dashboard/directory_home.html", {"query": query, "utenti": risultati, "totale_utenti": User.objects.count(), "totale_filtrati": risultati.count(), "gruppi": Group.objects.order_by("name"), "tipi": tipi, "presenza": presenza, "attivo": attivo, "gruppo": gruppo})


@directory_admin_required
def directory_groups(request):
    query = (request.GET.get("q") or "").strip()
    try:
        gruppi = DirectoryAdminService().lista_gruppi()
        totale_gruppi = len(gruppi)
        if query:
            ricerca = query.casefold()
            gruppi = [
                gruppo for gruppo in gruppi
                if ricerca in gruppo["name"].casefold()
                or ricerca in gruppo["description"].casefold()
            ]
    except Exception as exc: gruppi = []; messages.error(request, "Impossibile leggere i gruppi AD: %s" % exc)
    return render(request, "dashboard/directory_groups.html", {"gruppi": gruppi, "query": query, "totale_gruppi": totale_gruppi if 'totale_gruppi' in locals() else 0, "totale_filtrati": len(gruppi)})


@directory_admin_required
@require_POST
def directory_group_rename(request):
    nome, nuovo_nome = request.POST.get("nome", ""), request.POST.get("nuovo_nome", "")
    try:
        if not nuovo_nome.strip(): raise DirectoryAdminException("Indicare il nuovo nome del gruppo.")
        DirectoryAdminService().rinomina_gruppo(nome, nuovo_nome)
        AuditService.log(user=request.user, tipo="UPDATE", oggetto="ActiveDirectoryGroup:%s" % nome, descrizione="Gruppo AD rinominato in %s." % nuovo_nome, ip_address=request.META.get("REMOTE_ADDR")); messages.success(request, "Gruppo AD rinominato. Eseguire ora la sincronizzazione directory.")
    except Exception as exc: messages.error(request, str(exc))
    return redirect("dashboard:directory_groups")


@directory_admin_required
@require_POST
def directory_bulk_action(request):
    tipi = {"amministrativista": User.TipoAttivita.AMMINISTRATIVISTA, "sportellista": User.TipoAttivita.SPORTELLISTA, "tecnico": User.TipoAttivita.TECNICO, "disuso": User.TipoAttivita.DISUSO}
    ids, azione = request.POST.getlist("utenti"), request.POST.get("azione")
    if not ids:
        messages.warning(request, "Selezionare almeno un utente.")
    elif azione not in tipi:
        messages.error(request, "Azione massiva non valida.")
    else:
        aggiornati = User.objects.filter(pk__in=ids).update(tipo_attivita=tipi[azione])
        AuditService.log(user=request.user, tipo="UPDATE", oggetto="DirectoryAdmin:bulk", descrizione="Tipo attività %s per %s utenti." % (azione, aggiornati), ip_address=request.META.get("REMOTE_ADDR"))
        messages.success(request, "Aggiornati %s utenti." % aggiornati)
    return redirect("dashboard:directory_home")


@directory_admin_required
def directory_user(request, pk):
    utente = get_object_or_404(User, pk=pk)
    try:
        dettaglio = DirectoryAdminService().dettaglio(utente.username)
    except Exception as exc:
        dettaglio = None; messages.error(request, "Impossibile leggere AD: %s" % exc)
    return render(request, "dashboard/directory_user.html", {"utente": utente, "dettaglio": dettaglio})


@directory_admin_required
@require_POST
def directory_action(request, pk):
    utente = get_object_or_404(User, pk=pk); service = DirectoryAdminService(); azione = request.POST.get("azione")
    try:
        if azione == "anagrafica":
            first_name = request.POST.get("first_name", "").strip()
            last_name = request.POST.get("last_name", "").strip()
            service.aggiorna_anagrafica(
                utente.username,
                first_name,
                last_name,
                request.POST.get("personal_email", ""),
                request.POST.get("mobile", ""),
            )
            User.objects.filter(pk=utente.pk).update(first_name=first_name, last_name=last_name)
        elif azione == "stato": service.imposta_attivo(utente.username, request.POST.get("attivo") == "true")
        elif azione == "password":
            password = request.POST.get("password", "")
            if len(password) < 12: raise DirectoryAdminException("La password provvisoria deve avere almeno 12 caratteri.")
            service.reset_password(utente.username, password, request.POST.get("forza_cambio") == "on")
        elif azione == "gruppi": service.aggiorna_gruppi(utente.username, [item.strip() for item in request.POST.get("gruppi", "").splitlines() if item.strip()])
        else: raise DirectoryAdminException("Operazione non valida.")
        AuditService.log(user=request.user, tipo="UPDATE", oggetto="ActiveDirectory:%s" % utente.username, descrizione="Operazione AD: %s." % azione, ip_address=request.META.get("REMOTE_ADDR")); messages.success(request, "Operazione AD completata.")
    except Exception as exc:
        AuditService.log(user=request.user, tipo="SYSTEM", oggetto="ActiveDirectory:%s" % utente.username, descrizione="Operazione AD non riuscita: %s; errore: %s" % (azione, exc), ip_address=request.META.get("REMOTE_ADDR"))
        messages.error(request, str(exc))
    return redirect("dashboard:directory_user", pk=utente.pk)
