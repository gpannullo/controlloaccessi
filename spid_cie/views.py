from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse

from .models import IdentitaDigitale
from .services import SpidCieConfigurationError, SpidCieService


def login(request, provider):
    provider = provider.upper()
    if provider not in IdentitaDigitale.Provider.values:
        return redirect("prenotazioni:wizard")
    next_url = SpidCieService.safe_next_url(request.GET.get("next"))
    if not SpidCieService.is_configured():
        return render(request, "spid_cie/non_configurato.html", {"next_url": next_url})
    request.session[SpidCieService.SESSION_NEXT_KEY] = next_url
    request.session[SpidCieService.SESSION_PROVIDER_KEY] = provider
    try:
        return SpidCieService.client().authorize_redirect(
            request,
            request.build_absolute_uri(reverse("spid_cie:callback")),
            ui_locales="it-IT",
        )
    except SpidCieConfigurationError as exc:
        messages.error(request, str(exc))
        return redirect(next_url)


def callback(request):
    next_url = SpidCieService.safe_next_url(
        request.session.pop(SpidCieService.SESSION_NEXT_KEY, None)
    )
    provider = request.session.pop(
        SpidCieService.SESSION_PROVIDER_KEY, IdentitaDigitale.Provider.SPID
    )
    try:
        token = SpidCieService.client().authorize_access_token(request)
        identity = SpidCieService.save_identity(token, provider)
    except Exception:
        messages.error(
            request,
            "L'accesso con identità digitale non è stato completato. Riprova.",
        )
        return redirect(next_url)
    request.session[SpidCieService.SESSION_IDENTITY_KEY] = identity.pk
    messages.success(request, "Identità digitale verificata correttamente.")
    return redirect(next_url)


def logout(request):
    request.session.pop(SpidCieService.SESSION_IDENTITY_KEY, None)
    messages.info(request, "Accesso con identità digitale terminato.")
    return redirect(SpidCieService.safe_next_url(request.GET.get("next")))
