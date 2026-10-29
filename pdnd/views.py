import json

from django.contrib import messages
from django.shortcuts import redirect, render

from common.module_access import DirectoryAdministrationAccessMixin, module_required

from .forms import InterrogazionePDNDForm
from .services import PDNDConfigurationError, PDNDService


SERVIZI = {
    "anpr-soggetto": {"titolo": "ANPR — dati del soggetto", "descrizione": "Interroga i dati anagrafici mediante codice fiscale."},
    "anpr-famiglia": {"titolo": "ANPR — composizione famiglia", "descrizione": "Interroga la composizione della famiglia anagrafica."},
    "inps-isee": {"titolo": "INPS — attestazione ISEE", "descrizione": "Interroga l'importo dell'attestazione ISEE autorizzata."},
    "durc": {"titolo": "DURC", "descrizione": "Interroga la regolarità contributiva tramite codice fiscale o partita IVA."},
}


@module_required(DirectoryAdministrationAccessMixin)
def home(request):
    configured = PDNDService.configuration()["SERVICES"]
    servizi = [{**data, "slug": slug, "configurato": bool(configured.get(PDNDService.servizio(slug), {}).get("ENDPOINT"))} for slug, data in SERVIZI.items()]
    return render(request, "pdnd/home.html", {"servizi": servizi})


@module_required(DirectoryAdministrationAccessMixin)
def interroga(request, servizio):
    if servizio not in SERVIZI:
        messages.error(request, "Servizio PDND non disponibile.")
        return redirect("pdnd:home")
    form = InterrogazionePDNDForm(request.POST or None)
    result = None
    audit = None
    if request.method == "POST" and form.is_valid():
        try:
            result, audit = PDNDService.interroga(servizio, form.cleaned_data["identificativo"], request.user)
        except PDNDConfigurationError as exc:
            messages.error(request, str(exc))
        else:
            if audit.esito == audit.Esito.ESEGUITA:
                messages.success(request, "Interrogazione eseguita. I dati non vengono salvati nel database.")
            elif audit.esito == audit.Esito.NON_CONFIGURATA:
                messages.warning(request, "Il relativo e-service PDND non è ancora configurato.")
            else:
                messages.error(request, "L'interrogazione non è stata completata. Verifica l'audit tecnico.")
    return render(request, "pdnd/interroga.html", {"servizio": SERVIZI[servizio], "form": form, "result": json.dumps(result, indent=2, ensure_ascii=False) if result is not None else None, "audit": audit})
