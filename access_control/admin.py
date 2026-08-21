from urllib.parse import urlencode

from django.contrib import admin
from django.db.models import Count, Q
from django.http import HttpResponseRedirect

from .models import (
    CalendarioApertura,
    GruppoOrganizzativo,
    Ufficio,
)
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
        "prefisso_coda",
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

    inlines = [
        CalendarioAperturaInline,
    ]

    def numero_dipendenti(self, obj):
        utenti_ids = set()

        for gruppo in obj.gruppi.select_related(
            "django_group"
        ):
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

        for gruppo in obj.gruppi.select_related(
            "django_group"
        ):
            for utente in (
                gruppo.django_group
                .user_set
                .filter(is_active=True)
            ):
                utenti[utente.pk] = utente

        if not utenti:
            return "—"

        def etichetta(utente):
            nome_completo = (
                utente.get_full_name().strip()
            )

            return (
                nome_completo
                or utente.username
            )

        return ", ".join(
            sorted(
                (
                    etichetta(utente)
                    for utente
                    in utenti.values()
                ),
                key=str.casefold,
            )
        )

    dipendenti_agganciati.short_description = (
        "Dipendenti agganciati"
    )


@admin.register(GruppoOrganizzativo)
class GruppoOrganizzativoAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "tipo",
        "ufficio",
        "numero_utenti",
        "attivo",
        "sincronizzato",
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

    actions = (
        "attiva_gruppi",
        "disattiva_gruppi",
        "imposta_organizzativi",
        "imposta_tecnici",
        "genera_uffici",
    )

    def get_queryset(self, request):
        """
        Aggiunge al queryset il numero di utenti attivi
        appartenenti al gruppo Django.

        L'annotazione rende ordinabile la colonna
        'Dipendenti' direttamente dalla changelist.
        """
        queryset = super().get_queryset(
            request
        )

        return queryset.annotate(
            numero_utenti_attivi=Count(
                "django_group__user",
                filter=Q(
                    django_group__user__is_active=True,
                ),
                distinct=True,
            )
        )

    @admin.display(
        description="Dipendenti",
        ordering="numero_utenti_attivi",
    )
    def numero_utenti(self, obj):
        return obj.numero_utenti_attivi

    @admin.action(
        description="Attiva gruppi selezionati"
    )
    def attiva_gruppi(self, request, queryset):
        ids = list(
            queryset.values_list("pk", flat=True)
        )

        GruppoOrganizzativo.objects.filter(
            pk__in=ids
        ).update(
            attivo=True
        )

    @admin.action(
        description="Disattiva gruppi selezionati"
    )
    def disattiva_gruppi(self, request, queryset):
        ids = list(
            queryset.values_list("pk", flat=True)
        )

        GruppoOrganizzativo.objects.filter(
            pk__in=ids
        ).update(
            attivo=False
        )

    @admin.action(
        description="Imposta come Organizzativo"
    )
    def imposta_organizzativi(self, request, queryset):
        ids = list(
            queryset.values_list("pk", flat=True)
        )

        GruppoOrganizzativo.objects.filter(
            pk__in=ids
        ).update(
            tipo=GruppoOrganizzativo.Tipo.ORGANIZZATIVO
        )

    @admin.action(
        description="Imposta come Tecnico"
    )
    def imposta_tecnici(self, request, queryset):
        ids = list(
            queryset.values_list("pk", flat=True)
        )

        GruppoOrganizzativo.objects.filter(
            pk__in=ids
        ).update(
            tipo=GruppoOrganizzativo.Tipo.TECNICO
        )

    def genera_uffici(
        self,
        request,
        queryset,
    ):
        OfficeService().generate_from_groups(
            queryset
        )

    def changelist_view(
        self,
        request,
        extra_context=None,
    ):
        """
        Applica automaticamente il filtro
        'Tipo = Organizzativo' solo al primo accesso.
        """

        if (
            "tipo__exact" not in request.GET
            and "_changelist_filters"
            not in request.GET
        ):
            query = request.GET.copy()

            query["tipo__exact"] = (
                GruppoOrganizzativo
                .Tipo
                .ORGANIZZATIVO
            )

            return HttpResponseRedirect(
                f"{request.path}?"
                f"{urlencode(query)}"
            )

        return super().changelist_view(
            request,
            extra_context=extra_context,
        )
