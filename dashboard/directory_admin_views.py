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
from prenotazioni.models import PersonaleWordPress, UnitaOrganizzativaWordPress
from prenotazioni.wordpress_connector import WordPressConnectorError, crea_unita_organizzativa_wordpress

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


def _directory_user_create_context(form_data=None):
    gruppi_operativi = GruppoOrganizzativo.objects.filter(
        tipo=GruppoOrganizzativo.Tipo.ORGANIZZATIVO,
        attivo=True,
        ufficio__attivo=True,
    ).select_related("ufficio", "django_group").order_by("ufficio__nome", "nome")
    return {
        "uffici": Ufficio.objects.filter(attivo=True).order_by("nome"),
        "gruppi_operativi": gruppi_operativi,
        "domini_istituzionali": settings.INSTITUTIONAL_EMAIL_DOMAINS,
        "form_data": form_data or {},
    }


@directory_admin_required
def directory_user_create(request):
    return render(request, "dashboard/directory_user_create.html", _directory_user_create_context())


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
        user_dn = service.crea_utente(
            username,
            first_name,
            last_name,
            email_directory,
            email,
            mobile,
            password,
            upn_domain=dominio if mail_istituzionale else None,
        )
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
        return render(
            request,
            "dashboard/directory_user_create.html",
            _directory_user_create_context(request.POST),
            status=400,
        )


