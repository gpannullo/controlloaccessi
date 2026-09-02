"""Regole centralizzate di autorizzazione per i moduli applicativi."""

from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect


class ModuleAccessMixin(AccessMixin):
    """Mixin riusabile dalle class based view e dai decorator di modulo."""

    module_label = "questa area"

    @classmethod
    def has_module_access(cls, user):
        return bool(user.is_authenticated)

    @classmethod
    def denied_message(cls):
        return f"Non sei autorizzato ad accedere a {cls.module_label}."

    @classmethod
    def access_response(cls, request):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not cls.has_module_access(request.user):
            messages.error(request, cls.denied_message())
            return redirect("access_denied")
        return None

    def dispatch(self, request, *args, **kwargs):
        response = self.access_response(request)
        if response is not None:
            return response
        return super().dispatch(request, *args, **kwargs)


def module_required(access_mixin):
    """Applica la medesima policy alle function based view di un modulo."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            response = access_mixin.access_response(request)
            if response is not None:
                return response
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


class PortineriaAccessMixin(ModuleAccessMixin):
    module_label = "l'area Portineria"

    @classmethod
    def has_module_access(cls, user):
        return bool(
            user.is_authenticated
            and (
                user.is_superuser
                or user.groups.filter(
                    name__iexact=settings.PORTINERIA_GROUP_NAME,
                ).exists()
            )
        )


class UfficiAccessMixin(ModuleAccessMixin):
    module_label = "la Gestione uffici"

    @classmethod
    def has_module_access(cls, user):
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        if PortineriaAccessMixin.has_module_access(user):
            return False
        return user.groups.filter(
            gruppo_organizzativo__attivo=True,
            gruppo_organizzativo__ufficio__attivo=True,
        ).exists()


class DirigenzaAccessMixin(ModuleAccessMixin):
    module_label = "l'area Dirigenti / Funzionari EQ"
    group_names = {"Dirigenti", "Funzionari_EQ"}

    @classmethod
    def has_module_access(cls, user):
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        # L'assegnazione a Portineria è esclusiva: prevale su eventuali altri
        # gruppi e limita l'operatore a Portineria e Monitor portineria.
        if PortineriaAccessMixin.has_module_access(user):
            return False
        return user.groups.filter(name__in=cls.group_names).exists()


class MonitorPortineriaAccessMixin(ModuleAccessMixin):
    module_label = "il Monitor portineria"

    @classmethod
    def has_module_access(cls, user):
        return (
            PortineriaAccessMixin.has_module_access(user)
            or DirigenzaAccessMixin.has_module_access(user)
        )


class DirectoryAdministrationAccessMixin(ModuleAccessMixin):
    module_label = "l'Amministrazione Account"

    @classmethod
    def has_module_access(cls, user):
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return bool(
            user.is_staff
            and user.groups.filter(
                name__iexact=settings.DIRECTORY["ADMINISTRATION_GROUP"],
            ).exists()
        )


class AdminModuleAccessMiddleware:
    """Applica la policy superuser anche al Django Admin integrato."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/admin/"):
            response = DirectoryAdministrationAccessMixin.access_response(request)
            if response is not None:
                return response
        return self.get_response(request)
