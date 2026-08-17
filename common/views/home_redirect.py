from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from visitors.permissions import is_portineria_user


@login_required
def home_redirect(request):
    """
    Reindirizza l'utente autenticato verso
    l'area applicativa di competenza.
    """

    user = request.user

    if user.is_superuser:
        return redirect("dashboard:home")

    if is_portineria_user(user):
        return redirect("dashboard:home")

    if user.groups.filter(
        gruppo_organizzativo__ufficio__isnull=False,
        gruppo_organizzativo__ufficio__attivo=True,
    ).exists():
        return redirect("uffici:selezione")

    return redirect("access_denied")