from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone
from accounts.services.directory_admin_service import DirectoryAdminService
from visitors.permissions import is_portineria_user


@login_required
def home(request):
    """
    Pagina iniziale dell'applicazione.

    Mostra tutte le aree disponibili. I controlli
    autorizzativi vengono effettuati quando l'utente
    prova ad accedere alla singola area.
    """

    has_offices = request.user.is_superuser or request.user.groups.filter(
        gruppo_organizzativo__ufficio__isnull=False,
        gruppo_organizzativo__ufficio__attivo=True,
    ).exists()
    has_dirigenza = request.user.is_superuser or request.user.groups.filter(
        name__in={"Dirigenti", "Funzionari_EQ"},
    ).exists()
    can_portineria = request.user.is_superuser or is_portineria_user(request.user)
    password_expiry = None
    password_days_remaining = None
    password_never_expires = False
    password_expiring_soon = False
    try:
        password_info = DirectoryAdminService().dettaglio(request.user.username)
        password_expiry = password_info.get("password_expiry")
        password_never_expires = password_info.get("password_never_expires", False)
        if password_expiry and not password_never_expires:
            password_days_remaining = max(0, (timezone.localdate(password_expiry) - timezone.localdate()).days)
            password_expiring_soon = password_days_remaining <= 15
    except Exception:
        pass
    return render(request, "common/home.html", {
        "can_portineria": can_portineria,
        "can_offices": has_offices,
        "can_dirigenza": has_dirigenza,
        "can_monitor": can_portineria or has_dirigenza,
        "password_expiry": password_expiry,
        "password_days_remaining": password_days_remaining,
        "password_never_expires": password_never_expires,
        "password_expiring_soon": password_expiring_soon,
    })
