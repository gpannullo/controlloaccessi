from urllib.parse import urlencode

from django.contrib import admin
from django.http import HttpResponseRedirect

from .models import Ufficio, GruppoOrganizzativo, CalendarioApertura
from .services.office_service import OfficeService


class CalendarioAperturaInline(admin.TabularInline):
    model = CalendarioApertura

    extra = 0

    ordering = (
        "giorno",
        "ora_inizio",
    )


@admin.register(Ufficio)
class UfficioAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "responsabile",
        "riceve_pubblico",
        "numero_dipendenti",
        "dipendenti_agganciati",
        "attivo",
    )

    list_filter = (
        "attivo",
        "riceve_pubblico",
    )

    search_fields = (
        "nome",
    )

    ordering = (
        "nome",
    )

    autocomplete_fields = (
        "responsabile",
    )

    inlines = [CalendarioAperturaInline]

    def numero_dipendenti(self, obj):
        utenti_ids = set()

        for gruppo in obj.gruppi.select_related("django_group"):
            utenti_ids.update(
                gruppo.django_group.user_set.filter(
                    is_active=True,
                ).values_list(
                    "pk",
                    flat=True,
                )
            )

        return len(utenti_ids)

    numero_dipendenti.short_description = "Dipendenti"

    def dipendenti_agganciati(self, obj):
        utenti = {}

        for gruppo in obj.gruppi.select_related("django_group"):
            for utente in gruppo.django_group.user_set.filter(
                is_active=True,
            ):
                utenti[utente.pk] = utente

        if not utenti:
            return "—"

        def etichetta(utente):
            nome_completo = utente.get_full_name().strip()
            return nome_completo or utente.username

        return ", ".join(
            sorted(
                (etichetta(utente) for utente in utenti.values()),
                key=str.casefold,
            )
        )

    dipendenti_agganciati.short_description = "Dipendenti agganciati"


@admin.register(GruppoOrganizzativo)
class GruppoOrganizzativoAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "tipo",
        "ufficio",
        "attivo",
        "sincronizzato",
        "numero_utenti",
    )

    autocomplete_fields = (
        "ufficio",
        "django_group",
    )

    list_filter = (
        "tipo",
        "attivo",
        "sincronizzato",
    )

    search_fields = (
        "nome",
        "directory_name",
        "note",
    )

    ordering = (
        "nome",
    )

    readonly_fields = (
        "numero_utenti",
    )

    def numero_utenti(self, obj):
        return obj.django_group.user_set.filter(is_active=True).count()

    numero_utenti.short_description = "Dipendenti"

    actions = (
        "attiva_gruppi",
        "disattiva_gruppi",
        "genera_uffici",
    )

    def attiva_gruppi(self, request, queryset):
        queryset.update(attivo=True)

    def disattiva_gruppi(self, request, queryset):
        queryset.update(attivo=False)

    def genera_uffici(self, request, queryset):
        OfficeService().generate_from_groups(queryset)



    def changelist_view(self, request, extra_context=None):
        """
        Applica automaticamente il filtro
        'Tipo = Organizzativo' solo al primo accesso.
        """

        if (
                "tipo__exact" not in request.GET
                and "_changelist_filters" not in request.GET
        ):
            query = request.GET.copy()
            query["tipo__exact"] = GruppoOrganizzativo.Tipo.ORGANIZZATIVO

            return HttpResponseRedirect(
                f"{request.path}?{urlencode(query)}"
            )

        return super().changelist_view(
            request,
            extra_context=extra_context,
        )