from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin

from .models import CustomUser
from prenotazioni.models import PersonaleWordPress
from prenotazioni.wordpress_connector import WordPressConnectorError, crea_persona_pubblica_wordpress


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = (
        "username",
        "first_name",
        "last_name",
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

    readonly_fields = (
        "last_login",
        "date_joined",
        "presenza_verificata_il",
        "presenza_fonte",
    )

    fieldsets = UserAdmin.fieldsets + (
        (
            "Organizzazione",
            {
                "fields": (
                    "tipo_attivita",
                    "stato_presenza",
                    "presenza_verificata_il",
                    "presenza_fonte",
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
