from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin

from accounts.services.directory_admin_service import (
    DirectoryAdminException,
    DirectoryAdminService,
)
from access_control.models import GruppoOrganizzativo

from .models import CustomUser
from prenotazioni.models import PersonaleWordPress
from prenotazioni.wordpress_connector import WordPressConnectorError, crea_persona_pubblica_wordpress


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = (
        "username",
        "first_name",
        "last_name",
        "badge",
        "tipo_attivita",
        "stato_presenza",
        "is_active",
        "is_staff",
    )

    list_filter = (
        "tipo_attivita",
        "stato_presenza",
        "is_active",
        "is_staff",
    )

    search_fields = UserAdmin.search_fields + ("badge",)

    readonly_fields = (
        "last_login",
        "date_joined",
        "presenza_verificata_il",
        "presenza_fonte",
        "ultima_timbratura_il",
        "ultima_timbratura_verso",
        "ultima_timbratura_causale",
    )

    fieldsets = UserAdmin.fieldsets + (
        (
            "Organizzazione",
            {
                "fields": (
                    "tipo_attivita",
                    "badge",
                    "stato_presenza",
                    "presenza_verificata_il",
                    "presenza_fonte",
                    "ultima_timbratura_il",
                    "ultima_timbratura_verso",
                    "ultima_timbratura_causale",
                )
            },
        ),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            "Organizzazione",
            {
                "fields": (
                    "tipo_attivita",
                    "badge",
                    "stato_presenza",
                )
            },
        ),
    )

    actions = (
        "imposta_amministrativisti",
        "imposta_sportellisti",
        "imposta_tecnici",
        "imposta_disuso",
        "crea_persone_pubbliche_wordpress",
    )

    def save_model(self, request, obj, form, change):
        if change and "groups" in form.changed_data:
            # save_related() viene eseguito dopo save_model(): conserviamo il
            # solo sottoinsieme di gruppi che ha una controparte AD.
            request._gruppi_ad_precedenti = set(
                GruppoOrganizzativo.objects.filter(
                    django_group__user=obj,
                ).values_list("directory_name", flat=True)
            )
        if change and "is_active" in form.changed_data:
            DirectoryAdminService().imposta_attivo(obj.username, obj.is_active)
        if change and "badge" in form.changed_data:
            DirectoryAdminService().imposta_badge(obj.username, obj.badge)
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        if change and "groups" in form.changed_data:
            gruppi_precedenti = getattr(request, "_gruppi_ad_precedenti", set())
            gruppi_correnti = set(
                GruppoOrganizzativo.objects.filter(
                    django_group__in=form.cleaned_data["groups"],
                ).values_list("directory_name", flat=True)
            )
            try:
                DirectoryAdminService().sincronizza_gruppi_selezionati(
                    form.instance.username,
                    da_aggiungere=gruppi_correnti - gruppi_precedenti,
                    da_rimuovere=gruppi_precedenti - gruppi_correnti,
                )
            except DirectoryAdminException as exc:
                self.message_user(
                    request,
                    "I gruppi non sono stati salvati: Active Directory non è stata aggiornata (%s)." % exc,
                    messages.ERROR,
                )
                # Non salviamo l'M2M locale: la modifica resta coerente con AD.
                return
        super().save_related(request, form, formsets, change)

    @admin.action(
        description="Imposta come Amministrativista",
    )
    def imposta_amministrativisti(self, request, queryset):
        queryset.update(
            tipo_attivita=CustomUser.TipoAttivita.AMMINISTRATIVISTA,
        )

    @admin.action(
        description="Imposta come Sportellista",
    )
    def imposta_sportellisti(self, request, queryset):
        queryset.update(
            tipo_attivita=CustomUser.TipoAttivita.SPORTELLISTA,
        )

    @admin.action(
        description="Imposta come Tecnico",
    )
    def imposta_tecnici(self, request, queryset):
        queryset.update(
            tipo_attivita=CustomUser.TipoAttivita.TECNICO,
        )

    @admin.action(
        description="Imposta come Disuso",
    )
    def imposta_disuso(self, request, queryset):
        queryset.update(
            tipo_attivita=CustomUser.TipoAttivita.DISUSO,
        )

    @admin.action(description="Crea le Persone pubbliche selezionate su WordPress")
    def crea_persone_pubbliche_wordpress(self, request, queryset):
        creati = gia_collegati = errori = 0
        for utente in queryset.prefetch_related("groups__gruppi_organizzativi"):
            if PersonaleWordPress.objects.filter(utente=utente).exists():
                gia_collegati += 1
                continue
            try:
                crea_persona_pubblica_wordpress(utente)
            except WordPressConnectorError as exc:
                errori += 1
                self.message_user(request, f"{utente.username}: {exc}", messages.ERROR)
            else:
                creati += 1
        livello = messages.WARNING if errori else messages.SUCCESS
        self.message_user(
            request,
            f"Create: {creati}; già collegate: {gia_collegati}; errori: {errori}.",
            livello,
        )
