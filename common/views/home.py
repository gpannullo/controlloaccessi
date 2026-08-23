from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone
from accounts.services.directory_admin_service import DirectoryAdminService
from common.module_access import (
    DirigenzaAccessMixin,
    MonitorPortineriaAccessMixin,
    PortineriaAccessMixin,
    UfficiAccessMixin,
)


@login_required
def home(request):
    """
    Pagina iniziale dell'applicazione.

    Mostra tutte le aree disponibili. I controlli
    autorizzativi vengono effettuati quando l'utente
    prova ad accedere alla singola area.
    """

    has_offices = UfficiAccessMixin.has_module_access(request.user)
    has_dirigenza = DirigenzaAccessMixin.has_module_access(request.user)
    can_portineria = PortineriaAccessMixin.has_module_access(request.user)
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
        "can_monitor": MonitorPortineriaAccessMixin.has_module_access(request.user),
        "password_expiry": password_expiry,
        "password_days_remaining": password_days_remaining,
        "password_never_expires": password_never_expires,
        "password_expiring_soon": password_expiring_soon,
    })
