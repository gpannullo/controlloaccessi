import hashlib
import hmac
from datetime import datetime
from hmac import compare_digest
from urllib.parse import urlencode

from django.contrib import messages
from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from spid_cie.services import AppIOService, SpidCieService

from .forms import DettagliForm, RichiedenteForm, SlotForm, UfficioForm
from .models import Prenotazione
from .services import slot_disponibili, uffici_prenotabili


SESSION_KEY = "prenotazione_wizard"


@csrf_exempt
@require_http_methods(["GET", "POST"])
def whatsapp_webhook(request):
    """Verifica Meta e ricezione sicura degli eventi WhatsApp.

    Gli eventi in ingresso non vengono ancora trattati: la risposta 200 evita
    ritentativi inutili. Quando sarà attivata la messaggistica bidirezionale,
    qui sarà aggiunta la relativa logica applicativa.
    """

    if request.method == "GET":
        mode = request.GET.get("hub.mode", "")
        verify_token = request.GET.get("hub.verify_token", "")
        challenge = request.GET.get("hub.challenge", "")
        expected_token = settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN
        if (
            mode == "subscribe"
            and expected_token
            and compare_digest(verify_token, expected_token)
        ):
            return HttpResponse(challenge, content_type="text/plain")
        return HttpResponseForbidden("Token webhook non valido.")

    # La firma verrà controllata appena sarà inserito l'App Secret Meta.
    app_secret = settings.WHATSAPP_APP_SECRET
    if app_secret:
        signature = request.headers.get("X-Hub-Signature-256", "")
        expected_signature = "sha256=" + hmac.new(
            app_secret.encode("utf-8"), request.body, hashlib.sha256
        ).hexdigest()
        if not compare_digest(signature, expected_signature):
            return HttpResponseForbidden("Firma webhook non valida.")

    return HttpResponse(status=200)


def _data(request):
    return request.session.get(SESSION_KEY, {})


def _save(request, **values):
    data = _data(request)
    data.update(values)
    request.session[SESSION_KEY] = data


def wizard(request):
    step = int(request.GET.get("step", "1"))
    step = min(max(step, 1), 5)
    data = _data(request)
    identity = SpidCieService.identity_from_session(request)
    ufficio_id = None

    if step == 1:
        form = UfficioForm(request.POST or None, initial={"ufficio": data.get("ufficio")})
        if request.method == "POST" and form.is_valid():
            _save(request, ufficio=form.cleaned_data["ufficio"].pk)
            return redirect(f"{reverse('prenotazioni:wizard')}?step=2")
    elif step == 2:
        if not data.get("ufficio"):
            return redirect(reverse("prenotazioni:wizard"))
        ufficio = get_object_or_404(uffici_prenotabili(), pk=data["ufficio"])
        ufficio_id = ufficio.pk
        form = SlotForm(request.POST or None, ufficio=ufficio, initial={"data": data.get("data")})
        if request.method == "POST" and form.is_valid():
            _save(request, data_ora=form.cleaned_data["data_ora"].isoformat(), data=form.cleaned_data["data"].isoformat())
            return redirect(f"{reverse('prenotazioni:wizard')}?step=3")
    elif step == 3:
        form = DettagliForm(request.POST or None, initial={key: data.get(key, "") for key in ("motivo", "dettagli")})
        if request.method == "POST" and form.is_valid():
            _save(request, **form.cleaned_data)
            return redirect(f"{reverse('prenotazioni:wizard')}?step=4")
    elif step == 4:
        initial = {key: data.get(key, "") for key in ("nome", "cognome", "codice_fiscale", "email", "telefono")}
        if identity:
            initial.update({"nome": identity.nome, "cognome": identity.cognome, "codice_fiscale": identity.codice_fiscale, "email": identity.email})
        form = RichiedenteForm(request.POST or None, initial=initial)
        if request.method == "POST" and form.is_valid():
            _save(request, **form.cleaned_data)
            return redirect(f"{reverse('prenotazioni:wizard')}?step=5")
    else:
        required = {"ufficio", "data_ora", "motivo", "nome", "cognome", "codice_fiscale", "email"}
        if not required.issubset(data):
            return redirect(reverse("prenotazioni:wizard"))
        form = None
        if request.method == "POST":
            ufficio = get_object_or_404(uffici_prenotabili(), pk=data["ufficio"])
            data_ora = datetime.fromisoformat(data["data_ora"])
            try:
                with transaction.atomic():
                    prenotazione = Prenotazione.objects.create(ufficio=ufficio, data_ora=data_ora, motivo=data["motivo"], dettagli=data.get("dettagli", ""), nome=data["nome"], cognome=data["cognome"], codice_fiscale=data["codice_fiscale"], email=data["email"], telefono=data.get("telefono", ""), identita_digitale=identity)
            except IntegrityError:
                messages.error(request, "Lo slot non è più disponibile. Selezionane un altro.")
                return redirect(f"{reverse('prenotazioni:wizard')}?step=2")
            # Il mancato recapito su IO non deve annullare una prenotazione valida.
            transaction.on_commit(
                lambda: AppIOService.invia_conferma_prenotazione(prenotazione)
            )
            request.session.pop(SESSION_KEY, None)
            return redirect("prenotazioni:conferma", codice=prenotazione.codice)
    gateway_login_url = ""
    if settings.SPID_GATEWAY["ENABLED"]:
        gateway_login_url = f'{settings.SPID_GATEWAY["BASE_URL"].rstrip("/")}/login/?{urlencode({"next": request.get_full_path()})}'
    return render(request, "prenotazioni/wizard.html", {"step": step, "form": form, "data": data, "identity": identity, "gateway_login_url": gateway_login_url, "ufficio_id": ufficio_id})


@require_GET
def slot_disponibili_json(request):
    try:
        ufficio = get_object_or_404(uffici_prenotabili(), pk=request.GET.get("ufficio"))
        data = datetime.fromisoformat(request.GET["data"]).date()
    except (KeyError, TypeError, ValueError):
        return JsonResponse({"slots": []})
    return JsonResponse({"slots": [{"value": slot.isoformat(), "label": slot.strftime("%H:%M")} for slot in slot_disponibili(ufficio, data)]})


def conferma(request, codice):
    prenotazione = get_object_or_404(Prenotazione, codice=codice)
    return render(request, "prenotazioni/conferma.html", {"prenotazione": prenotazione})
