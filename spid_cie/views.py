import hashlib
import hmac
import json
from datetime import timedelta

from django.contrib import messages
from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpResponseBadRequest, HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import CodiceAccessoGateway, IdentitaDigitale
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


def _gateway_signature_is_valid(request):
    config = settings.SPID_GATEWAY
    secret = config["SHARED_SECRET"].encode("utf-8")
    timestamp = request.headers.get("X-Spid-Gateway-Timestamp", "")
    signature = request.headers.get("X-Spid-Gateway-Signature", "")
    if not secret or not timestamp or not signature:
        return False
    try:
        age = abs(timezone.now().timestamp() - int(timestamp))
    except ValueError:
        return False
    if age > config["MAX_AGE_SECONDS"]:
        return False
    expected = hmac.new(secret, f"{timestamp}.".encode("ascii") + request.body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@csrf_exempt
@require_POST
def gateway_identity(request):
    """Riceve dal gateway SAML un codice e dati firmati, non dal browser."""
    if not settings.SPID_GATEWAY["ENABLED"] or not _gateway_signature_is_valid(request):
        return HttpResponseForbidden("Gateway SPID non autorizzato.")
    try:
        payload = json.loads(request.body)
        code = str(payload["code"])
        fiscal_code = str(payload["codice_fiscale"]).upper().replace("TINIT-", "")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return HttpResponseBadRequest("Dati gateway non validi.")
    if len(code) < 32 or len(fiscal_code) != 16:
        return HttpResponseBadRequest("Dati gateway non validi.")
    destination = SpidCieService.safe_next_url(payload.get("destinazione"))
    try:
        CodiceAccessoGateway.objects.create(
            codice_hash=hashlib.sha256(code.encode("utf-8")).hexdigest(),
            codice_fiscale=fiscal_code,
            nome=str(payload.get("nome", ""))[:100],
            cognome=str(payload.get("cognome", ""))[:100],
            email=str(payload.get("email", ""))[:254],
            destinazione=destination,
            scade_il=timezone.now() + timedelta(minutes=5),
        )
    except IntegrityError:
        return HttpResponseBadRequest("Codice gateway già ricevuto.")
    return JsonResponse({"ok": True})


@require_GET
def gateway_complete(request):
    code = request.GET.get("code", "")
    if not settings.SPID_GATEWAY["ENABLED"] or len(code) < 32:
        return HttpResponseBadRequest("Codice di accesso non valido.")
    code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
    with transaction.atomic():
        record = CodiceAccessoGateway.objects.select_for_update().filter(codice_hash=code_hash, usato_il__isnull=True, scade_il__gt=timezone.now()).first()
        if record is None:
            return HttpResponseBadRequest("Codice di accesso scaduto o già utilizzato.")
        record.usato_il = timezone.now()
        record.save(update_fields=["usato_il"])
    identity, _ = IdentitaDigitale.objects.update_or_create(
        provider=IdentitaDigitale.Provider.SPID,
        subject=f"fiscal:{record.codice_fiscale}",
        defaults={"codice_fiscale": record.codice_fiscale, "nome": record.nome, "cognome": record.cognome, "email": record.email},
    )
    request.session[SpidCieService.SESSION_IDENTITY_KEY] = identity.pk
    messages.success(request, "Identità SPID verificata correttamente.")
    return redirect(record.destinazione)
