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
        return redirect("home")

    if is_portineria_user(user):
        return redirect("dashboard:home")

    return redirect("home")