@directory_admin_required
def directory_users(request):
    session_key = "directory_users_filters"
    if "reset" in request.GET:
        request.session.pop(session_key, None)
        filtri = {}
    elif request.GET:
        filtri = {"q": request.GET.get("q", ""), "tipo_attivita": request.GET.getlist("tipo_attivita"), "stato_presenza": request.GET.get("stato_presenza", ""), "stato_account": request.GET.get("stato_account", ""), "gruppo": request.GET.get("gruppo", ""), "ufficio": request.GET.getlist("ufficio")}
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
    uffici_selezionati = filtri.get("ufficio", [])
    if isinstance(uffici_selezionati, str):
        uffici_selezionati = [uffici_selezionati] if uffici_selezionati else []
    if tipi: utenti = utenti.filter(tipo_attivita__in=tipi)
    if presenza: utenti = utenti.filter(stato_presenza=presenza)
    if attivo == "attivi": utenti = utenti.filter(is_active=True)
    elif attivo == "disattivi": utenti = utenti.filter(is_active=False)
    if gruppo: utenti = utenti.filter(groups__pk=gruppo)
    if uffici_selezionati:
        utenti = utenti.filter(groups__gruppi_organizzativi__ufficio_id__in=uffici_selezionati)
    risultati = utenti.distinct().order_by("last_name", "first_name", "username")
    return render(request, "dashboard/directory_home.html", {"query": query, "utenti": risultati, "totale_utenti": User.objects.count(), "totale_filtrati": risultati.count(), "gruppi": Group.objects.order_by("name"), "uffici": Ufficio.objects.filter(attivo=True).order_by("nome"), "uffici_selezionati": [str(pk) for pk in uffici_selezionati], "tipi": tipi, "presenza": presenza, "attivo": attivo, "gruppo": gruppo})


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
def directory_staff(request):
    session_key = "directory_staff_offices"
    if "reset" in request.GET:
        request.session.pop(session_key, None)
        uffici_selezionati = []
    elif "uffici" in request.GET:
        uffici_selezionati = request.GET.getlist("uffici")
        request.session[session_key] = uffici_selezionati
    else:
        uffici_selezionati = request.session.get(session_key, [])
    personale = User.objects.filter(
        groups__gruppi_organizzativi__ufficio__isnull=False,
        groups__gruppi_organizzativi__ufficio__attivo=True,
    ).distinct().prefetch_related("groups__gruppi_organizzativi__ufficio").order_by("last_name", "first_name", "username")
    if uffici_selezionati:
        personale = personale.filter(groups__gruppi_organizzativi__ufficio_id__in=uffici_selezionati).distinct()
    for utente in personale:
        assegnazioni = [
            gruppo_operativo.ufficio
            for gruppo in utente.groups.all()
            for gruppo_operativo in gruppo.gruppi_organizzativi.all()
            if gruppo_operativo.ufficio_id
        ]
        utente.uffici_associati = list({ufficio.pk: ufficio for ufficio in assegnazioni}.values())
        utente.numero_uffici = len(utente.uffici_associati)
        utente.email_istituzionale = utente.email if utente.groups.filter(name="MDAEMON").exists() else ""
        utente.cellulare = utente.cellulare_personale
    return render(request, "dashboard/directory_staff.html", {"personale": personale, "uffici": Ufficio.objects.filter(attivo=True).order_by("nome"), "uffici_selezionati": [str(pk) for pk in uffici_selezionati]})


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
@require_POST
def directory_sync_mail_from_upn(request):
    try:
        aggiornati, saltati, errori = DirectoryAdminService().allinea_mail_da_upn()
        for item in aggiornati:
            User.objects.filter(username__iexact=item["username"]).update(email=item["email"])
        AuditService.log(
            user=request.user,
            tipo="UPDATE",
            oggetto="ActiveDirectory:mail",
            descrizione="Allineate %s e-mail LDAP dal relativo UPN; %s utenti già valorizzati; %s errori." % (
                len(aggiornati), saltati, len(errori),
            ),
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        messaggio = "%s e-mail LDAP allineate dall'UPN. %s utenti avevano già l'e-mail." % (len(aggiornati), saltati)
        if errori:
            messages.warning(request, "%s. %s utenti senza UPN valido o non aggiornabili." % (messaggio, len(errori)))
        else:
            messages.success(request, messaggio)
    except Exception as exc:
        messages.error(request, "Allineamento e-mail non riuscito: %s" % exc)
    return redirect("dashboard:directory_users")


@directory_admin_required
def directory_user(request, pk):
    utente = get_object_or_404(User, pk=pk)
    uffici_associati = GruppoOrganizzativo.objects.filter(
        django_group__user=utente,
        tipo=GruppoOrganizzativo.Tipo.ORGANIZZATIVO,
        ufficio__isnull=False,
    ).select_related("ufficio", "django_group").order_by("ufficio__nome", "nome")
    gruppi_ufficio_disponibili = GruppoOrganizzativo.objects.filter(
        tipo=GruppoOrganizzativo.Tipo.ORGANIZZATIVO,
        attivo=True,
        ufficio__attivo=True,
    ).exclude(django_group__user=utente).select_related("ufficio", "django_group").order_by("ufficio__nome", "nome")
    unita_per_ufficio = {
        unita.ufficio_id: unita
        for unita in UnitaOrganizzativaWordPress.objects.filter(
            ufficio__in=[assegnazione.ufficio for assegnazione in uffici_associati]
        ).select_related("ufficio")
    }
    for assegnazione in uffici_associati:
        assegnazione.unita_organizzativa_wordpress = unita_per_ufficio.get(assegnazione.ufficio_id)
    persone_pubbliche = PersonaleWordPress.objects.filter(
        utente=utente,
    ).prefetch_related("unita_organizzative").order_by("cognome", "nome", "titolo")
    try:
        dettaglio = DirectoryAdminService().dettaglio(utente.username)
        gruppi_automatici = set(
            GruppoOrganizzativo.objects.filter(
                tipo=GruppoOrganizzativo.Tipo.ORGANIZZATIVO
            ).values_list("directory_name", flat=True)
        )
        gruppi_automatici.add("MDAEMON")
        gruppi_ad_disponibili = [
            gruppo["name"] for gruppo in DirectoryAdminService().lista_gruppi()
            if gruppo["name"] not in gruppi_automatici and gruppo["name"] not in dettaglio["groups"]
        ]
        dominio_istituzionale = ""
        if "@" in dettaglio["email"]:
            candidato = dettaglio["email"].rsplit("@", 1)[1].lower()
            if candidato in settings.INSTITUTIONAL_EMAIL_DOMAINS:
                dominio_istituzionale = candidato
    except Exception as exc:
        dettaglio = None; gruppi_ad_disponibili = []; dominio_istituzionale = ""; messages.error(request, "Impossibile leggere AD: %s" % exc)
    return render(request, "dashboard/directory_user.html", {
        "utente": utente,
        "dettaglio": dettaglio,
        "uffici_associati": uffici_associati,
        "gruppi_ufficio_disponibili": gruppi_ufficio_disponibili,
        "domini_istituzionali": settings.INSTITUTIONAL_EMAIL_DOMAINS,
        "dominio_istituzionale": dominio_istituzionale,
        "gruppi_ad_disponibili": gruppi_ad_disponibili,
        "persone_pubbliche": persone_pubbliche,
    })


@directory_admin_required
@require_POST
def directory_action(request, pk):
    utente = get_object_or_404(User, pk=pk); service = DirectoryAdminService(); azione = request.POST.get("azione")
    try:
        messaggio_successo = "Operazione completata."
        avviso_email = None
        if azione == "anagrafica":
            first_name = request.POST.get("first_name", "").strip()
            last_name = request.POST.get("last_name", "").strip()
            personal_email = request.POST.get("personal_email", "").strip()
            service.aggiorna_anagrafica(
                utente.username,
                first_name,
                last_name,
                personal_email,
                request.POST.get("mobile", ""),
            )
            mail_istituzionale = request.POST.get("mail_istituzionale") == "on"
            dominio = request.POST.get("dominio_istituzionale", "").strip().lower()
            if mail_istituzionale and dominio not in settings.INSTITUTIONAL_EMAIL_DOMAINS:
                raise DirectoryAdminException("Selezionare un dominio valido per la mail istituzionale.")
            email_istituzionale = service.imposta_mail_istituzionale(utente.username, dominio if mail_istituzionale else None)
            gruppo_mdaemon, _ = Group.objects.get_or_create(name="MDAEMON")
            if mail_istituzionale:
                utente.groups.add(gruppo_mdaemon)
            else:
                utente.groups.remove(gruppo_mdaemon)
            User.objects.filter(pk=utente.pk).update(first_name=first_name, last_name=last_name, email=email_istituzionale or personal_email)
            messaggio_successo = "Anagrafica e impostazioni della mail istituzionale aggiornate."
        elif azione == "stato":
            service.imposta_attivo(utente.username, request.POST.get("attivo") == "true")
        elif azione == "password":
            destinatario = service.dettaglio(utente.username).get("personal_email", "").strip()
            if not destinatario:
                raise DirectoryAdminException("Impossibile reimpostare la password: l'utente non ha un'e-mail personale.")
            password = _password_provvisoria()
            service.reset_password(utente.username, password, True)
            try:
                from post_office import mail

                mail.send(
                    recipients=[destinatario],
                    sender=settings.DEFAULT_FROM_EMAIL,
                    subject="Nuova password di accesso",
                    message=(
                        "Buongiorno %s %s,\n\n"
                        "la password del suo account è stata reimpostata.\n"
                        "Username: %s\nPassword provvisoria: %s\n\n"
                        "Al primo accesso sarà richiesto di cambiare la password."
                    ) % (utente.first_name, utente.last_name, utente.username, password),
                )
            except Exception as exc:
                avviso_email = "Password reimpostata, ma l'e-mail non è stata accodata: %s" % exc
            messaggio_successo = (
                "Password reimpostata."
                if avviso_email
                else "Password reimpostata e credenziali accodate per l'invio all'e-mail personale."
            )
        elif azione == "rimuovi_ufficio":
            assegnazione = get_object_or_404(
                GruppoOrganizzativo.objects.select_related("django_group", "ufficio"),
                pk=request.POST.get("gruppo_organizzativo"),
                django_group__user=utente,
                tipo=GruppoOrganizzativo.Tipo.ORGANIZZATIVO,
                ufficio__isnull=False,
            )
            service.rimuovi_da_gruppo(utente.username, assegnazione.directory_name)
            utente.groups.remove(assegnazione.django_group)
            messaggio_successo = "Ufficio %s rimosso dall'account." % assegnazione.ufficio
        elif azione == "aggiungi_ufficio":
            assegnazione = get_object_or_404(
                GruppoOrganizzativo.objects.select_related("django_group", "ufficio"),
                pk=request.POST.get("gruppo_organizzativo"),
                tipo=GruppoOrganizzativo.Tipo.ORGANIZZATIVO,
                attivo=True,
                ufficio__attivo=True,
            )
            if utente.groups.filter(pk=assegnazione.django_group_id).exists():
                raise DirectoryAdminException("L'ufficio è già associato all'account.")
            service.aggiungi_utente_al_gruppo(utente.username, assegnazione.directory_name)
            utente.groups.add(assegnazione.django_group)
            messaggio_successo = "Ufficio %s aggiunto all'account." % assegnazione.ufficio
        elif azione == "crea_unita_organizzativa":
            ufficio = get_object_or_404(
                Ufficio.objects.distinct(),
                pk=request.POST.get("ufficio"),
                gruppi__django_group__user=utente,
                gruppi__tipo=GruppoOrganizzativo.Tipo.ORGANIZZATIVO,
            )
            esistente = UnitaOrganizzativaWordPress.objects.filter(ufficio=ufficio).first()
            if esistente:
                raise DirectoryAdminException("L'ufficio %s è già collegato all'unità organizzativa WordPress %s." % (ufficio, esistente.nome))
            unita = crea_unita_organizzativa_wordpress(ufficio)
            messaggio_successo = "Creata l'unità organizzativa %s su WordPress e collegata all'ufficio %s." % (unita.nome, ufficio.nome)
        elif azione == "aggiungi_gruppo_ad":
            nome_gruppo = request.POST.get("gruppo_ad", "").strip()
            if not nome_gruppo:
                raise DirectoryAdminException("Selezionare un gruppo AD.")
            if nome_gruppo == "MDAEMON" or GruppoOrganizzativo.objects.filter(
                tipo=GruppoOrganizzativo.Tipo.ORGANIZZATIVO,
                directory_name=nome_gruppo,
            ).exists():
                raise DirectoryAdminException("Questo gruppo è gestito automaticamente e non può essere aggiunto da qui.")
            service.aggiungi_utente_al_gruppo(utente.username, nome_gruppo)
            gruppo_locale, _ = Group.objects.get_or_create(name=nome_gruppo)
            utente.groups.add(gruppo_locale)
            messaggio_successo = "Gruppo AD %s aggiunto all'account." % nome_gruppo
        elif azione in {"accesso_remoto", "smartworking"}:
            nome_gruppo = "ACCESSO-RDP" if azione == "accesso_remoto" else "VPN_COMMON_RULES"
            abilita = request.POST.get("abilita") == "true"
            if abilita:
                service.aggiungi_utente_al_gruppo(utente.username, nome_gruppo)
                gruppo_locale, _ = Group.objects.get_or_create(name=nome_gruppo)
                utente.groups.add(gruppo_locale)
            else:
                service.rimuovi_da_gruppo(utente.username, nome_gruppo)
                gruppo_locale = Group.objects.filter(name=nome_gruppo).first()
                if gruppo_locale:
                    utente.groups.remove(gruppo_locale)
            servizio = "Accesso remoto" if azione == "accesso_remoto" else "SmartWorking"
            messaggio_successo = "%s %s." % (servizio, "abilitato" if abilita else "disabilitato")
        else: raise DirectoryAdminException("Operazione non valida.")
        AuditService.log(user=request.user, tipo="UPDATE", oggetto="ActiveDirectory:%s" % utente.username, descrizione="Operazione AD: %s." % azione, ip_address=request.META.get("REMOTE_ADDR"))
        if avviso_email:
            messages.warning(request, avviso_email)
        messages.success(request, messaggio_successo)
    except Exception as exc:
        AuditService.log(user=request.user, tipo="SYSTEM", oggetto="ActiveDirectory:%s" % utente.username, descrizione="Operazione AD non riuscita: %s; errore: %s" % (azione, exc), ip_address=request.META.get("REMOTE_ADDR"))
        messages.error(request, str(exc))
    return redirect("dashboard:directory_user", pk=utente.pk)
