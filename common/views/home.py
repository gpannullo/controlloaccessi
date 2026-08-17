from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def home(request):
    """
    Pagina iniziale dell'applicazione.

    Mostra tutte le aree disponibili. I controlli
    autorizzativi vengono effettuati quando l'utente
    prova ad accedere alla singola area.
    """

    return render(
        request,
        "common/home.html",
    )