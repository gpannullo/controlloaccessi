from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from accounts.services.active_directory_service import ActiveDirectoryService
from accounts.services.directory_admin_service import DirectoryAdminException, DirectoryAdminService
from access_control.models import AssegnazioneUfficio, GruppoOrganizzativo
from common.module_access import PortineriaAccessMixin


PENDING_PASSWORD_CHANGE = "initial_password_change"


def _safe_next(request, value):
    if value and url_has_allowed_host_and_scheme(value, {request.get_host()}):
        return value
    return _default_destination(request)


def _default_destination(request):
    if request.get_host().split(":", 1)[0].lower() == settings.PUBLIC_ACCOUNT_HOST:
        return reverse("my_account")
    user = getattr(request, "user", None)
    if (
        user
        and user.is_authenticated
        and not user.is_superuser
        and PortineriaAccessMixin.has_module_access(user)
    ):
        return reverse("dashboard:home")
    return reverse("home")


def _aggiorna_stato_password_locale(user):
    """Evita di mostrare fino al prossimo sync il vecchio stato AD."""
    user.password_senza_scadenza = False
    user.scadenza_password = None
    user.save(update_fields=["password_senza_scadenza", "scadenza_password"])


class DirectoryLoginView(LoginView):
    """Login AD che intercetta la password provvisoria obbligatoria."""

    template_name = "registration/login.html"

    def get_success_url(self):
        if self.request.get_host().split(":", 1)[0].lower() == settings.PUBLIC_ACCOUNT_HOST:
            return reverse("my_account")
        return self.get_redirect_url() or _default_destination(self.request)

    def post(self, request, *args, **kwargs):
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        if username and password and ActiveDirectoryService().authentication_status(username, password) == "password_change_required":
            request.session[PENDING_PASSWORD_CHANGE] = {
                "username": username,
                "next": _safe_next(request, request.POST.get("next")),
            }
            return redirect("initial_password_change")
        return super().post(request, *args, **kwargs)


@require_http_methods(["GET", "POST"])
def initial_password_change(request):
    pending = request.session.get(PENDING_PASSWORD_CHANGE)
    if not pending:
        messages.warning(request, "Accedi prima con la password provvisoria.")
        return redirect("login")

    if request.method == "POST":
        password = request.POST.get("password", "")
        confirmation = request.POST.get("password_confirmation", "")
        if len(password) < 12:
            messages.error(request, "La nuova password deve contenere almeno 12 caratteri.")
        elif password != confirmation:
            messages.error(request, "Le due password non coincidono.")
        else:
            try:
                DirectoryAdminService().cambia_password_iniziale(pending["username"], password)
                user = authenticate(request, username=pending["username"], password=password)
                if not user:
                    raise DirectoryAdminException("Password aggiornata, ma non è stato possibile completare l'accesso. Riprova ad accedere.")
                login(request, user)
                _aggiorna_stato_password_locale(user)
                destination = pending.get("next") or _default_destination(request)
                request.session.pop(PENDING_PASSWORD_CHANGE, None)
                messages.success(request, "Password aggiornata correttamente.")
                return redirect(destination)
            except Exception as exc:
                messages.error(request, "Cambio password non riuscito: %s" % exc)
    return render(request, "registration/initial_password_change.html", {"username": pending["username"]})


@login_required
@require_http_methods(["GET", "POST"])
def my_account(request):
    tab = request.GET.get("tab", "anagrafica")
    if request.method == "POST":
        request.user.email_aggiuntiva = request.POST.get("email_aggiuntiva", "").strip()
        request.user.telefono_aggiuntivo = request.POST.get("telefono_aggiuntivo", "").strip()
        request.user.save(update_fields=["email_aggiuntiva", "telefono_aggiuntivo"])
        messages.success(request, "Recapiti aggiuntivi aggiornati.")
        return redirect("%s?tab=anagrafica" % reverse("my_account"))
    try:
        dettaglio = DirectoryAdminService().dettaglio(request.user.username)
    except Exception as exc:
        dettaglio = None; messages.warning(request, "Dati directory non disponibili: %s" % exc)
    uffici = AssegnazioneUfficio.objects.filter(utente=request.user, attiva=True).select_related("ufficio", "ufficio__gruppo_operativo").order_by("ufficio__nome")
    uffici_responsabili = request.user.uffici_responsabili.filter(attivo=True).order_by("nome")
    return render(request, "accounts/my_account.html", {
        "dettaglio": dettaglio,
        "uffici": uffici,
        "uffici_responsabili": uffici_responsabili,
        "tab": tab if tab in {"anagrafica", "uffici", "abilitazioni"} else "anagrafica",
        "account_update_contact_email": settings.ACCOUNT_UPDATE_CONTACT_EMAIL,
        "is_public_account": request.get_host().split(":", 1)[0].lower() == settings.PUBLIC_ACCOUNT_HOST,
    })


@login_required
@require_http_methods(["GET", "POST"])
def change_own_password(request):
    if request.method == "POST":
        current = request.POST.get("current_password", "")
        new = request.POST.get("password", "")
        confirm = request.POST.get("password_confirmation", "")
        if len(new) < 12 or new != confirm:
            messages.error(request, "La nuova password deve avere almeno 12 caratteri e coincidere con la conferma.")
        else:
            try:
                ActiveDirectoryService().cambia_password_personale(
                    request.user.username,
                    current,
                    new,
                )
                DirectoryAdminService().rimuovi_password_senza_scadenza(
                    request.user.username
                )
                _aggiorna_stato_password_locale(request.user)
                messages.success(request, "Password aggiornata correttamente.")
                return redirect("my_account")
            except Exception as exc:
                messages.error(request, "Cambio password non riuscito: %s" % exc)
    return render(request, "accounts/change_own_password.html")


@login_required
@require_http_methods(["GET", "POST"])
def profile_completion(request):
    if request.method == "POST":
        email = request.POST.get("email_personale", "").strip()
        mobile = request.POST.get("cellulare_personale", "").strip()
        if not email or not mobile:
            messages.error(request, "E-mail personale e cellulare sono obbligatori.")
        else:
            try:
                detail = DirectoryAdminService().dettaglio(request.user.username)
                DirectoryAdminService().aggiorna_anagrafica(request.user.username, detail["first_name"], detail["last_name"], email, mobile)
                request.user.email_personale, request.user.cellulare_personale = email, mobile
                request.user.save(update_fields=["email_personale", "cellulare_personale"])
                messages.success(request, "Profilo completato correttamente.")
                return redirect(_default_destination(request))
            except Exception as exc: messages.error(request, "Aggiornamento non riuscito: %s" % exc)
    return render(request, "accounts/profile_completion.html")
