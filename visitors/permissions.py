from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect
from django.urls import reverse


def is_portineria_user(user):
    """
    Restituisce True se l'utente appartiene
    al gruppo configurato come Portineria.
    """

    if not user.is_authenticated:
        return False

    group_name = getattr(
        settings,
        "PORTINERIA_GROUP_NAME",
        "Portineria",
    )

    return user.groups.filter(
        name__iexact=group_name,
    ).exists()


def portineria_required(view_func):
    """
    Consente l'accesso alle funzioni di portineria.

    I superuser possono accedere per amministrazione
    e assistenza.
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(
                request.get_full_path()
            )

        if (
            request.user.is_superuser
            or is_portineria_user(request.user)
        ):
            return view_func(
                request,
                *args,
                **kwargs,
            )

        messages.error(
            request,
            "Non sei autorizzato ad accedere all'area Portineria.",
        )

        return redirect("access_denied")

    return wrapper


def ufficio_required(view_func):
    """
    Impedisce agli utenti della portineria di accedere
    alle pagine operative degli uffici.

    L'appartenenza al gruppo Portineria prevale sulle
    eventuali altre associazioni organizzative.
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(
                request.get_full_path()
            )

        if request.user.is_superuser:
            return view_func(
                request,
                *args,
                **kwargs,
            )

        if is_portineria_user(request.user):
            messages.error(
                request,
                (
                    "Gli operatori della portineria non possono "
                    "accedere alla gestione degli uffici."
                ),
            )

            return redirect("dashboard:home")

        return view_func(
            request,
            *args,
            **kwargs,
        )

    return wrapper